import re
from utils.constants import FIELDS, USERS

def clean_category(value):
    return ' '.join(str(value or '').split())

def validate_contact(values, category):
    if not any(str(values.get(k, '')).strip() for k in ('name', 'company_name', 'mobile_number', 'email')):
        raise ValueError('Please provide at least a name, company, mobile number or email.')
    if not clean_category(category):
        raise ValueError('Please select or enter a category.')
    for key in (*FIELDS, 'remark'):
        if len(str(values.get(key, ''))) > (10000 if key in ('remark', 'full_address') else 500):
            raise ValueError(f'{FIELDS.get(key, "Remark")} is too long.')
    if str(values.get('added_by', '') or '').strip() not in ('', *USERS):
        raise ValueError('Please choose who is adding this contact.')
    if len(clean_category(category)) > 120:
        raise ValueError('Category must be 120 characters or fewer.')
    for key in ('email', 'alternate_email'):
        value = str(values.get(key, '')).strip()
        if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError(f'Please correct {FIELDS[key]} or leave it blank.')
