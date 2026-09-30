from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QSplitter,
    QSizePolicy,
)
from UI.camera_view import CameraView
from UI.mode_panel_view import ModePanelView
from UI.bottom_panel_view import BottomPanelView
from UI.control_bar_view import AcquisitionSideBar

from UI.draw_panel_view import DrawView
from UI.general_view import GeneralView


class MainView(QMainWindow):
    """Main window: control bar, camera area and settings panels above the console.

    Holds no application logic (passive view).
    """

    modes: dict[str, type[QWidget]] = {
        "General": GeneralView,
        "Draw": DrawView,
    }

    cameras: CameraView
    _mode_panel: ModePanelView
    bottom_panel: BottomPanelView
    acquisition_control_bar: AcquisitionSideBar

    def __init__(self, parent=None):
        """Build the main window and its panels."""
        super().__init__(parent)
        self.setWindowTitle("iCorrVision 2.0 Grabber")

        main_layout = QSplitter(Qt.Orientation.Vertical)
        main_layout.setContentsMargins(0, 0, 0, 0)

        top_splitter = QSplitter()
        top_splitter.setSizes([20, 800, 200])

        self.acquisition_control_bar = AcquisitionSideBar(self)
        min_width = self.acquisition_control_bar.minimumSizeHint().width()
        self.acquisition_control_bar.setFixedWidth(min_width)
        self.acquisition_control_bar.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        top_splitter.addWidget(self.acquisition_control_bar)

        self.cameras = CameraView()
        top_splitter.addWidget(self.cameras)  # CameraView owns its own tabs/stack

        self._mode_panel = ModePanelView(modes=self.modes)
        top_splitter.addWidget(self._mode_panel)

        main_layout.addWidget(top_splitter)
        main_layout.setStretchFactor(0, 3)

        self.bottom_panel = BottomPanelView()
        main_layout.addWidget(self.bottom_panel)
        main_layout.setStretchFactor(0, 1)

        self.setCentralWidget(main_layout)

    def get_mode_view(self, name: str) -> QWidget:
        """Return the settings panel named `name` ("General", "Draw", a backend)."""
        return self._mode_panel.get_view(name)

    def append_camera_panel(self, panel_name: str, panel_ui: type[QWidget]) -> None:
        """Add a camera backend's settings panel under `panel_name`."""
        self.modes[panel_name] = panel_ui
        self._mode_panel.append_panel(panel_name, panel_ui)
