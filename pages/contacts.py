import pandas as pd
import streamlit as st
from utils.constants import FIELDS
from utils.helpers import get_store, card_image, contact_form, start_edit, show_error

@st.dialog('Delete Contact?')
def delete_dialog(contact):
    st.write('Are you sure you want to delete this contact?')
    st.write(contact['name'] or contact['company_name'] or contact['email'])
    st.caption('The contact and its Excel row will be removed.')
    a, b = st.columns(2)
    if a.button('Cancel', width='stretch'):
        st.session_state.pop('pending_delete', None)
        st.rerun()
    if b.button('Delete', type='primary', width='stretch'):
        try:
            get_store().delete_contact(contact['id'])
            st.session_state.pop('contact_action', None)
            st.session_state.pop('pending_delete', None)
            st.session_state['contacts_notice'] = 'Contact deleted. Excel is synchronized.'
            st.rerun()
        except Exception as exc:
            show_error(exc)


def open_contact(contact_id, action):
    st.session_state['contact_id'] = contact_id
    st.session_state['contact_action'] = action
    if action == 'edit':
        start_edit(contact_id)
    st.rerun()


def render():
    store = get_store()
    st.title('Contacts')
    pending = st.session_state.get('pending_delete')
    if pending:
        candidate = store.get_contact(pending)
        if candidate:
            delete_dialog(candidate)
        else:
            st.session_state.pop('pending_delete', None)
    if st.session_state.get('contacts_notice'):
        st.success(st.session_state.pop('contacts_notice'))
    action = st.session_state.get('contact_action')
    if action in ('view', 'edit'):
        contact = store.get_contact(st.session_state['contact_id'])
        if st.button('← Back to Contacts'):
            st.session_state.pop('contact_action', None)
            st.rerun()
        if not contact:
            st.warning('This contact is no longer available.')
            return
        if action == 'edit':
            st.subheader('Edit Contact')
            # Snapshot preserves concurrency token and original values while the form is open.
            if 'edit_snapshot' not in st.session_state:
                st.session_state['edit_snapshot'] = contact
            if contact_form(st.session_state['edit_snapshot'], 'edit_', editing=True):
                st.session_state.pop('contact_action', None)
                st.session_state['contacts_notice'] = 'Contact updated. Excel is synchronized.'
                st.rerun()
        else:
            a, b = st.columns([1, 1.5], gap='large')
            with a:
                card_image(contact['business_card_image'])
                if contact.get('business_card_back_image'):
                    st.caption('Back of card')
                    card_image(contact['business_card_back_image'])
            with b:
                st.subheader(contact['name'] or contact['company_name'] or 'Contact details')
                for key, label in {**FIELDS, 'category': 'Category', 'remark': 'Remark', 'added_by': 'Added By', 'date_added': 'Date Added', 'time_added': 'Time Added'}.items():
                    st.caption(label)
                    st.text(contact.get(key) or '—')
                edit, delete = st.columns(2)
                if edit.button('Edit', type='primary', width='stretch'):
                    open_contact(contact['id'], 'edit')
                if delete.button('Delete', width='stretch'):
                    st.session_state['pending_delete'] = contact['id']
                    st.rerun()
        return
    st.caption('Search your collection, review a card, or update a contact.')
    categories = store.categories()
    a, b = st.columns([2, 1])
    search = a.text_input('Search contacts', placeholder='Name, company, phone, city, remark or added by…', key='contacts_search')
    category_id = b.selectbox('Category Filter', [None] + [c['id'] for c in categories],
                              format_func=lambda cid: 'All Categories' if cid is None else next(c['name'] for c in categories if c['id'] == cid), key='contacts_filter')
    def clear_filter():
        st.session_state['contacts_search'] = ''
        st.session_state['contacts_filter'] = None
    st.button('Clear Filter', on_click=clear_filter)
    contacts = store.contacts(search, category_id)
    if not contacts:
        with st.container(border=True):
            if search or category_id:
                st.subheader('No matching contacts')
                st.write('Try another search or clear the category filter.')
            else:
                st.subheader('No Contacts Yet')
                st.write('Scan your first business card to begin.')
                if st.button('Scan Business Card', type='primary'):
                    st.switch_page('pages/scan_card.py')
        return
    st.caption(f'{len(contacts)} contact{"s" if len(contacts) != 1 else ""}')
    display = st.segmented_control('Display', ['Cards', 'Table'], default='Cards')
    if display == 'Table':
        columns = {'serial_number': 'Sr No', 'name': 'Name', 'designation': 'Designation', 'company_name': 'Company',
                   'mobile_number': 'Mobile', 'email': 'Email', 'category': 'Category', 'remark': 'Remark', 'added_by': 'Added By', 'date_added': 'Date Added'}
        st.dataframe(pd.DataFrame(contacts)[list(columns)].rename(columns=columns), hide_index=True, width='stretch')
        selected = st.selectbox('Select contact for actions', [c['id'] for c in contacts],
                                format_func=lambda cid: next(f"{c['serial_number']} · {c['name'] or c['company_name'] or c['email']}" for c in contacts if c['id'] == cid))
        chosen = next(c for c in contacts if c['id'] == selected)
        action_buttons(chosen)
    else:
        # Cards stay readable on narrow screens; bounded pages keep reruns fast.
        per_page = 12
        total_pages = (len(contacts) + per_page - 1) // per_page
        page = st.number_input('Page', min_value=1, max_value=max(1, total_pages), value=1, step=1)
        for contact in contacts[(page - 1) * per_page:page * per_page]:
            with st.container(border=True):
                st.subheader(contact['name'] or contact['company_name'] or contact['email'])
                if contact['company_name']:
                    st.text(contact['company_name'])
                st.text(' · '.join(v for v in (contact['mobile_number'], contact['email']) if v) or 'No phone or email')
                st.text('Category: ' + contact['category'])
                if contact['remark']:
                    st.text(contact['remark'])
                st.caption(f"#{contact['serial_number']} · Added {contact['date_added']}" + (f" by {contact['added_by']}" if contact['added_by'] else ''))
                action_buttons(contact)


def action_buttons(contact):
    a, b, c = st.columns(3)
    if a.button('View / Card', key=f"view_{contact['id']}", width='stretch'):
        open_contact(contact['id'], 'view')
    if b.button('Edit', key=f"change_{contact['id']}", width='stretch'):
        open_contact(contact['id'], 'edit')
    if c.button('Delete', key=f"delete_{contact['id']}", width='stretch'):
        st.session_state['pending_delete'] = contact['id']
        st.rerun()

render()
