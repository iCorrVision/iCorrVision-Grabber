from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTabWidget,
)

from UI.console_view import ConsoleLogView
from UI.histogram_view import HistogramView


class BottomPanelView(QWidget):
    """Bottom panel holding the console log and histogram tabs."""

    def __init__(self, parent=None):
        """Build the tab widget and its console and histogram tabs."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()

        self.console = ConsoleLogView()
        self.histogram = HistogramView()

        self._tabs.addTab(self.console, "Console Log")
        self._tabs.addTab(self.histogram, "Histogram")

        layout.addWidget(self._tabs)
