import os
import shutil
import shlex
from pathlib import Path
from collections import OrderedDict
import pytesseract
import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import cv2
import numpy as np
from services.image_service import preprocess, prepare_ocr_image, deskew_text

class OCRError(RuntimeError):
    pass

class TesseractEngine:
    def __init__(self):
        executable = os.getenv('TESSERACT_CMD') or shutil.which('tesseract')
        if not executable:
            for path in ('/opt/homebrew/bin/tesseract', '/usr/local/bin/tesseract'):
                if os.path.isfile(path):
                    executable = path
                    break
        if not executable:
            raise OCRError('Tesseract is not installed. See the OCR setup instructions, or enter details manually.')
        pytesseract.pytesseract.tesseract_cmd = executable
        local_models = Path(__file__).resolve().parents[1] / '.models' / 'tessdata'
        self.language = os.getenv('BCCM_OCR_LANGUAGE', 'eng')
        directory = os.getenv('BCCM_TESSDATA_DIR', '')
        # Prefer bundled models when they cover every requested language.
        if not directory and all((local_models / f'{lang}.traineddata').is_file() for lang in self.language.split('+')):
            directory = str(local_models)
        self.model_config = f' --tessdata-dir {shlex.quote(directory)}' if directory else ''

    def _read(self, image, mode):
        try:
            result = pytesseract.image_to_data(image, lang=self.language, config=f'--psm {mode} --oem 1' + self.model_config,
                                             output_type=pytesseract.Output.DICT, timeout=15)
        except (RuntimeError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError) as exc:
            raise OCRError('OCR could not finish. Check Tesseract language files or try a clearer photo.') from exc
        groups = OrderedDict()
        positions = {}
        confidences = []
        for i, text in enumerate(result['text']):
            text = text.strip()
            if not text:
                continue
            key = (result['block_num'][i], result['par_num'][i], result['line_num'][i])
            groups.setdefault(key, []).append(text)
            x,y,w,h = (int(result[field][i]) for field in ('left','top','width','height'))
            if key not in positions:
                positions[key] = [x,y,x+w,y+h]
            else:
                box=positions[key]
                positions[key]=[min(box[0],x),min(box[1],y),max(box[2],x+w),max(box[3],y+h)]
            confidence = float(result['conf'][i])
            if confidence >= 0:
                confidences.append(confidence)
        lines = [' '.join(words) for words in groups.values()]
        return {'raw_text': '\n'.join(lines), 'lines': lines,
                'confidence': sum(confidences) / len(confidences) if confidences else 0,
                'layout': [{'text':' '.join(groups[key]), 'box':box} for key,box in positions.items()]}

    def orient(self, image):
        import re
        candidates = []
        for angle in (0, 90, 180, 270):
            rotated = image.rotate(angle, expand=True)
            probe = rotated.copy()
            probe.thumbnail((1400, 1400))
            output = self._read(probe, 11)
            words = re.findall(r'[A-Za-z]{3,}', output['raw_text'])
            score = output['confidence'] + min(len(words), 35) * 2
            if '@' in output['raw_text']:
                score += 15
            candidates.append((score, angle, rotated))
        _, angle, oriented = max(candidates, key=lambda candidate: candidate[0])
        return oriented, angle

    def read(self, image):
        from services.contact_parser import parse_contact, merge_contacts
        candidates, failures = [], []
        enhanced = ImageOps.autocontrast(ImageOps.grayscale(image)).filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=3))
        contrast = ImageOps.grayscale(image)
        contrast = Image.fromarray(cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(np.array(contrast)))
        for variant, mode in ((image, 6), (image, 11), (image, 3), (ImageOps.invert(image.convert('L')), 6), (enhanced, 11), (contrast, 11)):
            try:
                candidates.append(self._read(variant, mode))
            except OCRError as exc:
                failures.append(exc)
        if not candidates:
            raise failures[0]
        # Re-read identifier lines locally; logos, QR codes and neighboring columns can
        # interfere with full-card segmentation even when the characters are visible.
        import re
        boxes=[]
        for candidate in candidates:
            for line in candidate.get('layout', []):
                if '@' in line['text'] or re.search(r'(?:\d[\s.-]*){8,}', line['text']):
                    box=line['box']
                    if not any(abs(box[1]-existing[1]) < max(10,(box[3]-box[1])/2) for existing in boxes):
                        boxes.append(box)
        for x1,y1,x2,y2 in boxes[:8]:
            pad=max(12,int((y2-y1)*.8))
            crop=image.crop((max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad*3),min(image.height,y2+pad)))
            crop=ImageOps.autocontrast(crop).resize((crop.width*2,crop.height*2),Image.Resampling.LANCZOS)
            try:
                candidate=self._read(crop,7)
                candidate['local_identifiers']=True
                candidates.append(candidate)
            except OCRError:
                pass

        def score(output):
            fields = parse_contact(output['raw_text'])
            useful = sum(bool(fields[k]) for k in ('email', 'mobile_number', 'telephone_number', 'website', 'name', 'company_name'))
            return useful * 30 + output['confidence'] + min(len(output['raw_text']), 500) / 20
        candidates.sort(key=score, reverse=True)
        best = candidates[0]
        # Keep complementary fields from successful passes rather than discarding all but one.
        credible = [candidate for candidate in candidates if candidate is best or candidate['confidence'] >= 30]
        parsed=[]
        for candidate in credible:
            values=parse_contact(candidate['raw_text'])
            # Identifier crops lack context, and low-confidence passes are mostly logos or
            # background texture; keep only pattern-checked fields from them.
            if candidate.get('local_identifiers') or candidate['confidence'] < 50:
                for key in ('name','company_name','designation','full_address','city','state','pin_code','country'):
                    values[key]=''
            parsed.append(values)
        fields, alternatives = merge_contacts(parsed, weights=[max(c['confidence'], 1) for c in credible])
        return {**best, 'fields': fields, 'alternatives': alternatives,
                'passes': [{'raw_text': candidate['raw_text'], 'confidence': candidate['confidence']} for candidate in candidates]}

@st.cache_resource(show_spinner=False)
def load_ocr_model(revision="card-geometry-local-v10"):
    # Tesseract loads trained language data in its subprocess; cache executable configuration.
    return TesseractEngine()

def read_card(data):
    engine = load_ocr_model('card-geometry-local-v10')
    image, rectified = prepare_ocr_image(data)
    oriented, angle = engine.orient(image)
    deskewed, skew = deskew_text(oriented)
    result = engine.read(deskewed if abs(skew) >= 1.5 else oriented)
    return {**result, 'rotation': angle, 'perspective_corrected': rectified, 'deskew_angle': skew}

def combine_sides(outputs):
    """Merge front/back readings into one contact draft plus review suggestions."""
    from services.contact_parser import parse_contact, merge_contacts, company_from_domain
    sides = [output.get('fields') or parse_contact(output['raw_text']) for output in outputs]
    # A logo-only side must not outvote the side carrying the contact details.
    weights = [max(output.get('confidence', 0), 1) + 20 * sum(bool(fields[k]) for k in ('email', 'mobile_number', 'website'))
               for fields, output in zip(sides, outputs)]
    values, alternatives = merge_contacts(sides, combine_addresses=True, weights=weights)
    for output in outputs:
        for field, suggestions in output.get('alternatives', {}).items():
            alternatives[field] = list(dict.fromkeys(alternatives.get(field, []) + suggestions))
    company_from_domain(values, alternatives)
    return values, alternatives
