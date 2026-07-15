"""Modular image preprocessing pipeline for OCR."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Callable, Optional

import cv2
import numpy as np

from ..utils import (
    calculate_skew_angle,
    rotate_image,
    resize_by_long_edge,
    upscale_image,
    get_logger,
)

logger = get_logger(__name__)


@dataclass
class PreprocessingConfig:
    """Configuration for preprocessing pipeline.

    All processing steps are individually togglable. By default
    all are enabled so the pipeline starts with sensible defaults.
    """

    grayscale: bool = True
    adaptive_threshold: bool = True
    deskew: bool = True
    noise_removal: bool = True
    resize_scale: float = 2.0  # > 0 upscale factor, 0 = disabled

    # --- adaptive threshold parameters ---
    threshold_block_size: int = 11   # must be odd
    threshold_c: int = 2

    # --- noise removal (morphology) parameters ---
    morph_kernel_size: int = 3        # must be odd
    morph_iterations: int = 1

    # --- resize by long-edge ---
    target_long_edge: int = 0         # 0 = disabled; else max px


class PreprocessingPipeline:
    """Modular image preprocessing pipeline.

    Each step is implemented as a separate method so individual
    steps can be enabled/disabled via the config object.

    Example
    -------
    >>> config = PreprocessingConfig(grayscale=True, deskew=True)
    >>> pipeline = PreprocessingPipeline(config)
    >>> processed = pipeline.apply(image)
    """

    def __init__(self, config: PreprocessingConfig | None = None) -> None:
        """
        Parameters
        ----------
        config : PreprocessingConfig, optional
            Pipeline configuration. Uses defaults if None.
        """
        self.config = config or PreprocessingConfig()

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Run the full preprocessing pipeline on an image.

        Parameters
        ----------
        img : np.ndarray
            Input image (BGR or grayscale).

        Returns
        -------
        np.ndarray
            Preprocessed image (grayscale or BGR depending on steps).
        """
        cfg = self.config
        steps_applied: List[str] = []
        result = img.copy()

        h, w = result.shape[:2]
        logger.debug("Preprocessing started: %dx%d, channels=%s", w, h,
                     result.shape[2] if len(result.shape) == 3 else 1)

        # 1. Resize (scale)
        if cfg.resize_scale > 0:
            result = self._resize(result)
            steps_applied.append(f"resize(x{cfg.resize_scale})")

        # 2. Resize (long-edge cap)
        if cfg.target_long_edge > 0:
            result = self._resize_by_long_edge(result)
            steps_applied.append(f"long_edge_cap({cfg.target_long_edge})")

        # 3. Grayscale
        if cfg.grayscale:
            result = self._to_grayscale(result)
            steps_applied.append("grayscale")

        # 4. Deskew
        if cfg.deskew:
            result, angle = self._deskew(result)
            if abs(angle) > 0.1:
                steps_applied.append(f"deskew({angle:.2f}°)")
            else:
                steps_applied.append("deskew(0°)")

        # 5. Adaptive threshold (binarization)
        if cfg.adaptive_threshold:
            result = self._adaptive_threshold(result)
            steps_applied.append("adaptive_threshold")

        # 6. Noise removal
        if cfg.noise_removal:
            result = self._noise_removal(result)
            steps_applied.append("noise_removal")

        h2, w2 = result.shape[:2]
        logger.info("Preprocessing done: %s → %dx%d", " → ".join(steps_applied), w2, h2)
        return result

    # ── Individual step methods ──────────────────────────────────────────────

    def _resize(self, img: np.ndarray) -> np.ndarray:
        """Upscale image by the configured scale factor."""
        return upscale_image(img, self.config.resize_scale)

    def _resize_by_long_edge(self, img: np.ndarray) -> np.ndarray:
        """Resize image so the longest edge equals target_long_edge."""
        return resize_by_long_edge(img, self.config.target_long_edge)

    def _to_grayscale(self, img: np.ndarray) -> np.ndarray:
        """Convert image to grayscale."""
        if len(img.shape) == 2:
            return img
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def _deskew(self, img: np.ndarray) -> tuple[np.ndarray, float]:
        """Detect and correct document skew.

        Returns
        -------
        Tuple[np.ndarray, float]
            (corrected image, detected angle in degrees)
        """
        angle = calculate_skew_angle(img)
        if abs(angle) < 0.1:
            return img, 0.0
        logger.debug("Detected skew angle: %.2f°", angle)
        return rotate_image(img, angle), angle

    def _adaptive_threshold(self, img: np.ndarray) -> np.ndarray:
        """Apply adaptive thresholding for binarization.

        Works best on grayscale images; converts to binary (black & white).
        """
        cfg = self.config
        gray = img if len(img.shape) == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        block_size = cfg.threshold_block_size
        # block_size must be odd
        if block_size % 2 == 0:
            block_size += 1
        return cv2.adaptiveThreshold(
            gray,
            maxValue=255,
            adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            thresholdType=cv2.THRESH_BINARY,
            blockSize=block_size,
            C=cfg.threshold_c,
        )

    def _noise_removal(self, img: np.ndarray) -> np.ndarray:
        """Remove salt-and-pepper noise using morphological operations.

        Uses a 3×3 kernel (configurable) with erosion followed by dilation
        (open operation) to remove small white noise, then dilation to close
        small black holes.
        """
        cfg = self.config
        kernel_size = cfg.morph_kernel_size
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (kernel_size, kernel_size),
        )

        # Opening: erode → dilate (removes white noise)
        opened = cv2.morphologyEx(
            img, cv2.MORPH_OPEN, kernel, iterations=cfg.morph_iterations
        )
        # Closing: dilate → erode (removes black holes)
        closed = cv2.morphologyEx(
            opened, cv2.MORPH_CLOSE, kernel, iterations=cfg.morph_iterations
        )
        return closed

    def apply_single_step(
        self, img: np.ndarray, step: str
    ) -> np.ndarray:
        """Apply a single named preprocessing step.

        Parameters
        ----------
        img : np.ndarray
            Input image.
        step : str
            One of: grayscale, adaptive_threshold, deskew,
                    noise_removal, resize.

        Returns
        -------
        np.ndarray
            Result of the single step.
        """
        if step == "grayscale":
            return self._to_grayscale(img)
        elif step == "adaptive_threshold":
            return self._adaptive_threshold(img)
        elif step == "deskew":
            out, _ = self._deskew(img)
            return out
        elif step == "noise_removal":
            return self._noise_removal(img)
        elif step == "resize":
            return self._resize(img)
        else:
            raise ValueError(f"Unknown step: {step!r}")
