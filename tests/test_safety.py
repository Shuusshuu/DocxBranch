"""Tests for conservative DOCX safety inspection."""

from io import BytesIO

from docx import Document

from docxbranch.safety import (
    inspect_comparison,
    inspect_docx,
)


def make_docx(
    paragraphs: list[str],
    add_table: bool = False,
) -> bytes:
    """Create an in-memory DOCX for safety testing.

    Args:
        paragraphs: Text for each document paragraph.
        add_table: Whether to include a Word table.

    Returns:
        Serialized DOCX bytes.
    """
    document = Document()

    for text in paragraphs:
        document.add_paragraph(text)

    if add_table:
        table = document.add_table(
            rows=1,
            cols=2,
        )
        table.cell(0, 0).text = "Item"
        table.cell(0, 1).text = "Value"

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_plain_docx_is_not_authorized_for_merge():
    """Verify that inspection never authorizes automatic merging."""
    content = make_docx(["Project overview"])

    report = inspect_docx(
        "proposal.docx",
        content,
    )

    assert report.safe_for_automatic_merge is False


def test_detect_table():
    """Verify that a Word table is detected as unsupported."""
    content = make_docx(
        ["Project overview"],
        add_table=True,
    )

    report = inspect_docx(
        "proposal.docx",
        content,
    )

    assert "Tables" in report.issues


def test_detect_empty_paragraph():
    """Verify that empty paragraphs are reported."""
    content = make_docx([
        "Introduction",
        "",
        "Conclusion",
    ])

    report = inspect_docx(
        "proposal.docx",
        content,
    )

    assert (
        "Empty or whitespace-only paragraphs"
        in report.issues
    )


def test_detect_whitespace_only_paragraph():
    """Verify that whitespace-only paragraphs are reported."""
    content = make_docx([
        "Introduction",
        "   ",
        "Conclusion",
    ])

    report = inspect_docx(
        "proposal.docx",
        content,
    )

    assert (
        "Empty or whitespace-only paragraphs"
        in report.issues
    )


def test_inspect_three_documents():
    """Verify that each document receives its own safety report."""
    baseline = make_docx(["Original"])
    modified_a = make_docx(["Employee A"])
    modified_b = make_docx(
        ["Employee B"],
        add_table=True,
    )

    reports = inspect_comparison(
        "baseline.docx",
        baseline,
        "employee_a.docx",
        modified_a,
        "employee_b.docx",
        modified_b,
    )

    assert set(reports) == {
        "Official Baseline",
        "First Submission",
        "Second Submission",
    }

    assert (
        "Tables"
        in reports["Second Submission"].issues
    )


def test_issues_are_sorted_and_unique():
    """Verify that repeated unsupported elements yield one issue."""
    content = make_docx(
        ["Introduction", "", ""],
        add_table=True,
    )

    report = inspect_docx(
        "proposal.docx",
        content,
    )

    assert report.issues == tuple(
        sorted(set(report.issues))
    )
