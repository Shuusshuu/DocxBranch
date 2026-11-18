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

## Current Limitations

- Local prototype without user authentication
- Only body paragraphs and headings are previewed
- DOCX formatting is preserved in storage but not rendered
  in the preview
- No employee submission or reviewer workflow yet
- No change comparison, conflict resolution, or merging
- No publication of subsequent official versions yet
- Database-level immutability enforcement is not complete

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