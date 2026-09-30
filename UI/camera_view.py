from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QStackedWidget,
    QTabWidget,
)
from PySide6.QtCore import Signal, Qt

from UI.camera_frame import CameraFrame


class CameraView(QWidget):
    """Central area: choice of acquisition mode, then the camera slots for that mode.

    Mono mode shows one `CameraFrame`. Two-camera (stereo) mode shows both
    cameras side by side in one tab and each camera in its own tab; the
    single-camera tabs mirror the side-by-side slots. Confirming a mode emits
    `mode_confirmed` with `"mono"` or `"stereo"`.
    """

    mode_confirmed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._selection_page = self._build_selection_page()
        self._camera_page = QWidget()  # replaced when a mode is confirmed

        self._stack.addWidget(self._selection_page)  # index 0
        self._stack.addWidget(self._camera_page)  # index 1

        self._stack.setCurrentIndex(0)

        # Set by _build_camera_page for the confirmed mode.
        self.stereo_left: CameraFrame | None = None
        self.stereo_right: CameraFrame | None = None
        self.solo_left: CameraFrame | None = None
        self.solo_right: CameraFrame | None = None
        self.mono: CameraFrame | None = None

        self._mode_list: QListWidget | None

    def _build_selection_page(self) -> QWidget:
        """Build the page listing the acquisition modes."""
        page = QWidget()
        layout = QVBoxLayout(page)

        label = QLabel("Select DIC Mode")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._mode_list = QListWidget()
        modes = [
            "MonoDIC",
            "StereoDIC",
        ]
        for mode in modes:
            self._mode_list.addItem(mode)

        self._mode_list.itemDoubleClicked.connect(self._on_mode_confirmed)
        confirm_btn = QPushButton("Confirm")
        confirm_btn.clicked.connect(self._on_mode_confirmed)

        layout.addWidget(label)
        layout.addWidget(self._mode_list)
        layout.addWidget(confirm_btn)
        return page

    def _on_mode_confirmed(self):
        """Build the camera page for the selected mode and announce the mode."""
        selected = self._mode_list.currentItem()
        if not selected:
            return

        mapping = {
            "MonoDIC": "mono",
            "StereoDIC": "stereo",
        }
        mode = mapping[selected.text()]
        self._build_camera_page(mode)
        self._stack.setCurrentIndex(1)
        self.mode_confirmed.emit(mode)

    def _build_camera_page(self, mode: str):
        """Replace the camera page with new slots for `mode` ("mono" or "stereo")."""
        # The previous page's slots belong to the previous mode and are discarded.
        self._stack.removeWidget(self._camera_page)
        self._camera_page.deleteLater()

        self._tabs = QTabWidget()

        if mode == "mono":
            self.mono = CameraFrame("Camera")
            self._tabs.addTab(self._wrap(self.mono), "Camera")

        elif mode == "stereo":
            self.stereo_left = CameraFrame("Left Camera")
            self.stereo_right = CameraFrame("Right Camera")
            self.solo_left = CameraFrame("Left Camera")
            self.solo_right = CameraFrame("Right Camera")

            self._tabs.addTab(
                self._build_stereo_tab(self.stereo_left, self.stereo_right), "Stereo"
            )
            self._tabs.addTab(self._wrap(self.solo_left), "Left")
            self._tabs.addTab(self._wrap(self.solo_right), "Right")

        self._camera_page = QWidget()
        layout = QVBoxLayout(self._camera_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        back_btn = QPushButton("← Back")
        back_btn.setFixedHeight(28)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))

        layout.addWidget(back_btn)
        layout.addWidget(self._tabs)

        self._stack.insertWidget(1, self._camera_page)

    def _build_stereo_tab(self, left: CameraFrame, right: CameraFrame) -> QWidget:
        """Place the two camera slots side by side."""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(left)
        layout.addWidget(right)
        return w

    def _wrap(self, frame: CameraFrame) -> QWidget:
        """Place one camera slot in a padded container."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(frame)
        return container
