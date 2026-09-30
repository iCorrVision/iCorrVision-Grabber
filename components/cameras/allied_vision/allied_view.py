from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
    QVBoxLayout,
    QLabel,
    QCheckBox,
)

from UI.utils.view_utils import ask_load_file, ask_export_folder


class AlliedOptionsView(QWidget):
    """Settings panel of the Allied Vision (Vimba X) backend.

    Frame-rate control (enable, rate in fps), exposure time (µs) and the camera
    settings as GenICam XML: "generate" saves `<serial>.xml` per camera into a
    chosen folder, "load" applies a file to the camera with that serial number.
    Numbers are emitted as the text typed; the extension validates them.
    """

    exposure_time_signal: Signal = Signal(str)

    frame_rate_toggle_signal: Signal = Signal(bool)
    frame_rate_signal: Signal = Signal(str)

    path_xml_signal: Signal = Signal(str)
    load_xml_signal: Signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        layout.addLayout(self._make_frame_rate_edit())
        layout.addLayout(self._make_exposure_edit())
        layout.addLayout(self._make_xml_buttons())

    def _make_exposure_edit(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        label = QLabel("Exposure time")
        layout.addWidget(label)

        line_edit = QLineEdit()
        layout.addWidget(line_edit)
        line_edit.returnPressed.connect(
            lambda: self.exposure_time_signal.emit(line_edit.text())
        )

        return layout

    def _make_frame_rate_edit(self) -> QVBoxLayout:
        main_layout = QVBoxLayout()

        toggle_layout = QHBoxLayout()
        toggle_label = QLabel("Toggle custom frame rate")
        toggle = QCheckBox()
        toggle.toggled.connect(
            lambda enabled: self.frame_rate_toggle_signal.emit(enabled)
        )
        toggle_layout.addWidget(toggle_label)
        toggle_layout.addWidget(toggle)
        main_layout.addLayout(toggle_layout)

        value_layout = QHBoxLayout()
        value_label = QLabel("Frame Rate")
        line_edit = QLineEdit()
        line_edit.returnPressed.connect(
            lambda: self.frame_rate_signal.emit(line_edit.text())
        )
        value_layout.addWidget(value_label)
        value_layout.addWidget(line_edit)
        main_layout.addLayout(value_layout)

        return main_layout

    def _make_xml_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        gen_button = QPushButton("generate XML config")
        gen_button.clicked.connect(  # asks for the folder to write the XML files to
            lambda: ask_export_folder(self, self.path_xml_signal.emit)
        )
        layout.addWidget(gen_button)

        load_button = QPushButton("Load XML config")
        load_button.clicked.connect(
            lambda: ask_load_file(self, self.load_xml_signal.emit, "xml(*.xml)")
        )
        layout.addWidget(load_button)

        return layout
