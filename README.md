# AirGap Transfer

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](https://github.com)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.13+-orange)](https://opencv.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.10+-green)](https://www.riverbankcomputing.com/software/pyqt/)

Secure, offline data transfer between air-gapped systems using QR codes - no network required.

- **Sender**: standalone HTML5 app that encodes text into a sequence of QR codes
- **Reader**: Python desktop app that captures and reassembles them from the screen

```
┌─────────────────────┐        ┌────────────────────────────────────┐
│       SENDER        │        │               READER               │
│                     │        │                                    │
│  HTML Interface     │        │  MSS Screen Capture                │
│  → QRCode.js        │  QR    │  → Preprocessing (bilateral+CLAHE) │
│  → QR Generation    │ ~~~~►  │  → zxing-cpp Decoder               │
│  → Screen Display   │        │  → Protocol Parser                 │
│                     │        │  → Reassembly                      │
└─────────────────────┘        │  → Clipboard / File                │
                               └────────────────────────────────────┘
```

## Setup

> Reader only - Sender runs directly in the browser, no install needed.

```bash
# 1. Create and activate virtualenv
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt
```

## Usage

**Sender** - open `sender/index.html` in a browser:
1. Paste text, set Chunk Size and Speed, press **Start** (or `Ctrl+Enter`)
2. QR codes cycle automatically; **Stop** to cancel

**Reader** - run `python reader/main.py`:
1. Click **Select Area**, draw a rectangle around the Sender's QR display
2. Scanning starts automatically; output is copied to clipboard and saved to `qr_received.txt`

> Start the Reader **before** the Sender. If chunks are missed, re-run the Sender at a slower speed.

## Configuration

Key tunables in `reader/config.py` and `reader/core/qr_worker.py`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `upscale_factor` | 1.0 | Higher = better detection, more CPU |
| `min_delay_ms` | 10 | Higher = lower CPU, lower FPS |
| Chunk Size (Sender) | 200 | Lower = more reliable, more QR codes |
| Speed/ms (Sender) | 500 | Higher = Reader misses fewer frames |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` on start | `pip install -r requirements.txt` |
| No QR detected | Enlarge selection rectangle |
| Missing chunks | Increase Sender speed to 800–1000ms |
| High CPU | Increase `min_delay_ms` in `reader/config.py` |
| Screen capture fails (Windows) | Run as Administrator |
| Screen capture fails (macOS) | Grant screen recording in System Preferences |
| Screen capture fails (Linux/Wayland) | Grant screen capture permissions |

## Building the exe (Windows)

> Requires GNU `make` - install via `choco install make` or Scoop if not available.  
> Run with the venv active.

```bash
make build        # → reader/dist/QRReader.exe
```

The resulting exe is standalone - no Python needed on the target machine.

| Target | Description |
|--------|-------------|
| `make install` | Install Python dependencies |
| `make test` | Run the test suite |
| `make build` | Build `reader/dist/QRReader.exe` |
| `make clean` | Remove `reader/dist/` and `reader/build/` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing, and commit conventions.

## License

MIT - see [LICENSE](LICENSE).
