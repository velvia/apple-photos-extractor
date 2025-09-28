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
}
def is_image(path: pathlib.Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS

# ----------------------------------------------------------------------
def scan_folder(root: pathlib.Path) -> dict[pathlib.Path, dict]:
    """
    Walk `root` recursively and collect stats for each directory that
    contains at least one image file.
    Returns a mapping:
        dir_path -> {"count": int, "size": int, "ext_counter": Counter}
    """
    stats = defaultdict(lambda: {"count": 0, "size": 0, "ext_counter": Counter()})

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

    return stats

# ----------------------------------------------------------------------
def human_readable(num_bytes: int) -> str:
    """Convert bytes → KiB, MiB, GiB …"""
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PiB"

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
    args = parser.parse_args()

    if not args.library_path.is_dir():
        sys.exit(f"Error: {args.library_path} is not a directory.")

    stats = scan_folder(args.library_path)
    if not stats:
        print("No image files found.")
        return

    print_report(stats, args.library_path)


if __name__ == "__main__":
    main()

