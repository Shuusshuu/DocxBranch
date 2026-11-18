"""Tests for SQLite database initialization and transactions."""

import sqlite3

import pytest

from docxbranch.database import (
    connect_database,
    database_session,
    initialize_database,
)


def test_initialize_database_creates_tables(tmp_path):
    """Verify that initialization creates all required tables.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with database_session(db_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {row["name"] for row in rows}

    assert {
        "projects",
        "documents",
        "versions",
        "stored_files",
    }.issubset(table_names)


def test_initialize_database_is_idempotent(tmp_path):
    """Verify that reinitialization preserves existing project records.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with database_session(db_path) as connection:
        connection.execute(
            "INSERT INTO projects (name) VALUES (?)",
            ("Test Project",),
        )

    initialize_database(db_path)

    with database_session(db_path) as connection:
        row = connection.execute(
            "SELECT name FROM projects WHERE id = 1"
        ).fetchone()

    assert row["name"] == "Test Project"


def test_foreign_key_enforcement(tmp_path):
    """Verify that documents cannot reference nonexistent projects.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with pytest.raises(sqlite3.IntegrityError):
        with database_session(db_path) as connection:
            connection.execute(
                """
                INSERT INTO documents (project_id, name)
                VALUES (?, ?)
                """,
                (9999, "Invalid Document"),
            )


def test_transaction_commit(tmp_path):
    """Verify that successful transactions persist their changes.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with database_session(db_path) as connection:
        connection.execute(
            "INSERT INTO projects (name) VALUES (?)",
            ("Committed Project",),
        )

    with database_session(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM projects"
        ).fetchone()

    assert row["count"] == 1


def test_transaction_rollback(tmp_path):
    """Verify that an exception rolls back uncommitted changes.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with pytest.raises(RuntimeError):
        with database_session(db_path) as connection:
            connection.execute(
                "INSERT INTO projects (name) VALUES (?)",
                ("Rolled Back Project",),
            )
            raise RuntimeError("Simulated failure")

    with database_session(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM projects"
        ).fetchone()

    assert row["count"] == 0


def test_connection_enables_foreign_keys(tmp_path):
    """Verify that every connection enables SQLite foreign keys.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    db_path = tmp_path / "test.db"

    connection = connect_database(db_path)
    try:
        result = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()

        assert result[0] == 1
    finally:
        connection.close()
