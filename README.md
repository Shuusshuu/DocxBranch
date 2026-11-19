# DocxBranch

A review-gated document version control system for Microsoft Word documents.

DocxBranch aims to support collaborative document editing through controlled submissions, change reviews, conflict resolution, and immutable official versions.

## Implemented Features

- Upload and validate `.docx` files.
- Preview non-empty body paragraphs and headings.
- Display document paragraph count and file size.
- Reject invalid, empty, and oversized files.
- Run automated tests with pytest.

## Technology Stack

- Python 3.13
- Streamlit
- python-docx
- SQLite (planned)
- pytest

## Getting Started

### Requirements

- Python 3.13
- Git

### Installation

Clone the repository:

```powershell
git clone https://github.com/Shuusshuu/DocxBranch.git
cd DocxBranch
```

Create a virtual environment:

```powershell
py -3.13 -m venv .venv
```

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Run the Application

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open `http://localhost:8501` in your browser.

### Run Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Implemented Features

- DOCX file validation and paragraph preview
- SQLite-backed project management
- Persistent storage of original DOCX files
- Initial official document baseline (v1.0)
- SHA-256 file integrity verification
- Document retrieval and download
- Duplicate initial baseline protection
- Automated tests with pytest
- Independent employee DOCX submissions
- Submission author and timestamp tracking
- Submission-to-baseline version references
- Persistent submission history and downloads
- Duplicate submission detection
- Backend enforcement of document review locks
- Paragraph-level comparison against a common official baseline
- Detection of paragraph insertions, deletions, and replacements
- Heading-style change detection
- Conservative overlapping-change conflict detection
- Side-by-side submission selection and comparison summaries
- Conservative DOCX structural safety inspection
- Detection of unsupported tables, images, comments,
  tracked changes, fields, and other document structures
- Detection of empty paragraphs omitted by the current diff
- Safety reports for baseline and employee submissions

## Current Limitations

- Demo employee selection is not authentication
- Reviewer workflows are not yet implemented
- Document comparison and merging are not yet implemented
- Subsequent official version publishing is not yet implemented
- Database-level immutability enforcement is not complete
- DOCX tables, images, and other complex structures are not compared
- Empty paragraphs are not included in the current comparison
- Repeated identical paragraphs require manual review
- Conflict detection is paragraph-level, not semantic
- Comparison results are diagnostic and cannot yet be published
- Historical baseline comparison is not yet supported in the UI
- Safety inspection does not certify lossless DOCX merging
- Automatic merging and version publishing remain disabled
- Run-level formatting is not yet compared
- Package-level relationship and XML changes are not fully analyzed
- The safety validator is not a complete DOCX security scanner

## Planned Features

- Multi-project and multi-document management.
- Immutable official document versions.
- Independent employee submissions.
- Document-level review locking.
- Three-way comparison and conflict detection.
- Reviewer-controlled change approval.
- Approved document version publishing.

## License

No license has been selected yet.