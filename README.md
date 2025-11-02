# Mac Photo Extractor

Tools for analyzing and extracting metadata from macOS Photos Library packages.

## ⭐ photo-export.py - Export Photos by Year

**The main feature of this repository** - Export all photos from a Photos Library organized by year and month, with EXIF metadata preserved.

This script extracts photos from a `.photoslibrary` package and organizes them into a structured directory hierarchy. Photos are automatically named with their capture date and time, making it easy to organize and browse your exported collection.

### Features

- ✅ **Export by Year**: Export all photos from a specific year
- ✅ **Smart File Finding**: Automatically finds originals first, falls back to derivatives if needed
- ✅ **EXIF Preservation**: Preserves creation dates and camera metadata using Pillow
- ✅ **Organized Structure**: Photos organized by month with descriptive filenames
- ✅ **Unique Filenames**: Automatic indexing ensures no filename collisions

### Usage

**Basic usage:**
```bash
python3 photo-export.py "/path/to/Photos Library.photoslibrary" --year 2014 --destination /Volumes/ChanPhotos1/Photos/2014
```

**Example:**
```bash
python3 photo-export.py "/Volumes/ChanPhotosB/DATA/iMac Backup/Photos Library.photoslibrary" --year 2006 --destination /Volumes/ChanPhotos1/Photos/2006
```

### Output Structure

Photos are exported to the destination directory with the following structure:

```
<destination>/MM/extracted/YYYY-MM-DD-HH-{index}.jpeg
```

**Example path:**
```
/Volumes/ChanPhotos1/Photos/2006/10/extracted/2006-10-01-13-001.jpeg
```

Where:
- `2006/` - Year directory (matches `--destination`)
- `10/` - Month directory (01-12)
- `extracted/` - Subdirectory containing the actual photos
- `2006-10-01-13-001.jpeg` - Filename format: `YYYY-MM-DD-HH-{index:03d}.jpeg`

The index (001, 002, etc.) ensures uniqueness when multiple photos were taken in the same hour.

### File Selection Logic

1. **First Priority**: Original files from `/originals/{hash}/{UUID}.{ext}`
2. **Second Priority**: JPEG derivatives from `/resources/derivatives/{hash}/{UUID}_{suffix}.jpeg`
3. **Third Priority**: Any other derivative files found

This ensures you get the highest quality version available while gracefully handling cases where originals might be missing.

### EXIF Metadata

**The script actively writes metadata from the SQLite database into the EXIF of exported JPEG files.** This is important because the original JPEG files in your Photos Library may not contain complete EXIF metadata - much of it is stored only in the Photos app's SQLite database.

The script embeds the following metadata from the database:
- **Creation date/time** (`DateTimeOriginal` and `DateTimeDigitized`)
- **Camera make and model**
- **Camera settings** (aperture/f-number, ISO speed, shutter speed/exposure time, focal length)
- **Exposure bias**
- **White balance and flash settings**
- **GPS coordinates** (if available in the database)

The script:
1. Loads any existing EXIF from the source file
2. Merges/overwrites with metadata from the SQLite database
3. Writes the combined EXIF data to the exported JPEG

**Requirements**: For full EXIF metadata writing, install:
```bash
pip install Pillow piexif
```

- `Pillow` - Required for basic image processing
- `piexif` - Required for writing EXIF metadata to JPEG files

Without `piexif`, the script will only preserve existing EXIF from source files but won't add the rich metadata from your Photos Library database.

### Options

- `library_path` (required): Path to the `.photoslibrary` bundle
- `--year` (required): Year to export (e.g., `2014`, `2006`)
- `--destination` (required): Destination directory (e.g., `/Volumes/ChanPhotos1/Photos/2014`)

### Example Output

```
Querying database for photos from 2014...
Found 9641 photos from 2014.
Exporting to: /Volumes/ChanPhotos1/Photos/2014

[100/9641] Exported: 2014-01-15-14-042.jpeg from 000A8095-A52E-4197-BBEB-261ED448BBC7.jpeg
[200/9641] Exported: 2014-02-22-09-023.jpeg from A136EC4B-C9C1-4C51-99C1-B62C7390011D.jpg
...
[9641/9641] Exported: 2014-12-31-23-089.jpeg from FEDC1516-03A8-4DD1-BF47-1499BFE84A96.jpg

============================================================
Export complete!
  Exported: 9641
  Skipped:  0
  Errors:   0
  Total:    9641
============================================================
```

---

## Tools

### photo-scan.py

Recursively scans a Photos/Aperture library (or any directory) and produces a summary per sub-folder:
- Total number of image files
- Cumulative size
- Average file size
- List of the most common image extensions

**Usage:**
```bash
python3 photo-scan.py "/path/to/Photos Library.photoslibrary"
```

**Options:**
- `--group-size-thresholds`: Comma-separated size thresholds for grouping (e.g., '500KB,100KB')
- `--display-limit`: Maximum number of folders to display (default: 1000)
- `--dump-all-folders`: Show all individual folder statistics

**Example:**
```bash
python3 photo-scan.py "/Volumes/ChanPhotosB/DATA/iMac Backup/Photos Library.photoslibrary" --group-size-thresholds "500KB,100KB"
```

### photo-metadata.py

Query the Photos Library SQLite database to extract metadata for photos by UUID and generate reports.

This tool can:
- Look up a photo by UUID and display its metadata
- Export metadata for all photos to CSV
- Generate a report of photos grouped by year of capture
- Show file locations within the photoslibrary package

**Usage:**

**Look up a specific photo by UUID:**
```bash
python3 photo-metadata.py "/path/to/Photos Library.photoslibrary" --uuid "000A8095-A52E-4197-BBEB-261ED448BBC7"
```

**Show resources/derivatives for a photo:**
```bash
python3 photo-metadata.py "/path/to/Photos Library.photoslibrary" --uuid "000A8095-A52E-4197-BBEB-261ED448BBC7" --show-resources
```

**Export all photos to CSV:**
```bash
python3 photo-metadata.py "/path/to/Photos Library.photoslibrary" --export-csv photos_metadata.csv
```

**Export first 100 photos (for testing):**
```bash
python3 photo-metadata.py "/path/to/Photos Library.photoslibrary" --export-csv photos_metadata.csv --limit 100
```

**Generate a year report (console output):**
```bash
python3 photo-metadata.py "/path/to/Photos Library.photoslibrary" --year-report
```

**Export year report to CSV:**
```bash
python3 photo-metadata.py "/path/to/Photos Library.photoslibrary" --export-year-report year_report.csv
```

**Options:**
- `--uuid UUID`: Look up a specific photo by UUID
- `--show-resources`: Show resources/derivatives when looking up by UUID
- `--export-csv PATH`: Export all photos to CSV file
- `--limit N`: Limit number of results when exporting
- `--year-report`: Generate a report of photos grouped by year of capture
- `--export-year-report PATH`: Export year report to CSV file

**Example Output:**

When looking up a photo, you'll see:
- UUID and filename
- Original file location within the library (e.g., `originals/0/000A8095-A52E-4197-BBEB-261ED448BBC7.jpeg`)
- Derivatives/thumbnails if they exist
- Date captured and date added
- Image dimensions
- Camera information (make, model, aperture, ISO, etc.)
- GPS location if available

The year report shows:
- Count of photos per year
- Percentage of total
- Visual bar chart

## File Structure Mapping

Photos are stored in the photoslibrary package using UUID-based filenames:
- **Originals**: `originals/{hash}/{UUID}.{ext}` where `{hash}` is the first character of the UUID (0-9, A-F)
- **Derivatives**: `resources/derivatives/{hash}/{UUID}_{suffix}.{ext}`

The SQLite database at `database/Photos.sqlite` contains all metadata and can be queried to map UUIDs to:
- Date captured
- Camera settings
- GPS location
- File locations within the package

See `database_schema_summary.md` for detailed database schema information.

## Requirements

- Python 3.6+
- Standard library modules: `sqlite3`, `pathlib`, `argparse`, `csv`, `datetime`, `shutil`, `collections`, `importlib`
- **Required for EXIF metadata writing in photo-export.py**:
  - `Pillow` - Basic image processing
  - `piexif` - Full EXIF metadata reading/writing
  - Install with: `pip install Pillow piexif`

**Note**: Without `piexif`, `photo-export.py` will only preserve existing EXIF metadata from source files but won't add metadata from the SQLite database to exported files.

## How It Works

The `photo-export.py` script uses the following workflow:

1. **Query Database**: Connects to `database/Photos.sqlite` and queries all photos from the specified year
2. **Find Source Files**: For each photo, searches for the original file first, then derivatives
3. **Organize by Date**: Groups photos by capture date to create month directories
4. **Generate Filenames**: Creates descriptive filenames based on capture date/time with unique indices
5. **Preserve Metadata**: Uses Pillow to preserve EXIF data when copying/converting files
6. **Progress Reporting**: Shows progress and summary statistics

The script imports functionality from `photo-metadata.py` to avoid code duplication, including:
- Database query functions
- File path resolution
- Timestamp conversion utilities
