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
