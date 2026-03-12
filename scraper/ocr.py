"""
OCR module using macOS built-in Vision framework.
No model download required. Excellent Traditional Chinese support.
"""
from pathlib import Path

import objc
import Vision
from Foundation import NSURL


def extract_text(image_path: Path) -> str:
    """Returns extracted text from a single image file using Apple Vision OCR."""
    if not image_path.exists() or image_path.suffix == '.mp4':
        return ""
    try:
        img_url = NSURL.fileURLWithPath_(str(image_path.resolve()))

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLanguages_(["zh-Hant", "zh-Hans", "en-US"])
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(img_url, {})
        success, error = handler.performRequests_error_([request], None)

        if not success or error:
            return ""

        texts = []
        for obs in request.results():
            candidates = obs.topCandidates_(1)
            if candidates:
                texts.append(candidates[0].string())

        return " ".join(texts).strip()

    except Exception:
        return ""


def extract_text_for_post(short_code: str, date_str: str, post_type: str, images_dir: Path) -> str:
    """Returns OCR text for all images in a post, joined by ' | ' for carousels."""
    if post_type == "Video":
        return ""

    if post_type == "Carousel":
        texts = []
        for j in range(1, 20):
            img_path = images_dir / f"{date_str}_{short_code}_slide{j}.jpg"
            if not img_path.exists():
                break
            text = extract_text(img_path)
            if text:
                texts.append(text)
        return " | ".join(texts)

    # Image
    img_path = images_dir / f"{date_str}_{short_code}.jpg"
    return extract_text(img_path)
