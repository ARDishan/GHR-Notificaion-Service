import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from config import (
    REQUIRED_COLUMNS,
    TEMPLATES_DIR,
    LOGS_DIR,
)

from dialog_sms import DialogSMS
from db import get_engine


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = LOGS_DIR / "notification_service.log"

logger = logging.getLogger("CustomerNotificationService")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)


# ---------------------------------------------------------------------------
# Notification Service
# ---------------------------------------------------------------------------

class NotificationService:

    def __init__(self):

        self.dialog = DialogSMS()

        logger.info(
            "Notification service initialized."
        )

    # -----------------------------------------------------------------------
    # Excel
    # -----------------------------------------------------------------------

    def load_excel(self, excel_file):

        df = pd.read_excel(excel_file)

        df.columns = [
            str(c).strip()
            for c in df.columns
        ]

        missing = [
            column
            for column in REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Missing required Excel column(s): {missing}"
            )

        # Convert phone numbers to strings
        df["PHONE NO"] = (
            df["PHONE NO"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        # Remove .0 that Excel sometimes adds
        df["PHONE NO"] = df["PHONE NO"].str.replace(
            r"\.0$",
            "",
            regex=True
        )

        return df

    # -----------------------------------------------------------------------
    # Database — pending documents (replaces Excel + folder matching)
    # -----------------------------------------------------------------------

    def load_pending_from_db(
        self,
        notification_type,
        month_folder=None,
        document_type=None,
        engine=None,
    ):
        """
        Return generated_documents rows that do NOT yet have a
        SUCCESS entry in notification_log for this notification_type —
        i.e. exactly what still needs sending.

        document_type optionally restricts which kind of document
        counts (e.g. "payment_schedule" vs "welcome_letter") since
        one table now holds multiple document kinds. If omitted, it
        defaults to matching notification_type itself, which covers
        the common case (payment_schedule -> payment_schedule,
        welcome_letter -> welcome_letter). Pass it explicitly for
        multi-stage reminders, e.g.:

            load_pending_from_db("due_reminder_1", document_type="payment_schedule")
            load_pending_from_db("due_reminder_2", document_type="payment_schedule")

        No folder path, no filename matching: the PDF bytes and
        Drive upload status all live on the row itself.
        """

        if engine is None:
            engine = get_engine()

        if document_type is None:
            document_type = notification_type

        query = """
            SELECT gd.*
            FROM generated_documents gd
            WHERE gd.document_type = :doc_type
              AND NOT EXISTS (
                SELECT 1 FROM notification_log nl
                WHERE nl.generated_document_id = gd.id
                  AND nl.notification_type = :ntype
                  AND nl.status IN ('SUCCESS')
            )
        """

        params = {"ntype": notification_type, "doc_type": document_type}

        if month_folder:
            query += " AND gd.month_folder = :month"
            params["month"] = month_folder

        query += " ORDER BY gd.customer, gd.unit_ref_id"

        df = pd.read_sql(text(query), engine, params=params)

        logger.info(
            "Loaded %d pending document(s) for notification_type=%s, document_type=%s, month=%s",
            len(df),
            notification_type,
            document_type,
            month_folder or "(all)",
        )

        return df

    def log_notification(
        self,
        generated_document_id,
        customer,
        unit_ref,
        phone,
        notification_type,
        status,
        comment="",
        engine=None,
    ):
        """
        Record one SMS attempt so it is never sent twice for the
        same document + notification type.
        """

        if engine is None:
            engine = get_engine()

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO notification_log
                        (generated_document_id, customer, unit_ref_id, phone,
                         notification_type, status, comment)
                    VALUES
                        (:doc_id, :customer, :unit_ref, :phone,
                         :ntype, :status, :comment)
                    """
                ),
                {
                    "doc_id": generated_document_id,
                    "customer": customer,
                    "unit_ref": unit_ref,
                    "phone": phone,
                    "ntype": notification_type,
                    "status": status,
                    "comment": comment,
                },
            )

    def mark_document_uploaded(
        self,
        generated_document_id,
        drive_file_id,
        drive_web_url,
        engine=None,
    ):
        """
        Record the Drive upload result on the generated_documents row.
        """

        if engine is None:
            engine = get_engine()

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE generated_documents
                    SET drive_file_id = :file_id,
                        drive_web_url = :web_url,
                        uploaded_at = now()
                    WHERE id = :doc_id
                    """
                ),
                {
                    "file_id": drive_file_id,
                    "web_url": drive_web_url,
                    "doc_id": generated_document_id,
                },
            )

    # -----------------------------------------------------------------------
    # Template
    # -----------------------------------------------------------------------

    def load_template(self, notification_type):

        template_file = (
            TEMPLATES_DIR /
            f"{notification_type}.txt"
        )

        if not template_file.exists():

            raise FileNotFoundError(
                f"Template not found: {template_file}"
            )

        return template_file.read_text(
            encoding="utf-8"
        ).strip()

    # -----------------------------------------------------------------------
    # Drive URL
    # -----------------------------------------------------------------------

    @staticmethod
    def build_drive_link(file_id):

        return (
            "https://drive.google.com/file/d/"
            f"{file_id}/view"
        )

    # -----------------------------------------------------------------------
    # Message
    # -----------------------------------------------------------------------

    def build_message(
        self,
        notification_type,
        customer,
        unit_ref,
        project,
        drive_link,
    ):

        template = self.load_template(
            notification_type
        )

        return template.format(
            customer=customer,
            unit_ref=unit_ref,
            project=project,
            drive_link=drive_link,
        )

    # -----------------------------------------------------------------------
    # Validate phone
    # -----------------------------------------------------------------------

    @staticmethod
    def validate_phone(phone):

        """
        Validate and normalize a Sri Lankan mobile number.

        Accepted examples:

            777575714
            0777575714
            94777575714
            +94777575714

        Internally the number is normalized to:

            777575714
        """

        if phone is None:
            return False

        # ---------------------------------------------------------------
        # Handle Excel numeric values
        # ---------------------------------------------------------------

        if isinstance(phone, float):

            if phone.is_integer():
                phone = str(int(phone))
            else:
                phone = str(phone)

        phone = str(phone).strip()

        # ---------------------------------------------------------------
        # Remove common formatting characters
        # ---------------------------------------------------------------

        phone = (
            phone
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        # ---------------------------------------------------------------
        # Remove +94
        # ---------------------------------------------------------------

        if phone.startswith("+94"):

            phone = phone[3:]

        # ---------------------------------------------------------------
        # Remove 94
        # ---------------------------------------------------------------

        elif phone.startswith("94"):

            phone = phone[2:]

        # ---------------------------------------------------------------
        # Remove leading 0
        # ---------------------------------------------------------------

        if phone.startswith("0"):

            phone = phone[1:]

        # ---------------------------------------------------------------
        # Validate
        # ---------------------------------------------------------------

        if not phone.isdigit():
            return False

        if len(phone) != 9:
            return False

        if not phone.startswith("7"):
            return False

        return True

    # -----------------------------------------------------------------------
    # Normalize phone
    # -----------------------------------------------------------------------

    @staticmethod
    def normalize_phone(phone):

        if phone is None:
            raise ValueError("Phone number is empty.")

        # Handle Excel numeric values
        if isinstance(phone, float):

            if phone.is_integer():
                phone = str(int(phone))
            else:
                phone = str(phone)

        phone = str(phone).strip()

        # Remove formatting
        phone = (
            phone
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        # +94XXXXXXXXX
        if phone.startswith("+94"):
            phone = phone[3:]

        # 94XXXXXXXXX
        elif phone.startswith("94"):
            phone = phone[2:]

        # 0XXXXXXXXX
        if phone.startswith("0"):
            phone = phone[1:]

        # Validate digits
        if not phone.isdigit():
            raise ValueError(
                f"Invalid phone number: {phone}"
            )

        # Validate length
        if len(phone) != 9:
            raise ValueError(
                f"Invalid Sri Lankan mobile number: {phone}"
            )

        # Validate mobile prefix
        if not phone.startswith("7"):
            raise ValueError(
                f"Invalid Sri Lankan mobile number: {phone}"
            )

        return phone

    # -----------------------------------------------------------------------
    # Send one notification
    # -----------------------------------------------------------------------

    def send_notification(
        self,
        customer,
        phone,
        unit_ref,
        project,
        drive_file_id,
        notification_type="payment_schedule",
    ):

        # ---------------------------------------------------------------
        # Normalize phone
        # ---------------------------------------------------------------

        try:

            phone = self.normalize_phone(phone)

        except ValueError as e:

            return {
                "success": False,
                "status": "INVALID_PHONE",
                "customer": customer,
                "phone": phone,
                "unit_ref": unit_ref,
                "comment": str(e),
            }

        drive_link = self.build_drive_link(
            drive_file_id
        )

        message = self.build_message(
            notification_type=notification_type,
            customer=customer,
            unit_ref=unit_ref,
            project=project,
            drive_link=drive_link,
        )

        # ---------------------------------------------------------------
        # Real SMS
        # ---------------------------------------------------------------

        try:

            result = self.dialog.send_sms(
                mobile=phone,
                message=message,
            )

            result.update({
                "customer": customer,
                "phone": phone,
                "unit_ref": unit_ref,
                "project": project,
                "drive_link": drive_link,
                "message": message,
            })

            if result.get("success"):

                logger.info(
                    "SMS SUCCESS | Customer=%s | Phone=%s | Unit=%s | "
                    "Campaign=%s",
                    customer,
                    phone,
                    unit_ref,
                    result.get("campaign_id", ""),
                )

            else:

                logger.error(
                    "SMS FAILED | Customer=%s | Phone=%s | Unit=%s | "
                    "Status=%s | Comment=%s",
                    customer,
                    phone,
                    unit_ref,
                    result.get("status", ""),
                    result.get("comment", ""),
                )

            return result

        except Exception as e:

            logger.exception(
                "SMS exception for %s",
                customer
            )

            return {
                "success": False,
                "status": "EXCEPTION",
                "customer": customer,
                "phone": phone,
                "unit_ref": unit_ref,
                "comment": str(e),
            }

    # -----------------------------------------------------------------------
    # Close
    # -----------------------------------------------------------------------

    def close(self):

        try:
            self.dialog.close()
        except Exception:
            pass