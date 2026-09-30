from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
    QVBoxLayout,
)
from UI.utils.view_utils import make_labeled_toggle


class OpencvView(QWidget):
    """Settings panel of the OpenCV backend: polling on/off, polling rate, greyscale.

    The rate is emitted as the text typed; the extension validates it.
    """

    toggle_poll_signal = Signal(bool)
    grayscale_on_signal = Signal(bool)
    fps_changed_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.capture_button = make_labeled_toggle(
            self,
            label_on="stop frame polling",
            label_off="start frame polling",
            initial=False,
            on_toggle=self.toggle_poll_signal,
        )
        layout.addWidget(self.capture_button)

        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("FPS"))
        fps_input = QLineEdit()
        fps_input.setPlaceholderText("please enter integer FPS value (default 30)")
        fps_input.returnPressed.connect(
            lambda: self.fps_changed_signal.emit(fps_input.text())
        )
        fps_layout.addWidget(fps_input)
        layout.addLayout(fps_layout)

        self.grayscale_button = make_labeled_toggle(
            self,
            label_on="greyscale off",
            label_off="greyscale on",
            initial=False,
            on_toggle=self.grayscale_on_signal,
        )
        layout.addWidget(self.grayscale_button)
