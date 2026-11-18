from io import BytesIO

import pytest
from docx import Document

from docxbranch.document import (
    DocumentError,
    MAX_FILE_SIZE,
    read_docx,
)


def make_docx(paragraphs=None):
    """Create a sample DOCX entirely in memory."""
    document = Document()
    for text, style in paragraphs or []:
        document.add_paragraph(text, style=style)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_read_paragraphs_and_headings():
    """
    Verify that headings and body paragraphs are extracted
    in their original document order.
    """

    data = make_docx([
        ("Project Proposal", "Heading 1"),
        ("This is the project overview.", "Normal"),
        ("Budget", "Heading 2"),
        ("The budget is 100 million yen.", "Normal"),
    ])

    result = read_docx("proposal.docx", data)

    assert len(result) == 4
    assert result[0].text == "Project Proposal"
    assert result[0].style == "Heading 1"
    assert result[3].text == "The budget is 100 million yen."


def test_empty_document():
    """
    Verify that a valid DOCX without body text returns
    an empty paragraph list.
    """

    data = make_docx()
    assert read_docx("empty.docx", data) == []


def test_reject_doc_extension():
    """
    Verify that legacy .doc files are rejected.
    """

    with pytest.raises(DocumentError):
        read_docx("old_document.doc", b"invalid")


def test_reject_fake_docx():
    """
    Verify that non-DOCX content with a .docx extension
    raises DocumentError.
    """

    with pytest.raises(DocumentError):
        read_docx("fake.docx", b"This is not a Word document")


def test_reject_empty_file():
    """
    Verify that an empty uploaded file is rejected.
    """

    with pytest.raises(DocumentError):
        read_docx("empty.docx", b"")


def test_reject_oversized_file():
    """
    Verify that files exceeding MAX_FILE_SIZE are rejected
    before document parsing begins.
    """

    with pytest.raises(DocumentError):
        read_docx("large.docx", b"x" * (MAX_FILE_SIZE + 1))
