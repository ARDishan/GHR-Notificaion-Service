# Customer Notification Service

Uploads generated statements to Google Drive and sends customers an SMS with the link, using a message template chosen per notification type. Reads entirely from the shared Supabase database — no Excel upload, no local PDF folder to point at.

## What it does

1. **Load pending customers** — for the chosen notification type (and optional month filter), queries `generated_documents` in Supabase for documents that don't yet have a successful `notification_log` entry for that type. This list is always exactly "who still needs this message" — nothing more.
2. **Start Notification Process** — for each pending document:
   - Uploads the PDF to Google Drive if it hasn't been uploaded yet (reuses the existing link if it has).
   - Sends the SMS via Dialog, using the matching template from `templates/`.
   - Logs the attempt (success or failure) to `notification_log`, so it's never sent twice.
3. **Download notification log (Excel)** — after a run completes, a one-click button appears to download that run's results (customer, unit, phone, status, Drive link, comment, timestamp) as an `.xlsx` file. Browsers block truly automatic downloads for security, so this is a ready-made button rather than a file that appears with zero clicks.

## Project structure

```
streamlit_app.py         Streamlit UI — Load pending, Start process, Excel log download
notification_service.py  Pending-document queries, SMS sending, phone validation, logging
storage_service.py       Google Drive upload (OAuth) — flat Payment Schedule/YYYY-MM/ folders
dialog_sms.py            Dialog SMS gateway client (unchanged from before the DB migration)
config.py                Env var loading (Dialog credentials, DB credentials, paths)
db.py                    Supabase connection (get_engine) — this app never touches the main dashboard DB
templates/                One .txt file per notification type (payment_schedule.txt, due_reminder.txt, ...)
credentials/              credentials.json (Google OAuth client) + token.json (created on first run)
logs/                     notification_service.log
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```
Add the packages listed in `requirements-notification-additions.txt` (`sqlalchemy`, `psycopg2-binary`, `openpyxl`) to your existing `requirements.txt`.

### 2. Configure `.env`

Add these lines to your existing `.env` next to `config.py`:

```env
# Same Supabase credentials as the Statement Generator's .env
DB_HOST=your-project.supabase.co
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_supabase_db_password
DB_SSLMODE=require

# Your existing Dialog / Drive settings stay as they are:
# DIALOG_USERNAME=...
# DIALOG_PASSWORD=...
# DIALOG_SOURCE_ADDRESS=...
# DIALOG_PAYMENT_METHOD=...
```

This app never needs `MASTER_DB_*` credentials — it only ever talks to Supabase.

### 3. Set up the shared database

Run `schema.sql` against the same Supabase project the Statement Generator uses — see the [top-level README](../README.md#shared-database-setup-do-this-once). Both apps must point at the same Supabase database.

### 4. Google Drive credentials

Make sure `credentials/credentials.json` (your Google OAuth client, downloaded from Google Cloud Console) is in place. `credentials/token.json` is created automatically the first time you upload a PDF — it'll open a browser window for you to sign in and authorize.

### 5. Run it

```bash
streamlit run streamlit_app.py
```

## Using the app

1. Pick a **Notification Type** (`payment_schedule`, `due_reminder_1`, `due_reminder_2`, `welcome_letter`, `offer_letter`) and, optionally, a **month folder filter**.
2. Click **Load pending customers** — review the table. This already excludes anyone who's already been successfully notified for this type.
3. Tick **"I understand REAL SMS messages will be sent to these customers"**, then **Start Notification Process**.
4. Watch the process log; when it finishes, download the Excel log if you want a record.

## Key design notes

- **`document_type` vs `notification_type`.** `DOCUMENT_TYPE_BY_NOTIFICATION` in `streamlit_app.py` maps each notification type to the kind of document it should pull. Both reminder stages (`due_reminder_1`, `due_reminder_2`) reuse the same `payment_schedule` document — they're different *messages* about the same PDF, not different documents. Add new reminder stages by adding a template file and a line in `NOTIFICATION_TYPES`/`DOCUMENT_TYPE_BY_NOTIFICATION` — no schema change needed.
- **Duplicate-send protection.** A notification only counts as "done" once its `notification_log` row has status `SUCCESS` — this is normalized in code regardless of what casing the SMS gateway itself returns (Dialog's API happens to return lowercase `"success"`), so the pending-query check reliably matches.
- **Drive folder structure is flat**: `Payment Schedule/YYYY-MM/file.pdf`. No per-document-type subfolder — that was tried and reverted since it just added a redundant-looking nested folder when there's really only one type in regular use.
- **No Dry Run mode.** Every send is real. The one remaining safety net is the manual confirmation checkbox before the Start button becomes clickable.
- **No Excel upload / local PDF folder.** Both were removed once the shared database took over — `generated_documents` already has everything (PDF bytes, phone, project, month) needed to process a batch.

## Troubleshooting

- **`GoogleDriveService.upload_bytes() got an unexpected keyword argument 'document_type'`** — you're running an older copy of `storage_service.py`. Make sure the one in this project matches the current version (it accepts `document_type` for compatibility but doesn't use it for folder placement).
- **Same customer gets messaged again on a re-run** — check `notification_log` for that customer/type; the status should read exactly `SUCCESS`. If you see lowercase `success` in there, that row was written before the casing fix and won't be recognized as done — resolve manually (delete or update that row) if needed.
- **`could not translate host name "...@db...."`** — see the [Statement Generator's README](../statement-generator/README.md#troubleshooting); same root cause and fix, since both apps share `db.py`'s connection logic.
- **A customer never appears in "pending"** — check that their `generated_documents` row's `document_type` matches what `DOCUMENT_TYPE_BY_NOTIFICATION` expects for the notification type you selected, and that the month filter (if set) matches their `month_folder`.
