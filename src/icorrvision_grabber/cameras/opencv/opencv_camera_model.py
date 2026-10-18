from typing_extensions import override
import cv2 as cv
import numpy as np

import logging

from components.cameras.template.camera_model import CameraModel

from components.cameras.camera_exceptions import CameraFatalError


class OpencvCameraModel(CameraModel):
    """OpenCV video device (`cv2.VideoCapture`) identified by its device index."""

    def __init__(self, index: int) -> None:
        self._index: int = index
        self._cap: cv.VideoCapture | None = None
        self.fps: int = 30  # informational; the extension's poll timer sets the rate
        logging.debug(
            f"Initialised OpencvCameraModel for camera index {self._index} with default FPS {self.fps}"
        )

    @override
    def open(self) -> None:
        """Open the device; raises `RuntimeError` if it cannot be opened."""
        logging.info(f"Attempting to open camera at index {self._index}")
        cap = cv.VideoCapture(self._index)
        if not cap.isOpened():
            logging.error(f"Failed to open camera at index {self._index}")
            raise RuntimeError(f"Cannot open camera at index {self._index}")
        self._cap = cap
        logging.info(f"Camera at index {self._index} opened successfully")

    @override
    def read_frame(self) -> np.ndarray | None:
        """Return the next frame (BGR, as delivered by OpenCV).

        Blocks until the device delivers a frame. A failed read raises
        `CameraFatalError`; reading from a closed device raises `RuntimeError`.
        """
        if self._cap is None:
            logging.error("Attempted to read frame without an active camera connection")
            raise RuntimeError("No viable camera connection")
        ret, frame = self._cap.read()
        if not ret:
            logging.error("Failed to capture frame from camera")
            raise CameraFatalError("Camera read failed")
        return frame

    @override
    def close(self) -> None:
        """Release the device; raises `RuntimeError` if it is not open."""
        if self._cap:
            logging.info(f"Closing camera at index {self._index}")
            self._cap.release()
            self._cap = None
            logging.info(f"Camera at index {self._index} closed and resources released")
        else:
            logging.error("Attempted to close camera with no active connection")
            raise RuntimeError("No camera to release")
