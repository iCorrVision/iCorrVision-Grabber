"""Synthetic speckle images for the acquisition test.

Derived from the synthetic-image module of iCorrVision 2D (its benchmarks use the same
speckle pattern and Fourier shift); only the two functions the acquisition test uses are kept,
with their code unchanged so the test images can be regenerated exactly. The recordings in
the thesis used 20 frames of `speckle(768, 1024)` (Vimba X simulator) or `speckle(1024, 1280)`
(v4l2loopback source), each shifted by `translate(..., dx=0.5 * k, dy=0.0)` for k = 0..19 and
rounded to 8 bit.
"""

import cv2
import numpy as np
from scipy.ndimage import fourier_shift


def speckle(
    height: int = 256, width: int = 256, feature_px: float = 2.5, seed: int = 0
) -> np.ndarray:
    """A random speckle-like pattern: Gaussian-blurred white noise, 8-bit range.

    `feature_px` is the blur sigma, i.e. roughly the speckle radius in pixels.
    Blurring makes the pattern band-limited, which is what lets a sub-pixel
    shift be applied exactly below.
    """
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((height, width)).astype(np.float32)
    ksize = int(6 * feature_px) | 1  # smallest odd kernel covering +/-3 sigma
    blurred = cv2.GaussianBlur(noise, (ksize, ksize), sigmaX=feature_px)
    blurred = (blurred - blurred.min()) / (blurred.max() - blurred.min())
    return (blurred * 200 + 25).astype(np.float32)


def translate(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Rigid sub-pixel shift by (dx, dy) px, applied in the Fourier domain.

    A Fourier shift is exact for a band-limited image -- no interpolation kernel
    is involved -- so the true displacement between frames is known exactly,
    which is what the contract test with iCorrVision 2D relies on. The shift is
    circular, so a strip |dx| px wide wraps around at the image edge; points near
    the border should not be used for checks.
    """
    spectrum = fourier_shift(np.fft.fft2(image), shift=(dy, dx))
    return np.real(np.fft.ifft2(spectrum)).astype(np.float32)
