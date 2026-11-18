"""Employee document submission storage for DocxBranch."""

import hashlib
import sqlite3
from pathlib import Path

from docxbranch.database import (
    DEFAULT_DB_PATH,
    database_session,
    initialize_database,
)
from docxbranch.document import read_docx
from docxbranch.versions import VersionError


DEMO_AUTHORS = ("Employee A", "Employee B")


class SubmissionError(ValueError):
    """Raised when a document submission cannot be accepted."""


def create_submission(
    document_id: int,
    author: str,
    filename: str,
    content: bytes,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Store an employee's DOCX submission against an official baseline.

    The current official baseline is resolved inside a write
    transaction. Submitting a file does not modify that baseline.

    Args:
        document_id: Document receiving the submission.
        author: Demo employee identity.
        filename: Name of the uploaded DOCX.
        content: Original uploaded DOCX bytes.
        db_path: SQLite database location.

    Returns:
        Database ID of the new submission.

    Raises:
        SubmissionError: If the author is invalid, review is locked,
            the document is missing, or the same author already
            submitted identical content against the same baseline.
        DocumentError: If the DOCX is invalid.
        sqlite3.Error: If a database operation fails.
    """
    if author not in DEMO_AUTHORS:
        raise SubmissionError("Invalid demo employee.")

    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise SubmissionError("Invalid document filename.")

    read_docx(filename, content)
    file_hash = hashlib.sha256(content).hexdigest()

    initialize_database(db_path)

    with database_session(db_path) as connection:
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
            raise SubmissionError("Document not found.")

        if document["review_locked"]:
            raise SubmissionError(
                "This document is locked for review."
            )

        baseline_id = document["current_version_id"]

        if baseline_id is None:
            raise SubmissionError(
                "Document has no official baseline."
            )

        duplicate = connection.execute(
            """
            SELECT s.id
            FROM submissions AS s
            JOIN stored_files AS f ON f.id = s.file_id
            WHERE s.document_id = ?
              AND s.baseline_version_id = ?
              AND s.author = ?
              AND f.sha256 = ?
            """,
            (document_id, baseline_id, author, file_hash),
        ).fetchone()

        if duplicate is not None:
            raise SubmissionError(
                "You already submitted this file "
                "against the current baseline."
            )

        file_cursor = connection.execute(
            """
            INSERT INTO stored_files
                (filename, content, sha256, size_bytes)
            VALUES (?, ?, ?, ?)
            """,
            (filename, content, file_hash, len(content)),
        )
        file_id = int(file_cursor.lastrowid)

        submission_cursor = connection.execute(
            """
            INSERT INTO submissions
                (document_id, baseline_version_id,
                 author, file_id)
            VALUES (?, ?, ?, ?)
            """,
            (document_id, baseline_id, author, file_id),
        )

        return int(submission_cursor.lastrowid)


def list_submissions(
    document_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """Retrieve submissions for one document.

    Args:
        document_id: Document whose submissions should be listed.
        db_path: SQLite database location.

    Returns:
        Submission metadata in newest-first order.

    Raises:
        sqlite3.Error: If the query fails.
    """
    initialize_database(db_path)

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
                f.size_bytes,
                v.version_number AS baseline_number
            FROM submissions AS s
            JOIN stored_files AS f
                ON f.id = s.file_id
            JOIN versions AS v
                ON v.id = s.baseline_version_id
                AND v.document_id = s.document_id
            WHERE s.document_id = ?
            ORDER BY s.id DESC
            """,
            (document_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def get_submission_content(
    submission_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bytes:
    """Retrieve submitted DOCX bytes after an integrity check.

    Args:
        submission_id: Submission to download.
        db_path: SQLite database location.

    Returns:
        Original submitted DOCX bytes.

    Raises:
        VersionError: If the submission is missing or the stored
            file fails its SHA-256 or size integrity check.
        sqlite3.Error: If the database query fails.
    """
    initialize_database(db_path)

    with database_session(db_path) as connection:
        row = connection.execute(
            """
            SELECT f.content, f.sha256, f.size_bytes
            FROM submissions AS s
            JOIN stored_files AS f ON f.id = s.file_id
            WHERE s.id = ?
            """,
            (submission_id,),
        ).fetchone()

        if row is None:
            raise VersionError("Submission not found.")

        content = bytes(row["content"])

        if (
            len(content) != row["size_bytes"]
            or hashlib.sha256(content).hexdigest()
            != row["sha256"]
        ):
            raise VersionError(
                "Submitted file failed the integrity check."
            )

        return content
