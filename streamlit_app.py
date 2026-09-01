import os
import re
import traceback
from pathlib import Path
from datetime import datetime

import streamlit as st

from notification_service import NotificationService
from storage_service import GoogleDriveService


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GHR Customer Notification Service",
    page_icon="📩",
    layout="wide",
)

NOTIFICATION_TYPES = [
    "payment_schedule",
    "welcome_letter",
    "offer_letter",
    "due_reminder",
]

TEMP_UPLOAD_DIR = Path("temp_uploads")


# ---------------------------------------------------------------------------
# Helpers (ported from app.py)
# ---------------------------------------------------------------------------

def find_pdf(pdf_folder, excel_file_name):

    base_name = Path(str(excel_file_name)).stem

    candidates = [
        pdf_folder / f"{base_name}.pdf",
        pdf_folder / str(excel_file_name),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", base_name)
    candidate = pdf_folder / f"{safe_name}.pdf"

    if candidate.exists():
        return candidate

    for file in pdf_folder.rglob("*.pdf"):
        if file.stem == base_name:
            return file
        if file.stem == safe_name:
            return file

    return None


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def init_state():
    if "logs" not in st.session_state:
        st.session_state.logs = []
    if "running" not in st.session_state:
        st.session_state.running = False
    if "summary" not in st.session_state:
        st.session_state.summary = None


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{timestamp}] {message}")


def render_logs(log_box):
    log_box.code("\n".join(st.session_state.logs) or "Ready.", language=None)


# ---------------------------------------------------------------------------
# Main process
# ---------------------------------------------------------------------------

def run_process(
    excel_file,
    pdf_folder,
    month,
    notification_type,
    dry_run,
    log_box,
    progress_bar,
    status_text,
):

    service = None
    drive = None

    try:
        log("Starting Customer Notification Service...")
        render_logs(log_box)

        service = NotificationService()
        df = service.load_excel(excel_file)

        log(f"Excel loaded: {len(df)} row(s)")
        render_logs(log_box)

        log("Connecting to Google Drive...")
        render_logs(log_box)

        drive = GoogleDriveService()

        log("Google Drive connection successful.")
        render_logs(log_box)

        groups = df.groupby(
            ["CUSTOMER", "Unit REF ID", "FILE NAME"],
            sort=False,
        )

        total = len(groups)
        success_count = 0
        failed_count = 0

        for index, (key, group) in enumerate(groups, start=1):

            customer, unit_ref, excel_file_name = key
            phone = group["PHONE NO"].iloc[0]
            project = group["PROJECT"].iloc[0]

            pdf_path = find_pdf(pdf_folder, excel_file_name)

            if not pdf_path:
                log(f"[{index}/{total}] PDF not found: {excel_file_name}")
                failed_count += 1
                progress_bar.progress(index / total)
                status_text.text(f"Processing {index}/{total}...")
                render_logs(log_box)
                continue

            log(f"[{index}/{total}] Processing {customer} - {unit_ref}")
            render_logs(log_box)

            upload_result = drive.upload_payment_schedule(
                pdf_path=pdf_path,
                month_name=month,
                drive_file_name=pdf_path.name,
                skip_if_exists=True,
            )

            if not upload_result.get("success"):
                log("  Drive: FAILED - " + str(upload_result.get("comment", "Unknown error")))
                failed_count += 1
                progress_bar.progress(index / total)
                status_text.text(f"Processing {index}/{total}...")
                render_logs(log_box)
                continue

            drive_file_id = upload_result["id"]
            log(f"  Drive: {upload_result['web_url']}")

            sms_result = service.send_notification(
                customer=customer,
                phone=phone,
                unit_ref=unit_ref,
                project=project,
                drive_file_id=drive_file_id,
                notification_type=notification_type,
                dry_run=dry_run,
            )

            if sms_result.get("success"):
                success_count += 1
                log("  SMS: SUCCESS")
            else:
                failed_count += 1
                log("  SMS: FAILED - " + str(sms_result.get("comment", "")))

            progress_bar.progress(index / total)
            status_text.text(f"Processing {index}/{total}...")
            render_logs(log_box)

        log("")
        log("=" * 60)
        log("PROCESS COMPLETED")
        log("=" * 60)
        log(f"Total notifications : {total}")
        log(f"Successful          : {success_count}")
        log(f"Failed              : {failed_count}")
        render_logs(log_box)

        status_text.text(f"Completed — {success_count} successful, {failed_count} failed.")

        st.session_state.summary = {
            "total": total,
            "success": success_count,
            "failed": failed_count,
        }

    except Exception as e:

        log(f"ERROR: {e}")
        log(traceback.format_exc())
        render_logs(log_box)

        status_text.text("Process failed.")

        st.session_state.summary = {"error": str(e)}

    finally:

        if service:
            service.close()

        st.session_state.running = False


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def main():

    init_state()

    st.title("📩 GHR Customer Notification Service")
    st.caption("Upload customer documents to Google Drive and send notification SMS.")

    with st.form("settings_form"):

        col1, col2 = st.columns(2)

        with col1:
            excel_upload = st.file_uploader(
                "Excel File",
                type=["xlsx", "xls"],
            )

            month = st.text_input(
                "Drive Folder (Month)",
                value=datetime.now().strftime("%Y-%m"),
            )

        with col2:
            pdf_folder_path = st.text_input(
                "PDF Folder (full path on this machine)",
                placeholder="/home/dishan/Documents/PaymentSchedules",
            )

            notification_type = st.selectbox(
                "Notification Type",
                NOTIFICATION_TYPES,
            )

        dry_run = st.checkbox(
            "Dry Run — do NOT send SMS",
            value=True,
            help="Recommended for testing",
        )

        confirm_real_sms = st.checkbox(
            "I understand REAL SMS messages will be sent to customers "
            "(required if Dry Run is off)"
        )

        submitted = st.form_submit_button(
            "Start Notification Process",
            disabled=st.session_state.running,
        )

    status_text = st.empty()
    progress_bar = st.progress(0)

    st.subheader("Process Log")
    log_box = st.empty()
    render_logs(log_box)

    if submitted:

        errors = []

        if not excel_upload:
            errors.append("Please upload the Excel file.")

        if not pdf_folder_path or not os.path.isdir(pdf_folder_path):
            errors.append("Please provide a valid PDF folder path that exists on this machine.")

        if not month.strip():
            errors.append("Please provide a Drive folder / month value.")

        if not dry_run and not confirm_real_sms:
            errors.append(
                "Dry Run is off — please tick the confirmation checkbox, "
                "or re-enable Dry Run."
            )

        if errors:
            for error in errors:
                st.error(error)
            return

        # Save uploaded Excel to a temp path so pandas/openpyxl can read it
        TEMP_UPLOAD_DIR.mkdir(exist_ok=True)
        excel_path = TEMP_UPLOAD_DIR / excel_upload.name

        with open(excel_path, "wb") as f:
            f.write(excel_upload.getbuffer())

        st.session_state.logs = []
        st.session_state.running = True
        st.session_state.summary = None

        run_process(
            excel_file=str(excel_path),
            pdf_folder=Path(pdf_folder_path),
            month=month.strip(),
            notification_type=notification_type,
            dry_run=dry_run,
            log_box=log_box,
            progress_bar=progress_bar,
            status_text=status_text,
        )

    if st.session_state.summary:

        summary = st.session_state.summary

        if "error" in summary:
            st.error(f"Process failed: {summary['error']}")
        else:
            st.success(
                f"Completed — {summary['success']} successful, "
                f"{summary['failed']} failed (of {summary['total']} total)."
            )


if __name__ == "__main__":
    main()