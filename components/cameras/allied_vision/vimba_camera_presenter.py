from typing_extensions import override
from vmbpy import *
import logging
import os

from PySide6.QtGui import QImage
from PySide6.QtCore import Slot

from components.cameras.template.camera_presenter import (
    CameraPresenter,
    FrameWorker,
)

from components.cameras.allied_vision.vimba_camera_model import VimbaCameraModel
from components.enumeration_model import CameraDescriptor

from UI.camera_frame import CameraFrame

from components.cameras.camera_exceptions import CameraFatalError


class VimbaFrameWorker(FrameWorker):
    """Acquisition worker for Vimba cameras: streamed (default) or polled."""

    def __init__(self, model: VimbaCameraModel) -> None:
        logging.debug("VimbaFrameWorker initialising")
        super().__init__(model)

    # --------------------------------------------------------------------------
    # Polled acquisition
    # --------------------------------------------------------------------------
    # Required by the FrameWorker interface; Vimba cameras stream by default, so
    # this path is not used in normal operation.

    @Slot()
    @override
    def request_frame(self) -> None:
        """Read one frame, save it if recording, and emit it.

        A timeout emits `camera_error`.
        """
        try:
            frame = self._model.read_frame()
            if frame is None:
                logging.warning("Vimba frame read returned None")
                return
            self._last_full_frame = frame
            self._maybe_save(frame)
            self.frame_ready_signal.emit(frame, self.frame_name)
        except CameraFatalError as e:
            logging.critical(f"Fatal Vimba camera error during frame acquisition: {e}")
            self.camera_error.emit()

    # --------------------------------------------------------------------------
    # Streamed acquisition
    # --------------------------------------------------------------------------

    @Slot()
    def start_streaming(self) -> None:
        """Start streaming; frames arrive in `_streaming_handler`."""
        try:
            logging.info("Starting Vimba async streaming")
            self._model.start_streaming(self._streaming_handler)
        except Exception as e:
            logging.error(f"Failed to start Vimba streaming: {e}")
            self.camera_error.emit()

    @Slot()
    def stop_streaming(self) -> None:
        """Stop streaming."""
        logging.info("Stopping Vimba async streaming")
        self._model.stop_streaming()

    def _streaming_handler(self, camera, stream, frame) -> None:
        """Handle one streamed frame (runs on an SDK thread).

        A complete frame is copied out of the SDK buffer, saved if recording and
        emitted; incomplete frames are logged and skipped. The buffer is returned
        to the camera in either case.
        """
        if frame.get_status() == FrameStatus.Complete:
            arr = frame.as_numpy_ndarray().copy()
            self._last_full_frame = arr
            self._maybe_save(arr)
            self.frame_ready_signal.emit(arr, self.frame_name)
        else:
            logging.warning(
                f"Vimba frame received with non-complete status: {frame.get_status()}"
            )
        camera.queue_frame(frame)


class VimbaCameraPresenter(CameraPresenter):
    """Camera presenter for Allied Vision cameras; streams frames by default."""

    @override
    def __init__(
        self, frame: CameraFrame, mirrors: list[CameraFrame] | None = None
    ) -> None:
        logging.debug("VimbaCameraPresenter initialising")
        super().__init__(frame, mirrors)
        self._async_mode: bool = True
        self._model: VimbaCameraModel | None = None

    @override
    def connect_camera(self, descriptor: CameraDescriptor) -> None:
        """Open the camera and, in streaming mode, start streaming."""
        logging.info(f"Connecting Vimba camera {descriptor.display_name}")
        super().connect_camera(descriptor)
        if self._async_mode and self._worker is not None:
            self._worker.start_streaming()

    def disconnect_camera(self) -> None:
        """Stop streaming, then disconnect as in `CameraPresenter`."""
        logging.info("Disconnecting Vimba camera")
        if self._worker is not None and self._async_mode:
            self._worker.stop_streaming()
        super().disconnect_camera()

    @override
    def _create_model(self, descriptor: CameraDescriptor) -> VimbaCameraModel:
        logging.debug(f"Creating Vimba camera model for {descriptor.display_name}")
        return VimbaCameraModel(descriptor.backend_id)

    @override
    def _create_worker(self, model: VimbaCameraModel) -> VimbaFrameWorker:
        logging.debug("Creating VimbaFrameWorker")
        return VimbaFrameWorker(model)

    @override
    def _frame_to_qimage(self, frame) -> QImage:
        """Wrap a Mono8 frame, (H, W) or (H, W, 1), in a greyscale `QImage`."""
        try:
            frame_2d = frame[:, :, 0] if frame.ndim == 3 else frame
            h, w = frame_2d.shape
            self._qt_buffer = frame_2d.tobytes()  # QImage does not copy the data
            return QImage(self._qt_buffer, w, h, w, QImage.Format.Format_Grayscale8)
        except Exception as e:
            logging.error(f"Failed to convert Vimba frame to QImage: {e}")
            raise

    @override
    def set_async_mode(self, enabled: bool) -> None:
        """Switch between streamed (True) and polled acquisition at any time."""
        logging.info(f"Setting Vimba async mode: {enabled}")
        self._async_mode = enabled
        if self._worker is None:
            logging.debug("No active worker, mode will take effect on next connection")
            return
        if enabled:
            logging.debug("Transitioning to Vimba async streaming")
            self._worker.start_streaming()
        else:
            logging.debug("Transitioning to Vimba sync polling")
            self._worker.stop_streaming()

    # --------------------------------------------------------------------------
    # Camera settings
    # --------------------------------------------------------------------------

    def set_exposition_time(self, value: float) -> None:
        self._model.set_exposition_time(value)

    def set_frame_rate(self, value: float) -> None:
        self._model.set_frame_rate(value)

    def enable_frame_rate(self, enabled: bool) -> None:
        self._model.enable_frame_rate(enabled)

    def save_config(self, path: str) -> None:
        """Save the camera's GenICam settings to `path`, creating its folder."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._model.save_xml(path)

    def load_config(self, path: str) -> None:
        self._model.load_xml(path)

    @property
    def serial_number(self) -> str:
        if self._model is not None:
            return self._model.serial_number
