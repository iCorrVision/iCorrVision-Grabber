import logging
from typing import Callable
import numpy as np
from dataclasses import dataclass
from pathlib import Path
import csv
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot

from components.cameras.template.acquisition_extender import AcquisitionExtension
from components.enumeration_model import (
    CameraBackendType,
    EnumerationModel,
    CameraRegistry,
    CameraDescriptor,
)

from UI.camera_view import CameraView
from UI.camera_frame import CameraFrame
from UI.control_bar_view import AcquisitionSideBar
from UI.general_view import GeneralView
from UI.draw_panel_view import DrawView

from components.cameras.template.camera_presenter import CameraPresenter


@dataclass
class CameraSlot:
    """A connected camera: presenter, device and position (0 left or mono, 1 right)."""

    presenter: CameraPresenter
    descriptor: CameraDescriptor
    index: int


class AcquisitionPresenter(QObject):
    """Camera slots, device claiming, saving and the manifest.

    Assigns each requested device to a slot through its backend's presenter,
    after claiming it so that no device is opened twice; forwards display and
    overlay settings to every slot; starts and stops saving on all cameras
    together; and writes the manifest.
    """

    frame_ready_signal: Signal = Signal(int, np.ndarray, str)
    roi_changed_signal: Signal = Signal(int, object)
    roi_enabled_signal: Signal = Signal(bool)

    def __init__(
        self,
        camera_view: CameraView,
        control_bar: AcquisitionSideBar,
        general_view: GeneralView,
        draw_view: DrawView,
        camera_extensions: list[Callable] | None = None,
    ) -> None:
        """Connect to the views; `camera_extensions` are backend factories."""
        super().__init__()

        self._presenter_registry: dict[CameraBackendType, type[CameraPresenter]] = {}

        self._registry: CameraRegistry = CameraRegistry()
        self._enumeration: EnumerationModel = EnumerationModel(self._registry)
        self._camera_view: CameraView = camera_view

        self._cameras: dict[CameraFrame, CameraSlot | None] = {}

        self._extensions: list[AcquisitionExtension] = [
            factory(self._cameras, self._presenter_registry, self._enumeration)
            for factory in (camera_extensions or [])
        ]

        self._current_mode: str = ""

        self._roi_enabled: bool = False
        self._roi_by_index: dict[int, tuple[float, float, float, float] | None] = {}

        self.save_path: str = " "
        self._is_saving: bool = False
        self.prefix: str = " "
        self._saturation_scale_value: int = 5

        self._start_time: float | None = None
        # Per camera index: (elapsed time, file name) awaiting the other camera,
        # and the file name written in the last manifest row.
        self._csv_row_buffer: dict[int, tuple[float, str]] = {}
        self._last_manifest_name: dict[int, str] = {}
        self._pending_snapshot: bool = False

        self._control_bar: AcquisitionSideBar = control_bar

        control_bar.save_begin_signal.connect(self._start_saving)
        control_bar.save_stop_signal.connect(self._stop_saving)

        control_bar.save_path_signal.connect(self._save_path_update)
        general_view.save_prefix_signal.connect(self._update_frame_prefix)

        control_bar.snapshot_signal.connect(self._save_snapshot)

        # Refresh re-runs the discovery of every backend, not only OpenCV's.
        control_bar.refresh_cameras_signal.connect(self._refresh_pickers)

        general_view.saturation_filter_on_signal.connect(
            self._on_saturation_filter_toggled
        )
        general_view.saturation_scaler_signal.connect(
            self._on_saturation_scaler_changed
        )
        general_view.saturation_threshold_changed.connect(
            self._on_saturation_threshold_changed
        )

        draw_view.grid_toggle_signal.connect(self._on_grid_toggled)
        draw_view.grid_changed_signal.connect(self._on_grid_changed)

        draw_view.subset_toggle_signal.connect(self._on_subset_toggled)
        draw_view.subset_changed_signal.connect(self._on_subset_changed)

        draw_view.target_toggle_signal.connect(self._on_target_toggled)
        draw_view.target_changed_signal.connect(self._on_target_changed)

        draw_view.draw_ROI_signal.connect(self._on_roi_setup_requested)
        draw_view.toggle_ROI_signal.connect(self._on_roi_analysis_toggled)
        draw_view.match_ROI_signal.connect(self._on_roi_match_requested)
        draw_view.clear_ROI_signal.connect(self._on_roi_teardown_requested)

        camera_view.mode_confirmed.connect(self._on_mode_confirmed)

        self.frame_ready_signal.connect(self._write_csv)

    def shutdown(self) -> None:
        """Stop saving and disconnect every camera before the application exits.

        Disconnecting drains each camera's writer queue, so every frame already
        captured reaches the disk.
        """
        if self._is_saving:
            self._stop_saving()
        for camera in filter(None, self._cameras.values()):
            logging.debug(f"Disconnecting camera: {camera.descriptor.display_name}")
            camera.presenter.disconnect_camera()
            self._registry.release(camera.descriptor)
        self._cameras.clear()

    def add_extension(self, factory: Callable) -> None:
        """Instantiate a camera backend from its factory (once each, at start-up)."""
        ext = factory(self._cameras, self._presenter_registry, self._enumeration)
        self._extensions.append(ext)

    # -------------------------------------------------------------------------
    # Mode setup
    # -------------------------------------------------------------------------

    def _on_mode_confirmed(self, mode: str) -> None:
        """Release every camera of the previous mode and create the slots for `mode`.

        Each device is released from the registry before the slots are cleared,
        so no claim outlives its camera.
        """
        logging.info(f"Mode change requested: {self._current_mode} -> {mode}")
        logging.debug(f"Tearing down {len(self._cameras)} camera frame(s)")
        for camera in filter(None, self._cameras.values()):
            logging.debug(f"Disconnecting camera: {camera.descriptor.display_name}")
            camera.presenter.disconnect_camera()
            self._registry.release(camera.descriptor)
        self._cameras.clear()
        self._roi_by_index.clear()
        logging.debug("Cameras cleared, setting up new mode")

        if mode == "mono":
            logging.info("Setting up MONO DIC mode")
            self._setup_mono()
        elif mode == "stereo":
            logging.info("Setting up STEREO DIC mode")
            self._setup_stereo()

        self._current_mode = mode
        logging.info(f"Mode setup complete: {mode}")
        self._refresh_pickers()

    def _setup_mono(self) -> None:
        """Register the single camera slot and connect its device picker."""
        logging.debug("Setting up MONO camera frame")
        frame = self._camera_view.mono
        if frame is None:
            logging.critical("MONO frame view is None")
            raise RuntimeError("CameraView.mono returned None")
        self._cameras[frame] = None
        frame.camera_requested.connect(
            lambda idx: self._on_camera_requested(frame, idx)
        )
        frame.roi_changed.connect(lambda rect, fi=0: self._on_roi_changed(fi, rect))
        logging.debug("MONO frame initialised and signal connected")

    def _setup_stereo(self) -> None:
        """Register the left and right slots; each also feeds its single-camera tab."""
        logging.debug("Setting up STEREO camera frames (left and right)")
        pairs = [  # side-by-side slot, single-camera tab showing the same camera, index
            (self._camera_view.stereo_left, self._camera_view.solo_left, 0),
            (self._camera_view.stereo_right, self._camera_view.solo_right, 1),
        ]

        for primary, mirror, index in pairs:
            if primary is None or mirror is None:
                logging.critical("STEREO frame view is None (primary or mirror)")
                raise RuntimeError("CameraView.stereo returned None")
            else:
                self._cameras[primary] = None

        for primary, mirror, index in pairs:
            primary.camera_requested.connect(
                lambda idx, f=primary, m=mirror, fi=index: self._on_camera_requested(
                    f, idx, mirrors=[m], index=fi
                )
            )
            primary.roi_changed.connect(
                lambda rect, fi=index: self._on_roi_changed(fi, rect)
            )
            mirror.roi_changed.connect(
                lambda rect, fi=index: self._on_roi_changed(fi, rect)
            )
        logging.debug("STEREO frames initialised with mirror setup")

    # --------------------------------------------------------------------------
    # Camera claiming
    # --------------------------------------------------------------------------

    def _on_camera_requested(
        self, frame: CameraFrame, id: str, mirrors=None, index: int = 0
    ) -> None:
        """Claim device `id` and connect it to `frame`, replacing any camera there.

        The device is ignored if it is no longer available or already claimed.
        """
        logging.info(f"Camera requested: {id}")
        available = self._enumeration.available_cameras()
        descriptor = next((d for d in available if d.id == id), None)
        if descriptor is None:
            logging.warning(f"Camera {id} not found in available cameras")
            return
        if not self._registry.claim(descriptor):
            logging.warning(
                f"Failed to claim camera {descriptor.display_name}: already in use"
            )
            return

        existing = self._cameras.get(frame)
        if existing is not None:
            logging.info(
                f"Switching camera on frame: {existing.descriptor.display_name} -> {descriptor.display_name}"
            )
            existing.presenter.frame_ready_signal.disconnect()
            existing.presenter.disconnect_camera()
            self._registry.release(existing.descriptor)
        self._cameras[frame] = None

        PresenterClass = self._presenter_registry[descriptor.backend]
        presenter = PresenterClass(frame, mirrors=mirrors)
        presenter.set_save_path(self.save_path)
        presenter.set_saturation_scaling(self._saturation_scale_value)
        presenter.connect_camera(descriptor)

        self._cameras[frame] = CameraSlot(
            presenter=presenter, descriptor=descriptor, index=index
        )
        self._cameras[frame].presenter.set_index(index)

        presenter.frame_ready_signal.connect(
            lambda idx, f, name: self.frame_ready_signal.emit(idx, f, name)
        )

        presenter.oversaturation_count.connect(
            lambda idx, count: self._on_saturation_count(idx, count)
        )

        logging.info(
            f"Camera acquisition started: {descriptor.display_name} (index={index})"
        )
        self._refresh_pickers()

    def _refresh_pickers(self) -> None:
        """Rediscover devices and list the unclaimed ones in every empty slot."""
        logging.debug("Refreshing camera picker views")
        available = self._enumeration.available_cameras()
        camera_list = [(d.id, d.display_name) for d in available]
        logging.debug(f"Available cameras for picker: {len(available)} total")
        for frame, entry in self._cameras.items():
            if entry is None:
                frame.set_available_cameras(camera_list)
                logging.debug("Updated empty frame picker")

    def _has_active_cameras(self) -> bool:
        """Whether at least one slot holds a connected camera."""
        return any(self._cameras.values())

    def _save_snapshot(self) -> None:
        """Save the latest frame of every camera and add one manifest row.

        Snapshots are numbered like recorded frames; outside a recording the
        manifest's elapsed time starts at the snapshot request.
        """
        if not self._has_active_cameras():
            logging.warning("Cannot take snapshot: no active cameras")
            return
        self._pending_snapshot = True
        if not self._is_saving:
            self._start_csv_timer()
        logging.info("Snapshot requested from all active cameras")
        for camera in filter(None, self._cameras.values()):
            camera.presenter.snapshot()

    def _start_saving(self) -> None:
        """Start recording on every connected camera and restart the manifest clock."""
        if not self._has_active_cameras():
            logging.warning("Cannot start saving: no active cameras")
            return
        self._is_saving = True
        self._start_csv_timer()
        self._control_bar.set_save_running(True)
        logging.info("Started saving frames from all active cameras")
        for camera in filter(None, self._cameras.values()):
            camera.presenter.start_saving()

    def _stop_saving(self) -> None:
        """Stop recording; frames already queued are still written."""
        self._is_saving = False
        logging.info("Stopping frame saving from all active cameras")
        self._stop_csv_timer()
        self._control_bar.set_save_running(False)
        for camera in filter(None, self._cameras.values()):
            camera.presenter.stop_saving()

    # --------------------------------------------------------------------------
    # Draw settings
    # --------------------------------------------------------------------------

    # --- Grid ---
    @Slot(bool)
    def _on_grid_toggled(self, enabled: bool) -> None:
        """Show or hide the grid in every slot."""
        logging.debug(f"Grid visibility toggled: {enabled}")
        for frame in self._cameras:
            frame.set_grid_visible(enabled)

    @staticmethod
    def _parse_positive_int(value: str, what: str) -> int | None:
        """Parse view text as a positive integer, or log a warning and return None.

        `what` names the setting in the warning.
        """
        try:
            number = int(value)
        except ValueError:
            logging.warning(f"Invalid {what}: {value!r} (must be an integer)")
            return None
        if number <= 0:
            logging.warning(f"Invalid {what}: {number} (must be > 0)")
            return None
        return number

    @Slot(str)
    def _on_grid_changed(self, value: str) -> None:
        """Apply a grid spacing (image pixels, as typed) to every slot."""
        size = self._parse_positive_int(value, "grid spacing")
        if size is None:
            return
        logging.debug(f"Grid spacing updated to {size} pixels")
        for frame in self._cameras:
            frame.set_grid_spacing(size)

    # --- Subset square ---
    @Slot(bool)
    def _on_subset_toggled(self, enabled: bool) -> None:
        for frame in self._cameras:
            frame.set_subset_visible(enabled)

    @Slot(str)
    def _on_subset_changed(self, value: str) -> None:
        size = self._parse_positive_int(value, "subset size")
        if size is None:
            return
        for frame in self._cameras:
            frame.set_subset_size(size)

    # --- Target ---
    @Slot(bool)
    def _on_target_toggled(self, enabled: bool) -> None:
        for frame in self._cameras:
            frame.set_target_visible(enabled)

    @Slot(str)
    def _on_target_changed(self, value: str) -> None:
        size = self._parse_positive_int(value, "target size")
        if size is None:
            return
        for frame in self._cameras:
            frame.set_target_size(size)

    # --- Region of interest (histogram) ---
    def _on_roi_setup_requested(self) -> None:
        for frame in self._cameras:
            frame.enable_roi_selection(True)

    def _on_roi_analysis_toggled(self, enabled: bool) -> None:
        self._roi_enabled = enabled
        self.roi_enabled_signal.emit(enabled)

    def _on_roi_changed(self, index: int, rect: object) -> None:
        self._roi_by_index[index] = rect
        self.roi_changed_signal.emit(index, rect)

    def _on_roi_match_requested(self) -> None:
        """Copy the left camera's region of interest to the right camera."""
        left_frame = None
        right_frame = None
        for frame, slot in self._cameras.items():
            if slot is None:
                continue
            if slot.index == 0:
                left_frame = frame
            elif slot.index == 1:
                right_frame = frame

        if left_frame is None or right_frame is None:
            logging.debug(f"Cannot match ROI, both cameras required: {self._cameras}")
            return

        self._roi_by_index[1] = self._roi_by_index[0]
        self.roi_changed_signal.emit(1, self._roi_by_index[1])
        right_frame.set_roi_selection(left_frame.get_roi_selection())

    def _on_roi_teardown_requested(self) -> None:
        for frame in self._cameras:
            frame.clear_roi_selection()
        self._roi_by_index = {0: None, 1: None}
        self.roi_changed_signal.emit(0, None)
        self.roi_changed_signal.emit(1, None)

    @Slot(str)
    def _update_frame_prefix(self, prefix: str) -> None:
        """Set the file-name prefix of images and manifest for every camera."""
        self.prefix = prefix
        for camera in filter(None, self._cameras.values()):
            camera.presenter.set_save_prefix(prefix)

    @Slot(str)
    def _save_path_update(self, path: str) -> None:
        """Set the save folder; all cameras share it and differ by camera index."""
        logging.info(f"Save path updated: {path}")
        self.save_path = path
        for camera in filter(None, self._cameras.values()):
            camera.presenter.set_save_path(path)

    @Slot(bool)
    def _on_saturation_filter_toggled(self, enabled: bool) -> None:
        for camera in filter(None, self._cameras.values()):
            camera.presenter.set_overlay_enabled(enabled)
        for frame in self._cameras:
            frame.set_saturation_bar_visible(enabled)

    @Slot(int)
    def _on_saturation_scaler_changed(self, value: int) -> None:
        self._saturation_scale_value = value
        for camera in filter(None, self._cameras.values()):
            camera.presenter.set_saturation_scaling(value)

    @Slot(int)
    def _on_saturation_threshold_changed(self, value: int) -> None:
        """Apply an overexposure threshold (grey level 0-255) to every camera."""
        if 0 <= value <= 255:
            for camera in filter(None, self._cameras.values()):
                camera.presenter.set_threshold_value(value)

    def _on_saturation_count(self, index: int, count: int) -> None:
        for frame, slot in self._cameras.items():
            if slot is not None and slot.index == index:
                frame.update_saturation_bar(count)
                break

    def _start_csv_timer(self) -> None:
        self._start_time = time.perf_counter()

    def _stop_csv_timer(self) -> None:
        self._start_time = None

    # Writing the manifest belongs in a model; moving it is post-thesis work.
    def _write_csv(self, index: int, frame: np.ndarray, frame_name: str) -> None:
        """Add a manifest row once every connected camera has delivered a new file.

        Called for every displayed frame. A row holds the wall-clock date and, per
        camera (`left` = index 0, `right` = index 1), the elapsed time since
        recording started and the saved file name.
        """
        if not self._is_saving and not self._pending_snapshot:
            return
        if self.save_path == " ":
            logging.debug("Please input a valid save directory.")
            self._pending_snapshot = False
            return
        if self.prefix == " ":
            self.prefix = "capture_data"

        camera = next(
            (c for c in filter(None, self._cameras.values()) if c.index == index),
            None,
        )
        if camera is None:
            return

        # Only a frame that brings a newly saved file counts: frames in flight when
        # saving or a snapshot started carry an older (or blank) name.
        if not frame_name.strip() or frame_name == self._last_manifest_name.get(index):
            return

        now = time.perf_counter()
        if self._start_time is None:
            self._start_time = now
        elapsed = now - self._start_time
        date: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        self._csv_row_buffer[index] = (elapsed, frame_name)

        # Wait until every connected camera has contributed to this row.
        active_indices = {c.index for c in filter(None, self._cameras.values())}
        if not active_indices.issubset(self._csv_row_buffer.keys()):
            return

        row = [date]
        header = ["date"]
        for i in sorted(self._csv_row_buffer):
            t, name = self._csv_row_buffer[i]
            label = "left" if i == 0 else "right"
            header += [f"{label}_frame_time", f"{label}_frame_name"]
            row += [f"{t:.4f}", name]

        output_csv = Path(self.save_path) / f"{self.prefix}.csv"
        write_header = not output_csv.exists()
        with open(output_csv, "a", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=";")
            if write_header:
                writer.writerow(header)
            writer.writerow(row)

        for i, (_, name) in self._csv_row_buffer.items():
            self._last_manifest_name[i] = name
        self._csv_row_buffer.clear()

        if self._pending_snapshot:
            self._pending_snapshot = False
