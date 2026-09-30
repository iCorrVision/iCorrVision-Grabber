from PySide6.QtWidgets import (
    QWidget,
    QSizePolicy,
    QFrame,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QStackedWidget,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap

from UI.frame_display import FrameDisplay


class CameraFrame(QFrame):
    """One camera slot: a device picker that becomes the live view once frames arrive.

    Selecting a device emits `camera_requested` with its identifier; the
    presenter decides whether the device can be opened. The first frame passed
    to `update_frame` switches the slot to the live view. Overlay settings
    are forwarded to the embedded `FrameDisplay`.
    """

    camera_requested = Signal(str)
    roi_changed = Signal(object)

    def __init__(self, label: str, parent=None):
        """`label` names the slot in the picker, e.g. "Left Camera"."""
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)

        self._available_indices: list[tuple[str, str]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()

        root.addWidget(self._stack)

        # --- Page 0: picker ---
        picker = QWidget()
        picker_layout = QVBoxLayout(picker)
        picker_layout.addWidget(QLabel(f"{label} — select a camera:"))

        self._camera_list = QListWidget()
        picker_layout.addWidget(self._camera_list)
        self._camera_list.itemDoubleClicked.connect(self._on_connect_clicked)

        self._connect_button = QPushButton("Connect")
        self._connect_button.clicked.connect(self._on_connect_clicked)
        picker_layout.addWidget(self._connect_button)

        self._stack.addWidget(picker)  # index 0

        # --- Page 1: live feed ---
        feed_page = QWidget()
        feed_layout = QVBoxLayout(feed_page)
        feed_layout.setContentsMargins(0, 0, 0, 0)
        feed_layout.setSpacing(0)

        self._saturation_bar = QLabel("Overexposed: 0 px")
        self._saturation_bar.setMaximumHeight(20)
        self._saturation_bar.setVisible(False)
        feed_layout.addWidget(self._saturation_bar)

        self.display = FrameDisplay()
        feed_layout.addWidget(self.display)
        self._stack.addWidget(feed_page)

        self.display.roi_changed.connect(self.roi_changed)

        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Device picker
    # ------------------------------------------------------------------
    def set_available_cameras(self, cameras: list[tuple[str, str]]) -> None:
        """Show the unclaimed devices, given as (identifier, display name) pairs."""
        self._available_ids = [id for id, _ in cameras]
        self._camera_list.clear()
        for _, name in cameras:
            self._camera_list.addItem(name)
        if self._camera_list.count():
            self._camera_list.setCurrentRow(0)
        self._stack.setCurrentIndex(0)

    def update_frame(self, frame: QPixmap) -> None:
        """Show `frame` in the live view (switching to it if needed).

        The pixmap is kept at full resolution; zoom and pan are applied by
        `FrameDisplay` when painting.
        """
        self._stack.setCurrentIndex(1)
        self.display.set_pixmap(frame)

    def _on_connect_clicked(self) -> None:
        row = self._camera_list.currentRow()
        if row < 0 or row >= len(self._available_ids):
            return
        self.camera_requested.emit(self._available_ids[row])

    # --------------------------------------------------------------------------
    # Overlays
    # --------------------------------------------------------------------------

    # --- Grid ---
    def set_grid_visible(self, visible: bool) -> None:
        """Show or hide the grid overlay."""
        self.display.set_grid_visible(visible)

    def set_grid_spacing(self, spacing_px: int) -> None:
        """Set the grid spacing in image pixels."""
        self.display.set_grid_spacing(spacing_px)

    # --- Subset ---
    def set_subset_visible(self, visible: bool) -> None:
        self.display.set_subset_visible(visible)

    def set_subset_size(self, spacing_px: int) -> None:
        self.display.set_subset_size(spacing_px)

    # --- Target ---
    def set_target_visible(self, visible: bool) -> None:
        self.display.set_target_visible(visible)

    def set_target_size(self, spacing_px: int) -> None:
        self.display.set_target_size(spacing_px)

    # --- ROI ---
    def enable_roi_selection(self, enabled: bool) -> None:
        self.display.enable_roi_selection(enabled)

    def clear_roi_selection(self) -> None:
        self.display.clear_roi_rect()

    def get_roi_selection(self) -> tuple[float, float, float, float] | None:
        return self.display.current_roi_rect()

    def set_roi_selection(self, rect: tuple[float, float, float, float]) -> None:
        self.display.set_roi_rect(rect)

    def reset_view(self) -> None:
        """Fit the image to the widget and remove any pan."""
        self.display.reset_view()

    def update_saturation_bar(self, count: int) -> None:
        self._saturation_bar.setText(f"Overexposed: {count} px")

    def set_saturation_bar_visible(self, visible: bool) -> None:
        self._saturation_bar.setVisible(visible)
