from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QComboBox,
)


class ModePanelView(QWidget):
    """Settings panels (General, Draw, one per camera backend) behind a selector."""

    def __init__(self, modes: dict[str, type[QWidget]], parent=None):
        """Add one panel per entry of `modes`, a mapping of name to view class."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._mode_selector = QComboBox()
        self._stack = QStackedWidget()
        self._views: dict[str, QWidget] = {}

        for panel_name, panel_ui in modes.items():
            instance = panel_ui()
            self._views[panel_name] = instance
            self._mode_selector.addItem(panel_name)
            self._stack.addWidget(instance)

        self._mode_selector.currentIndexChanged.connect(self._stack.setCurrentIndex)

        layout.addWidget(self._mode_selector)
        layout.addWidget(self._stack)
        layout.addStretch()

    def append_panel(self, panel_name: str, panel_ui: type[QWidget]) -> None:
        """Add a camera backend's panel after start-up."""
        instance = panel_ui()
        self._views[panel_name] = instance
        self._mode_selector.addItem(panel_name)
        self._stack.addWidget(instance)

    def get_view(self, name: str) -> QWidget:
        """Return the view of the named mode."""
        return self._views[name]
