"""
storage_service.py

Google Drive storage service for CustomerNotificationService.

Responsibilities:
    - Authenticate with Google Drive
    - Find/create Payment Schedule folder
    - Find/create monthly folders such as 2026-08
    - Upload payment schedule PDFs
    - Make uploaded PDFs viewable by link
    - Return Google Drive URL

Folder structure:

    My Drive/
        Payment Schedule/
            2026-08/
                EBR_F04_Unit1_xxxxx.pdf
                OCB-2_F04_Unit1_xxxxx.pdf

First run:
    Google OAuth browser authentication will be opened.

Later runs:
    token.json will be reused.
"""

import mimetypes
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


# ============================================================================
# PATH CONFIGURATION
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent

CREDENTIALS_FILE = BASE_DIR /"credentials"/"credentials.json"
TOKEN_FILE = BASE_DIR /"credentials" / "token.json"


# ============================================================================
# GOOGLE DRIVE CONFIGURATION
# ============================================================================

SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

ROOT_FOLDER_NAME = "Payment Schedule"


# ============================================================================
# GOOGLE DRIVE SERVICE
# ============================================================================

class GoogleDriveService:

    def __init__(self, root_folder_name=ROOT_FOLDER_NAME):

        self.root_folder_name = root_folder_name
        self.service = None

        self._authenticate()

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    def _authenticate(self):

        creds = None

        # --------------------------------------------------------------------
        # Load existing token
        # --------------------------------------------------------------------

        if TOKEN_FILE.exists():

            creds = Credentials.from_authorized_user_file(
                str(TOKEN_FILE),
                SCOPES
            )

        # --------------------------------------------------------------------
        # Refresh expired token
        # --------------------------------------------------------------------

        if creds and creds.expired and creds.refresh_token:

            try:

                creds.refresh(Request())

            except Exception:

                creds = None

        # --------------------------------------------------------------------
        # First-time authentication
        # --------------------------------------------------------------------

        if not creds or not creds.valid:

            if not CREDENTIALS_FILE.exists():

                raise FileNotFoundError(
                    f"Google credentials file not found:\n"
                    f"{CREDENTIALS_FILE}\n\n"
                    f"Please place credentials.json beside storage_service.py."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE),
                SCOPES
            )

            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent"
            )

            # Save token
            with open(TOKEN_FILE, "w", encoding="utf-8") as token:

                token.write(creds.to_json())

        # --------------------------------------------------------------------
        # Build Drive API service
        # --------------------------------------------------------------------

        self.service = build(
            "drive",
            "v3",
            credentials=creds
        )

        print("Google Drive authentication successful.")

    # ========================================================================
    # FIND EXISTING FILE
    # ========================================================================

    def find_file(self, file_name, parent_id=None):

        query_parts = [
            f"name = '{self._escape_query_value(file_name)}'",
            "trashed = false"
        ]

        if parent_id:
            query_parts.append(
                f"'{parent_id}' in parents"
            )

        query = " and ".join(query_parts)

        response = (
            self.service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name, webViewLink)",
                pageSize=100
            )
            .execute()
        )

        files = response.get("files", [])

        if not files:
            return None

        file = files[0]

        return {
            "id": file["id"],
            "name": file["name"],
            "web_url": (
                f"https://drive.google.com/file/d/"
                f"{file['id']}/view"
            ),
            "folder_id": parent_id
        }

    # ========================================================================
    # FIND FOLDER
    # ========================================================================

    def find_folder(self, folder_name, parent_id=None):

        query_parts = [
            f"name = '{self._escape_query_value(folder_name)}'",
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false"
        ]

        if parent_id:
            query_parts.append(
                f"'{parent_id}' in parents"
            )

        query = " and ".join(query_parts)

        response = (
            self.service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                pageSize=100
            )
            .execute()
        )

        folders = response.get("files", [])

        if not folders:
            return None

        return folders[0]["id"]

    # ========================================================================
    # CREATE FOLDER
    # ========================================================================

    def create_folder(self, folder_name, parent_id=None):

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }

        if parent_id:

            metadata["parents"] = [parent_id]

        folder = (
            self.service.files()
            .create(
                body=metadata,
                fields="id, name"
            )
            .execute()
        )

        print(
            f"Created Google Drive folder: "
            f"{folder['name']} ({folder['id']})"
        )

        return folder["id"]

    # ========================================================================
    # GET OR CREATE FOLDER
    # ========================================================================

    def get_or_create_folder(self, folder_name, parent_id=None):

        folder_id = self.find_folder(
            folder_name,
            parent_id
        )

        if folder_id:

            return folder_id

        return self.create_folder(
            folder_name,
            parent_id
        )

    # ========================================================================
    # PAYMENT SCHEDULE ROOT FOLDER
    # ========================================================================

    def get_payment_schedule_folder(self):

        """
        Returns:

            Payment Schedule/
        """

        return self.get_or_create_folder(
            self.root_folder_name
        )

    # ========================================================================
    # MONTH FOLDER
    # ========================================================================

    def get_month_folder(self, month_name):

        """
        Returns:

            Payment Schedule/
                YYYY-MM/
        """

        if not month_name:

            raise ValueError(
                "month_name cannot be empty."
            )

        root_id = self.get_payment_schedule_folder()

        return self.get_or_create_folder(
            str(month_name),
            root_id
        )

    # ========================================================================
    # UPLOAD PAYMENT SCHEDULE
    # ========================================================================

    def upload_payment_schedule(
        self,
        pdf_path,
        month_name,
        drive_file_name=None,
        skip_if_exists=True
    ):
        """
        Upload a payment schedule PDF to:

            Payment Schedule/
                YYYY-MM/

        Parameters
        ----------
        pdf_path:
            Local PDF file.

        month_name:
            Google Drive month folder.
            Example: 2026-08

        drive_file_name:
            Optional filename for Google Drive.

        skip_if_exists:
            If True, an existing file with the same name
            will not be uploaded again.

        Returns
        -------
        dict
        """

        try:

            # ---------------------------------------------------------------
            # Validate PDF
            # ---------------------------------------------------------------

            pdf_path = Path(pdf_path)

            if not pdf_path.exists():
                raise FileNotFoundError(
                    f"PDF file not found: {pdf_path}"
                )

            if pdf_path.suffix.lower() != ".pdf":
                raise ValueError(
                    f"Expected PDF file: {pdf_path}"
                )

            # ---------------------------------------------------------------
            # Get month folder
            # ---------------------------------------------------------------

            month_folder_id = self.get_month_folder(
                month_name
            )

            # ---------------------------------------------------------------
            # Determine filename
            # ---------------------------------------------------------------

            file_name = (
                drive_file_name
                if drive_file_name
                else pdf_path.name
            )

            if not file_name.lower().endswith(".pdf"):
                file_name += ".pdf"

            # ---------------------------------------------------------------
            # Check existing file
            # ---------------------------------------------------------------

            if skip_if_exists:

                existing = self.find_file(
                    file_name,
                    month_folder_id
                )

                if existing:

                    print(
                        f"File already exists in Google Drive: "
                        f"{file_name}"
                    )

                    existing["success"] = True
                    existing["uploaded"] = False
                    existing["public"] = True
                    existing["comment"] = (
                        "File already exists in Google Drive."
                    )

                    return existing

            # ---------------------------------------------------------------
            # MIME type
            # ---------------------------------------------------------------

            mime_type = (
                mimetypes.guess_type(str(pdf_path))[0]
                or "application/pdf"
            )

            # ---------------------------------------------------------------
            # Google Drive metadata
            # ---------------------------------------------------------------

            metadata = {
                "name": file_name,
                "parents": [month_folder_id]
            }

            # ---------------------------------------------------------------
            # Upload
            # ---------------------------------------------------------------

            media = MediaFileUpload(
                str(pdf_path),
                mimetype=mime_type,
                resumable=True
            )

            uploaded_file = (
                self.service.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id, name, webViewLink"
                )
                .execute()
            )

            file_id = uploaded_file["id"]

            print(
                f"Uploaded to Google Drive: "
                f"{uploaded_file['name']}"
            )

            # ---------------------------------------------------------------
            # Make publicly accessible
            # ---------------------------------------------------------------

            public = self._make_file_public(
                file_id
            )

            # ---------------------------------------------------------------
            # Build URL
            # ---------------------------------------------------------------

            web_url = (
                f"https://drive.google.com/file/d/"
                f"{file_id}/view"
            )

            return {
                "success": True,
                "uploaded": True,
                "id": file_id,
                "name": uploaded_file["name"],
                "web_url": web_url,
                "folder_id": month_folder_id,
                "public": public,
                "comment": "PDF uploaded successfully."
            }

        except Exception as error:

            print(
                f"Google Drive upload failed: {error}"
            )

            return {
                "success": False,
                "uploaded": False,
                "id": "",
                "name": "",
                "web_url": "",
                "folder_id": "",
                "public": False,
                "comment": str(error)
            }

    # ========================================================================
    # BACKWARD COMPATIBILITY
    # ========================================================================

    def upload_pdf(
        self,
        pdf_path,
        month_name,
        drive_file_name=None,
        skip_if_exists=True
    ):
        """
        Backward-compatible wrapper around upload_payment_schedule().
        """

        return self.upload_payment_schedule(
            pdf_path=pdf_path,
            month_name=month_name,
            drive_file_name=drive_file_name,
            skip_if_exists=skip_if_exists
        )

    # ========================================================================
    # MAKE FILE PUBLIC
    # ========================================================================

    def _make_file_public(self, file_id):

        """
        Allow anyone with the link to view the PDF.

        This is required because the customer will receive
        the Google Drive link through SMS and normally will not
        be signed into your Google account.
        """

        permission = {
            "type": "anyone",
            "role": "reader"
        }

        try:

            result = (
                self.service.permissions()
                .create(
                    fileId=file_id,
                    body=permission,
                    fields="id"
                )
                .execute()
            )

            print(
                f"Public permission created for file: "
                f"{file_id}"
            )

            return True

        except HttpError as error:

            print(
                f"Warning: Could not create public permission "
                f"for file {file_id}: {error}"
            )

            return False

    # ========================================================================
    # ESCAPE DRIVE QUERY
    # ========================================================================

    @staticmethod
    def _escape_query_value(value):

        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
        )


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":

    print("=" * 60)
    print("Google Drive Storage Service Test")
    print("=" * 60)

    try:

        drive = GoogleDriveService()

        # ---------------------------------------------------------------
        # Test root folder
        # ---------------------------------------------------------------

        root_id = drive.get_payment_schedule_folder()

        print(
            "\nPayment Schedule folder ID:"
        )

        print(root_id)

        # ---------------------------------------------------------------
        # Test month folder
        # ---------------------------------------------------------------

        month_id = drive.get_month_folder(
            "2026-08"
        )

        print(
            "\n2026-08 folder ID:"
        )

        print(month_id)

        print(
            "\nGoogle Drive connection test successful."
        )

    except Exception as error:

        print(
            "\nGoogle Drive test FAILED."
        )

        print(error)