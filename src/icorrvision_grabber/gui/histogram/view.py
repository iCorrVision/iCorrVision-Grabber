from PySide6.QtWidgets import QLabel, QSizePolicy
from PySide6.QtCore import Slot, Qt, Signal, QSize
from PySide6.QtGui import QPixmap


class HistogramView(QLabel):
    """Displays the histogram image rendered by `HistogramPresenter`.

    The presenter renders at the widget's size, so every change of the drawable
    area is reported through `size_changed` (width, height).
    """

    size_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContentsMargins(1, 1, 1, 1)
        self.setScaledContents(True)  # the pixmap follows the label, not the reverse
        self._last_size = (0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        w, h = rect.width(), rect.height()
        # Qt emits resize events that do not change the drawable area.
        if (w, h) != self._last_size and w > 0 and h > 0:
            self._last_size = (w, h)
            self.size_changed.emit(w, h)

    def sizeHint(self) -> QSize:
        # A minimal hint keeps the rendered pixmap from enlarging the layout.
        return QSize(1, 1)

    def minimumSizeHint(self) -> QSize:
        return QSize(1, 1)

    @Slot(QPixmap)
    def update_display(self, pixmap: QPixmap) -> None:
        self.setPixmap(pixmap)
