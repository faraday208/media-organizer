"""undo_from_report, _cleanup_empty_dirs ve execute_rename round-trip testleri."""
import json
import os
import time

import pytest

from media_organizer import (
    _cleanup_empty_dirs,
    execute_rename,
    generate_rename_plan,
    generate_tree_rename_plan,
    save_report,
    scan_directory,
    undo_from_report,
)


def _run_forward(scan_result, prefix, *, mode, output_dir=None,
                 source_root=None, recursive_mode=None):
    """Yardımcı: plan üret, gerçekleştir, raporu kaydet, rapor yolunu döndür."""
    if recursive_mode == 'tree':
        plan = generate_tree_rename_plan(
            scan_result, source_root=source_root, prefix=prefix,
            output_dir=output_dir,
        )
    else:
        plan = generate_rename_plan(scan_result, prefix=prefix, output_dir=output_dir)
    execute_rename(plan, dry_run=False, mode=mode)
    report_dir = output_dir if output_dir else source_root
    report_path = os.path.join(report_dir, "rename_report.json")
    save_report(plan, report_path, mode=mode)
    return report_path


# ---------- forward execute ----------

def test_in_place_rename_preserves_file_count(flat_dir):
    """In-place rename: dosya sayısı değişmez, sadece isimler değişir."""
    before = sum(1 for _ in flat_dir.iterdir() if _.is_file())
    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X")
    execute_rename(plan, dry_run=False, mode='rename')
    after = sum(1 for _ in flat_dir.iterdir() if _.is_file())
    assert before == after


def test_copy_mode_preserves_source(flat_dir, tmp_path):
    """Copy mod: kaynak dokunulmaz, hedefte kopyalar oluşur."""
    out = tmp_path / "out"
    out.mkdir()
    source_files = sorted(p.name for p in flat_dir.iterdir())

    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X", output_dir=str(out))
    execute_rename(plan, dry_run=False, mode='copy')

    # Source aynen
    assert sorted(p.name for p in flat_dir.iterdir()) == source_files
    # Output dolu (8 medya dosyası kopyalandı)
    assert sum(1 for _ in out.iterdir() if _.is_file()) == 8


def test_dry_run_does_not_modify_files(flat_dir):
    """Dry-run hiçbir dosyaya dokunmaz."""
    snapshot = sorted(p.name for p in flat_dir.iterdir())
    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X")
    execute_rename(plan, dry_run=True, mode='rename')
    assert sorted(p.name for p in flat_dir.iterdir()) == snapshot


# ---------- undo round-trip ----------

def test_undo_in_place_restores_original_names(flat_dir):
    """In-place rename → undo → orijinal isimler geri."""
    original = sorted(p.name for p in flat_dir.iterdir() if p.is_file())

    files = scan_directory(str(flat_dir))
    report_path = _run_forward(
        files, prefix="X", mode='rename', source_root=str(flat_dir),
    )

    rc = undo_from_report(report_path, dry_run=False)
    assert rc == 0

    after_undo = sorted(p.name for p in flat_dir.iterdir() if p.is_file())
    # rename_report.json eklenmiş, ama orijinal medyalar yerinde olmalı
    assert set(original).issubset(set(after_undo))


def test_undo_copy_deletes_copies_keeps_source(flat_dir, tmp_path):
    """Copy → undo → output kopyaları silinir, kaynak dokunulmaz."""
    out = tmp_path / "out"
    out.mkdir()
    files = scan_directory(str(flat_dir))
    report_path = _run_forward(
        files, prefix="X", mode='copy',
        source_root=str(flat_dir), output_dir=str(out),
    )

    rc = undo_from_report(report_path, dry_run=False)
    assert rc == 0

    # Kaynak medya dosyaları yerinde
    src_media = [
        p for p in flat_dir.iterdir() if p.suffix.lower() in {'.jpg', '.mp4', '.mp3'}
    ]
    assert len(src_media) == 8

    # Output'ta sadece rename_report.json kaldı
    out_files = sorted(p.name for p in out.iterdir())
    assert out_files == ["rename_report.json"]


def test_undo_skips_when_target_missing(flat_dir, tmp_path):
    """Hedef silinmişse undo atlar — fail değil."""
    out = tmp_path / "out"
    out.mkdir()
    files = scan_directory(str(flat_dir))
    report_path = _run_forward(
        files, prefix="X", mode='copy',
        source_root=str(flat_dir), output_dir=str(out),
    )

    # Bir kopyayı manuel sil — undo kalanını silmeye devam etmeli
    deleted = next(p for p in out.iterdir() if p.suffix == '.jpg')
    deleted.unlink()

    rc = undo_from_report(report_path, dry_run=False)
    assert rc == 0


def test_undo_dry_run_does_not_execute(flat_dir):
    """Undo dry-run hiçbir dosya hareketi yapmaz."""
    files = scan_directory(str(flat_dir))
    report_path = _run_forward(
        files, prefix="X", mode='rename', source_root=str(flat_dir),
    )

    snapshot = sorted(p.name for p in flat_dir.iterdir())
    rc = undo_from_report(report_path, dry_run=True)
    assert rc == 0
    assert sorted(p.name for p in flat_dir.iterdir()) == snapshot


# ---------- cleanup_empty_dirs ----------

def test_cleanup_removes_empty_subdirs_bottom_up(tmp_path):
    """_cleanup_empty_dirs en derinden başlayarak rmdir eder."""
    root = tmp_path / "root"
    a = root / "a"
    b = a / "b"
    c = b / "c"
    c.mkdir(parents=True)

    removed = _cleanup_empty_dirs([str(c), str(b), str(a)], stop_at=str(root))
    assert removed == 3
    assert not c.exists() and not b.exists() and not a.exists()
    assert root.exists()  # stop_at korundu


def test_cleanup_does_not_remove_stop_at(tmp_path):
    """stop_at dizini kendisi silinmez."""
    root = tmp_path / "root"
    root.mkdir()
    removed = _cleanup_empty_dirs([str(root)], stop_at=str(root))
    assert removed == 0
    assert root.exists()


def test_cleanup_skips_non_empty_dirs(tmp_path):
    """İçinde dosya olan dizin silinmez."""
    root = tmp_path / "root"
    sub = root / "sub"
    sub.mkdir(parents=True)
    (sub / "marker.txt").write_text("hi")

    removed = _cleanup_empty_dirs([str(sub)], stop_at=str(root))
    assert removed == 0
    assert sub.exists()
    assert (sub / "marker.txt").exists()


def test_cleanup_will_not_escape_above_stop_at(tmp_path):
    """stop_at dışındaki dizinler dokunulmaz."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()

    removed = _cleanup_empty_dirs([str(outside)], stop_at=str(root))
    assert removed == 0
    assert outside.exists()


def test_recursive_tree_undo_with_cleanup_removes_mirror_dirs(tree_dir, tmp_path):
    """End-to-end: tree mirror copy → undo + cleanup → mirror dizinleri yok."""
    out = tmp_path / "mirror"
    out.mkdir()
    per_dir = scan_directory(str(tree_dir), recursive_mode='tree')
    report_path = _run_forward(
        per_dir, prefix=None, mode='copy',
        source_root=str(tree_dir), output_dir=str(out),
        recursive_mode='tree',
    )

    # Mirror oluştu mu?
    assert (out / "sub_a").exists()
    assert (out / "sub_a" / "deep").exists()

    rc = undo_from_report(report_path, dry_run=False, cleanup_empty_dirs=True)
    assert rc == 0

    # Mirror alt klasörleri temizlendi
    assert not (out / "sub_a").exists()
    assert not (out / "sub_b").exists()
    # Output root duruyor (rapor içinde)
    assert out.exists()
    assert (out / "rename_report.json").exists()
