from PySide6.QtGui import QImage, QPixmap, QColor, QPainter
from PySide6.QtCore import QObject, QTimer, Signal, Slot, QThread, Qt
import numpy as np
import cv2 as cv
from UI.utils.theme import THEME


class HistogramModel:
    """Per-channel intensity histogram of an 8-bit frame."""

    def __init__(self, bins: int = 256):
        """`bins` = 256 gives one bin per grey level."""
        self._bins = bins

    @property
    def bins(self) -> int:
        return self._bins

    @bins.setter
    def bins(self, value: int) -> None:
        self._bins = max(1, min(value, 256))

    def compute(self, frame: np.ndarray) -> np.ndarray:
        """Counts per bin, shape (channels, bins), of a (H, W) or (H, W, 3) frame."""
        if frame.ndim == 2:
            channels = [frame]
        else:
            channels = [frame[:, :, i] for i in range(frame.shape[2])]

        return np.array(
            [
                cv.calcHist([ch], [0], None, [self._bins], [0, 256]).flatten()
                for ch in channels
            ]
        )


class HistogramWorker(QObject):
    """Computes the histograms and renders them into an image, on its own thread.

    The latest histogram of each camera is kept, so in two-camera mode both are
    drawn on one canvas (camera 1 in the secondary colour).
    """

    DEFAULT_WIDTH: int = 256
    DEFAULT_HEIGHT: int = 200

    result_ready: Signal = Signal(QImage)

    _GRAY: QColor = QColor(THEME.histogram.gray_bar)
    _CHANNEL_COLORS: list[QColor] = [
        QColor(THEME.histogram.channel_bars[0]),
        QColor(THEME.histogram.channel_bars[1]),
        QColor(THEME.histogram.channel_bars[2]),
    ]
    _SECONDARY_COLOR: QColor = QColor(THEME.histogram.secondary_gray_bar)
    _BG: QColor = QColor(THEME.histogram.background)

    def __init__(self, model: HistogramModel) -> None:
        super().__init__()
        self._model = model
        self._w = self.DEFAULT_WIDTH
        self._h = self.DEFAULT_HEIGHT
        self._histograms: dict[int, np.ndarray] = {}

    @Slot(int, int)
    def set_size(self, w: int, h: int) -> None:
        """Set the size of the rendered image in pixels."""
        if w > 0 and h > 0:
            self._w = w
            self._h = h

    @Slot()
    def clear_histograms(self) -> None:
        self._histograms.clear()

    @Slot(np.ndarray, int)
    def process(self, frame: np.ndarray, camera_index: int) -> None:
        """Update the histogram of `camera_index` and emit a newly rendered image."""
        self._store_histogram(frame, camera_index)
        image = self._create_canvas()
        self._render_histograms(image)
        self.result_ready.emit(image)

    def _store_histogram(self, frame: np.ndarray, camera_index: int) -> None:
        hist = self._model.compute(frame)
        self._histograms[camera_index] = hist

    def _create_canvas(self) -> QImage:
        image = QImage(self._w, self._h, QImage.Format.Format_RGBA8888)
        image.fill(self._BG)
        return image

    def _render_histograms(self, image: QImage) -> None:
        """Draw every stored histogram, normalised to the highest bin of all of them."""
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)

        if not self._histograms:
            painter.end()
            return

        peak = max(hist.max() for hist in self._histograms.values())
        if peak <= 0:
            painter.end()
            return

        for cam_index in sorted(self._histograms.keys()):
            cam_hist = self._histograms[cam_index]
            normalized = cam_hist / peak
            bins = normalized.shape[1]

            if cam_index == 1:
                for channel in normalized:
                    painter.setBrush(self._SECONDARY_COLOR)
                    self._draw_channel_bars(painter, channel, bins)
            else:
                channel_colors = (
                    [self._GRAY] if normalized.shape[0] == 1 else self._CHANNEL_COLORS
                )
                for i, channel in enumerate(normalized):
                    painter.setBrush(channel_colors[i % len(channel_colors)])
                    self._draw_channel_bars(painter, channel, bins)

        painter.end()

    def _draw_channel_bars(
        self, painter: QPainter, channel: np.ndarray, bins: int
    ) -> None:
        """Draw one channel as bars; `channel` holds heights normalised to [0, 1]."""
        w, h = self._w, self._h

        for b in range(bins):
            # Integer edges make adjacent bars meet without gaps or overlaps.
            x0 = (b * w) // bins
            x1 = ((b + 1) * w) // bins
            bar_w = max(1, x1 - x0)
            bar_h = int(channel[b] * h)

            if bar_h > 0:
                # Qt's y axis points down, so bars grow from the bottom edge.
                painter.drawRect(x0, h - bar_h, bar_w, bar_h)


class HistogramPresenter(QObject):
    """Feeds frames to the histogram worker at a fixed rate and publishes the image.

    Only the latest frame of each camera is kept; every `update_interval_ms` it
    is sent to the worker thread, restricted to the region of interest if enabled.
    """

    histogram_ready = Signal(QPixmap)
    _request_compute = Signal(np.ndarray, int)
    _request_clear = Signal()

    def __init__(self, model: HistogramModel, update_interval_ms: int = 100) -> None:
        super().__init__()
        self._pending: dict[int, np.ndarray] = {}
        self._size = (256, 200)
        self._suppress_results = False
        self._roi_enabled = False
        self._roi_by_index: dict[int, tuple[float, float, float, float] | None] = {}

        self._worker = HistogramWorker(model)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._request_compute.connect(self._worker.process)
        self._request_clear.connect(self._worker.clear_histograms)
        # Cross-thread signal: _on_result runs on the main thread.
        self._worker.result_ready.connect(self._on_result)

        self._timer = QTimer()
        self._timer.setInterval(update_interval_ms)
        self._timer.timeout.connect(self._update)

    def set_size(self, w: int, h: int) -> None:
        if w > 0 and h > 0:
            self._size = (w, h)
            self._worker.set_size(w, h)

    def on_frame(self, camera_index: int, frame: np.ndarray) -> None:
        self._suppress_results = False
        self._pending[camera_index] = frame

    def set_roi_enabled(self, enabled: bool) -> None:
        self._roi_enabled = enabled

    def set_roi(self, camera_index: int, roi_norm: object) -> None:
        if roi_norm is None:
            self._roi_by_index.pop(camera_index, None)
            return
        self._roi_by_index[camera_index] = roi_norm

    def _apply_roi(self, frame: np.ndarray, camera_index: int) -> np.ndarray:
        """Crop to the camera's normalised region of interest, if enabled and valid."""
        if not self._roi_enabled:
            return frame
        roi = self._roi_by_index.get(camera_index)
        if roi is None or not isinstance(roi, (tuple, list)) or len(roi) != 4:
            return frame

        x0, y0, x1, y1 = roi
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return frame

        x0_px = int(round(x0 * w))
        x1_px = int(round(x1 * w))
        y0_px = int(round(y0 * h))
        y1_px = int(round(y1 * h))

        x0_px, x1_px = sorted((max(0, min(x0_px, w)), max(0, min(x1_px, w))))
        y0_px, y1_px = sorted((max(0, min(y0_px, h)), max(0, min(y1_px, h))))
        if x1_px - x0_px < 1 or y1_px - y0_px < 1:
            return frame

        return frame[y0_px:y1_px, x0_px:x1_px]

    def _update(self) -> None:
        if not self._pending:
            return
        pending, self._pending = self._pending, {}
        for cam_index, frame in pending.items():
            roi_frame = self._apply_roi(frame, cam_index)
            self._request_compute.emit(roi_frame, cam_index)

    @Slot(QImage)
    def _on_result(self, image: QImage) -> None:
        if self._suppress_results:
            return
        # QPixmap may only be created on the main thread, hence here.
        self.histogram_ready.emit(QPixmap.fromImage(image))

    def start(self) -> None:
        self._thread.start()
        self._timer.start()

    def clear(self) -> None:
        """Discard pending frames and stored histograms and show an empty canvas."""
        self._suppress_results = True
        self._pending.clear()
        self._request_clear.emit()
        w, h = self._size
        if w <= 0 or h <= 0:
            return
        pixmap = QPixmap(w, h)
        pixmap.fill(QColor(THEME.histogram.background))
        self.histogram_ready.emit(pixmap)

    def stop(self) -> None:
        self.clear()
        self._timer.stop()
        self._thread.quit()
        self._thread.wait()
