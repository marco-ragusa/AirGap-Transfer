"""Characterization tests for QRWorker.

Tests cover state transitions, chunk handling, deduplication, auto-start,
finalization assembly, stop behavior, and error handling.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

import numpy as np
from PyQt6.QtWidgets import QApplication

from reader.config import END_MARKER, LOG_FILE, START_PATTERN, START_COMPRESSED_PATTERN
from reader.core.chunk_manager import ChunkBuffer
from reader.core.qr_worker import QRWorker
from reader.core.state_machine import QRStateMachine, ReaderState

# Ensure a QApplication exists for Qt signals/threads
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestQRWorkerInitialization(unittest.TestCase):
    """Test QRWorker initialization parameters and defaults."""

    def test_init_parameters(self):
        """QRWorker stores constructor parameters correctly."""
        region = {"top": 10, "left": 20, "width": 100, "height": 200}
        with patch.object(QRWorker, '_scale_region_to_physical', return_value=region):
            worker = QRWorker(
                region,
                upscale_factor=3.0,
                min_delay_ms=50,
            )
        self.assertEqual(worker._region, region)
        self.assertEqual(worker._upscale_factor, 3.0)
        self.assertEqual(worker._min_delay_ms, 50)
        self.assertIsNone(worker._mss)
        self.assertIsInstance(worker._state_machine, QRStateMachine)

    def test_initial_state(self):
        """QRWorker starts with state machine in IDLE and empty buffer."""
        region = {"top": 0, "left": 0, "width": 10, "height": 10}
        worker = QRWorker(region)
        self.assertEqual(worker._state_machine.state, ReaderState.IDLE)
        self.assertEqual(len(worker._state_machine.buffer), 0)
        self.assertEqual(worker._state_machine.buffer.max_seq, 0)


class TestStateTransitions(unittest.TestCase):
    """Test state machine transitions via QRWorker data routing."""

    def setUp(self):
        self.region = {"top": 0, "left": 0, "width": 10, "height": 10}
        self.worker = QRWorker(self.region)

    def test_start_marker_idle_to_receiving(self):
        """START_MARKER transitions from IDLE to RECEIVING."""
        self.worker._state_machine.reset()  # Ensure IDLE
        self.worker._state_machine.handle_start()
        self.assertEqual(self.worker._state_machine.state, ReaderState.RECEIVING)
        self.assertEqual(len(self.worker._state_machine.buffer), 0)

    def test_start_marker_restarts_when_receiving_empty_buffer(self):
        """START resets a stuck RECEIVING session that received no chunks yet.

        Real scenario: START caught, all chunks missed (screen blocked), sender
        loops and shows START again - session must be allowed to restart.
        """
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.assertEqual(len(self.worker._state_machine.buffer), 0)

        self.worker._state_machine.handle_start(compressed=False, total_chunks=3)

        self.assertEqual(self.worker._state_machine.state, ReaderState.RECEIVING)
        self.assertEqual(self.worker._state_machine.total_chunks, 3)

    def test_start_marker_restart_when_receiving_with_chunks(self):
        """START_MARKER while RECEIVING with existing chunks resets the buffer."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.worker._state_machine.buffer.add(1, "data")
        self.worker._state_machine.handle_start()
        self.assertEqual(self.worker._state_machine.state, ReaderState.RECEIVING)
        self.assertEqual(len(self.worker._state_machine.buffer), 0)

    def test_end_marker_ignored_when_idle(self):
        """END_MARKER in IDLE state is ignored."""
        self.worker._state_machine.reset()
        self.worker._state_machine.handle_end()
        self.assertEqual(self.worker._state_machine.state, ReaderState.IDLE)

    def test_end_marker_ignored_when_receiving_no_chunks(self):
        """END_MARKER in RECEIVING with no chunks is ignored (ghost marker)."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.worker._state_machine.handle_end()
        self.assertEqual(self.worker._state_machine.state, ReaderState.RECEIVING)

    def test_end_marker_finalizes_and_stops(self):
        """END_MARKER in RECEIVING with chunks transitions to DONE and finalizes."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.worker._state_machine.buffer.add(1, "A")
        self.worker._state_machine.buffer.add(2, "B")
        # Simulate end marker
        self.worker._state_machine.handle_end()
        self.assertEqual(self.worker._state_machine.state, ReaderState.DONE)

    def test_end_marker_idempotent_after_done(self):
        """END_MARKER in DONE state remains DONE and does not re-finalize."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.worker._state_machine.buffer.add(1, "A")
        self.worker._state_machine.handle_end()  # First end
        self.assertEqual(self.worker._state_machine.state, ReaderState.DONE)
        # Second end marker should not change state
        self.worker._state_machine.handle_end()
        self.assertEqual(self.worker._state_machine.state, ReaderState.DONE)


class TestChunkHandling(unittest.TestCase):
    """Test chunk reception, deduplication, and auto-start."""

    def setUp(self):
        self.region = {"top": 0, "left": 0, "width": 10, "height": 10}
        self.worker = QRWorker(self.region)

    def test_chunk_stored_and_sequence_updated(self):
        """New chunk is stored and max_seq is updated."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        seq_num = 1
        data = "payload"
        was_added = self.worker._state_machine.handle_chunk(seq_num, data)
        self.assertTrue(was_added)
        self.assertIn(seq_num, self.worker._state_machine.buffer.chunks)
        self.assertEqual(self.worker._state_machine.buffer.chunks[seq_num], data)
        self.assertEqual(self.worker._state_machine.buffer.max_seq, 1)

    def test_duplicate_chunk_deduped(self):
        """Duplicate sequence number is ignored and not added."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.worker._state_machine.buffer.add(1, "A")
        was_added = self.worker._state_machine.handle_chunk(1, "A")
        self.assertFalse(was_added)
        self.assertEqual(len(self.worker._state_machine.buffer), 1)

    def test_auto_start_on_chunk_when_idle(self):
        """Chunk received in IDLE state auto-starts session (forgiving)."""
        self.worker._state_machine.reset()
        self.assertEqual(self.worker._state_machine.state, ReaderState.IDLE)
        seq_num = 5
        data = "payload"
        was_added = self.worker._state_machine.handle_chunk(seq_num, data)
        self.assertTrue(was_added)
        self.assertEqual(self.worker._state_machine.state, ReaderState.RECEIVING)
        self.assertIn(seq_num, self.worker._state_machine.buffer.chunks)

    def test_chunk_rejected_in_done_state(self):
        """Chunks are rejected (not added) when state machine is DONE."""
        self.worker._state_machine.reset()
        self.worker._state_machine._state = ReaderState.RECEIVING
        self.worker._state_machine.buffer.add(1, "A")
        self.worker._state_machine.handle_end()  # transition to DONE
        self.assertEqual(self.worker._state_machine.state, ReaderState.DONE)

        was_added = self.worker._state_machine.handle_chunk(2, "B")
        self.assertFalse(was_added)
        self.assertEqual(len(self.worker._state_machine.buffer), 1)  # still only 1 chunk


class TestFinalization(unittest.TestCase):
    """Test message assembly and finalization side effects."""

    @patch("reader.core.qr_worker.pyperclip.copy")
    @patch("builtins.open", new_callable=mock_open)
    def test_finalizer_writes_file_and_copies_clipboard(self, mock_open_func, mock_pyperclip_copy):
        """Finalization base64-decodes chunks and writes result to file and clipboard."""
        import base64
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._state_machine._buffer = ChunkBuffer()
        worker._state_machine._buffer.add(1, base64.b64encode("Hello".encode()).decode())
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()

        worker._finalize_transfer()

        mock_open_func.assert_called_once_with(LOG_FILE, "w", encoding="utf-8")
        mock_file = mock_open_func.return_value
        mock_file.write.assert_called_once_with("Hello")
        mock_pyperclip_copy.assert_called_once_with("Hello")
        worker.log_signal.emit.assert_any_call("📋 Copied to Clipboard!")

    def test_finalizer_empty_content_returns_warning(self):
        """Finalization with empty buffer returns warning."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._state_machine._buffer = ChunkBuffer()  # Ensure empty
        worker.log_signal = MagicMock()

        worker._finalize_transfer()

        worker.log_signal.emit.assert_any_call("⚠️ No data received.")

    @patch("builtins.open")
    def test_finalizer_file_error_returns_error(self, mock_open):
        """Finalization returns file error if write fails."""
        import base64
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._state_machine._buffer = ChunkBuffer()
        worker._state_machine._buffer.add(1, base64.b64encode(b"data").decode())
        worker.log_signal = MagicMock()

        mock_open.side_effect = OSError("disk full")
        worker._finalize_transfer()

        worker.log_signal.emit.assert_any_call("❌ File write error: disk full")


class TestFinalizationIdempotency(unittest.TestCase):
    """Test that _finalize_transfer is not called a second time if END marker arrives while DONE."""

    def test_end_marker_in_done_state_does_not_refinalize(self):
        """_process_qr_data with END_MARKER while already DONE must not call _finalize_transfer.

        handle_end() returns False in DONE state; _process_qr_data gates finalization
        on that return value, so a duplicate END marker is fully ignored.
        """
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()

        # Prime: force state machine to DONE with one chunk already received.
        worker._state_machine._state = ReaderState.RECEIVING
        worker._state_machine.buffer.add(1, "hello")
        transitioned = worker._state_machine.handle_end()
        self.assertTrue(transitioned)
        self.assertEqual(worker._state_machine.state, ReaderState.DONE)

        # Spy on _finalize_transfer.
        finalize_call_count = 0

        def counting_finalize():
            nonlocal finalize_call_count
            finalize_call_count += 1

        worker._finalize_transfer = counting_finalize  # type: ignore[method-assign]

        # Feed a second END marker while already DONE.
        worker._process_qr_data(END_MARKER)

        self.assertEqual(finalize_call_count, 0,
                         "_finalize_transfer must not be called when handle_end() returns False")
        self.assertEqual(worker._state_machine.state, ReaderState.DONE)


class TestTotalChunks(unittest.TestCase):
    """Test total_chunks tracking in state machine and _finalize_transfer."""

    def setUp(self):
        self.region = {"top": 0, "left": 0, "width": 10, "height": 10}
        self.worker = QRWorker(self.region)

    def test_total_chunks_stored_by_handle_start(self):
        """handle_start stores the announced total_chunks."""
        self.worker._state_machine.reset()
        self.worker._state_machine.handle_start(compressed=False, total_chunks=7)
        self.assertEqual(self.worker._state_machine.total_chunks, 7)

    def test_total_chunks_updated_on_restart(self):
        """A restarted session updates total_chunks to the new announced value."""
        self.worker._state_machine.handle_start(compressed=False, total_chunks=5)
        self.worker._state_machine.buffer.add(1, "x")
        self.worker._state_machine.handle_start(compressed=False, total_chunks=10)
        self.assertEqual(self.worker._state_machine.total_chunks, 10)

    @patch("reader.core.qr_worker.pyperclip.copy")
    @patch("builtins.open", new_callable=mock_open)
    def test_finalize_detects_trailing_missing_chunks(self, mock_open_func, mock_pyperclip_copy):
        """_finalize_transfer reports trailing chunks missing beyond max_seq."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()

        # Sender announced 5 chunks; only 3 received (no gap within received range).
        worker._state_machine.handle_start(compressed=False, total_chunks=5)
        worker._state_machine.buffer.add(1, "chunk1")
        worker._state_machine.buffer.add(2, "chunk2")
        worker._state_machine.buffer.add(3, "chunk3")

        worker._finalize_transfer()

        log_calls = [call.args[0] for call in worker.log_signal.emit.call_args_list]
        incomplete_msgs = [m for m in log_calls if "Transfer incomplete" in m]
        self.assertEqual(len(incomplete_msgs), 1)
        self.assertIn("2", incomplete_msgs[0])  # 2 trailing missing: chunks 4 and 5

    @patch("reader.core.qr_worker.pyperclip.copy")
    @patch("builtins.open", new_callable=mock_open)
    def test_finalize_success_rate_with_announced_total(self, mock_open_func, mock_pyperclip_copy):
        """_finalize_transfer emits correct success rate using announced total."""
        import base64
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()

        # Encode full payload then split - mirrors how the sender works.
        b64_payload = base64.b64encode("Hello World".encode()).decode()
        mid = len(b64_payload) // 2
        chunk1, chunk2 = b64_payload[:mid], b64_payload[mid:]

        worker._state_machine.handle_start(compressed=False, total_chunks=2)
        worker._state_machine.buffer.add(1, chunk1)
        worker._state_machine.buffer.add(2, chunk2)

        worker._finalize_transfer()

        log_calls = [call.args[0] for call in worker.log_signal.emit.call_args_list]
        done_msgs = [m for m in log_calls if "DONE" in m]
        self.assertEqual(len(done_msgs), 1)
        self.assertIn("2/2", done_msgs[0])
        self.assertIn("100.0%", done_msgs[0])


class TestStopBehavior(unittest.TestCase):
    """Test stop flag and loop termination."""

    def test_stop_sets_flag(self):
        """stop() sets the stop event."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        self.assertFalse(worker._stop_event.is_set())
        worker.stop()
        self.assertTrue(worker._stop_event.is_set())


class TestErrorHandling(unittest.TestCase):
    """Test error conditions and recovery."""

    @patch("reader.core.qr_worker.mss.mss")
    def test_mss_initialize_failure_logs_error(self, mock_mss):
        """If mss.mss() init fails, an error is logged and run exits."""
        mock_mss.side_effect = Exception("display unavailable")
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker.log_signal = MagicMock()

        worker.run()

        worker.log_signal.emit.assert_called_once_with(
            "⚠️ Screen capture init failed: display unavailable"
        )

    def test_process_qr_data_routing(self):
        """_process_qr_data correctly routes markers and chunks."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._state_machine.reset()
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()
        worker._finalize_transfer = MagicMock()

        # Simulate start marker - v2 format includes total chunk count
        worker._process_qr_data("__QR_START_3__")
        worker.log_signal.emit.assert_any_call("🟢 START MARKER DETECTED!")
        self.assertEqual(worker._state_machine.total_chunks, 3)

        # Simulate chunk with proper sequence tag at end
        worker._process_qr_data("data__QR_SEQ_1__")
        worker.log_signal.emit.assert_any_call("✅ Received #1")

        # Simulate end marker
        worker._state_machine.buffer.add(2, "more")
        worker._process_qr_data(END_MARKER)
        worker.log_signal.emit.assert_any_call("🛑 END MARKER RECEIVED!")
        worker._finalize_transfer.assert_called_once()


class TestFinalizationEdgeCases(unittest.TestCase):
    """Edge cases in _finalize_transfer not covered by TestFinalization."""

    def test_finalizer_invalid_utf8_logs_error_and_finishes(self):
        """Non-UTF-8 payload must log an error and emit finished_signal - never freeze the UI."""
        import base64 as _b64
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()

        # bytes([0xFF, 0xFE, 0xFD]) round-trips through base64 but is NOT valid UTF-8
        invalid_utf8 = bytes([0xFF, 0xFE, 0xFD])
        worker._state_machine.handle_start(compressed=False, total_chunks=1)
        worker._state_machine.buffer.add(1, _b64.b64encode(invalid_utf8).decode())

        worker._finalize_transfer()  # must not raise UnicodeDecodeError

        worker.finished_signal.emit.assert_called_once()
        log_calls = [c.args[0] for c in worker.log_signal.emit.call_args_list]
        self.assertTrue(
            any("❌" in m for m in log_calls),
            f"Expected an error log entry; got: {log_calls}",
        )

    @patch("reader.core.qr_worker.pyperclip.copy")
    @patch("builtins.open", new_callable=mock_open)
    def test_finalize_detects_leading_missing_chunks(self, mock_open_func, mock_pyperclip):
        """Chunks missing before min_seq are detected and reported as incomplete."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()

        # 5 chunks announced; only 3–5 received - chunks 1 and 2 never arrived
        worker._state_machine.handle_start(compressed=False, total_chunks=5)
        worker._state_machine.buffer.add(3, "chunk3")
        worker._state_machine.buffer.add(4, "chunk4")
        worker._state_machine.buffer.add(5, "chunk5")

        worker._finalize_transfer()

        log_calls = [c.args[0] for c in worker.log_signal.emit.call_args_list]
        incomplete = [m for m in log_calls if "Transfer incomplete" in m]
        self.assertEqual(len(incomplete), 1, f"Expected 'Transfer incomplete'; got: {log_calls}")
        self.assertIn("2", incomplete[0])  # 2 leading missing: chunks 1 and 2


class TestWorkerFrameHandling(unittest.TestCase):
    """Tests for _process_frame and _process_qr_data routing."""

    @patch("reader.core.qr_worker.zxingcpp")
    @patch("reader.core.qr_worker.cv2")
    def test_process_frame_propagates_decoder_exception(self, mock_cv2, mock_zxing):
        """Exceptions from zxingcpp.read_barcodes must propagate, not be swallowed silently."""
        flat = np.zeros((10, 10), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = flat
        mock_cv2.bilateralFilter.return_value = flat
        mock_cv2.createCLAHE.return_value.apply.return_value = flat
        mock_zxing.read_barcodes.side_effect = RuntimeError("decoder crash")

        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._mss = MagicMock()
        worker._mss.grab.return_value = np.zeros((10, 10, 4), dtype=np.uint8)

        with self.assertRaises(RuntimeError):
            worker._process_frame()

    def test_start_marker_logged_once_on_repeated_captures(self):
        """START seen many times while waiting for chunks must log exactly once."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._state_machine.reset()
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()
        worker._finalize_transfer = MagicMock()

        for _ in range(10):
            worker._process_qr_data("__QR_START_3__")

        log_calls = [c.args[0] for c in worker.log_signal.emit.call_args_list]
        start_logs = [m for m in log_calls if "START MARKER" in m]
        self.assertEqual(len(start_logs), 1, f"START logged {len(start_logs)} times instead of 1")

    def test_end_marker_not_logged_when_ignored(self):
        """END_MARKER in IDLE state must be silently discarded - no log entry."""
        worker = QRWorker({"top": 0, "left": 0, "width": 1, "height": 1})
        worker._state_machine.reset()  # IDLE
        worker.log_signal = MagicMock()
        worker.finished_signal = MagicMock()
        worker._finalize_transfer = MagicMock()

        worker._process_qr_data(END_MARKER)

        log_calls = [c.args[0] for c in worker.log_signal.emit.call_args_list]
        self.assertFalse(
            any("END MARKER" in m for m in log_calls),
            f"END MARKER must not be logged when ignored; got: {log_calls}",
        )
        worker._finalize_transfer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
