import subprocess
import json
import sys


AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".flac",
    ".wav",
    ".aiff",
    ".aif",
    ".wma",
    ".mp4",
    ".3gp",
    ".webm",
}

# Quality score constants
SCORE_LOSSLESS = 50
SCORE_OPUS = 35
SCORE_AAC = 35
SCORE_MP3 = 30
SCORE_OGG = 25
SCORE_OTHER = 10

SCORE_BITRATE_HIGH = 30  # >= 320 kbps
SCORE_BITRATE_GOOD = 25  # >= 256 kbps
SCORE_BITRATE_MEDIUM = 20  # >= 192 kbps
SCORE_BITRATE_LOW = 15  # >= 128 kbps
SCORE_BITRATE_MIN = 5  # < 128 kbps

SCORE_SAMPLE_RATE_HIGH = 20  # >= 96 kHz
SCORE_SAMPLE_RATE_GOOD = 15  # >= 48 kHz
SCORE_SAMPLE_RATE_MEDIUM = 10  # >= 44.1 kHz
SCORE_SAMPLE_RATE_MIN = 5  # < 44.1 kHz

# Size scoring: 1 point per 100MB, capped at 50 points
SIZE_SCORE_DIVISOR = 100 * 1024 * 1024  # 100 MB
SIZE_SCORE_MAX = 50


def check_dependencies():
    """Check if required external tools are available."""
    missing = []

    try:
        subprocess.run(["fpcalc", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        missing.append("fpcalc (libchromaprint-tools)")

    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        missing.append("ffprobe (ffmpeg)")

    if missing:
        print("Error: Missing external dependencies.")
        print(f"Required tools not found: {', '.join(missing)}")
        print("\nPlease install them using your package manager:")
        print("  sudo apt install libchromaprint-tools ffmpeg")
        sys.exit(1)


def get_fingerprint(filepath):
    """Generate acoustic fingerprint using fpcalc."""
    try:
        result = subprocess.run(
            ["fpcalc", "-length", "120", "-raw", "-json", filepath],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        # Return fingerprint as a list of integers
        return data.get("fingerprint", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return []


def get_audio_metadata(filepath):
    """Extract audio metadata using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_format",
                "-show_streams",
                "-select_streams",
                "a:0",
                "-of",
                "json",
                filepath,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        format_info = data.get("format", {})
        audio_stream = data.get("streams", [{}])[0]

        return {
            "filename": format_info.get("filename", ""),
            "duration": int(float(format_info.get("duration", 0))),
            "bitrate": int(format_info.get("bit_rate", 0)),
            "sample_rate": int(audio_stream.get("sample_rate", 0)),
            "codec": audio_stream.get("codec_name", "unknown"),
        }
    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        ValueError,
    ):
        return {
            "filename": "",
            "duration": 0,
            "bitrate": 0,
            "sample_rate": 0,
            "codec": "unknown",
        }


def format_size(size):
    """Format file size in human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def get_quality_score(ext, size, bitrate, sample_rate):
    """Calculate quality score for audio files."""
    score = 0

    # Normalize extension (remove dot and convert to lowercase)
    ext_normalized = ext.lower().lstrip(".")

    # Format scoring (lossless gets bonus)
    lossless_formats = {"flac", "wav", "aiff", "aif"}
    if ext_normalized in lossless_formats:
        score += SCORE_LOSSLESS
    elif ext_normalized == "opus":
        score += SCORE_OPUS
    elif ext_normalized in {"m4a", "aac"}:
        score += SCORE_AAC
    elif ext_normalized == "mp3":
        score += SCORE_MP3
    elif ext_normalized == "ogg":
        score += SCORE_OGG
    else:
        score += SCORE_OTHER

    # Bitrate scoring
    if bitrate:
        if bitrate >= 320000:
            score += SCORE_BITRATE_HIGH
        elif bitrate >= 256000:
            score += SCORE_BITRATE_GOOD
        elif bitrate >= 192000:
            score += SCORE_BITRATE_MEDIUM
        elif bitrate >= 128000:
            score += SCORE_BITRATE_LOW
        else:
            score += SCORE_BITRATE_MIN

    # Sample rate scoring
    if sample_rate:
        if sample_rate >= 96000:
            score += SCORE_SAMPLE_RATE_HIGH
        elif sample_rate >= 48000:
            score += SCORE_SAMPLE_RATE_GOOD
        elif sample_rate >= 44100:
            score += SCORE_SAMPLE_RATE_MEDIUM
        else:
            score += SCORE_SAMPLE_RATE_MIN

    # File size as last resort (larger is usually better)
    # 1 point per 100MB, capped at 50 points
    score += min(size / SIZE_SCORE_DIVISOR, SIZE_SCORE_MAX)

    return score
