#!/usr/bin/env python3
import os
import sys
import argparse

try:
    from wavetwin.database import init_db
    from wavetwin.audio import check_dependencies, AUDIO_EXTENSIONS
    from wavetwin.logic import (
        scan_phase,
        process_files,
        analysis_phase,
        find_best_match,
    )
    from wavetwin.report import generate_report
except ImportError:
    from database import init_db
    from audio import check_dependencies, AUDIO_EXTENSIONS
    from logic import scan_phase, process_files, analysis_phase, find_best_match
    from report import generate_report


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

    # Check dependencies (using new module)
    # The new function exits if missing, but let's wrap it just in case
    # Actually, check_dependencies in audio.py calls sys.exit, so we just call it
    check_dependencies()

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
        # Phase 1: Scan
        print("\n--- PHASE 1: Scanning ---")
        scan_phase(conn, search_dir, AUDIO_EXTENSIONS)

        # Phase 1.5: Process Files (Fingerprinting)
        print("\n--- PHASE 2: Processing ---")
        processing_errors = process_files(conn, search_dir)

        # Phase 2: Analyze
        print("\n--- PHASE 3: Analysis ---")
        duplicates = analysis_phase(conn)

        # Phase 3: Report
        print("\n--- PHASE 4: Reporting ---")
        generate_report(duplicates, report_file, find_best_match)

        print(f"\nDone! Found {len(duplicates)} duplicate groups.")
        if processing_errors > 0:
            print(f"Warnings: {processing_errors} files failed to process.")
        print(f"Report saved to {report_file}")

    except KeyboardInterrupt:
        print("\n\n🛑 Process interrupted by user.")
        print("Progress has been saved to the database.")
        print("Run the script again to resume scanning.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
