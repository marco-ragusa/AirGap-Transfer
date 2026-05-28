"""QR Transfer - Main Window UI."""

from datetime import datetime
from typing import TypedDict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from reader.config import (
    DEFAULT_MIN_DELAY_MS,
    DEFAULT_UPSCALE_FACTOR,
    THREAD_JOIN_TIMEOUT_MS,
)
from reader.core.qr_worker import QRWorker
from reader.core.state_machine import ReaderState
from reader.ui.overlay import SnippingController


class ScanStats(TypedDict):
    fps: float
    frames: int
    qr_detected: int
    chunks: int
    total_chunks: int
    state: ReaderState


class MainWindow(QMainWindow):
    """Main application window for the QR Reader."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("QR Reader")
        self.resize(420, 560)
        self._setup_ui()
        self._apply_theme()

        self.worker: QRWorker | None = None
        self.snip_controller: SnippingController = SnippingController()
        self.snip_controller.finished.connect(self.on_area_selected)
        self.snip_controller.cancelled.connect(self.on_selection_cancelled)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # Header row - title + state badge.
        header = QHBoxLayout()
        title = QLabel("QR READER")
        title.setObjectName("title")
        self._badge = QLabel("IDLE")
        self._badge.setObjectName("badge_idle")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._badge)
        root.addLayout(header)

        # Buttons.
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.select_button = QPushButton("📷  Select Area")
        self.select_button.setObjectName("btn_primary")
        self.select_button.clicked.connect(self.start_selection)
        self.stop_button = QPushButton("⏹  Stop")
        self.stop_button.setObjectName("btn_danger")
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)
        btn_row.addWidget(self.select_button)
        btn_row.addWidget(self.stop_button)
        root.addLayout(btn_row)

        # Stats strip.
        self.stats_label = QLabel("FPS - &nbsp;·&nbsp; Chunks - &nbsp;·&nbsp; QR -")
        self.stats_label.setObjectName("stats")
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.stats_label)

        # Progress bar (hidden until a transfer starts).
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        # Separator.
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Log area.
        self.log_text = QTextEdit()
        self.log_text.setObjectName("log")
        self.log_text.setReadOnly(True)
        root.addWidget(self.log_text)

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #181715;
                color: #E8E2DA;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
            }

            QLabel#title {
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 4px;
                color: #E8E2DA;
            }

            QLabel#badge_idle {
                background: #211F1C;
                color: #AEA79E;
                border: 1px solid #3A3631;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#badge_receiving {
                background: #1a2420;
                color: #7FB07A;
                border: 1px solid #3a5e38;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#badge_done {
                background: #221d10;
                color: #D3A25F;
                border: 1px solid #6a5028;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#stats {
                color: #AEA79E;
                font-size: 12px;
                padding: 2px 0;
            }

            QPushButton {
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                padding: 9px 16px;
                border: none;
            }
            QPushButton#btn_primary           { background: #6FA3A7; color: #0c1a1c; }
            QPushButton#btn_primary:hover     { background: #84B5B8; }
            QPushButton#btn_primary:disabled  { background: #202e30; color: #405658; }
            QPushButton#btn_danger            { background: transparent;
                                                border: 1px solid #D07A89; color: #D07A89; }
            QPushButton#btn_danger:hover      { background: rgba(208,122,137,.1); }
            QPushButton#btn_danger:disabled   { border-color: #4a2430; color: #4a2430; }

            QTextEdit#log {
                background: #181715;
                color: #C8C2BA;
                border: 1px solid #3A3631;
                border-radius: 6px;
                font-family: 'Consolas', 'Cascadia Code', monospace;
                font-size: 12px;
                padding: 6px;
                selection-background-color: #2a2820;
            }

            QScrollBar:vertical              { background: #181715; width: 6px; border: none; }
            QScrollBar::handle:vertical      { background: #3A3631; border-radius: 3px; min-height: 20px; }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical    { height: 0; }

            QFrame#separator { color: #3A3631; }

            QProgressBar#progress            { background: #3A3631; border: none; border-radius: 2px; }
            QProgressBar#progress::chunk     { background: #6FA3A7; border-radius: 2px; }
        """)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_badge(self, name: str, text: str) -> None:
        self._badge.setObjectName(name)
        self._badge.setText(text)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

    def log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"<span style='color:#7A756E'>[{ts}]</span> {message}")
        bar = self.log_text.verticalScrollBar()
        bar.setValue(bar.maximum())

    def update_stats(self, stats: ScanStats) -> None:
        state = stats["state"]
        total = stats["total_chunks"]
        chunks_str = f"{stats['chunks']}/{total}" if total > 0 else str(stats["chunks"])

        if state == ReaderState.RECEIVING:
            self._set_badge("badge_receiving", "RECEIVING")
        elif state == ReaderState.DONE:
            self._set_badge("badge_done", "DONE")
        else:
            self._set_badge("badge_idle", "IDLE")

        self.stats_label.setText(
            f"FPS <b>{stats['fps']}</b> &nbsp;·&nbsp; "
            f"Chunks <b>{chunks_str}</b> &nbsp;·&nbsp; "
            f"QR <b>{stats['qr_detected']}</b>"
        )

        if total > 0 and stats["chunks"] > 0:
            self.progress_bar.setValue(int(stats["chunks"] / total * 100))
            self.progress_bar.show()
        elif state == ReaderState.IDLE:
            self.progress_bar.hide()
            self.progress_bar.setValue(0)

    # ------------------------------------------------------------------
    # Selection flow
    # ------------------------------------------------------------------

    def start_selection(self) -> None:
        # setWindowOpacity(0) hides this window visually but keeps it as the
        # OS foreground owner, so Windows keeps delivering keyboard events to
        # this process. The overlay covers the screen; the opacity is restored
        # when selection ends.
        self.setWindowOpacity(0.0)
        self.snip_controller.start()

    def on_selection_cancelled(self) -> None:
        self.setWindowOpacity(1.0)
        self.showNormal()
        self.activateWindow()
        self.log("Selection cancelled.")

    def on_area_selected(self, region: dict[str, int]) -> None:
        self.setWindowOpacity(1.0)
        self.showNormal()
        self.activateWindow()

        if self.worker:
            self.stop_scan()

        self.worker = QRWorker(
            region,
            upscale_factor=DEFAULT_UPSCALE_FACTOR,
            min_delay_ms=DEFAULT_MIN_DELAY_MS,
        )
        self.worker.log_signal.connect(self.log)
        self.worker.stats_signal.connect(self.update_stats)
        self.worker.finished_signal.connect(self.on_scan_finished)
        self.worker.start()

        self.select_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log_text.clear()

    # ------------------------------------------------------------------
    # Scan control
    # ------------------------------------------------------------------

    def stop_scan(self) -> None:
        if self.worker:
            self._shutdown_worker(self.worker)
            self.worker = None
        self.on_scan_finished()

    def _shutdown_worker(self, worker: QRWorker) -> None:
        try:
            worker.finished_signal.disconnect(self.on_scan_finished)
        except TypeError:
            pass
        worker.stop()
        if worker.isRunning():
            if not worker.wait(THREAD_JOIN_TIMEOUT_MS):
                self.log("⚠️ Worker did not terminate gracefully")
        worker.deleteLater()

    def on_scan_finished(self) -> None:
        self.select_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._set_badge("badge_idle", "IDLE")
        self.stats_label.setText("FPS - &nbsp;·&nbsp; Chunks - &nbsp;·&nbsp; QR -")
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
