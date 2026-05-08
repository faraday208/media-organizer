"""CLI seviyesi davranış (subprocess) ve EXIF okuma testleri."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "media_organizer.py")


def _run(*args):
    """media_organizer.py'i subprocess olarak çağır, CompletedProcess döndür."""
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_cli_recursive_flat_without_output_dir_errors(tree_dir):
    """--recursive flat + --output-dir yokluğu → hata + non-zero rc."""
    result = _run(str(tree_dir), "--recursive", "flat")
    assert result.returncode != 0
    assert "--recursive flat requires --output-dir" in result.stdout + result.stderr


def test_cli_move_without_output_dir_errors(flat_dir):
    """--move + --output-dir yokluğu → hata."""
    result = _run(str(flat_dir), "--move")
    assert result.returncode != 0
    assert "--move requires --output-dir" in result.stdout + result.stderr


def test_cli_recursive_invalid_value_errors(tree_dir):
    """--recursive bilinmeyen değer → hata."""
    result = _run(str(tree_dir), "--recursive", "bogus")
    assert result.returncode != 0
    assert "--recursive requires 'flat' or 'tree'" in result.stdout + result.stderr


def test_cli_invalid_directory_errors(tmp_path):
    """Var olmayan dizin → hata."""
    result = _run(str(tmp_path / "no-such-dir"))
    assert result.returncode != 0


def test_cli_dry_run_succeeds_without_moving_media(flat_dir):
    """
    Dry-run medya dosyalarını hareket ettirmez. Not: rename_report.json
    dry-run'da da yazılır (bilinçli — undo için kayıt).
    """
    media_before = sorted(
        p.name for p in flat_dir.iterdir()
        if p.is_file() and p.name != "rename_report.json"
    )
    result = _run(str(flat_dir), "--prefix", "X", "--dry-run")
    assert result.returncode == 0
    media_after = sorted(
        p.name for p in flat_dir.iterdir()
        if p.is_file() and p.name != "rename_report.json"
    )
    assert media_before == media_after


def test_cli_recursive_tree_writes_per_subdir_report(tree_dir, tmp_path):
    """E2E: --recursive tree --output-dir → mirror, rapor merkezi."""
    out = tmp_path / "tree_out"
    result = _run(
        str(tree_dir), "--recursive", "tree", "--output-dir", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "rename_report.json").exists()
    assert (out / "sub_a").is_dir()
    assert (out / "sub_a" / "deep").is_dir()

    with open(out / "rename_report.json", encoding='utf-8') as f:
        report = json.load(f)
    # Tüm rename'larda 'subdir' alanı dolu (tree generator sayesinde)
    assert all('subdir' in r for r in report['renames'])


# ---------- EXIF (Pillow varsa) ----------

PIL_AVAILABLE = False
try:
    from PIL import Image  # noqa: F401
    from PIL.ExifTags import Base as _Exif  # noqa: F401
    PIL_AVAILABLE = True
except ImportError:
    pass


@pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow yüklü değil")
def test_exif_datetimeoriginal_takes_precedence_over_mtime(tmp_path):
    """EXIF DateTimeOriginal varsa mtime yerine o kullanılır."""
    from PIL import Image
    from media_organizer import get_file_sort_time

    img_path = tmp_path / "with_exif.jpg"
    # Manuel JPEG + EXIF DateTimeOriginal yaz
    img = Image.new('RGB', (10, 10), color='red')
    exif = img.getexif()
    exif[36867] = "2020:01:15 12:30:45"  # DateTimeOriginal
    img.save(img_path, exif=exif)

    # mtime'ı çok farklı bir zamana ayarla
    os.utime(img_path, (1700000000, 1700000000))  # 2023

    timestamp, source = get_file_sort_time(str(img_path), '.jpg')
    assert source == 'exif'
    # EXIF tarih (2020) mtime (2023)'ten farklı olmalı
    import datetime
    dt = datetime.datetime.fromtimestamp(timestamp)
    assert dt.year == 2020
    assert dt.month == 1
    assert dt.day == 15
