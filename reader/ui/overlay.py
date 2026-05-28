"""QR Transfer - UI Overlay Components.

Overlay and selection components for screen region selection.

This module contains SelectionOverlay and SnippingController classes.
"""

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

_SELECTION_MIN_SIZE = 50
_PEN_WIDTH = 2
_ALPHA_DIM = 100


class SelectionOverlay(QWidget):
    """Transparent overlay widget for screen region selection.

    Displays a semi-transparent overlay on all screens allowing the user
    to select a rectangular region by clicking and dragging. The selected
    region coordinates are emitted via selection_completed signal.

    Attributes:
        begin: Starting point of the current selection rectangle.
        end: Ending point of the current selection rectangle.
        is_selecting: True while the user is actively dragging a selection.
    """

    # Emits region dict with keys: top, left, width, height.
    selection_completed = pyqtSignal(dict)
    selection_dismissed = pyqtSignal()  # Emitted when mouse released with too-small a selection.

    def __init__(self, geometry: QRect) -> None:
        """Initialize the selection overlay.

        Args:
            geometry: Screen geometry to cover with this overlay.
        """
        super().__init__()
        self.setGeometry(geometry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.begin: QPoint = QPoint()
        self.end: QPoint = QPoint()
        self.is_selecting: bool = False

    def paintEvent(self, _event) -> None:
        """Draw the overlay background and the live selection rectangle."""
        painter = QPainter(self)
        painter.setBrush(QColor(0, 0, 0, _ALPHA_DIM))  # Dim background.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

        if self.is_selecting:
            selection_rect = QRect(self.begin, self.end).normalized()
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )
            painter.drawRect(selection_rect)

            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
            painter.setPen(QPen(QColor(0, 255, 127), _PEN_WIDTH))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(selection_rect)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to start selection."""
        self.begin = event.pos()
        self.end = event.pos()
        self.is_selecting = True
        self.update()

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move to update selection rectangle."""
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release to finalize and emit the selection."""
        self.is_selecting = False
        selection_rect = QRect(self.begin, self.end).normalized()
        self.close()
        # Require a minimum reasonable size to avoid accidental tiny selections
        if selection_rect.width() >= _SELECTION_MIN_SIZE and selection_rect.height() >= _SELECTION_MIN_SIZE:
            self.selection_completed.emit(
                {
                    "top": self.geometry().y() + selection_rect.y(),
                    "left": self.geometry().x() + selection_rect.x(),
                    "width": selection_rect.width(),
                    "height": selection_rect.height(),
                }
            )
        else:
            self.selection_dismissed.emit()

    def keyPressEvent(self, event) -> None:
        """Cancel selection on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.selection_dismissed.emit()


class SnippingController(QObject):
    """Controller for managing screen region selection across multiple monitors.

    Creates SelectionOverlay instances on all available screens and
    coordinates the selection process, emitting the final region via
    the finished signal.

    Attributes:
        overlays: Active overlay widgets, one per connected screen.
    """

    finished = pyqtSignal(dict)  # Emits the selected region dictionary.
    cancelled = pyqtSignal()     # Emits when selection is aborted.

    def __init__(self) -> None:
        """Initialize the snipping controller."""
        super().__init__()
        self.overlays: list[SelectionOverlay] = []

    def start(self) -> None:
        """Start selection process by creating overlays on all screens."""
        # Clean up any existing overlays first to avoid leaks.
        for overlay in self.overlays:
            overlay.close()
        self.overlays = []

        for screen in QApplication.screens():
            overlay = SelectionOverlay(screen.geometry())
            overlay.selection_completed.connect(self._on_selection)
            overlay.selection_dismissed.connect(self._on_overlay_closed)
            overlay.show()
            self.overlays.append(overlay)

        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._teardown()
            self.cancelled.emit()
            return True
        return super().eventFilter(obj, event)

    def _teardown(self) -> None:
        QApplication.instance().removeEventFilter(self)
        for overlay in self.overlays:
            overlay.close()
        self.overlays = []

    def _on_selection(self, region: dict) -> None:
        """Handle selection completion from an overlay."""
        self._teardown()
        self.finished.emit(region)

    def _on_overlay_closed(self) -> None:
        """Handle an overlay closing without a selection."""
        self._teardown()
        self.cancelled.emit()
