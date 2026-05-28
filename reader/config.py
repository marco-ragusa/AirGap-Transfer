"""QR Transfer - Configuration."""

import pathlib
import re
from typing import Final

# Protocol - START markers include total chunk count: __QR_START_N__ / __QR_START_COMP_N__
START_PATTERN: Final[re.Pattern] = re.compile(r"^__QR_START_(\d+)__$")
START_COMPRESSED_PATTERN: Final[re.Pattern] = re.compile(r"^__QR_START_COMP_(\d+)__$")
END_MARKER: Final[str] = "__QR_END__"
SEQ_PATTERN: Final[re.Pattern] = re.compile(r"__QR_SEQ_(\d+)__$")

# Output - absolute path, no CWD ambiguity
LOG_FILE: Final[pathlib.Path] = pathlib.Path.home() / "qr_received.txt"

# Worker defaults - upscale_factor>1.0 helps small QRs from remote/compressed sources
DEFAULT_UPSCALE_FACTOR: Final[float] = 1.0
DEFAULT_MIN_DELAY_MS: Final[int] = 10

# Timing
STATS_UPDATE_INTERVAL: Final[float] = 0.5
THREAD_JOIN_TIMEOUT_MS: Final[int] = 2000
