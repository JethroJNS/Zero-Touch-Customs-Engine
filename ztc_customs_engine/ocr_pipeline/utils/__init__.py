"""Utility helpers for the OCR pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple
import numpy as np
import cv2

logger = logging.getLogger(__name__)


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger with consistent formatting."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(level)
    return log


def open_image(path: Path) -> np.ndarray:
    """Load an image from disk using cv2."""
    img = cv2.imread(str(path))
    if img is None:
        raise IOError(f"Failed to load image: {path}")
    return img


def save_image(img: np.ndarray, path: Path) -> Path:
    """Save an image to disk."""
    cv2.imwrite(str(path), img)
    logger.debug("Saved image to %s", path)
    return path


def calculate_skew_angle(img: np.ndarray) -> float:
    """Estimate document skew angle using Hough line transform.

    Returns
    -------
    float
        Skew angle in degrees. Positive = clockwise, negative = counter-clockwise.
    """
    # Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # Edge detection
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Hough line detection
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

    if lines is None or len(lines) == 0:
        return 0.0

    angles = []
    for line in lines:
        rho, theta = line[0]
        # Convert rho/theta to angle (in degrees)
        angle = np.degrees(theta) - 90
        angles.append(angle)

    # Use median to be robust against outliers
    median_angle = np.median(angles)
    return float(median_angle)


def rotate_image(
    img: np.ndarray, angle: float, keep_size: bool = True
) -> np.ndarray:
    """Rotate image by angle degrees around its center.

    Parameters
    ----------
    img : np.ndarray
        Input image (BGR or grayscale).
    angle : float
        Rotation angle in degrees. Positive = clockwise.
    keep_size : bool
        If True, adjust output canvas so no content is cropped.

    Returns
    -------
    np.ndarray
        Rotated image.
    """
    h, w = img.shape[:2]
    center = (w / 2, h / 2)

    if keep_size:
        # Get the full canvas size to avoid cropping
        rot_mat = cv2.getRotationMatrix2D(center, angle, scale=1.0)
        cos = np.abs(rot_mat[0, 0])
        sin = np.abs(rot_mat[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        rot_mat[0, 2] += (new_w / 2) - center[0]
        rot_mat[1, 2] += (new_h / 2) - center[1]
        return cv2.warpAffine(img, rot_mat, (new_w, new_h), flags=cv2.INTER_CUBIC)
    else:
        rot_mat = cv2.getRotationMatrix2D(center, angle, scale=1.0)
        return cv2.warpAffine(img, rot_mat, (w, h), flags=cv2.INTER_CUBIC)


def normalize_bbox(
    bbox: List[float], img_width: int, img_height: int, norm: int = 1000
) -> List[int]:
    """Normalize bounding box coordinates to [0, norm] range.

    Parameters
    ----------
    bbox : List[float]
        [x1, y1, x2, y2] in pixel coordinates.
    img_width : int
        Image width in pixels.
    img_height : int
        Image height in pixels.
    norm : int
        Upper bound of normalized coordinate space (default 1000).

    Returns
    -------
    List[int]
        [x1, y1, x2, y2] normalized to [0, norm].
    """
    x1, y1, x2, y2 = bbox
    nx1 = int(np.clip((x1 / img_width) * norm, 0, norm))
    ny1 = int(np.clip((y1 / img_height) * norm, 0, norm))
    nx2 = int(np.clip((x2 / img_width) * norm, 0, norm))
    ny2 = int(np.clip((y2 / img_height) * norm, 0, norm))
    return [nx1, ny1, nx2, ny2]


def resize_by_long_edge(img: np.ndarray, long_edge: int) -> np.ndarray:
    """Resize image so the longest edge equals `long_edge` while preserving aspect ratio."""
    h, w = img.shape[:2]
    if max(h, w) <= long_edge:
        return img
    scale = long_edge / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


def upscale_image(img: np.ndarray, scale: float) -> np.ndarray:
    """Upscale image by a fixed factor using bicubic interpolation."""
    if scale <= 0:
        return img
    h, w = img.shape[:2]
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


from typing import List
