#!/usr/bin/env python3
"""
Query the Photos Library SQLite database to extract metadata for photos by UUID.

This script can:
- Look up a photo by UUID and display its metadata
- Export metadata for all photos to CSV
- Find photos by date range or other criteria
"""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Core Data timestamp offset: seconds between Jan 1, 1970 (Unix epoch) and Jan 1, 2001
COREDATA_TIMESTAMP_OFFSET = 978307200


def core_data_to_datetime(timestamp):
    """Convert Core Data timestamp to Python datetime."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp + COREDATA_TIMESTAMP_OFFSET)


def query_photo_by_uuid(db_path: Path, uuid: str) -> Optional[dict]:
    """Query the database for a photo by UUID."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        a.Z_PK,
        a.ZUUID,
        datetime(a.ZDATECREATED + 978307200, 'unixepoch') as date_captured,
        a.ZDATECREATED as raw_timestamp,
        a.ZADDEDDATE as date_added,
        a.ZFILENAME,
        a.ZDIRECTORY,
        a.ZWIDTH,
        a.ZHEIGHT,
        a.ZDURATION,
        a.ZKIND,
        a.ZKINDSUBTYPE,
        a.ZFAVORITE,
        a.ZHIDDEN,
        a.ZTRASHEDSTATE,
        e.ZCAMERAMAKE,
        e.ZCAMERAMODEL,
        e.ZAPERTURE,
        e.ZSHUTTERSPEED,
        e.ZISO,
        e.ZFOCALLENGTH,
        e.ZEXPOSUREBIAS,
        e.ZLATITUDE,
        e.ZLONGITUDE,
        e.ZWHITEBALANCE,
        e.ZFLASHFIRED,
        datetime(e.ZDATECREATED + 978307200, 'unixepoch') as exif_date_created
    FROM ZASSET a
    LEFT JOIN ZEXTENDEDATTRIBUTES e ON a.ZEXTENDEDATTRIBUTES = e.Z_PK
    WHERE a.ZUUID = ? COLLATE NOCASE
    LIMIT 1
    """

    cursor.execute(query, (uuid,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def query_all_photos(db_path: Path, limit: Optional[int] = None) -> list[dict]:
    """Query all photos from the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        a.Z_PK,
        a.ZUUID,
        datetime(a.ZDATECREATED + 978307200, 'unixepoch') as date_captured,
        a.ZDATECREATED as raw_timestamp,
        a.ZADDEDDATE as date_added,
        a.ZFILENAME,
        a.ZDIRECTORY,
        a.ZWIDTH,
        a.ZHEIGHT,
        a.ZDURATION,
        a.ZKIND,
        a.ZKINDSUBTYPE,
        a.ZFAVORITE,
        a.ZHIDDEN,
        a.ZTRASHEDSTATE,
        e.ZCAMERAMAKE,
        e.ZCAMERAMODEL,
        e.ZAPERTURE,
        e.ZSHUTTERSPEED,
        e.ZISO,
        e.ZFOCALLENGTH,
        e.ZEXPOSUREBIAS,
        e.ZLATITUDE,
        e.ZLONGITUDE,
        e.ZWHITEBALANCE,
        e.ZFLASHFIRED,
        datetime(e.ZDATECREATED + 978307200, 'unixepoch') as exif_date_created
    FROM ZASSET a
    LEFT JOIN ZEXTENDEDATTRIBUTES e ON a.ZEXTENDEDATTRIBUTES = e.Z_PK
    WHERE a.ZTRASHEDSTATE = 0
    ORDER BY a.ZDATECREATED ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def query_resources(db_path: Path, asset_pk: int) -> list[dict]:
    """Query resources (derivatives, thumbnails) for an asset."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        Z_PK,
        ZASSET,
        ZRESOURCETYPE,
        ZFINGERPRINT,
        ZSTABLEHASH,
        ZFILEID,
        ZDATALENGTH,
        ZUNORIENTEDWIDTH,
        ZUNORIENTEDHEIGHT
    FROM ZINTERNALRESOURCE
    WHERE ZASSET = ?
    ORDER BY ZRESOURCETYPE
    """

    cursor.execute(query, (asset_pk,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_file_paths(uuid: str, filename: str, directory: str, library_path: Path) -> dict:
    """Determine file paths within the photoslibrary package."""
    paths = {
        'original': None,
        'derivatives': []
    }

    # Extract extension from filename
    ext = Path(filename).suffix

    # For newer Photos.app format, ZDIRECTORY is just a hash character (0-9, A-F)
    # For older iPhoto/Aperture format, ZDIRECTORY might contain a full path
    if directory and directory not in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']:
        # Old format - use the directory path as-is
        original_path = library_path / directory / filename
        if original_path.exists():
            paths['original'] = str(original_path.relative_to(library_path))
    else:
        # New format - use first character of UUID as hash directory
        hash_dir = uuid[0].upper()
        original_path = library_path / "originals" / hash_dir / filename
        if original_path.exists():
            paths['original'] = f"originals/{hash_dir}/{filename}"

        # Check for derivatives
        deriv_base = library_path / "resources" / "derivatives" / hash_dir
        if deriv_base.exists():
            for deriv_file in deriv_base.glob(f"{uuid}_*"):
                paths['derivatives'].append(f"resources/derivatives/{hash_dir}/{deriv_file.name}")
            for deriv_file in deriv_base.glob(f"{uuid}.*"):
                if deriv_file.name != filename:  # Don't include if it's the same as original
                    paths['derivatives'].append(f"resources/derivatives/{hash_dir}/{deriv_file.name}")

    return paths


def print_photo_info(photo: dict, library_path: Optional[Path] = None):
    """Pretty print photo information."""
    print(f"UUID: {photo['ZUUID']}")
    print(f"Filename: {photo['ZFILENAME']}")

    # Show file paths if library path provided
    if library_path:
        paths = get_file_paths(photo['ZUUID'], photo['ZFILENAME'], str(photo['ZDIRECTORY'] or ''), library_path)
        if paths['original']:
            print(f"Original Location: {paths['original']}")
        if paths['derivatives']:
            print(f"Derivatives ({len(paths['derivatives'])}):")
            for deriv in paths['derivatives'][:5]:  # Show first 5
                print(f"  - {deriv}")
            if len(paths['derivatives']) > 5:
                print(f"  ... and {len(paths['derivatives']) - 5} more")

    print(f"Date Captured: {photo['date_captured']}")
    if photo['date_added']:
        date_added = core_data_to_datetime(photo['date_added'])
        print(f"Date Added: {date_added}")
    print(f"Dimensions: {photo['ZWIDTH']} x {photo['ZHEIGHT']}")

    if photo['ZDURATION']:
        print(f"Duration: {photo['ZDURATION']:.2f} seconds")

    if photo['ZCAMERAMAKE'] or photo['ZCAMERAMODEL']:
        print(f"Camera: {photo['ZCAMERAMAKE'] or ''} {photo['ZCAMERAMODEL'] or ''}".strip())

    if photo['ZAPERTURE']:
        print(f"Aperture: f/{photo['ZAPERTURE']:.1f}")
    if photo['ZSHUTTERSPEED']:
        print(f"Shutter Speed: {photo['ZSHUTTERSPEED']:.6f}s")
    if photo['ZISO']:
        print(f"ISO: {photo['ZISO']}")
    if photo['ZFOCALLENGTH']:
        print(f"Focal Length: {photo['ZFOCALLENGTH']}mm")

    if photo['ZLATITUDE'] and photo['ZLONGITUDE']:
        print(f"Location: {photo['ZLATITUDE']:.6f}, {photo['ZLONGITUDE']:.6f}")

    flags = []
    if photo['ZFAVORITE']:
        flags.append("Favorite")
    if photo['ZHIDDEN']:
        flags.append("Hidden")
    if photo['ZTRASHEDSTATE']:
        flags.append("Trashed")
    if flags:
        print(f"Flags: {', '.join(flags)}")


def query_photos_by_year(db_path: Path) -> dict:
    """Query photos grouped by year of capture."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        CAST(strftime('%Y', datetime(a.ZDATECREATED + 978307200, 'unixepoch')) AS INTEGER) as year,
        COUNT(*) as count
    FROM ZASSET a
    WHERE a.ZTRASHEDSTATE = 0
        AND a.ZDATECREATED IS NOT NULL
    GROUP BY year
    ORDER BY year ASC
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return {row['year']: row['count'] for row in rows}


def print_year_report(year_counts: dict):
    """Print a report of photos grouped by year."""
    if not year_counts:
        print("No photos found.")
        return

    total = sum(year_counts.values())

    print(f"\nPhotos by Year of Capture\n")
    print(f"{'Year':<10} {'Count':<12} {'Percentage':<12} {'Bar Chart'}")
    print("-" * 70)

    # Calculate max count for bar chart scaling
    max_count = max(year_counts.values())

    for year in sorted(year_counts.keys()):
        count = year_counts[year]
        percentage = (count / total * 100) if total > 0 else 0
        bar_length = int((count / max_count * 50)) if max_count > 0 else 0
        bar = "█" * bar_length

        print(f"{year:<10} {count:<12,} {percentage:>6.2f}%      {bar}")

    print("-" * 70)
    print(f"{'TOTAL':<10} {total:<12,} {'100.00%':>12}")
    print()


def export_to_csv(photos: list[dict], output_path: Path, library_path: Optional[Path] = None):
    """Export photo metadata to CSV."""
    if not photos:
        print("No photos to export.")
        return

    fieldnames = [
        'UUID', 'Filename', 'Original Path', 'Date Captured', 'Date Added',
        'Width', 'Height', 'Duration',
        'Camera Make', 'Camera Model',
        'Aperture', 'Shutter Speed', 'ISO Speed', 'Focal Length', 'Exposure Bias',
        'Latitude', 'Longitude',
        'Favorite', 'Hidden', 'Trashed'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for photo in photos:
            date_added = None
            if photo['date_added']:
                dt = core_data_to_datetime(photo['date_added'])
                date_added = dt.isoformat() if dt else None

            # Get file path
            original_path = ''
            if library_path:
                paths = get_file_paths(photo['ZUUID'], photo['ZFILENAME'], str(photo['ZDIRECTORY'] or ''), library_path)
                original_path = paths['original'] or ''

            row = {
                'UUID': photo['ZUUID'],
                'Filename': photo['ZFILENAME'],
                'Original Path': original_path,
                'Date Captured': photo['date_captured'],
                'Date Added': date_added,
                'Width': photo['ZWIDTH'],
                'Height': photo['ZHEIGHT'],
                'Duration': photo['ZDURATION'] if photo['ZDURATION'] else '',
                'Camera Make': photo['ZCAMERAMAKE'] or '',
                'Camera Model': photo['ZCAMERAMODEL'] or '',
                'Aperture': photo['ZAPERTURE'] if photo['ZAPERTURE'] else '',
                'Shutter Speed': photo['ZSHUTTERSPEED'] if photo['ZSHUTTERSPEED'] else '',
                'ISO Speed': photo['ZISO'] if photo['ZISO'] else '',
                'Focal Length': photo['ZFOCALLENGTH'] if photo['ZFOCALLENGTH'] else '',
                'Exposure Bias': photo['ZEXPOSUREBIAS'] if photo['ZEXPOSUREBIAS'] else '',
                'Latitude': photo['ZLATITUDE'] if photo['ZLATITUDE'] else '',
                'Longitude': photo['ZLONGITUDE'] if photo['ZLONGITUDE'] else '',
                'Favorite': 'Yes' if photo['ZFAVORITE'] else 'No',
                'Hidden': 'Yes' if photo['ZHIDDEN'] else 'No',
                'Trashed': 'Yes' if photo['ZTRASHEDSTATE'] else 'No',
            }
            writer.writerow(row)

    print(f"Exported {len(photos)} photos to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Query Photos Library SQLite database for photo metadata."
    )
    parser.add_argument(
        "library_path",
        type=Path,
        help="Path to the .photoslibrary bundle",
    )
    parser.add_argument(
        "--uuid",
        type=str,
        help="Look up a specific photo by UUID",
    )
    parser.add_argument(
        "--export-csv",
        type=Path,
        help="Export all photos to CSV file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of results when exporting (default: all)",
    )
    parser.add_argument(
        "--show-resources",
        action="store_true",
        help="Show resources/derivatives when looking up by UUID",
    )
    parser.add_argument(
        "--year-report",
        action="store_true",
        help="Generate a report of photos grouped by year of capture",
    )
    parser.add_argument(
        "--export-year-report",
        type=Path,
        help="Export year report to CSV file",
    )

    args = parser.parse_args()

    # Construct database path
    db_path = args.library_path / "database" / "Photos.sqlite"

    if not db_path.exists():
        sys.exit(f"Error: Database not found at {db_path}")

    if args.uuid:
        # Look up specific UUID
        photo = query_photo_by_uuid(db_path, args.uuid)
        if photo:
            print_photo_info(photo, library_path=args.library_path)

            if args.show_resources:
                resources = query_resources(db_path, photo['Z_PK'])
                if resources:
                    print("\nResources/Derivatives:")
                    resource_types = {
                        0: "Original/Full size",
                        1: "Thumbnail",
                        3: "Render/Derivative",
                        4: "Other",
                        5: "Sidecar",
                        31: "Other",
                    }
                    for res in resources:
                        res_type = resource_types.get(res['ZRESOURCETYPE'], f"Type {res['ZRESOURCETYPE']}")
                        print(f"  - {res_type}: FileID={res['ZFILEID']}, "
                              f"Size={res['ZDATALENGTH']} bytes" if res['ZDATALENGTH'] else "Size=unknown")
        else:
            print(f"Photo with UUID {args.uuid} not found in database.")
            sys.exit(1)

    elif args.export_csv:
        # Export all photos to CSV
        print(f"Querying database at {db_path}...")
        photos = query_all_photos(db_path, limit=args.limit)
        export_to_csv(photos, args.export_csv, library_path=args.library_path)

    elif args.year_report or args.export_year_report:
        # Generate year report
        print(f"Querying database at {db_path}...")
        year_counts = query_photos_by_year(db_path)

        if args.export_year_report:
            # Export to CSV
            with open(args.export_year_report, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['Year', 'Count', 'Percentage'])
                writer.writeheader()

                total = sum(year_counts.values())
                for year in sorted(year_counts.keys()):
                    count = year_counts[year]
                    percentage = (count / total * 100) if total > 0 else 0
                    writer.writerow({
                        'Year': year,
                        'Count': count,
                        'Percentage': f"{percentage:.2f}%"
                    })
            print(f"Year report exported to {args.export_year_report}")
        else:
            # Print to console
            print_year_report(year_counts)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

