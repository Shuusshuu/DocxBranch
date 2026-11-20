"""Tests for read-only candidate paragraph reconstruction."""

import pytest

from docxbranch.candidate import CandidateError, build_candidate_paragraphs, preview_review_candidate
from docxbranch.diff import Change, Comparison
from docxbranch.regions import build_regions
from docxbranch.region_decisions import (
    _region_payload, register_regions, save_region_decision,
)
from test_decisions import workspace as review_workspace


def comparison(a, b):
    """Build a comparison from two baseline-relative change sets."""
    return Comparison(tuple(a), tuple(b), ())


def records(comp, choices):
    """Construct frozen region records with explicit decisions."""
    return [dict(region_key=f"R:{i}", payload=_region_payload(r), decision=d)
            for i, (r, d) in enumerate(zip(build_regions(comp), choices), 1)]


def test_independent_edits_preserve_unmodified_paragraphs():
    """Apply independent edits without dropping unaffected paragraphs."""
    comp = comparison([Change("replace", 0, 1, ("one",), ("A",))],
                      [Change("replace", 2, 3, ("three",), ("B",))])
    assert build_candidate_paragraphs(["one", "two", "three"], comp,
                                      records(comp, ["A", "B"])) == ["A", "two", "B"]


@pytest.mark.parametrize("choice,expected", [("baseline", "old"), ("A", "alice"), ("B", "bob")])
def test_conflict_has_one_authoritative_resolution(choice, expected):
    """A conflict produces exactly the selected source text."""
    comp = comparison([Change("replace", 0, 1, ("old",), ("alice",))],
                      [Change("replace", 0, 1, ("old",), ("bob",))])
    assert build_candidate_paragraphs(["old"], comp, records(comp, [choice])) == [expected]


def test_insertion_and_deletion():
    """Handle insertion at a boundary and deletion of an existing paragraph."""
    comp = comparison([Change("insert", 1, 1, (), ("new",))],
                      [Change("delete", 2, 3, ("three",), ())])
    assert build_candidate_paragraphs(["one", "two", "three"], comp,
                                      records(comp, ["A", "B"])) == ["one", "new", "two"]


def test_incomplete_decisions_are_rejected():
    """An unresolved region must never yield a candidate."""
    comp = comparison([Change("replace", 0, 1, ("old",), ("new",))], [])
    with pytest.raises(CandidateError, match="valid saved decision"):
        build_candidate_paragraphs(["old"], comp, records(comp, [None]))


def test_manifest_tampering_is_rejected():
    """Do not apply changes when the frozen region payload differs."""
    comp = comparison([Change("replace", 0, 1, ("old",), ("new",))], [])
    items = records(comp, ["A"])
    items[0]["payload"]["start"] = 8
    with pytest.raises(CandidateError, match="payload"):
        build_candidate_paragraphs(["old"], comp, items)


def test_full_review_preview_requires_all_decisions(review_workspace):
    """Preview from persisted frozen files only after completion."""
    w = review_workspace
    register_regions(w.review_id, w.comparison, w.submission_a_id,
                     w.submission_b_id, w.db_path)
    with pytest.raises(CandidateError, match="Resolve every region"):
        preview_review_candidate(w.review_id, w.db_path)
    save_region_decision(w.review_id, "R:1", "A", w.db_path)
    result = preview_review_candidate(w.review_id, w.db_path)
    assert isinstance(result, list)
    assert result
