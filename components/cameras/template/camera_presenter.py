import queue
from abc import abstractmethod
from functools import lru_cache
import cv2 as cv
import numpy as np
from pathlib import Path
import logging
import re

from PySide6.QtCore import (
    QObject,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QPixmap

from components.enumeration_model import CameraDescriptor
from components.cameras.template.camera_model import CameraModel
from UI.camera_frame import CameraFrame


class FrameWriterWorker(QThread):
    """Thread writing queued frames to TIFF files, so acquisition never waits on disk.

    Queue items are `{"path": Path, "data": ndarray}`; frames are written in
    queue order.
    """

    def __init__(self, save_queue: queue.Queue) -> None:
        super().__init__()
        self._queue = save_queue
        self._stop_token = object()

    def run(self) -> None:
        """Write items until the stop token is dequeued."""
        while True:
            item = self._queue.get()
            if item is self._stop_token:
                break
            data = np.squeeze(item["data"])
            cv.imwrite(str(item["path"]), data)

    def stop(self) -> None:
        """Finish writing everything queued so far, then end the thread."""
        self._queue.put(self._stop_token)
        self.wait()


class SaturationOverlayWorker(QThread):
    """Thread that computes the overexposure overlay of the most recent frame.

    The queue holds a single item: a new frame replaces one not yet processed,
    so a slow overlay drops frames instead of delaying the display.
    """

    overlay_ready: Signal = Signal(object)
    oversaturated_count: Signal = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._stop_token = object()

    def submit(self, frame: np.ndarray, threshold: int, scale_value: int) -> None:
        """Queue a frame, replacing any frame still waiting."""
        item = (frame, threshold, scale_value)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._queue.get_nowait()
            self._queue.put_nowait(item)

    def run(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._stop_token:
                break
            frame, threshold, scale_value = item
            if frame is None:
                continue
            display, osc = CameraPresenter.apply_overexposure_overlay(
                frame, threshold, scale_value
            )
            self.overlay_ready.emit(display)
            self.oversaturated_count.emit(osc)

    def stop(self) -> None:
        """End the thread, discarding a frame still waiting."""
        try:
            self._queue.put_nowait(self._stop_token)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(self._stop_token)
        self.wait()


class FrameWorker(QObject):
    """Acquisition worker of one camera, run on its own thread.

    Each frame is kept for snapshots, queued for writing while recording, and
    emitted with the name of the most recently saved file. Files are named
    <prefix>_<camera index>_<4-digit number>.tiff, continuing after the highest
    existing number in the save folder.
    """

    # The file name travels with the frame: by the time the main thread handles
    # a frame, the worker may already have saved later ones.
    frame_ready_signal = Signal(object, str)
    camera_error = Signal()

    def __init__(self, model: CameraModel) -> None:
        super().__init__()
        self._model = model

        self._saving: bool = False
        self._save_path: str = " "
        self._save_prefix: str = "frame"
        self.frame_name: str = " "  # most recently saved file
        self._frame_count: int = 0
        self._index: int = 0
        self._last_full_frame: np.ndarray | None = None

        self._save_queue: queue.Queue = queue.Queue()
        self._writer = FrameWriterWorker(self._save_queue)
        self._writer.start()
        logging.debug("FrameWorker initialised and ready for frame acquisition")

    def stop_writer(self) -> None:
        """Write the remaining queued frames and stop the writer thread."""
        self._writer.stop()

    # ------------------------------------------------------------------
    # Saving (invoked through queued signals from CameraPresenter)
    # ------------------------------------------------------------------

    @Slot(str)
    def start_saving(self, path: str) -> None:
        """Save every following frame into `path`."""
        self._frame_count = self.find_last_frame_count(self._save_prefix)
        self._save_path = path
        self._saving = True
        logging.info(f"Started saving frames to {path}")

    def find_last_frame_count(self, prefix: str) -> int:
        """Next free frame number for `prefix` and this camera in the save folder."""
        pattern = re.compile(rf"^{re.escape(prefix)}_{self._index}_(\d+)\.tiff$")
        counts = [
            int(m.group(1))
            for f in Path(self._save_path).glob("*.tiff")
            if (m := pattern.match(f.name))
        ]
        return max(counts) + 1 if counts else 0

    @Slot()
    def stop_saving(self) -> None:
        """Stop saving; frames already queued are still written."""
        self._saving = False
        logging.info("Stopped saving frames")

    @Slot(str)
    def take_snapshot(self) -> None:
        """Save the most recent frame, numbered like a recorded frame."""
        if self._last_full_frame is None:
            logging.warning("Snapshot requested but no frame has been received yet.")
            return
        if self._save_path == " ":
            logging.warning("No save path set yet.")

        self._frame_count = self.find_last_frame_count(self._save_prefix)
        self.frame_name = (
            f"{self._save_prefix}_{self._index}_{self._frame_count:04d}.tiff"
        )
        save_path = Path(self._save_path) / self.frame_name
        self._save_queue.put({"path": save_path, "data": self._last_full_frame})
        logging.info(f"Snapshot queued: {self._save_path}")
        self._frame_count += 1

    # ------------------------------------------------------------------
    # Polled acquisition (timer -> CameraPresenter.poll -> request_frame)
    # ------------------------------------------------------------------

    # CRITICAL: do not decorate this base declaration with @Slot, but DO decorate
    # every subclass override with @Slot(). If both the base and the override are
    # slots, PySide6 (seen on 6.10.2) runs the call on the main thread instead of
    # the worker's acquisition thread, and frame reading blocks the GUI.
    @abstractmethod
    def request_frame(self) -> None:
        """Read one frame, keep it for snapshots, save it if recording, and emit it."""
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _maybe_save(self, frame: np.ndarray) -> None:
        """Queue `frame` for writing if recording, and advance the frame number."""
        if not self._saving:
            return
        if self._save_path == " ":
            logging.warning("Saving enabled but no save path set - stopping save.")
            self._saving = False
            return
        self.frame_name = (
            f"{self._save_prefix}_{self._index}_{self._frame_count:04d}.tiff"
        )
        save_path = Path(self._save_path) / self.frame_name
        self._save_queue.put({"path": save_path, "data": frame})
        self._frame_count += 1


class CameraPresenter(QObject):
    """Presenter of one camera: its model and worker, bound to a camera slot.

    Opens the device, runs the backend's worker on an acquisition thread,
    displays each frame in the slot and its mirrors (with the overexposure
    overlay computed on a further thread when enabled), and passes the save
    commands to the worker through queued signals.
    """

    # (camera index, frame, most recently saved file name)
    frame_ready_signal: Signal = Signal(int, np.ndarray, str)
    oversaturation_count: Signal = Signal(int, int)  # (camera index, pixel count)

    _request_frame = Signal()
    _request_snapshot = Signal(str)
    _start_saving = Signal(str)
    _stop_saving = Signal()

    def __init__(
        self, frame: CameraFrame, mirrors: list[CameraFrame] | None = None
    ) -> None:
        """`mirrors` are further slots that show the same camera."""
        super().__init__()
        self._frame: CameraFrame = frame
        self._mirrors: list[CameraFrame] = mirrors or []
        self.index: int = 0  # overwritten by set_index() once the slot is known
        self._model = None
        self._worker = None
        self._thread = None
        self._async_mode = False
        self._qt_buffer = None
        self.path = " "
        self.prefix = "frame"
        self._overlay_saturation_enabled: bool = False
        self._sat_threshold: int = 200
        self._overlay_scale_value: int = 0
        self._overlay_worker: SaturationOverlayWorker | None = None
        self.oversaturated_count: int = 0

    # --------------------------------------------------------------------------
    # Camera connection
    # --------------------------------------------------------------------------

    def connect_camera(self, descriptor: CameraDescriptor) -> None:
        """Open the device and start its acquisition and overlay threads.

        Frames then arrive from the backend's poll timer or the camera's stream.
        """
        logging.info(
            f"Connecting to camera: {descriptor.display_name} ({descriptor.id})"
        )
        self._model = self._create_model(descriptor)
        self._model.open()

        self._worker = self._create_worker(self._model)
        if self.path != " ":
            self._worker._save_path = self.path
        if self.prefix != "frame":
            self._worker._save_prefix = self.prefix
        self._thread = QThread()

        self._worker.moveToThread(self._thread)

        self._request_frame.connect(self._worker.request_frame)
        self._request_snapshot.connect(self._worker.take_snapshot)
        self._start_saving.connect(self._worker.start_saving)
        self._stop_saving.connect(self._worker.stop_saving)
        self._worker.frame_ready_signal.connect(self._on_frame_ready)
        self._worker.camera_error.connect(self.disconnect_camera)

        self._thread.start()
        self._start_overlay_worker()
        logging.info(f"Camera connected successfully: {descriptor.display_name}")

    def disconnect_camera(self) -> None:
        """Write the queued frames, stop the threads and close the device."""
        logging.info("Disconnecting camera and cleaning up resources")
        if self._worker is not None:
            self._worker.stop_writer()
            logging.debug("Frame writer stopped")

        self._stop_overlay_worker()

        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            logging.debug("Worker thread quit and joined")

        if self._model is not None:
            self._model.close()
            logging.debug("Camera model closed")

        self._worker = None
        self._thread = None
        self._model = None
        logging.info("Camera disconnected and resources cleaned up")

    @abstractmethod
    def _create_model(self, descriptor: CameraDescriptor) -> CameraModel:
        """Return the backend's model for the device (not yet opened)."""
        ...

    @abstractmethod
    def _create_worker(self, model) -> QObject:
        """Return the backend's acquisition worker for `model`."""
        ...

    # --------------------------------------------------------------------------
    # Saving
    # --------------------------------------------------------------------------

    # NOTE: set_save_path, set_save_prefix and set_index write the worker's
    # attributes from the main thread while the worker runs on the acquisition
    # thread (start/stop and snapshots use queued signals instead). Changing the
    # folder or prefix during a recording can therefore race with the frame
    # counter and, at worst, reuse a file name. Known limitation of v2.0.0-msc:
    # set both before recording.
    def set_save_path(self, path: str) -> None:
        """Set the save folder; numbering continues after its existing files."""
        logging.info(f"Save path updated: {self.path!r} -> {path!r}")
        self.path = path
        if self._worker is not None:
            self._worker._save_path = path
            self._worker._frame_count = self._worker.find_last_frame_count(self.prefix)

    def set_save_prefix(self, prefix: str) -> None:
        """Set the file-name prefix (blank values are ignored).

        Numbering continues after the highest existing file with that prefix.
        """
        logging.info(f"Save prefix updated: {self.prefix!r} -> {prefix!r}")
        if self.prefix != prefix and (prefix != "" and prefix != " "):
            self.prefix = prefix
            if self._worker is not None:
                self._worker._frame_count = self._worker.find_last_frame_count(prefix)
                self._worker._save_prefix = prefix

    def set_index(self, index: int = 0) -> None:
        """Set the camera index used in file names and the manifest (0 or 1)."""
        self.index = index
        if self._worker is not None:
            self._worker._index = index

    def set_overlay_enabled(self, enabled: bool) -> None:
        """Switch the overexposure overlay on or off for this camera's display."""
        self._overlay_saturation_enabled = enabled

    @Slot(int)
    def set_saturation_scaling(self, value: int) -> None:
        """Set the overlay downscaling step (0-10; see `_scale_from_value`)."""
        self._overlay_scale_value = int(np.clip(value, 0, 10))

    def start_saving(self) -> None:
        """Start recording into the save folder (ignored if none is set)."""
        if self.path == " ":
            logging.warning("Cannot start saving: no save path set.")
            return
        logging.info(f"Initiating frame saving to {self.path}")
        self._start_saving.emit(self.path)

    def stop_saving(self) -> None:
        """Stop recording."""
        logging.info("Stopping frame saving")
        self._stop_saving.emit()

    def snapshot(self) -> None:
        """Save the most recent frame (ignored if no save folder is set)."""
        if self.path == " ":
            logging.warning("Cannot take snapshot: no save path set.")
            return
        logging.info(f"Snapshot requested, saving to {self.path}")
        self._request_snapshot.emit(self.path)

    # --------------------------------------------------------------------------
    # Acquisition and display
    # --------------------------------------------------------------------------

    # Called by polled backends (OpenCV) from their timer; push backends (Vimba)
    # never call it. It is kept here for any future polled backend.
    def poll(self) -> None:
        """Ask the worker, on its thread, to read one frame."""
        if self._worker is None:
            logging.debug("Poll called but no active worker")
            return
        self._request_frame.emit()

    def _start_overlay_worker(self) -> None:
        if self._overlay_worker is not None:
            return
        self._overlay_worker = SaturationOverlayWorker()
        self._overlay_worker.overlay_ready.connect(self._on_overlay_ready)
        self._overlay_worker.oversaturated_count.connect(
            self._update_oversaturated_count
        )
        self._overlay_worker.start()

    @Slot(int)
    def _update_oversaturated_count(self, count: int) -> None:
        self.oversaturated_count = count
        self.oversaturation_count.emit(self.index, count)

    def _stop_overlay_worker(self) -> None:
        if self._overlay_worker is None:
            return
        self._overlay_worker.stop()
        self._overlay_worker = None

    @Slot(int)
    def set_threshold_value(self, value: int) -> None:
        """Set the overexposure threshold (grey level 0-255)."""
        if 0 <= value <= 255:
            self._sat_threshold = value
        else:
            logging.warning("please input valid value for threshold.")

    @Slot(object, str)
    def _on_frame_ready(self, frame, frame_name: str) -> None:
        """Display a frame from the worker and pass it on unchanged (main thread).

        With the overlay enabled, the display is updated by `_on_overlay_ready`
        when the overlay thread has processed the frame.
        """
        # Frames wait in the main thread's event queue, so some can arrive after
        # disconnect_camera(); they must not be drawn, counted or written.
        if self._worker is None:
            return
        if self._overlay_saturation_enabled:
            if self._overlay_worker is None:
                display, _ = self.apply_overexposure_overlay(
                    frame, self._sat_threshold, self._overlay_scale_value
                )
                self._on_overlay_ready(display)
            else:
                self._overlay_worker.submit(
                    frame, self._sat_threshold, self._overlay_scale_value
                )
        else:
            qt_image = self._frame_to_qimage(frame)
            pixmap = QPixmap.fromImage(qt_image)
            self._frame.update_frame(pixmap)
            for mirror in self._mirrors:
                mirror.update_frame(pixmap)
        self.frame_ready_signal.emit(self.index, frame, frame_name)  # never the overlay

    @Slot(object)
    def _on_overlay_ready(self, display: np.ndarray) -> None:
        """Display an overlay image (RGB) in the slot and its mirrors."""
        if not self._overlay_saturation_enabled:
            return
        h, w, ch = display.shape
        self._qt_buffer = display  # QImage does not copy the array; keep it alive
        qt_image = QImage(display.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        self._frame.update_frame(pixmap)
        for mirror in self._mirrors:
            mirror.update_frame(pixmap)

    # --------------------------------------------------------------------------
    # Backend-specific methods
    # --------------------------------------------------------------------------

    @abstractmethod
    def _frame_to_qimage(self, frame) -> QImage:
        """Convert a frame of this backend to a `QImage` for display."""

    @abstractmethod
    def set_async_mode(self, enabled: bool) -> None:
        """Choose streamed (camera-pushed) or polled acquisition, if supported."""

    # --------------------------------------------------------------------------
    # Overexposure overlay
    # --------------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=256)
    def _build_overlay_lut(threshold: int) -> np.ndarray:
        """Grey level -> RGB lookup table: grey below or at `threshold`, red above."""
        base = np.arange(256, dtype=np.uint8)
        lut = np.stack((base, base, base), axis=1)
        if threshold < 255:
            lut[threshold + 1 :] = (200, 0, 0)
        return lut

    @staticmethod
    def _scale_from_value(value: int) -> float:
        """Scale for a downscaling step: 0 -> 1.0, 5 -> 0.5, at least 0.1."""
        value = int(np.clip(value, 0, 10))
        scale = 1.0 - (value * 0.1)
        return max(scale, 0.1)

    @staticmethod
    def _resize_for_overlay(frame: np.ndarray, scale: float) -> np.ndarray:
        """Shrink the frame by `scale` (nearest neighbour, so no new grey levels)."""
        if scale >= 0.999:
            return frame
        h, w = frame.shape[:2]
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return cv.resize(frame, (new_w, new_h), interpolation=cv.INTER_NEAREST)

    @staticmethod
    def apply_overexposure_overlay(
        frame: np.ndarray, threshold: int, scale_value: int = 0
    ) -> tuple[np.ndarray, int]:
        """Mark pixels brighter than `threshold` in red and count them.

        The frame is first downscaled according to `scale_value`, so the count
        refers to the pixels of the downscaled frame. Returns the RGB overlay
        image and the count.
        """
        scale = CameraPresenter._scale_from_value(scale_value)
        frame = CameraPresenter._resize_for_overlay(frame, scale)
        if frame.ndim == 2:
            gray = frame
        elif frame.ndim == 3 and frame.shape[2] == 1:
            gray = frame[:, :, 0]
        else:
            gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)

        if gray.dtype != np.uint8:
            gray = cv.convertScaleAbs(gray)

        oversaturated_count: int = int(np.count_nonzero(gray > threshold))

        lut = CameraPresenter._build_overlay_lut(threshold)
        display = lut[gray]
        if not display.flags["C_CONTIGUOUS"]:
            display = np.ascontiguousarray(display)
        return display, oversaturated_count
