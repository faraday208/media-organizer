# Media Organizer

A Python CLI + library that organizes media files for AI dataset preparation: sequential renaming by type and creation time, optional relocation (copy/move to a separate output directory), and undo support for any previous run.

## What Does This Tool Do?

**Problem**: You have a folder with hundreds of media files with messy, inconsistent names.

**Solution**: This tool renames all media files in a clean, organized format:
- Groups files by type (images, videos, audio)
- Sorts each group by creation time (oldest to newest)
- Renames with sequential numbers: `prefix_1.jpg`, `prefix_2.jpg`, `prefix_1.mp4`, etc.
- Each file type gets its own numbering sequence

## Quick Example

**Before:**
```
MyVacation/
├── IMG_3847.jpg (created 2024-01-15)
├── DSC_0291.jpg (created 2024-01-10)
├── VID_2847.mp4 (created 2024-01-12)
├── photo_final.png (created 2024-01-11)
├── video_edit.mp4 (created 2024-01-09)
└── recording.mp3 (created 2024-01-14)
```

**After running:**
```bash
python3 media_organizer.py /path/to/MyVacation --prefix "Vacation"
```

**Result:**
```
MyVacation/
├── Vacation_1.jpg (DSC_0291.jpg - 2024-01-10)
├── Vacation_2.png (photo_final.png - 2024-01-11)
├── Vacation_3.jpg (IMG_3847.jpg - 2024-01-15)
├── Vacation_1.mp4 (video_edit.mp4 - 2024-01-09)
├── Vacation_2.mp4 (VID_2847.mp4 - 2024-01-12)
└── Vacation_1.mp3 (recording.mp3 - 2024-01-14)
```

Notice:
- JPG files: numbered 1-3 by creation date
- MP4 files: numbered 1-2 by creation date (separate sequence)
- MP3 files: numbered 1 (separate sequence)

**With `--include-extension` flag:**
```
MyVacation/
├── Vacation_jpg_1.jpg (DSC_0291.jpg - 2024-01-10)
├── Vacation_png_1.png (photo_final.png - 2024-01-11)
├── Vacation_jpg_2.jpg (IMG_3847.jpg - 2024-01-15)
├── Vacation_mp4_1.mp4 (video_edit.mp4 - 2024-01-09)
├── Vacation_mp4_2.mp4 (VID_2847.mp4 - 2024-01-12)
└── Vacation_mp3_1.mp3 (recording.mp3 - 2024-01-14)
```

This mode includes the extension in the filename, making it impossible to have naming conflicts between different file types.

## Features

✅ **Sequential Numbering by Type**: Each file format gets its own number sequence
✅ **EXIF-Aware Sorting**: Images sorted by EXIF `DateTimeOriginal` when available; falls back to `mtime` (which survives `cp -p` and `rsync`, unlike `ctime`)
✅ **Multi-Format Support**: Images, videos, and audio files
✅ **Three Operation Modes**: in-place rename, copy to output dir (sources preserved), or move to output dir
✅ **Undo Support**: Reverse any previous run from its `rename_report.json` (in-place / copy / move all supported)
✅ **Dry-Run Mode**: Preview changes — including undo previews — before applying
✅ **Custom Prefix**: Use any prefix you want
✅ **Extension in Filename**: Optional mode to include extension in filename
✅ **JSON Report**: Detailed log of all renames (written even in dry-run; embedded `mode` enables exact undo)
✅ **Conflict Detection**: Warns about potential naming conflicts
✅ **Safe Operation**: Non-recursive (only processes target directory)

## Supported File Types

### Images
`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`, `.tiff`, `.tif`, `.heic`, `.raw`

### Videos
`.mp4`, `.avi`, `.mov`, `.mkv`, `.flv`, `.wmv`, `.webm`, `.m4v`, `.mpeg`, `.mpg`

### Audio
`.mp3`, `.wav`, `.flac`, `.aac`, `.m4a`, `.ogg`, `.wma`, `.opus`

## Installation

No required dependencies — uses only the Python standard library.

**Requirements:**
- Python 3.6+

**Optional (recommended for image collections):**
- [Pillow](https://pypi.org/project/Pillow/) — `pip install Pillow`
  Enables EXIF `DateTimeOriginal` reading so images get sorted by their actual capture time. Without Pillow, images fall back to filesystem `mtime`.

## Usage

### Basic Usage

```bash
# Dry run (preview only - recommended first step)
python3 media_organizer.py /path/to/folder --dry-run

# In-place rename (uses folder name as prefix)
python3 media_organizer.py /path/to/folder

# Custom prefix
python3 media_organizer.py /path/to/folder --prefix "MyPhotos"

# Include extension in filename
python3 media_organizer.py /path/to/folder --include-extension

# Copy to a separate output directory (sources untouched — safest)
python3 media_organizer.py /path/to/folder --output-dir /path/organized

# Move to output directory (sources removed)
python3 media_organizer.py /path/to/folder --output-dir /path/organized --move

# Combine options
python3 media_organizer.py /path/to/folder --prefix "Summer2024" --include-extension --dry-run
```

### Command Line Options

```
python3 media_organizer.py <directory> [OPTIONS]

Required:
  <directory>           Path to folder containing media files

Optional:
  --prefix <name>       Custom prefix for renamed files
                        Default: uses directory name

  --include-extension   Include extension in filename
                        Format: prefix_ext_number.ext
                        Example: MyPhotos_jpg_1.jpg
                        Default: prefix_number.ext

  --output-dir <path>   Write renamed files to this directory.
                        Sources stay untouched (copy mode).
                        Created automatically if missing.
                        Default: write next to source (in-place rename).

  --move                With --output-dir: MOVE files instead of copying.
                        Sources are removed, output dir is populated.
                        Useless without --output-dir (errors out).

  --undo <report>       Reverse a previous run using its rename_report.json.
                        Behavior auto-determined from the recorded mode:
                          in-place → revert names (os.rename)
                          copy     → delete copies (sources untouched)
                          move     → move files back to source

  --dry-run             Preview mode - shows what would happen
                        without actually modifying any file
                        (works with both forward and undo runs)
```

### Operation Modes

| Flags | Behavior | Sources after run |
|---|---|---|
| _(none)_ | In-place rename (`os.rename`) | Same files, new names |
| `--output-dir <path>` | Copy with new names (`shutil.copy2`) | Untouched — full backup |
| `--output-dir <path> --move` | Move with new names (`shutil.move`) | Empty — files relocated |
| `--undo <report>` | Auto-reverse from JSON report | Restored to pre-run state |

### Undo

Every run writes a `rename_report.json` with absolute `old_path` ↔ `new_path` mappings plus the `mode` used. To reverse a run, point `--undo` at that report:

```bash
# Önce ne geri alacağını gör
python3 media_organizer.py --undo /path/photos/rename_report.json --dry-run

# Sonra gerçeği
python3 media_organizer.py --undo /path/photos/rename_report.json
```

**Güvenlik:** Undo, hedef dosya artık yoksa ya da eski yol başka bir dosyayla doluysa o kaydı **atlar** ve uyarı basar — hiçbir zaman üzerine yazma yapmaz.

**Tip:** For destructive `--output-dir` modes, run `--dry-run` first; the JSON plan tells you exactly which target paths will be created before any file moves.

## Examples

### Example 1: Test First with Dry Run

```bash
# See what will happen without making changes
python3 media_organizer.py "/home/user/Photos/Birthday2024" --dry-run
```

Output:
```
================================================================================
MEDIA FILE RENAMER
================================================================================
Directory: /home/user/Photos/Birthday2024
Prefix: Birthday2024
Mode: DRY RUN

Scanning directory: /home/user/Photos/Birthday2024
================================================================================
Found 45 media files
File types: .jpg, .mp4, .png

.JPG files (30):
--------------------------------------------------------------------------------
  IMG_3421.jpg → Birthday2024_1.jpg
  IMG_3422.jpg → Birthday2024_2.jpg
  ...

.MP4 files (10):
--------------------------------------------------------------------------------
  VID_1234.mp4 → Birthday2024_1.mp4
  ...

.PNG files (5):
--------------------------------------------------------------------------------
  screenshot.png → Birthday2024_1.png
  ...
```

### Example 2: Rename with Custom Prefix

```bash
python3 media_organizer.py "/media/Photos" --prefix "Summer2024"
```

All media files in `/media/Photos` will be renamed as:
- `Summer2024_1.jpg`, `Summer2024_2.jpg`, etc.
- `Summer2024_1.mp4`, `Summer2024_2.mp4`, etc.

### Example 3: Include Extension to Avoid Conflicts

```bash
# When you have mixed file types (jpg, jpeg, png, etc.)
python3 media_organizer.py "/path/to/folder" --prefix "MyPhotos" --include-extension

# Result:
# MyPhotos_jpg_1.jpg, MyPhotos_jpg_2.jpg
# MyPhotos_jpeg_1.jpeg, MyPhotos_jpeg_2.jpeg
# MyPhotos_png_1.png, MyPhotos_png_2.png
# No naming conflicts between different extensions!
```

### Example 4: Large Photo Collection

```bash
# You have 1200+ photos from a photo shoot
python3 media_organizer.py "/mnt/external/PhotoShoot" --prefix "ClientName" --dry-run

# Review the output, then execute
python3 media_organizer.py "/mnt/external/PhotoShoot" --prefix "ClientName"
```

## How It Works

1. **Scan Directory**
   - Finds all media files (non-recursive)
   - Groups by file extension

2. **Sort by Best-Available Timestamp**
   - Each file type is sorted independently
   - Priority order:
     1. **EXIF `DateTimeOriginal`** (images, requires Pillow) — survives copying
     2. **`st_birthtime`** (macOS/BSD only) — true filesystem creation time
     3. **`st_mtime`** (modification time) — survives `cp -p` and `rsync`
   - `st_ctime` is intentionally NOT used: on Linux it tracks metadata-change time and gets reset by `cp`, `mv`, `chmod`, etc.

3. **Generate Rename Plan**
   - Assigns sequential numbers starting from 1
   - Each file type has its own sequence
   - Format: `{prefix}_{number}{extension}`

4. **Check for Conflicts**
   - Detects existing files with target names
   - Warns about duplicate names in plan

5. **Execute Rename**
   - Renames files according to plan
   - Creates JSON report with complete mapping

## Output Report

A `rename_report.json` file is written to the target directory after every run — including dry-run mode. This lets you inspect the planned mapping before committing to the rename, and keeps a permanent record afterwards. Example:

```json
{
  "timestamp": "2024-11-15T22:30:45",
  "total_files": 1277,
  "renames": [
    {
      "old_path": "/path/to/IMG_3847.jpg",
      "new_path": "/path/to/Vacation_1.jpg",
      "old_filename": "IMG_3847.jpg",
      "new_filename": "Vacation_1.jpg",
      "extension": ".jpg",
      "sort_time": "2024-01-15T10:23:45",
      "time_source": "exif",
      "index": 1
    },
    ...
  ]
}
```

## Use Cases

### Photography & Video Production
- Organize client photo shoots
- Rename event videos chronologically
- Clean up camera dump folders

### Content Creation
- Organize social media assets
- Rename video project files
- Sort podcast audio files

### Media Libraries
- Standardize file naming conventions
- Prepare files for archival
- Create consistent naming for media servers

### Digital Asset Management
- Batch rename product photos
- Organize marketing materials
- Clean up downloaded media files

## Safety Features

✅ **Dry-run mode**: Test before executing
✅ **Conflict detection**: Warns about existing files
✅ **Detailed reporting**: JSON log of all changes
✅ **Non-recursive**: Only processes specified directory
✅ **Preserves extensions**: Original formats maintained
✅ **Timestamp-based**: Chronological organization

## Important Notes

- **Default is in-place**: Without `--output-dir`, source files are renamed where they sit. Use `--output-dir` for a non-destructive copy if you want to preserve originals.
- **Single directory**: Does not process subdirectories
- **File extensions preserved**: `.jpg` stays `.jpg`, `.mp4` stays `.mp4`
- **Sort time**: EXIF `DateTimeOriginal` for images (when Pillow installed), otherwise filesystem `mtime`. Console + JSON report show which source was used per file.
- **No duplicates**: Each file type gets unique sequential numbers
- **Output dir auto-created**: `--output-dir` creates the path if it doesn't exist (`mkdir -p` semantics)
- **Same dir guard**: If `--output-dir` resolves to the same path as the input, the tool falls back to in-place rename and prints a note

## Limitations

- Only processes files in the specified directory (not subdirectories)
- Requires write permissions in target directory
- Without Pillow installed, image sorting falls back to `mtime` (loses EXIF precision for copied/moved files)
- Video and audio files always use `mtime` (no EXIF equivalent is read)
- Does not modify EXIF data or file contents

## Troubleshooting

**Files not found?**
- Ensure path is correct and contains supported media files
- Check file extensions match supported formats

**Permission errors?**
- Verify write permissions in target directory
- Run with appropriate user privileges

**Naming conflicts?**
- Review conflict warnings
- Use different prefix or move conflicting files first

## Project Structure

```
media-organizer/
├── media_organizer.py   # CLI + library (single file)
├── pyproject.toml     # Dependency tanımı (uv / pip)
├── LICENSE
├── .gitignore
└── README.md
```

## Future Features (Planned)

- Subdirectory support with grouping options (organize files into year/month folders, by media type, etc.)
- Multiple sorting methods (size, name, modified date)
- Batch processing of multiple directories

## License

MIT License - Feel free to use and modify

## Contributing

This is a simple utility tool. Feel free to fork and enhance!

## Version

**v0.4.0** - Reverted to `media-organizer` + module renamed to `media_organizer.py`
- v0.2.0'da `media-renamer`'a geçilmişti; ama o noktadan sonra eklenen
  `--output-dir`, `--move`, `--undo` özellikleri tool'u saf rename'in
  ötesine taşıdı (kopyalama, taşıma, geri alma — yerleşim de değiştiriyor).
- Roadmap'teki "Subdirectory support with grouping" tam organize işi.
- Dolayısıyla repo `media-organizer` adına geri döndü; ama eski
  tutarsızlığı tekrarlamamak için modül adı `rename_files.py` değil,
  `media_organizer.py` (paket adıyla uyumlu, Python identifier).
- In-process import: `from media_organizer import generate_rename_plan, ...`
- Davranışsal değişiklik yok — tüm v0.3.0 özellikleri korunuyor.

**v0.3.0** - Undo support
- New `--undo <report.json>` flag: reverses a previous run from its JSON report.
- Behavior auto-detected from the report's `mode` field:
  - in-place → `os.rename` back to old names
  - copy → delete copies in output dir (sources untouched)
  - move → `shutil.move` files back to original locations
- Skips records (with warning) when target file is missing or origin path is occupied.
- Works with `--dry-run` for safe preview.
- `rename_report.json` now records the `mode` used (backward-compat: missing field assumes 'rename').

**v0.2.0** *(reverted in v0.4.0)* - Renamed `media-organizer` → `media-renamer`
- Çağrı için: bu sürümde repo/modül adı geçici olarak `media-renamer`'a değişti.
- v0.4.0 ile geri alındı (yukarıdaki not'a bakın).

**v0.1.x history (eski standalone `media-organizer` döneminde):**

**v1.2.0** - Output directory + copy/move modes
- New `--output-dir` flag: write renamed files to a separate directory (copy mode); sources untouched.
- New `--move` flag (requires `--output-dir`): move files instead of copying (sources removed).
- Default behavior unchanged: without `--output-dir`, in-place rename as before.
- `--output-dir` is auto-created with `mkdir -p` semantics; if it equals the input dir the tool falls back to in-place with a notice.
- Minor: console output now prints "Operation: ..." line so the chosen mode is unambiguous.

**v1.1.0** - EXIF-aware sorting
- Reads EXIF `DateTimeOriginal` for image files when Pillow is installed
- Falls back to `mtime` instead of unreliable `ctime` (which gets reset by `cp`/`mv`/`chmod`)
- Reports per-file sort-time source in console output and JSON report
- New optional dependency: Pillow (graceful fallback when missing)

**v1.0.0** - Initial release
- Basic rename functionality
- Sequential numbering by type
- Creation time sorting
- Dry-run mode

---

**Created for organizing media files efficiently and consistently.**
