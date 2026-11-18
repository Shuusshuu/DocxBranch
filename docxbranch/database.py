"""SQLite database configuration and schema for DocxBranch."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "docxbranch.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    current_version_id INTEGER,
    review_locked INTEGER NOT NULL DEFAULT 0
        CHECK (review_locked IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES projects(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (current_version_id)
        REFERENCES versions(id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS stored_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    content BLOB NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL
        CHECK (version_number >= 1),
    file_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (document_id)
        REFERENCES documents(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (file_id)
        REFERENCES stored_files(id)
        ON DELETE RESTRICT,

    UNIQUE (document_id, version_number),
    UNIQUE (document_id, id)
);

CREATE INDEX IF NOT EXISTS idx_documents_project
    ON documents(project_id);

CREATE INDEX IF NOT EXISTS idx_versions_document
    ON versions(document_id);
"""


def connect_database(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled.

    Args:
        db_path: Location of the SQLite database file. The default
            location is the project root directory.

    Returns:
        An open SQLite connection configured to return rows with
        dictionary-like column access.

    Raises:
        sqlite3.Error: If SQLite cannot open or configure the database.
    """
    connection = sqlite3.connect(str(db_path))
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except Exception:
        connection.close()
        raise


def initialize_database(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Create the database tables and indexes if they do not exist.

    The operation is idempotent: running it repeatedly does not
    delete existing records or recreate existing tables.

    Args:
        db_path: Location of the database to initialize.

    Raises:
        sqlite3.Error: If the schema cannot be initialized.
    """
    connection = connect_database(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


@contextmanager
def database_session(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> Iterator[sqlite3.Connection]:
    """Provide a database connection with transaction management.

    Changes are committed when the context exits normally and rolled
    back if an exception occurs.

    Args:
        db_path: Location of the database file.

    Yields:
        An open SQLite connection.

    Raises:
        sqlite3.Error: If a database operation or commit fails.
    """
    connection = connect_database(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
