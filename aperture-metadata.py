#!/usr/bin/env python3
"""
Query the Aperture Library SQLite database to extract metadata for photos by UUID.

This script can:
- Look up a photo by UUID and display its metadata
- Export metadata for all photos to CSV
- Generate year report of photos grouped by capture date
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


def query_photo_by_uuid(library_db_path: Path, properties_db_path: Path, uuid: str) -> Optional[dict]:
    """Query the database for a photo by UUID."""
    library_conn = sqlite3.connect(str(library_db_path))
    library_conn.row_factory = sqlite3.Row
    library_cursor = library_conn.cursor()

    # Query RKVersion (the main photo table)
    query = f"""
    SELECT
        v.modelId,
        v.uuid,
        v.name,
        v.fileName,
        v.masterUuid,
        datetime(v.imageDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch') as date_captured,
        v.imageDate as raw_timestamp,
        datetime(v.createDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch') as date_created,
        v.masterWidth,
        v.masterHeight,
        v.processedWidth,
        v.processedHeight,
        v.exifLatitude,
        v.exifLongitude,
        v.isFlagged,
        v.isHidden,
        v.isInTrash,
        v.mainRating,
        v.colorLabelIndex,
        m.imagePath,
        m.fileName as masterFileName,
        m.fileSize,
        m.imageDate as masterImageDate,
        datetime(m.imageDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch') as master_date_captured
    FROM RKVersion v
    LEFT JOIN RKMaster m ON v.masterUuid = m.uuid
    WHERE v.uuid = ? COLLATE NOCASE
    LIMIT 1
    """

    library_cursor.execute(query, (uuid,))
    row = library_cursor.fetchone()

    if not row:
        library_conn.close()
        return None

    photo = dict(row)
    library_conn.close()

    # Get EXIF properties from Properties database
    if properties_db_path.exists():
        exif_data = get_exif_properties(properties_db_path, photo['modelId'])
        photo.update(exif_data)

    return photo


def get_exif_properties(properties_db_path: Path, version_id: int) -> dict:
    """Get EXIF properties for a version from Properties database."""
    conn = sqlite3.connect(str(properties_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    exif = {}

    # Get string properties
    query_str = """
    SELECT ep.propertyKey, us.stringProperty
    FROM RKExifStringProperty ep
    LEFT JOIN RKUniqueString us ON ep.stringId = us.modelId
    WHERE ep.versionId = ?
    """
    cursor.execute(query_str, (version_id,))
    for row in cursor.fetchall():
        key = row['propertyKey']
        value = row['stringProperty']
        if key == 'Make':
            exif['cameraMake'] = value
        elif key == 'Model':
            exif['cameraModel'] = value
        elif key == 'LensModel':
            exif['lensModel'] = value
        elif key == 'Software':
            exif['software'] = value
        else:
            exif[f'exif_{key}'] = value

    # Get number properties
    query_num = """
    SELECT propertyKey, numberProperty
    FROM RKExifNumberProperty
    WHERE versionId = ?
    """
    cursor.execute(query_num, (version_id,))
    for row in cursor.fetchall():
        key = row['propertyKey']
        value = row['numberProperty']
        if key == 'ApertureValue':
            exif['aperture'] = value
        elif key == 'FocalLength':
            exif['focalLength'] = value
        elif key == 'ISOSpeedRating':
            exif['iso'] = value
        elif key == 'ExposureBiasValue':
            exif['exposureBias'] = value
        elif key == 'Latitude':
            exif['latitude'] = value
        elif key == 'Longitude':
            exif['longitude'] = value
        elif key == 'Flash':
            exif['flash'] = value
        else:
            exif[f'exif_{key}'] = value

    conn.close()
    return exif


def query_all_photos(library_db_path: Path, properties_db_path: Path, limit: Optional[int] = None) -> list[dict]:
    """Query all photos from the database."""
    library_conn = sqlite3.connect(str(library_db_path))
    library_conn.row_factory = sqlite3.Row
    library_cursor = library_conn.cursor()

    query = f"""
    SELECT
        v.modelId,
        v.uuid,
        v.name,
        v.fileName,
        v.masterUuid,
        datetime(v.imageDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch') as date_captured,
        v.imageDate as raw_timestamp,
        datetime(v.createDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch') as date_created,
        v.masterWidth,
        v.masterHeight,
        v.processedWidth,
        v.processedHeight,
        v.exifLatitude,
        v.exifLongitude,
        v.isFlagged,
        v.isHidden,
        v.isInTrash,
        v.mainRating,
        v.colorLabelIndex,
        m.imagePath,
        m.fileName as masterFileName,
        m.fileSize,
        m.imageDate as masterImageDate,
        datetime(m.imageDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch') as master_date_captured
    FROM RKVersion v
    LEFT JOIN RKMaster m ON v.masterUuid = m.uuid
    WHERE v.isInTrash = 0
    ORDER BY v.imageDate ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    library_cursor.execute(query)
    rows = library_cursor.fetchall()
    library_conn.close()

    photos = []
    # Get EXIF data for each photo (this might be slow for large libraries)
    for row in rows:
        photo = dict(row)
        if properties_db_path.exists():
            exif_data = get_exif_properties(properties_db_path, photo['modelId'])
            photo.update(exif_data)
        photos.append(photo)

    return photos


def get_file_path(image_path: str, library_path: Path) -> Optional[str]:
    """Determine file path within the Aperture library."""
    if not image_path:
        return None

    library_path = Path(library_path).resolve()

    # Aperture stores paths like "Photos/2010/12/.../filename.jpg"
    # Files are in the Masters directory
    full_path = library_path / "Masters" / image_path

    try:
        if full_path.exists():
            return str(full_path.relative_to(library_path))
    except (ValueError, OSError):
        pass

    return None


def print_photo_info(photo: dict, library_path: Optional[Path] = None):
    """Pretty print photo information."""
    print(f"UUID: {photo['uuid']}")
    print(f"Name: {photo['name']}")
    print(f"Filename: {photo['fileName']}")

    # Show file path if library path provided
    if library_path and photo.get('imagePath'):
        file_path = get_file_path(photo['imagePath'], library_path)
        if file_path:
            print(f"Original Location: {file_path}")

    if photo['date_captured']:
        print(f"Date Captured: {photo['date_captured']}")
    if photo.get('date_created'):
        print(f"Date Created: {photo['date_created']}")

    if photo['masterWidth'] and photo['masterHeight']:
        print(f"Dimensions: {photo['masterWidth']} x {photo['masterHeight']}")

    if photo.get('cameraMake') or photo.get('cameraModel'):
        camera_str = f"{photo.get('cameraMake', '')} {photo.get('cameraModel', '')}".strip()
        print(f"Camera: {camera_str}")

    if photo.get('lensModel'):
        print(f"Lens: {photo['lensModel']}")

    if photo.get('aperture'):
        print(f"Aperture: f/{photo['aperture']:.1f}")
    if photo.get('focalLength'):
        print(f"Focal Length: {photo['focalLength']}mm")
    if photo.get('iso'):
        print(f"ISO: {photo['iso']}")
    if photo.get('exposureBias'):
        print(f"Exposure Bias: {photo['exposureBias']:+.1f} EV")

    # Use GPS from RKVersion first, then from EXIF
    latitude = photo.get('exifLatitude') or photo.get('latitude')
    longitude = photo.get('exifLongitude') or photo.get('longitude')
    if latitude and longitude:
        print(f"Location: {latitude:.6f}, {longitude:.6f}")

    flags = []
    if photo['isFlagged']:
        flags.append("Flagged")
    if photo['isHidden']:
        flags.append("Hidden")
    if photo['isInTrash']:
        flags.append("Trashed")
    if photo.get('mainRating'):
        flags.append(f"Rating: {photo['mainRating']} stars")
    if flags:
        print(f"Flags: {', '.join(flags)}")


def query_photos_by_year(library_db_path: Path) -> dict:
    """Query photos grouped by year of capture."""
    conn = sqlite3.connect(str(library_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = f"""
    SELECT
        CAST(strftime('%Y', datetime(v.imageDate + {COREDATA_TIMESTAMP_OFFSET}, 'unixepoch')) AS INTEGER) as year,
        COUNT(*) as count
    FROM RKVersion v
    WHERE v.isInTrash = 0
        AND v.imageDate IS NOT NULL
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
        'UUID', 'Name', 'Filename', 'Master Path', 'Date Captured', 'Date Created',
        'Width', 'Height', 'File Size',
        'Camera Make', 'Camera Model', 'Lens Model',
        'Aperture', 'Focal Length', 'ISO Speed', 'Exposure Bias',
        'Latitude', 'Longitude',
        'Flagged', 'Hidden', 'Rating'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for photo in photos:
            master_path = ''
            if library_path and photo.get('imagePath'):
                file_path = get_file_path(photo['imagePath'], library_path)
                master_path = file_path or ''

            row = {
                'UUID': photo['uuid'],
                'Name': photo['name'] or '',
                'Filename': photo['fileName'] or '',
                'Master Path': master_path,
                'Date Captured': photo['date_captured'] or '',
                'Date Created': photo.get('date_created') or '',
                'Width': photo['masterWidth'] if photo['masterWidth'] else '',
                'Height': photo['masterHeight'] if photo['masterHeight'] else '',
                'File Size': photo.get('fileSize') if photo.get('fileSize') else '',
                'Camera Make': photo.get('cameraMake') or '',
                'Camera Model': photo.get('cameraModel') or '',
                'Lens Model': photo.get('lensModel') or '',
                'Aperture': photo.get('aperture') if photo.get('aperture') else '',
                'Focal Length': photo.get('focalLength') if photo.get('focalLength') else '',
                'ISO Speed': photo.get('iso') if photo.get('iso') else '',
                'Exposure Bias': photo.get('exposureBias') if photo.get('exposureBias') else '',
                'Latitude': photo.get('exifLatitude') or photo.get('latitude') or '',
                'Longitude': photo.get('exifLongitude') or photo.get('longitude') or '',
                'Flagged': 'Yes' if photo['isFlagged'] else 'No',
                'Hidden': 'Yes' if photo['isHidden'] else 'No',
                'Rating': photo['mainRating'] if photo['mainRating'] else '',
            }
            writer.writerow(row)

    print(f"Exported {len(photos)} photos to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Query Aperture Library SQLite database for photo metadata."
    )
    parser.add_argument(
        "library_path",
        type=Path,
        help="Path to the .aplibrary or .migratedaplibrary bundle",
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

    # Construct database paths
    library_db_path = args.library_path / "Database" / "apdb" / "Library.apdb"
    properties_db_path = args.library_path / "Database" / "apdb" / "Properties.apdb"

    if not library_db_path.exists():
        sys.exit(f"Error: Library database not found at {library_db_path}")

    if args.uuid:
        # Look up specific UUID
        photo = query_photo_by_uuid(library_db_path, properties_db_path, args.uuid)
        if photo:
            print_photo_info(photo, library_path=args.library_path)
        else:
            print(f"Photo with UUID {args.uuid} not found in database.")
            sys.exit(1)

    elif args.export_csv:
        # Export all photos to CSV
        print(f"Querying database at {library_db_path}...")
        photos = query_all_photos(library_db_path, properties_db_path, limit=args.limit)
        export_to_csv(photos, args.export_csv, library_path=args.library_path)

    elif args.year_report or args.export_year_report:
        # Generate year report
        print(f"Querying database at {library_db_path}...")
        year_counts = query_photos_by_year(library_db_path)

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

