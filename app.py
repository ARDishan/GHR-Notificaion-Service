import os
import re
import threading
import traceback
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox

from notification_service import NotificationService
from storage_service import GoogleDriveService


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class CustomerNotificationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GHR Customer Notification Service")
        self.geometry("900x700")
        self.minsize(800,600)
        self.excel_path = tk.StringVar()
        self.pdf_folder = tk.StringVar()
        self.month = tk.StringVar(value=datetime.now().strftime("%Y-%m"))

        self.notification_type = tk.StringVar(
            value="payment_schedule"
        )

        self.dry_run = tk.BooleanVar(
            value=True
        )

        self.status = tk.StringVar(
            value="Ready."
        )

        self.results = []

        self._build_ui()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):

        main = ttk.Frame(
            self,
            padding=20
        )

        main.pack(
            fill="both",
            expand=True
        )

        # ---------------------------------------------------------------
        # Title
        # ---------------------------------------------------------------

        ttk.Label(
            main,
            text="GHR Customer Notification Service",
            font=("Segoe UI", 20, "bold"),
        ).pack(
            anchor="w"
        )

        ttk.Label(
            main,
            text=(
                "Upload customer documents to Google Drive "
                "and send notification SMS."
            ),
            font=("Segoe UI", 10),
        ).pack(
            anchor="w",
            pady=(3, 20)
        )

        # ---------------------------------------------------------------
        # Settings
        # ---------------------------------------------------------------

        settings = ttk.LabelFrame(
            main,
            text="Notification Settings",
            padding=15
        )

        settings.pack(
            fill="x"
        )

        # Excel

        ttk.Label(
            settings,
            text="Excel File:"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=8
        )

        ttk.Entry(
            settings,
            textvariable=self.excel_path
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=10
        )

        ttk.Button(
            settings,
            text="Browse",
            command=self.select_excel
        ).grid(
            row=0,
            column=2
        )

        # PDF folder

        ttk.Label(
            settings,
            text="PDF Folder:"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=8
        )

        ttk.Entry(
            settings,
            textvariable=self.pdf_folder
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=10
        )

        ttk.Button(
            settings,
            text="Browse",
            command=self.select_pdf_folder
        ).grid(
            row=1,
            column=2
        )

        # Month

        ttk.Label(
            settings,
            text="Drive Folder:"
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=8
        )

        ttk.Entry(
            settings,
            textvariable=self.month,
            width=20
        ).grid(
            row=2,
            column=1,
            sticky="w",
            padx=10
        )

        # Notification

        ttk.Label(
            settings,
            text="Notification:"
        ).grid(
            row=3,
            column=0,
            sticky="w",
            pady=8
        )

        notification_combo = ttk.Combobox(
            settings,
            textvariable=self.notification_type,
            values=[
                "payment_schedule",
                "welcome_letter",
                "offer_letter",
                "due_reminder",
            ],
            state="readonly",
            width=30
        )

        notification_combo.grid(
            row=3,
            column=1,
            sticky="w",
            padx=10
        )

        settings.columnconfigure(
            1,
            weight=1
        )

        # ---------------------------------------------------------------
        # Mode
        # ---------------------------------------------------------------

        mode_frame = ttk.Frame(
            main
        )

        mode_frame.pack(
            fill="x",
            pady=15
        )

        ttk.Checkbutton(
            mode_frame,
            text="Dry Run — do NOT send SMS",
            variable=self.dry_run
        ).pack(
            side="left"
        )

        ttk.Label(
            mode_frame,
            text=(
                "Recommended for testing"
            )
        ).pack(
            side="left",
            padx=10
        )

        # ---------------------------------------------------------------
        # Buttons
        # ---------------------------------------------------------------

        button_frame = ttk.Frame(
            main
        )

        button_frame.pack(
            fill="x",
            pady=5
        )

        self.start_button = ttk.Button(
            button_frame,
            text="Start Notification Process",
            command=self.start_process
        )

        self.start_button.pack(
            side="left"
        )

        ttk.Button(
            button_frame,
            text="Clear Log",
            command=self.clear_log
        ).pack(
            side="left",
            padx=10
        )

        # ---------------------------------------------------------------
        # Progress
        # ---------------------------------------------------------------

        self.progress = ttk.Progressbar(
            main,
            mode="determinate"
        )

        self.progress.pack(
            fill="x",
            pady=(15, 5)
        )

        # ---------------------------------------------------------------
        # Log
        # ---------------------------------------------------------------

        log_frame = ttk.LabelFrame(
            main,
            text="Process Log",
            padding=5
        )

        log_frame.pack(
            fill="both",
            expand=True,
            pady=10
        )

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled"
        )

        self.log_text.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar = ttk.Scrollbar(
            log_frame,
            command=self.log_text.yview
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.log_text.configure(
            yscrollcommand=scrollbar.set
        )

        # ---------------------------------------------------------------
        # Status
        # ---------------------------------------------------------------

        ttk.Label(
            self,
            textvariable=self.status,
            relief="sunken",
            anchor="w",
            padding=5
        ).pack(
            fill="x",
            side="bottom"
        )

    # -----------------------------------------------------------------------
    # File selection
    # -----------------------------------------------------------------------

    def select_excel(self):

        path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*"),
            ]
        )

        if path:
            self.excel_path.set(path)

    def select_pdf_folder(self):

        path = filedialog.askdirectory(
            title="Select PDF Folder"
        )

        if path:
            self.pdf_folder.set(path)

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def log(self, message):

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        self.after(
            0,
            self._write_log,
            f"[{timestamp}] {message}"
        )

    def _write_log(self, message):

        self.log_text.configure(
            state="normal"
        )

        self.log_text.insert(
            "end",
            message + "\n"
        )

        self.log_text.see(
            "end"
        )

        self.log_text.configure(
            state="disabled"
        )

    def clear_log(self):

        self.log_text.configure(
            state="normal"
        )

        self.log_text.delete(
            "1.0",
            "end"
        )

        self.log_text.configure(
            state="disabled"
        )

    # -----------------------------------------------------------------------
    # Start
    # -----------------------------------------------------------------------

    def start_process(self):

        if not self.excel_path.get():

            messagebox.showerror(
                "Missing Excel",
                "Please select the Excel file."
            )

            return

        if not os.path.isfile(
            self.excel_path.get()
        ):

            messagebox.showerror(
                "Invalid Excel",
                "Selected Excel file does not exist."
            )

            return

        if not self.pdf_folder.get():

            messagebox.showerror(
                "Missing PDF Folder",
                "Please select the folder containing the generated PDFs."
            )

            return

        if not os.path.isdir(
            self.pdf_folder.get()
        ):

            messagebox.showerror(
                "Invalid PDF Folder",
                "Selected PDF folder does not exist."
            )

            return

        # ---------------------------------------------------------------
        # Confirm real SMS
        # ---------------------------------------------------------------

        if not self.dry_run.get():

            answer = messagebox.askyesno(
                "Confirm SMS Sending",
                (
                    "Dry Run is disabled.\n\n"
                    "REAL SMS messages will be sent to customers.\n\n"
                    "Do you want to continue?"
                )
            )

            if not answer:
                return

        self.start_button.configure(
            state="disabled"
        )

        self.progress["value"] = 0

        thread = threading.Thread(
            target=self.run_process,
            daemon=True
        )

        thread.start()

    # -----------------------------------------------------------------------
    # Main process
    # -----------------------------------------------------------------------

    def run_process(self):

        service = None
        drive = None

        try:

            self.log(
                "Starting Customer Notification Service..."
            )

            excel_file = self.excel_path.get()

            pdf_folder = Path(
                self.pdf_folder.get()
            )

            month = self.month.get().strip()

            notification_type = (
                self.notification_type.get()
            )

            dry_run = self.dry_run.get()

            # -----------------------------------------------------------
            # Read Excel
            # -----------------------------------------------------------

            service = NotificationService()

            df = service.load_excel(
                excel_file
            )

            self.log(
                f"Excel loaded: {len(df)} row(s)"
            )

            # -----------------------------------------------------------
            # Connect Google Drive
            # -----------------------------------------------------------

            self.log(
                "Connecting to Google Drive..."
            )

            drive = GoogleDriveService()

            self.log(
                "Google Drive connection successful."
            )

            # -----------------------------------------------------------
            # Process each PDF
            # -----------------------------------------------------------

            processed = set()

            groups = df.groupby(
                [
                    "CUSTOMER",
                    "Unit REF ID",
                    "FILE NAME",
                ],
                sort=False
            )

            total = len(groups)

            self.after(
                0,
                self.set_progress_max,
                total
            )

            success_count = 0
            failed_count = 0

            for index, (
                key,
                group
            ) in enumerate(
                groups,
                start=1
            ):

                customer = key[0]
                unit_ref = key[1]
                excel_file_name = key[2]

                phone = group[
                    "PHONE NO"
                ].iloc[0]

                project = group[
                    "PROJECT"
                ].iloc[0]

                # -------------------------------------------------------
                # Find local PDF
                # -------------------------------------------------------

                pdf_path = self.find_pdf(
                    pdf_folder,
                    excel_file_name
                )

                if not pdf_path:

                    self.log(
                        f"[{index}/{total}] PDF not found: "
                        f"{excel_file_name}"
                    )

                    failed_count += 1

                    self.after(
                        0,
                        self.update_progress,
                        index
                    )

                    continue

                self.log(
                    f"[{index}/{total}] Processing "
                    f"{customer} - {unit_ref}"
                )

                # -------------------------------------------------------
                # Upload to Google Drive
                # -------------------------------------------------------

                upload_result = drive.upload_payment_schedule(
                    pdf_path=pdf_path,
                    month_name=month,
                    drive_file_name=pdf_path.name,
                    skip_if_exists=True,
                )

                if not upload_result.get("success"):
                    self.log(
                        "  Drive: FAILED - "
                        + str(upload_result.get("comment", "Unknown error"))
                    )

                    failed_count += 1

                    self.after(
                        0,
                        self.update_progress,
                        index
                    )

                    continue

                drive_file_id = upload_result["id"]

                self.log(
                    f"  Drive: {upload_result['web_url']}"
                )

                # -------------------------------------------------------
                # Send SMS
                # -------------------------------------------------------

                sms_result = (
                    service.send_notification(
                        customer=customer,
                        phone=phone,
                        unit_ref=unit_ref,
                        project=project,
                        drive_file_id=drive_file_id,
                        notification_type=notification_type,
                        dry_run=dry_run,
                    )
                )

                if sms_result.get("success"):

                    success_count += 1

                    self.log(
                        "  SMS: SUCCESS"
                    )

                else:

                    failed_count += 1

                    self.log(
                        "  SMS: FAILED - "
                        + str(
                            sms_result.get(
                                "comment",
                                ""
                            )
                        )
                    )

                self.after(
                    0,
                    self.update_progress,
                    index
                )

            # -----------------------------------------------------------
            # Summary
            # -----------------------------------------------------------

            self.log("")
            self.log("=" * 60)
            self.log("PROCESS COMPLETED")
            self.log("=" * 60)
            self.log(
                f"Total notifications : {total}"
            )
            self.log(
                f"Successful          : {success_count}"
            )
            self.log(
                f"Failed              : {failed_count}"
            )

            self.after(
                0,
                self.process_complete,
                total,
                success_count,
                failed_count
            )

        except Exception as e:

            self.log(
                f"ERROR: {e}"
            )

            self.log(
                traceback.format_exc()
            )

            self.after(
                0,
                self.process_error,
                str(e)
            )

        finally:

            if service:

                service.close()

            self.after(
                0,
                lambda: self.start_button.configure(
                    state="normal"
                )
            )

    # -----------------------------------------------------------------------
    # Find PDF
    # -----------------------------------------------------------------------

    @staticmethod
    def find_pdf(
        pdf_folder,
        excel_file_name
    ):

        # Remove extension if Excel already contains one
        base_name = Path(
            str(excel_file_name)
        ).stem

        # Exact expected filename
        candidates = [
            pdf_folder / f"{base_name}.pdf",
            pdf_folder / str(excel_file_name),
        ]

        for candidate in candidates:

            if candidate.exists():
                return candidate

        # Sanitized filename fallback
        safe_name = re.sub(
            r'[<>:"/\\|?*]',
            "_",
            base_name
        )

        candidate = (
            pdf_folder /
            f"{safe_name}.pdf"
        )

        if candidate.exists():
            return candidate

        # Search recursively
        for file in pdf_folder.rglob("*.pdf"):

            if file.stem == base_name:
                return file

            if file.stem == safe_name:
                return file

        return None

    # -----------------------------------------------------------------------
    # Progress
    # -----------------------------------------------------------------------

    def set_progress_max(
        self,
        maximum
    ):

        self.progress["maximum"] = maximum

    def update_progress(
        self,
        value
    ):

        self.progress["value"] = value

        self.status.set(
            f"Processing {value}/"
            f"{int(self.progress['maximum'])}..."
        )

    # -----------------------------------------------------------------------
    # Complete
    # -----------------------------------------------------------------------

    def process_complete(
        self,
        total,
        success,
        failed
    ):

        self.status.set(
            f"Completed — {success} successful, "
            f"{failed} failed."
        )

        messagebox.showinfo(
            "Completed",
            (
                f"Notification process completed.\n\n"
                f"Total: {total}\n"
                f"Successful: {success}\n"
                f"Failed: {failed}"
            )
        )

    # -----------------------------------------------------------------------
    # Error
    # -----------------------------------------------------------------------

    def process_error(
        self,
        error
    ):
        self.status.set(
            "Process failed."
        )
        messagebox.showerror(
            "Error",
            error
        )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = CustomerNotificationApp()
    app.mainloop()