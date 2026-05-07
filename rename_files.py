#!/usr/bin/env python3
"""
Media File Renamer
Renames media files by type with sequential numbering, sorted by creation time.

Sort-time priority (most accurate first):
  1. EXIF DateTimeOriginal (image files, requires Pillow)
  2. st_birthtime           (true creation time, macOS/BSD only)
  3. st_mtime               (modification time; survives `cp -p` and rsync)

Note: st_ctime is intentionally NOT used. On Linux it reflects metadata-change
time, not creation time, so any chmod/chown/move resets it.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False


IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.raw'
}

VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpeg', '.mpg'
}

AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg', '.wma', '.opus'
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# EXIF tag IDs for date fields (priority order: capture > digitized > generic)
EXIF_DATE_TAGS = (36867, 36868, 306)
EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def get_image_exif_datetime(filepath):
    """Read EXIF DateTimeOriginal (or fallback) from an image. Returns Unix timestamp or None."""
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(filepath) as img:
            exif = img.getexif()
            if not exif:
                return None
            for tag in EXIF_DATE_TAGS:
                value = exif.get(tag)
                if value:
                    return datetime.strptime(value, EXIF_DATETIME_FORMAT).timestamp()
        return None
    except Exception:
        return None


def get_file_sort_time(filepath, ext):
    """
    Get best-available timestamp for chronological sorting.
    Returns (timestamp, source) tuple, or (None, None) on error.
    """
    if ext in IMAGE_EXTENSIONS:
        exif_time = get_image_exif_datetime(filepath)
        if exif_time is not None:
            return (exif_time, 'exif')

    try:
        stat_info = os.stat(filepath)
        # st_birthtime: real creation time on macOS/BSD; not available on Linux
        if hasattr(stat_info, 'st_birthtime') and stat_info.st_birthtime > 0:
            return (stat_info.st_birthtime, 'birthtime')
        return (stat_info.st_mtime, 'mtime')
    except Exception as e:
        print(f"Error reading timestamp for {filepath}: {e}")
        return (None, None)


def scan_directory(directory):
    """
    Scan directory for media files and group by extension.
    Returns dict: extension -> list of (filepath, timestamp, source) tuples.
    """
    files_by_ext = defaultdict(list)
    source_counts = defaultdict(int)

    print(f"Scanning directory: {directory}")
    print("=" * 80)

    if not PIL_AVAILABLE:
        print("Note: Pillow not installed — falling back to filesystem mtime for images.")
        print("      For accurate EXIF-based sorting, run:  pip install Pillow")
        print()

    try:
        all_files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    except Exception as e:
        print(f"Error reading directory: {e}")
        return {}

    media_count = 0
    for filename in all_files:
        filepath = os.path.join(directory, filename)
        ext = Path(filename).suffix.lower()

        if ext in MEDIA_EXTENSIONS:
            timestamp, source = get_file_sort_time(filepath, ext)
            if timestamp is not None:
                files_by_ext[ext].append((filepath, timestamp, source))
                source_counts[source] += 1
                media_count += 1

    print(f"Found {media_count} media files")
    if files_by_ext:
        print(f"File types: {', '.join(sorted(files_by_ext.keys()))}")
    if source_counts:
        breakdown = ', '.join(f"{count} via {source}" for source, count in sorted(source_counts.items()))
        print(f"Sort-time sources: {breakdown}")
    print()

    return files_by_ext


def generate_rename_plan(files_by_ext, prefix, include_extension=False):
    """Sort each file group by timestamp and assign sequential numbers."""
    rename_plan = []

    for ext, file_list in files_by_ext.items():
        sorted_files = sorted(file_list, key=lambda x: x[1])

        for idx, (old_path, timestamp, source) in enumerate(sorted_files, 1):
            directory = os.path.dirname(old_path)

            if include_extension:
                ext_name = ext.lstrip('.')
                new_filename = f"{prefix}_{ext_name}_{idx}{ext}"
            else:
                new_filename = f"{prefix}_{idx}{ext}"

            new_path = os.path.join(directory, new_filename)

            rename_plan.append({
                'old_path': old_path,
                'new_path': new_path,
                'old_filename': os.path.basename(old_path),
                'new_filename': new_filename,
                'extension': ext,
                'sort_time': datetime.fromtimestamp(timestamp).isoformat(),
                'time_source': source,
                'index': idx
            })

    return rename_plan


def check_conflicts(rename_plan):
    """Detect existing files that would be overwritten and duplicate target names."""
    conflicts = []
    new_names = set()
    sources = {item['old_path'] for item in rename_plan}

    for item in rename_plan:
        new_path = item['new_path']

        if os.path.exists(new_path) and new_path not in sources:
            conflicts.append({'new_path': new_path, 'reason': 'File already exists'})

        if new_path in new_names:
            conflicts.append({'new_path': new_path, 'reason': 'Duplicate name in rename plan'})
        else:
            new_names.add(new_path)

    return conflicts


def execute_rename(rename_plan, dry_run=True):
    """Apply (or simulate) the rename plan."""
    print("=" * 80)
    print("DRY RUN MODE - No files will be renamed" if dry_run else "RENAMING FILES")
    print("=" * 80)
    print()

    success_count = 0
    error_count = 0

    by_ext = defaultdict(list)
    for item in rename_plan:
        by_ext[item['extension']].append(item)

    for ext, items in sorted(by_ext.items()):
        print(f"\n{ext.upper()} files ({len(items)}):")
        print("-" * 80)

        for item in items:
            old_name = item['old_filename']
            new_name = item['new_filename']

            if dry_run:
                print(f"  {old_name} → {new_name}")
                success_count += 1
            else:
                try:
                    os.rename(item['old_path'], item['new_path'])
                    print(f"  ✓ {old_name} → {new_name}")
                    success_count += 1
                except Exception as e:
                    print(f"  ✗ {old_name} → {new_name} (Error: {e})")
                    error_count += 1

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files: {len(rename_plan)}")
    print(f"Successful: {success_count}")
    if error_count > 0:
        print(f"Errors: {error_count}")

    if dry_run:
        print("\nThis was a DRY RUN. No files were actually renamed.")
        print("Run without --dry-run to perform the actual rename.")


def save_report(rename_plan, output_file="rename_report.json"):
    """Save rename plan to JSON file."""
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_files': len(rename_plan),
        'pillow_available': PIL_AVAILABLE,
        'renames': rename_plan
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRename plan saved to: {output_file}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 rename_files.py <directory> [OPTIONS]")
        print("\nArguments:")
        print("  directory           : Directory containing media files to rename")
        print("\nOptions:")
        print("  --prefix <name>     : Prefix for renamed files (default: directory name)")
        print("  --include-extension : Include extension in filename (e.g., prefix_jpg_1.jpg)")
        print("  --dry-run           : Simulate rename without actually changing files")
        print("\nExamples:")
        print('  python3 rename_files.py "/path/to/photos" --dry-run')
        print('  python3 rename_files.py "/path/to/photos" --prefix "Vacation2024"')
        print('  python3 rename_files.py "/path/to/photos" --include-extension')
        sys.exit(1)

    target_dir = sys.argv[1]
    prefix = None
    dry_run = False
    include_extension = False

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--prefix' and i + 1 < len(sys.argv):
            prefix = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--dry-run':
            dry_run = True
            i += 1
        elif sys.argv[i] == '--include-extension':
            include_extension = True
            i += 1
        else:
            i += 1

    if prefix is None:
        prefix = os.path.basename(os.path.abspath(target_dir))

    if not os.path.exists(target_dir):
        print(f"Error: Directory not found: {target_dir}")
        sys.exit(1)

    if not os.path.isdir(target_dir):
        print(f"Error: Not a directory: {target_dir}")
        sys.exit(1)

    print()
    print("=" * 80)
    print("MEDIA FILE RENAMER")
    print("=" * 80)
    print(f"Directory: {target_dir}")
    print(f"Prefix: {prefix}")
    print(f"Include extension: {'Yes' if include_extension else 'No'}")
    print(f"Mode: {'DRY RUN' if dry_run else 'RENAME'}")
    print()

    files_by_ext = scan_directory(target_dir)

    if not files_by_ext:
        print("No media files found!")
        sys.exit(0)

    rename_plan = generate_rename_plan(files_by_ext, prefix, include_extension)

    conflicts = check_conflicts(rename_plan)
    if conflicts:
        print("WARNING: Naming conflicts detected!")
        for conflict in conflicts:
            print(f"  - {conflict['new_path']}: {conflict['reason']}")
        print()
        response = input("Continue anyway? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Aborted.")
            sys.exit(1)

    execute_rename(rename_plan, dry_run=dry_run)

    report_file = os.path.join(target_dir, "rename_report.json")
    save_report(rename_plan, report_file)

    print("\nDone!")


if __name__ == "__main__":
    main()
