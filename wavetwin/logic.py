import os
import datetime
import json
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

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

    # First count total files for progress bar
    total_files = sum(
        1
        for root, dirs, files in os.walk(search_dir)
        for name in files
        if not name.startswith(".")
        and os.path.splitext(name)[1].lower() in audio_extensions
    )

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
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
                        pbar.update(1)
                    except OSError:
                        pbar.update(1)
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

        # Process results as they complete with progress bar
        with tqdm(total=total, desc="Processing files", unit="file") as pbar:
            for future in as_completed(future_to_file):
                track_id, path = future_to_file[future]

                try:
                    success, file_path, error_type, error_msg = future.result()

                    if not success:
                        tqdm.write(f"Error: [{error_type}] {file_path}")
                        failed_files.append((file_path, error_type, error_msg))
                        errors += 1

                except Exception as e:
                    # This catches any unexpected errors in the worker thread
                    tqdm.write(
                        f"Error: Unexpected error processing {path}: {type(e).__name__}: {e}"
                    )
                    failed_files.append((path, type(e).__name__, str(e)))
                    errors += 1

                pbar.update(1)

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


# Similarity thresholds for duplicate detection
SIMILARITY_THRESHOLD = 0.80
SIMILARITY_QUICK_THRESHOLD = 0.6
DURATION_TOLERANCE_SECONDS = 3.0


def _parse_fingerprint_row(row):
    """Parse a single fingerprint row from database."""
    try:
        track_id, path, name, size, duration, fp_str, bitrate, sample_rate = row
        if not fp_str:
            return None
        # Handle potential empty strings or nulls
        fp_list = [int(x) for x in fp_str.split(",") if x.strip()]
        if not fp_list:
            return None
        return {
            "id": track_id,
            "data": (path, name, size, bitrate, duration),
            "sample_rate": sample_rate,
            "fingerprint": fp_list,
            "duration": duration,
        }
    except Exception:
        return None


def _are_fingerprints_similar(fp1, fp2):
    """Check if two fingerprints are similar enough to be duplicates."""
    matcher = SequenceMatcher(None, fp1, fp2)

    # Quick check first
    if matcher.quick_ratio() < SIMILARITY_QUICK_THRESHOLD:
        return False

    return matcher.ratio() > SIMILARITY_THRESHOLD


def _find_duplicate_group(item, all_items, start_index, processed_ids):
    """Find all duplicates for a given item."""
    group = [item]

    for j in range(start_index + 1, len(all_items)):
        item2 = all_items[j]

        # Since rows are sorted by duration, stop if difference is too large
        if item2["duration"] - item["duration"] > DURATION_TOLERANCE_SECONDS:
            break

        if item2["id"] in processed_ids:
            continue

        # Similarity check
        if _are_fingerprints_similar(item["fingerprint"], item2["fingerprint"]):
            group.append(item2)
            processed_ids.add(item2["id"])

    return group


def analysis_phase(conn):
    """Analyze database for duplicates."""
    print("Analyzing for duplicates...")

    # Get all processed tracks
    # Row format: id, path, filename, size, duration, fingerprint, bitrate, sample_rate
    rows = get_all_fingerprints(conn)

    if not rows:
        return []

    # Parse fingerprints once
    parsed_rows = [_parse_fingerprint_row(row) for row in rows]
    parsed_rows = [row for row in parsed_rows if row is not None]

    groups = []
    processed_ids = set()
    total = len(parsed_rows)

    with tqdm(total=total, desc="Analyzing duplicates", unit="track") as pbar:
        for i in range(total):
            item = parsed_rows[i]
            pbar.update(1)

            if item["id"] in processed_ids:
                continue

            group = _find_duplicate_group(item, parsed_rows, i, processed_ids)

            if len(group) > 1:
                processed_ids.add(item["id"])
                groups.append(group)

    return groups
