import logging
import streamlit as st
from services.database_service import ContactStore
from services.image_service import image_path
from utils.constants import FIELDS, USERS

@st.cache_resource
def get_store(revision="two-sided-v1"):
    store = ContactStore()
    store.initialize()
    return store

def show_error(exc):
    if isinstance(exc, ValueError):
        st.error(str(exc))
    elif isinstance(exc, PermissionError):
        st.error('Could not update Excel. Close the workbook in Excel and check folder permissions, then try again.')
    else:
        logging.exception('Application operation failed')
        st.error('The operation could not finish. Your existing contacts are preserved. Check the application logs and try again.')

def reset_scan():
    for key in list(st.session_state):
        if key.startswith(('scan_', 'draft_')):
            del st.session_state[key]
    st.session_state['scan_generation'] = st.session_state.get('upload_generation', 0) + 1
    st.session_state['upload_generation'] = st.session_state['scan_generation']

def start_edit(contact_id):
    st.session_state['contact_action'] = 'edit'
    st.session_state['contact_id'] = contact_id
    for key in list(st.session_state):
        if key.startswith('edit_'):
            del st.session_state[key]

def card_image(reference):
    path = image_path(reference)
    if path:
        st.image(str(path), width='stretch')
    elif reference:
        st.warning('The original card image is unavailable. Restore the image folder from your backup.')
    else:
        st.info('This contact was entered manually without a card image.')

def contact_form(values, prefix, original=None, editing=False, back_original=None):
    """Form keeps corrections across reruns; category accepts existing or new values."""
    store = get_store()
    left, right = st.columns([1, 1.5], gap='large')
    with left:
        st.subheader('Original business card')
        if original:
            st.image(original, width='stretch')
        elif editing:
            card_image(values.get('business_card_image', ''))
        elif not back_original:
            st.info('Manual entry • no photo attached')
        if back_original:
            st.caption('Back of card')
            st.image(back_original, width='stretch')
        elif editing and values.get('business_card_back_image'):
            st.caption('Back of card')
            card_image(values['business_card_back_image'])
        st.caption('Compare the photo with the details, then correct anything OCR missed.')
        raw = values.get('ocr_raw_text', '')
        if raw:
            with st.expander('View OCR text'):
                st.text(raw)
    with right:
        with st.form(f'{prefix}form', border=True):
            st.subheader('Contact information')
            result = {}
            keys = list(FIELDS)
            for offset in range(0, 9, 2):
                columns = st.columns(2)
                for column, field in zip(columns, keys[offset:min(offset + 2, 9)]):
                    with column:
                        result[field] = st.text_input(FIELDS[field], value=values.get(field, ''), key=f'{prefix}{field}')
            st.subheader('Address details')
            result['full_address'] = st.text_area('Full Address', value=values.get('full_address', ''), key=f'{prefix}full_address', height=90)
            for pair in (('city', 'state'), ('pin_code', 'country')):
                columns = st.columns(2)
                for column, field in zip(columns, pair):
                    with column:
                        result[field] = st.text_input(FIELDS[field], value=values.get(field, ''), key=f'{prefix}{field}')
            st.divider()
            st.subheader('Added by, category & remark')
            # New scans default to the person who saved last in this browser session.
            current_user = values.get('added_by') if editing else values.get('added_by') or st.session_state.get('last_added_by')
            result['added_by'] = st.selectbox('Added By', USERS, index=USERS.index(current_user) if current_user in USERS else None,
                                              placeholder='Select who is adding this contact', key=f'{prefix}added_by')
            names = [c['name'] for c in store.categories()]
            current = values.get('category')
            index = names.index(current) if current in names else None
            selected = st.selectbox('Select Existing Category', names, index=index,
                                    placeholder='Search saved categories', key=f'{prefix}category', disabled=not names)
            new_category = st.text_input('Create New Category', placeholder='Type a new category', key=f'{prefix}new_category',
                                         help='Leave this blank to use the selected category. A new name is remembered when you save.')
            category = new_category.strip() or selected
            if not names:
                st.caption('No categories saved yet. Type your first category above.')
            result['remark'] = st.text_area('Remark', value=values.get('remark', ''), placeholder='Add notes about this contact…', key=f'{prefix}remark')
            st.caption('Added By, category and at least a name, company, mobile number or email are required.')
            submitted = st.form_submit_button('Save Changes' if editing else 'Save Contact', type='primary', width='stretch')
        if submitted:
            if not result['added_by']:
                st.error('Please select who is adding this contact in Added By.')
                return None
            try:
                result['ocr_raw_text'] = values.get('ocr_raw_text', '')
                contact_id = store.save_contact(result, category, image_data=original,
                                               back_image_data=back_original, contact_id=values.get('id') if editing else None,
                                               expected_updated_at=values.get('updated_at') if editing else None)
                st.session_state['last_added_by'] = result['added_by']
                return contact_id
            except Exception as exc:
                show_error(exc)
    return None
