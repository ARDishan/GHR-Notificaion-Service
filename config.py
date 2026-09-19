import os
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Base directory
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    str(BASE_DIR / "credentials" / "google_drive_credentials.json")
)

GOOGLE_TOKEN_FILE = os.getenv(
    "GOOGLE_TOKEN_FILE",
    str(BASE_DIR / "token.json")
)

GOOGLE_DRIVE_ROOT_FOLDER = os.getenv(
    "GOOGLE_DRIVE_ROOT_FOLDER",
    "Payment Schedule"
)


# ---------------------------------------------------------------------------
# Dialog SMS
# ---------------------------------------------------------------------------

DIALOG_USERNAME = os.getenv(
    "DIALOG_USERNAME",
    ""
)

DIALOG_PASSWORD = os.getenv(
    "DIALOG_PASSWORD",
    ""
)

DIALOG_SOURCE_ADDRESS = os.getenv(
    "DIALOG_SOURCE_ADDRESS",
    "GHR Global"
)

DIALOG_PAYMENT_METHOD = os.getenv(
    "DIALOG_PAYMENT_METHOD",
    "4"
)


# ---------------------------------------------------------------------------
# Shared Postgres database (same DB used by the Statement Generator app)
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "")

DB_PORT = os.getenv("DB_PORT", "5432")

DB_NAME = os.getenv("DB_NAME", "")

DB_USER = os.getenv("DB_USER", "")

DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DB_SSLMODE = os.getenv("DB_SSLMODE", "require")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

TEMPLATES_DIR = BASE_DIR / "templates"

LOGS_DIR = BASE_DIR / "logs"

LOGS_DIR.mkdir(
    exist_ok=True
)


# ---------------------------------------------------------------------------
# Excel columns
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "PROJECT",
    "CUSTOMER",
    "PHONE NO",
    "Unit REF ID",
    "S NO",
    "INSTALLMENT NO",
    "INSTALLMENT AMT",
    "DUE DATE",
    "PAID AMT",
    "OUTSTANDING",
    "FILE NAME",
]