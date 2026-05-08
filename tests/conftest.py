"""Paylaşılan pytest fixture'ları."""
import os
import sys
import time

import pytest

# Üst dizini path'e ekle (media_organizer modülü için)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _touch(path, mtime):
    """Dosyayı 1 baytlık placeholder ile yarat ve mtime'ını sabitle."""
    with open(path, 'wb') as f:
        f.write(b'\x00')
    os.utime(path, (mtime, mtime))


@pytest.fixture
def flat_dir(tmp_path):
    """
    Düz dizin: 5 jpg + 2 mp4 + 1 mp3, mtime'lar zamansal olarak karışık
    (filename alfabetik ≠ kronolojik). Sıralama testleri için ideal.
    """
    base = tmp_path / "flat"
    base.mkdir()
    base_time = time.time() - 86400  # 1 gün önce

    # jpg'ler — alfabetik (z,b,a,m,c) ama kronolojik (1,2,3,4,5)
    _touch(base / "z.jpg", base_time + 100)
    _touch(base / "b.jpg", base_time + 200)
    _touch(base / "a.jpg", base_time + 300)
    _touch(base / "m.jpg", base_time + 400)
    _touch(base / "c.jpg", base_time + 500)

    _touch(base / "vid_b.mp4", base_time + 50)
    _touch(base / "vid_a.mp4", base_time + 150)

    _touch(base / "audio.mp3", base_time + 75)

    # Medya olmayan dosya (filtre testi için)
    _touch(base / "notes.txt", base_time)

    return base


@pytest.fixture
def tree_dir(tmp_path):
    """
    İç içe dizin yapısı: root + 3 alt klasör + 1 derin alt klasör.
    Her klasörde 2-3 jpg.
    """
    base = tmp_path / "tree"
    base.mkdir()
    base_time = time.time() - 86400

    # root: 3 dosya
    _touch(base / "root1.jpg", base_time + 10)
    _touch(base / "root2.jpg", base_time + 20)
    _touch(base / "root3.jpg", base_time + 30)

    sub_a = base / "sub_a"
    sub_a.mkdir()
    _touch(sub_a / "a1.jpg", base_time + 40)
    _touch(sub_a / "a2.jpg", base_time + 50)

    sub_b = base / "sub_b"
    sub_b.mkdir()
    _touch(sub_b / "b1.jpg", base_time + 60)
    _touch(sub_b / "b2.jpg", base_time + 70)
    _touch(sub_b / "b3.jpg", base_time + 80)

    deep = sub_a / "deep"
    deep.mkdir()
    _touch(deep / "d1.jpg", base_time + 90)
    _touch(deep / "d2.jpg", base_time + 100)

    # Hidden dizin — recursive scan tarafından atlanmalı
    hidden = base / ".cache"
    hidden.mkdir()
    _touch(hidden / "secret.jpg", base_time + 200)

    return base
