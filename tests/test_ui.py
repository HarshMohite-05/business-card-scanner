import os
from pathlib import Path
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ['BCCM_DATA_DIR'] = TEMP.name + '/data'
os.environ['BCCM_IMAGE_DIR'] = TEMP.name + '/images'
from streamlit.testing.v1 import AppTest
from utils.helpers import get_store

class UITests(unittest.TestCase):
    def setUp(self):
        store = get_store()
        for contact in store.contacts():
            store.delete_contact(contact['id'])
        for category in store.categories():
            store.delete_category(category['id'])

    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20).run()

    def button(self, app, label):
        return next(button for button in app.button if button.label == label)

    def test_manual_save_and_next(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.button(app, 'Enter Manually').click().run()
        self.assertFalse(app.exception)
        app.text_input(key='draft_name').set_value('UI Test Contact')
        app.text_input(key='draft_email').set_value('ui@example.com')
        app.text_input(key='draft_new_category').set_value('Industrial Client')
        app.selectbox(key='draft_added_by').set_value('Akash')
        app.text_area(key='draft_remark').set_value('Manual correction test')
        self.button(app, 'Save Contact').click().run()
        self.assertFalse(app.exception)
        self.assertIn('Contact Saved Successfully', [s.value for s in app.success])
        self.assertEqual(get_store().contacts()[0]['remark'], 'Manual correction test')
        self.assertEqual(get_store().contacts()[0]['added_by'], 'Akash')
        self.button(app, 'Scan Next Card').click().run()
        self.button(app, 'Enter Manually').click().run()
        self.assertIn('Industrial Client', app.selectbox(key='draft_category').options)
        self.assertEqual(app.text_input(key='draft_name').value, '')
        self.assertEqual(app.selectbox(key='draft_added_by').value, 'Akash')
        self.assertFalse(app.exception)

    def test_contact_pages(self):
        cid = get_store().save_contact({'name': 'Test Contact', 'city': 'Mumbai'}, 'Consultant')
        app = self.app()
        app.switch_page('pages/contacts.py').run()
        self.assertFalse(app.exception)
        app.text_input(key='contacts_search').set_value('Mumbai').run()
        self.button(app, 'Clear Filter').click().run()
        self.assertEqual(app.text_input(key='contacts_search').value, '')
        self.button(app, 'Edit').click().run()
        self.assertFalse(app.exception)
        app.text_input(key='edit_name').set_value('Edited Contact')
        app.selectbox(key='edit_added_by').set_value('Neer')
        self.button(app, 'Save Changes').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_store().get_contact(cid)['name'], 'Edited Contact')
        self.button(app, 'View / Card').click().run()
        self.assertFalse(app.exception)
        self.button(app, 'Delete').click().run()
        self.assertFalse(app.exception)
        # Both view and confirmation contain Delete; the final button belongs to the dialog.
        [button for button in app.button if button.label == 'Delete'][-1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_store().contacts(), [])
        app.switch_page('pages/categories.py').run()
        self.assertFalse(app.exception)
        app.switch_page('pages/excel_data.py').run()
        self.assertFalse(app.exception)

    def test_capture_and_upload_processing(self):
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (1400, 500), 'white')
        font_path = '/System/Library/Fonts/Supplemental/Arial.ttf'
        font = ImageFont.truetype(font_path if Path(font_path).exists() else 'DejaVuSans.ttf', 44)
        ImageDraw.Draw(image).text((60, 100), 'scan@example.com', fill='black', font=font)
        output = BytesIO()
        image.save(output, format='PNG')
        uploaded = SimpleNamespace(name='card.png', type='image/png', getvalue=lambda: output.getvalue())
        for capture in ('camera', 'gallery'):
            app = self.app()
            if capture == 'gallery':
                app.radio[0].set_value('Choose From Gallery').run()
            target = 'streamlit.camera_input' if capture == 'camera' else 'streamlit.file_uploader'
            with patch(target, return_value=uploaded):
                app.run()
                self.button(app, 'Process Card').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.text_input(key='draft_email').value, 'scan@example.com')
            self.assertEqual(app.session_state['scan_image'], output.getvalue())
            self.assertEqual(get_store().contacts(), [])

    def test_empty_ocr_manual_fallback(self):
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from PIL import Image
        output = BytesIO()
        Image.new('RGB', (800, 400), 'white').save(output, format='PNG')
        uploaded = SimpleNamespace(name='blank.png', type='image/png', getvalue=lambda: output.getvalue())
        app = self.app()
        with patch('streamlit.camera_input', return_value=uploaded):
            app.run()
            self.button(app, 'Process Card').click().run()
            self.assertTrue(app.warning)
            self.button(app, 'Enter Details Manually').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='draft_name').value, '')
        self.assertEqual(app.session_state['scan_image'], output.getvalue())

    def test_two_sided_capture_review_and_save(self):
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from PIL import Image
        images = []
        for color in ('white', 'blue'):
            buffer = BytesIO()
            Image.new('RGB', (800, 400), color).save(buffer, format='PNG')
            data = buffer.getvalue()
            images.append(SimpleNamespace(name='card.png', type='image/png', getvalue=lambda data=data: data))
        app = self.app()
        app.checkbox(key='scan_include_back').check().run()
        with patch('streamlit.camera_input', side_effect=lambda label, **kwargs: images[1] if 'Back' in label else images[0]), patch('services.ocr_service.read_card', side_effect=[
            {'raw_text': 'Alice Example\nDirector\n+91 9876543210'},
            {'raw_text': 'Example Industries\nsales@example.com\n1 Main Road, Mumbai, Maharashtra 400001'}]):
            app.run()
            self.button(app, 'Process Card').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='draft_name').value, 'Alice Example')
        self.assertEqual(app.text_input(key='draft_company_name').value, 'Example Industries')
        self.assertEqual(app.text_input(key='draft_email').value, 'sales@example.com')
        app.text_input(key='draft_new_category').set_value('Two-sided Client')
        app.selectbox(key='draft_added_by').set_value('Deepak')
        with tempfile.TemporaryDirectory() as image_dir, patch('services.image_service.IMAGE_ROOT', Path(image_dir).resolve()):
            self.button(app, 'Save Contact').click().run()
            self.assertFalse(app.exception)
            contact = get_store().contacts()[0]
            self.assertTrue(contact['business_card_image'])
            self.assertTrue(contact['business_card_back_image'])
            self.assertIn('--- Front ---', contact['ocr_raw_text'])
            self.assertIn('--- Back ---', contact['ocr_raw_text'])
            get_store().delete_contact(contact['id'])

    def test_partial_side_failure_keeps_success(self):
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from PIL import Image
        from services.ocr_service import OCRError
        output = BytesIO()
        Image.new('RGB', (800, 400), 'white').save(output, format='PNG')
        upload = SimpleNamespace(name='card.png', type='image/png', getvalue=lambda: output.getvalue())
        app = self.app()
        app.checkbox(key='scan_include_back').check().run()
        with patch('streamlit.camera_input', return_value=upload), patch('services.ocr_service.read_card', side_effect=[
            {'raw_text': 'Alice Example\nalice@example.com'}, OCRError('Unreadable back')]):
            app.run()
            self.button(app, 'Process Card').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='draft_email').value, 'alice@example.com')
        self.assertTrue(app.warning)
        self.assertTrue(app.session_state['scan_back_image'])

    def test_ocr_review_state(self):
        from services.contact_parser import parse_contact
        app = self.app()
        values = parse_contact('OCR Person\nDirector\nExample Industries\nocr@example.com')
        values['ocr_raw_text'] = 'OCR Person\nocr@example.com'
        app.session_state['scan_values'] = values
        app.session_state['scan_stage'] = 'review'
        app.session_state['scan_image'] = None
        app.run()
        self.assertEqual(app.text_input(key='draft_email').value, 'ocr@example.com')
        app.text_input(key='draft_name').set_value('Corrected Person')
        app.text_input(key='draft_new_category').set_value('Review Category')
        app.selectbox(key='draft_added_by').set_value('Akash')
        self.button(app, 'Save Contact').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_store().contacts()[0]['name'], 'Corrected Person')
        self.assertIn('ocr@example.com', get_store().contacts()[0]['ocr_raw_text'])

    def test_validation(self):
        app = self.app()
        self.button(app, 'Enter Manually').click().run()
        self.button(app, 'Save Contact').click().run()
        self.assertTrue(app.error)
        self.assertFalse(app.exception)
        self.assertEqual(get_store().contacts(), [])
        app.text_input(key='draft_name').set_value('No User')
        app.text_input(key='draft_new_category').set_value('Client')
        self.button(app, 'Save Contact').click().run()
        self.assertIn('Added By', ' '.join(e.value for e in app.error))
        self.assertEqual(get_store().contacts(), [])

if __name__ == '__main__':
    unittest.main()
