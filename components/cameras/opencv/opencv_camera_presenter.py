import logging
from typing_extensions import override
import cv2 as cv

from PySide6.QtGui import QImage
from PySide6.QtCore import Slot

from components.cameras.template.camera_presenter import (
    CameraPresenter,
    FrameWorker,
)

from components.cameras.opencv.opencv_camera_model import OpencvCameraModel
from components.enumeration_model import CameraDescriptor

from UI.camera_frame import CameraFrame
from components.cameras.camera_exceptions import CameraFatalError


class OpencvFrameWorker(FrameWorker):
    """Polled acquisition worker for OpenCV devices, with optional greyscale."""

    def __init__(self, model: OpencvCameraModel) -> None:
        logging.debug("OpencvFrameWorker initialising")
        super().__init__(model)
        self.grayscale_filter: bool = False

    @Slot()
    @override
    def request_frame(self) -> None:
        """Read a frame (greyscale if enabled), save it if recording, and emit it.

        A fatal read error emits `camera_error`.
        """
        try:
            frame = self._model.read_frame()
            if frame is None:
                logging.debug("Frame read returned None")
                return
            if self.grayscale_filter == True:
                frame = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
            self._last_full_frame = frame
            self._maybe_save(frame)
            self.frame_ready_signal.emit(frame, self.frame_name)
        except CameraFatalError as e:
            logging.critical(f"Fatal camera error during frame acquisition: {e}")
            self.camera_error.emit()


class OpencvCameraPresenter(CameraPresenter):
    """Camera presenter for OpenCV devices (polled acquisition)."""

    @override
    def __init__(
        self, frame: CameraFrame, mirrors: list[CameraFrame] | None = None
    ) -> None:
        logging.debug("OpencvCameraPresenter initialising")
        super().__init__(frame, mirrors)
        self._model: OpencvCameraModel | None = None
        self.grayscale_filter: bool = False

    @override
    def connect_camera(self, descriptor: CameraDescriptor) -> None:
        logging.info(
            f"Connecting OpenCV camera from video device index {descriptor.backend_id}"
        )
        super().connect_camera(descriptor)

    @override
    def _create_model(self, descriptor: CameraDescriptor) -> OpencvCameraModel:
        logging.debug(
            f"Creating OpenCV camera model for device index {descriptor.backend_id}"
        )
        return OpencvCameraModel(descriptor.backend_id)

    @override
    def _create_worker(self, model: OpencvCameraModel) -> OpencvFrameWorker:
        logging.debug("Creating OpencvFrameWorker")
        return OpencvFrameWorker(model)

    @override
    def _frame_to_qimage(self, frame) -> QImage:
        """Wrap a greyscale or BGR frame in a `QImage` (BGR is converted to RGB)."""
        try:
            # Decide from the frame, not from self.grayscale_filter: frames queued
            # before the setting changed still have the previous format.
            if frame.ndim == 2:
                h, w = frame.shape
                self._qt_buffer = frame.tobytes()  # QImage does not copy the data
                return QImage(self._qt_buffer, w, h, w, QImage.Format.Format_Grayscale8)
            else:
                h, w, ch = frame.shape
                rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
                self._qt_buffer = rgb.tobytes()
                return QImage(
                    self._qt_buffer, w, h, ch * w, QImage.Format.Format_RGB888
                )
        except Exception as e:
            logging.error(f"Failed to convert frame to QImage: {e}")
            raise

    @override
    def set_async_mode(self, enabled: bool) -> None:
        """OpenCV devices are always polled; the request is only logged."""
        logging.warning("Async mode requested but OpenCV backend does not support it.")

    @Slot(bool)
    def set_grayscale_mode(self, enabled: bool):
        """Convert frames to greyscale before display and saving."""
        self.grayscale_filter = enabled
        self._worker.grayscale_filter = enabled
        logging.debug(f"greyscale filter set to {self.grayscale_filter}")
