import io
from datetime import datetime
import json

import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload



# Google Drive folder IDs (replace with your actual folder IDs)
ORIGINAL_DST_FOLDER_ID = "1evbb47pc4wVovWkzmIXEtFADXogiVKBy"
AMENDED_DST_FOLDER_ID = "1uHnJYnk_ULo5xtxJyAwxE_4OddFOZQUm"

# Columns that FL is allowed to edit
EDITABLE_COLUMNS = [
    "SALES CONSULTANT (SC/SM)",
    "DOCTOR CUSTOMER ADMIN (DCA)",
    "CONSULTANT THERAPIST (CT)",
    "PIC",
]


# ==========================
# Google Drive helpers
# ==========================
@st.cache_resource
def setup_gdrive():
    creds_dict = json.loads(st.secrets["google_service_account"])
    if"Private_key" in creds_dict:
        creds_dict["private_key"]
        .replace("\\n","\n")
        .strip()
      )
    scopes=["https://www.googleapis.com/auth/drive"]
    creds=service_accounts.Credentials.from_service_account_info(
        creds_dict,
        scopes=scopes
    )
    service = build("drive","v3",credentials = creds)
    


def upload_to_gdrive(service, folder_id: str, file_bytes: bytes, filename: str) -> str:
    """
    Upload a binary file to Google Drive and return the file ID.
    """
    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    bytes_io = io.BytesIO(file_bytes)
    media = MediaIoBaseUpload(
        bytes_io,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=False,
    )

    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    return uploaded.get("id")


# ==========================
# Streamlit App
# ==========================
st.set_page_config(page_title="DST Digitisation System", layout="wide")
st.title("DST Digitisation System")

tabs = st.tabs(["1. BCC Upload DST", "2. FL Amend DST"])


# ==========================
# TAB 1 – BCC Upload DST

with tabs[0]:
    st.subheader("BCC – Upload Daily DST")

    uploaded_file = st.file_uploader(
        "Upload the daily DST Excel file (.xlsx)",
        type=["xlsx"],
        key="bcc_uploader",
    )

    if uploaded_file is not None:
        # Read Excel into DataFrame
        try:
            df = pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
            df = None

        if df is not None:
            # Store in session_state for later use by FL
            st.session_state["original_df"] = df
            st.session_state["original_file_bytes"] = uploaded_file.getvalue()

            st.success("DST file loaded successfully. Preview below:")
            st.dataframe(df.head(20), use_container_width=True)

            # Upload original file to Google Drive
            if st.button("Upload Original DST to Google Drive"):
                try:
                    service = get_drive_service()
                    today_str = datetime.today().strftime("%d-%m-%Y")
                    original_filename = f"Original DST - {today_str}.xlsx"
                    file_id = upload_to_gdrive(
                        service,
                        ORIGINAL_DST_FOLDER_ID,
                        st.session_state["original_file_bytes"],
                        original_filename,
                    )
                    st.success(
                        f"Original DST uploaded to Google Drive.\n"
                        f"Filename: {original_filename}\n"
                        f"File ID: {file_id}"
                    )
                except Exception as e:
                    st.error(f"Failed to upload to Google Drive: {e}")
    else:
        st.info("Please upload the daily DST Excel file provided by BCC.")


# ==========================
# TAB 2 – FL Amend DST
# ==========================
with tabs[1]:
    st.subheader("FL – Amend DST")

    # Editor name (required)
    editor_name = st.text_input("Your Name (required):")

    # Check if BCC has uploaded DST
    if "original_df" not in st.session_state:
        st.warning("No DST loaded yet. Please ask BCC to upload DST in Tab 1.")
        st.stop()

    original_df = st.session_state["original_df"].copy()

    # Determine which columns are editable (only those that exist in DF)
    existing_editable_cols = [c for c in EDITABLE_COLUMNS if c in original_df.columns]
    disabled_columns = [c for c in original_df.columns if c not in existing_editable_cols]

    if not existing_editable_cols:
        st.warning(
            "None of the expected editable columns were found in the DST file.\n"
            f"Expected one of: {EDITABLE_COLUMNS}"
        )

    st.markdown("#### DST Table (only specific columns are editable):")

    edited_df = st.data_editor(
        original_df,
        disabled=disabled_columns,
        use_container_width=True,
        key="dst_editor",
    )

    st.markdown("---")
    st.markdown("### Export Amended DST")

    col1, col2, col3 = st.columns(3)
    with col1:
        dst_date = st.date_input("DST Date", value=datetime.today())
    with col2:
        branch = st.selectbox("Branch", options=["WG", "KV", "RP", "NMC", "SMC", "Other"])
    with col3:
        custom_branch = st.text_input("If 'Other', specify branch code:")

    # Resolve final branch label
    final_branch = branch
    if branch == "Other" and custom_branch.strip():
        final_branch = custom_branch.strip()

    generate_btn = st.button("Generate & Upload Amended DST")

    if generate_btn:
        # Basic validation
        if not editor_name.strip():
            st.error("Please enter your name before generating the amended DST.")
        elif not final_branch.strip():
            st.error("Please select or enter a branch code.")
        else:
            try:
                # Use edited_df directly as our amended table
                buffer = io.BytesIO()
                edited_df.to_excel(buffer, index=False)
                buffer.seek(0)
                file_bytes = buffer.getvalue()

                # Build filename: dd-mm-yyyy BRANCH DST amended by NAME.xlsx
                date_str = dst_date.strftime("%d-%m-%Y")
                safe_name = editor_name.strip().replace("/", "-")
                safe_branch = final_branch.replace("/", "-")
                amended_filename = f"{date_str} {safe_branch} DST amended by {safe_name}.xlsx"

                # Upload to Google Drive
                service = get_drive_service()
                file_id = upload_to_gdrive(
                    service,
                    AMENDED_DST_FOLDER_ID,
                    file_bytes,
                    amended_filename,
                )

                st.success(
                    f"Amended DST generated and uploaded to Google Drive.\n"
                    f"Filename: {amended_filename}\n"
                    f"File ID: {file_id}"
                )

                # Download button for FL
                st.download_button(
                    label="Download Amended DST",
                    data=file_bytes,
                    file_name=amended_filename,
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                )

            except Exception as e:
                st.error(f"Failed to generate or upload amended DST: {e}")

