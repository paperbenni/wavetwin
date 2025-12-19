import os
import datetime
import json
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed

from wavetwin.audio import get_fingerprint, get_audio_metadata, get_quality_score
from wavetwin.database import (
    get_unprocessed_files,
    update_track_processing,
    add_file_if_needed,
    get_all_fingerprints,
)

# Number of worker threads for parallel processing
MAX_WORKERS = 2


def scan_phase(conn, search_dir, audio_extensions):
    """Scan directory for audio files and update database."""
    print(f"Scanning {search_dir}...")
    count = 0

    for root, dirs, files in os.walk(search_dir):
        # Ignore hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for name in files:
            # Ignore hidden files
            if name.startswith("."):
                continue

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


def _process_single_file(track_id, path, size, mtime, conn):
    """Process a single file and return result."""
    try:
        fingerprint_list = get_fingerprint(path)
        metadata = get_audio_metadata(path)

        # Ensure metadata has all required fields
        if "filename" not in metadata or not metadata["filename"]:
            metadata["filename"] = os.path.basename(path)

        # Convert fingerprint list to comma-separated string for storage
        fingerprint_str = ",".join(map(str, fingerprint_list))

        # Database writes are thread-safe (handled in database.py)
        update_track_processing(conn, track_id, fingerprint_str, metadata)

        return (True, path, None, None)
    except FileNotFoundError as e:
        return (False, path, "FileNotFoundError", str(e))
    except PermissionError as e:
        return (False, path, "PermissionError", str(e))
    except Exception as e:
        return (False, path, type(e).__name__, str(e))


def process_files(conn, search_dir=None):
    """Process files that need fingerprinting with multithreading."""
    files = get_unprocessed_files(conn, search_dir)
    total = len(files)
    errors = 0
    failed_files = []
    processed_count = 0

    if total == 0:
        print("No new files to process.")
        return 0

    print(f"Processing {total} files with {MAX_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all files for processing
        future_to_file = {
            executor.submit(_process_single_file, track_id, path, size, mtime, conn): (
                track_id,
                path,
            )
            for track_id, path, size, mtime in files
        }

        # Process results as they complete
        for future in as_completed(future_to_file):
            track_id, path = future_to_file[future]
            processed_count += 1

            try:
                success, file_path, error_type, error_msg = future.result()

                print(
                    f"[{processed_count}/{total}] Analyzed: {os.path.basename(file_path)}"
                )

                if not success:
                    print(f"Error: [{error_type}] {file_path}")
                    failed_files.append((file_path, error_type, error_msg))
                    errors += 1

            except Exception as e:
                # This catches any unexpected errors in the worker thread
                print(
                    f"Error: Unexpected error processing {path}: {type(e).__name__}: {e}"
                )
                failed_files.append((path, type(e).__name__, str(e)))
                errors += 1

    if failed_files:
        print("\n--- Processing Errors Summary ---")
        for path, error_type, error_msg in failed_files:
            print(f"  [{error_type}] {path}")
            print(f"    {error_msg}")

    return errors


def find_best_match(group):
    """Find the highest quality file in a group of duplicates."""
    best_score = -1
    best_entry = None

    for entry in group:
        path, name, size, bitrate, dur = entry["data"]
        # Retrieve sample_rate from extra data if available, otherwise default
        sample_rate = entry.get("sample_rate", 44100)

        ext = os.path.splitext(path)[1]

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
