import os
import logging
from typing import override
from components.cameras.allied_vision.allied_view import AlliedOptionsView
from PySide6.QtCore import Slot

from components.cameras.allied_vision.vimba_runtime import get_vmb
from components.enumeration_model import CameraBackendType, CameraDescriptor
from components.cameras.template.acquisition_extender import AcquisitionExtension
from components.cameras.allied_vision.vimba_camera_presenter import VimbaCameraPresenter

CameraBackendType.register("VIMBA")


class VimbaAcquisitionExtension(AcquisitionExtension):
    """Allied Vision backend (Vimba X): device discovery and the camera settings.

    Loaded only if VmbPy imports. Settings from the Allied Vision panel (frame
    rate, exposure time, GenICam XML) are applied to every connected Vimba
    camera; an XML file is applied only to the camera whose serial number it
    carries in its name.
    """

    def __init__(
        self,
        cameras: dict,
        presenter_registry: dict,
        enumeration,
        allied_view: AlliedOptionsView,
    ) -> None:
        super().__init__(cameras, presenter_registry, enumeration)
        self._presenter_registry[CameraBackendType.VIMBA] = VimbaCameraPresenter

        allied_view.path_xml_signal.connect(self._retrieve_allied_stats)
        allied_view.load_xml_signal.connect(self._apply_allied_config)

        allied_view.frame_rate_toggle_signal.connect(self.enable_frame_rate)
        allied_view.frame_rate_signal.connect(self.set_frame_rate)

        allied_view.exposure_time_signal.connect(self.allied_exposition_time)

    @override
    def enumerate(self) -> list[CameraDescriptor]:
        """List the cameras the Vimba system reports (identified by extended ID)."""
        descriptors: list[CameraDescriptor] = []
        try:
            vmb = get_vmb()
            if vmb is None:
                return descriptors
            for cam in vmb.get_all_cameras():
                descriptors.append(
                    CameraDescriptor(
                        backend=CameraBackendType.VIMBA,
                        backend_id=cam.get_extended_id(),
                        display_name=cam.get_model(),
                    )
                )
        except Exception as e:
            logging.error(f"Vimba enumeration failed: {e}")
        return descriptors

    # ---------------------------------------------------------------------------
    # Camera settings
    # ---------------------------------------------------------------------------

    @staticmethod
    def _parse_positive_float(value: str, what: str) -> float | None:
        """Parse panel text as a positive number, or log a warning and return None."""
        try:
            number = float(value)
        except ValueError:
            logging.warning(f"Invalid {what}: {value!r} (must be a number)")
            return None
        if number <= 0:
            logging.warning(f"Invalid {what}: {number} (must be > 0)")
            return None
        return number

    @Slot(str)
    def allied_exposition_time(self, value: str) -> None:
        """Set the exposure time (µs, as typed) of every Vimba camera."""
        exposure = self._parse_positive_float(value, "exposure time")
        if exposure is None:
            return
        for camera in filter(None, self._cameras.values()):
            if camera.descriptor.backend == CameraBackendType.VIMBA:
                camera.presenter.set_exposition_time(exposure)

    @Slot(bool)
    def enable_frame_rate(self, enabled: bool) -> None:
        """Make the set frame rate govern acquisition (else the camera free-runs)."""
        for camera in filter(None, self._cameras.values()):
            if camera.descriptor.backend == CameraBackendType.VIMBA:
                camera.presenter.enable_frame_rate(enabled)

    @Slot(str)
    def set_frame_rate(self, value: str) -> None:
        """Set the frame rate (fps, as typed) of every Vimba camera."""
        rate = self._parse_positive_float(value, "frame rate")
        if rate is None:
            return
        for camera in filter(None, self._cameras.values()):
            if camera.descriptor.backend == CameraBackendType.VIMBA:
                camera.presenter.set_frame_rate(rate)

    @Slot(str)
    def _apply_allied_config(self, file_path: str) -> None:
        """Load `<serial>.xml` into the camera with that serial number."""
        if not file_path.endswith(".xml"):
            logging.warning("Selected file is not an XML")
            return

        # The file name identifies the one camera the settings belong to.
        serial = os.path.splitext(os.path.basename(file_path))[0]
        logging.info(f"Loading camera settings for serial number {serial}")
        matching = [
            c
            for c in self._cameras.values()
            if c is not None
            and c.descriptor.backend == CameraBackendType.VIMBA
            and c.presenter.serial_number == serial
        ]

        if not matching:
            logging.warning(f"XML serial '{serial}' doesn't match any connected camera")
            return

        for camera in matching:
            camera.presenter.load_config(file_path)

    @Slot(str)
    def _retrieve_allied_stats(self, folder: str) -> None:
        """Save each Vimba camera's settings as `<serial>.xml` in `folder`."""
        os.makedirs(folder, exist_ok=True)
        for camera in filter(None, self._cameras.values()):
            if camera.descriptor.backend == CameraBackendType.VIMBA:
                logging.debug(
                    f"retrieving camera settings for {camera.presenter.serial_number}"
                )
                path = os.path.join(folder, f"{camera.presenter.serial_number}.xml")
                camera.presenter.save_config(path)
