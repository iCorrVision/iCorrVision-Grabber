from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import QPointF, Signal, Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QBrush


class FrameDisplay(QWidget):
    """Image view with zoom and pan, and the framing aids drawn over it.

    Mouse-wheel zoom within limits, click-drag panning, double-click to reset
    the view; the aspect ratio is preserved and the image centred. The grid,
    subset square, target and region of interest are drawn in image coordinates,
    so they follow zoom and pan; a region of interest drawn with the mouse is
    emitted through `roi_changed` as normalised (x0, y0, x1, y1).
    """

    roi_changed = Signal(object)

    _ZOOM_MIN: float = 1.0
    MAX_PX_PER_IMAGE_PX = 16

    _GRID_COLOR = QColor(0, 255, 0, 160)
    _TARGET_COLOR = QColor(255, 120, 120, 160)
    _SUBSET_COLOR_LINE = QColor(120, 255, 120, 220)
    _SUBSET_COLOR_FILL = QColor(120, 255, 120, 100)
    _ROI_COLOR = QColor(0, 0, 255, 200)

    def __init__(self, parent=None):
        """Start with no image, zoom 1 and no pan."""
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._pixmap: QPixmap | None = None
        self._zoom: float = 1.0
        self._pan: QPointF = QPointF(0.0, 0.0)

        self._show_grid: bool = False
        self._grid_spacing: int = 50

        self._show_subset: bool = False
        self._subset_size: int = 30
        self._subset_pos_norm: tuple[float, float] = (0.5, 0.5)
        self._subset_dragging: bool = False
        self._subset_drag_offset: tuple[float, float] = (0.0, 0.0)

        self._show_target: bool = False
        self._target_size: int = 40

        self._roi_select_enabled: bool = False
        self._roi_select_one_shot: bool = True
        self._roi_drag_start: tuple[float, float] | None = None
        self._roi_drag_end: tuple[float, float] | None = None
        self._roi_rect_norm: tuple[float, float, float, float] | None = None

        self._drag_origin: QPointF | None = None  # set on mouse click
        self._pan_at_drag: QPointF = QPointF(0.0, 0.0)

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Show `pixmap`, keeping the current zoom and pan."""
        self._pixmap = pixmap
        self.update()

    def set_grid_visible(self, visible: bool) -> None:
        """Show or hide the grid overlay."""
        self._show_grid = visible
        self.update()

    def set_subset_visible(self, visible: bool) -> None:
        self._show_subset = visible
        self.update()

    def set_subset_size(self, value: int) -> None:
        self._subset_size = value
        self.update()

    def set_target_visible(self, visible: bool) -> None:
        self._show_target = visible
        self.update()

    def set_target_size(self, value: int) -> None:
        self._target_size = value
        self.update()

    def set_grid_spacing(self, spacing_px: int) -> None:
        """Set the grid spacing in image pixels (at least 4)."""
        self._grid_spacing = max(4, spacing_px)
        self.update()

    def enable_roi_selection(self, enabled: bool, one_shot: bool = True) -> None:
        self._roi_select_enabled = enabled
        self._roi_select_one_shot = one_shot
        self._roi_drag_start = None
        self._roi_drag_end = None
        self.update()

    def reset_view(self) -> None:
        """Reset zoom and pan so the image fits the widget."""
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.update()

    def _widget_to_norm(self, pos: QPointF) -> tuple[float, float] | None:
        """Map a widget position to image coordinates normalised to [0, 1] (clamped)."""
        rect = self._render_rect()
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return None
        x = (pos.x() - rect.x()) / rect.width()
        y = (pos.y() - rect.y()) / rect.height()
        x = min(max(x, 0.0), 1.0)
        y = min(max(y, 0.0), 1.0)
        return (x, y)

    @staticmethod
    def _normalized_rect(
        start: tuple[float, float], end: tuple[float, float]
    ) -> tuple[float, float, float, float] | None:
        """Order two corners as (x0, y0, x1, y1); None for a rectangle of zero area."""
        x0, y0 = start
        x1, y1 = end
        if x0 == x1 or y0 == y1:
            return None
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        return (x0, y0, x1, y1)

    def current_roi_rect(self) -> tuple[float, float, float, float] | None:
        """The region of interest, including one still being dragged, or None."""
        if self._roi_drag_start is not None and self._roi_drag_end is not None:
            return self._normalized_rect(self._roi_drag_start, self._roi_drag_end)
        return self._roi_rect_norm

    def clear_roi_rect(self) -> None:
        if self._roi_rect_norm is not None:
            self._roi_rect_norm = None

    def set_roi_rect(self, rect: tuple[float, float, float, float]) -> None:
        self._roi_rect_norm = rect
        self.roi_changed.emit(rect)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _base_scale(self) -> float:
        """Return the scale (widget px per image px) that fits the image in the widget."""
        if self._pixmap is None or self._pixmap.isNull():
            return 1.0
        return min(
            self.width() / self._pixmap.width(),
            self.height() / self._pixmap.height(),
        )

    def _render_rect(self) -> QRectF | None:
        """Return the widget rectangle the image is drawn in, or None without an image.

        Accounts for the base scale, the zoom and the pan offset.
        """
        if self._pixmap is None or self._pixmap.isNull():
            return None

        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        w = self.width()
        h = self.height()

        total_scale = self._base_scale() * self._zoom

        rendered_w = pix_w * total_scale
        rendered_h = pix_h * total_scale

        # Centre then apply pan
        x = (w - rendered_w) / 2.0 + self._pan.x()
        y = (h - rendered_h) / 2.0 + self._pan.y()

        return QRectF(x, y, rendered_w, rendered_h)

    def _total_scale(self) -> float:
        """Return the base scale times the zoom (widget px per image px)."""
        if self._pixmap is None or self._pixmap.isNull():
            return 1.0
        return self._base_scale() * self._zoom

    def _render_subset_rect(self) -> QRectF | None:
        """Widget-space rectangle of the subset square around its normalised centre."""
        rect = self._render_rect()
        scale = rect.width() / self._pixmap.width()
        cx = rect.x() + self._subset_pos_norm[0] * rect.width()
        cy = rect.y() + self._subset_pos_norm[1] * rect.height()
        half = self._subset_size * 0.5 * scale
        return QRectF(cx - half, cy - half, half * 2, half * 2)

    # --------------------------------------------------------------------------
    # Painting
    # --------------------------------------------------------------------------

    def paintEvent(self, event):
        """Render the pixmap and the enabled overlays to the widget."""
        rect = self._render_rect()
        if rect is None:
            return

        with QPainter(self) as painter:
            # sharp pixel edges at high zoom
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

            src = QRectF(self._pixmap.rect())
            painter.drawPixmap(rect, self._pixmap, src)

            if self._show_grid and self._grid_spacing > 0:
                self._draw_grid(painter, rect)

            roi = self.current_roi_rect()
            if roi is not None:
                self._draw_roi(painter, rect, roi)

            if self._show_target:
                self._draw_target(painter, rect)

            if self._show_subset:
                subset_rect = self._render_subset_rect()
                self._draw_subset(painter, rect, subset_rect)

    def _draw_roi(
        self, painter: QPainter, rect: QRectF, roi: tuple[float, float, float, float]
    ) -> None:
        painter.save()
        x0, y0, x1, y1 = roi
        x = rect.x() + x0 * rect.width()
        y = rect.y() + y0 * rect.height()
        w = (x1 - x0) * rect.width()
        h = (y1 - y0) * rect.height()

        pen = QPen(self._ROI_COLOR)
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)

        painter.setClipRect(rect)
        painter.drawRect(QRectF(x, y, w, h))
        painter.restore()

    def _draw_grid(self, painter: QPainter, rect: QRectF) -> None:
        """Draw lines every `_grid_spacing` image pixels, clipped to the frame."""
        painter.save()

        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        scale = rect.width() / pix_w

        pen = QPen(self._GRID_COLOR)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setClipRect(rect)

        ix = 0
        while ix <= pix_w:
            wx = rect.x() + ix * scale
            painter.drawLine(wx, rect.top(), wx, rect.bottom())
            ix += self._grid_spacing

        iy = 0
        while iy <= pix_h:
            wy = rect.y() + iy * scale
            painter.drawLine(rect.left(), wy, rect.right(), wy)
            iy += self._grid_spacing

        painter.restore()

    def _draw_target(self, painter: QPainter, rect: QRectF) -> None:
        """Draw a centre crosshair and a circle `_target_size` px wide."""
        painter.save()

        pen = QPen(self._TARGET_COLOR)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(3)
        painter.setPen(pen)

        center = rect.center()

        scale = rect.width() / self._pixmap.width()
        scaled_target_size = self._target_size * scale
        target_offset = scaled_target_size * 0.5

        painter.drawLine(rect.left(), center.y(), rect.right(), center.y())
        painter.drawLine(center.x(), rect.top(), center.x(), rect.bottom())

        painter.drawEllipse(
            center.x() - target_offset,
            center.y() - target_offset,
            scaled_target_size,
            scaled_target_size,
        )

        painter.restore()

    def _draw_subset(
        self, painter: QPainter, subset_rect: QRectF, rect: QRectF
    ) -> None:
        painter.save()

        pen = QPen(self._SUBSET_COLOR_LINE)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(QBrush(self._SUBSET_COLOR_FILL))
        painter.setClipRect(rect)
        painter.drawRect(subset_rect)

        painter.restore()

    # --------------------------------------------------------------------------
    # Mouse actions
    # --------------------------------------------------------------------------

    def _max_zoom(self) -> float:
        """Return the zoom at which one image pixel spans MAX_PX_PER_IMAGE_PX."""
        if self._pixmap is None:
            return 1.0  # no image: zoom is fixed at 1
        return self.MAX_PX_PER_IMAGE_PX / self._base_scale()

    def wheelEvent(self, event):
        """Zoom about the cursor, within the zoom limits."""
        if self._pixmap is None:
            return

        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1.0 / 1.15

        old_zoom = self._zoom
        new_zoom = max(self._ZOOM_MIN, min(self._max_zoom(), old_zoom * factor))
        if new_zoom == old_zoom:
            return

        cursor = QPointF(event.position())
        w_centre = QPointF(self.width() / 2.0, self.height() / 2.0)

        ratio = new_zoom / old_zoom
        self._pan = cursor - w_centre - (cursor - w_centre - self._pan) * ratio
        self._zoom = new_zoom
        self.update()

    def mousePressEvent(self, event):
        """Start a drag: region of interest, else subset square, else pan."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = QPointF(event.position())

            if self._roi_select_enabled:
                if self._pixmap is None or self._pixmap.isNull():
                    return
                norm = self._widget_to_norm(pos)
                if norm is None:
                    return
                self._roi_drag_start = norm
                self._roi_drag_end = norm
                self.update()
                return

            if self._show_subset:
                sub_rect = self._render_subset_rect()
                if sub_rect is not None and sub_rect.contains(pos):
                    self._subset_dragging = True
                    # Keep the grab point under the cursor; do not recentre the square.
                    self._subset_drag_offset = (
                        pos.x() - sub_rect.center().x(),
                        pos.y() - sub_rect.center().y(),
                    )
                    return

            self._drag_origin = pos
            self._pan_at_drag = QPointF(self._pan)

    def mouseMoveEvent(self, event):
        """Continue the drag started by the press."""
        pos = QPointF(event.position())
        if self._roi_select_enabled and self._roi_drag_start is not None:
            norm = self._widget_to_norm(pos)
            if norm is None:
                return
            self._roi_drag_end = norm
            self.update()
            return

        if self._subset_dragging:
            rect = self._render_rect()
            if rect is not None:
                target_x = pos.x() - self._subset_drag_offset[0]
                target_y = pos.y() - self._subset_drag_offset[1]
                nx = (target_x - rect.x()) / rect.width()
                ny = (target_y - rect.y()) / rect.height()
                self._subset_pos_norm = (
                    min(max(nx, 0.0), 1.0),
                    min(max(ny, 0.0), 1.0),
                )
                self.update()
            return

        if self._drag_origin is not None:
            delta = pos - self._drag_origin
            self._pan = self._pan_at_drag + delta
            self.update()

    def mouseReleaseEvent(self, event):
        """End the drag; a completed region of interest is stored and emitted."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._roi_select_enabled:
                if self._roi_drag_start is None:
                    return
                norm = self._widget_to_norm(QPointF(event.position()))
                if norm is None:
                    norm = self._roi_drag_end or self._roi_drag_start
                rect = self._normalized_rect(self._roi_drag_start, norm)
                self._roi_drag_start = None
                self._roi_drag_end = None
                if rect is not None:
                    self._roi_rect_norm = rect
                    self.roi_changed.emit(rect)
                if self._roi_select_one_shot:
                    self._roi_select_enabled = False
                self.update()
                return

            if self._subset_dragging:
                self._subset_dragging = False
                return

            self._drag_origin = None

    def mouseDoubleClickEvent(self, event):
        """Reset the view."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
