"""QR Transfer - State Machine.

Pure state machine for handling start/end markers and data chunks.
No side-effects, no Qt signals, no I/O. Easily testable.
"""

from enum import Enum, auto

from reader.core.chunk_manager import ChunkBuffer


class ReaderState(Enum):
    """States of the QR reader state machine."""

    IDLE = auto()
    RECEIVING = auto()
    DONE = auto()


class QRStateMachine:
    """State machine for QR transfer protocol.

    Handles transitions based on markers and chunks, manages chunk buffer,
    and enforces protocol rules (auto-start, ghost marker filtering).

    Attributes:
        state: Current state (IDLE, RECEIVING, or DONE).
        buffer: ChunkBuffer instance for storing data chunks.
    """

    def __init__(self, buffer: ChunkBuffer | None = None) -> None:
        """Initialize state machine.

        Args:
            buffer: Optional ChunkBuffer; creates new one if None.
        """
        self._state: ReaderState = ReaderState.IDLE
        self._buffer: ChunkBuffer = buffer or ChunkBuffer()
        self._compressed: bool = False
        self._total_chunks: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> ReaderState:
        """Current state."""
        return self._state

    @property
    def buffer(self) -> ChunkBuffer:
        """Underlying chunk buffer."""
        return self._buffer

    def handle_start(self, compressed: bool = False, total_chunks: int = 0) -> None:
        """Reset the session and transition to RECEIVING.

        Args:
            compressed: Whether the payload is compressed.
            total_chunks: Total number of chunks announced by sender (0 if unknown).
        """
        self._compressed = compressed
        self._total_chunks = total_chunks
        self._buffer.clear()
        self._state = ReaderState.RECEIVING

    def handle_end(self) -> bool:
        """Process an END_MARKER event.

        Transitions to DONE only when RECEIVING with at least one chunk.
        All other states (IDLE, DONE, or empty buffer) are silently ignored.

        Returns:
            True if the state transitioned to DONE (first valid END), False otherwise.
        """
        if self._state != ReaderState.RECEIVING or len(self._buffer) == 0:
            return False
        self._state = ReaderState.DONE
        return True

    def handle_chunk(self, seq_num: int, data: str) -> bool:
        """Process a sequenced data chunk.

        Args:
            seq_num: Sequence number from the chunk tag.
            data: Chunk content (without the sequence tag).

        Returns:
            True if the chunk was added (new), False if duplicate or in DONE state.
        """
        if self._state == ReaderState.DONE:
            return False
        if self._state == ReaderState.IDLE:
            self._state = ReaderState.RECEIVING
        was_added = self._buffer.add(seq_num, data)
        return was_added

    @property
    def is_compressed(self) -> bool:
        """Whether the current session uses compression."""
        return self._compressed

    @property
    def total_chunks(self) -> int:
        """Total chunks announced in START marker (0 if sender did not announce)."""
        return self._total_chunks

    def reset(self) -> None:
        """Force reset to IDLE with empty buffer."""
        self._state = ReaderState.IDLE
        self._buffer.clear()
        self._compressed = False
        self._total_chunks = 0

