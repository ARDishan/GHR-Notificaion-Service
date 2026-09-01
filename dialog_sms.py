"""
dialog_sms.py

Reusable Dialog eSMS Gateway client.

Usage:

    from dialog_sms import DialogSMS

    dialog = DialogSMS()

    result = dialog.send_sms(
        mobile="771234567",
        message="Dear Sir/Madam, your document is ready."
    )

    if result["success"]:
        print("SMS sent successfully")
    else:
        print("SMS failed:", result["comment"])
"""

import os
import random
import time
from datetime import datetime

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DIALOG_LOGIN_URL = "https://esms.dialog.lk/api/v2/user/login"
DIALOG_SMS_URL = "https://e-sms.dialog.lk/api/v2/sms"


# ---------------------------------------------------------------------------
# Dialog SMS Client
# ---------------------------------------------------------------------------

class DialogSMS:

    def __init__(
        self,
        username=None,
        password=None,
        source_address=None,
        payment_method=None,
        timeout=30,
    ):
        """
        Create Dialog SMS client.

        Credentials are normally read from .env:

            DIALOG_USERNAME
            DIALOG_PASSWORD
            DIALOG_SOURCE_ADDRESS
            DIALOG_PAYMENT_METHOD
        """

        self.username = (
            username
            or os.getenv("DIALOG_USERNAME")
        )

        self.password = (
            password
            or os.getenv("DIALOG_PASSWORD")
        )

        self.source_address = (
            source_address
            or os.getenv("DIALOG_SOURCE_ADDRESS", "")
        )

        self.payment_method = (
            payment_method
            or os.getenv("DIALOG_PAYMENT_METHOD", "4")
        )

        self.timeout = timeout

        # Access token is kept in memory.
        self.access_token = None

        # Reuse HTTP connection.
        self.session = requests.Session()

    # -----------------------------------------------------------------------
    # Validate configuration
    # -----------------------------------------------------------------------

    def validate_config(self):
        """
        Validate Dialog configuration.

        Raises:
            ValueError: if username/password are missing.
        """

        if not self.username:
            raise ValueError(
                "DIALOG_USERNAME is not configured."
            )

        if not self.password:
            raise ValueError(
                "DIALOG_PASSWORD is not configured."
            )

    # -----------------------------------------------------------------------
    # Login
    # -----------------------------------------------------------------------

    def login(self):
        """
        Get a new Dialog access token.

        The token is stored in self.access_token.
        """

        self.validate_config()

        payload = {
            "username": self.username,
            "password": self.password,
        }

        headers = {
            "Content-Type": "application/json"
        }

        try:
            response = self.session.post(
                DIALOG_LOGIN_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

        except requests.RequestException as e:
            raise RuntimeError(
                f"Unable to connect to Dialog login API: {e}"
            )

        try:
            data = response.json()

        except ValueError:
            raise RuntimeError(
                "Dialog login API returned an invalid response:\n"
                + response.text
            )

        # HTTP-level error
        if response.status_code >= 400:
            raise RuntimeError(
                f"Dialog login failed. "
                f"HTTP {response.status_code}: "
                f"{data}"
            )

        # Dialog-level error
        if data.get("status") != "success":
            raise RuntimeError(
                "Dialog login failed: "
                + str(data.get("comment", data))
            )

        token = data.get("token")

        if not token:
            raise RuntimeError(
                "Dialog login succeeded but no access token "
                "was returned."
            )

        self.access_token = token

        return {
            "success": True,
            "token": token,
            "status": data.get("status", ""),
            "comment": data.get("comment", ""),
            "remaining_count": data.get(
                "remainingCount",
                ""
            ),
            "expiration": data.get(
                "expiration",
                ""
            ),
        }

    # -----------------------------------------------------------------------
    # Ensure token
    # -----------------------------------------------------------------------

    def ensure_token(self):
        """
        Return a valid access token.

        If no token currently exists, login is performed.
        """

        if not self.access_token:
            self.login()

        return self.access_token

    # -----------------------------------------------------------------------
    # Format mobile number
    # -----------------------------------------------------------------------

    @staticmethod
    def format_mobile(mobile):
        """
        Convert common Sri Lankan phone-number formats
        into Dialog's expected 9-digit format.

        Examples:

            0771234567  -> 771234567
            +94771234567 -> 771234567
            94771234567 -> 771234567
            771234567 -> 771234567
        """

        if mobile is None:
            raise ValueError("Mobile number is empty.")

        # Handle Excel numeric values
        if isinstance(mobile, float):
            if mobile.is_integer():
                mobile = str(int(mobile))
            else:
                mobile = str(mobile)

        mobile = str(mobile).strip()

        # Remove common formatting characters
        mobile = (
            mobile
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        # Remove country code
        if mobile.startswith("+94"):
            mobile = mobile[3:]

        elif mobile.startswith("94"):
            mobile = mobile[2:]

        # Remove local leading zero
        if mobile.startswith("0"):
            mobile = mobile[1:]

        # Validate digits
        if not mobile.isdigit():
            raise ValueError(
                f"Invalid mobile number: {mobile}"
            )

        # Must contain exactly 9 digits
        if len(mobile) != 9:
            raise ValueError(
                f"Invalid Sri Lankan mobile number: {mobile}"
            )

        # Sri Lankan mobile numbers should start with 7
        if not mobile.startswith("7"):
            raise ValueError(
                f"Invalid Sri Lankan mobile number: {mobile}"
            )

        return mobile

    # -----------------------------------------------------------------------
    # Generate transaction ID
    # -----------------------------------------------------------------------

    @staticmethod
    def generate_transaction_id():
        """
        Generate a numeric transaction ID.

        Dialog expects a transaction ID within the
        supported numeric length.
        """

        timestamp = int(time.time())

        random_part = random.randint(
            100,
            999
        )

        transaction_id = (
            timestamp * 1000
            + random_part
        )

        # Keep within 18 digits.
        transaction_id = (
            transaction_id
            % 100000000000000000
        )

        return transaction_id

    # -----------------------------------------------------------------------
    # Send SMS
    # -----------------------------------------------------------------------

    def send_sms(
        self,
        mobile,
        message,
        transaction_id=None,
    ):
        """
        Send one SMS through Dialog.

        Returns a dictionary containing:

            success
            status
            comment
            errCode
            transaction_id
            campaign_id
            campaign_cost
            wallet_balance
        """

        # ---------------------------------------------------------------
        # Format mobile
        # ---------------------------------------------------------------

        try:
            mobile = self.format_mobile(mobile)
            print(f"Original mobile: {mobile}")

        except ValueError as e:
            return {
                "success": False,
                "status": "INVALID_MOBILE",
                "comment": str(e),
                "errCode": "",
                "transaction_id": "",
                "campaign_id": "",
                "campaign_cost": "",
                "wallet_balance": "",
            }

        # ---------------------------------------------------------------
        # Get token
        # ---------------------------------------------------------------

        try:
            token = self.ensure_token()

        except Exception as e:
            return {
                "success": False,
                "status": "LOGIN_ERROR",
                "comment": str(e),
                "errCode": "",
                "transaction_id": "",
                "campaign_id": "",
                "campaign_cost": "",
                "wallet_balance": "",
            }

        # ---------------------------------------------------------------
        # Transaction ID
        # ---------------------------------------------------------------

        if transaction_id is None:
            transaction_id = (
                self.generate_transaction_id()
            )

        # ---------------------------------------------------------------
        # Request payload
        # ---------------------------------------------------------------

        msisdn = [
            {
                "mobile": mobile
            }
        ]

        payload = {
            "msisdn": msisdn,
            "message": message,
            "transaction_id": transaction_id,
            "payment_method": self.payment_method,
        }

        # Only include sourceAddress when configured.
        if self.source_address:
            payload["sourceAddress"] = (
                self.source_address
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # ---------------------------------------------------------------
        # Send request
        # ---------------------------------------------------------------

        try:
            response = self.session.post(
                DIALOG_SMS_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

        except requests.RequestException as e:
            return {
                "success": False,
                "status": "CONNECTION_ERROR",
                "comment": str(e),
                "errCode": "",
                "transaction_id": transaction_id,
                "campaign_id": "",
                "campaign_cost": "",
                "wallet_balance": "",
            }

        # ---------------------------------------------------------------
        # Parse response
        # ---------------------------------------------------------------

        try:
            data = response.json()

        except ValueError:
            return {
                "success": False,
                "status": "INVALID_RESPONSE",
                "comment": response.text,
                "errCode": "",
                "transaction_id": transaction_id,
                "campaign_id": "",
                "campaign_cost": "",
                "wallet_balance": "",
            }

        # ---------------------------------------------------------------
        # Token expired
        # ---------------------------------------------------------------

        if data.get("errCode") in [
            "100",
            "105",
            "106",
        ]:

            # Clear old token.
            self.access_token = None

            try:
                # Login again.
                self.login()

            except Exception as e:
                return {
                    "success": False,
                    "status": "TOKEN_REFRESH_ERROR",
                    "comment": str(e),
                    "errCode": data.get(
                        "errCode",
                        ""
                    ),
                    "transaction_id": transaction_id,
                    "campaign_id": "",
                    "campaign_cost": "",
                    "wallet_balance": "",
                }

            # Generate a NEW transaction ID.
            #
            # We intentionally do not reuse the previous ID.
            new_transaction_id = (
                self.generate_transaction_id()
            )

            return self.send_sms(
                mobile=mobile,
                message=message,
                transaction_id=new_transaction_id,
            )

        # ---------------------------------------------------------------
        # Success
        # ---------------------------------------------------------------

        if data.get("status") == "success":

            response_data = (
                data.get("data") or {}
            )

            return {
                "success": True,
                "status": data.get(
                    "status",
                    "",
                ),
                "comment": data.get(
                    "comment",
                    "",
                ),
                "errCode": data.get(
                    "errCode",
                    "",
                ),
                "transaction_id": transaction_id,
                "campaign_id": response_data.get(
                    "campaignId",
                    "",
                ),
                "campaign_cost": response_data.get(
                    "campaignCost",
                    "",
                ),
                "wallet_balance": response_data.get(
                    "walletBalance",
                    "",
                ),
            }

        # ---------------------------------------------------------------
        # Dialog returned an error
        # ---------------------------------------------------------------

        return {
            "success": False,
            "status": data.get(
                "status",
                "FAILED",
            ),
            "comment": data.get(
                "comment",
                response.text,
            ),
            "errCode": data.get(
                "errCode",
                "",
            ),
            "transaction_id": transaction_id,
            "campaign_id": "",
            "campaign_cost": "",
            "wallet_balance": "",
        }

    # -----------------------------------------------------------------------
    # Send multiple SMS
    # -----------------------------------------------------------------------

    def send_bulk(self, records, message_builder=None):
        """
        Send SMS messages to multiple customers.

        records should contain dictionaries such as:

            {
                "customer": "John",
                "phone": "0771234567",
                "message": "Hello John"
            }

        If message_builder is supplied, it should be a function:

            message_builder(record)

        Returns a list of results.
        """

        results = []

        for record in records:

            customer = record.get(
                "customer",
                "",
            )

            phone = record.get(
                "phone",
                "",
            )

            if message_builder:
                message = message_builder(
                    record
                )
            else:
                message = record.get(
                    "message",
                    "",
                )

            result = self.send_sms(
                mobile=phone,
                message=message,
            )

            result["customer"] = customer
            result["phone"] = phone
            result["message"] = message

            results.append(result)

        return results

    # -----------------------------------------------------------------------
    # Close session
    # -----------------------------------------------------------------------

    def close(self):
        """
        Close the HTTP session.
        """
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()

if __name__ == "__main__":

    print("Testing phone number...")

    test_numbers = [
        "719342445",
        "0719342445",
        "+94719342445",
        "94719342445",
    ]

    for number in test_numbers:

        try:
            result = DialogSMS.format_mobile(number)
            print(f"{number} -> {result}")

        except Exception as e:
            print(f"{number} -> ERROR: {e}")