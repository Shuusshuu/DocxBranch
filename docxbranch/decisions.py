"""Persistent reviewer decisions for frozen DOCX comparisons."""

import hashlib
import json
import sqlite3
from pathlib import Path

from docxbranch.database import DEFAULT_DB_PATH
from docxbranch.review import initialize_reviews


class DecisionError(ValueError):
    """Raised when a review decision is invalid or unauthorized."""


DECISION_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    item_key TEXT NOT NULL,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('change', 'conflict')),
    source TEXT NOT NULL,
    payload TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    decision TEXT,
    updated_at TEXT,
    UNIQUE (review_id, item_key),
    FOREIGN KEY (review_id)
        REFERENCES reviews(id) ON DELETE RESTRICT
);
"""


def _connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement."""
    connection = sqlite3.connect(
        str(db_path),
        timeout=30,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_decisions(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Create persistent review-decision storage."""
    initialize_reviews(db_path)

    connection = _connect(db_path)
    try:
        connection.executescript(DECISION_SCHEMA)
    finally:
        connection.close()


def _serialize_change(change) -> dict:
    """Convert a paragraph change into stable JSON-compatible data."""
    return {
        "kind": change.kind,
        "start": change.start,
        "end": change.end,
        "original": list(change.original),
        "modified": list(change.modified),
    }


def _make_item(key: str, item_type: str, source: str, data: dict) -> dict:
    """Build a canonical, fingerprinted review item."""
    payload = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return {
        "item_key": key,
        "item_type": item_type,
        "source": source,
        "payload": payload,
        "fingerprint": fingerprint,
    }


def build_review_items(comparison) -> list[dict]:
    """Build review items from all changes and detected conflicts.

    Every individual change is included, including changes that
    participate in conflicts. Conflict choices are stored separately.

    The future merge engine must use conflict decisions to resolve
    overlapping changes rather than blindly applying both edits.
    """
    items = []

    for source, changes in (
        ("A", comparison.changes_a),
        ("B", comparison.changes_b),
    ):
        for index, change in enumerate(changes):
            items.append(
                _make_item(
                    f"{source}:{index}",
                    "change",
                    source,
                    _serialize_change(change),
                )
            )

    for index, conflict in enumerate(comparison.conflicts):
        items.append(
            _make_item(
                f"C:{index}",
                "conflict",
                "A/B",
                {
                    "employee_a": _serialize_change(
                        conflict.change_a
                    ),
                    "employee_b": _serialize_change(
                        conflict.change_b
                    ),
                },
            )
        )

    return items


def register_review_items(
    review_id: int,
    comparison,
    submission_a_id: int,
    submission_b_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Register the immutable comparison manifest for an active review.

    Both submissions must belong to the review's frozen snapshot.
    The first registration freezes the manifest. Subsequent calls
    must supply exactly the same manifest and submission order.

    Returns:
        Number of registered review items.
    """
    initialize_decisions(db_path)

    if submission_a_id == submission_b_id:
        raise DecisionError("Two different submissions are required.")

    items = build_review_items(comparison)

    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")

        review = connection.execute(
            """
            SELECT id, status
            FROM reviews
            WHERE id = ?
            """,
            (review_id,),
        ).fetchone()

        if review is None or review["status"] != "active":
            raise DecisionError("An active review is required.")

        snapshot = connection.execute(
            """
            SELECT rs.submission_id, s.author
            FROM review_submissions AS rs
            JOIN submissions AS s ON s.id = rs.submission_id
            WHERE rs.review_id = ?
            """,
            (review_id,),
        ).fetchall()

        frozen_ids = {row["submission_id"] for row in snapshot}
        author_by_id = {
            row["submission_id"]: row["author"]
            for row in snapshot
        }

        if (
            submission_a_id not in frozen_ids
            or submission_b_id not in frozen_ids
        ):
            raise DecisionError(
                "Both submissions must belong to the frozen snapshot."
            )

        if (
            author_by_id[submission_a_id] != "Employee A"
            or author_by_id[submission_b_id] != "Employee B"
        ):
            raise DecisionError(
                "Submission A and B must match their employee roles."
            )

        manifest = _make_item(
            "_manifest",
            "change",
            "system",
            {
                "submission_a_id": submission_a_id,
                "submission_b_id": submission_b_id,
                "items": [
                    {
                        "key": item["item_key"],
                        "fingerprint": item["fingerprint"],
                    }
                    for item in items
                ],
            },
        )

        existing_manifest = connection.execute(
            """
            SELECT fingerprint
            FROM review_decisions
            WHERE review_id = ? AND item_key = '_manifest'
            """,
            (review_id,),
        ).fetchone()

        if existing_manifest is not None:
            if existing_manifest["fingerprint"] != manifest["fingerprint"]:
                raise DecisionError(
                    "The review manifest is already frozen "
                    "and cannot be replaced."
                )

            connection.execute("COMMIT")
            return len(items)

        existing_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM review_decisions
            WHERE review_id = ?
            """,
            (review_id,),
        ).fetchone()["count"]

        if existing_count:
            raise DecisionError(
                "Unexpected review items exist without a manifest."
            )

        for item in [manifest, *items]:
            connection.execute(
                """
                INSERT INTO review_decisions (
                    review_id, item_key, item_type,
                    source, payload, fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    item["item_key"],
                    item["item_type"],
                    item["source"],
                    item["payload"],
                    item["fingerprint"],
                ),
            )

        connection.execute("COMMIT")
        return len(items)

    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def save_decision(
    review_id: int,
    item_key: str,
    decision: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Save or replace one decision in an active review.

    Ordinary changes accept 'accept' or 'reject'.
    Conflicts accept 'baseline', 'A', or 'B'.
    """
    initialize_decisions(db_path)

    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT d.item_type, r.status
            FROM review_decisions AS d
            JOIN reviews AS r ON r.id = d.review_id
            WHERE d.review_id = ? AND d.item_key = ?
            """,
            (review_id, item_key),
        ).fetchone()

        if row is None or item_key == "_manifest":
            raise DecisionError("Review item not found.")

        if row["status"] != "active":
            raise DecisionError(
                "Decisions can only be changed during active review."
            )

        allowed = (
            {"accept", "reject"}
            if row["item_type"] == "change"
            else {"baseline", "A", "B"}
        )

        if decision not in allowed:
            raise DecisionError(
                f"Invalid decision for {row['item_type']}."
            )

        connection.execute(
            """
            UPDATE review_decisions
            SET decision = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE review_id = ? AND item_key = ?
            """,
            (decision, review_id, item_key),
        )

        connection.execute("COMMIT")

    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def list_decisions(
    review_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return review items with their persisted decisions."""
    initialize_decisions(db_path)

    connection = _connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT item_key, item_type, source,
                   payload, decision, updated_at
            FROM review_decisions
            WHERE review_id = ?
              AND item_key != '_manifest'
            ORDER BY id
            """,
            (review_id,),
        ).fetchall()

        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]
    finally:
        connection.close()


def get_decision_progress(
    review_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """Calculate whether every registered item has a decision."""
    initialize_decisions(db_path)

    connection = _connect(db_path)
    try:
        manifest = connection.execute(
            """
            SELECT id
            FROM review_decisions
            WHERE review_id = ? AND item_key = '_manifest'
            """,
            (review_id,),
        ).fetchone()

        if manifest is None:
            return {
                "registered": False,
                "total": 0,
                "decided": 0,
                "remaining": 0,
                "complete": False,
            }

        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(decision) AS decided
            FROM review_decisions
            WHERE review_id = ?
              AND item_key != '_manifest'
            """,
            (review_id,),
        ).fetchone()

        total = row["total"]
        decided = row["decided"]

        return {
            "registered": True,
            "total": total,
            "decided": decided,
            "remaining": total - decided,
            "complete": total == decided,
        }
    finally:
        connection.close()
