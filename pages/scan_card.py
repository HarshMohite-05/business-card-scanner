import hashlib
import streamlit as st
from services.image_service import validate_image, processing_copy
from services.ocr_service import read_card, combine_sides, OCRError
from utils.constants import FIELDS
from utils.helpers import contact_form, reset_scan, show_error


def capture_side(side, method, generation):
    label = 'Front' if side == 'front' else 'Back'
    st.subheader(f'{label} of card' + (' (optional)' if side == 'back' else ''))
    if method == 'Take Photo':
        uploaded = st.camera_input('Take Business Card Photo' if side == 'front' else 'Take Back Photo', key=f'scan_camera_{side}_{generation}')
    else:
        uploaded = st.file_uploader('Upload from Gallery' if side == 'front' else 'Upload Back from Gallery',
                                    type=['jpg', 'jpeg', 'png', 'webp'], key=f'scan_upload_{side}_{generation}',
                                    help='JPG, PNG or WEBP • up to 10 MB per side')
    legacy = st.session_state.get('scan_reprocess_image') or st.session_state.get('scan_image') if side == 'front' else None
    data = st.session_state.get(f'scan_original_{side}', legacy)
    if uploaded is not None:
        try:
            validate_image(uploaded.getvalue(), uploaded.name, uploaded.type)
            data = uploaded.getvalue()
        except ValueError as exc:
            st.error(str(exc))
            return None, None, False
    if not data:
        return None, None, True
    st.session_state[f'scan_original_{side}'] = data
    digest = hashlib.sha256(data).hexdigest()
    config_key = f'scan_crop_{side}_{digest}'
    # Migrate the previously captured single-sided draft without losing its crop.
    defaults = st.session_state.get(config_key, {})
    if side == 'front' and not defaults and st.session_state.get('scan_crop_digest') == digest:
        defaults = st.session_state.get('scan_crop_config', {})
    with st.expander(f'Crop or rotate {label.lower()} for better OCR'):
        st.caption('Select only the card. Original photos are preserved unchanged.')
        horizontal = st.slider(f'{label} left / right edges (%)', 0, 100, defaults.get('horizontal', (0, 100)), key=f'crop_x_{side}_{digest}')
        vertical = st.slider(f'{label} top / bottom edges (%)', 0, 100, defaults.get('vertical', (0, 100)), key=f'crop_y_{side}_{digest}')
        rotation = st.selectbox(f'Rotate {label.lower()} counterclockwise', [0, 90, 180, 270],
                                index=[0, 90, 180, 270].index(defaults.get('rotation', 0)),
                                format_func=lambda value: f'{value}°', key=f'rotate_{side}_{digest}')
    st.session_state[config_key] = {'horizontal': horizontal, 'vertical': vertical, 'rotation': rotation}
    try:
        processed = processing_copy(data, (horizontal[0], vertical[0], horizontal[1], vertical[1]), rotation)
        st.image(processed, width=600, caption=f'{label} • OCR preview')
        return data, processed, True
    except ValueError as exc:
        st.error(str(exc))
        return data, None, False


def enter_review(front, back, values=None):
    for key in list(st.session_state):
        if key.startswith('draft_'):
            del st.session_state[key]
    st.session_state['scan_values'] = values if values is not None else dict.fromkeys(FIELDS, '')
    st.session_state['scan_image'] = front
    st.session_state['scan_back_image'] = back
    st.session_state['scan_stage'] = 'review'
    st.rerun()


def render():
    st.title('Scan Business Card')
    st.caption('Scan the front and, if needed, the back. Review one combined contact before saving.')
    if st.session_state.get('scan_saved'):
        st.success('Contact Saved Successfully')
        a, b = st.columns(2)
        if a.button('Scan Next Card', type='primary', width='stretch'):
            reset_scan()
            st.rerun()
        if b.button('View Contacts', width='stretch'):
            st.switch_page('pages/contacts.py')
        return
    if st.session_state.get('scan_stage') == 'review':
        st.subheader('Review Contact Details')
        if st.button('Cancel / Scan Another Card'):
            reset_scan()
            st.rerun()
        if (st.session_state.get('scan_image') or st.session_state.get('scan_back_image')) and st.button('Adjust Photo / Add Back / Reprocess Card'):
            st.session_state['scan_stage'] = 'capture'
            st.session_state['scan_reprocess_image'] = st.session_state.get('scan_image')
            st.rerun()
        for warning in st.session_state.get('scan_warnings', []):
            st.warning(warning)
        alternatives = st.session_state.get('scan_alternatives', {})
        if alternatives:
            with st.expander('Other detected values • check before saving'):
                st.caption('Sides or OCR passes may disagree. Correct the form using the original images.')
                for field, values in alternatives.items():
                    st.text(f"{FIELDS[field]}: " + ' | '.join(values))
        contact_id = contact_form(st.session_state['scan_values'], 'draft_', st.session_state.get('scan_image'),
                                  back_original=st.session_state.get('scan_back_image'))
        if contact_id:
            reset_scan()
            st.session_state['scan_saved'] = contact_id
            st.rerun()
        return

    generation = st.session_state.get('scan_generation', 0)
    method = st.radio('Choose input', ['Take Photo', 'Choose From Gallery'], horizontal=True, label_visibility='collapsed')
    st.caption('Camera unavailable? Choose From Gallery. For best results fill the frame with the card.')
    include_back = st.checkbox('Add back of card', value=bool(st.session_state.get('scan_back_image') or st.session_state.get('scan_original_back')), key='scan_include_back')
    front, front_copy, front_valid = capture_side('front', method, generation)
    back, back_copy, back_valid = capture_side('back', method, generation) if include_back else (None, None, True)
    if st.button('Enter Manually', width='stretch'):
        enter_review(front, back)
    if not front and not back:
        st.info('Capture or upload a card. Add the back if it contains additional details.')
        return
    a, b = st.columns(2)
    process = a.button('Process Card', type='primary', width='stretch', disabled=not (front_valid and back_valid))
    if b.button('Clear / Choose Another', width='stretch'):
        reset_scan()
        st.rerun()
    if process:
        outputs, warnings = [], []
        try:
            with st.status('Reading business card…', expanded=True) as status:
                for side, data in (('Front', front_copy), ('Back', back_copy)):
                    if data:
                        st.write(f'Reading {side.lower()}…')
                        try:
                            output = read_card(data)
                            if output['raw_text'].strip():
                                outputs.append((side, output))
                            else:
                                warnings.append(f'{side}: no readable text detected. Retake this side or enter its details manually.')
                        except OCRError as exc:
                            warnings.append(f'{side}: {exc}')
                if not outputs:
                    raise OCRError("We couldn't clearly read this business card. Try again or enter details manually.")
                st.write('Combining details from both sides and OCR passes…')
                values, alternatives = combine_sides([output for _, output in outputs])
                values['ocr_raw_text'] = '\n\n'.join(f'--- {side} ---\n{output["raw_text"]}' for side, output in outputs)
                st.session_state['scan_alternatives'] = alternatives
                st.session_state['scan_warnings'] = warnings
                status.update(label='Card read. Ready for review.', state='complete')
            enter_review(front, back, values)
        except (OCRError, ValueError) as exc:
            st.session_state['scan_ocr_error'] = str(exc)
        except Exception as exc:
            show_error(exc)
            st.session_state['scan_ocr_error'] = 'OCR could not finish. Try again or enter details manually.'
    if st.session_state.get('scan_ocr_error'):
        st.warning(st.session_state['scan_ocr_error'])
        if st.button('Enter Details Manually', type='primary'):
            enter_review(front, back)

render()
