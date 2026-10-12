import streamlit as st
from utils.helpers import get_store, show_error

st.set_page_config(page_title='Business Card Contact Manager', page_icon='📇', layout='wide')
st.markdown('''<style>
.block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem;}
h1 {letter-spacing: -0.035em; font-size: 2.2rem !important;}
h3 {letter-spacing: -0.02em;}
[data-testid="stSidebar"] {border-right: 1px solid #e3eaf2;}
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {border-radius: 14px;}
.stButton button, .stDownloadButton button {min-height: 44px; border-radius: 9px;}
[data-testid="stCaptionContainer"] {color: #61748b;}
@media (max-width: 700px) {
 .block-container {padding: 1rem 1rem 3rem;}
 h1 {font-size: 1.8rem !important;}
 [data-testid="stHorizontalBlock"] {flex-wrap: wrap; gap: .75rem;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width: min(100%, 290px); flex: 1 1 100%;}
}
</style>''', unsafe_allow_html=True)
with st.sidebar:
    st.markdown('## 📇 Card Contacts')
    st.caption('Business Card Contact Manager')
    st.divider()
try:
    get_store()
except Exception as exc:
    show_error(exc)
    st.stop()
page = st.navigation([
    st.Page('pages/scan_card.py', title='Scan Card', icon='📷', default=True),
    st.Page('pages/contacts.py', title='Contacts', icon='👥'),
    st.Page('pages/categories.py', title='Categories', icon='🏷️'),
    st.Page('pages/excel_data.py', title='Excel Data', icon='📊'),
])
with st.sidebar:
    st.divider()
    st.caption('Capture → Review → Save')
    st.caption('Your categories. Your contacts. Always in Excel.')
page.run()
