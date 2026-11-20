"""Tests for persistent review decisions."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document

from docxbranch.projects import create_project
from docxbranch.versions import create_initial_version
from docxbranch.submissions import create_submission
from docxbranch.review import start_review, cancel_review
from docxbranch.diff import compare_docx_bytes
from docxbranch.decisions import (
    DecisionError,
    get_decision_progress,
    list_decisions,
    register_review_items,
    save_decision,
)


def make_docx(text: str) -> bytes:
    """Create an in-memory DOCX containing one paragraph."""
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def workspace(tmp_path):
    """Create a complete isolated review workspace."""
    db_path = tmp_path / "decisions.db"

    baseline = make_docx("Original paragraph")
    employee_a = make_docx("Employee A paragraph")
    employee_b = make_docx("Employee B paragraph")

    project_id = create_project(
        "Decision Tests",
        db_path=db_path,
    )

    document_id = create_initial_version(
        project_id,
        "baseline.docx",
        baseline,
        db_path=db_path,
    )

    submission_a_id = create_submission(
        document_id,
        "Employee A",
        "a.docx",
        employee_a,
        db_path=db_path,
    )

    submission_b_id = create_submission(
        document_id,
        "Employee B",
        "b.docx",
        employee_b,
        db_path=db_path,
    )

    review_id = start_review(document_id, db_path)

    comparison = compare_docx_bytes(
        "baseline.docx",
        baseline,
        "a.docx",
        employee_a,
        "b.docx",
        employee_b,
    )

    return SimpleNamespace(
        db_path=db_path,
        review_id=review_id,
        submission_a_id=submission_a_id,
        submission_b_id=submission_b_id,
        comparison=comparison,
    )


def prepare(workspace) -> None:
    """Register the comparison manifest for the test review."""
    register_review_items(
        workspace.review_id,
        workspace.comparison,
        workspace.submission_a_id,
        workspace.submission_b_id,
        workspace.db_path,
    )


def test_review_items_are_registered(workspace):
    """Verify that all changes and conflicts are registered."""
    prepare(workspace)

    items = list_decisions(
        workspace.review_id,
        workspace.db_path,
    )

    assert len(items) == (
        len(workspace.comparison.changes_a)
        + len(workspace.comparison.changes_b)
        + len(workspace.comparison.conflicts)
    )


def test_decisions_persist(workspace):
    """Verify that a saved decision survives another database read."""
    prepare(workspace)

    save_decision(
        workspace.review_id,
        "A:0",
        "accept",
        workspace.db_path,
    )

    items = list_decisions(
        workspace.review_id,
        workspace.db_path,
    )

    selected = next(
        item for item in items
        if item["item_key"] == "A:0"
    )

    assert selected["decision"] == "accept"


def test_decision_can_be_changed(workspace):
    """Verify that reviewers may revise an active decision."""
    prepare(workspace)

    save_decision(
        workspace.review_id,
        "A:0",
        "accept",
        workspace.db_path,
    )

    save_decision(
        workspace.review_id,
        "A:0",
        "reject",
        workspace.db_path,
    )

    selected = next(
        item for item in list_decisions(
            workspace.review_id,
            workspace.db_path,
        )
        if item["item_key"] == "A:0"
    )

    assert selected["decision"] == "reject"


def test_invalid_decision_is_rejected(workspace):
    """Verify that an unsupported decision cannot be saved."""
    prepare(workspace)

    with pytest.raises(DecisionError):
        save_decision(
            workspace.review_id,
            "A:0",
            "baseline",
            workspace.db_path,
        )


def test_progress_requires_every_decision(workspace):
    """Verify that completion requires decisions for every item."""
    prepare(workspace)

    items = list_decisions(
        workspace.review_id,
        workspace.db_path,
    )

    initial = get_decision_progress(
        workspace.review_id,
        workspace.db_path,
    )

    assert initial["registered"] is True
    assert initial["complete"] is False

    for item in items:
        choice = (
            "baseline"
            if item["item_type"] == "conflict"
            else "accept"
        )

        save_decision(
            workspace.review_id,
            item["item_key"],
            choice,
            workspace.db_path,
        )

    completed = get_decision_progress(
        workspace.review_id,
        workspace.db_path,
    )

    assert completed["complete"] is True
    assert completed["remaining"] == 0


def test_manifest_cannot_be_replaced(workspace):
    """Verify that another submission order cannot replace a manifest."""
    prepare(workspace)

    with pytest.raises(DecisionError):
        register_review_items(
            workspace.review_id,
            workspace.comparison,
            workspace.submission_b_id,
            workspace.submission_a_id,
            workspace.db_path,
        )


def test_cancelled_review_rejects_decisions(workspace):
    """Verify that cancelled reviews no longer accept changes."""
    prepare(workspace)
    cancel_review(
        workspace.review_id,
        workspace.db_path,
    )

    with pytest.raises(DecisionError):
        save_decision(
            workspace.review_id,
            "A:0",
            "accept",
            workspace.db_path,
        )


def test_conflict_decision_is_saved(workspace):
    """Verify that a conflict may select the official baseline."""
    prepare(workspace)

    conflicts = [
        item for item in list_decisions(
            workspace.review_id,
            workspace.db_path,
        )
        if item["item_type"] == "conflict"
    ]

    assert conflicts

    save_decision(
        workspace.review_id,
        conflicts[0]["item_key"],
        "baseline",
        workspace.db_path,
    )

    updated = list_decisions(
        workspace.review_id,
        workspace.db_path,
    )

    assert next(
        item for item in updated
        if item["item_key"] == conflicts[0]["item_key"]
    )["decision"] == "baseline"
