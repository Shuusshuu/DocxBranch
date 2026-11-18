import streamlit as st

from docxbranch.document import DocumentError, MAX_FILE_SIZE, read_docx

st.set_page_config(
    page_title="DocxBranch",
    page_icon="📄",
    layout="wide",
)

st.title("📄 DocxBranch")
st.caption("Review-Gated Document Version Control System")

st.sidebar.header("Workspace")
st.sidebar.info("DOCX upload and preview")
st.sidebar.selectbox("Current user", ["Employee A"], disabled=True)

st.subheader("Document Preview")
st.write("Upload a Word document to inspect its text content.")
st.info("Preview only. Files are not saved as official versions yet.")

uploaded_file = st.file_uploader(
    "Choose a Word document",
    type=["docx"],
    max_upload_size=10,
)

if uploaded_file is not None:
    data = uploaded_file.getvalue()

    try:
        paragraphs = read_docx(uploaded_file.name, data)

        st.success(f"Loaded: {uploaded_file.name}")

        col1, col2 = st.columns(2)
        col1.metric("Paragraphs", len(paragraphs))
        col2.metric("File size", f"{len(data) / 1024:.1f} KB")

        st.divider()

        if not paragraphs:
            st.warning("No non-empty body paragraphs were found.")
        else:
            for index, paragraph in enumerate(paragraphs, start=1):
                if paragraph.style.startswith("Heading"):
                    st.markdown(f"**{index}. {paragraph.text}**")
                else:
                    st.write(f"{index}. {paragraph.text}")

        st.caption(
            "Preview includes body paragraphs and headings only. "
            "Tables, images, comments and tracked changes are not displayed."
        )

    except DocumentError as error:
        st.error(str(error))
