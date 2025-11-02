# Photos Library Database Schema Summary

## Location
Database: `/Volumes/ChanPhotosB/DATA/iMac Backup/Photos Library.photoslibrary/database/Photos.sqlite`

## Key Tables

### ZASSET (Main Photo/Asset Table)
This is the primary table that tracks all photos and videos in the library.

**Key Fields:**
- `Z_PK` - Primary key
- `ZUUID` - **UUID matching the filename** (e.g., `000A8095-A52E-4197-BBEB-261ED448BBC7`)
- `ZDATECREATED` - **Date captured** (Unix timestamp offset by 978307200 seconds from Jan 1, 2001)
  - To convert: `datetime(ZDATECREATED + 978307200, 'unixepoch')`
- `ZFILENAME` - Filename with extension (e.g., `000A8095-A52E-4197-BBEB-261ED448BBC7.jpeg`)
- `ZDIRECTORY` - Directory indicator (0 = originals)
- `ZWIDTH`, `ZHEIGHT` - Image dimensions
- `ZMASTER` - Links to ZCLOUDMASTER (if exists)

**Relationship:**
- UUID filename in `/originals/*/` matches `ZUUID` in this table
- Derivative filenames in `/resources/derivatives/*/` start with `ZUUID` followed by suffix (e.g., `_1_105_c`)

### ZEXTENDEDATTRIBUTES (Camera/EXIF Metadata)
Contains camera and EXIF metadata.

**Key Fields:**
- `Z_PK` - Primary key
- `ZASSET` - Foreign key to ZASSET
- `ZDATECREATED` - Date created (more precise timestamp)
- `ZCAMERAMAKE`, `ZCAMERAMODEL` - Camera information
- `ZAPERTURE`, `ZSHUTTERSPEED`, `ZISOSPEED` - Camera settings
- `ZLATITUDE`, `ZLONGITUDE` - GPS coordinates
- `ZFOCALLENGTH`, `ZEXPOSUREBIAS` - More camera settings

### ZINTERNALRESOURCE (Resources/Derivatives)
Tracks different resource types for each asset (originals, thumbnails, derivatives, etc.).

**Key Fields:**
- `Z_PK` - Primary key
- `ZASSET` - Foreign key to ZASSET
- `ZRESOURCETYPE` - Type of resource:
  - 0 = Original/Full size
  - 1 = Thumbnail
  - 3 = Render/Derivative
  - 4 = Other
  - 5 = Sidecar
  - 31 = Other
- `ZFINGERPRINT` - Fingerprint/hash (may be empty)
- `ZSTABLEHASH` - Stable hash identifier
- `ZFILEID` - File identifier

### ZADDITIONALASSETATTRIBUTES (Additional Metadata)
Contains additional asset attributes.

**Key Fields:**
- `Z_PK` - Primary key
- `ZASSET` - Foreign key to ZASSET
- Various metadata fields

### ZCLOUDMASTER (Cloud/Online Master Records)
Contains master records for cloud-synced photos (may be empty for older libraries).

**Key Fields:**
- `Z_PK` - Primary key
- `ZCLOUDMASTERGUID` - Cloud GUID
- `ZCREATIONDATE` - Creation date
- `ZORIGINALFILENAME` - Original filename

### ZCLOUDRESOURCE (Cloud Resources)
Contains cloud resource information (may be empty for older libraries).

**Key Fields:**
- `Z_PK` - Primary key
- `ZASSETUUID` - UUID of associated asset
- `ZFINGERPRINT` - Fingerprint
- `ZFILEPATH` - File path
- `ZTYPE` - Resource type

## File Structure Mapping

### Originals
- Path pattern: `/originals/{hash}/{UUID}.{ext}`
- Example: `/originals/0/000A8095-A52E-4197-BBEB-261ED448BBC7.jpeg`
- UUID matches `ZASSET.ZUUID`
- **Hash directory** = First character of UUID (0-9, A-F)
  - The first character of the UUID determines which subdirectory it's stored in
  - This allows for better file system performance with large libraries

### Derivatives
- Path pattern: `/resources/derivatives/{hash}/{UUID}_{suffix}.{ext}`
- Example: `/resources/derivatives/0/000A8095-A52E-4197-BBEB-261ED448BBC7_1_105_c.jpeg`
- UUID prefix matches `ZASSET.ZUUID`
- Hash directory follows the same rule (first character of UUID)

### Legacy Format (iPhoto/Aperture)
- Some older photos may have `ZDIRECTORY` containing a full path (e.g., `Photos/2011/01/...`)
- These may be located in:
  - `/Masters.legacy/` directory
  - Or may have been migrated to the new hash-based structure

## Sample Query

```sql
SELECT
    a.ZUUID,
    datetime(a.ZDATECREATED + 978307200, 'unixepoch') as date_captured,
    a.ZFILENAME,
    a.ZDIRECTORY,
    substr(a.ZUUID, 1, 1) as hash_directory,
    a.ZWIDTH,
    a.ZHEIGHT,
    e.ZCAMERAMAKE,
    e.ZCAMERAMODEL,
    e.ZAPERTURE,
    e.ZSHUTTERSPEED,
    e.ZISO,
    e.ZLATITUDE,
    e.ZLONGITUDE
FROM ZASSET a
LEFT JOIN ZEXTENDEDATTRIBUTES e ON a.ZEXTENDEDATTRIBUTES = e.Z_PK
WHERE a.ZUUID = '000A8095-A52E-4197-BBEB-261ED448BBC7';
```

## Path Construction

To find a file's location within the photoslibrary package:

1. **Extract the UUID** from `ZASSET.ZUUID`
2. **Get the hash directory** = first character of UUID (uppercase)
3. **Construct the path**:
   - Original: `originals/{hash_dir}/{ZUUID}.{extension}`
   - Derivatives: `resources/derivatives/{hash_dir}/{ZUUID}_{suffix}.{ext}`
4. **Check if file exists** at that location

The `photo-metadata.py` script includes a `get_file_paths()` function that automatically constructs and verifies these paths.

