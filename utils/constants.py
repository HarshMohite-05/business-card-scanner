from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv('BCCM_DATA_DIR', str(ROOT / 'data'))).expanduser().resolve()
IMAGE_ROOT = Path(os.getenv('BCCM_IMAGE_DIR', str(ROOT / 'storage' / 'business_cards'))).expanduser().resolve()
DB_PATH = DATA_ROOT / 'contacts.db'
EXCEL_PATH = DATA_ROOT / 'exports' / 'Business_Card_Contacts.xlsx'
TIMEZONE = os.getenv('BCCM_TIMEZONE', 'Asia/Kolkata')
MAX_IMAGE_BYTES = 10 * 1024 * 1024
FIELDS = {
    'name': 'Name', 'designation': 'Designation', 'company_name': 'Company Name',
    'mobile_number': 'Mobile Number', 'alternate_mobile': 'Alternate Mobile Number',
    'telephone_number': 'Telephone Number', 'email': 'Email',
    'alternate_email': 'Alternate Email', 'website': 'Website',
    'full_address': 'Full Address', 'city': 'City', 'state': 'State',
    'pin_code': 'PIN Code', 'country': 'Country',
}
USERS = ('Akash', 'Deepak', 'Neer')
EXCEL_COLUMNS = [('serial_number', 'Sr No'), ('date_added', 'Date Added'),
 ('time_added', 'Time Added'), ('added_by', 'Added By'), *[(k, v if k != 'alternate_mobile' else 'Alternate Mobile') for k, v in FIELDS.items()],
 ('category', 'Category'), ('remark', 'Remark'), ('business_card_image', 'Business Card Image Reference')]
