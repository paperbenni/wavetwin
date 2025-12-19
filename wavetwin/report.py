import os
import datetime

from wavetwin.audio import format_size


def _calculate_savings(groups, best_finder_func):
    """Calculate potential space savings from deduplication."""
    saved_space = 0
    processed_groups = []

    for group in groups:
        best = best_finder_func(group)
        processed_groups.append((group, best))
        for entry in group:
            if entry != best:
                saved_space += entry["data"][2]  # size is at index 2

    return saved_space, processed_groups


def _format_table_row(entry, is_best):
    """Format a single row for the duplicate table."""
    path, name, size, bitrate, dur = entry["data"]
    ext = os.path.splitext(path)[1].upper().replace(".", "")
    br_str = f"{int(bitrate / 1000)} kbps" if bitrate else "Unknown"
    keep_mark = "✅" if is_best else "❌"

    return (
        f"| {keep_mark} | "
        f"**{name}** | "
        f"{ext} | "
        f"{br_str} | "
        f"{format_size(size)} | "
        f"{dur}s | "
        f"`{path}` |\n"
    )


def _write_group_section(f, idx, group, best):
    """Write the section for a single group of duplicates."""
    f.write(f"## Group {idx}\n\n")

    best_path = best["data"][0]
    best_size = best["data"][2]

    f.write(f"**Best Match:** `{best_path}`\n")
    if "quality_score" in best:
        f.write(f"**Score:** {best['quality_score']}\n")
    f.write(f"**Quality:** {format_size(best_size)}\n\n")

    # Write table header
    f.write(f"| Keep | Filename | Format | Bitrate | Size | Duration | Path |\n")
    f.write(f"| --- | --- | --- | --- | --- | --- | --- |\n")

    # Write rows
    for entry in group:
        f.write(_format_table_row(entry, entry == best))

    f.write("\n---\n\n")


def generate_report(groups, report_file, best_finder_func):
    """Generate HTML/Markdown report of duplicates."""
    saved_space, processed_groups = _calculate_savings(groups, best_finder_func)

    with open(report_file, "w") as f:
        f.write("# Duplicate Audio Report\n")
        f.write(f"Generated on: {datetime.datetime.now()}\n\n")
        f.write(f"Found {len(groups)} groups of duplicates.\n")
        f.write(f"Total potential space saving: {format_size(saved_space)}\n\n")

        for idx, (group, best) in enumerate(processed_groups, 1):
            _write_group_section(f, idx, group, best)
