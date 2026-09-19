import io
import traceback
from datetime import datetime

import pandas as pd
import streamlit as st

from notification_service import NotificationService
from storage_service import GoogleDriveService
from db import get_engine


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
    "due_reminder_1",
    "due_reminder_2",
    "welcome_letter",
    "offer_letter",
]

# Which generated_documents.document_type each notification type should
# pull PDFs from. Multiple notification types can share one document type —
# e.g. both reminder stages reuse the same payment-schedule PDF.
DOCUMENT_TYPE_BY_NOTIFICATION = {
    "payment_schedule": "payment_schedule",
    "due_reminder_1": "payment_schedule",
    "due_reminder_2": "payment_schedule",
    "welcome_letter": "welcome_letter",
    "offer_letter": "offer_letter",
}


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
    if "pending_df" not in st.session_state:
        st.session_state.pending_df = None


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{timestamp}] {message}")


def render_logs(log_box):
    log_box.code("\n".join(st.session_state.logs) or "Ready.", language=None)


# ---------------------------------------------------------------------------
# Main process — reads pending documents straight from the DB
# ---------------------------------------------------------------------------

def run_process(
    pending_df,
    month_filter,
    notification_type,
    log_box,
    progress_bar,
    status_text,
):

    service = None
    drive = None

    try:
        engine = get_engine()

        log(f"Found {len(pending_df)} document(s) pending '{notification_type}'.")
        render_logs(log_box)

        service = NotificationService()

        log("Connecting to Google Drive...")
        render_logs(log_box)

        drive = GoogleDriveService()

        log("Google Drive connection successful.")
        render_logs(log_box)

        total = len(pending_df)
        success_count = 0
        failed_count = 0
        log_rows = []

        for index, row in enumerate(pending_df.itertuples(), start=1):

            customer = row.customer
            unit_ref = row.unit_ref_id
            phone = row.phone_no
            project = row.project
            doc_id = row.id

            log(f"[{index}/{total}] Processing {customer} - {unit_ref}")
            render_logs(log_box)

            # -----------------------------------------------------------
            # Upload to Drive if not already uploaded
            # -----------------------------------------------------------
            if row.drive_file_id:
                drive_file_id = row.drive_file_id
                drive_web_url = row.drive_web_url
                log("  Drive: already uploaded, reusing link")
            else:
                upload_result = drive.upload_bytes(
                    pdf_bytes=row.pdf_data,
                    file_name=row.pdf_filename,
                    month_name=row.month_folder,
                    document_type=row.document_type,
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
                drive_web_url = upload_result["web_url"]
                log(f"  Drive: {drive_web_url}")

                service.mark_document_uploaded(
                    generated_document_id=doc_id,
                    drive_file_id=drive_file_id,
                    drive_web_url=drive_web_url,
                    engine=engine,
                )

            # -----------------------------------------------------------
            # Send SMS
            # -----------------------------------------------------------
            sms_result = service.send_notification(
                customer=customer,
                phone=phone,
                unit_ref=unit_ref,
                project=project,
                drive_file_id=drive_file_id,
                notification_type=notification_type,
            )

            raw_status = sms_result.get("status", "FAILED")

            # Normalize what we store: the SMS gateway returns its own
            # casing ("success" lowercase) which doesn't match what the
            # pending-notification query checks for. Always store the
            # success/fail outcome as a consistent "SUCCESS"/the raw
            # failure reason, so a sent notification is reliably excluded
            # from future runs.
            db_status = "SUCCESS" if sms_result.get("success") else raw_status

            service.log_notification(
                generated_document_id=doc_id,
                customer=customer,
                unit_ref=unit_ref,
                phone=phone,
                notification_type=notification_type,
                status=db_status,
                comment=sms_result.get("comment", ""),
                engine=engine,
            )

            sent_at = datetime.now()

            log_rows.append({
                "Customer": customer,
                "Unit REF ID": unit_ref,
                "Phone": phone,
                "Project": project,
                "Notification Type": notification_type,
                "Status": db_status,
                "Drive Link": drive_web_url,
                "Comment": sms_result.get("comment", ""),
                "Sent At": sent_at.strftime("%Y-%m-%d %H:%M:%S"),
            })

            if sms_result.get("success"):
                success_count += 1
                log(f"  SMS: {raw_status}")
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

        # Build the notification log as an Excel file for immediate download
        if log_rows:
            log_df = pd.DataFrame(log_rows)
            excel_buf = io.BytesIO()
            log_df.to_excel(excel_buf, index=False, engine="openpyxl")
            excel_buf.seek(0)

            st.session_state["notification_log_excel"] = excel_buf.getvalue()
            st.session_state["notification_log_excel_name"] = (
                f"notification_log_{notification_type}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            )

        # Refresh the pending list so sent rows drop off
        st.session_state.pending_df = service.load_pending_from_db(
            notification_type,
            month_filter or None,
            document_type=DOCUMENT_TYPE_BY_NOTIFICATION.get(notification_type, notification_type),
            engine=engine,
        )

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
    st.caption("Uploads statements to Google Drive and sends notification SMS — driven by the shared database.")

    col1, col2 = st.columns(2)

    with col1:
        notification_type = st.selectbox("Notification Type", NOTIFICATION_TYPES)

    with col2:
        month_filter = st.text_input(
            "Month folder filter (optional)",
            value=datetime.now().strftime("%Y-%m"),
            help="Leave blank to check all months.",
        )

    if st.button("🔄 Load pending customers", disabled=st.session_state.running):
        try:
            service = NotificationService()
            st.session_state.pending_df = service.load_pending_from_db(
                notification_type,
                month_filter.strip() or None,
                document_type=DOCUMENT_TYPE_BY_NOTIFICATION.get(notification_type, notification_type),
            )
            service.close()
        except Exception as e:
            st.error(f"Could not load pending documents: {e}")
            st.session_state.pending_df = None

    pending_df = st.session_state.pending_df

    if pending_df is not None:
        if pending_df.empty:
            st.info(f"No pending '{notification_type}' notifications for this filter — everyone's up to date.")
        else:
            st.subheader(f"Pending: {len(pending_df)} customer(s)")
            st.caption(
                "This list already excludes anyone with a SUCCESS record "
                "for this notification type — re-running never double-sends."
            )
            st.dataframe(
                pending_df[["customer", "unit_ref_id", "phone_no", "project", "month_folder"]],
                use_container_width=True,
            )

            confirm_real_sms = st.checkbox(
                "I understand REAL SMS messages will be sent to these customers"
            )

            status_text = st.empty()
            progress_bar = st.progress(0)

            st.subheader("Process Log")
            log_box = st.empty()
            render_logs(log_box)

            start_disabled = st.session_state.running or not confirm_real_sms

            if st.button("🚀 Start Notification Process", type="primary", disabled=start_disabled):
                st.session_state.logs = []
                st.session_state.running = True
                st.session_state.summary = None

                run_process(
                    pending_df=pending_df,
                    month_filter=month_filter.strip(),
                    notification_type=notification_type,
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

            excel_bytes = st.session_state.get("notification_log_excel")
            if excel_bytes:
                st.download_button(
                    "⬇️ Download notification log (Excel)",
                    data=excel_bytes,
                    file_name=st.session_state.get("notification_log_excel_name", "notification_log.xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )


if __name__ == "__main__":
    main()