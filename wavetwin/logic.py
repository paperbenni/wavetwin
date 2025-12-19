import os
import datetime
import json
from difflib import SequenceMatcher

try:
    from wavetwin.audio import get_fingerprint, get_audio_metadata, get_quality_score
    from wavetwin.database import (
        get_unprocessed_files,
        update_track_processing,
        add_file_if_needed,
        get_all_fingerprints,
    )
except ImportError:
    from audio import get_fingerprint, get_audio_metadata, get_quality_score
    from database import (
        get_unprocessed_files,
        update_track_processing,
        add_file_if_needed,
        get_all_fingerprints,
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
    errors = 0

    if total == 0:
        print("No new files to process.")
        return 0

    print(f"Processing {total} files...")
    for i, (track_id, path, size, mtime) in enumerate(files, 1):
        try:
            print(f"[{i}/{total}] Analyzing: {os.path.basename(path)}")
            fingerprint_list = get_fingerprint(path)
            metadata = get_audio_metadata(path)

            # Ensure metadata has all required fields
            if "filename" not in metadata or not metadata["filename"]:
                metadata["filename"] = os.path.basename(path)

            # Convert fingerprint list to comma-separated string for storage
            fingerprint_str = ",".join(map(str, fingerprint_list))

            update_track_processing(conn, track_id, fingerprint_str, metadata)
        except Exception as e:
            print(f"Error processing {path}: {e}")
            errors += 1

    return errors


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

    # Get all processed tracks
    # Row format: id, path, filename, size, duration, fingerprint, bitrate, sample_rate
    rows = get_all_fingerprints(conn)

    if not rows:
        return []

    # Parse fingerprints once
    parsed_rows = []
    for row in rows:
        try:
            track_id, path, name, size, duration, fp_str, bitrate, sample_rate = row
            if not fp_str:
                continue
            # Handle potential empty strings or nulls
            fp_list = [int(x) for x in fp_str.split(",") if x.strip()]
            if not fp_list:
                continue
            parsed_rows.append(
                {
                    "id": track_id,
                    "data": (path, name, size, bitrate, duration),
                    "sample_rate": sample_rate,
                    "fingerprint": fp_list,
                    "duration": duration,
                }
            )
        except Exception:
            continue

    groups = []
    processed_ids = set()
    total = len(parsed_rows)

    for i in range(total):
        item1 = parsed_rows[i]
        if item1["id"] in processed_ids:
            continue

        current_group = [item1]

        for j in range(i + 1, total):
            item2 = parsed_rows[j]

            # Since rows are sorted by duration, we can stop if difference is too large
            # Allow 3 seconds difference (slightly generous)
            if item2["duration"] - item1["duration"] > 3.0:
                break

            if item2["id"] in processed_ids:
                continue

            # Similarity check
            matcher = SequenceMatcher(None, item1["fingerprint"], item2["fingerprint"])

            # Quick check first
            if matcher.quick_ratio() < 0.6:
                continue

            if matcher.ratio() > 0.80:
                current_group.append(item2)
                processed_ids.add(item2["id"])

        if len(current_group) > 1:
            processed_ids.add(item1["id"])
            groups.append(current_group)

    return groups
