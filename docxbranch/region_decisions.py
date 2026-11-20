"""Persistent, single-resolution decisions for review regions.

Legacy review_decisions records are deliberately left untouched.
Existing reviews with old manifests must be cancelled and restarted.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from docxbranch.database import DEFAULT_DB_PATH
from docxbranch.decisions import DecisionError, _connect, _serialize_change
from docxbranch.regions import build_regions
from docxbranch.review import initialize_reviews


REGION_SCHEMA = """
CREATE TABLE IF NOT EXISTS region_review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    region_key TEXT NOT NULL,
    payload TEXT NOT NULL,
    decision TEXT,
    updated_at TEXT,
    UNIQUE(review_id, region_key),
    FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE RESTRICT
);
"""


def initialize_region_decisions(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Initialize region storage without changing historical decision rows."""
    initialize_reviews(db_path)
    with _connect(db_path) as connection:
        connection.executescript(REGION_SCHEMA)


def _region_payload(region) -> dict:
    """Serialize one region, retaining every contributing change."""
    return {
        "start": region.start,
        "end": region.end,
        "conflict": region.is_conflict,
        "changes_a": [_serialize_change(change) for change in region.changes_a],
        "changes_b": [_serialize_change(change) for change in region.changes_b],
    }


def register_regions(
    review_id: int,
    comparison,
    submission_a_id: int,
    submission_b_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Freeze one authoritative decision per region for a review.

    Registration is idempotent only for identical manifests. Existing
    legacy manifests are rejected rather than silently migrated.
    """
    initialize_region_decisions(db_path)
    if submission_a_id == submission_b_id:
        raise DecisionError("Two different submissions are required.")
    regions = build_regions(comparison)
    items = [_region_payload(region) for region in regions]
    manifest = json.dumps({
        "submission_a_id": submission_a_id,
        "submission_b_id": submission_b_id,
        "regions": items,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(manifest.encode("utf-8")).hexdigest()

    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        review = connection.execute(
            "SELECT status FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if review is None or review["status"] != "active":
            raise DecisionError("An active review is required.")
        legacy = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_decisions'"
        ).fetchone()
        if legacy and connection.execute(
            "SELECT 1 FROM review_decisions WHERE review_id = ? LIMIT 1", (review_id,)
        ).fetchone():
            raise DecisionError(
                "This review uses the legacy decision model. Cancel it and start a new review; historical decisions are preserved."
            )
        frozen = connection.execute(
            """SELECT rs.submission_id, s.author FROM review_submissions rs
               JOIN submissions s ON s.id = rs.submission_id
               WHERE rs.review_id = ?""", (review_id,)
        ).fetchall()
        authors = {row["submission_id"]: row["author"] for row in frozen}
        if (authors.get(submission_a_id) != "Employee A"
                or authors.get(submission_b_id) != "Employee B"):
            raise DecisionError("Selected A/B submissions must belong to the frozen review snapshot.")
        previous = connection.execute(
            "SELECT payload FROM region_review_items WHERE review_id=? AND region_key='_manifest'",
            (review_id,),
        ).fetchone()
        if previous is not None:
            if previous["payload"] != manifest:
                raise DecisionError("Frozen region manifest cannot be replaced.")
            connection.execute("COMMIT")
            return len(items)
        if connection.execute(
            "SELECT 1 FROM region_review_items WHERE review_id=? LIMIT 1", (review_id,)
        ).fetchone():
            raise DecisionError("Unexpected region items exist without a manifest.")
        connection.execute(
            "INSERT INTO region_review_items (review_id,region_key,payload) VALUES (?,?,?)",
            (review_id, "_manifest", manifest),
        )
        for index, item in enumerate(items, start=1):
            connection.execute(
                "INSERT INTO region_review_items (review_id,region_key,payload) VALUES (?,?,?)",
                (review_id, f"R:{index}", json.dumps(item, ensure_ascii=False, sort_keys=True)),
            )
        connection.execute("COMMIT")
        return len(items)
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def get_region_selection(
    review_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict | None:
    """Read the A/B submission IDs frozen into a region review manifest.

    Args:
        review_id: Review session ID.
        db_path: Location of the SQLite database.

    Returns:
        Frozen submission IDs, or None before region registration.
    """
    initialize_region_decisions(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            """SELECT payload FROM region_review_items
               WHERE review_id = ? AND region_key = '_manifest'""",
            (review_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        return {
            "submission_a_id": payload["submission_a_id"],
            "submission_b_id": payload["submission_b_id"],
        }


def list_region_decisions(review_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    """List all region items and their saved resolutions."""
    initialize_region_decisions(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            """SELECT region_key, payload, decision, updated_at
               FROM region_review_items
               WHERE review_id=? AND region_key != '_manifest' ORDER BY id""",
            (review_id,),
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


def save_region_decision(
    review_id: int, region_key: str, decision: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Save one authoritative choice for an active region."""
    initialize_region_decisions(db_path)
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT i.payload, r.status FROM region_review_items i
               JOIN reviews r ON r.id=i.review_id
               WHERE i.review_id=? AND i.region_key=?""",
            (review_id, region_key),
        ).fetchone()
        if row is None or region_key == "_manifest":
            raise DecisionError("Review region not found.")
        if row["status"] != "active":
            raise DecisionError("Decisions require an active review.")
        payload = json.loads(row["payload"])
        allowed = ({"baseline", "A", "B"} if payload["conflict"]
                   else {"baseline", "A"} if payload["changes_a"]
                   else {"baseline", "B"})
        if decision not in allowed:
            raise DecisionError("Invalid resolution for this region.")
        connection.execute(
            """UPDATE region_review_items SET decision=?, updated_at=CURRENT_TIMESTAMP
               WHERE review_id=? AND region_key=?""",
            (decision, review_id, region_key),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def get_region_progress(review_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    """Report completion only after all registered regions are resolved."""
    initialize_region_decisions(db_path)
    with _connect(db_path) as connection:
        registered = connection.execute(
            "SELECT 1 FROM region_review_items WHERE review_id=? AND region_key='_manifest'",
            (review_id,),
        ).fetchone() is not None
        row = connection.execute(
            """SELECT COUNT(*) AS total, COUNT(decision) AS decided
               FROM region_review_items WHERE review_id=? AND region_key!='_manifest'""",
            (review_id,),
        ).fetchone()
        return {
            "registered": registered,
            "total": row["total"],
            "decided": row["decided"],
            "remaining": row["total"] - row["decided"],
            "complete": registered and row["total"] == row["decided"],
        }
