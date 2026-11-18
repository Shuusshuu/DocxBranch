"""Official document baseline storage and retrieval."""

import hashlib
import sqlite3
from pathlib import Path, PureWindowsPath

from docxbranch.database import (
    DEFAULT_DB_PATH,
    database_session,
    initialize_database,
)
from docxbranch.document import read_docx


class VersionError(ValueError):
    """Raised when document version management fails."""


def create_initial_version(
    project_id: int,
    filename: str,
    content: bytes,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Store a DOCX as a document's initial official baseline.

    The original DOCX bytes are stored without modification. A
    document with the same filename in the same project cannot
    receive another initial baseline through this operation.

    Args:
        project_id: ID of the project receiving the document.
        filename: Original DOCX filename.
        content: Original DOCX file bytes.
        db_path: SQLite database location.

    Returns:
        ID of the newly created document.

    Raises:
        VersionError: If the project does not exist, the filename
            is invalid, or the document already exists.
        DocumentError: If the DOCX validation fails.
        sqlite3.Error: If the database transaction fails.
    """
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or PureWindowsPath(filename).name != filename
    ):
        raise VersionError("Invalid document filename.")

    # Validate the package before starting a database transaction.
    read_docx(filename, content)

    file_hash = hashlib.sha256(content).hexdigest()

    initialize_database(db_path)

    with database_session(db_path) as connection:
        # Reserve the write transaction before checking duplicates.
        # This prevents concurrent uploads from passing the same
        # duplicate-name check.
        connection.execute("BEGIN IMMEDIATE")

        project = connection.execute(
            "SELECT id FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if project is None:
            raise VersionError("The selected project does not exist.")

        existing = connection.execute(
            """
            SELECT id
            FROM documents
            WHERE project_id = ? AND name = ?
            """,
            (project_id, filename),
        ).fetchone()

        if existing is not None:
            raise VersionError(
                "A document with this filename already exists "
                "in the selected project."
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

        document_cursor = connection.execute(
            """
            INSERT INTO documents (project_id, name)
            VALUES (?, ?)
            """,
            (project_id, filename),
        )
        document_id = int(document_cursor.lastrowid)

        version_cursor = connection.execute(
            """
            INSERT INTO versions
                (document_id, version_number, file_id)
            VALUES (?, ?, ?)
            """,
            (document_id, 1, file_id),
        )
        version_id = int(version_cursor.lastrowid)

        connection.execute(
            """
            UPDATE documents
            SET current_version_id = ?
            WHERE id = ?
            """,
            (version_id, document_id),
        )

        return document_id


def list_documents(
    project_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """List documents and current official baselines in a project.

    Args:
        project_id: ID of the selected project.
        db_path: SQLite database location.

    Returns:
        Document records containing version and file metadata.

    Raises:
        sqlite3.Error: If the database query fails.
    """
    initialize_database(db_path)

    with database_session(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                d.id,
                d.name,
                d.created_at,
                v.version_number,
                f.size_bytes,
                f.sha256
            FROM documents AS d
            JOIN versions AS v
                ON v.id = d.current_version_id
                AND v.document_id = d.id
            JOIN stored_files AS f
                ON f.id = v.file_id
            WHERE d.project_id = ?
            ORDER BY d.id DESC
            """,
            (project_id,),
        ).fetchall()

        return [dict(row) for row in rows]


def get_document_content(
    document_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bytes:
    """Retrieve and verify the current official DOCX bytes.

    Args:
        document_id: ID of the document to retrieve.
        db_path: SQLite database location.

    Returns:
        The original bytes of the current official DOCX version.

    Raises:
        VersionError: If the document is missing or its stored
            content fails the integrity check.
        sqlite3.Error: If the database query fails.
    """
    initialize_database(db_path)

    with database_session(db_path) as connection:
        row = connection.execute(
            """
            SELECT f.content, f.sha256, f.size_bytes
            FROM documents AS d
            JOIN versions AS v
                ON v.id = d.current_version_id
                AND v.document_id = d.id
            JOIN stored_files AS f
                ON f.id = v.file_id
            WHERE d.id = ?
            """,
            (document_id,),
        ).fetchone()

        if row is None:
            raise VersionError("Document not found.")

        content = bytes(row["content"])
        actual_hash = hashlib.sha256(content).hexdigest()

        if (
            actual_hash != row["sha256"]
            or len(content) != row["size_bytes"]
        ):
            raise VersionError(
                "Stored document failed the integrity check."
            )

        return content
