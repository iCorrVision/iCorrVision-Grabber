import os
import platform
import logging
from PySide6.QtCore import Slot, QTimer
import cv2 as cv

from components.enumeration_model import CameraBackendType, CameraDescriptor
from components.cameras.template.acquisition_extender import AcquisitionExtension
from components.cameras.opencv.opencv_camera_presenter import OpencvCameraPresenter
from components.cameras.opencv.opencv_view import OpencvView

CameraBackendType.register("OPENCV")


class OpencvAquisitionExtension(AcquisitionExtension):
    """OpenCV backend: device discovery (Linux) and the timer that polls the cameras.

    OpenCV devices deliver no frames by themselves; while polling is on, a timer
    asks every connected OpenCV camera for a frame at the set rate (default
    30 fps, as an integer interval of `1000 // fps` ms).
    """

    def __init__(
        self,
        cameras: dict,
        presenter_registry: dict,
        enumeration,
        view: OpencvView,
    ) -> None:
        super().__init__(cameras, presenter_registry, enumeration)
        self._presenter_registry[CameraBackendType.OPENCV] = OpencvCameraPresenter

        self._fps: int = 30
        self._timer: QTimer = QTimer()
        self._timer.timeout.connect(self._poll)

        self.view: OpencvView = view
        view.grayscale_on_signal.connect(self._on_grayscale_toggled)
        view.toggle_poll_signal.connect(self._on_capture_toggled)
        view.fps_changed_signal.connect(self._on_fps_changed)

    def enumerate(self) -> list[CameraDescriptor]:
        """List the `/dev/video*` devices that deliver a frame (Linux only).

        Devices already in use are listed without probing; the others are opened
        and read once, which filters out nodes that cannot capture.
        """
        opencv_cameras: list[CameraDescriptor] = []
        system = platform.system()
        logging.debug(f"Enumerating OpenCV cameras on {system}")

        active_indices = {
            c.descriptor.backend_id
            for c in self._cameras.values()
            if c is not None and c.descriptor.backend == CameraBackendType.OPENCV
        }

        if system == "Linux":
            try:
                video_entries = sorted(os.scandir("/dev"), key=lambda e: e.name)
                video_entries = [e for e in video_entries if e.name.startswith("video")]

                for entry in video_entries:
                    try:
                        index = int(entry.name.removeprefix("video"))
                    except ValueError:
                        continue

                    try:
                        with open(f"/sys/class/video4linux/video{index}/name") as f:
                            display_name = f.read().strip()
                    except (FileNotFoundError, IOError):
                        display_name = f"Camera {index}"

                    # A device in use cannot be opened a second time for probing.
                    if index in active_indices:
                        descriptor = CameraDescriptor(
                            backend=CameraBackendType.OPENCV,
                            backend_id=index,
                            display_name=display_name,
                        )
                        opencv_cameras.append(descriptor)
                        continue

                    cap = cv.VideoCapture(index)
                    if not cap.isOpened():
                        cap.release()
                        continue

                    ok, _ = cap.read()
                    cap.release()
                    if not ok:
                        continue

                    descriptor = CameraDescriptor(
                        backend=CameraBackendType.OPENCV,
                        backend_id=index,
                        display_name=display_name,
                    )
                    opencv_cameras.append(descriptor)
            except Exception as e:
                logging.error(f"Error during OpenCV camera enumeration: {e}")

        elif system == "Windows":
            logging.warning("Windows camera enumeration not yet implemented")
        elif system == "Darwin":
            logging.warning("macOS camera enumeration not yet implemented")

        return opencv_cameras

    # ==========================================================================
    # Polling and settings
    # ==========================================================================

    @Slot(bool)
    def _on_grayscale_toggled(self, enabled: bool = False):
        """Apply the greyscale setting to every OpenCV camera."""
        for camera in filter(None, self._cameras.values()):
            if camera.descriptor.backend == CameraBackendType.OPENCV:
                camera.presenter.set_grayscale_mode(enabled)

    def _has_active_cameras(self) -> bool:
        return any(self._cameras.values())

    @Slot(bool)
    def _on_capture_toggled(self, enabled: bool = False) -> None:
        self._start_feed() if enabled else self._stop_feed()

    def _start_feed(self) -> None:
        if not self._has_active_cameras():
            return
        self._timer.start(1000 // self._fps)
        logging.info(f"OpenCV frame polling started at {self._fps} fps")

    def _stop_feed(self) -> None:
        self._timer.stop()

    def _poll(self) -> None:
        """Request one frame from every connected OpenCV camera."""
        for camera in filter(None, self._cameras.values()):
            if camera.descriptor.backend == CameraBackendType.OPENCV:
                camera.presenter.poll()

    @Slot(str)
    def _on_fps_changed(self, value: str) -> None:
        """Set the polling rate from the typed text (positive integer, fps).

        Applied at once while polling runs, otherwise at the next start.
        """
        try:
            fps = int(value)
        except ValueError:
            logging.warning(f"Invalid FPS value: {value!r} (must be an integer)")
            return
        if fps <= 0:
            logging.warning(f"Invalid FPS value: {fps} (must be > 0)")
            return
        self._fps = fps
        if self._timer.isActive():
            self._timer.setInterval(1000 // fps)
            logging.info(f"OpenCV polling rate changed to {fps} fps")
        else:
            logging.info(f"OpenCV polling rate set to {fps} fps (applies on start)")
