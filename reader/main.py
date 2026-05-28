#!/usr/bin/env python3
"""QR Transfer - Main Entry Point.

Entry point for the QR Reader application.

This module simply initializes and launches the main window.
"""

import sys
import os

# When run directly (python reader/main.py), __package__ is None and the project
# root is not on sys.path. Insert it so `reader.*` imports resolve correctly.
if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication

from reader.ui.main_window import MainWindow


def main() -> None:
    """Initialize and launch the application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
