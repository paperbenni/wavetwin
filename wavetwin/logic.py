import os
import datetime
from difflib import SequenceMatcher

try:
    from wavetwin.audio import get_fingerprint, get_audio_metadata, get_quality_score
    from wavetwin.database import (
        get_unprocessed_files,
        update_track_processing,
        add_file_if_needed,
        get_duplicate_groups,
    )
except ImportError:
    from audio import get_fingerprint, get_audio_metadata, get_quality_score
    from database import (
        get_unprocessed_files,
        update_track_processing,
        add_file_if_needed,
        get_duplicate_groups,
    )


def scan_phase(conn, search_dir, audio_extensions):
    """Scan directory for audio files and update database."""
    print(f"Scanning {search_dir}...")
    count = 0

    for root, _, files in os.walk(search_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in audio_extensions:
                path = os.path.abspath(os.path.join(root, name))
                try:
                    stat = os.stat(path)
                    add_file_if_needed(conn, path, stat.st_size, stat.st_mtime)
                    count += 1
                except OSError:
                    continue

    print(f"Found {count} audio files.")


def process_files(conn):
    """Process files that need fingerprinting."""
    files = get_unprocessed_files(conn)
    total = len(files)

    if total == 0:
        print("No new files to process.")
        return

    print(f"Processing {total} files...")
    for i, (track_id, path, size, mtime) in enumerate(files, 1):
        try:
            print(f"[{i}/{total}] Analyzing: {os.path.basename(path)}")
            fingerprint = get_fingerprint(path)
            metadata = get_audio_metadata(path)

            # Ensure metadata has all required fields
            if "filename" not in metadata or not metadata["filename"]:
                metadata["filename"] = os.path.basename(path)

            update_track_processing(conn, track_id, fingerprint, metadata)
        except Exception as e:
            print(f"Error processing {path}: {e}")


def find_best_match(group):
    """Find the highest quality file in a group of duplicates."""
    best_score = -1
    best_entry = None

    for entry in group:
        path, name, size, bitrate, dur = entry["data"]
        # Retrieve sample_rate from extra data if available, otherwise default
        sample_rate = entry.get("sample_rate", 44100)

        ext = os.path.splitext(path)[1].upper().replace(".", "")

        score = get_quality_score(ext, size, bitrate, sample_rate)

        entry["quality_score"] = score
        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry


def analysis_phase(conn):
    """Analyze database for duplicates."""
    print("Analyzing for duplicates...")

    # Get all files that have duplicates (ordered by fingerprint)
    # Row format: path, filename, size, duration, fingerprint, bitrate, sample_rate
    rows = get_duplicate_groups(conn)

    if not rows:
        return []

    groups = []
    current_group = []
    current_fp = None

    for row in rows:
        path, name, size, duration, fingerprint, bitrate, sample_rate = row

        if fingerprint != current_fp:
            if current_group:
                groups.append(current_group)
            current_group = []
            current_fp = fingerprint

        # Structure compatible with report generation
        entry = {
            "data": (path, name, size, bitrate, duration),
            "sample_rate": sample_rate,
            "fingerprint": fingerprint,
        }
        current_group.append(entry)

    if current_group:
        groups.append(current_group)

    return groups
