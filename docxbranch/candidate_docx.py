"""Fail-closed plain-text DOCX export for completed review candidates.

This creates a NEW, unformatted DOCX; it is not a lossless source merge.
"""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from docx import Document

from docxbranch.candidate import CandidateError, preview_review_candidate
from docxbranch.database import DEFAULT_DB_PATH
from docxbranch.decisions import _connect
from docxbranch.document import read_docx
from docxbranch.safety import WORD_NS
from docxbranch.region_decisions import get_region_selection


_ALLOWED_PARTS = {
    '[Content_Types].xml', '_rels/.rels', 'docProps/app.xml',
    'docProps/core.xml', 'docProps/thumbnail.jpeg',
    'word/document.xml', 'word/_rels/document.xml.rels',
    'word/styles.xml', 'word/stylesWithEffects.xml',
    'word/settings.xml', 'word/webSettings.xml', 'word/fontTable.xml',
    'word/theme/theme1.xml', 'word/numbering.xml',
    'customXml/item1.xml', 'customXml/itemProps1.xml',
    'customXml/_rels/item1.xml.rels',
}


def validate_plain_text_docx(filename: str, content: bytes) -> None:
    """Reject any document with potentially lost formatting or body structure.

    Only direct body paragraphs with plain text runs are accepted. The
    boilerplate package parts are permitted but are NOT carried into the
    newly generated document. Unknown package parts are rejected.
    """
    read_docx(filename, content)
    namespace = f'{{{WORD_NS}}}'
    with ZipFile(BytesIO(content)) as archive:
        names = set(archive.namelist())
        unexpected = {name for name in names if name not in _ALLOWED_PARTS}
        if unexpected:
            raise CandidateError('DOCX export blocked: unsupported package parts: '
                                 + ', '.join(sorted(unexpected)[:5]))
        root = ET.fromstring(archive.read('word/document.xml'))
        body = root.find(f'{namespace}body')
        if body is None:
            raise CandidateError('DOCX export blocked: missing document body.')
        for child in body:
            if child.tag == f'{namespace}sectPr':
                # Page setup is intentionally not preserved in plain-text export.
                # Reject references to headers/footers and other complex sections.
                if any(node.tag in {f'{namespace}headerReference', f'{namespace}footerReference'} for node in child.iter()):
                    raise CandidateError('DOCX export blocked: linked headers or footers detected.')
                continue
            if child.tag != f'{namespace}p' or child.attrib:
                raise CandidateError('DOCX export blocked: unsupported body structure.')
            if not len(child):
                raise CandidateError('DOCX export blocked: empty paragraphs detected.')
            for run in child:
                if run.tag != f'{namespace}r' or run.attrib or not len(run):
                    raise CandidateError('DOCX export blocked: paragraph formatting or fields detected.')
                for node in run:
                    if node.tag != f'{namespace}t' or node.attrib.keys() - {'{http://www.w3.org/XML/1998/namespace}space'}:
                        raise CandidateError('DOCX export blocked: run formatting or non-text content detected.')
            text = ''.join(t.text or '' for t in child.iter(f'{namespace}t'))
            if not text.strip() or text != text.strip():
                raise CandidateError('DOCX export blocked: empty or whitespace-altered paragraph.')


def export_candidate_docx(review_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> bytes:
    """Generate a new plain-text DOCX after validating all frozen inputs.

    The existing candidate preview performs status, decision, selection and
    manifest checks. The stricter export additionally rejects any unsupported
    source structure and does not alter the database or official baseline.
    """
    paragraphs = preview_review_candidate(review_id, db_path)
    with _connect(db_path) as connection:
        review = connection.execute(
            '''SELECT r.document_id, v.file_id AS baseline_file_id
               FROM reviews r JOIN versions v ON v.id=r.baseline_version_id
               WHERE r.id=?''', (review_id,),
        ).fetchone()
        if review is None:
            raise CandidateError('Review does not exist.')
        selection = get_region_selection(review_id, db_path)
        if selection is None:
            raise CandidateError('Missing frozen submission selection.')
        files = []
        baseline_file = connection.execute(
            'SELECT filename, content FROM stored_files WHERE id=?', (review['baseline_file_id'],),
        ).fetchone()
        if baseline_file is None:
            raise CandidateError('Missing baseline file.')
        files.append(baseline_file)
        for role, submission_id in (('Employee A', selection['submission_a_id']),
                                    ('Employee B', selection['submission_b_id'])):
            row = connection.execute(
                '''SELECT f.filename, f.content FROM review_submissions rs
                   JOIN submissions s ON s.id=rs.submission_id
                   JOIN stored_files f ON f.id=s.file_id
                   WHERE rs.review_id=? AND s.id=? AND s.author=?
                     AND s.document_id=? AND s.baseline_version_id=(
                         SELECT baseline_version_id FROM reviews WHERE id=?)''',
                (review_id, submission_id, role, review['document_id'], review_id),
            ).fetchone()
            if row is None:
                raise CandidateError('Frozen submission is missing or mismatched.')
            files.append(row)
    for file in files:
        validate_plain_text_docx(file['filename'], file['content'])
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    output = BytesIO()
    document.save(output)
    return output.getvalue()
