"""QR Transfer - Worker Module.

Core QR reading logic and worker thread implementation.
"""

import base64
import threading
import time
import zlib

import cv2
import mss
import numpy as np
import pyperclip
import zxingcpp
from PyQt6.QtCore import QPoint, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from reader.core.state_machine import QRStateMachine, ReaderState

from reader.config import (
    DEFAULT_MIN_DELAY_MS,
    DEFAULT_UPSCALE_FACTOR,
    END_MARKER,
    LOG_FILE,
    SEQ_PATTERN,
    START_COMPRESSED_PATTERN,
    START_PATTERN,
    STATS_UPDATE_INTERVAL,
)

_EXCEPTION_SLEEP_MS = 10


class QRWorker(QThread):
    """Background worker thread for capturing the screen and decoding QR codes.

    Signals:
        log_signal: Emits log messages for UI display.
        finished_signal: Emits when scanning completes.
        stats_signal: Emits a performance statistics dictionary.
    """

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    stats_signal = pyqtSignal(dict)

    def __init__(
        self,
        region: dict[str, float],
        upscale_factor: float = DEFAULT_UPSCALE_FACTOR,
        min_delay_ms: int = DEFAULT_MIN_DELAY_MS,
    ) -> None:
        """Initialize the QR worker thread.

        Args:
            region: Screen region coordinates with keys 'top', 'left',
                'width', 'height'. These are logical (Qt) coordinates.
            upscale_factor: Scale factor applied to captured frames before
                QR detection. Higher values improve detection of small codes.
            min_delay_ms: Minimum delay between frame captures in
                milliseconds, used to cap CPU usage.
        """
        super().__init__()
        # Convert logical (Qt) coordinates to physical (MSS) coordinates
        # by applying the device pixel ratio of the screen containing the region.
        self._region: dict[str, int] = self._scale_region_to_physical(region)
        self._upscale_factor: float = upscale_factor
        self._min_delay_ms: int = min_delay_ms

        # Thread control.
        self._stop_event: threading.Event = threading.Event()

        # Components.
        self._state_machine: QRStateMachine = QRStateMachine()
        self._mss: mss.mss | None = None

        # Performance counters.
        self._frames_processed: int = 0
        self._qr_detected_count: int = 0
        self._start_time: float | None = None

    def _scale_region_to_physical(self, logical_region: dict[str, float]) -> dict[str, int]:
        """Convert logical Qt coordinates to physical screen coordinates.

        On Windows with DPI scaling, Qt reports coordinates in logical pixels,
        but MSS (screen capture) requires physical pixels. This method finds
        the screen containing the region and scales by its device pixel ratio.

        Args:
            logical_region: Dict with 'top', 'left', 'width', 'height' in logical pixels.

        Returns:
            Dict with coordinates converted to physical pixels (integers).

        Raises:
            ValueError: If width or height are not positive.
        """
        # Validate region dimensions
        width = logical_region.get("width", 0)
        height = logical_region.get("height", 0)
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Invalid region dimensions: width={width}, height={height}. "
                "Both must be positive numbers."
            )

        # Find the screen that contains the top-left corner of the region
        top_left = QPoint(int(logical_region["left"]), int(logical_region["top"]))
        screen = QApplication.screenAt(top_left)
        if screen is None:
            # Fallback to primary screen
            screen = QApplication.primaryScreen()

        dpr = screen.devicePixelRatio()

        return {
            "top": int(logical_region["top"] * dpr),
            "left": int(logical_region["left"] * dpr),
            "width": int(width * dpr),
            "height": int(height * dpr),
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute the main scanning loop."""
        try:
            self._mss = mss.mss()
        except Exception as e:
            self.log_signal.emit(f"⚠️ Screen capture init failed: {e}")
            return

        self._start_time = time.time()
        try:
            self.log_signal.emit("🚀 Scanning started (Engine: zxing-cpp)")
            self.log_signal.emit("⏳ WAITING FOR START MARKER...")
            self._scan_loop()
        finally:
            if self._mss is not None:
                self._mss.close()
            self._mss = None

    def _scan_loop(self) -> None:
        """Main scanning loop with rate limiting and stats emission."""
        last_stats_time: float = 0.0

        while not self._stop_event.is_set():
            try:
                frame_start = time.time()
                self._process_frame()

                elapsed_ms = (time.time() - frame_start) * 1000
                if elapsed_ms < self._min_delay_ms:
                    time.sleep((self._min_delay_ms - elapsed_ms) / 1000)

                now = time.time()
                if now - last_stats_time >= STATS_UPDATE_INTERVAL:
                    self._emit_stats()
                    last_stats_time = now

            except Exception as e:
                self.log_signal.emit(f"⚠️ Runtime Error: {e}")
                time.sleep(_EXCEPTION_SLEEP_MS / 1000)

    def _process_frame(self) -> None:
        """Capture, decode (raw fast-path then preprocessed fallback)."""
        screenshot = self._mss.grab(self._region)
        image = np.ascontiguousarray(np.array(screenshot))
        self._frames_processed += 1

        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)

        # Fast path: clean local captures decode directly. Only spend CPU on
        # bilateral+CLAHE if the raw frame produced nothing (compressed remote).
        results = zxingcpp.read_barcodes(gray, formats=zxingcpp.BarcodeFormat.QRCode)
        if not results:
            results = zxingcpp.read_barcodes(
                self._preprocess(gray), formats=zxingcpp.BarcodeFormat.QRCode
            )

        for r in results:
            if r.text:
                self._process_qr_data(r.text)

    def _preprocess(self, gray: np.ndarray) -> np.ndarray:
        """Recover QR codes degraded by remote-desktop / VNC compression.

        - Upscale small captures so downstream filters have pixels to work with
        - bilateralFilter smooths JPEG artefacts while preserving module edges
        - CLAHE restores local contrast lost to aggressive compression
        zxing-cpp performs its own binarisation, so we do not threshold here.
        """
        if self._upscale_factor > 1.0:
            gray = cv2.resize(
                gray,
                None,
                fx=self._upscale_factor,
                fy=self._upscale_factor,
                interpolation=cv2.INTER_CUBIC,
            )
        gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def stop(self) -> None:
        """Signal the worker loop to stop on the next iteration."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_qr_data(self, data: str) -> None:
        """Route decoded QR data through the state machine."""
        self._qr_detected_count += 1

        start_match = START_PATTERN.match(data)
        start_comp_match = START_COMPRESSED_PATTERN.match(data)
        if start_match or start_comp_match:
            m = start_match or start_comp_match
            total_chunks = int(m.group(1))
            compressed = start_comp_match is not None
            prev_state = self._state_machine.state
            had_chunks = len(self._state_machine.buffer) > 0
            self._state_machine.handle_start(compressed, total_chunks)
            is_new_session = prev_state != ReaderState.RECEIVING or had_chunks
            if is_new_session:
                if compressed:
                    self.log_signal.emit("🟡 START COMPRESSED MARKER DETECTED!")
                else:
                    self.log_signal.emit("🟢 START MARKER DETECTED!")
        elif data == END_MARKER:
            if self._state_machine.handle_end():
                self.log_signal.emit("🛑 END MARKER RECEIVED!")
                self._finalize_transfer()
                self._stop_event.set()
        else:
            seq_match = SEQ_PATTERN.search(data)
            if seq_match:
                seq_num = int(seq_match.group(1))
                was_idle = self._state_machine.state == ReaderState.IDLE
                was_added = self._state_machine.handle_chunk(seq_num, data[: seq_match.start()])
                if was_added:
                    self.log_signal.emit(f"✅ Received #{seq_num}")
                    if was_idle:
                        self.log_signal.emit("⚠️ Auto-start: chunk before START marker")

    def _emit_stats(self) -> None:
        """Emit current performance statistics via stats_signal."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        fps = self._frames_processed / elapsed if elapsed > 0 else 0
        stats = {
            "fps": round(fps, 1),
            "frames": self._frames_processed,
            "qr_detected": self._qr_detected_count,
            "chunks": len(self._state_machine.buffer),
            "total_chunks": self._state_machine.total_chunks,
            "state": self._state_machine.state,
        }
        self.stats_signal.emit(stats)

    def _finalize_transfer(self) -> None:
        """Assemble received chunks and write output.

        Thin orchestrator over small, independently testable steps.
        """
        full_content, missing_indices, received, expected_total, success_rate = (
            self._compute_assembly()
        )

        if not full_content:
            self.log_signal.emit("⚠️ No data received.")
            self.finished_signal.emit()
            return

        if missing_indices:
            shown = missing_indices[:5]
            suffix = "..." if len(missing_indices) > 5 else ""
            self.log_signal.emit(
                f"❌ Transfer incomplete: {len(missing_indices)} missing chunk(s): {shown}{suffix}"
            )
            self.log_signal.emit("Re-run the Sender at a slower speed to retry.")
            self.finished_signal.emit()
            return

        try:
            raw_bytes = self._decode_payload(full_content)
        except Exception as e:
            self.log_signal.emit(f"❌ Base64 decode failed: {e}")
            self.finished_signal.emit()
            return

        if self._state_machine.is_compressed:
            try:
                raw_bytes = self._decompress(raw_bytes)
            except Exception as e:
                self.log_signal.emit(f"❌ Decompression failed: {e}")
                self.finished_signal.emit()
                return

        try:
            text = self._to_text(raw_bytes)
        except UnicodeDecodeError as e:
            self.log_signal.emit(f"❌ Decode failed (not UTF-8): {e}")
            self.finished_signal.emit()
            return

        self._persist(text)

        self.log_signal.emit(f"✨ DONE: {received}/{expected_total} chunks ({success_rate:.1f}%)")
        self.finished_signal.emit()

    def _compute_assembly(self) -> tuple[str, list[int], int, int, float]:
        """Assemble the buffer and compute missing chunks and success rate.

        Returns (full_content, missing_indices, received, expected_total,
        success_rate).
        """
        buffer = self._state_machine.buffer
        full_content, missing_in_range = buffer.assemble()
        received = len(buffer)
        max_seq = buffer.max_seq
        total_announced = self._state_machine.total_chunks

        if total_announced > 0:
            expected_total = total_announced
            leading = list(range(1, buffer.min_seq))
            trailing = list(range(max_seq + 1, total_announced + 1))
            missing_indices = leading + missing_in_range + trailing
        else:
            expected_total = max_seq - buffer.min_seq + 1
            missing_indices = missing_in_range

        success_rate = (received / expected_total * 100) if expected_total > 0 else 0.0
        return full_content, missing_indices, received, expected_total, success_rate

    @staticmethod
    def _decode_payload(b64_text: str) -> bytes:
        """Decode the assembled base64 payload to raw bytes."""
        return base64.b64decode(b64_text)

    @staticmethod
    def _decompress(data: bytes) -> bytes:
        """Inflate zlib-compressed bytes."""
        return zlib.decompress(data)

    @staticmethod
    def _to_text(data: bytes) -> str:
        """Decode raw bytes as UTF-8 text."""
        return data.decode('utf-8')

    def _persist(self, text: str) -> None:
        """Write the text to the log file and copy it to the clipboard.

        File-write and clipboard failures are logged but non-fatal: neither
        aborts the other, matching the previous inline behavior.
        """
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(text)
            self.log_signal.emit(f"📄 Saved to: {LOG_FILE}")
        except OSError as e:
            self.log_signal.emit(f"❌ File write error: {e}")

        try:
            pyperclip.copy(text)
            self.log_signal.emit("📋 Copied to Clipboard!")
        except Exception as e:
            self.log_signal.emit(f"⚠️ Clipboard failed: {e}")
