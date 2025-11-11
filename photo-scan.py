#!/usr/bin/env python3
"""
Recursive scan of a Photos/Aperture library (or any directory) that
produces a summary per sub‑folder:

* total number of image files
* cumulative size
* average file size
* list of the most common image extensions

The output mimics a simple “du” view but focuses on image assets only.
"""

import argparse
import os
import pathlib
import sys
from collections import Counter, defaultdict

# ----------------------------------------------------------------------
# Helper: decide whether a file is an image we care about
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".gif",
    ".raw", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf",
    ".mp4", ".mov",
}
def is_image(path: pathlib.Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS

# ----------------------------------------------------------------------
def scan_folder(root: pathlib.Path) -> dict[pathlib.Path, dict]:
    """
    Walk `root` recursively and collect stats for each directory that
    contains at least one image file.
    Returns a mapping:
        dir_path -> {"count": int, "size": int, "ext_counter": Counter, "sizes": list[int]}
    """
    stats = defaultdict(lambda: {"count": 0, "size": 0, "ext_counter": Counter(), "sizes": []})

    for dirpath, _, filenames in os.walk(root):
        dir_path = pathlib.Path(dirpath)
        for name in filenames:
            file_path = dir_path / name
            if not is_image(file_path):
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                continue  # skip unreadable files

            entry = stats[dir_path]
            entry["count"] += 1
            entry["size"] += size
            entry["ext_counter"][file_path.suffix.lower()] += 1
            entry["sizes"].append(size)

    return stats

# ----------------------------------------------------------------------
def human_readable(num_bytes: float) -> str:
    """Convert bytes → KiB, MiB, GiB …"""
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PiB"

# ----------------------------------------------------------------------
def parse_size_string(size_str: str) -> int:
    """Convert human-readable size string (e.g., "500KB") to bytes."""
    size_str = size_str.strip().upper()
    if size_str.endswith("KB"):
        return int(float(size_str[:-2]) * 1024)
    elif size_str.endswith("MB"):
        return int(float(size_str[:-2]) * 1024**2)
    elif size_str.endswith("GB"):
        return int(float(size_str[:-2]) * 1024**3)
    elif size_str.endswith("B"):
        return int(float(size_str[:-1]))
    else:
        return int(float(size_str)) # Assume bytes if no unit

# ----------------------------------------------------------------------
def print_report(stats: dict[pathlib.Path, dict], root: pathlib.Path):
    """Print a sorted table similar to `du`."""
    # Sort by total size descending (most interesting folders first)
    sorted_items = sorted(stats.items(), key=lambda kv: kv[1]["size"], reverse=True)

    print(f"\nSummary for {root}\n")
    header = f"{'Folder (relative)':<40} {'# files':>8} {'Total size':>12} {'Avg size':>12} {'Top ext':>10}"
    print(header)
    print("-" * len(header))

    for folder, data in sorted_items:
        rel = folder.relative_to(root)
        count = data["count"]
        total = data["size"]
        avg = total / count if count else 0
        top_ext = data["ext_counter"].most_common(1)[0][0] if data["ext_counter"] else ""
        print(
            f"{str(rel):<40} {count:8d} {human_readable(total):>12} {human_readable(avg):>12} {top_ext:>10}"
        )

# ----------------------------------------------------------------------
def group_and_report(
    stats: dict[pathlib.Path, dict],
    root: pathlib.Path,
    group_size_thresholds: list[int],
    display_limit: int,
    dump_all_folders: bool,
    show_subdirs: bool = False,
):
    """
    Group folders by size categories and common root folders, then print a report.
    """
    if dump_all_folders:
        print_report(stats, root)
        return

    # Grouping logic
    grouped_stats = defaultdict(
        lambda: {"count": 0, "size": 0, "ext_counter": Counter(), "folders": [], "subdirs": defaultdict(lambda: {"count": 0, "size": 0, "ext_counter": Counter()})}
    )

    # Define size categories (largest to smallest)
    categories = []
    if len(group_size_thresholds) == 1:
        categories.append((group_size_thresholds[0], float('inf'), "Originals"))
        categories.append((0, group_size_thresholds[0], "Thumbnails"))
    elif len(group_size_thresholds) >= 2:
        categories.append((group_size_thresholds[0], float('inf'), "Originals"))
        categories.append((group_size_thresholds[1], group_size_thresholds[0], "Thumbnails"))
        categories.append((0, group_size_thresholds[1], "Smaller Thumbnails"))
    else:
        categories.append((0, float('inf'), "All Files"))

    for folder, data in stats.items():
        avg_size = data["size"] / data["count"] if data["count"] else 0
        category_name = "Other"
        for lower, upper, name in categories:
            if lower <= avg_size < upper:
                category_name = name
                break

        # Determine the root folder for grouping (e.g., 'originals', 'resources/renders')
        relative_folder = folder.relative_to(root)
        parts = relative_folder.parts
        root_group = parts[0] if parts else "/"
        if len(parts) > 1 and parts[0] in ["resources", "originals"]:
            root_group = f"{parts[0]}/{parts[1]}"
        elif len(parts) > 0: # Catch other top-level folders
            root_group = parts[0]
        else:
            root_group = "/"

        group_key = f"{root_group} ({category_name})"
        grouped_entry = grouped_stats[group_key]
        grouped_entry["count"] += data["count"]
        grouped_entry["size"] += data["size"]
        grouped_entry["ext_counter"].update(data["ext_counter"])
        grouped_entry["folders"].append((folder, data)) # Store individual folder data for later if needed

        # Track subdirectory stats if requested
        if show_subdirs:
            # Get the first subdirectory under the root_group
            # For Masters/Photos/2010/..., we want "Photos" or "2010" depending on structure
            subdir_key = "/"
            if parts:
                # Skip the root_group parts and take the next level
                root_parts = root_group.split('/')
                if len(parts) > len(root_parts):
                    subdir_key = parts[len(root_parts)]
                elif len(parts) > 1:
                    subdir_key = parts[1]

            subdir_entry = grouped_entry["subdirs"][subdir_key]
            subdir_entry["count"] += data["count"]
            subdir_entry["size"] += data["size"]
            subdir_entry["ext_counter"].update(data["ext_counter"])

    sorted_groups = sorted(grouped_stats.items(), key=lambda kv: kv[1]["size"], reverse=True)

    print(f"\nSummary for {root} (Grouped by Size and Root Folder)\n")
    header = f"{'Group (Category)':<40} {'# files':>8} {'Total size':>12} {'Avg size':>12} {'Top ext':>10}"
    print(header)
    print("-" * len(header))

    for group_name, data in sorted_groups:
        count = data["count"]
        total = data["size"]
        avg = total / count if count else 0
        top_ext = data["ext_counter"].most_common(1)[0][0] if data["ext_counter"] else ""
        print(
            f"{group_name:<40} {count:8d} {human_readable(total):>12} {human_readable(avg):>12} {top_ext:>10}"
        )

        # Show subdirectory breakdown if requested
        if show_subdirs and data["subdirs"]:
            sorted_subdirs = sorted(data["subdirs"].items(), key=lambda kv: kv[1]["size"], reverse=True)
            for subdir_name, subdir_data in sorted_subdirs:
                subdir_count = subdir_data["count"]
                subdir_total = subdir_data["size"]
                subdir_avg = subdir_total / subdir_count if subdir_count else 0
                subdir_ext = subdir_data["ext_counter"].most_common(1)[0][0] if subdir_data["ext_counter"] else ""
                print(
                    f"  └─ {subdir_name:<36} {subdir_count:8d} {human_readable(subdir_total):>12} {human_readable(subdir_avg):>12} {subdir_ext:>10}"
                )


# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Recursively count image files in a Photos/Aperture library "
                    "and report per‑folder statistics."
    )
    parser.add_argument(
        "library_path",
        type=pathlib.Path,
        help="Path to the .photoslibrary or .aplibrary bundle (or any folder).",
    )
    parser.add_argument(
        "--group-size-thresholds",
        type=str,
        default="500KB,100KB",
        help="Comma-separated list of size thresholds for grouping (e.g., '500KB,100KB').",
    )
    parser.add_argument(
        "--display-limit",
        type=int,
        default=1000,
        help="Maximum number of individual folders to display when --dump-all-folders is used.",
    )
    parser.add_argument(
        "--dump-all-folders",
        action="store_true",
        help="Dump all individual folder statistics, overriding the default grouped view.",
    )
    parser.add_argument(
        "--show-subdirs",
        action="store_true",
        help="Show subdirectory breakdown within each group (intermediate detail level).",
    )
    args = parser.parse_args()

    if not args.library_path.is_dir():
        sys.exit(f"Error: {args.library_path} is not a directory.")

    stats = scan_folder(args.library_path)
    if not stats:
        print("No image files found.")
        return

    group_threshold_bytes = [
        parse_size_string(s) for s in args.group_size_thresholds.split(",")
    ]
    group_threshold_bytes.sort(reverse=True) # Ensure descending order for categorization

    group_and_report(
        stats,
        args.library_path,
        group_threshold_bytes,
        args.display_limit,
        args.dump_all_folders,
        args.show_subdirs,
    )


if __name__ == "__main__":
    main()

