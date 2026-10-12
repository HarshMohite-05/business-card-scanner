"""SQLite repository. Database write locks serialize mutations and workbook publication."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
from services.excel_service import build_workbook, replace_workbook
from services.image_service import store_original, remove_image
from utils.constants import DB_PATH, EXCEL_PATH, TIMEZONE, FIELDS
from utils.validators import clean_category, validate_contact

SELECT = 'SELECT c.*, cat.name AS category FROM contacts c JOIN categories cat ON cat.id=c.category_id'

class ContactStore:
    def __init__(self, db_path=DB_PATH, excel_path=EXCEL_PATH, timezone=TIMEZONE):
        self.db_path, self.excel_path = Path(db_path), Path(excel_path)
        self.timezone = ZoneInfo(timezone)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=30000')
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            fields_sql = ', '.join(f'{field} TEXT NOT NULL DEFAULT \'\'' for field in FIELDS)
            db.executescript(f'''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {fields_sql}, category_id INTEGER NOT NULL REFERENCES categories(id),
                    remark TEXT NOT NULL DEFAULT '', business_card_image TEXT NOT NULL DEFAULT '',
                    ocr_raw_text TEXT NOT NULL DEFAULT '', date_added TEXT NOT NULL,
                    time_added TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS contacts_category ON contacts(category_id);
            ''')
        with self.connection() as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(contacts)')}
            if 'business_card_back_image' not in columns:
                db.execute("ALTER TABLE contacts ADD COLUMN business_card_back_image TEXT NOT NULL DEFAULT ''")
                db.commit()
            if 'added_by' not in columns:
                db.execute("ALTER TABLE contacts ADD COLUMN added_by TEXT NOT NULL DEFAULT ''")
                db.commit()
        # Startup heals any interrupted export; categories are deliberately never seeded.
        self.export_excel()

    def _rows(self, db):
        return [dict(row) for row in db.execute(SELECT + ' ORDER BY c.id')]

    @contextmanager
    def mutation(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                data = build_workbook(self._rows(db))
                replace_workbook(data, self.excel_path)
                db.commit()
            except Exception:
                db.rollback()
                # Restore export if commit failed after publication.
                try:
                    replace_workbook(build_workbook(self._rows(db)), self.excel_path)
                except Exception:
                    pass  # Startup/on-demand export retries from the committed database.
                raise

    def _category(self, db, name, now):
        name = clean_category(name)
        normalized = name.casefold()
        db.execute('INSERT INTO categories(name,normalized_name,created_at) VALUES(?,?,?) ON CONFLICT(normalized_name) DO NOTHING',
                   (name, normalized, now))
        return db.execute('SELECT id FROM categories WHERE normalized_name=?', (normalized,)).fetchone()['id']

    def save_contact(self, values, category, image_data=None, contact_id=None, expected_updated_at=None, back_image_data=None):
        validate_contact(values, category)
        now = datetime.now(self.timezone)
        payload = {field: str(values.get(field, '') or '').strip() for field in FIELDS}
        payload['remark'] = str(values.get('remark', '') or '').strip()
        payload['added_by'] = str(values.get('added_by', '') or '').strip()
        new_image = ''
        new_back_image = ''
        try:
            if image_data is not None and contact_id is None:
                new_image = store_original(image_data)
            if back_image_data is not None and contact_id is None:
                new_back_image = store_original(back_image_data)
            with self.mutation() as db:
                if contact_id is not None:
                    existing = db.execute('SELECT * FROM contacts WHERE id=?', (contact_id,)).fetchone()
                    if existing is None:
                        raise ValueError('This contact was deleted. Return to Contacts.')
                    if expected_updated_at and existing['updated_at'] != expected_updated_at:
                        raise ValueError('This contact changed in another session. Reopen it before saving.')
                payload['category_id'] = self._category(db, category, now.isoformat())
                payload['updated_at'] = now.isoformat()
                if contact_id is None:
                    payload.update(business_card_image=new_image, business_card_back_image=new_back_image, ocr_raw_text=values.get('ocr_raw_text', ''),
                                   date_added=now.date().isoformat(), time_added=now.strftime('%H:%M:%S'), created_at=now.isoformat())
                    names = list(payload)
                    cursor = db.execute(f'INSERT INTO contacts({",".join(names)}) VALUES({",".join("?" for _ in names)})', list(payload.values()))
                    contact_id = cursor.lastrowid
                else:
                    db.execute('UPDATE contacts SET ' + ','.join(f'{field}=?' for field in payload) + ' WHERE id=?',
                               [*payload.values(), contact_id])
            return contact_id
        except Exception:
            if new_image:
                remove_image(new_image)
            if new_back_image:
                remove_image(new_back_image)
            raise

    def contacts(self, search='', category_id=None):
        with self.connection() as db:
            rows = self._rows(db)
        for serial, row in enumerate(rows, 1):
            row['serial_number'] = serial
        query = search.strip().casefold()
        return [row for row in rows if (category_id is None or row['category_id'] == category_id)
                and (not query or any(query in str(row.get(field, '')).casefold() for field in (*FIELDS, 'category', 'remark', 'added_by')))]

    def get_contact(self, contact_id):
        with self.connection() as db:
            row = db.execute(SELECT + ' WHERE c.id=?', (contact_id,)).fetchone()
            return dict(row) if row else None

    def delete_contact(self, contact_id):
        references = []
        with self.mutation() as db:
            row = db.execute('SELECT business_card_image,business_card_back_image FROM contacts WHERE id=?', (contact_id,)).fetchone()
            if row:
                references = [row['business_card_image'], row['business_card_back_image']]
                db.execute('DELETE FROM contacts WHERE id=?', (contact_id,))
        for reference in references:
            try:
                remove_image(reference)
            except OSError:
                pass  # Contact deletion succeeded; orphan image can be cleaned separately.

    def categories(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('''SELECT cat.*, COUNT(c.id) AS contact_count
                FROM categories cat LEFT JOIN contacts c ON c.category_id=cat.id
                GROUP BY cat.id ORDER BY cat.name COLLATE NOCASE''')]

    def rename_category(self, category_id, name):
        name = clean_category(name)
        if not name or len(name) > 120:
            raise ValueError('Enter a category name of 1–120 characters.')
        try:
            with self.mutation() as db:
                if not db.execute('UPDATE categories SET name=?, normalized_name=? WHERE id=?',
                                  (name, name.casefold(), category_id)).rowcount:
                    raise ValueError('Category no longer exists.')
        except sqlite3.IntegrityError as exc:
            raise ValueError('A category with this name already exists.') from exc

    def delete_category(self, category_id):
        with self.mutation() as db:
            count = db.execute('SELECT COUNT(*) FROM contacts WHERE category_id=?', (category_id,)).fetchone()[0]
            if count:
                raise ValueError(f'This category is currently assigned to {count} contacts. Reassign them before deleting.')
            db.execute('DELETE FROM categories WHERE id=?', (category_id,))

    def export_excel(self):
        with self.connection() as db:
            # Same lock as mutations prevents an older download from overwriting a newer export.
            db.execute('BEGIN IMMEDIATE')
            try:
                data = build_workbook(self._rows(db))
                replace_workbook(data, self.excel_path)
                db.commit()
                return data
            except Exception:
                db.rollback()
                raise
