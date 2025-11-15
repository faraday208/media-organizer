#!/usr/bin/env python3
"""
Media File Renamer
Renames media files by type with sequential numbering
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict


# Supported media file extensions
MEDIA_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.raw',
    # Videos
    '.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpeg', '.mpg',
    # Audio
    '.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg', '.wma', '.opus'
}


def get_file_creation_time(filepath):
    """
    Get file creation time

    Returns:
        timestamp or None if error
    """
    try:
        stat_info = os.stat(filepath)
        # Use ctime (creation time on Windows, metadata change time on Unix)
        # On some systems, use birthtime if available
        if hasattr(stat_info, 'st_birthtime'):
            return stat_info.st_birthtime
        else:
            return stat_info.st_ctime
    except Exception as e:
        print(f"Error getting creation time for {filepath}: {e}")
        return None


def scan_directory(directory):
    """
    Scan directory for media files and group by extension

    Returns:
        dict: extension -> list of (filepath, creation_time) tuples
    """
    files_by_ext = defaultdict(list)

    print(f"Scanning directory: {directory}")
    print("=" * 80)

    # Get all files in directory (non-recursive)
    try:
        all_files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    except Exception as e:
        print(f"Error reading directory: {e}")
        return {}

    media_count = 0

    for filename in all_files:
        filepath = os.path.join(directory, filename)
        ext = Path(filename).suffix.lower()

        # Check if it's a media file
        if ext in MEDIA_EXTENSIONS:
            creation_time = get_file_creation_time(filepath)
            if creation_time is not None:
                files_by_ext[ext].append((filepath, creation_time))
                media_count += 1

    print(f"Found {media_count} media files")
    print(f"File types: {', '.join(files_by_ext.keys())}")
    print()

    return files_by_ext


def generate_rename_plan(files_by_ext, prefix):
    """
    Generate rename plan: sort by creation time and assign sequential numbers

    Args:
        files_by_ext: dict of extension -> list of (filepath, creation_time)
        prefix: prefix for new filenames

    Returns:
        list of (old_path, new_path) tuples
    """
    rename_plan = []

    # Process each file type
    for ext, file_list in files_by_ext.items():
        # Sort by creation time
        sorted_files = sorted(file_list, key=lambda x: x[1])

        # Assign sequential numbers
        for idx, (old_path, creation_time) in enumerate(sorted_files, 1):
            directory = os.path.dirname(old_path)
            new_filename = f"{prefix}_{idx}{ext}"
            new_path = os.path.join(directory, new_filename)

            rename_plan.append({
                'old_path': old_path,
                'new_path': new_path,
                'old_filename': os.path.basename(old_path),
                'new_filename': new_filename,
                'extension': ext,
                'creation_time': datetime.fromtimestamp(creation_time).isoformat(),
                'index': idx
            })

    return rename_plan


def check_conflicts(rename_plan):
    """
    Check for naming conflicts in the rename plan

    Returns:
        list of conflicts (if any)
    """
    conflicts = []
    new_names = set()

    for item in rename_plan:
        new_path = item['new_path']

        # Check if new name already exists
        if os.path.exists(new_path):
            # Check if it's not one of the files being renamed
            if new_path not in [i['old_path'] for i in rename_plan]:
                conflicts.append({
                    'new_path': new_path,
                    'reason': 'File already exists'
                })

        # Check for duplicate new names in the plan
        if new_path in new_names:
            conflicts.append({
                'new_path': new_path,
                'reason': 'Duplicate name in rename plan'
            })

        new_names.add(new_path)

    return conflicts


def execute_rename(rename_plan, dry_run=True):
    """
    Execute the rename plan

    Args:
        rename_plan: list of rename operations
        dry_run: if True, only simulate (don't actually rename)
    """
    print("=" * 80)
    if dry_run:
        print("DRY RUN MODE - No files will be renamed")
    else:
        print("RENAMING FILES")
    print("=" * 80)
    print()

    success_count = 0
    error_count = 0

    # Group by extension for display
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

    # Summary
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
    """Save rename plan to JSON file"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_files': len(rename_plan),
        'renames': rename_plan
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRename plan saved to: {output_file}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 rename_files.py <directory> [--prefix <name>] [--dry-run]")
        print("\nArguments:")
        print("  directory    : Directory containing media files to rename")
        print("  --prefix     : Prefix for renamed files (default: directory name)")
        print("  --dry-run    : Simulate rename without actually changing files")
        print("\nExample:")
        print('  python3 rename_files.py "/path/to/photos" --dry-run')
        print('  python3 rename_files.py "/path/to/photos" --prefix "Vacation2024"')
        sys.exit(1)

    # Parse arguments
    target_dir = sys.argv[1]
    prefix = None
    dry_run = False

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--prefix' and i + 1 < len(sys.argv):
            prefix = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--dry-run':
            dry_run = True
            i += 1
        else:
            i += 1

    # Default prefix: directory name
    if prefix is None:
        prefix = os.path.basename(os.path.abspath(target_dir))

    # Validate directory
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
    print(f"Mode: {'DRY RUN' if dry_run else 'RENAME'}")
    print()

    # Scan directory
    files_by_ext = scan_directory(target_dir)

    if not files_by_ext:
        print("No media files found!")
        sys.exit(0)

    # Generate rename plan
    rename_plan = generate_rename_plan(files_by_ext, prefix)

    # Check for conflicts
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

    # Execute rename
    execute_rename(rename_plan, dry_run=dry_run)

    # Save report
    report_file = os.path.join(target_dir, "rename_report.json")
    save_report(rename_plan, report_file)

    print("\nDone!")


if __name__ == "__main__":
    main()
