# Wavetwin

Remove duplicates from your music library using acoustic fingerprinting.

## Installation

Run directly from the git repository with uvx:

```bash
uvx https://github.com/paperbenni/wavetwin.git /path/to/music
```

Or install the tool:

```bash
uv tool install git+https://github.com/paperbenni/wavetwin.git
wavetwin /path/to/music
```

## Usage

```bash
uvx https://github.com/paperbenni/wavetwin.git /path/to/music
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
