#!/usr/bin/env python3
"""
Export photos from an Aperture Library by year.

This script extracts photos from a .aplibrary or .migratedaplibrary package and organizes them
by year and month, preserving EXIF metadata and using master files.
"""

import argparse
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import functionality from aperture-metadata.py
import importlib.util
_aperture_metadata_path = Path(__file__).parent / "aperture-metadata.py"
spec = importlib.util.spec_from_file_location("aperture_metadata", _aperture_metadata_path)
aperture_metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aperture_metadata)

# Import the functions we need
get_exif_properties = aperture_metadata.get_exif_properties
get_file_path = aperture_metadata.get_file_path

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("Warning: Pillow not installed. EXIF metadata preservation will be limited.", file=sys.stderr)
    print("Install with: pip install Pillow", file=sys.stderr)

try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False
    if HAS_PILLOW:
        print("Warning: piexif not installed. EXIF metadata writing will be limited.", file=sys.stderr)
        print("Install with: pip install piexif for full EXIF metadata support", file=sys.stderr)


def query_photos_for_year(library_db_path: Path, properties_db_path: Path, year: int) -> list:
    """Query all photos for a specific year from Aperture library."""
    import sqlite3

    conn = sqlite3.connect(str(library_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        v.modelId,
        v.uuid,
        v.name,
        v.fileName,
        v.masterUuid,
        datetime(v.imageDate + 978307200, 'unixepoch') as date_captured,
        v.imageDate as raw_timestamp,
        v.masterWidth,
        v.masterHeight,
        v.exifLatitude,
        v.exifLongitude,
        m.imagePath,
        m.fileName as masterFileName,
        m.fileSize
    FROM RKVersion v
    LEFT JOIN RKMaster m ON v.masterUuid = m.uuid
    WHERE v.isInTrash = 0
        AND v.imageDate IS NOT NULL
        AND CAST(strftime('%Y', datetime(v.imageDate + 978307200, 'unixepoch')) AS INTEGER) = ?
    ORDER BY v.imageDate ASC
    """

    cursor.execute(query, (year,))
    rows = cursor.fetchall()
    conn.close()

    photos = []
    for row in rows:
        photo = dict(row)
        # Get EXIF properties from Properties database
        if properties_db_path.exists():
            exif_data = get_exif_properties(properties_db_path, photo['modelId'])
            photo.update(exif_data)
        photos.append(photo)

    return photos


def find_source_file(photo: dict, library_path: Path) -> Optional[Path]:
    """Find the source file for a photo in the Aperture library.

    Looks in Masters first (original full-size files), then falls back to
    Previews directory (thumbnails) if the master is not found.
    """
    library_path = library_path.resolve()

    # Get image path from master
    image_path = photo.get('imagePath')
    if not image_path:
        return None

    # Aperture stores paths like "Photos/2010/12/.../filename.jpg"
    # Try Masters directory first (full-size originals)
    full_path = library_path / "Masters" / image_path

    if full_path.exists() and full_path.is_file():
        # Verify the resolved path is within the library (safety check)
        try:
            resolved_lib = library_path.resolve()
            resolved_path = full_path.resolve()
            lib_str = str(resolved_lib) + os.sep
            path_str = str(resolved_path)
            if path_str.startswith(lib_str) or path_str == str(resolved_lib):
                return full_path
        except (OSError, ValueError):
            pass

    # Try Previews directory as fallback (thumbnails)
    preview_path = library_path / "Previews" / image_path
    if preview_path.exists() and preview_path.is_file():
        try:
            resolved_lib = library_path.resolve()
            resolved_path = preview_path.resolve()
            lib_str = str(resolved_lib) + os.sep
            path_str = str(resolved_path)
            if path_str.startswith(lib_str) or path_str == str(resolved_lib):
                return preview_path
        except (OSError, ValueError):
            pass

    # If the exact path doesn't exist, try searching by filename
    master_filename = photo.get('masterFileName') or photo.get('fileName')
    if master_filename:
        # Search in Masters directory first
        for root, dirs, files in os.walk(library_path / "Masters"):
            if master_filename in files:
                candidate = Path(root) / master_filename
                try:
                    resolved_lib = library_path.resolve()
                    resolved_candidate = candidate.resolve()
                    lib_str = str(resolved_lib) + os.sep
                    path_str = str(resolved_candidate)
                    if path_str.startswith(lib_str) or path_str == str(resolved_lib):
                        return candidate
                except (OSError, ValueError):
                    continue

        # If not found in Masters, search in Previews directory
        previews_dir = library_path / "Previews"
        if previews_dir.exists():
            for root, dirs, files in os.walk(previews_dir):
                if master_filename in files:
                    candidate = Path(root) / master_filename
                    try:
                        resolved_lib = library_path.resolve()
                        resolved_candidate = candidate.resolve()
                        lib_str = str(resolved_lib) + os.sep
                        path_str = str(resolved_candidate)
                        if path_str.startswith(lib_str) or path_str == str(resolved_lib):
                            return candidate
                    except (OSError, ValueError):
                        continue

    return None


def decimal_to_dms(decimal_deg: float) -> tuple:
    """Convert decimal degrees to degrees, minutes, seconds tuple for EXIF GPS."""
    degrees = int(abs(decimal_deg))
    minutes = int((abs(decimal_deg) - degrees) * 60)
    seconds = int(((abs(decimal_deg) - degrees - minutes/60) * 3600) * 100)
    return ((degrees, 1), (minutes, 1), (seconds, 100))


def write_exif_from_sqlite(source_path: Path, dest_path: Path, photo_metadata: dict) -> bool:
    """Write EXIF metadata from SQLite database to exported JPEG file."""
    if not HAS_PIEXIF:
        # Without piexif, we can't easily write EXIF, so just copy
        return False

    try:
        # Load existing EXIF or create new
        try:
            exif_dict = piexif.load(str(source_path))
        except:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        # Set DateTimeOriginal and DateTimeDigitized from date_captured
        if photo_metadata.get('date_captured'):
            try:
                dt = datetime.strptime(photo_metadata['date_captured'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    dt = datetime.strptime(photo_metadata['date_captured'], '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    dt = None

            if dt:
                date_str = dt.strftime("%Y:%m:%d %H:%M:%S")
                # EXIF DateTimeOriginal (tag 36867)
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str
                # EXIF DateTimeDigitized (tag 36868)
                exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str

        # Set camera make and model
        if photo_metadata.get('cameraMake'):
            exif_dict["0th"][piexif.ImageIFD.Make] = photo_metadata['cameraMake'].encode('utf-8')
        if photo_metadata.get('cameraModel'):
            exif_dict["0th"][piexif.ImageIFD.Model] = photo_metadata['cameraModel'].encode('utf-8')

        # Set camera settings
        if photo_metadata.get('aperture'):
            # Convert aperture to EXIF format (f-number stored as rational)
            fnumber = photo_metadata['aperture']
            exif_dict["Exif"][piexif.ExifIFD.FNumber] = (int(fnumber * 10), 10)

        if photo_metadata.get('iso'):
            exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings] = (photo_metadata['iso'],)

        if photo_metadata.get('focalLength'):
            focal = photo_metadata['focalLength']
            exif_dict["Exif"][piexif.ExifIFD.FocalLength] = (int(focal * 10), 10)

        if photo_metadata.get('exposureBias') is not None:
            # Exposure bias in EV (stored as rational)
            bias = photo_metadata['exposureBias']
            exif_dict["Exif"][piexif.ExifIFD.ExposureBiasValue] = (int(bias * 100), 100)

        if photo_metadata.get('flash') is not None:
            flash = int(photo_metadata['flash'])
            exif_dict["Exif"][piexif.ExifIFD.Flash] = flash

        # Set GPS coordinates (use RKVersion GPS first, then EXIF)
        latitude = photo_metadata.get('exifLatitude') or photo_metadata.get('latitude')
        longitude = photo_metadata.get('exifLongitude') or photo_metadata.get('longitude')
        if latitude is not None and longitude is not None:
            lat = float(latitude)
            lon = float(longitude)

            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = decimal_to_dms(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = 'N' if lat >= 0 else 'S'
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = decimal_to_dms(lon)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = 'E' if lon >= 0 else 'W'

        # Write EXIF to file
        exif_bytes = piexif.dump(exif_dict)
        img = Image.open(source_path)
        img.save(dest_path, "JPEG", exif=exif_bytes, quality=95)

        # Preserve file timestamps (try, but don't fail if it doesn't work)
        try:
            if source_path.exists():
                stat = source_path.stat()
                os.utime(dest_path, (stat.st_mtime, stat.st_mtime))
        except Exception as e:
            # Timestamp preservation is nice-to-have, not critical
            pass

        return True
    except Exception as e:
        print(f"Warning: Could not write EXIF metadata for {source_path.name}: {e}", file=sys.stderr)
        return False


def preserve_exif_metadata(source_path: Path, dest_path: Path, photo_metadata: Optional[dict] = None) -> bool:
    """Copy file and preserve EXIF metadata using Pillow if available.

    If photo_metadata is provided, writes SQLite metadata to EXIF.
    Otherwise, preserves existing EXIF from source file.
    """
    # If we have SQLite metadata and piexif, write it to EXIF
    if photo_metadata and HAS_PIEXIF:
        if write_exif_from_sqlite(source_path, dest_path, photo_metadata):
            return True
        # If writing failed, fall through to preserve existing EXIF

    # Otherwise, preserve existing EXIF from source
    if HAS_PILLOW:
        try:
            # Open source image
            img = Image.open(source_path)

            # Get EXIF data if it exists
            try:
                exif_dict = img.getexif()
            except:
                exif_dict = None

            # If source has EXIF data, preserve it
            if exif_dict and len(exif_dict) > 0:
                # Convert to bytes if needed
                try:
                    # Save with EXIF data, using format from source if possible
                    # Otherwise default to JPEG
                    save_format = img.format if img.format in ['JPEG', 'PNG'] else 'JPEG'
                    if save_format == 'JPEG':
                        img.save(dest_path, format='JPEG', exif=exif_dict, quality=95)
                    else:
                        img.save(dest_path, format=save_format, exif=exif_dict)
                except Exception as e:
                    # If saving with EXIF fails, try without
                    print(f"Warning: Could not save with EXIF for {source_path.name}: {e}", file=sys.stderr)
                    img.save(dest_path, format='JPEG', quality=95)
            else:
                # No EXIF, but convert to JPEG if needed
                if img.format and img.format != 'JPEG':
                    img.save(dest_path, format='JPEG', quality=95)
                else:
                    shutil.copy2(source_path, dest_path)

            # Preserve file timestamps (try, but don't fail if it doesn't work)
            try:
                if source_path.exists():
                    stat = source_path.stat()
                    os.utime(dest_path, (stat.st_mtime, stat.st_mtime))
            except Exception as e:
                # Timestamp preservation is nice-to-have, not critical
                pass

            return True
        except Exception as e:
            print(f"Warning: Could not process image {source_path.name}: {e}", file=sys.stderr)
            # Fall back to regular copy
            try:
                shutil.copy2(source_path, dest_path)
                return True  # File was copied successfully
            except Exception as e2:
                print(f"Error: Could not copy {source_path.name}: {e2}", file=sys.stderr)
                return False
    else:
        # No Pillow, just copy (preserves timestamps via copy2)
        # Note: This may not preserve EXIF if converting formats
        try:
            shutil.copy2(source_path, dest_path)
            return False
        except Exception as e:
            print(f"Error: Could not copy {source_path.name}: {e}", file=sys.stderr)
            return False


def generate_destination_filename(date_captured: str, hour_index: int) -> str:
    """Generate destination filename: YYYY-MM-DD-HH-{index:03d}.jpeg"""
    try:
        # Parse the date string - handle with or without microseconds
        try:
            dt = datetime.strptime(date_captured, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            # Try with microseconds
            dt = datetime.strptime(date_captured, '%Y-%m-%d %H:%M:%S.%f')

        # Format: YYYY-MM-DD-HH-{index:03d}
        filename = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}-{dt.hour:02d}-{hour_index:03d}"

        # Always return .jpeg extension
        return f"{filename}.jpeg"
    except ValueError:
        # If date parsing fails, use a fallback with sanitized date string
        sanitized = date_captured.replace(' ', '-').replace(':', '').split('.')[0]
        return f"{sanitized}-{hour_index:03d}.jpeg"


def export_photos_by_year(library_path: Path, year: int, destination: Path) -> None:
    """Export all photos for a given year to the destination directory."""
    # Ensure paths are absolute and resolved to prevent confusion
    library_path = library_path.resolve()
    destination = destination.resolve()

    # Safety check: ensure library_path and destination are different
    if library_path == destination:
        sys.exit(f"Error: Library path and destination cannot be the same: {library_path}")

    library_db_path = library_path / "Database" / "apdb" / "Library.apdb"
    properties_db_path = library_path / "Database" / "apdb" / "Properties.apdb"

    if not library_db_path.exists():
        sys.exit(f"Error: Library database not found at {library_db_path}")

    print(f"Querying database for photos from {year}...")
    photos = query_photos_for_year(library_db_path, properties_db_path, year)

    if not photos:
        print(f"No photos found for year {year}.")
        return

    print(f"Found {len(photos)} photos from {year}.")
    print(f"Exporting to: {destination}")
    print()

    # Track index per hour for uniqueness
    hour_indices = defaultdict(int)

    exported_count = 0
    skipped_count = 0
    error_count = 0

    for i, photo in enumerate(photos, 1):
        uuid = photo['uuid']
        date_captured = photo['date_captured']

        # Find source file
        source_file = find_source_file(photo, library_path)

        if not source_file:
            print(f"[{i}/{len(photos)}] SKIP: {uuid} - File not found")
            skipped_count += 1
            continue

        try:
            # Parse date to get month and hour - handle with or without microseconds
            try:
                dt = datetime.strptime(date_captured, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(date_captured, '%Y-%m-%d %H:%M:%S.%f')
            month = f"{dt.month:02d}"

            # Create destination directory: <destination>/MM/ap_extracted/
            dest_dir = destination / month / "ap_extracted"
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Get index for this hour
            hour_key = (dt.year, dt.month, dt.day, dt.hour)
            hour_indices[hour_key] += 1
            index = hour_indices[hour_key]

            # Generate destination filename
            dest_filename = generate_destination_filename(date_captured, index)
            dest_path = dest_dir / dest_filename

            # Ensure we use .jpeg extension (as per requirements)
            if dest_path.suffix.lower() not in ['.jpg', '.jpeg']:
                dest_path = dest_path.with_suffix('.jpeg')

            # Handle filename collisions (shouldn't happen with proper indexing, but just in case)
            collision_count = 0
            while dest_path.exists():
                collision_count += 1
                base_name = dest_path.stem
                dest_path = dest_dir / f"{base_name}-{collision_count:03d}{dest_path.suffix}"

            # Copy file with EXIF preservation and SQLite metadata writing
            preserve_exif_metadata(source_file, dest_path, photo_metadata=photo)

            exported_count += 1
            if (i % 100 == 0) or (i == len(photos)):
                print(f"[{i}/{len(photos)}] Exported: {dest_filename} from {source_file.name}")

        except Exception as e:
            print(f"[{i}/{len(photos)}] ERROR: {uuid} - {e}", file=sys.stderr)
            error_count += 1
            continue

    print()
    print("=" * 60)
    print(f"Export complete!")
    print(f"  Exported: {exported_count}")
    print(f"  Skipped:  {skipped_count}")
    print(f"  Errors:   {error_count}")
    print(f"  Total:    {len(photos)}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Export photos from an Aperture Library by year, organized by month.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export all photos from 2010
  %(prog)s "/path/to/Aperture Library.migratedaplibrary" --year 2010 --destination /Volumes/ChanPhotos1/Photos/2010

  # Export photos from 2011
  %(prog)s "/Volumes/ChanPhotosB/DATA/iMac Backup/Aperture Library.migratedaplibrary" --year 2011 --destination /Volumes/ChanPhotos1/Photos/2011
        """
    )
    parser.add_argument(
        "library_path",
        type=Path,
        help="Path to the .aplibrary or .migratedaplibrary bundle",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year to export (e.g., 2010)",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="Destination directory (e.g., /Volumes/ChanPhotos1/Photos/2010)",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.library_path.exists():
        sys.exit(f"Error: Library path does not exist: {args.library_path}")

    if not args.library_path.is_dir():
        sys.exit(f"Error: Library path is not a directory: {args.library_path}")

    # Create destination directory if it doesn't exist
    args.destination.mkdir(parents=True, exist_ok=True)

    # Export photos
    export_photos_by_year(args.library_path, args.year, args.destination)


if __name__ == "__main__":
    main()

