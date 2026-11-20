"""Regression tests for region-based reviewer decisions."""

from dataclasses import replace

import pytest

from docxbranch.diff import Change, Comparison, Conflict
from docxbranch.regions import build_regions
from docxbranch.region_decisions import (
    register_regions, list_region_decisions, save_region_decision,
    get_region_progress,
)
from docxbranch.decisions import DecisionError
from test_decisions import workspace as review_workspace


def change(start, end, label):
    """Build a baseline-relative replacement or insertion."""
    return Change("insert" if start == end else "replace", start, end, (), (label,))


def comparison(a, b):
    """Construct a comparison with overlap diagnostics."""
    return Comparison(tuple(a), tuple(b), ())


def test_same_location_is_one_region():
    """One conflict must require exactly one decision."""
    regions = build_regions(comparison([change(0, 1, "105")], [change(0, 1, "110")]))
    assert len(regions) == 1
    assert regions[0].is_conflict


def test_independent_edits_remain_separate():
    """Unrelated edits must each require their own decision."""
    regions = build_regions(comparison([change(0, 1, "A")], [change(2, 3, "B")]))
    assert len(regions) == 2
    assert not any(region.is_conflict for region in regions)


def test_transitive_overlap_is_one_region():
    """Connected overlaps must not yield contradictory decisions."""
    regions = build_regions(comparison(
        [change(0, 2, "A1"), change(3, 5, "A2")],
        [change(1, 4, "B")],
    ))
    assert len(regions) == 1
    assert (regions[0].start, regions[0].end) == (0, 5)
    assert len(regions[0].changes_a) == 2


def test_insertions_at_same_boundary_conflict():
    """Simultaneous insertions must resolve together."""
    regions = build_regions(comparison([change(1, 1, "A")], [change(1, 1, "B")]))
    assert len(regions) == 1 and regions[0].is_conflict


def test_adjacent_replacements_do_not_conflict():
    """Adjacent replacements should remain independent."""
    regions = build_regions(comparison([change(0, 1, "A")], [change(1, 2, "B")]))
    assert len(regions) == 2


def test_deletion_and_replacement_conflict():
    """Overlapping deletion and replacement must share a region."""
    deletion = Change("delete", 0, 1, ("old",), ())
    regions = build_regions(comparison([deletion], [change(0, 1, "new")]))
    assert len(regions) == 1 and regions[0].is_conflict


def test_region_decision_persists(review_workspace):
    """One saved resolution must survive a new database read."""
    w = review_workspace
    assert register_regions(w.review_id, w.comparison, w.submission_a_id,
                            w.submission_b_id, w.db_path) == 1
    save_region_decision(w.review_id, "R:1", "A", w.db_path)
    assert list_region_decisions(w.review_id, w.db_path)[0]["decision"] == "A"
    assert get_region_progress(w.review_id, w.db_path)["complete"]


def test_region_rejects_invalid_choice(review_workspace):
    """Region decisions must only accept valid sources."""
    w = review_workspace
    register_regions(w.review_id, w.comparison, w.submission_a_id,
                     w.submission_b_id, w.db_path)
    with pytest.raises(DecisionError):
        save_region_decision(w.review_id, "R:1", "accept", w.db_path)


def test_manifest_is_immutable(review_workspace):
    """A different submission order must not replace a frozen manifest."""
    w = review_workspace
    register_regions(w.review_id, w.comparison, w.submission_a_id,
                     w.submission_b_id, w.db_path)
    with pytest.raises(DecisionError):
        register_regions(w.review_id, w.comparison, w.submission_b_id,
                         w.submission_a_id, w.db_path)


def test_legacy_decisions_are_preserved(review_workspace):
    """An old review must be restarted rather than silently migrated."""
    from docxbranch.decisions import register_review_items, list_decisions
    w = review_workspace
    register_review_items(w.review_id, w.comparison, w.submission_a_id,
                          w.submission_b_id, w.db_path)
    before = list_decisions(w.review_id, w.db_path)
    with pytest.raises(DecisionError, match="legacy"):
        register_regions(w.review_id, w.comparison, w.submission_a_id,
                         w.submission_b_id, w.db_path)
    assert list_decisions(w.review_id, w.db_path) == before


def test_region_selection_is_frozen_after_registration(tmp_path):
    """Keep the chosen submission IDs stable across repeated reads."""
    from io import BytesIO
    from docx import Document
    from docxbranch.projects import create_project
    from docxbranch.versions import create_initial_version
    from docxbranch.submissions import create_submission
    from docxbranch.review import start_review
    from docxbranch.diff import compare_docx_bytes
    from docxbranch.region_decisions import (
        get_region_selection,
        register_regions,
    )

    def make_docx(text):
        """Create a simple DOCX fixture."""
        doc = Document()
        doc.add_paragraph(text)
        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    db_path = tmp_path / "selection.db"
    baseline = make_docx("Budget 100")
    a_content = make_docx("Budget 105")
    b_old = make_docx("Budget 110")
    b_new = make_docx("Budget 120")
    project_id = create_project("Selection", db_path=db_path)
    document_id = create_initial_version(
        project_id, "baseline.docx", baseline, db_path=db_path
    )
    a_id = create_submission(
        document_id, "Employee A", "a.docx", a_content, db_path=db_path
    )
    old_id = create_submission(
        document_id, "Employee B", "b_old.docx", b_old, db_path=db_path
    )
    new_id = create_submission(
        document_id, "Employee B", "b_new.docx", b_new, db_path=db_path
    )
    review_id = start_review(document_id, db_path=db_path)
    assert get_region_selection(review_id, db_path) is None
    comparison = compare_docx_bytes(
        "baseline.docx", baseline, "a.docx", a_content, "b_new.docx", b_new
    )
    register_regions(review_id, comparison, a_id, new_id, db_path)
    assert get_region_selection(review_id, db_path) == {
        "submission_a_id": a_id,
        "submission_b_id": new_id,
    }
    assert old_id != new_id


def test_frozen_selection_rejects_another_employee_b_submission(tmp_path):
    """Prevent silently replacing the chosen B submission after preparation."""
    from io import BytesIO
    from docx import Document
    from docxbranch.projects import create_project
    from docxbranch.versions import create_initial_version
    from docxbranch.submissions import create_submission
    from docxbranch.review import start_review
    from docxbranch.diff import compare_docx_bytes
    from docxbranch.region_decisions import register_regions

    def make_docx(text):
        """Create a single-paragraph test document."""
        doc = Document()
        doc.add_paragraph(text)
        output = BytesIO()
        doc.save(output)
        return output.getvalue()

    db_path = tmp_path / "locked_selection.db"
    baseline, a, b1, b2 = map(make_docx, ["100", "105", "110", "120"])
    project_id = create_project("Lock test", db_path=db_path)
    document_id = create_initial_version(
        project_id, "base.docx", baseline, db_path=db_path
    )
    a_id = create_submission(document_id, "Employee A", "a.docx", a, db_path=db_path)
    b1_id = create_submission(document_id, "Employee B", "b1.docx", b1, db_path=db_path)
    b2_id = create_submission(document_id, "Employee B", "b2.docx", b2, db_path=db_path)
    review_id = start_review(document_id, db_path=db_path)
    original = compare_docx_bytes("base.docx", baseline, "a.docx", a, "b2.docx", b2)
    alternate = compare_docx_bytes("base.docx", baseline, "a.docx", a, "b1.docx", b1)
    register_regions(review_id, original, a_id, b2_id, db_path)
    with pytest.raises(DecisionError, match="cannot be replaced"):
        register_regions(review_id, alternate, a_id, b1_id, db_path)
