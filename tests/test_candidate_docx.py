"""Regression tests for narrowly scoped plain-text DOCX export."""

from io import BytesIO

import pytest
from docx import Document

from docxbranch.candidate import CandidateError
from docxbranch.candidate_docx import validate_plain_text_docx, export_candidate_docx
from docxbranch.region_decisions import register_regions, save_region_decision
from test_decisions import workspace as review_workspace


def make_docx(text, *, bold=False):
    """Create a minimal DOCX fixture with optional unsupported formatting."""
    doc = Document()
    run = doc.add_paragraph().add_run(text)
    if bold:
        run.bold = True
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


def test_plain_text_source_is_eligible():
    """Allow a basic Word document with no paragraph/run formatting."""
    validate_plain_text_docx('plain.docx', make_docx('hello'))


def test_bold_run_is_rejected():
    """Reject formatting that the paragraph diff does not track."""
    with pytest.raises(CandidateError, match='formatting'):
        validate_plain_text_docx('bold.docx', make_docx('hello', bold=True))


def test_empty_paragraph_is_rejected():
    """Reject paragraphs omitted by the text comparison engine."""
    doc = Document()
    doc.add_paragraph('hello')
    doc.add_paragraph('')
    stream = BytesIO()
    doc.save(stream)
    with pytest.raises(CandidateError, match='empty'):
        validate_plain_text_docx('empty.docx', stream.getvalue())


def test_export_requires_completed_decisions(review_workspace):
    """Block DOCX export when the review still has unresolved regions."""
    w = review_workspace
    register_regions(w.review_id, w.comparison, w.submission_a_id,
                     w.submission_b_id, w.db_path)
    with pytest.raises(CandidateError, match='Resolve every region'):
        export_candidate_docx(w.review_id, w.db_path)


def test_export_is_a_valid_docx_or_explicitly_blocked(review_workspace):
    """Never silently export unsupported source documents."""
    w = review_workspace
    register_regions(w.review_id, w.comparison, w.submission_a_id,
                     w.submission_b_id, w.db_path)
    save_region_decision(w.review_id, 'R:1', 'A', w.db_path)
    try:
        output = export_candidate_docx(w.review_id, w.db_path)
    except CandidateError as error:
        assert 'DOCX export blocked' in str(error)
    else:
        assert Document(BytesIO(output)).paragraphs
