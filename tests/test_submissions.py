"""Tests for employee document submissions."""

from io import BytesIO

import pytest
from docx import Document

from docxbranch.database import database_session
from docxbranch.projects import create_project
from docxbranch.submissions import (
    SubmissionError,
    create_submission,
    get_submission_content,
    list_submissions,
)
from docxbranch.versions import (
    create_initial_version,
    get_document_content,
)


def make_docx(text: str) -> bytes:
    """Create a Word document containing one paragraph.

    Args:
        text: Paragraph content.

    Returns:
        Serialized DOCX bytes.
    """
    document = Document()
    document.add_paragraph(text)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def sample_document(tmp_path):
    """Create an isolated database with one official baseline.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        Tuple containing database path, document ID,
        and original baseline bytes.
    """
    db_path = tmp_path / "test.db"
    project_id = create_project(
        "Project Alpha",
        db_path=db_path,
    )

    baseline = make_docx("Original proposal")

    document_id = create_initial_version(
        project_id,
        "proposal.docx",
        baseline,
        db_path,
    )

    return db_path, document_id, baseline


def test_employee_submission_persists(sample_document):
    """Verify that a submitted DOCX can be retrieved unchanged.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document
    modified = make_docx("Employee A changes")

    submission_id = create_submission(
        document_id,
        "Employee A",
        "proposal_A.docx",
        modified,
        db_path,
    )

    assert (
        get_submission_content(submission_id, db_path)
        == modified
    )


def test_multiple_employees_submit_independently(sample_document):
    """Verify that two employees can submit different documents.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document

    create_submission(
        document_id,
        "Employee A",
        "A.docx",
        make_docx("Change from A"),
        db_path,
    )

    create_submission(
        document_id,
        "Employee B",
        "B.docx",
        make_docx("Change from B"),
        db_path,
    )

    submissions = list_submissions(document_id, db_path)

    assert len(submissions) == 2
    assert {
        row["author"] for row in submissions
    } == {"Employee A", "Employee B"}
    assert all(
        row["status"] == "pending"
        for row in submissions
    )


def test_submission_preserves_official_baseline(sample_document):
    """Verify that submissions never overwrite the official file.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, baseline = sample_document

    create_submission(
        document_id,
        "Employee A",
        "modified.docx",
        make_docx("Modified proposal"),
        db_path,
    )

    assert (
        get_document_content(document_id, db_path)
        == baseline
    )


def test_reject_duplicate_submission(sample_document):
    """Verify that identical submissions cannot be repeated.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document
    modified = make_docx("Repeated change")

    create_submission(
        document_id,
        "Employee A",
        "modified.docx",
        modified,
        db_path,
    )

    with pytest.raises(SubmissionError):
        create_submission(
            document_id,
            "Employee A",
            "modified.docx",
            modified,
            db_path,
        )

    assert len(
        list_submissions(document_id, db_path)
    ) == 1


def test_reject_invalid_employee(sample_document):
    """Verify that unknown demo employee identities are rejected.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document

    with pytest.raises(SubmissionError):
        create_submission(
            document_id,
            "Unknown Employee",
            "modified.docx",
            make_docx("Modified"),
            db_path,
        )


def test_review_lock_blocks_new_submissions(sample_document):
    """Verify that a document review lock prevents uploads.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document

    with database_session(db_path) as connection:
        connection.execute(
            """
            UPDATE documents
            SET review_locked = 1
            WHERE id = ?
            """,
            (document_id,),
        )

    with pytest.raises(
        SubmissionError,
        match="locked for review",
    ):
        create_submission(
            document_id,
            "Employee A",
            "modified.docx",
            make_docx("Modified"),
            db_path,
        )

    assert list_submissions(document_id, db_path) == []


def test_submission_records_baseline_id(sample_document):
    """Verify that submissions reference the correct baseline ID.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document

    create_submission(
        document_id,
        "Employee A",
        "modified.docx",
        make_docx("Modified"),
        db_path,
    )

    with database_session(db_path) as connection:
        official = connection.execute(
            """
            SELECT current_version_id
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

    submission = list_submissions(
        document_id,
        db_path,
    )[0]

    assert (
        submission["baseline_version_id"]
        == official["current_version_id"]
    )


def test_invalid_docx_leaves_no_submission(sample_document):
    """Verify that invalid files create no submission records.

    Args:
        sample_document: Fixture containing an official baseline.
    """
    db_path, document_id, _ = sample_document

    with pytest.raises(ValueError):
        create_submission(
            document_id,
            "Employee A",
            "invalid.docx",
            b"invalid content",
            db_path,
        )

    assert list_submissions(document_id, db_path) == []
