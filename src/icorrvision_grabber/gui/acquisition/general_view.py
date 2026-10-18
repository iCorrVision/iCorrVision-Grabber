from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
)
from UI.utils.view_utils import make_labeled_toggle


class GeneralView(QWidget):
    """File-name prefix and overexposure overlay settings.

    The overlay marks pixels above the threshold (grey level 0-255). Downscaling
    (0-10) shrinks the frame by 10 % per step, to at least 10 %, before the overlay
    is computed; the overexposed-pixel count then refers to the smaller frame.
    Neither setting affects the recorded images.
    """

    save_prefix_signal: Signal = Signal(str)

    saturation_filter_on_signal: Signal = Signal(bool)
    saturation_scaler_signal: Signal = Signal(int)
    saturation_threshold_changed: Signal = Signal(int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addLayout(self._make_prefix_input())

        layout.addWidget(
            make_labeled_toggle(
                self,
                label_on="disable overexposure overlay",
                label_off="enable overexposure overlay",
                initial=False,
                on_toggle=self.saturation_filter_on_signal,
            )
        )
        layout.addLayout(self._make_saturation_scalling_slider())
        layout.addLayout(self._make_saturation_threshold_slider())

    def _make_prefix_input(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        label = QLabel("Prefix")
        layout.addWidget(label)

        prefix_input = QLineEdit()
        prefix_input.setPlaceholderText("input frame prefix")
        prefix_input.returnPressed.connect(
            lambda: self.save_prefix_signal.emit(prefix_input.text())
        )

        layout.addWidget(prefix_input)

        return layout

    def _make_saturation_threshold_slider(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        label = QLabel("Overexposure threshold")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(255)
        slider.setValue(255)

        slider_label = QLabel("255")
        layout.addWidget(slider_label)

        def on_value_changed(value: int) -> None:
            self.saturation_threshold_changed.emit(value)
            slider_label.setText(str(value))

        slider.valueChanged.connect(on_value_changed)

        layout.addWidget(slider)

        return layout

    def _make_saturation_scalling_slider(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        label = QLabel("Overlay downscaling")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(10)
        slider.setValue(5)

        scaler_label = QLabel("5")
        layout.addWidget(scaler_label)

        def on_value_changed(value: int) -> None:
            self.saturation_scaler_signal.emit(value)
            scaler_label.setText(str(value))

        slider.valueChanged.connect(on_value_changed)

        layout.addWidget(slider)

        return layout
