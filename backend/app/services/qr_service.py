from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


class QrDecodeError(Exception):
    """Raised when a QR code cannot be decoded from the provided image."""


def _decode_from_array(arr: np.ndarray) -> str | None:
    """Decode a QR code from an RGB/BGR numpy array using OpenCV.

    OpenCV's QRCodeDetector is self-contained (no external DLLs) and robust on
    plain QR images. Returns the payload string or None if no QR is found.
    """
    if arr is None or arr.size == 0:
        return None

    bgr = arr
    if arr.ndim == 3:
        # Convert RGB -> BGR for OpenCV, if the channel order is RGB.
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(bgr)
    if data:
        return data

    # Retry on the original ordering as a fallback.
    if arr.ndim == 3:
        data, _, _ = detector.detectAndDecode(arr)
        if data:
            return data

    return None


def decode_qr_image(image_bytes: bytes) -> str:
    """Decode a QR code from raw image bytes.

    Accepts common formats (PNG, JPEG, WEBP) that Pillow can open.
    """
    if not image_bytes:
        raise QrDecodeError("Empty image")

    try:
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise QrDecodeError("Unsupported or corrupt image") from exc

    arr = np.asarray(pil_image)

    # Try the full image first.
    payload = _decode_from_array(arr)
    if payload:
        return payload

    # Scale up small images for better detection.
    h, w = arr.shape[:2]
    max_dim = 1600
    if max(h, w) < max_dim:
        scale = max_dim / max(h, w)
        if scale > 1.0:
            bigger = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
            payload = _decode_from_array(bigger)
            if payload:
                return payload

    raise QrDecodeError("No QR code found in image")
