# Business Card Contact Manager

A focused Python + Streamlit application: photograph or upload a card, extract text with real Tesseract OCR, review the editable details, choose or create a category, add a remark, and save. SQLite stores the records and every change regenerates a formatted Excel workbook. No contacts or categories are seeded.

## Quick start

Requires Python 3.12 or newer and Tesseract 5 with English language data. Tested on Python 3.12 with the pinned requirements.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows PowerShell activation: `.venv\Scripts\Activate.ps1`.

Open the URL printed by Streamlit (normally http://localhost:8501). If another app uses that port, run `streamlit run app.py --server.port 8502`.

Install Tesseract separately:

- macOS: `brew install tesseract`
- Ubuntu / Debian: `sudo apt-get update && sudo apt-get install tesseract-ocr tesseract-ocr-eng`
- Windows: install a Tesseract build following [Tesseract's installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html), then add its installation directory to PATH or set `TESSERACT_CMD` to the executable's full path.

Check installation with `tesseract --version` and `tesseract --list-langs`. No paid API, API key, or OCR model download is needed. If OCR is unavailable, manual entry remains usable.

## Using the app

1. On **Scan Card**, choose Take Photo or Choose From Gallery. Capture/upload the front and enable **Add back of card** for a second photo. Each side has independent crop and rotation controls. Camera availability depends on browser permission and hardware; use gallery if unavailable.
2. Preview the image, optionally crop to the card area or rotate it, and click **Process Card**. OCR runs only on that click, with visible progress. The engine compares block, sparse, automatic-layout, and inverted-image OCR results. Fields are suggestions, never automatically saved. Use **Adjust Photo / Add Back / Reprocess Card** from review to retry; reprocessing replaces the extracted draft fields.
3. Compare the original photo with **Review Contact Details**. Correct every field as needed. Uncertain or unavailable fields remain blank. Latin-script English parsing is the initial implementation; name/company/address heuristics can misclassify unusual layouts.
4. Search/select **Select Existing Category**, or type **Create New Category**. A typed new name takes precedence over the selected existing category. Categories are created only when the contact successfully saves. Leading/trailing whitespace, repeated internal spaces, and case differences are normalized.
5. Add an optional remark and click **Save Contact**. Category plus at least a name, company, mobile number, or email is required. Malformed email values need correction or removal.
6. Select **Scan Next Card** to clear the draft immediately, or **View Contacts**.
7. Contacts supports case-insensitive substring search and category filtering together, compact cards, a table view, full details/original image, editing and confirmed deletion. Editing preserves the stable record ID and creation date/time.
8. Categories supports renaming (including updating the Excel category values) and confirmed deletion of unused categories. Used categories cannot be deleted until their contacts are reassigned.
9. **Excel Data → Download Excel** downloads current records in `Business_Card_Contacts.xlsx` with a `Contacts` sheet and all 20 requested columns.

Uploads accept JPG/JPEG/PNG/WEBP, maximum 10 MB and 40 megapixels. The actual image is validated in addition to the filename/MIME. EXIF orientation, resizing and mild local contrast enhancement apply only to the OCR copy. The stored original retains its original bytes. All stored filenames are generated UUIDs.

## Project structure

```text
app.py                      Streamlit entry point, style, navigation
pages/scan_card.py          Capture, preview, OCR, review, success
pages/contacts.py           Search/filter, view, edit, delete dialog
pages/categories.py         Rename and safely delete categories
pages/excel_data.py         Workbook information and fresh download
services/ocr_service.py     Cached Tesseract engine configuration
services/contact_parser.py OCR-to-field regex and conservative heuristics
services/image_service.py  Validation, preprocessing, original file storage
services/database_service.py SQLite repository and synchronized mutations
services/excel_service.py  Workbook building and atomic replacement
services/category_service.py Category helpers
models/                    Contact/category models
utils/                     Constants, validation, shared UI helpers
 tests/                    Service integration tests and Streamlit AppTest
```

## Persistence and Excel integrity

On first launch, directories, the SQLite database, schema, and empty workbook are created automatically. No manual SQL step is needed.

Default locations (relative to the project):

- `data/contacts.db`: SQLite source of truth.
- `data/exports/Business_Card_Contacts.xlsx`: maintained workbook.
- `storage/business_cards/`: original card images.

The workbook contains exactly: Sr No, Date Added, Time Added, Name, Designation, Company Name, Mobile Number, Alternate Mobile, Telephone Number, Email, Alternate Email, Website, Full Address, City, State, PIN Code, Country, Category, Remark, Business Card Image Reference.

The database uses WAL, foreign keys, parameterized queries, a 30-second busy timeout, and stable IDs. Visible serial numbers are generated from ID order, so deletion produces sequential Excel rows without changing IDs. The Excel exporter writes a validated temporary workbook and atomically replaces the previous file. A SQLite immediate transaction serializes mutations and workbook publication so overlapping sessions cannot publish an older snapshot after a newer save. Export errors roll back contact/category changes; startup and on-demand export heal interrupted exports from committed SQLite records. SQLite and a filesystem cannot provide one crash-atomic transaction together; SQLite remains authoritative after a process or machine crash.

An edit checks the record's update timestamp and rejects stale edits from another session. On-demand downloads rebuild from current database data. Excel has a bold header, frozen top row, AutoFilter, readable widths, native dates/times, and wrapped address/remark cells. Phone and PIN values stay text, preserving leading zeros and `+` prefixes. Contact strings stay literal text so uploaded values cannot become Excel formulas. Front and back originals are saved separately and displayed together in review, view, and edit. The existing database migrates automatically by adding an optional back-image column; older contacts remain intact. Excel keeps its 20-column structure, with both references separated by a semicolon in Business Card Image Reference. OCR passes and both sides contribute complementary fields; phone/email duplicates are normalized, and conflicting suggestions appear under Other detected values for review. A failed or blank side does not discard a successful side. Original image references are relative `business_cards/card_<uuid>.<ext>` paths; images are not embedded in Excel. Keep the image folder alongside backups.

Do not manually edit the maintained workbook expecting changes to flow back into the app. SQLite-to-Excel synchronization is one-way; use Edit in Contacts.

## Configuration

See `.env.example`. Variables must be exported in the shell or set in the hosting platform; the app intentionally does not automatically load `.env` files.

| Variable | Default | Purpose |
|---|---|---|
| `BCCM_TIMEZONE` | `Asia/Kolkata` | Zone used for contact Date Added and Time Added |
| `BCCM_DATA_DIR` | `<project>/data` | Database and exports root |
| `BCCM_IMAGE_DIR` | `<project>/storage/business_cards` | Original image storage |
| `TESSERACT_CMD` | PATH lookup | Optional absolute executable path |
| `BCCM_OCR_LANGUAGE` | `eng` | Installed Tesseract language code(s) |

Restart after changing configuration. To use additional languages, install their Tesseract language packages, e.g. `tesseract-ocr-hin`, and set `BCCM_OCR_LANGUAGE=eng+hin`; structured parsing is currently optimized for English text.

No contacts/categories are cached. OCR executable configuration and the initialized repository are cached with `st.cache_resource`; Tesseract itself loads its trained data in an isolated process on each explicitly requested OCR operation.

## Deployment

### Preferred: persistent Streamlit-compatible host

Use a VM or container host that supports an always-running Python process, Streamlit's browser connection, HTTPS and a persistent local disk. Run a single app instance against the disk; SQLite is not designed for multiple replicas on network filesystems. Put both data and images on a persistent volume. This local backend is isolated in `ContactStore` and `image_service`, allowing later replacement by a hosted database and object storage without replacing the UI/OCR layers; remote adapters are not included in this version.

A Dockerfile includes Tesseract and a non-root app user:

```bash
docker build -t business-card-contacts .
docker volume create bccm-storage
docker run --rm -p 8501:8501 -v bccm-storage:/var/lib/bccm business-card-contacts
```

Use HTTPS and access control provided by your host/reverse proxy when deploying for a team. This version is a shared single collection and has no built-in login or per-user tenancy. Local preview binds to loopback; do not expose a public contact collection without appropriate host access control.

### Streamlit Community Cloud

Deploy `app.py` and `requirements.txt`; `packages.txt` installs system Tesseract packages. Follow [Streamlit's deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app). Community Cloud's local storage is not guaranteed durable across reboots/redeployments: use it only for a disposable pilot with backups, or implement durable remote database/file adapters before collecting permanent contacts. Excel regeneration cannot recover a lost SQLite database.

### Vercel feasibility

The app remains Python + Streamlit. Vercel's documented [Python Functions runtime](https://vercel.com/docs/functions/runtimes/python) does not establish supported hosting for the long-running `streamlit run app.py` process. Vercel runtime capabilities evolve; do not assume a Python function wrapper supplies a compatible persistent Streamlit server and durable SQLite disk. No unsupported Vercel shim is included. Host this app on a persistent Streamlit-compatible service; a Vercel site can link to its HTTPS URL if desired.

### Camera and mobile

Camera access requires localhost or HTTPS, a browser with camera support, and user permission. To scan from a phone, deploy using HTTPS. A desktop `localhost` URL cannot be opened directly from another device. Phone gallery upload is an available fallback. Compact contact cards are the default and the form/image columns stack below 700px. Device camera behavior still requires checking on the intended real phone.

## Backups

Back up the database with SQLite's backup API (or stop the app before copying it), and copy the original image folder. If copying a live SQLite database directly, WAL files may contain uncheckpointed changes; prefer the backup API. Excel alone does not contain images or raw OCR text and cannot fully restore the app. Keep periodic backups of both persistent directories.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and images. They cover empty startup, real OCR on a generated card, partial/empty OCR, image validation, first category creation and normalization, corrections, search/filter, edits, category rename/delete guards, contact deletion, sequential Excel serials, restart persistence, Excel formatting/download bytes, concurrent writes, failed-export rollback, stale edit protection, literal Excel strings, and Streamlit form/page workflows. Real OCR tests require installed Tesseract and Arial (macOS) or DejaVu Sans (Linux).

## Troubleshooting

- **Tesseract not found:** install it, verify PATH, or set `TESSERACT_CMD`. Use Enter Manually in the meantime.
- **Low-quality OCR:** use a sharp, evenly lit image with visible card edges. Re-upload/Process Card to retry. Correct the form; heuristics never guarantee perfect extraction.
- **Missing language data:** check `tesseract --list-langs` against `BCCM_OCR_LANGUAGE`.
- **Excel cannot be updated:** close the file in Excel (especially on Windows), verify export folder permissions, then retry. The app does not report a save as successful when export fails.
- **Database locked:** ensure the volume is a local filesystem and only this app uses the DB. Do not run multiple replicas against SQLite. Operations wait up to 30 seconds.
- **Images missing after deployment:** preserve both configured persistent folders. Ephemeral hosting cannot retain them reliably.
- **Camera unavailable:** allow browser access on HTTPS/localhost, or upload a photo from gallery.
- **Invalid email:** correct OCR mistakes or clear the field. Only category and one useful identifier are required.
