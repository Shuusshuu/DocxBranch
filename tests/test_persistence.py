"""Tests for project and document persistence."""

import hashlib
from io import BytesIO

import pytest
from docx import Document

from docxbranch.database import database_session
from docxbranch.projects import (
    ProjectError,
    create_project,
    list_projects,
)
from docxbranch.versions import (
    VersionError,
    create_initial_version,
    get_document_content,
    list_documents,
)


def make_sample_docx() -> bytes:
    """Create a valid Word document entirely in memory.

    Returns:
        Serialized DOCX bytes containing a heading and a paragraph.
    """
    document = Document()
    document.add_heading("Project Proposal", level=1)
    document.add_paragraph("This is a test document.")

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_create_and_list_projects(tmp_path):
    """Verify that created projects persist across connections.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"

    project_id = create_project(
        "Project Alpha",
        "Test description",
        db_path,
    )

    projects = list_projects(db_path)

    assert len(projects) == 1
    assert projects[0]["id"] == project_id
    assert projects[0]["name"] == "Project Alpha"
    assert projects[0]["description"] == "Test description"


def test_reject_empty_project_name(tmp_path):
    """Verify that blank project names are rejected.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"

    with pytest.raises(ProjectError):
        create_project("   ", db_path=db_path)


def test_save_and_retrieve_original_docx(tmp_path):
    """Verify that the original DOCX bytes survive database reopening.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    project_id = create_project("Project Alpha", db_path=db_path)
    original_content = make_sample_docx()

    document_id = create_initial_version(
        project_id,
        "proposal.docx",
        original_content,
        db_path,
    )

    # Each API call opens a new SQLite connection.
    restored_content = get_document_content(
        document_id,
        db_path,
    )

    assert restored_content == original_content
    assert (
        hashlib.sha256(restored_content).hexdigest()
        == hashlib.sha256(original_content).hexdigest()
    )


def test_initial_version_metadata(tmp_path):
    """Verify that a new document starts with official version 1.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    project_id = create_project("Project Alpha", db_path=db_path)
    content = make_sample_docx()

    create_initial_version(
        project_id,
        "proposal.docx",
        content,
        db_path,
    )

    documents = list_documents(project_id, db_path)

    assert len(documents) == 1
    assert documents[0]["version_number"] == 1
    assert documents[0]["name"] == "proposal.docx"
    assert documents[0]["size_bytes"] == len(content)


def test_reject_duplicate_document(tmp_path):
    """Verify that an existing initial baseline cannot be overwritten.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    project_id = create_project("Project Alpha", db_path=db_path)
    content = make_sample_docx()

    create_initial_version(
        project_id,
        "proposal.docx",
        content,
        db_path,
    )

    with pytest.raises(VersionError):
        create_initial_version(
            project_id,
            "proposal.docx",
            content,
            db_path,
        )

    assert len(list_documents(project_id, db_path)) == 1


def test_reject_nonexistent_project(tmp_path):
    """Verify that a document cannot be saved to an unknown project.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    content = make_sample_docx()

    with pytest.raises(VersionError):
        create_initial_version(
            9999,
            "proposal.docx",
            content,
            db_path,
        )


def test_reject_invalid_docx_without_partial_records(tmp_path):
    """Verify that invalid files leave no partial document records.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    project_id = create_project("Project Alpha", db_path=db_path)

    with pytest.raises(ValueError):
        create_initial_version(
            project_id,
            "invalid.docx",
            b"not a real Word file",
            db_path,
        )

    assert list_documents(project_id, db_path) == []

    with database_session(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM stored_files"
        ).fetchone()[0]

    assert count == 0


def test_detect_stored_file_corruption(tmp_path):
    """Verify that corrupted stored bytes fail the integrity check.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    project_id = create_project("Project Alpha", db_path=db_path)
    content = make_sample_docx()

    document_id = create_initial_version(
        project_id,
        "proposal.docx",
        content,
        db_path,
    )

    # Simulate corruption through direct database access.
    with database_session(db_path) as connection:
        connection.execute(
            "UPDATE stored_files SET content = ?",
            (b"corrupted content",),
        )

    with pytest.raises(VersionError):
        get_document_content(document_id, db_path)


def test_documents_are_separated_by_project(tmp_path):
    """Verify that each project lists only its own documents.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    db_path = tmp_path / "test.db"
    project_a = create_project("Project A", db_path=db_path)
    project_b = create_project("Project B", db_path=db_path)

    create_initial_version(
        project_a,
        "alpha.docx",
        make_sample_docx(),
        db_path,
    )

    documents_a = list_documents(project_a, db_path)
    documents_b = list_documents(project_b, db_path)

    assert len(documents_a) == 1
    assert documents_a[0]["name"] == "alpha.docx"
    assert documents_b == []
