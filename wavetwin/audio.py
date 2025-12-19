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


def check_dependencies():
    """Check if required external tools are available."""
    try:
        subprocess.run(["fpcalc", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("Error: fpcalc (chromaprint) is required but not found in PATH")

    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("Error: ffprobe (ffmpeg) is required but not found in PATH")


def get_fingerprint(filepath):
    """Generate acoustic fingerprint using fpcalc."""
    try:
        result = subprocess.run(
            ["fpcalc", "-length", "120", "-json", filepath],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return data.get("fingerprint", "")
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return ""


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

    # Format scoring (lossless gets bonus)
    lossless_formats = {"flac", "wav", "aiff", "aif"}
    if ext.lower() in lossless_formats:
        score += 50
    elif ext.lower() in {"m4a", "aac"}:
        score += 35
    elif ext.lower() == "mp3":
        score += 30
    elif ext.lower() in {"ogg", "opus"}:
        score += 25
    else:
        score += 10

    # Bitrate scoring
    if bitrate:
        if bitrate >= 320000:
            score += 30
        elif bitrate >= 256000:
            score += 25
        elif bitrate >= 192000:
            score += 20
        elif bitrate >= 128000:
            score += 15
        else:
            score += 5

    # Sample rate scoring
    if sample_rate:
        if sample_rate >= 96000:
            score += 20
        elif sample_rate >= 48000:
            score += 15
        elif sample_rate >= 44100:
            score += 10
        else:
            score += 5

    # File size as last resort (larger is usually better)
    score += min(size / (1024 * 1024), 20)  # Max 20 points for size

    return score
