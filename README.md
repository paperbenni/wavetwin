# Wavetwin

Remove duplicates from your music library using acoustic fingerprinting.

## Installation

```bash
uv tool install wavetwin
```

## Usage

```bash
wavetwin /path/to/music
```

## Requirements

- `fpcalc` (chromaprint) - for audio fingerprinting
- `ffprobe` (ffmpeg) - for metadata extraction

Install with:
```bash
# Ubuntu/Debian
sudo apt install libchromaprint-tools ffmpeg

# macOS
brew install chromaprint ffmpeg

# Other systems
# Install via your package manager
```

## Features

- Acoustic fingerprinting for accurate duplicate detection
- Resumable scanning (progress saved to database)
- Quality-based recommendations
- Detailed HTML reports
- Supports most audio formats
