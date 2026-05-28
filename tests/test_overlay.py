"""Unit tests for overlay.py selection components."""

import sys
import unittest

from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget

from reader.ui.overlay import SelectionOverlay, SnippingController

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestSelectionOverlayEscape(unittest.TestCase):
    """Keyboard cancel behaviour on SelectionOverlay."""

    def test_escape_key_emits_selection_dismissed(self):
        """Pressing Escape on the overlay emits selection_dismissed."""
        overlay = SelectionOverlay(QRect(0, 0, 100, 100))

        dismissed = [False]
        overlay.selection_dismissed.connect(lambda: dismissed.__setitem__(0, True))

        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(overlay, event)

        self.assertTrue(dismissed[0], "Escape key must trigger selection_dismissed")
        overlay.close()


class TestSnippingControllerEscape(unittest.TestCase):
    """Escape handled at QApplication level - no overlay focus required."""

    def test_escape_cancels_via_event_filter_without_overlay_focus(self):
        """Escape sent to a non-overlay widget still cancels the selection."""
        controller = SnippingController()
        QApplication.instance().installEventFilter(controller)

        cancelled = [False]
        controller.cancelled.connect(lambda: cancelled.__setitem__(0, True))

        # Escape sent to a plain widget that is NOT the overlay - simulates
        # the real case where the overlay never receives OS-level focus.
        dummy = QWidget()
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(dummy, event)

        self.assertTrue(cancelled[0], "Event filter must cancel even without overlay focus")
        dummy.close()


if __name__ == "__main__":
    unittest.main()
