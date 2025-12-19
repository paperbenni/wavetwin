import os
import datetime

try:
    from wavetwin.audio import format_size
except ImportError:
    from audio import format_size


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


def _format_table_row(entry, is_best, col_widths):
    """Format a single row for the duplicate table."""
    path, name, size, bitrate, dur = entry["data"]
    ext = os.path.splitext(path)[1].upper().replace(".", "")
    br_str = f"{int(bitrate / 1000)} kbps" if bitrate else "Unknown"
    keep_mark = "✅" if is_best else "❌"

    # Truncate long content and pad to fixed width
    name_display = f"**{name}**"
    if len(name_display) > col_widths["filename"]:
        name_display = f"**{name[: col_widths['filename'] - 7]}...**"

    path_display = f"`{path}`"
    if len(path_display) > col_widths["path"]:
        path_display = f"`{path[: col_widths['path'] - 10]}...`"

    return (
        f"| {keep_mark:^{col_widths['keep']}} | "
        f"{name_display:<{col_widths['filename']}} | "
        f"{ext:<{col_widths['format']}} | "
        f"{br_str:<{col_widths['bitrate']}} | "
        f"{format_size(size):<{col_widths['size']}} | "
        f"{f'{dur}s':<{col_widths['duration']}} | "
        f"{path_display:<{col_widths['path']}} |\n"
    )


def _write_group_section(f, idx, group, best, col_widths):
    """Write the section for a single group of duplicates."""
    f.write(f"## Group {idx}\n\n")

    best_path = best["data"][0]
    best_size = best["data"][2]

    f.write(f"**Best Match:** `{best_path}`\n")
    if "quality_score" in best:
        f.write(f"**Score:** {best['quality_score']}\n")
    f.write(f"**Quality:** {format_size(best_size)}\n\n")

    # Write table header
    f.write(
        f"| {'Keep':^{col_widths['keep']}} | {'Filename':^{col_widths['filename']}} | {'Format':^{col_widths['format']}} | {'Bitrate':^{col_widths['bitrate']}} | {'Size':^{col_widths['size']}} | {'Duration':^{col_widths['duration']}} | {'Path':^{col_widths['path']}} |\n"
    )
    f.write(
        f"| {'':-^{col_widths['keep']}} | {'':-^{col_widths['filename']}} | {'':-^{col_widths['format']}} | {'':-^{col_widths['bitrate']}} | {'':-^{col_widths['size']}} | {'':-^{col_widths['duration']}} | {'':-^{col_widths['path']}} |\n"
    )

    # Write rows
    for entry in group:
        f.write(_format_table_row(entry, entry == best, col_widths))

    f.write("\n---\n\n")


def generate_report(groups, report_file, best_finder_func):
    """Generate HTML/Markdown report of duplicates."""
    saved_space, processed_groups = _calculate_savings(groups, best_finder_func)

    col_widths = {
        "keep": 6,
        "filename": 30,
        "format": 8,
        "bitrate": 10,
        "size": 8,
        "duration": 10,
        "path": 40,
    }

    with open(report_file, "w") as f:
        f.write(f"# Duplicate Audio Report\n")
        f.write(f"Generated on: {datetime.datetime.now()}\n\n")
        f.write(f"Found {len(groups)} groups of duplicates.\n")
        f.write(f"Total potential space saving: {format_size(saved_space)}\n\n")

        for idx, (group, best) in enumerate(processed_groups, 1):
            _write_group_section(f, idx, group, best, col_widths)
