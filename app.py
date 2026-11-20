"""Streamlit interface for DocxBranch."""

import streamlit as st

from docxbranch.database import initialize_database
from docxbranch.document import DocumentError, read_docx
from docxbranch.projects import (
    ProjectError,
    create_project,
    list_projects,
)
from docxbranch.versions import (
    VersionError,
    create_initial_version,
    get_document_content,
    list_documents,
)
from docxbranch.submissions import (
    DEMO_AUTHORS,
    SubmissionError,
    create_submission,
    get_submission_content,
    list_submissions,
)
from docxbranch.diff import DiffError, compare_docx_bytes
from docxbranch.safety import inspect_comparison
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile
from docxbranch.review import (
    ReviewError,
    start_review,
    get_active_review,
    list_review_submissions,
    cancel_review,
)
from docxbranch.decisions import DecisionError
from docxbranch.region_decisions import (
    register_regions,
    list_region_decisions,
    save_region_decision,
    get_region_progress,
)


st.set_page_config(
    page_title="DocxBranch",
    page_icon="📄",
    layout="wide",
)

initialize_database()

st.title("📄 DocxBranch")
st.caption("Review-Gated Document Version Control System")

st.sidebar.header("Workspace")
st.sidebar.selectbox(
    "Current user",
    ["Demo User"],
    disabled=True,
)
st.sidebar.caption(
    "Local prototype. Authentication is not implemented."
)

st.header("Projects")

with st.expander("Create New Project"):
    with st.form("create_project_form", clear_on_submit=True):
        project_name = st.text_input("Project Name")
        project_description = st.text_area(
            "Description",
            height=80,
        )
        create_clicked = st.form_submit_button(
            "Create Project",
            type="primary",
        )

        if create_clicked:
            try:
                project_id = create_project(
                    project_name,
                    project_description,
                )
                st.success(
                    f"Project created successfully (ID: {project_id})."
                )
            except ProjectError as error:
                st.error(str(error))

projects = list_projects()

if not projects:
    st.info("No projects yet. Create a project to get started.")
    st.stop()

project_options = {
    f"{project['name']} (ID: {project['id']})": project
    for project in projects
}

selected_label = st.selectbox(
    "Select Project",
    options=list(project_options.keys()),
)

selected_project = project_options[selected_label]
project_id = selected_project["id"]

if selected_project["description"]:
    st.caption(selected_project["description"])

st.divider()
st.header("Documents")

st.subheader("Upload a New Document")

uploaded_file = st.file_uploader(
    "Choose a Word document",
    type=["docx"],
    key=f"upload_{project_id}",
)

if uploaded_file is not None:
    content = uploaded_file.getvalue()

    try:
        paragraphs = read_docx(uploaded_file.name, content)

        st.success(f"Validated: {uploaded_file.name}")

        col1, col2 = st.columns(2)
        col1.metric("Paragraphs", len(paragraphs))
        col2.metric(
            "File Size",
            f"{len(content) / 1024:.1f} KB",
        )

        with st.expander("Document Preview"):
            if not paragraphs:
                st.info("No non-empty body paragraphs found.")
            else:
                for index, paragraph in enumerate(
                    paragraphs,
                    start=1,
                ):
                    st.write(
                        f"{index}. [{paragraph.style}] "
                        f"{paragraph.text}"
                    )

        st.caption(
            "Preview displays non-empty body paragraphs only. "
            "The original DOCX file is preserved when saved."
        )

        if st.button(
            "Save as Official Baseline v1.0",
            type="primary",
            key=f"save_{project_id}",
        ):
            try:
                document_id = create_initial_version(
                    project_id,
                    uploaded_file.name,
                    content,
                )
                st.success(
                    f"Document saved successfully "
                    f"(ID: {document_id}, Version: v1.0)."
                )
            except (VersionError, DocumentError) as error:
                st.error(str(error))

    except DocumentError as error:
        st.error(str(error))

st.divider()
st.subheader("Saved Documents")

documents = list_documents(project_id)

if not documents:
    st.info("No saved documents in this project.")
else:
    for document in documents:
        with st.container(border=True):
            col_info, col_download = st.columns([3, 1])

            with col_info:
                st.markdown(f"**{document['name']}**")
                st.caption(
                    f"Official Version: "
                    f"v{document['version_number']}.0"
                    f" | Size: {document['size_bytes'] / 1024:.1f} KB"
                    f" | Created: {document['created_at']} UTC"
                )

            with col_download:
                try:
                    saved_content = get_document_content(
                        document["id"]
                    )
                    st.download_button(
                        "Download DOCX",
                        data=saved_content,
                        file_name=document["name"],
                        mime=(
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        ),
                        key=f"download_{document['id']}",
                    )
                except VersionError as error:
                    st.error(str(error))

# Employee submissions are separate from official document versions.
st.divider()
st.header("Employee Submissions")

if not documents:
    st.info(
        "Create an official document baseline before "
        "submitting changes."
    )
else:
    document_options = {
        f"{document['name']} (ID: {document['id']})": document
        for document in documents
    }

    selected_document_label = st.selectbox(
        "Select Document",
        options=list(document_options.keys()),
        key="submission_document",
    )

    selected_document = document_options[
        selected_document_label
    ]
    selected_document_id = selected_document["id"]

    st.caption(
        "Current official baseline: "
        f"v{selected_document['version_number']}.0"
    )

    selected_author = st.selectbox(
        "Submitting Employee",
        options=DEMO_AUTHORS,
        key="submission_author",
    )

    submission_file = st.file_uploader(
        "Upload Modified DOCX",
        type=["docx"],
        key=f"submission_upload_{selected_document_id}",
    )

    if submission_file is not None:
        submission_content = submission_file.getvalue()

        try:
            preview = read_docx(
                submission_file.name,
                submission_content,
            )

            st.success(
                f"Validated: {submission_file.name}"
            )

            st.caption(
                f"{len(preview)} non-empty body paragraphs"
            )

            if st.button(
                "Submit for Review",
                type="primary",
                key=f"submit_{selected_document_id}",
            ):
                try:
                    submission_id = create_submission(
                        document_id=selected_document_id,
                        author=selected_author,
                        filename=submission_file.name,
                        content=submission_content,
                    )

                    st.success(
                        "Submission saved successfully "
                        f"(ID: {submission_id})."
                    )

                except SubmissionError as error:
                    st.error(str(error))

        except DocumentError as error:
            st.error(str(error))

    st.subheader("Submission History")

    submissions = list_submissions(
        selected_document_id
    )

    if not submissions:
        st.info("No submissions for this document.")
    else:
        for submission in submissions:
            with st.container(border=True):
                col_info, col_download = st.columns(
                    [3, 1]
                )

                with col_info:
                    st.markdown(
                        f"**Submission #{submission['id']}**"
                    )
                    st.write(
                        f"Author: {submission['author']}"
                    )
                    st.caption(
                        f"Baseline: "
                        f"v{submission['baseline_number']}.0"
                        f" | Status: {submission['status']}"
                        f" | Submitted: "
                        f"{submission['created_at']} UTC"
                    )
                    st.caption(
                        f"File: {submission['filename']}"
                    )

                with col_download:
                    try:
                        stored_content = (
                            get_submission_content(
                                submission["id"]
                            )
                        )

                        st.download_button(
                            "Download",
                            data=stored_content,
                            file_name=submission["filename"],
                            mime=(
                                "application/vnd.openxmlformats-officedocument."
                                "wordprocessingml.document"
                            ),
                            key=(
                                f"submission_download_"
                                f"{submission['id']}"
                            ),
                        )

                    except VersionError as error:
                        st.error(str(error))


# Manage review sessions for the selected official document.
st.divider()
st.header("Review Management")

if not documents:
    st.info(
        "Create an official document before starting a review."
    )
else:
    active_review = get_active_review(
        selected_document_id
    )

    if active_review is None:
        st.info(
            "No active review for the selected document."
        )

        pending_submissions = [
            submission
            for submission in submissions
            if (
                submission["status"] == "pending"
                and submission["baseline_version_id"]
                == selected_document["version_number"]
            )
        ]

        st.caption(
            f"{len(pending_submissions)} pending submission(s) "
            "available for review."
        )

        if st.button(
            "Start Review",
            type="primary",
            disabled=not pending_submissions,
            key=f"start_review_{selected_document_id}",
        ):
            try:
                review_id = start_review(
                    selected_document_id
                )

                st.success(
                    f"Review #{review_id} started successfully. "
                    "This document is now locked."
                )
                st.rerun()

            except ReviewError as error:
                st.error(str(error))

    else:
        st.warning(
            f"Review #{active_review['id']} is active. "
            "New submissions are locked for this document."
        )

        st.caption(
            f"Official Baseline: "
            f"v{active_review['baseline_number']}.0"
            f" | Started: {active_review['created_at']} UTC"
        )

        frozen_submissions = list_review_submissions(
            active_review["id"]
        )

        st.subheader("Frozen Submission Snapshot")

        for submission in frozen_submissions:
            with st.container(border=True):
                st.markdown(
                    f"**Submission #{submission['id']}**"
                )
                st.write(
                    f"Author: {submission['author']}"
                )
                st.caption(
                    f"File: {submission['filename']}"
                )

        st.caption(
            "The snapshot is fixed for this review. "
            "Approval and publishing are not implemented yet."
        )

        st.subheader("Review Decisions")

        # Only the frozen Employee A/B submissions are eligible.
        review_a = next(
            (
                item for item in frozen_submissions
                if item["author"] == "Employee A"
            ),
            None,
        )
        review_b = next(
            (
                item for item in frozen_submissions
                if item["author"] == "Employee B"
            ),
            None,
        )

        if review_a is None or review_b is None:
            st.warning(
                "This review needs a frozen submission "
                "from both Employee A and Employee B."
            )
        else:
            try:
                baseline_bytes = get_document_content(
                    selected_document_id
                )
                employee_a_bytes = get_submission_content(
                    review_a["id"]
                )
                employee_b_bytes = get_submission_content(
                    review_b["id"]
                )

                review_comparison = compare_docx_bytes(
                    selected_document["name"],
                    baseline_bytes,
                    review_a["filename"],
                    employee_a_bytes,
                    review_b["filename"],
                    employee_b_bytes,
                )

                if st.button(
                    "Prepare Review Regions",
                    key=f"prepare_regions_{active_review['id']}",
                ):
                    count = register_regions(
                        active_review["id"],
                        review_comparison,
                        review_a["id"],
                        review_b["id"],
                    )
                    st.success(f"{count} review region(s) registered.")
                    st.rerun()

                progress = get_region_progress(active_review["id"])
                if not progress["registered"]:
                    st.info(
                        "Prepare Review Regions to freeze the comparison. "
                        "Existing reviews using the legacy model must be "
                        "cancelled and restarted; their history is retained."
                    )
                else:
                    st.progress(progress["decided"] / max(progress["total"], 1))
                    st.caption(
                        f"{progress['decided']} of {progress['total']} "
                        "regions reviewed."
                    )
                    for item in list_region_decisions(active_review["id"]):
                        region_key = item["region_key"]
                        payload = item["payload"]
                        conflict = payload["conflict"]
                        with st.container(border=True):
                            st.markdown(
                                f"**{region_key} — "
                                f"{'Conflict' if conflict else 'Independent Change'}**"
                            )
                            st.caption(
                                f"Baseline paragraph boundaries: "
                                f"[{payload['start']}, {payload['end']})"
                            )
                            if conflict:
                                st.warning(
                                    "Both employees changed this region. "
                                    "Choose exactly one authoritative source."
                                )
                            for author, key in (
                                ("Employee A", "changes_a"),
                                ("Employee B", "changes_b"),
                            ):
                                if payload[key]:
                                    st.markdown(f"**{author}**")
                                    for change in payload[key]:
                                        st.caption(
                                            f"{change['kind']} "
                                            f"[{change['start']}, {change['end']})"
                                        )
                                        st.write("Baseline")
                                        st.code(
                                            "\n".join(change["original"]) or "(insertion)",
                                            language=None,
                                        )
                                        st.write("Proposed")
                                        st.code(
                                            "\n".join(change["modified"]) or "(deletion)",
                                            language=None,
                                        )
                            choices = ["Not reviewed", "baseline"]
                            if payload["changes_a"]:
                                choices.append("A")
                            if payload["changes_b"]:
                                choices.append("B")
                            current = item["decision"] or "Not reviewed"
                            choice = st.selectbox(
                                "Final Region Resolution",
                                choices,
                                index=choices.index(current),
                                key=f"region_choice_{active_review['id']}_{region_key}",
                                format_func=lambda value: {
                                    "Not reviewed": "Not reviewed",
                                    "baseline": "Keep Official Baseline",
                                    "A": "Use Employee A",
                                    "B": "Use Employee B",
                                }[value],
                            )
                            if st.button(
                                "Save Region Decision",
                                key=f"save_region_{active_review['id']}_{region_key}",
                            ):
                                if choice == "Not reviewed":
                                    st.warning("Choose a resolution before saving.")
                                else:
                                    save_region_decision(
                                        active_review["id"], region_key, choice
                                    )
                                    st.rerun()
                    if progress["complete"]:
                        st.success(
                            "All regions resolved. Merge and publication "
                            "remain disabled pending safety validation."
                        )
                    else:
                        st.warning(
                            f"{progress['remaining']} region(s) still need decisions."
                        )

            except (
                DecisionError,
                DiffError,
                DocumentError,
                VersionError,
            ) as error:
                st.error(str(error))

        st.divider()

        confirm_cancel = st.checkbox(
            "I understand that cancelling this review "
            "will unlock the document without publishing "
            "any changes.",
            key=f"confirm_cancel_{active_review['id']}",
        )

        if st.button(
            "Cancel Review",
            disabled=not confirm_cancel,
            key=f"cancel_review_{active_review['id']}",
        ):
            try:
                cancel_review(active_review["id"])

                st.success(
                    "Review cancelled. "
                    "The document is now unlocked."
                )
                st.rerun()

            except ReviewError as error:
                st.error(str(error))

# Compare employee submissions against their common baseline.
st.divider()
st.header("Compare Submissions")

if not documents:
    st.info(
        "Create an official document before comparing submissions."
    )
elif len(submissions) < 2:
    st.info(
        "At least two submissions are required for comparison."
    )
else:
    submission_options = {
        (
            f"#{item['id']} - {item['author']} - "
            f"{item['filename']}"
        ): item
        for item in submissions
    }

    labels = list(submission_options.keys())

    selected_a_label = st.selectbox(
        "First Submission",
        options=labels,
        index=0,
        key="compare_submission_a",
    )

    selected_b_label = st.selectbox(
        "Second Submission",
        options=labels,
        index=1,
        key="compare_submission_b",
    )

    submission_a = submission_options[selected_a_label]
    submission_b = submission_options[selected_b_label]

    if st.button(
        "Compare Changes",
        type="primary",
        key="compare_changes_button",
    ):
        if submission_a["id"] == submission_b["id"]:
            st.error("Please select two different submissions.")

        elif (
            submission_a["baseline_version_id"]
            != submission_b["baseline_version_id"]
        ):
            st.error(
                "The selected submissions use different "
                "official baselines."
            )

        elif (
            submission_a["baseline_number"]
            != selected_document["version_number"]
        ):
            st.error(
                "Historical baseline comparison is not "
                "available in this interface yet."
            )

        else:
            try:
                baseline_content = get_document_content(
                    selected_document_id
                )

                content_a = get_submission_content(
                    submission_a["id"]
                )
                content_b = get_submission_content(
                    submission_b["id"]
                )

                safety_reports = inspect_comparison(
                    selected_document["name"],
                    baseline_content,
                    submission_a["filename"],
                    content_a,
                    submission_b["filename"],
                    content_b,
                )

                result = compare_docx_bytes(
                    selected_document["name"],
                    baseline_content,
                    submission_a["filename"],
                    content_a,
                    submission_b["filename"],
                    content_b,
                )

                st.subheader("DOCX Safety Assessment")
                st.warning(
                    "Automatic merging is disabled. "
                    "The current comparison only analyzes non-empty "
                    "body paragraphs and paragraph styles."
                )

                for role, report in safety_reports.items():
                    with st.expander(
                        f"{role}: "
                        f"{len(report.issues)} detected limitation(s)"
                    ):
                        if report.issues:
                            for issue in report.issues:
                                st.write(f"- {issue}")
                        else:
                            st.info(
                                "No known unsupported structures were "
                                "detected. This does not guarantee "
                                "merge safety."
                            )

                st.subheader("Comparison Summary")

                metric_a, metric_b, metric_c = st.columns(3)

                metric_a.metric(
                    "First Submission Changes",
                    len(result.changes_a),
                )
                metric_b.metric(
                    "Second Submission Changes",
                    len(result.changes_b),
                )
                metric_c.metric(
                    "Potential Conflicts",
                    len(result.conflicts),
                )

                for label, changes in (
                    ("First Submission", result.changes_a),
                    ("Second Submission", result.changes_b),
                ):
                    st.subheader(label)

                    if not changes:
                        st.info("No paragraph changes detected.")

                    for index, change in enumerate(changes, 1):
                        with st.expander(
                            f"Change {index}: "
                            f"{change.kind.upper()} "
                            f"at baseline [{change.start}, "
                            f"{change.end})"
                        ):
                            st.markdown("**Original:**")
                            st.code(
                                "\n".join(change.original)
                                or "(empty)",
                                language=None,
                            )

                            st.markdown("**Modified:**")
                            st.code(
                                "\n".join(change.modified)
                                or "(empty)",
                                language=None,
                            )

                st.subheader("Potential Conflicts")

                if result.conflicts:
                    st.warning(
                        f"{len(result.conflicts)} overlapping "
                        "change pair(s) require review."
                    )

                    for index, conflict in enumerate(
                        result.conflicts, 1
                    ):
                        with st.expander(
                            f"Conflict {index}",
                            expanded=True,
                        ):
                            st.write("First submission:")
                            st.code(
                                "\n".join(
                                    conflict.change_a.modified
                                ) or "(deleted)",
                                language=None,
                            )

                            st.write("Second submission:")
                            st.code(
                                "\n".join(
                                    conflict.change_b.modified
                                ) or "(deleted)",
                                language=None,
                            )

                else:
                    st.success(
                        "No overlapping paragraph changes "
                        "were detected."
                    )

                st.caption(
                    "Diagnostic paragraph comparison only. "
                    "No document has been merged or published."
                )

            except (DiffError, VersionError, DocumentError, ParseError, BadZipFile) as error:
                st.error(str(error))
