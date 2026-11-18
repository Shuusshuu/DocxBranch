"""Conservative safety checks for DOCX comparison."""

from dataclasses import dataclass
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from docxbranch.document import read_docx


WORD_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)

REL_NS = (
    "http://schemas.openxmlformats.org/"
    "officeDocument/2006/relationships"
)

PACKAGE_REL_NS = (
    "http://schemas.openxmlformats.org/"
    "package/2006/relationships"
)

NS = {"w": WORD_NS}

# These elements indicate content or behavior that the current
# paragraph-based comparison cannot safely represent.
UNSUPPORTED_ELEMENTS = {
    "tbl": "Tables",
    "drawing": "Drawings or images",
    "pict": "Legacy pictures",
    "object": "Embedded objects",
    "hyperlink": "Hyperlinks",
    "fldChar": "Complex fields",
    "fldSimple": "Simple fields",
    "instrText": "Field instructions",
    "ins": "Tracked insertions",
    "del": "Tracked deletions",
    "moveFrom": "Tracked moves",
    "moveTo": "Tracked moves",
    "commentRangeStart": "Comment anchors",
    "commentRangeEnd": "Comment anchors",
    "commentReference": "Comment references",
    "footnoteReference": "Footnotes",
    "endnoteReference": "Endnotes",
    "sdt": "Content controls",
    "altChunk": "Imported external content",
    "br": "Line or page breaks",
    "tab": "Tabs",
    "sym": "Symbols",
    "oMath": "Equations",
    "oMathPara": "Equations",
}

# These Word document parts require dedicated comparison logic.
UNSUPPORTED_PARTS = {
    "word/comments.xml": "Comments",
    "word/footnotes.xml": "Footnotes",
    "word/endnotes.xml": "Endnotes",
    "word/numbering.xml": "Numbering definitions",
    "word/settings.xml": "Document settings",
}

UNSUPPORTED_PREFIXES = (
    "word/header",
    "word/footer",
    "word/media/",
    "word/embeddings/",
    "word/charts/",
    "word/diagrams/",
    "word/activeX/",
)


@dataclass(frozen=True)
class SafetyReport:
    """Describe the outcome of conservative DOCX checks."""

    safe_for_automatic_merge: bool
    issues: tuple[str, ...]


def inspect_docx(
    filename: str,
    content: bytes,
) -> SafetyReport:
    """Inspect a DOCX for structures outside the supported scope.

    The report intentionally does not authorize automatic merging.
    It only identifies known unsupported structures.

    Args:
        filename: Original DOCX filename.
        content: Original DOCX file bytes.

    Returns:
        A safety report containing detected limitations.

    Raises:
        DocumentError: If the DOCX fails existing validation.
        zipfile.BadZipFile: If its ZIP structure cannot be read.
        xml.etree.ElementTree.ParseError: If document XML is invalid.
    """
    # Reuse the existing upload validation and resource limits.
    read_docx(filename, content)

    issues = set()

    with ZipFile(BytesIO(content)) as archive:
        names = set(archive.namelist())

        for part, description in UNSUPPORTED_PARTS.items():
            if part in names:
                issues.add(description)

        for name in names:
            if name.startswith(UNSUPPORTED_PREFIXES):
                issues.add(f"Unsupported package part: {name}")

        root = ET.fromstring(
            archive.read("word/document.xml")
        )

        for element in root.iter():
            if not element.tag.startswith(f"{{{WORD_NS}}}"):
                continue

            local_name = element.tag.split("}", 1)[1]

            if local_name in UNSUPPORTED_ELEMENTS:
                issues.add(
                    UNSUPPORTED_ELEMENTS[local_name]
                )

        # Check for non-paragraph body children, which cannot be
        # represented by the existing ParagraphInfo model.
        body = root.find("w:body", NS)

        if body is None:
            issues.add("Missing document body")
        else:
            allowed_body_children = {
                f"{{{WORD_NS}}}p",
                f"{{{WORD_NS}}}sectPr",
            }

            for child in body:
                if child.tag not in allowed_body_children:
                    issues.add(
                        "Unsupported body-level structure"
                    )

        # Empty paragraphs are currently omitted by read_docx.
        # This is not safe for position-preserving merges.
        if body is not None:
            for paragraph in body.findall("w:p", NS):
                text = "".join(
                    node.text or ""
                    for node in paragraph.findall(
                        ".//w:t", NS
                    )
                )

                if not text.strip():
                    issues.add(
                        "Empty or whitespace-only paragraphs"
                    )

    return SafetyReport(
        safe_for_automatic_merge=False,
        issues=tuple(sorted(issues)),
    )


def inspect_comparison(
    baseline_name: str,
    baseline_content: bytes,
    employee_a_name: str,
    employee_a_content: bytes,
    employee_b_name: str,
    employee_b_content: bytes,
) -> dict[str, SafetyReport]:
    """Inspect all three DOCX files before displaying a diff.

    Args:
        baseline_name: Official baseline filename.
        baseline_content: Official baseline bytes.
        employee_a_name: First submission filename.
        employee_a_content: First submission bytes.
        employee_b_name: Second submission filename.
        employee_b_content: Second submission bytes.

    Returns:
        Safety reports keyed by document role.

    Raises:
        DocumentError: If a DOCX is invalid.
        zipfile.BadZipFile: If a ZIP archive is invalid.
        xml.etree.ElementTree.ParseError: If XML is invalid.
    """
    return {
        "Official Baseline": inspect_docx(
            baseline_name,
            baseline_content,
        ),
        "First Submission": inspect_docx(
            employee_a_name,
            employee_a_content,
        ),
        "Second Submission": inspect_docx(
            employee_b_name,
            employee_b_content,
        ),
    }
