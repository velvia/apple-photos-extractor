# Mac Photo Extractor

Tools for analyzing and extracting metadata from macOS Photos Library packages.

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
- Standard library only (sqlite3, pathlib, argparse, csv, datetime)
