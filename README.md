# DocxBranch

A review-gated document version control system for Microsoft Word documents.

DocxBranch aims to support collaborative document editing through controlled submissions, change reviews, conflict resolution, and immutable official versions.

## Technology Stack

- Python 3.13
- Streamlit
- python-docx
- SQLite
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
- Transactional document review sessions
- Document-level review locking
- Frozen submission snapshots for active reviews
- Prevention of new submissions during active reviews
- Review cancellation with lock release
- Persistent review records in SQLite
- Persistent reviewer decisions stored in SQLite
- Region-based review of independent and overlapping changes
- Transitive overlap grouping into one conflict region
- One authoritative resolution per review region (baseline, Employee A, or Employee B)
- Persistent region decisions with progress tracking
- Reviewer-selected submission per employee from a frozen review snapshot
- Immutable selected submission pair and region comparison manifest
- Preservation of legacy decision records without automatic migration
- Read-only candidate paragraph preview assembled from completed region decisions
- Frozen review input and region-manifest verification before preview
- Downloadable candidate text preview (.txt), without modifying official versions
- Optional reconstructed plain-text candidate DOCX export for strictly validated simple inputs
- DOCX export rejects unsupported body structures and run formatting; no official version is published

## Current Limitations

- Authentication and role-based access control are not yet implemented; employee selection is for demonstration purposes only.
- Region decisions can be recorded, but final approval and publication workflows are not yet implemented.
- Each review compares one explicitly selected frozen submission per employee; combining multiple submissions from the same employee into one review is not yet supported.
- Candidate text previews and restricted plain-text DOCX exports are supported, but lossless DOCX merging and official version publishing are not yet implemented.
- Document comparison currently supports non-empty body paragraphs and paragraph styles only; tables, images, and other complex DOCX structures are excluded.
- Run-level formatting changes are not yet compared.
- Repeated identical paragraphs require manual review due to ambiguous alignment.
- Conflict detection is paragraph-level and does not perform semantic analysis.
- Historical baseline comparison is not yet supported in the UI.
- DOCX safety inspection does not guarantee lossless merging or provide comprehensive security validation.
- Package-level relationships and XML changes are not fully analyzed.
- Database-level immutability enforcement, including protection of frozen submission snapshots, is not yet complete.
- Exported candidate DOCX files are newly reconstructed plain-text documents; source styles, page setup, metadata, and rich formatting are not preserved. Files outside the strict plain-text subset are blocked.
- Active reviews created with the legacy per-change decision model must be cancelled and restarted for region-based decisions; historical records are retained.

## Planned Features

- Lossless, safety-validated DOCX candidate generation with formatting and structural preservation
- Immutable subsequent official document version publishing
- Authentication and role-based reviewer permissions
- Historical baseline comparison in the UI
- More comprehensive DOCX structure and formatting support

## License

No license has been selected yet.