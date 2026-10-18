import logging
import numpy as np
from PySide6.QtWidgets import QWidget

from components.acquisition_presenter import AcquisitionPresenter
from components.cameras.template.acquisition_extender import AcquisitionExtension
from components.console_presenter import ConsolePresenter
from components.histogram_presenter import HistogramPresenter

from components.histogram_presenter import HistogramModel


class MainPresenter:
    """Creates the presenters and connects them to their views and to each other.

    Frames from the acquisition presenter feed the histogram, and the region
    of interest drawn in a camera slot restricts it.
    """

    def __init__(self, view) -> None:

        self.camera_extensions = []

        kwargs = {
            "camera_view": view.cameras,
            "control_bar": view.acquisition_control_bar,
            "general_view": view.get_mode_view("General"),
            "draw_view": view.get_mode_view("Draw"),
            "camera_extensions": self.camera_extensions,
        }

        self._acquisition_presenter = AcquisitionPresenter(**kwargs)
        logging.debug("AcquisitionPresenter initialised")

        self._console_presenter = ConsolePresenter(view.bottom_panel.console)
        logging.debug("ConsolePresenter initialised")

        self._hist_presenter = HistogramPresenter(HistogramModel())

        self._acquisition_presenter.frame_ready_signal.connect(self._dispatch_histogram)
        self._acquisition_presenter.roi_changed_signal.connect(
            self._hist_presenter.set_roi
        )
        self._acquisition_presenter.roi_enabled_signal.connect(
            self._hist_presenter.set_roi_enabled
        )

        self._hist_presenter.histogram_ready.connect(
            view.bottom_panel.histogram.update_display
        )

        view.cameras.mode_confirmed.connect(self._on_mode_confirmed)

        # The histogram is rendered at the size of its view.
        view.bottom_panel.histogram.size_changed.connect(self._hist_presenter.set_size)

        self._hist_presenter.start()

    def shutdown(self) -> None:
        """Release cameras and background threads before the application exits."""
        self._acquisition_presenter.shutdown()
        self._hist_presenter.stop()

    def _dispatch_histogram(
        self, idx: int, frame: np.ndarray, _frame_name: str
    ) -> None:
        self._hist_presenter.on_frame(idx, frame)

    def _on_mode_confirmed(self, _mode: str) -> None:
        """Restart the histogram so no histogram of the previous mode remains."""
        self._hist_presenter.stop()
        self._hist_presenter.start()

    def append_camera_extension(
        self, panel_ui: type[QWidget], camera_extension: AcquisitionExtension
    ) -> None:
        """Register a backend extension; `panel_ui` is its settings panel instance."""
        logging.info(f"Registering camera extension: {camera_extension.__name__}")
        factory = lambda cams, pr, enum: camera_extension(cams, pr, enum, panel_ui)
        self.camera_extensions.append(factory)
        self._acquisition_presenter.add_extension(factory)
