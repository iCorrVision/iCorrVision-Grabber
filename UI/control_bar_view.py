from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QStyle,
)
from PySide6.QtCore import Signal

from UI.utils.view_utils import make_button, ask_export_folder


class AcquisitionSideBar(QWidget):
    """Icon buttons for record/stop, snapshot, device refresh and the save folder.

    Each button only emits a signal; the record button changes icon and signal
    while a recording runs (see `set_save_running`).
    """

    save_begin_signal: Signal = Signal()
    save_stop_signal: Signal = Signal()
    save_path_signal: Signal = Signal(str)

    snapshot_signal: Signal = Signal()

    refresh_cameras_signal: Signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.addSpacing(25)

        self.save_button: QPushButton = make_button(
            self,
            QStyle.StandardPixmap.SP_DialogApplyButton,
            self.save_begin_signal,
            layout,
        )

        self.snapshot_button: QPushButton = make_button(
            self,
            QStyle.StandardPixmap.SP_DialogHelpButton,
            self.snapshot_signal,
            layout,
        )

        self.refresh_cameras_button: QPushButton = make_button(
            self,
            QStyle.StandardPixmap.SP_BrowserReload,
            self.refresh_cameras_signal,
            layout,
        )

        self.set_save_location: QPushButton = make_button(
            self,
            QStyle.StandardPixmap.SP_DirIcon,
            lambda: ask_export_folder(self, self.save_path_signal.emit),
            layout,
        )

        layout.addStretch(1)

    def set_save_running(self, saving: bool) -> None:
        """Make the record button stop (`saving` True) or start a recording."""
        icon_enum = (
            QStyle.StandardPixmap.SP_DialogCancelButton
            if saving
            else QStyle.StandardPixmap.SP_DialogApplyButton
        )
        signal = self.save_stop_signal if saving else self.save_begin_signal

        self.save_button.setIcon(self.save_button.style().standardIcon(icon_enum))
        self.save_button.clicked.disconnect()
        self.save_button.clicked.connect(signal)
