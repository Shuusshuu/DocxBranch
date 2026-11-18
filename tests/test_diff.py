"""Tests for conservative paragraph-level document comparison."""

import pytest

from docxbranch.diff import (
    DiffError,
    calculate_changes,
    compare_versions,
)
from docxbranch.document import ParagraphInfo


def paragraphs(*texts: str) -> list[ParagraphInfo]:
    """Create test paragraphs with the Normal style.

    Args:
        texts: Paragraph text values.

    Returns:
        ParagraphInfo objects for testing.
    """
    return [
        ParagraphInfo(text=text, style="Normal")
        for text in texts
    ]


def test_unchanged_document():
    """Verify that identical documents produce no changes."""
    baseline = paragraphs("A", "B", "C")

    assert calculate_changes(baseline, baseline) == ()


def test_replace_paragraph():
    """Verify that a replacement retains baseline coordinates."""
    changes = calculate_changes(
        paragraphs("A", "B", "C"),
        paragraphs("A", "Changed B", "C"),
    )

    assert len(changes) == 1
    assert changes[0].kind == "replace"
    assert changes[0].start == 1
    assert changes[0].end == 2
    assert changes[0].original == ("B",)
    assert changes[0].modified == ("Changed B",)


def test_insert_paragraph():
    """Verify that inserting text does not shift later changes."""
    changes = calculate_changes(
        paragraphs("A", "B", "C"),
        paragraphs("A", "New", "B", "C"),
    )

    assert len(changes) == 1
    assert changes[0].kind == "insert"
    assert changes[0].start == 1
    assert changes[0].end == 1


def test_delete_paragraph():
    """Verify that paragraph deletion is detected."""
    changes = calculate_changes(
        paragraphs("A", "B", "C"),
        paragraphs("A", "C"),
    )

    assert len(changes) == 1
    assert changes[0].kind == "delete"
    assert changes[0].original == ("B",)
    assert changes[0].modified == ()


def test_non_conflicting_changes():
    """Verify that changes to separate paragraphs do not conflict."""
    comparison = compare_versions(
        paragraphs("Budget 100", "Duration 6", "Target 20"),
        paragraphs("Budget 120", "Duration 6", "Target 20"),
        paragraphs("Budget 100", "Duration 8", "Target 20"),
    )

    assert len(comparison.changes_a) == 1
    assert len(comparison.changes_b) == 1
    assert comparison.conflicts == ()


def test_conflicting_replacements():
    """Verify that different edits to one paragraph conflict."""
    comparison = compare_versions(
        paragraphs("Budget 100", "Duration 6"),
        paragraphs("Budget 120", "Duration 6"),
        paragraphs("Budget 150", "Duration 6"),
    )

    assert len(comparison.conflicts) == 1
    assert comparison.conflicts[0].change_a.start == 0


def test_same_position_insertions_conflict():
    """Verify that insertions at one boundary require review."""
    comparison = compare_versions(
        paragraphs("A", "B"),
        paragraphs("A", "New from A", "B"),
        paragraphs("A", "New from B", "B"),
    )

    assert len(comparison.conflicts) == 1


def test_repeated_paragraphs_require_manual_review():
    """Reject ambiguous alignment involving repeated paragraphs."""
    with pytest.raises(
        DiffError,
        match="Repeated identical paragraphs",
    ):
        calculate_changes(
            paragraphs("A", "A", "B"),
            paragraphs("A", "B"),
        )


def test_style_change_is_detected():
    """Verify that changing a heading style counts as a change."""
    baseline = [
        ParagraphInfo(text="Overview", style="Normal")
    ]
    modified = [
        ParagraphInfo(text="Overview", style="Heading 1")
    ]

    changes = calculate_changes(baseline, modified)

    assert len(changes) == 1
    assert changes[0].kind == "replace"
