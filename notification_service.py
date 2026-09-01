import logging
import re
from pathlib import Path

import pandas as pd

from config import (
    REQUIRED_COLUMNS,
    TEMPLATES_DIR,
    LOGS_DIR,
)

from dialog_sms import DialogSMS


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
        dry_run=False,
    ):

        print(
        f"DEBUG PHONE: value={phone!r}, "
        f"type={type(phone).__name__}"
        )

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
        # Dry run
        # ---------------------------------------------------------------

        if dry_run:

            logger.info(
                "DRY RUN | Customer=%s | Phone=%s | Unit=%s",
                customer,
                phone,
                unit_ref,
            )

            return {
                "success": True,
                "status": "DRY_RUN",
                "customer": customer,
                "phone": phone,
                "unit_ref": unit_ref,
                "drive_link": drive_link,
                "message": message,
            }

        # ---------------------------------------------------------------
        # Real SMS
        # ---------------------------------------------------------------

        try:

            print("=" * 70)
            print("DEBUG: ABOUT TO SEND SMS")
            print(f"Customer : {customer}")
            print(f"Phone    : {phone!r}")
            print(f"Message  : {message!r}")

            result = self.dialog.send_sms(
                mobile=phone,
                message=message,
            )

            print("DEBUG: DIALOG API RESULT")
            print(result)
            print("=" * 70)

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