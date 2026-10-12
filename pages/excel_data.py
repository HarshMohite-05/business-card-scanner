from datetime import datetime
import streamlit as st
from utils.helpers import get_store, show_error


def render():
    store = get_store()
    st.title('Excel Data')
    st.caption('Your complete contact collection, ready to download.')
    with st.container(border=True):
        st.subheader('Business_Card_Contacts.xlsx')
        st.write(f'Total Contacts: {len(store.contacts())}')
        st.caption('Every contact change updates the workbook. Downloads are freshly generated from saved records.')
        try:
            data = store.export_excel()
            modified = datetime.fromtimestamp(store.excel_path.stat().st_mtime, store.timezone)
            st.write('Last Updated: ' + modified.strftime('%d %b %Y · %H:%M:%S %Z'))
            st.download_button('Download Excel', data=data, file_name='Business_Card_Contacts.xlsx',
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type='primary', width='stretch')
        except Exception as exc:
            show_error(exc)
    if st.button('Open Contacts', width='stretch'):
        st.switch_page('pages/contacts.py')
    st.caption('Original card images are stored separately. Include the image folder when backing up your collection.')

render()
