"""Unit tests for ChunkBuffer.

Tests cover chunk addition, deduplication, assembly, clearing, and properties.
"""

import unittest

from reader.core.chunk_manager import ChunkBuffer


class TestChunkBuffer(unittest.TestCase):
    """Test suite for ChunkBuffer class."""

    def test_add_new_chunk(self):
        """Adding a new chunk stores it and returns True."""
        buffer = ChunkBuffer()
        result = buffer.add(1, "A")
        self.assertTrue(result)
        self.assertEqual(buffer.chunks[1], "A")
        self.assertEqual(buffer.max_seq, 1)
        self.assertEqual(len(buffer), 1)

    def test_add_duplicate_chunk(self):
        """Duplicate chunk is ignored and returns False."""
        buffer = ChunkBuffer()
        buffer.add(1, "A")
        result = buffer.add(1, "A")
        self.assertFalse(result)
        self.assertEqual(len(buffer), 1)
        self.assertEqual(buffer.chunks[1], "A")

    def test_add_updates_max_seq(self):
        """max_seq updates when a higher sequence number is added."""
        buffer = ChunkBuffer()
        buffer.add(5, "E")
        self.assertEqual(buffer.max_seq, 5)
        buffer.add(3, "C")
        self.assertEqual(buffer.max_seq, 5)
        buffer.add(10, "J")
        self.assertEqual(buffer.max_seq, 10)

    def test_assemble_sequential(self):
        """assemble returns concatenated chunks in order."""
        buffer = ChunkBuffer()
        buffer.add(1, "A")
        buffer.add(2, "B")
        buffer.add(3, "C")
        content, missing = buffer.assemble()
        self.assertEqual(content, "ABC")
        self.assertEqual(missing, [])

    def test_assemble_with_missing(self):
        """assemble skips missing chunks and reports them in missing list."""
        buffer = ChunkBuffer()
        buffer.add(1, "A")
        buffer.add(3, "C")
        buffer.add(4, "D")
        content, missing = buffer.assemble()
        self.assertEqual(content, "ACD")  # missing chunk 2 is skipped, not inserted
        self.assertEqual(missing, [2])

    def test_assemble_empty(self):
        """assemble returns empty string and no missing when buffer is empty."""
        buffer = ChunkBuffer()
        content, missing = buffer.assemble()
        self.assertEqual(content, "")
        self.assertEqual(missing, [])

    def test_clear(self):
        """clear resets buffer to empty state."""
        buffer = ChunkBuffer()
        buffer.add(1, "A")
        buffer.add(2, "B")
        buffer.clear()
        self.assertEqual(len(buffer), 0)
        self.assertEqual(buffer.min_seq, 0)
        self.assertEqual(buffer.max_seq, 0)
        self.assertEqual(buffer.chunks, {})

    def test_min_seq_empty(self):
        """min_seq is 0 on empty buffer."""
        buffer = ChunkBuffer()
        self.assertEqual(buffer.min_seq, 0)

    def test_min_seq_single(self):
        """min_seq equals the only sequence number when one chunk is added."""
        buffer = ChunkBuffer()
        buffer.add(7, "G")
        self.assertEqual(buffer.min_seq, 7)

    def test_min_seq_multiple(self):
        """min_seq tracks the lowest sequence number across all additions."""
        buffer = ChunkBuffer()
        buffer.add(5, "E")
        self.assertEqual(buffer.min_seq, 5)
        buffer.add(3, "C")
        self.assertEqual(buffer.min_seq, 3)
        buffer.add(10, "J")
        self.assertEqual(buffer.min_seq, 3)  # Must not increase.

    def test_min_seq_resets_on_clear(self):
        """min_seq returns 0 after clear."""
        buffer = ChunkBuffer()
        buffer.add(4, "D")
        buffer.clear()
        self.assertEqual(buffer.min_seq, 0)


if __name__ == "__main__":
    unittest.main()
