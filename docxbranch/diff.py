"""Conservative paragraph-level DOCX comparison engine."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from docxbranch.document import ParagraphInfo, read_docx


class DiffError(ValueError):
    """Raised when a document cannot be compared safely."""


@dataclass(frozen=True)
class Change:
    """Represent one change relative to an official baseline."""

    kind: str
    start: int
    end: int
    original: tuple[str, ...]
    modified: tuple[str, ...]


@dataclass(frozen=True)
class Conflict:
    """Represent potentially overlapping employee changes."""

    change_a: Change
    change_b: Change


@dataclass(frozen=True)
class Comparison:
    """Hold employee changes and their detected conflicts."""

    changes_a: tuple[Change, ...]
    changes_b: tuple[Change, ...]
    conflicts: tuple[Conflict, ...]


def paragraph_keys(
    paragraphs: list[ParagraphInfo],
) -> list[tuple[str, str]]:
    """Convert paragraphs to comparable text-and-style keys.

    Args:
        paragraphs: Parsed DOCX paragraphs.

    Returns:
        A list of (text, style) tuples.
    """
    return [
        (paragraph.text, paragraph.style)
        for paragraph in paragraphs
    ]


def calculate_changes(
    baseline: list[ParagraphInfo],
    modified: list[ParagraphInfo],
) -> tuple[Change, ...]:
    """Find paragraph changes relative to a baseline.

    Positions use zero-based baseline paragraph boundaries.
    For insertions, start and end are the same boundary.

    Args:
        baseline: Official baseline paragraphs.
        modified: Employee-submitted paragraphs.

    Returns:
        Immutable sequence of detected changes.

    Raises:
        DiffError: If paragraph alignment is ambiguous.
    """
    original_keys = paragraph_keys(baseline)
    modified_keys = paragraph_keys(modified)

    # Repeated identical paragraphs can produce multiple plausible
    # alignments. We deliberately reject these cases for now.
    if (
        len(original_keys) != len(set(original_keys))
        or len(modified_keys) != len(set(modified_keys))
    ):
        raise DiffError(
            "Repeated identical paragraphs require manual review."
        )

    matcher = SequenceMatcher(
        None,
        original_keys,
        modified_keys,
        autojunk=False,
    )

    changes = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        # A changed style is a change even if text is identical.
        original_text = tuple(
            paragraph.text for paragraph in baseline[i1:i2]
        )
        modified_text = tuple(
            paragraph.text for paragraph in modified[j1:j2]
        )

        changes.append(
            Change(
                kind=tag,
                start=i1,
                end=i2,
                original=original_text,
                modified=modified_text,
            )
        )

    return tuple(changes)


def changes_overlap(
    first: Change,
    second: Change,
) -> bool:
    """Determine whether two changes may affect the same location.

    Insertions at the same boundary are treated as conflicts.
    Insertions on the boundary of another edited range are also
    treated conservatively as conflicts.

    Args:
        first: Change made by one employee.
        second: Change made by another employee.

    Returns:
        True when the changes may conflict.
    """
    first_insert = first.start == first.end
    second_insert = second.start == second.end

    if first_insert and second_insert:
        return first.start == second.start

    if first_insert:
        return second.start <= first.start <= second.end

    if second_insert:
        return first.start <= second.start <= first.end

    return (
        first.start < second.end
        and second.start < first.end
    )


def compare_versions(
    baseline: list[ParagraphInfo],
    employee_a: list[ParagraphInfo],
    employee_b: list[ParagraphInfo],
) -> Comparison:
    """Compare two employee documents against one official baseline.

    Args:
        baseline: Official baseline paragraphs.
        employee_a: First employee's paragraphs.
        employee_b: Second employee's paragraphs.

    Returns:
        Comparison containing changes and conflict candidates.

    Raises:
        DiffError: If paragraph alignment is ambiguous.
    """
    changes_a = calculate_changes(baseline, employee_a)
    changes_b = calculate_changes(baseline, employee_b)

    conflicts = tuple(
        Conflict(change_a=change_a, change_b=change_b)
        for change_a in changes_a
        for change_b in changes_b
        if changes_overlap(change_a, change_b)
    )

    return Comparison(
        changes_a=changes_a,
        changes_b=changes_b,
        conflicts=conflicts,
    )


def compare_docx_bytes(
    baseline_name: str,
    baseline_content: bytes,
    employee_a_name: str,
    employee_a_content: bytes,
    employee_b_name: str,
    employee_b_content: bytes,
) -> Comparison:
    """Compare three DOCX files using their parsed body paragraphs.

    This is a diagnostic comparison only. It is not proof that
    non-paragraph DOCX structures are safe to merge.

    Args:
        baseline_name: Filename of the official baseline.
        baseline_content: Original official DOCX bytes.
        employee_a_name: Filename of employee A's submission.
        employee_a_content: Employee A's DOCX bytes.
        employee_b_name: Filename of employee B's submission.
        employee_b_content: Employee B's DOCX bytes.

    Returns:
        A paragraph-level comparison result.

    Raises:
        DocumentError: If DOCX validation fails.
        DiffError: If paragraph alignment is ambiguous.
    """
    baseline = read_docx(
        baseline_name,
        baseline_content,
    )
    employee_a = read_docx(
        employee_a_name,
        employee_a_content,
    )
    employee_b = read_docx(
        employee_b_name,
        employee_b_content,
    )

    return compare_versions(
        baseline,
        employee_a,
        employee_b,
    )
