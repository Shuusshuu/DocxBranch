"""Project creation and retrieval for DocxBranch."""

import sqlite3
from pathlib import Path

from docxbranch.database import (
    DEFAULT_DB_PATH,
    database_session,
    initialize_database,
)


class ProjectError(ValueError):
    """Raised when a project operation is invalid."""


def create_project(
    name: str,
    description: str = "",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Create a project and return its database ID.

    Args:
        name: Project name, between 1 and 100 characters.
        description: Optional project description.
        db_path: SQLite database location.

    Returns:
        The newly created project's integer ID.

    Raises:
        ProjectError: If the project name is invalid.
        sqlite3.Error: If the database operation fails.
    """
    name = name.strip()
    description = description.strip()

    if not name or len(name) > 100:
        raise ProjectError(
            "Project name must contain 1 to 100 characters."
        )

    initialize_database(db_path)

    with database_session(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO projects (name, description)
            VALUES (?, ?)
            """,
            (name, description),
        )
        return int(cursor.lastrowid)


def list_projects(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """Retrieve all projects in descending creation order.

    Args:
        db_path: SQLite database location.

    Returns:
        Project records represented as dictionaries.

    Raises:
        sqlite3.Error: If the query fails.
    """
    initialize_database(db_path)

    with database_session(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, name, description, created_at
            FROM projects
            ORDER BY id DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]
