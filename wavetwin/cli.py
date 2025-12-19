#!/usr/bin/env python3
import os
import subprocess
import json
import sys
import sqlite3
import datetime
import argparse
from difflib import SequenceMatcher

# Extensions to scan
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


def init_db(db_file):
    """Initialize SQLite database for storing fingerprints."""
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    # Enable Write-Ahead Logging for concurrency/stability
    c.execute("PRAGMA journal_mode=WAL;")

    # Table to store file info
    c.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            filename TEXT,
            size INTEGER,
            mtime REAL,
            duration INTEGER,
            fingerprint TEXT,
            bitrate INTEGER,
            sample_rate INTEGER,
            codec TEXT,
            processed INTEGER DEFAULT 0
        )
    """)

    # Index for fast lookups by duration (crucial for analysis phase)
    c.execute("CREATE INDEX IF NOT EXISTS idx_duration ON tracks(duration);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_path ON tracks(path);")

    conn.commit()
    return conn


def get_fingerprint(filepath):
    """Run fpcalc -raw."""
    try:
        cmd = ["fpcalc", "-raw", filepath]
        # Set a timeout to prevent hanging on corrupt files
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            return None, None

        output = result.stdout.strip()
        duration = 0
        fingerprint = []

        for line in output.split("\n"):
            if line.startswith("DURATION="):
                try:
                    duration = int(float(line.split("=")[1]))
                except ValueError:
                    duration = 0
            elif line.startswith("FINGERPRINT="):
                fp_str = line.split("=")[1]
                if fp_str:
                    # Store as comma-separated string in DB to save space/complexity
                    fingerprint = fp_str

        return duration, fingerprint
    except (subprocess.TimeoutExpired, Exception):
        return None, None


def get_audio_metadata(filepath):
    """Get metadata using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "a:0",
            filepath,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        if not data.get("streams"):
            return None

        stream = data["streams"][0]
        bit_rate = stream.get("bit_rate")

        if not bit_rate:
            cmd_fmt = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                filepath,
            ]
            res_fmt = subprocess.run(
                cmd_fmt, capture_output=True, text=True, timeout=30
            )
            if res_fmt.returncode == 0:
                fmt_data = json.loads(res_fmt.stdout)
                bit_rate = fmt_data.get("format", {}).get("bit_rate", 0)

        return {
            "bit_rate": int(bit_rate) if bit_rate else 0,
            "sample_rate": int(stream.get("sample_rate", 0)),
            "codec": stream.get("codec_name", "unknown"),
        }
    except Exception:
        return None


def check_dependencies():
    deps = []
    try:
        subprocess.run(["fpcalc", "-v"], capture_output=True, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        deps.append("fpcalc (chromaprint)")
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        deps.append("ffprobe (ffmpeg)")
    return deps


def format_size(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def get_quality_score(ext, size, bitrate, sample_rate):
    if ext in [".flac", ".wav", ".aiff", ".aif", ".alac"]:
        base_score = 10000
    elif ext in [".opus", ".m4a", ".aac"]:
        base_score = 5000
    elif ext in [".mp3", ".ogg"]:
        base_score = 3000
    else:
        base_score = 1000

    score = base_score
    if bitrate:
        score += min(bitrate / 1000, 1500)
    if sample_rate:
        score += sample_rate / 1000
    score += size / (1024 * 1024)  # Size in MB
    return score


def scan_phase(conn, search_dir):
    print("\n--- PHASE 1: Scanning & Indexing ---")
    print(f"Directory: {search_dir}")
    print("This process is resumable. If stopped, run again to continue.")

    files_to_process = []
    print("Listing files (this might take a moment)...")

    for root, _, files in os.walk(search_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                path = os.path.join(root, file)
                files_to_process.append(path)

    print(f"Total audio files found on disk: {len(files_to_process)}")

    c = conn.cursor()

    # Check what's already done
    c.execute("SELECT path, mtime FROM tracks")
    existing_db = {row[0]: row[1] for row in c.fetchall()}

    processed_count = 0
    skipped_count = 0

    for i, path in enumerate(files_to_process):
        try:
            stat = os.stat(path)
            current_mtime = stat.st_mtime
            current_size = stat.st_size

            # Skip if file exists and mtime hasn't changed
            if path in existing_db and existing_db[path] == current_mtime:
                skipped_count += 1
                continue

            print(
                f"[{i + 1}/{len(files_to_process)}] Indexing: {os.path.basename(path)}"
            )

            # Process file
            dur, fp = get_fingerprint(path)
            if dur is None or not fp:
                print(f"  ⚠️  Failed to fingerprint: {os.path.basename(path)}")
                continue

            meta = get_audio_metadata(path) or {}

            # Insert or Replace into DB
            c.execute(
                """
                INSERT OR REPLACE INTO tracks 
                (path, filename, size, mtime, duration, fingerprint, bitrate, sample_rate, codec, processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
                (
                    path,
                    os.path.basename(path),
                    current_size,
                    current_mtime,
                    dur,
                    fp,
                    meta.get("bit_rate", 0),
                    meta.get("sample_rate", 0),
                    meta.get("codec", "unknown"),
                ),
            )

            processed_count += 1

            # Commit every 50 files to save progress and protect against crashes
            if processed_count % 50 == 0:
                conn.commit()

        except Exception as e:
            print(f"  ❌ Error processing {path}: {e}")

    conn.commit()
    print(
        f"\nIndexing complete. Processed: {processed_count}, Skipped (Already Indexed): {skipped_count}"
    )


def analysis_phase(conn):
    print("\n--- PHASE 2: Duplicate Analysis ---")
    print("Querying database (RAM efficient)...")

    c = conn.cursor()

    # Get list of all durations present in DB
    # We only fetch distinct durations to loop through them
    c.execute(
        "SELECT DISTINCT duration FROM tracks WHERE duration > 0 ORDER BY duration"
    )
    durations = [row[0] for row in c.fetchall()]

    groups = []
    processed_ids = set()

    total_durs = len(durations)

    # Iterate through durations (Time-based Windowing)
    # This ensures we only load a tiny subset of fingerprints into RAM at once
    for idx, dur in enumerate(durations):
        print(f"Analyzing time bucket: {dur}s ({idx + 1}/{total_durs})", end="\r")

        # Select files within +/- 2 seconds of current duration
        c.execute(
            """
            SELECT id, path, fingerprint, duration 
            FROM tracks 
            WHERE duration BETWEEN ? AND ?
        """,
            (dur - 2, dur + 2),
        )

        candidates = c.fetchall()
        if len(candidates) < 2:
            continue

        # Parse fingerprints for this batch
        # candidates_data = [ (id, path, [int list]) ]
        batch_data = []
        for row in candidates:
            try:
                # Convert comma-string back to list of ints
                fp_list = [int(x) for x in row[2].split(",")]
                batch_data.append(
                    {"id": row[0], "path": row[1], "fp": fp_list, "dur": row[3]}
                )
            except Exception:
                continue

        # Compare within this batch
        for i in range(len(batch_data)):
            item1 = batch_data[i]
            if item1["id"] in processed_ids:
                continue

            current_group = [item1["id"]]

            for j in range(i + 1, len(batch_data)):
                item2 = batch_data[j]
                if item2["id"] in processed_ids:
                    continue

                # Double check: ignore if duration difference is too big (DB selection covers this, but safe check)
                if abs(item1["dur"] - item2["dur"]) > 2:
                    continue

                # Similarity check
                matcher = SequenceMatcher(None, item1["fp"], item2["fp"])
                if matcher.quick_ratio() < 0.6:
                    continue

                if matcher.ratio() > 0.80:
                    current_group.append(item2["id"])
                    processed_ids.add(item2["id"])

            if len(current_group) > 1:
                processed_ids.add(item1["id"])
                # Fetch full details for the group
                # Hack to create sql IN clause
                sql = f"SELECT path, filename, size, bitrate, duration FROM tracks WHERE id IN ({','.join('?' * len(current_group))})"
                c.execute(sql, tuple(current_group))
                groups.append(c.fetchall())

    print(f"\nAnalysis complete. Found {len(groups)} groups of duplicates.")
    return groups


def generate_report(groups, report_file):
    print(f"Generating report: {report_file}")
    with open(report_file, "w") as f:
        f.write("# 🎵 Audio Duplicates Report\n\n")
        f.write(f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Duplicate Groups Found:** {len(groups)}\n\n")
        f.write("---\n\n")

        for i, group in enumerate(groups, 1):
            f.write(f"## 📁 Group {i} ({len(group)} files)\n\n")

            # Calculate scores
            scored_files = []
            for item in group:
                path, name, size, bitrate, dur = item
                ext = os.path.splitext(path)[1].lower()
                # bitrate can be 0/None
                br = bitrate if bitrate else 0
                score = get_quality_score(ext, size, br, 0)
                scored_files.append({"data": item, "score": score})

            scored_files.sort(key=lambda x: x["score"], reverse=True)
            best = scored_files[0]["data"]
            best_path, best_name, best_size, best_br, _ = best

            # Recommendation
            f.write(f"### 🌟 Recommendation: Keep `{best_name}`\n")
            if best_br:
                f.write(
                    f"**Quality:** {int(best_br / 1000)} kbps | {format_size(best_size)}\n\n"
                )
            else:
                f.write(f"**Quality:** {format_size(best_size)}\n\n")

            # Define fixed column widths
            col_widths = {
                "keep": 6,
                "filename": 30,
                "format": 8,
                "bitrate": 10,
                "size": 8,
                "duration": 10,
                "path": 40,
            }

            f.write(
                f"| {'Keep':^{col_widths['keep']}} | {'Filename':^{col_widths['filename']}} | {'Format':^{col_widths['format']}} | {'Bitrate':^{col_widths['bitrate']}} | {'Size':^{col_widths['size']}} | {'Duration':^{col_widths['duration']}} | {'Path':^{col_widths['path']}} |\n"
            )
            f.write(
                f"| {'':-^{col_widths['keep']}} | {'':-^{col_widths['filename']}} | {'':-^{col_widths['format']}} | {'':-^{col_widths['bitrate']}} | {'':-^{col_widths['size']}} | {'':-^{col_widths['duration']}} | {'':-^{col_widths['path']}} |\n"
            )

            for entry in scored_files:
                path, name, size, bitrate, dur = entry["data"]
                ext = os.path.splitext(path)[1].upper().replace(".", "")
                br_str = f"{int(bitrate / 1000)} kbps" if bitrate else "Unknown"
                keep_mark = "✅" if entry["data"] == best else "❌"

                # Truncate long content and pad to fixed width
                name_display = f"**{name}**"
                if len(name_display) > col_widths["filename"]:
                    name_display = f"**{name[: col_widths['filename'] - 7]}...**"

                path_display = f"`{path}`"
                if len(path_display) > col_widths["path"]:
                    path_display = f"`{path[: col_widths['path'] - 10]}...`"

                f.write(
                    f"| {keep_mark:^{col_widths['keep']}} | {name_display:<{col_widths['filename']}} | {ext:<{col_widths['format']}} | {br_str:<{col_widths['bitrate']}} | {format_size(size):<{col_widths['size']}} | {f'{dur}s':<{col_widths['duration']}} | {path_display:<{col_widths['path']}} |\n"
                )

            f.write("\n---\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Robust Audio Duplicate Detector using acoustic fingerprinting (fpcalc/chromaprint).",
        epilog="Examples:\n  python3 script.py /mnt/music\n  python3 script.py /mnt/read_only_music --db my_scan.db --report duplicates.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--db",
        default="music_scan.db",
        help="Path to SQLite database file (default: music_scan.db)",
    )
    parser.add_argument(
        "--report",
        default="duplicates_report.md",
        help="Path to output Markdown report (default: duplicates_report.md)",
    )

    args = parser.parse_args()

    missing = check_dependencies()
    if missing:
        print(f"Error: Missing dependencies: {', '.join(missing)}")
        print(
            "Please install them using your package manager (e.g., sudo apt install libchromaprint-tools ffmpeg)"
        )
        sys.exit(1)

    # Resolve absolute paths
    search_dir = os.path.abspath(args.directory)
    db_file = os.path.abspath(args.db)
    report_file = os.path.abspath(args.report)

    if not os.path.isdir(search_dir):
        print(f"Error: Directory not found: {search_dir}")
        sys.exit(1)

    print(f"Scan Directory: {search_dir}")
    print(f"Database File:  {db_file}")
    print(f"Report File:    {report_file}")

    conn = init_db(db_file)

    try:
        # Phase 1: Scan (Resumable)
        scan_phase(conn, search_dir)

        # Phase 2: Analyze (Low RAM)
        duplicates = analysis_phase(conn)

        # Phase 3: Report
        generate_report(duplicates, report_file)

        print(f"\nDone! Report saved to {report_file}")

    except KeyboardInterrupt:
        print("\n\n🛑 Process interrupted by user.")
        print("Progress has been saved to the database.")
        print("Run the script again to resume scanning.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
