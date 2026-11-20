"""Tests for transactional document review sessions."""

from io import BytesIO

import pytest
from docx import Document

from docxbranch.database import database_session
from docxbranch.projects import create_project
from docxbranch.review import (
    ReviewError,
    cancel_review,
    get_active_review,
    list_review_submissions,
    start_review,
)
from docxbranch.submissions import (
    SubmissionError,
    create_submission,
)
from docxbranch.versions import create_initial_version


def make_docx(text: str) -> bytes:
    """Build a simple DOCX document in memory.

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
def review_workspace(tmp_path):
    """Create an isolated project with two employee submissions.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Database path, document ID, and submission IDs.
    """
    db_path = tmp_path / "review_test.db"

    project_id = create_project(
        "Review Test",
        db_path=db_path,
    )

    document_id = create_initial_version(
        project_id,
        "baseline.docx",
        make_docx("Original text"),
        db_path=db_path,
    )

    submission_a = create_submission(
        document_id,
        "Employee A",
        "employee_a.docx",
        make_docx("Employee A changes"),
        db_path=db_path,
    )

    submission_b = create_submission(
        document_id,
        "Employee B",
        "employee_b.docx",
        make_docx("Employee B changes"),
        db_path=db_path,
    )

    return db_path, document_id, submission_a, submission_b


def test_start_review_creates_active_session(review_workspace):
    """Verify that a review is created for the current baseline."""
    db_path, document_id, _, _ = review_workspace

    review_id = start_review(document_id, db_path)

    active = get_active_review(document_id, db_path)

    assert active is not None
    assert active["id"] == review_id
    assert active["status"] == "active"
    assert active["baseline_number"] == 1


def test_start_review_locks_document(review_workspace):
    """Verify that starting review enables the document lock."""
    db_path, document_id, _, _ = review_workspace

    start_review(document_id, db_path)

    with database_session(db_path) as connection:
        row = connection.execute(
            "SELECT review_locked FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    assert row["review_locked"] == 1


def test_review_snapshot_contains_submissions(review_workspace):
    """Verify that the snapshot includes both employee files."""
    db_path, document_id, submission_a, submission_b = (
        review_workspace
    )

    review_id = start_review(document_id, db_path)

    snapshot = list_review_submissions(review_id, db_path)

    assert [row["id"] for row in snapshot] == [
        submission_a,
        submission_b,
    ]


def test_duplicate_review_is_rejected(review_workspace):
    """Verify that a document cannot have two active reviews."""
    db_path, document_id, _, _ = review_workspace

    start_review(document_id, db_path)

    with pytest.raises(ReviewError):
        start_review(document_id, db_path)


def test_submission_blocked_during_review(review_workspace):
    """Verify that employees cannot upload while review is active."""
    db_path, document_id, _, _ = review_workspace

    start_review(document_id, db_path)

    with pytest.raises(
        SubmissionError,
        match="locked for review",
    ):
        create_submission(
            document_id,
            "Employee A",
            "new.docx",
            make_docx("New changes"),
            db_path=db_path,
        )


def test_cancel_review_unlocks_document(review_workspace):
    """Verify that cancellation removes the document lock."""
    db_path, document_id, _, _ = review_workspace

    review_id = start_review(document_id, db_path)

    cancel_review(review_id, db_path)

    assert get_active_review(document_id, db_path) is None

    with database_session(db_path) as connection:
        row = connection.execute(
            "SELECT review_locked FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    assert row["review_locked"] == 0


def test_cancelled_review_keeps_snapshot(review_workspace):
    """Verify that cancellation retains historical review records."""
    db_path, document_id, _, _ = review_workspace

    review_id = start_review(document_id, db_path)
    before = list_review_submissions(review_id, db_path)

    cancel_review(review_id, db_path)

    after = list_review_submissions(review_id, db_path)

    assert before == after


def test_cancel_review_twice_is_rejected(review_workspace):
    """Verify that a cancelled review cannot be cancelled again."""
    db_path, document_id, _, _ = review_workspace

    review_id = start_review(document_id, db_path)
    cancel_review(review_id, db_path)

    with pytest.raises(ReviewError):
        cancel_review(review_id, db_path)


def test_upload_resumes_after_cancellation(review_workspace):
    """Verify that a cancelled review allows another submission."""
    db_path, document_id, _, _ = review_workspace

    review_id = start_review(document_id, db_path)
    cancel_review(review_id, db_path)

    new_id = create_submission(
        document_id,
        "Employee A",
        "new.docx",
        make_docx("New changes after cancellation"),
        db_path=db_path,
    )

    assert new_id > 0


def test_review_without_submissions_is_rejected(tmp_path):
    """Verify that an empty document cannot start a review."""
    db_path = tmp_path / "empty_review.db"

    project_id = create_project(
        "Empty Review",
        db_path=db_path,
    )

    document_id = create_initial_version(
        project_id,
        "baseline.docx",
        make_docx("Original"),
        db_path=db_path,
    )

    with pytest.raises(
        ReviewError,
        match="No pending submissions",
    ):
        start_review(document_id, db_path)
