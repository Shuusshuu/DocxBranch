"""Read-only, validated candidate paragraph preview for completed reviews.

No DOCX is generated or published: this preview does not certify lossless merging.
"""

import json
from pathlib import Path

from docxbranch.database import DEFAULT_DB_PATH
from docxbranch.decisions import _connect
from docxbranch.diff import compare_docx_bytes
from docxbranch.document import read_docx
from docxbranch.region_decisions import (
    _region_payload, get_region_progress, get_region_selection,
    list_region_decisions,
)
from docxbranch.regions import build_regions


class CandidateError(ValueError):
    """Indicate that a candidate preview cannot be validated."""


def _apply_changes(baseline, changes, start, end):
    """Apply non-overlapping baseline-relative edits within one region.

    Change objects do not retain replacement styles, so this preview is
    intentionally text-only and cannot be used to generate a DOCX.
    """
    output = []
    cursor = start
    for change in sorted(changes, key=lambda item: (item.start, item.end)):
        if change.start < cursor or change.end > end or change.start < start:
            raise CandidateError("Region changes overlap or exceed their bounds.")
        if tuple(baseline[change.start:change.end]) != change.original:
            raise CandidateError("Change no longer matches the frozen baseline.")
        output.extend(baseline[cursor:change.start])
        output.extend(change.modified)
        cursor = change.end
    output.extend(baseline[cursor:end])
    return output


def build_candidate_paragraphs(baseline, comparison, decisions):
    """Build an ordered text-only preview from one resolution per region.

    Args:
        baseline: List of nonempty baseline paragraph texts.
        comparison: Fresh baseline-relative A/B comparison.
        decisions: Frozen decision records from SQLite.

    Returns:
        List of candidate paragraph texts.

    Raises:
        CandidateError: For missing decisions, changed manifests or overlaps.
    """
    regions = build_regions(comparison)
    if len(regions) != len(decisions):
        raise CandidateError("Frozen review regions do not match the comparison.")
    result = []
    cursor = 0
    for index, (region, item) in enumerate(zip(regions, decisions), 1):
        if item["region_key"] != f"R:{index}" or item["payload"] != _region_payload(region):
            raise CandidateError("Frozen region payload does not match current inputs.")
        decision = item["decision"]
        allowed = {"baseline", "A", "B"} if region.is_conflict else (
            {"baseline", "A"} if region.changes_a else {"baseline", "B"}
        )
        if decision not in allowed:
            raise CandidateError("Every region must have a valid saved decision.")
        if region.start < cursor:
            raise CandidateError("Overlapping review regions cannot be applied safely.")
        if region.end > len(baseline):
            raise CandidateError("Review region extends beyond the baseline.")
        result.extend(baseline[cursor:region.start])
        if decision == "baseline":
            result.extend(baseline[region.start:region.end])
        else:
            changes = region.changes_a if decision == "A" else region.changes_b
            result.extend(_apply_changes(baseline, changes, region.start, region.end))
        cursor = region.end
    result.extend(baseline[cursor:])
    return result


def preview_review_candidate(review_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> list[str]:
    """Rebuild a candidate preview using the review's frozen stored files.

    Rejects missing or incomplete decisions, altered region manifests,
    invalid review status, and mismatched frozen submission ownership.
    Does not write to the database or create an official document.
    """
    progress = get_region_progress(review_id, db_path)
    if not progress["complete"]:
        raise CandidateError("Resolve every region before previewing the candidate.")
    selection = get_region_selection(review_id, db_path)
    if selection is None:
        raise CandidateError("The review has no frozen submission selection.")
    with _connect(db_path) as connection:
        review = connection.execute(
            """SELECT r.status, r.document_id, v.file_id AS baseline_file_id
               FROM reviews r JOIN versions v ON v.id = r.baseline_version_id
               WHERE r.id = ?""", (review_id,),
        ).fetchone()
        if review is None or review["status"] != "active":
            raise CandidateError("An active review is required for preview.")
        inputs = []
        for role, submission_id in (("Employee A", selection["submission_a_id"]),
                                    ("Employee B", selection["submission_b_id"])):
            row = connection.execute(
                """SELECT f.filename, f.content FROM review_submissions rs
                   JOIN submissions s ON s.id=rs.submission_id
                   JOIN stored_files f ON f.id=s.file_id
                   WHERE rs.review_id=? AND s.id=? AND s.author=?
                     AND s.document_id=? AND s.baseline_version_id=(
                       SELECT baseline_version_id FROM reviews WHERE id=?)""",
                (review_id, submission_id, role, review["document_id"], review_id),
            ).fetchone()
            if row is None:
                raise CandidateError("Frozen submission is missing or mismatched.")
            inputs.append((row["filename"], row["content"]))
        baseline_file = connection.execute(
            "SELECT filename, content FROM stored_files WHERE id=?",
            (review["baseline_file_id"],),
        ).fetchone()
        if baseline_file is None:
            raise CandidateError("Frozen baseline is missing.")
        manifest_row = connection.execute(
            "SELECT payload FROM region_review_items WHERE review_id=? AND region_key='_manifest'",
            (review_id,),
        ).fetchone()
        if manifest_row is None:
            raise CandidateError("Frozen region manifest is missing.")
        manifest = json.loads(manifest_row["payload"])
    comparison = compare_docx_bytes(
        baseline_file["filename"], baseline_file["content"],
        inputs[0][0], inputs[0][1], inputs[1][0], inputs[1][1],
    )
    if manifest.get("regions") != [_region_payload(r) for r in build_regions(comparison)]:
        raise CandidateError("Frozen manifest does not match the stored documents.")
    baseline = [p.text for p in read_docx(baseline_file["filename"], baseline_file["content"])]
    return build_candidate_paragraphs(baseline, comparison, list_region_decisions(review_id, db_path))
