"""QR Transfer - Chunk Management.

ChunkBuffer class encapsulates chunk storage, deduplication, and assembly.
Single responsibility, easily testable.
"""

class ChunkBuffer:
    """Manages incoming data chunks with deduplication and assembly.

    Stores chunks by sequence number, tracks recent sequences to avoid
    duplicates, and can assemble the complete message.

    Attributes:
        chunks: Dictionary mapping sequence numbers to chunk data.
        max_seq: Maximum sequence number received so far.
    """

    def __init__(self) -> None:
        """Initialize the chunk buffer."""
        self._chunks: dict[int, str] = {}
        self._min_seq: int = 0
        self._max_seq: int = 0

    def add(self, seq_num: int, data: str) -> bool:
        """Add a new chunk if not a duplicate.

        Args:
            seq_num: Sequence number of the chunk.
            data: Chunk content (without sequence tag).

        Returns:
            True if the chunk was added (new), False if duplicate.
        """
        if seq_num in self._chunks:
            return False
        self._chunks[seq_num] = data
        if self._min_seq == 0 or seq_num < self._min_seq:
            self._min_seq = seq_num
        if seq_num > self._max_seq:
            self._max_seq = seq_num
        return True

    def assemble(self) -> tuple[str, list[int]]:
        """Assemble the complete message from stored chunks.

        Returns:
            A tuple containing the full content string and a list of missing
            sequence indices (if any gaps exist in the sequence).
        """
        if not self._chunks:
            return "", []

        min_seq = self._min_seq
        parts: list[str] = []
        missing: list[int] = []

        for i in range(min_seq, self._max_seq + 1):
            if i in self._chunks:
                parts.append(self._chunks[i])
            else:
                missing.append(i)

        return "".join(parts), missing

    def clear(self) -> None:
        """Reset the buffer to empty state."""
        self._chunks.clear()
        self._min_seq = 0
        self._max_seq = 0

    @property
    def chunks(self) -> dict[int, str]:
        """Read-only access to stored chunks."""
        return self._chunks

    @property
    def min_seq(self) -> int:
        """Current minimum sequence number (0 if empty)."""
        return self._min_seq

    @property
    def max_seq(self) -> int:
        """Current maximum sequence number (0 if empty)."""
        return self._max_seq

    def __len__(self) -> int:
        """Number of stored chunks."""
        return len(self._chunks)
