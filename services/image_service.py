from io import BytesIO
from pathlib import Path
import warnings
from uuid import uuid4
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from utils.constants import IMAGE_ROOT, MAX_IMAGE_BYTES

FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}

def validate_image(data, filename='', mime=''):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Choose an image smaller than 10 MB.')
    if filename and Path(filename).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValueError('Please choose a JPG, JPEG, PNG or WEBP image.')
    if mime and mime not in ('image/jpeg', 'image/png', 'image/webp', 'application/octet-stream'):
        raise ValueError('The uploaded file must be an image.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data))
            if image.format not in FORMATS:
                raise ValueError('Please choose a JPG, JPEG, PNG or WEBP image.')
            if image.width * image.height > 40_000_000:
                raise ValueError('Image resolution is too large. Use an image below 40 megapixels.')
            image.verify()
            image = Image.open(BytesIO(data))
            image.load()
            return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('This image is corrupt or unsupported. Please choose another image.') from exc

def preprocess(data):
    image = ImageOps.exif_transpose(validate_image(data)).convert('RGB')
    image.thumbnail((3200, 3200))
    if max(image.size) < 1400:
        ratio = min(2, 1400 / max(image.size))
        image = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(gray)
    return Image.fromarray(enhanced)

def store_original(data):
    image = validate_image(data)
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f'card_{uuid4().hex}{FORMATS[image.format]}'
    path = IMAGE_ROOT / filename
    try:
        with path.open('xb') as file:
            file.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return f'business_cards/{filename}'

def image_path(reference):
    if not reference:
        return None
    path = (IMAGE_ROOT / Path(reference).name).resolve()
    if path.parent != IMAGE_ROOT.resolve() or not path.is_file():
        return None
    return path

def remove_image(reference):
    path = image_path(reference)
    if path:
        path.unlink(missing_ok=True)

def processing_copy(data, bounds=(0, 0, 100, 100), rotation=0):
    """Crop/rotate an OCR copy while keeping uploaded bytes untouched."""
    image = ImageOps.exif_transpose(validate_image(data)).convert('RGB')
    left, top, right, bottom = bounds
    if not (0 <= left < right <= 100 and 0 <= top < bottom <= 100):
        raise ValueError('Crop must have a right edge after the left edge and a bottom edge after the top edge.')
    image = image.crop((int(image.width * left / 100), int(image.height * top / 100),
                        int(image.width * right / 100), int(image.height * bottom / 100)))
    if min(image.size) < 30:
        raise ValueError('The selected card area is too small. Enlarge the crop.')
    image = image.rotate(rotation, expand=True)
    image.thumbnail((3200, 3200))
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()

def rectify_card(data):
    """Find a dominant card quadrilateral and remove perspective on an OCR-only copy."""
    image = ImageOps.exif_transpose(validate_image(data)).convert('RGB')
    rgb = np.array(image)
    ratio = min(1, 1400 / max(image.size))
    small = cv2.resize(rgb, None, fx=ratio, fy=ratio)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 25, 90)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    masks = [edges, cv2.inRange(hsv, (0, 0, 145), (180, 70, 255)),
             cv2.inRange(hsv, (85, 70, 45), (140, 255, 255))]
    candidates = []
    area = small.shape[0] * small.shape[1]
    for mask in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            fraction = cv2.contourArea(contour) / area
            if not .18 < fraction < .97:
                continue
            quad = cv2.approxPolyDP(contour, .035 * cv2.arcLength(contour, True), True)
            if len(quad) != 4 or not cv2.isContourConvex(quad):
                continue
            points = quad.reshape(4, 2).astype(np.float32)
            ordered = np.array([points[np.argmin(points.sum(axis=1))], points[np.argmin(np.diff(points, axis=1))],
                                points[np.argmax(points.sum(axis=1))], points[np.argmax(np.diff(points, axis=1))]])
            if len(np.unique(ordered, axis=0)) != 4:
                continue
            width = max(np.linalg.norm(ordered[1]-ordered[0]), np.linalg.norm(ordered[2]-ordered[3]))
            height = max(np.linalg.norm(ordered[3]-ordered[0]), np.linalg.norm(ordered[2]-ordered[1]))
            if 1.25 < max(width, height) / min(width, height) < 2.8:
                candidates.append((fraction, ordered / ratio, int(width / ratio), int(height / ratio)))
    if not candidates:
        # Low-contrast dark cards can lack a continuous edge. Segment a centered foreground
        # at low resolution, then accept only a large convex four-corner card outline.
        factor = min(1, 500 / max(image.size))
        thumbnail = cv2.resize(rgb, None, fx=factor, fy=factor)
        h, w = thumbnail.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        try:
            cv2.grabCut(thumbnail, mask, (int(w*.04), int(h*.12), int(w*.82), int(h*.77)),
                        np.zeros((1,65),np.float64), np.zeros((1,65),np.float64), 5, cv2.GC_INIT_WITH_RECT)
            foreground = np.where((mask==1)|(mask==3),255,0).astype(np.uint8)
            contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                fraction = cv2.contourArea(contour)/(w*h)
                quad = cv2.approxPolyDP(contour, .035*cv2.arcLength(contour,True), True)
                if .2 < fraction < .9 and len(quad)==4 and cv2.isContourConvex(quad):
                    points=quad.reshape(4,2).astype(np.float32)/factor
                    ordered=np.array([points[np.argmin(points.sum(axis=1))],points[np.argmin(np.diff(points,axis=1))],
                                      points[np.argmax(points.sum(axis=1))],points[np.argmax(np.diff(points,axis=1))]])
                    width=max(np.linalg.norm(ordered[1]-ordered[0]),np.linalg.norm(ordered[2]-ordered[3]))
                    height=max(np.linalg.norm(ordered[3]-ordered[0]),np.linalg.norm(ordered[2]-ordered[1]))
                    if len(np.unique(ordered,axis=0))==4 and 1.25 < max(width,height)/min(width,height) < 2.8:
                        candidates.append((fraction,ordered,int(width),int(height)))
        except cv2.error:
            pass
    if not candidates:
        return image, False
    _, corners, width, height = max(candidates, key=lambda candidate: candidate[0])
    target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
    matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), target)
    warped = cv2.warpPerspective(rgb, matrix, (width, height), flags=cv2.INTER_CUBIC)
    return Image.fromarray(warped), True


def prepare_ocr_image(data):
    image, rectified = rectify_card(data)
    image.thumbnail((3200, 3200))
    if max(image.size) < 1800:
        scale = min(3, 1800 / max(image.size))
        image = image.resize((int(image.width*scale), int(image.height*scale)), Image.Resampling.LANCZOS)
    return ImageOps.grayscale(image), rectified

def deskew_text(image):
    """Choose a small tilt correction using text-line projection; no original pixels are saved."""
    gray = np.array(image.convert('L'))
    scale = min(1, 1000 / gray.shape[1])
    small = cv2.resize(gray, None, fx=scale, fy=scale)
    _, mask = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if np.mean(mask > 0) > .5:
        mask = 255-mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    clean = np.zeros_like(mask)
    for i in range(1, count):
        x,y,w,h,area = stats[i]
        if 4 <= h <= small.shape[0]*.15 and 2 <= w <= small.shape[1]*.5 and area >= 5:
            clean[labels == i] = 255
    center = (clean.shape[1]/2, clean.shape[0]/2)
    scores = []
    for angle in np.arange(-10, 10.5, .5):
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1)
        rotated = cv2.warpAffine(clean, matrix, (clean.shape[1], clean.shape[0]))
        projection = np.sum(rotated > 0, axis=1).astype(float)
        scores.append((float(np.sum(np.diff(projection)**2)), float(angle)))
    best_score, angle = max(scores)
    base = next(score for score, a in scores if a == 0)
    if abs(angle) < .5 or best_score < base*1.15:
        return image, 0
    background = int(np.median(gray))
    return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=background), angle
