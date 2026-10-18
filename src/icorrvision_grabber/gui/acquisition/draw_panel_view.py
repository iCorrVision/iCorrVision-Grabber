from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from UI.utils.view_utils import make_labeled_toggle


class DrawView(QWidget):
    """Settings for the framing aids drawn over the live view.

    Covers the grid (spacing), the subset-sized square and the central target
    (size), and the region of interest used for the histogram (draw, copy from
    the left to the right camera, clear, restrict the histogram to it). Sizes
    are emitted as the text typed; the presenter validates them.
    """

    grid_toggle_signal: Signal = Signal(bool)
    grid_changed_signal: Signal = Signal(str)

    subset_toggle_signal: Signal = Signal(bool)
    subset_changed_signal: Signal = Signal(str)

    target_toggle_signal: Signal = Signal(bool)
    target_changed_signal: Signal = Signal(str)

    toggle_ROI_signal: Signal = Signal(bool)
    draw_ROI_signal: Signal = Signal()
    match_ROI_signal: Signal = Signal()
    clear_ROI_signal: Signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addLayout(self._make_grid_layout())
        layout.addLayout(self._make_subset_layout())
        layout.addLayout(self._make_target_layout())
        layout.addLayout(self._make_ROI_settings())

    def _make_grid_layout(self) -> QHBoxLayout:
        layout = QVBoxLayout()

        grid_toggle = make_labeled_toggle(
            self,
            label_on="hide grid",
            label_off="show grid",
            initial=False,
            on_toggle=self.grid_toggle_signal,
        )

        layout.addWidget(grid_toggle)

        grid_size_layout = QHBoxLayout()
        grid_size_layout.addWidget(QLabel("input grid size: "))

        _grid_size_input = QLineEdit()
        _grid_size_input.returnPressed.connect(
            lambda: self.grid_changed_signal.emit(_grid_size_input.text())
        )
        grid_size_layout.addWidget(_grid_size_input)
        layout.addLayout(grid_size_layout)

        mega_layout = QHBoxLayout()
        mega_layout.addLayout(layout)
        return mega_layout

    def _make_subset_layout(self) -> QHBoxLayout:
        layout = QVBoxLayout()

        subset_toggle = make_labeled_toggle(
            self,
            label_on="hide subset",
            label_off="show subset",
            initial=False,
            on_toggle=self.subset_toggle_signal,
        )

        layout.addWidget(subset_toggle)

        subset_size_layout = QHBoxLayout()
        subset_size_layout.addWidget(QLabel("input subset size: "))

        _subset_size_input = QLineEdit()
        _subset_size_input.returnPressed.connect(
            lambda: self.subset_changed_signal.emit(_subset_size_input.text())
        )
        subset_size_layout.addWidget(_subset_size_input)
        layout.addLayout(subset_size_layout)

        mega_layout = QHBoxLayout()
        mega_layout.addLayout(layout)
        return mega_layout

    def _make_target_layout(self) -> QHBoxLayout:
        layout = QVBoxLayout()

        target_toggle = make_labeled_toggle(
            self,
            label_on="hide target",
            label_off="show target",
            initial=False,
            on_toggle=self.target_toggle_signal,
        )

        layout.addWidget(target_toggle)

        target_size_layout = QHBoxLayout()
        target_size_layout.addWidget(QLabel("input target size: "))

        _target_size_input = QLineEdit()
        _target_size_input.returnPressed.connect(
            lambda: self.target_changed_signal.emit(_target_size_input.text())
        )
        target_size_layout.addWidget(_target_size_input)
        layout.addLayout(target_size_layout)

        mega_layout = QHBoxLayout()
        mega_layout.addLayout(layout)
        return mega_layout

    def _make_ROI_settings(self) -> QVBoxLayout:
        layout = QVBoxLayout()

        button_layout = QHBoxLayout()

        draw_button = QPushButton("Draw ROI")
        draw_button.clicked.connect(lambda: self.draw_ROI_signal.emit())
        button_layout.addWidget(draw_button)

        match_button = QPushButton("Match ROI")
        match_button.clicked.connect(lambda: self.match_ROI_signal.emit())
        button_layout.addWidget(match_button)

        clear_button = QPushButton("Clear ROI")
        clear_button.clicked.connect(lambda: self.clear_ROI_signal.emit())
        button_layout.addWidget(clear_button)

        layout.addLayout(button_layout)

        roi_analysis_toggle = make_labeled_toggle(
            self,
            label_on="disable ROI histogram analysis",
            label_off="enable ROI histogram analysis",
            initial=False,
            on_toggle=self.toggle_ROI_signal,
        )
        layout.addWidget(roi_analysis_toggle)

        return layout
