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
import shutil
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


def generate_rename_plan(files_by_ext, prefix, include_extension=False, output_dir=None):
    """
    Sort each file group by timestamp and assign sequential numbers.

    If `output_dir` is given, new_path lives there (copy/move mode).
    Otherwise new_path lives next to the source (in-place rename).
    """
    rename_plan = []

    for ext, file_list in files_by_ext.items():
        sorted_files = sorted(file_list, key=lambda x: x[1])

        for idx, (old_path, timestamp, source) in enumerate(sorted_files, 1):
            target_dir = output_dir if output_dir else os.path.dirname(old_path)

            if include_extension:
                ext_name = ext.lstrip('.')
                new_filename = f"{prefix}_{ext_name}_{idx}{ext}"
            else:
                new_filename = f"{prefix}_{idx}{ext}"

            new_path = os.path.join(target_dir, new_filename)

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


def execute_rename(rename_plan, dry_run=True, mode='rename'):
    """
    Apply (or simulate) the rename plan.

    mode:
      'rename' = in-place rename in source dir (os.rename)
      'copy'   = copy to output dir, sources untouched (shutil.copy2)
      'move'   = move to output dir, sources removed (shutil.move)
    """
    op_label = {
        'rename': 'RENAMING FILES',
        'copy':   'COPYING FILES',
        'move':   'MOVING FILES',
    }[mode]

    print("=" * 80)
    print("DRY RUN MODE - No files will be modified" if dry_run else op_label)
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
                    if mode == 'copy':
                        shutil.copy2(item['old_path'], item['new_path'])
                    elif mode == 'move':
                        shutil.move(item['old_path'], item['new_path'])
                    else:  # 'rename' (in-place)
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


def save_report(rename_plan, output_file="rename_report.json", mode='rename'):
    """Save rename plan to JSON file. `mode` is recorded so undo can reverse correctly."""
    report = {
        'timestamp': datetime.now().isoformat(),
        'mode': mode,
        'total_files': len(rename_plan),
        'pillow_available': PIL_AVAILABLE,
        'renames': rename_plan
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRename plan saved to: {output_file}")


def undo_from_report(report_path, dry_run=False):
    """
    Reverse the operation described in a rename_report.json.

    Behavior depends on the report's recorded mode:
      'rename' → os.rename(new_path, old_path)         (eski isme geri çevir)
      'copy'   → os.remove(new_path)                   (kopyayı sil; kaynak duruyor)
      'move'   → shutil.move(new_path, old_path)       (kaynağa geri taşı)

    Skipped (with warning) when:
      - new_path no longer exists
      - old_path is occupied (would overwrite, not safe)
    """
    if not os.path.exists(report_path):
        print(f"Error: Report not found: {report_path}")
        return 1

    with open(report_path, encoding='utf-8') as f:
        report = json.load(f)

    # v1.x raporlarında 'mode' yoktu — geriye uyumluluk için 'rename' varsay.
    mode = report.get('mode', 'rename')
    renames = report.get('renames', [])

    print("=" * 80)
    print("UNDO — reversing previous run")
    print("=" * 80)
    print(f"Report: {report_path}")
    print(f"Original mode: {mode}")
    print(f"Records: {len(renames)}")
    if dry_run:
        print("DRY RUN — no files will be modified")
    print("=" * 80)
    print()

    success = skipped = failed = 0

    for item in renames:
        old_path = item['old_path']
        new_path = item['new_path']
        old_name = os.path.basename(old_path)
        new_name = os.path.basename(new_path)

        # Hedef (yeni dosya) hâlâ var mı?
        if not os.path.exists(new_path):
            print(f"  ⊘ {new_name}  (artık yok — atlandı)")
            skipped += 1
            continue

        # Geri yazılacak yer (rename/move modlarında) zaten dolu mu?
        if mode in ('rename', 'move') and os.path.exists(old_path):
            print(f"  ⊘ {new_name} → {old_name}  (hedef dolu — atlandı, üzerine yazmıyoruz)")
            skipped += 1
            continue

        if dry_run:
            if mode == 'rename':
                print(f"  ← {new_name} → {old_name}  (in-place reverse)")
            elif mode == 'copy':
                print(f"  ✗ {new_name}  (kopya silinecek; kaynak {old_name} zaten yerinde)")
            elif mode == 'move':
                print(f"  ← {new_name} → {old_name}  (move back)")
            success += 1
            continue

        try:
            if mode == 'rename':
                os.rename(new_path, old_path)
                print(f"  ✓ {new_name} → {old_name}")
            elif mode == 'copy':
                os.remove(new_path)
                print(f"  ✓ {new_name} silindi (kaynak {old_name} zaten yerinde)")
            elif mode == 'move':
                shutil.move(new_path, old_path)
                print(f"  ✓ {new_name} → {old_name}")
            else:
                print(f"  ✗ {new_name}  (bilinmeyen mod: {mode})")
                failed += 1
                continue
            success += 1
        except Exception as e:
            print(f"  ✗ {new_name}  (Hata: {e})")
            failed += 1

    print()
    print("=" * 80)
    print(f"SUMMARY  Total: {len(renames)}  |  Restored: {success}  |  Skipped: {skipped}  |  Failed: {failed}")
    print("=" * 80)
    return 0 if failed == 0 else 2


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 media_renamer.py <directory> [OPTIONS]")
        print("       python3 media_renamer.py --undo <report.json> [--dry-run]")
        print("\nArguments:")
        print("  directory           : Directory containing media files to rename")
        print("\nOptions:")
        print("  --prefix <name>     : Prefix for renamed files (default: directory name)")
        print("  --include-extension : Include extension in filename (e.g., prefix_jpg_1.jpg)")
        print("  --output-dir <path> : Write to this directory; sources stay untouched (copy mode)")
        print("  --move              : With --output-dir: move instead of copy (sources removed)")
        print("  --undo <report>     : Reverse a previous run from its rename_report.json")
        print("  --dry-run           : Simulate without modifying any file")
        print("\nExamples:")
        print('  python3 media_renamer.py "/path/to/photos" --dry-run')
        print('  python3 media_renamer.py "/path/to/photos" --prefix "Vacation2024"')
        print('  python3 media_renamer.py "/path/to/photos" --output-dir "/path/organized"')
        print('  python3 media_renamer.py "/path/to/photos" --output-dir "/path/organized" --move')
        print('  python3 media_renamer.py --undo /path/to/photos/rename_report.json --dry-run')
        print('  python3 media_renamer.py --undo /path/to/photos/rename_report.json')
        sys.exit(1)

    # --undo modu: ilk arg --undo ise dizin değil rapor yolu kabul et
    if sys.argv[1] == '--undo':
        if len(sys.argv) < 3:
            print("Error: --undo requires a path to rename_report.json")
            sys.exit(1)
        report_path = sys.argv[2]
        dry_run = '--dry-run' in sys.argv[3:]
        sys.exit(undo_from_report(report_path, dry_run=dry_run))

    target_dir = sys.argv[1]
    prefix = None
    dry_run = False
    include_extension = False
    output_dir = None
    move = False
    undo_report = None

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--prefix' and i + 1 < len(sys.argv):
            prefix = sys.argv[i + 1]
            i += 2
        elif arg == '--output-dir' and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        elif arg == '--undo' and i + 1 < len(sys.argv):
            undo_report = sys.argv[i + 1]
            i += 2
        elif arg == '--dry-run':
            dry_run = True
            i += 1
        elif arg == '--include-extension':
            include_extension = True
            i += 1
        elif arg == '--move':
            move = True
            i += 1
        else:
            i += 1

    # --undo başka konumdan geldiyse (örn. 'rename_files.py /path --undo report.json'),
    # report yoluna sahip — dizin argümanı yok sayılır.
    if undo_report:
        sys.exit(undo_from_report(undo_report, dry_run=dry_run))

    if prefix is None:
        prefix = os.path.basename(os.path.abspath(target_dir))

    if not os.path.exists(target_dir):
        print(f"Error: Directory not found: {target_dir}")
        sys.exit(1)

    if not os.path.isdir(target_dir):
        print(f"Error: Not a directory: {target_dir}")
        sys.exit(1)

    if move and not output_dir:
        print("Error: --move requires --output-dir")
        sys.exit(1)

    # output_dir verildiyse: oluştur, abspath kıyasla, source ile aynıysa in-place'e indirge
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        if os.path.abspath(output_dir) == os.path.abspath(target_dir):
            print("Note: --output-dir matches input directory; falling back to in-place rename.")
            output_dir = None
            move = False

    if output_dir is None:
        mode = 'rename'
    else:
        mode = 'move' if move else 'copy'

    mode_label = {
        'rename': 'IN-PLACE RENAME',
        'copy':   f'COPY → {output_dir}',
        'move':   f'MOVE → {output_dir}',
    }[mode]

    print()
    print("=" * 80)
    print("MEDIA FILE RENAMER")
    print("=" * 80)
    print(f"Directory: {target_dir}")
    print(f"Prefix: {prefix}")
    print(f"Include extension: {'Yes' if include_extension else 'No'}")
    print(f"Operation: {mode_label}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()

    files_by_ext = scan_directory(target_dir)

    if not files_by_ext:
        print("No media files found!")
        sys.exit(0)

    rename_plan = generate_rename_plan(files_by_ext, prefix, include_extension, output_dir=output_dir)

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

    execute_rename(rename_plan, dry_run=dry_run, mode=mode)

    # Rapor: output_dir varsa oraya, yoksa kaynağa.
    report_dir = output_dir if output_dir else target_dir
    report_file = os.path.join(report_dir, "rename_report.json")
    save_report(rename_plan, report_file, mode=mode)

    print("\nDone!")


if __name__ == "__main__":
    main()
