from typing_extensions import override
from vmbpy import *
import numpy as np
import logging

from components.cameras.template.camera_model import CameraModel

from components.cameras.allied_vision.vimba_runtime import get_vmb
from components.cameras.camera_exceptions import CameraFatalError


class VimbaCameraModel(CameraModel):
    """Allied Vision camera accessed through Vimba X, identified by its extended ID.

    The camera is opened in 8-bit greyscale (Mono8). Frames can be read one at
    a time (`read_frame`) or streamed to a callback (`start_streaming`).
    """

    def __init__(self, extended_id: str):
        self._extended_id: str = extended_id
        self._cap: Camera | None = None
        self._pfm: PixelFormat | None = None
        self._serial_number: str = ""
        self.supported_pfm: tuple = ()
        logging.debug(f"Initialised VimbaCameraModel for camera ID {self._extended_id}")

    @override
    def open(self) -> tuple:
        """Open the camera, set Mono8 and read its serial number.

        Returns the pixel formats the camera supports; raises `RuntimeError` if
        the Vimba system is not running.
        """
        logging.info(f"Attempting to open Vimba camera with ID {self._extended_id}")
        vmb = get_vmb()
        if vmb is None:
            logging.error("Vimba runtime not available")
            raise RuntimeError("Vimba runtime not available.")
        try:
            self._cap = vmb.get_camera_by_id(self._extended_id)
            self._serial_number = self._cap.get_serial()
            self._cap.__enter__()
            logging.debug(f"Camera context entered for {self._extended_id}")
            self.supported_pfm = self._cap.get_pixel_formats()
            logging.debug(
                f"Retrieved {len(self.supported_pfm)} supported pixel formats"
            )
            self._pfm = PixelFormat.Mono8
            self._cap.set_pixel_format(self._pfm)
            self._serial_number = self._cap.get_feature_by_name(
                "DeviceSerialNumber"
            ).get()
            logging.info(
                f"Vimba camera {self._extended_id} opened successfully with pixel format {self._pfm}"
            )
        except Exception as e:
            logging.error(f"Failed to open Vimba camera {self._extended_id}: {e}")
            raise
        return self.supported_pfm

    @property
    def serial_number(self) -> str:
        """Device serial number (names the camera's XML settings file)."""
        return self._serial_number

    @override
    def close(self) -> None:
        """Close the camera; raises `RuntimeError` if it is not open."""
        if self._cap is None:
            logging.error("Attempted to close camera with no active connection")
            raise RuntimeError("No camera to release.")
        logging.info(f"Closing Vimba camera {self._extended_id}")
        self._cap.__exit__(None, None, None)
        self._cap = None
        logging.info(f"Vimba camera {self._extended_id} closed and resources released")

    @override
    def read_frame(self) -> np.ndarray | None:
        """Acquire one frame; None if incomplete, `CameraFatalError` on timeout."""
        if self._cap is None:
            logging.error("Attempted to read frame without an active camera connection")
            raise RuntimeError("No viable camera connection.")
        try:
            frame = self._cap.get_frame()
            logging.debug(f"Frame retrieved from camera {self._extended_id}")
        except VmbTimeout:
            logging.error(
                f"Camera {self._extended_id} timed out during frame acquisition"
            )
            raise CameraFatalError("Camera timed out")
        if frame.get_status() != FrameStatus.Complete:
            logging.warning(
                f"Incomplete frame received from camera {self._extended_id}, status: {frame.get_status()}"
            )
            return None
        logging.debug(f"Frame read successfully from camera {self._extended_id}")
        return frame.as_numpy_ndarray()

    # --------------------------------------------------------------------------
    # Asynchronous streaming
    # --------------------------------------------------------------------------

    def start_streaming(self, handler) -> None:
        """Stream frames to `handler(camera, stream, frame)` on an SDK thread."""
        if self._cap is None:
            logging.error(
                "Attempted to start streaming without an active camera connection"
            )
            raise RuntimeError("No viable camera connection.")
        logging.info(f"Starting streaming for camera {self._extended_id}")
        self._cap.start_streaming(handler)
        logging.info(f"Streaming started successfully for camera {self._extended_id}")

    def stop_streaming(self) -> None:
        """Stop streaming."""
        if self._cap is None:
            logging.error(
                "Attempted to stop streaming without an active camera connection"
            )
            raise RuntimeError("No viable camera connection.")
        logging.info(f"Stopping streaming for camera {self._extended_id}")
        self._cap.stop_streaming()
        logging.info(f"Streaming stopped for camera {self._extended_id}")

    # --------------------------------------------------------------------------
    # Camera settings (GenICam features)
    # --------------------------------------------------------------------------

    def set_exposition_time(self, value: float) -> None:
        """Set `ExposureTime` in microseconds."""
        self._cap.get_feature_by_name("ExposureTime").set(value)
        logging.info(f"Exposure time for {self._cap.get_model()} updated to {value}")

    def set_frame_rate(self, value: float) -> None:
        """Set `AcquisitionFrameRate` (fps); ignored unless rate control is on."""
        if self._cap.get_feature_by_name("AcquisitionFrameRateEnable").get() == False:
            logging.warning(
                f"Acquisition frame rate not yet enabled for {self._cap.get_model()}"
            )
            return
        self._cap.get_feature_by_name("AcquisitionFrameRate").set(value)

    def enable_frame_rate(self, enabled: bool) -> None:
        """Switch `AcquisitionFrameRateEnable`."""
        self._cap.get_feature_by_name("AcquisitionFrameRateEnable").set(enabled)

    def save_xml(self, path: str) -> None:
        """Save all camera settings to a GenICam XML file."""
        self._cap.save_settings(path)

    def load_xml(self, path: str) -> None:
        """Load camera settings from a GenICam XML file."""
        self._cap.load_settings(path)
