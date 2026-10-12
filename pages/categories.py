import streamlit as st
from utils.helpers import get_store, show_error


def render():
    store = get_store()
    st.title('Categories')
    st.caption('Your categories are created when you save a contact. Rename them here when needed.')
    categories = store.categories()
    if not categories:
        with st.container(border=True):
            st.subheader('No Categories Yet')
            st.write('Categories will appear here automatically when you add them while saving contacts.')
        return
    for category in categories:
        with st.container(border=True):
            st.subheader(category['name'])
            st.caption(f"{category['contact_count']} contacts · Created {category['created_at'][:10]}")
            with st.form(f"rename_category_{category['id']}"):
                name = st.text_input('Category name', value=category['name'])
                if st.form_submit_button('Rename'):
                    try:
                        store.rename_category(category['id'], name)
                        st.rerun()
                    except Exception as exc:
                        show_error(exc)
            if category['contact_count']:
                st.caption(f"This category is currently assigned to {category['contact_count']} contacts. Reassign those contacts before deleting.")
            else:
                confirm = st.checkbox('Confirm deletion of this unused category', key=f"confirm_cat_{category['id']}")
                if st.button('Delete unused category', disabled=not confirm, key=f"delete_cat_{category['id']}"):
                    try:
                        store.delete_category(category['id'])
                        st.rerun()
                    except Exception as exc:
                        show_error(exc)

render()
