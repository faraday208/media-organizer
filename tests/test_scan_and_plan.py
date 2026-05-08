"""scan_directory ve generate_rename_plan / generate_tree_rename_plan testleri."""
import os

from media_organizer import (
    MEDIA_EXTENSIONS,
    generate_rename_plan,
    generate_tree_rename_plan,
    scan_directory,
)


# ---------- scan_directory ----------

def test_scan_default_finds_only_top_level(tree_dir):
    """Default scan (recursive_mode=None) sadece üst seviye dosyaları bulur."""
    result = scan_directory(str(tree_dir))
    paths = [p for items in result.values() for (p, _, _) in items]

    assert len(paths) == 3
    assert all(os.path.dirname(p) == str(tree_dir) for p in paths)


def test_scan_flat_recursive_pools_entire_tree(tree_dir):
    """Flat mod tüm tree'yi tek dict'e toplar; alt klasörler düzleşir."""
    result = scan_directory(str(tree_dir), recursive_mode='flat')
    paths = [p for items in result.values() for (p, _, _) in items]

    # 3 (root) + 2 (sub_a) + 3 (sub_b) + 2 (deep) = 10. Hidden .cache atlanmalı.
    assert len(paths) == 10
    assert not any('.cache' in p for p in paths)


def test_scan_tree_returns_per_directory_dicts(tree_dir):
    """Tree mod nested dict döner: dirpath → {ext: [...]}."""
    result = scan_directory(str(tree_dir), recursive_mode='tree')

    expected_dirs = {
        str(tree_dir),
        str(tree_dir / "sub_a"),
        str(tree_dir / "sub_b"),
        str(tree_dir / "sub_a" / "deep"),
    }
    assert set(result.keys()) == expected_dirs

    counts = {d: sum(len(v) for v in groups.values()) for d, groups in result.items()}
    assert counts[str(tree_dir)] == 3
    assert counts[str(tree_dir / "sub_a")] == 2
    assert counts[str(tree_dir / "sub_b")] == 3
    assert counts[str(tree_dir / "sub_a" / "deep")] == 2


def test_scan_filters_non_media_files(flat_dir):
    """Medya olmayan dosyalar (.txt) sonuca girmez."""
    result = scan_directory(str(flat_dir))
    all_files = [p for items in result.values() for (p, _, _) in items]
    assert not any(p.endswith('.txt') for p in all_files)
    # 5 jpg + 2 mp4 + 1 mp3 = 8 (notes.txt elenir)
    assert len(all_files) == 8


def test_scan_groups_by_extension(flat_dir):
    """Her ekstansiyon ayrı bucket'a düşer."""
    result = scan_directory(str(flat_dir))
    assert '.jpg' in result and len(result['.jpg']) == 5
    assert '.mp4' in result and len(result['.mp4']) == 2
    assert '.mp3' in result and len(result['.mp3']) == 1


# ---------- generate_rename_plan (top-level / flat) ----------

def test_plan_sorts_by_timestamp_not_filename(flat_dir):
    """Sıralama mtime'a göre, alfabetik değil."""
    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X", include_extension=False)

    jpg_plan = [p for p in plan if p['extension'] == '.jpg']
    jpg_plan.sort(key=lambda p: p['index'])
    # mtime sırası: z,b,a,m,c → index 1,2,3,4,5
    assert [p['old_filename'] for p in jpg_plan] == [
        "z.jpg", "b.jpg", "a.jpg", "m.jpg", "c.jpg",
    ]
    assert [p['new_filename'] for p in jpg_plan] == [
        "X_1.jpg", "X_2.jpg", "X_3.jpg", "X_4.jpg", "X_5.jpg",
    ]


def test_plan_each_extension_has_independent_sequence(flat_dir):
    """Her ekstansiyon ayrı 1-N sequence alır."""
    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X")

    by_ext = {}
    for item in plan:
        by_ext.setdefault(item['extension'], []).append(item['index'])
    for ext, indices in by_ext.items():
        assert sorted(indices) == list(range(1, len(indices) + 1)), \
            f"{ext} sequence not 1..N: {sorted(indices)}"


def test_plan_include_extension_in_filename(flat_dir):
    """--include-extension ile filename'de ext yer alır."""
    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X", include_extension=True)
    jpg_first = next(p for p in plan if p['extension'] == '.jpg' and p['index'] == 1)
    assert jpg_first['new_filename'] == "X_jpg_1.jpg"


def test_plan_output_dir_redirects_new_paths(flat_dir, tmp_path):
    """output_dir verilirse new_path orada olur, dirname farkı."""
    out = tmp_path / "out"
    files = scan_directory(str(flat_dir))
    plan = generate_rename_plan(files, prefix="X", output_dir=str(out))
    assert all(os.path.dirname(p['new_path']) == str(out) for p in plan)


# ---------- generate_tree_rename_plan ----------

def test_tree_plan_each_subdir_has_independent_sequence(tree_dir):
    """Tree mod her klasörde 1-N kendi başına başlar."""
    per_dir = scan_directory(str(tree_dir), recursive_mode='tree')
    plan = generate_tree_rename_plan(per_dir, source_root=str(tree_dir))

    by_subdir = {}
    for item in plan:
        by_subdir.setdefault(item['subdir'], []).append(item['index'])

    assert sorted(by_subdir['.']) == [1, 2, 3]
    assert sorted(by_subdir['sub_a']) == [1, 2]
    assert sorted(by_subdir['sub_b']) == [1, 2, 3]


def test_tree_plan_default_prefix_is_subdir_name(tree_dir):
    """prefix=None → her subdir kendi adını prefix olarak kullanır."""
    per_dir = scan_directory(str(tree_dir), recursive_mode='tree')
    plan = generate_tree_rename_plan(per_dir, source_root=str(tree_dir), prefix=None)

    sub_a_items = [p for p in plan if p['subdir'] == 'sub_a']
    assert all(p['new_filename'].startswith('sub_a_') for p in sub_a_items)

    sub_b_items = [p for p in plan if p['subdir'] == 'sub_b']
    assert all(p['new_filename'].startswith('sub_b_') for p in sub_b_items)

    # Root'ta source dir base name kullanılır
    root_items = [p for p in plan if p['subdir'] == '.']
    assert all(p['new_filename'].startswith('tree_') for p in root_items)


def test_tree_plan_explicit_prefix_overrides_per_subdir(tree_dir):
    """--prefix verildiğinde tüm subdir'lar aynı prefix'i kullanır."""
    per_dir = scan_directory(str(tree_dir), recursive_mode='tree')
    plan = generate_tree_rename_plan(
        per_dir, source_root=str(tree_dir), prefix="ALL",
    )
    assert all(p['new_filename'].startswith("ALL_") for p in plan)


def test_tree_plan_mirrors_to_output_dir(tree_dir, tmp_path):
    """output_dir verildiğinde tree yapı mirror'lanır."""
    out = tmp_path / "mirror"
    per_dir = scan_directory(str(tree_dir), recursive_mode='tree')
    plan = generate_tree_rename_plan(
        per_dir, source_root=str(tree_dir), output_dir=str(out),
    )

    sub_a_target = next(p['new_path'] for p in plan if p['subdir'] == 'sub_a')
    assert os.path.dirname(sub_a_target) == str(out / "sub_a")

    deep_target = next(
        p['new_path'] for p in plan if p['subdir'] == os.path.join('sub_a', 'deep')
    )
    assert os.path.dirname(deep_target) == str(out / "sub_a" / "deep")


def test_supported_extensions_cover_image_video_audio():
    """MEDIA_EXTENSIONS sözleşmesinin korunduğunu doğrula (regression guard)."""
    for ext in ('.jpg', '.png', '.heic', '.mp4', '.mov', '.mp3', '.flac'):
        assert ext in MEDIA_EXTENSIONS
