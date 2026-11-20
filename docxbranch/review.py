"""Transactional review sessions for DocxBranch."""

import sqlite3
from pathlib import Path

from docxbranch.database import (
    DEFAULT_DB_PATH,
    database_session,
    initialize_database,
)


class ReviewError(ValueError):
    """Raised when a review operation is not permitted."""


REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    baseline_version_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'cancelled', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    FOREIGN KEY (document_id)
        REFERENCES documents(id) ON DELETE RESTRICT,
    FOREIGN KEY (baseline_version_id)
        REFERENCES versions(id) ON DELETE RESTRICT,
    FOREIGN KEY (document_id, baseline_version_id)
        REFERENCES versions(document_id, id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS review_submissions (
    review_id INTEGER NOT NULL,
    submission_id INTEGER NOT NULL,
    PRIMARY KEY (review_id, submission_id),
    FOREIGN KEY (review_id)
        REFERENCES reviews(id) ON DELETE RESTRICT,
    FOREIGN KEY (submission_id)
        REFERENCES submissions(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_review
ON reviews(document_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_reviews_document
ON reviews(document_id, id);
"""


def initialize_reviews(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Create the review tables and their indexes.

    Args:
        db_path: Location of the SQLite database.
    """
    initialize_database(db_path)

    with database_session(db_path) as connection:
        connection.executescript(REVIEW_SCHEMA)


def start_review(
    document_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Freeze pending submissions and lock one document.

    Only pending submissions based on the current official
    version are included in the review snapshot.

    Args:
        document_id: Document to review.
        db_path: Location of the SQLite database.

    Returns:
        ID of the newly created review.

    Raises:
        ReviewError: If the document cannot enter review.
    """
    initialize_reviews(db_path)

    with database_session(db_path) as connection:
        # Reserve the write transaction before checking the lock.
        # This prevents two reviewers from starting simultaneously.
        connection.execute("BEGIN IMMEDIATE")

        document = connection.execute(
            """
            SELECT current_version_id, review_locked
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

        if document is None:
            raise ReviewError("Document not found.")

        if document["review_locked"]:
            raise ReviewError(
                "This document is already locked for review."
            )

        baseline_id = document["current_version_id"]

        if baseline_id is None:
            raise ReviewError(
                "Document has no official baseline."
            )

        existing_review = connection.execute(
            """
            SELECT id
            FROM reviews
            WHERE document_id = ?
              AND status = 'active'
            """,
            (document_id,),
        ).fetchone()

        if existing_review is not None:
            raise ReviewError(
                "An active review already exists."
            )

        submissions = connection.execute(
            """
            SELECT id
            FROM submissions
            WHERE document_id = ?
              AND baseline_version_id = ?
              AND status = 'pending'
            ORDER BY id
            """,
            (document_id, baseline_id),
        ).fetchall()

        if not submissions:
            raise ReviewError(
                "No pending submissions for the current baseline."
            )

        cursor = connection.execute(
            """
            INSERT INTO reviews (
                document_id,
                baseline_version_id,
                status
            )
            VALUES (?, ?, 'active')
            """,
            (document_id, baseline_id),
        )

        review_id = int(cursor.lastrowid)

        connection.executemany(
            """
            INSERT INTO review_submissions (
                review_id,
                submission_id
            )
            VALUES (?, ?)
            """,
            [
                (review_id, row["id"])
                for row in submissions
            ],
        )

        connection.execute(
            """
            UPDATE documents
            SET review_locked = 1
            WHERE id = ?
            """,
            (document_id,),
        )

        return review_id


def get_active_review(
    document_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict | None:
    """Retrieve the active review for a document.

    Args:
        document_id: Document to inspect.
        db_path: Location of the SQLite database.

    Returns:
        Review metadata, or None if no review is active.
    """
    initialize_reviews(db_path)

    with database_session(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                r.id,
                r.document_id,
                r.baseline_version_id,
                r.status,
                r.created_at,
                v.version_number AS baseline_number
            FROM reviews AS r
            JOIN versions AS v
              ON v.id = r.baseline_version_id
             AND v.document_id = r.document_id
            WHERE r.document_id = ?
              AND r.status = 'active'
            """,
            (document_id,),
        ).fetchone()

        return dict(row) if row is not None else None


def list_review_submissions(
    review_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return the submissions frozen into one review.

    Args:
        review_id: Review whose snapshot should be retrieved.
        db_path: Location of the SQLite database.

    Returns:
        Submission metadata ordered by submission ID.
    """
    initialize_reviews(db_path)

    with database_session(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                s.id,
                s.document_id,
                s.baseline_version_id,
                s.author,
                s.status,
                s.created_at,
                f.filename,
                f.sha256,
                f.size_bytes
            FROM review_submissions AS rs
            JOIN reviews AS r
              ON r.id = rs.review_id
            JOIN submissions AS s
              ON s.id = rs.submission_id
             AND s.document_id = r.document_id
             AND s.baseline_version_id = r.baseline_version_id
            JOIN stored_files AS f
              ON f.id = s.file_id
            WHERE rs.review_id = ?
            ORDER BY s.id
            """,
            (review_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def cancel_review(
    review_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Cancel an active review and unlock its document.

    Cancellation retains the review and submission snapshot
    for audit purposes. It does not approve any changes.

    Args:
        review_id: Review to cancel.
        db_path: Location of the SQLite database.

    Raises:
        ReviewError: If the review is missing or not active.
    """
    initialize_reviews(db_path)

    with database_session(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        review = connection.execute(
            """
            SELECT id, document_id, status
            FROM reviews
            WHERE id = ?
            """,
            (review_id,),
        ).fetchone()

        if review is None:
            raise ReviewError("Review not found.")

        if review["status"] != "active":
            raise ReviewError(
                "Only an active review can be cancelled."
            )

        cursor = connection.execute(
            """
            UPDATE reviews
            SET status = 'cancelled',
                closed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'active'
            """,
            (review_id,),
        )

        if cursor.rowcount != 1:
            raise ReviewError(
                "Failed to cancel the active review."
            )

        connection.execute(
            """
            UPDATE documents
            SET review_locked = 0
            WHERE id = ?
            """,
            (review["document_id"],),
        )
