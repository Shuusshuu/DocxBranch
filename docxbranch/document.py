from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

from docx import Document

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000


class DocumentError(ValueError):
    """Raised when an uploaded document cannot be accepted."""


@dataclass(frozen=True)
class ParagraphInfo:
    """
    Represent one extracted Word paragraph.

    Attributes:
        text (str): Paragraph text without surrounding whitespace.
        style (str): Word paragraph style name, e.g. 'Heading 1'.
    """

    text: str
    style: str


def read_docx(filename: str, data: bytes) -> list[ParagraphInfo]:
    """
    Validate a DOCX file and extract its non-empty body paragraphs.

    Args:
        filename (str):
            Original uploaded filename. Must end with '.docx'.

        data (bytes):
            Raw binary content of the uploaded Word document.

    Returns:
        list[ParagraphInfo]:
            Paragraphs in document order, including their text
            and Word style names. Empty paragraphs are excluded.

    Raises:
        DocumentError:
            If the file extension is unsupported, the file is empty,
            the size limit is exceeded, or the DOCX cannot be parsed.

    Notes:
        Only body paragraphs are extracted.
        Tables, headers, footers, comments, and tracked changes
        are not included in the returned content.
    """

    if Path(filename).suffix.lower() != ".docx":
        raise DocumentError("Only .docx files are supported.")

    if not data:
        raise DocumentError("The uploaded file is empty.")

    if len(data) > MAX_FILE_SIZE:
        raise DocumentError("The file exceeds the 10 MB limit.")

    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise DocumentError("The DOCX contains too many entries.")

            total_size = sum(entry.file_size for entry in entries)
            if total_size > MAX_UNCOMPRESSED_SIZE:
                raise DocumentError("The DOCX expands beyond the safety limit.")

            names = set(archive.namelist())
            required = {"[Content_Types].xml", "word/document.xml", "_rels/.rels"}
            if not required.issubset(names):
                raise DocumentError("The file is not a valid DOCX package.")

            # Parse the document XML to reject malformed content.
            ET.fromstring(archive.read("word/document.xml"))

        document = Document(BytesIO(data))
        result = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                result.append(
                    ParagraphInfo(text=text, style=paragraph.style.name)
                )
        return result

    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise DocumentError("The DOCX file is damaged or invalid.") from exc
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("Unable to read this DOCX document.") from exc
