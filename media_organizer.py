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


def _collect_media_files(directory, source_counts):
    """
    Bir dizindeki (üst seviye) medya dosyalarını topla.
    Returns: {ext: [(filepath, timestamp, source)]}
    `source_counts` defaultdict(int) — telemetri için yerinde güncellenir.
    """
    files_by_ext = defaultdict(list)
    try:
        entries = os.listdir(directory)
    except Exception as e:
        print(f"Error reading directory {directory}: {e}")
        return files_by_ext

    for filename in entries:
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue
        ext = Path(filename).suffix.lower()
        if ext not in MEDIA_EXTENSIONS:
            continue
        timestamp, source = get_file_sort_time(filepath, ext)
        if timestamp is None:
            continue
        files_by_ext[ext].append((filepath, timestamp, source))
        source_counts[source] += 1

    return files_by_ext


def scan_directory(directory, recursive_mode=None):
    """
    Medya dosyalarını tara.

    recursive_mode:
      None   → sadece üst seviye dizin (eski davranış)
      'flat' → tüm alt ağaç tek havuza, ext bazında gruplanmış
      'tree' → her alt klasör ayrı havuz: {dir_path: {ext: [...]}}
    """
    source_counts = defaultdict(int)

    print(f"Scanning directory: {directory}")
    if recursive_mode:
        print(f"Recursive mode: {recursive_mode}")
    print("=" * 80)

    if not PIL_AVAILABLE:
        print("Note: Pillow not installed — falling back to filesystem mtime for images.")
        print("      For accurate EXIF-based sorting, run:  pip install Pillow")
        print()

    if recursive_mode == 'tree':
        per_dir = {}
        media_count = 0
        all_exts = set()
        for dirpath, dirnames, _filenames in os.walk(directory, followlinks=False):
            # Hidden dizinleri atla (.git, .venv, vs.)
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            files_by_ext = _collect_media_files(dirpath, source_counts)
            if files_by_ext:
                per_dir[dirpath] = dict(files_by_ext)
                count = sum(len(v) for v in files_by_ext.values())
                media_count += count
                all_exts.update(files_by_ext.keys())
                rel = os.path.relpath(dirpath, directory)
                rel_label = '.' if rel == '.' else rel
                print(f"  [{rel_label}] {count} media files")

        print(f"\nFound {media_count} media files in {len(per_dir)} directories")
        if all_exts:
            print(f"File types: {', '.join(sorted(all_exts))}")
        if source_counts:
            breakdown = ', '.join(f"{c} via {s}" for s, c in sorted(source_counts.items()))
            print(f"Sort-time sources: {breakdown}")
        print()
        return per_dir

    files_by_ext = defaultdict(list)
    if recursive_mode == 'flat':
        for dirpath, dirnames, _filenames in os.walk(directory, followlinks=False):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for ext, items in _collect_media_files(dirpath, source_counts).items():
                files_by_ext[ext].extend(items)
    else:
        for ext, items in _collect_media_files(directory, source_counts).items():
            files_by_ext[ext].extend(items)

    media_count = sum(len(v) for v in files_by_ext.values())
    print(f"Found {media_count} media files")
    if files_by_ext:
        print(f"File types: {', '.join(sorted(files_by_ext.keys()))}")
    if source_counts:
        breakdown = ', '.join(f"{c} via {s}" for s, c in sorted(source_counts.items()))
        print(f"Sort-time sources: {breakdown}")
    print()

    return dict(files_by_ext)


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


def generate_tree_rename_plan(per_dir, source_root, prefix=None,
                              include_extension=False, output_dir=None):
    """
    Tree mod: her alt klasör için ayrı sequence üret.

    - prefix=None ise her dizin kendi base name'ini prefix olarak kullanır
      (root dizini için source_root base name).
    - prefix verildiyse hepsi aynı prefix'i kullanır (farklı dizinlerde
      collision yok çünkü hedef yollar farklı).
    - output_dir verildiyse: kaynak ağaç mirror'lanır; aksi halde in-place.
    """
    rename_plan = []

    for dirpath in sorted(per_dir.keys()):
        files_by_ext = per_dir[dirpath]
        rel = os.path.relpath(dirpath, source_root)

        if output_dir:
            target_dir = output_dir if rel == '.' else os.path.join(output_dir, rel)
        else:
            target_dir = dirpath

        if prefix is None:
            dir_prefix = (
                os.path.basename(os.path.abspath(source_root))
                if rel == '.' else os.path.basename(dirpath)
            )
        else:
            dir_prefix = prefix

        for ext, file_list in files_by_ext.items():
            sorted_files = sorted(file_list, key=lambda x: x[1])
            for idx, (old_path, timestamp, source) in enumerate(sorted_files, 1):
                if include_extension:
                    ext_name = ext.lstrip('.')
                    new_filename = f"{dir_prefix}_{ext_name}_{idx}{ext}"
                else:
                    new_filename = f"{dir_prefix}_{idx}{ext}"

                new_path = os.path.join(target_dir, new_filename)

                rename_plan.append({
                    'old_path': old_path,
                    'new_path': new_path,
                    'old_filename': os.path.basename(old_path),
                    'new_filename': new_filename,
                    'extension': ext,
                    'sort_time': datetime.fromtimestamp(timestamp).isoformat(),
                    'time_source': source,
                    'index': idx,
                    'subdir': rel,
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


def execute_rename(rename_plan, dry_run=True, mode='rename', progress_cb=None):
    """
    Apply (or simulate) the rename plan.

    mode:
      'rename' = in-place rename in source dir (os.rename)
      'copy'   = copy to output dir, sources untouched (shutil.copy2)
      'move'   = move to output dir, sources removed (shutil.move)

    progress_cb: opsiyonel Callable[[int, int, str], None] — (current, total, msg)
                 olarak çağrılır. UI'ı taşmamak için her TICK dosyada bir + son
                 dosyada tetiklenir.
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

    total = len(rename_plan)
    current = 0
    TICK = 25  # callback frequency; küçük dataset'te çoğu güncellemeyi yine de görürüz

    if progress_cb:
        progress_cb(0, total, "Başlatılıyor…")

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
                    # Hedef parent dizini garanti et (tree mirror, flat output)
                    parent = os.path.dirname(item['new_path'])
                    if parent:
                        os.makedirs(parent, exist_ok=True)
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

            current += 1
            if progress_cb and (current % TICK == 0 or current == total):
                progress_cb(current, total, f"{current}/{total} dosya")

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

    # Sonuç sayaçları — çağıran (UI/CLI) başarı/error gösterebilsin diye döndürülür.
    # Geriye dönük uyumlu: dönüşü yok sayan mevcut çağrılar etkilenmez.
    return {
        "success": success_count,
        "error": error_count,
        "total": len(rename_plan),
    }


REPORT_TOOL_NAME = 'media-organizer'


def save_report(rename_plan, output_file="rename_report.json", mode='rename'):
    """Save rename plan to JSON file. `mode` is recorded so undo can reverse correctly."""
    report = {
        'tool': REPORT_TOOL_NAME,
        'timestamp': datetime.now().isoformat(),
        'mode': mode,
        'total_files': len(rename_plan),
        'pillow_available': PIL_AVAILABLE,
        'renames': rename_plan
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRename plan saved to: {output_file}")


def _cleanup_empty_dirs(dirs, stop_at, dry_run=False):
    """
    Verilen dizin setini bottom-up dolaş, boş olanları rmdir et.
    `stop_at` ve onun ataları silinmez (raporun yaşadığı dizin korunur).
    """
    stop_at = os.path.abspath(stop_at)
    candidates = sorted({os.path.abspath(d) for d in dirs}, key=len, reverse=True)
    removed = 0

    for d in candidates:
        # stop_at veya üstüne çıkma
        if d == stop_at:
            continue
        try:
            common = os.path.commonpath([d, stop_at])
        except ValueError:
            continue
        if common != stop_at:
            continue

        # Boş mu?
        try:
            if os.listdir(d):
                continue
        except FileNotFoundError:
            continue
        except Exception:
            continue

        if dry_run:
            print(f"  ⌫ (boş klasör silinecek) {d}")
            removed += 1
            continue

        try:
            os.rmdir(d)
            print(f"  ⌫ boş klasör silindi: {d}")
            removed += 1
        except OSError:
            pass

    return removed


def undo_from_report(report_path, dry_run=False, cleanup_empty_dirs=False):
    """
    Reverse the operation described in a rename_report.json.

    Behavior depends on the report's recorded mode:
      'rename' → os.rename(new_path, old_path)         (eski isme geri çevir)
      'copy'   → os.remove(new_path)                   (kopyayı sil; kaynak duruyor)
      'move'   → shutil.move(new_path, old_path)       (kaynağa geri taşı)

    Skipped (with warning) when:
      - new_path no longer exists
      - old_path is occupied (would overwrite, not safe)

    cleanup_empty_dirs: copy/move modlarında, undo sonrası `new_path`
    yollarındaki üst dizinler boş kaldıysa silinir (tree mirror temizliği).
    Raporun yaşadığı dizin daima korunur.
    """
    if not os.path.exists(report_path):
        print(f"Error: Report not found: {report_path}")
        return 1

    with open(report_path, encoding='utf-8') as f:
        report = json.load(f)

    # Tool kontratı: yanlış tool'un raporunu kabul etme. Eski raporlarda
    # 'tool' field'ı yoktu (v0.5.0 öncesi) — uyar ve devam et (back-compat).
    report_tool = report.get('tool')
    if report_tool and report_tool != REPORT_TOOL_NAME:
        print(f"Error: Report tool mismatch: expected {REPORT_TOOL_NAME!r}, got {report_tool!r}")
        return 1
    if not report_tool:
        print(f"Warning: Report has no 'tool' field — assuming {REPORT_TOOL_NAME} (legacy report).")

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
    candidate_dirs = set()  # cleanup için: undo'lanan new_path'lerin üst dizinleri

    for item in renames:
        old_path = item['old_path']
        new_path = item['new_path']
        old_name = os.path.basename(old_path)
        new_name = os.path.basename(new_path)
        candidate_dirs.add(os.path.dirname(new_path))

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
            # rename/move geri çevirirken eski parent dizin yoksa yarat
            # (recursive flat mode'da source ağacı silinmiş olabilir)
            if mode in ('rename', 'move'):
                parent = os.path.dirname(old_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
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

    if cleanup_empty_dirs and mode in ('copy', 'move'):
        # Raporun bulunduğu dizinin altındaki boş kalan ataları temizle.
        # Stop_at = raporun parent'ı (rename_report.json orada — hep dolu).
        stop_at = os.path.dirname(os.path.abspath(report_path))
        # Tüm ata dizinlerini de aday olarak ekle (deepest-first cleanup için)
        all_candidates = set(candidate_dirs)
        for d in list(candidate_dirs):
            cur = os.path.abspath(d)
            stop = os.path.abspath(stop_at)
            while cur and cur != stop and cur != os.path.dirname(cur):
                all_candidates.add(cur)
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
        print()
        print("=" * 80)
        print("CLEANUP — boş klasörleri sil")
        print("=" * 80)
        removed = _cleanup_empty_dirs(all_candidates, stop_at=stop_at, dry_run=dry_run)
        print(f"Cleanup: {removed} boş klasör {'silinecek' if dry_run else 'silindi'}")

    return 0 if failed == 0 else 2


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 media_organizer.py <directory> [OPTIONS]")
        print("       python3 media_organizer.py --undo <report.json> [--dry-run]")
        print("\nArguments:")
        print("  directory             : Directory containing media files to rename")
        print("\nOptions:")
        print("  --prefix <name>       : Prefix for renamed files (default: directory name)")
        print("  --include-extension   : Include extension in filename (e.g., prefix_jpg_1.jpg)")
        print("  --output-dir <path>   : Write to this directory; sources stay untouched (copy mode)")
        print("  --move                : With --output-dir: move instead of copy (sources removed)")
        print("  --recursive {flat,tree} : Process subdirectories.")
        print("                          flat = all files into one sequence (requires --output-dir)")
        print("                          tree = rename within each subdir, structure preserved")
        print("  --undo <report>       : Reverse a previous run from its rename_report.json")
        print("  --cleanup-empty-dirs  : With --undo (copy/move): remove dirs left empty after undo")
        print("  --dry-run             : Simulate without modifying any file")
        print("\nExamples:")
        print('  python3 media_organizer.py "/path/to/photos" --dry-run')
        print('  python3 media_organizer.py "/path/to/photos" --prefix "Vacation2024"')
        print('  python3 media_organizer.py "/path/to/photos" --output-dir "/path/organized"')
        print('  python3 media_organizer.py "/path/to/photos" --recursive flat --output-dir "/path/flat"')
        print('  python3 media_organizer.py "/path/to/photos" --recursive tree --output-dir "/path/tree"')
        print('  python3 media_organizer.py --undo /path/to/photos/rename_report.json --dry-run')
        sys.exit(1)

    # --undo modu: ilk arg --undo ise dizin değil rapor yolu kabul et
    if sys.argv[1] == '--undo':
        if len(sys.argv) < 3:
            print("Error: --undo requires a path to rename_report.json")
            sys.exit(1)
        report_path = sys.argv[2]
        rest = sys.argv[3:]
        dry_run = '--dry-run' in rest
        cleanup = '--cleanup-empty-dirs' in rest
        sys.exit(undo_from_report(report_path, dry_run=dry_run, cleanup_empty_dirs=cleanup))

    target_dir = sys.argv[1]
    prefix = None
    dry_run = False
    include_extension = False
    output_dir = None
    move = False
    undo_report = None
    recursive_mode = None
    explicit_prefix = False
    cleanup_empty = False

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--prefix' and i + 1 < len(sys.argv):
            prefix = sys.argv[i + 1]
            explicit_prefix = True
            i += 2
        elif arg == '--output-dir' and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        elif arg == '--undo' and i + 1 < len(sys.argv):
            undo_report = sys.argv[i + 1]
            i += 2
        elif arg == '--recursive' and i + 1 < len(sys.argv):
            value = sys.argv[i + 1]
            if value not in ('flat', 'tree'):
                print(f"Error: --recursive requires 'flat' or 'tree', got: {value}")
                sys.exit(1)
            recursive_mode = value
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
        elif arg == '--cleanup-empty-dirs':
            cleanup_empty = True
            i += 1
        else:
            i += 1

    # --undo başka konumdan geldiyse (örn. 'rename_files.py /path --undo report.json'),
    # report yoluna sahip — dizin argümanı yok sayılır.
    if undo_report:
        sys.exit(undo_from_report(undo_report, dry_run=dry_run, cleanup_empty_dirs=cleanup_empty))

    if not os.path.exists(target_dir):
        print(f"Error: Directory not found: {target_dir}")
        sys.exit(1)

    if not os.path.isdir(target_dir):
        print(f"Error: Not a directory: {target_dir}")
        sys.exit(1)

    if move and not output_dir:
        print("Error: --move requires --output-dir")
        sys.exit(1)

    # Flat recursive in-place çalışırsa dosyalar alt klasörlerden üst klasöre
    # kayar — bu rename'in ötesinde bir relocation. Kaza riski yüksek;
    # zorunlu output-dir.
    if recursive_mode == 'flat' and not output_dir:
        print("Error: --recursive flat requires --output-dir")
        print("       (cross-folder relocation in source tree is destructive)")
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

    # Default prefix: top-level/flat'da target_dir base name; tree'de None
    # bırakılır → her subdir kendi adını kullanır.
    if prefix is None and recursive_mode != 'tree':
        prefix = os.path.basename(os.path.abspath(target_dir))

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
    print(f"Recursive: {recursive_mode or 'no (top-level only)'}")
    if recursive_mode == 'tree' and not explicit_prefix:
        print("Prefix: (per-subdirectory: each folder uses its own name)")
    else:
        print(f"Prefix: {prefix}")
    print(f"Include extension: {'Yes' if include_extension else 'No'}")
    print(f"Operation: {mode_label}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()

    scanned = scan_directory(target_dir, recursive_mode=recursive_mode)

    if not scanned:
        print("No media files found!")
        sys.exit(0)

    if recursive_mode == 'tree':
        rename_plan = generate_tree_rename_plan(
            scanned,
            source_root=target_dir,
            prefix=(prefix if explicit_prefix else None),
            include_extension=include_extension,
            output_dir=output_dir,
        )
    else:
        rename_plan = generate_rename_plan(
            scanned, prefix, include_extension, output_dir=output_dir,
        )

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
