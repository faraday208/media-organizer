# media-organizer

> Medya dosyalarını AI dataset hazırlığı için düzenle: tip-bazlı sıralı
> rename, opsiyonel relocate (copy/move/output-dir), recursive scan,
> undo destekli.

[![tests](https://github.com/faraday208/media-organizer/actions/workflows/tests.yml/badge.svg)](https://github.com/faraday208/media-organizer/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/built%20with-uv-261230)](https://github.com/astral-sh/uv)

`media-dataset-prep` pipeline'ının **00. adımı**. Standalone kullanılabilir.

---

## 🎯 Ne yapıyor?

Karmaşık isimli dosyaları **tip-bazlı** ve **kronolojik** olarak yeniden adlandırır:

| Özellik | Açıklama |
|---|---|
| **Tip ayrımı** | Image / Video / Audio her biri kendi sequence'ında numaralandırılır |
| **Kronolojik sıra** | EXIF DateTimeOriginal (varsa) > mtime ile en eski → en yeni |
| **Format** | `{prefix}_{n}.{ext}` (örn. `Vacation_1.jpg`, `Vacation_1.mp4`) |
| **Recursive** | Alt klasörlerle iki mod: `flat` (tek output, hepsi) / `tree` (alt klasör yapısını koru) |
| **Sort kaynakları** | `exif`, `mtime`, `name` — rapor JSON'da hangisinin kullanıldığı kayıtlı |

### Desteklenen dosya tipleri

| Tip | Uzantılar |
|---|---|
| **Image** | jpg, jpeg, png, webp, gif, bmp, tiff, tif, heic, heif |
| **Video** | mp4, mov, avi, mkv, webm, m4v, mpg, mpeg, flv, wmv |
| **Audio** | mp3, wav, flac, m4a, ogg, aac, wma |

---

## 🚀 Kurulum

```bash
git clone https://github.com/faraday208/media-organizer
cd media-organizer
uv sync
```

EXIF tarihleri okumak için (opsiyonel ama önerilir):
```bash
uv sync --extra exif    # Pillow ekler
```

`media-dataset-prep` workspace'i altında: `make install` (tüm tool'lar tek venv'de).

---

## 🛠️ Kullanım — CLI

### In-place rename (dosya yerinde)

```bash
uv run python media_organizer.py /path/to/photos --prefix Vacation
```

### Copy mode (kaynak korunur, output-dir'e kopyalanır)

```bash
uv run python media_organizer.py /path/to/photos \
    --prefix Vacation \
    --mode copy \
    --output-dir /path/to/organized
```

### Move mode (dosyalar yer değiştirir)

```bash
uv run python media_organizer.py /path/to/photos \
    --prefix Vacation \
    --mode move \
    --output-dir /path/to/organized
```

### Recursive — alt klasörler dahil

```bash
# Flat: tüm alt klasörler tek output'ta birleşir, ortak sequence
uv run python media_organizer.py /path/to/photos \
    --recursive flat \
    --output-dir /path/to/flat_output

# Tree: alt klasör yapısı korunur, her alt klasör kendi sequence'ında
uv run python media_organizer.py /path/to/photos \
    --recursive tree \
    --output-dir /path/to/tree_output
```

### Dry-run (rapor üret, dosyalara dokunma)

```bash
uv run python media_organizer.py /path/to/photos --dry-run
```

### Geri al (undo)

```bash
uv run python media_organizer.py --undo /path/to/photos/rename_report.json

# Tree mode sonrası boş klasörleri temizle
uv run python media_organizer.py \
    --undo /path/to/output/rename_report.json \
    --cleanup-empty-dirs
```

---

## 📋 Operation modes — özet

| Mod | Komut | Etki | Undo |
|---|---|---|---|
| **In-place rename** | `--mode rename` (default) | Dosya yerinde | ✓ |
| **Copy** | `--mode copy --output-dir D` | Kaynakta dokunulmaz, D'ye kopya | ✓ (kopyaları sil) |
| **Move** | `--mode move --output-dir D` | Kaynaktan D'ye taşır | ✓ |
| **Recursive flat** | `--recursive flat --output-dir D` | Tüm alt klasörler D'de tek dizine | ✓ |
| **Recursive tree** | `--recursive tree --output-dir D` | Alt klasör yapısı korunur | ✓ + `--cleanup-empty-dirs` |
| **Dry-run** | `--dry-run` | Rapor üretilir, dosya dokunulmaz | – |
| **Undo** | `--undo REPORT` | rename_report.json'dan geri al | – |

---

## 🚩 Tüm CLI flag'leri

| Flag | Tip | Default | Açıklama |
|---|---|---|---|
| `<source_dir>` | path | – | Kaynak dizin (zorunlu, `--undo` hariç) |
| `--prefix NAME` | str | klasör adı | Yeni isim ön eki |
| `--mode {rename,copy,move}` | str | `rename` | İşlem modu |
| `--output-dir PATH` | str | – | copy/move için zorunlu |
| `--recursive {flat,tree}` | str | – (sadece üst seviye) | Alt klasör tarama modu |
| `--include-extension` | flag | False | İsme uzantıyı dahil et: `prefix_jpg_1.jpg` |
| `--dry-run` | flag | False | Plan üret, dosya dokunma |
| `--undo PATH` | str | – | rename_report.json'dan geri al |
| `--cleanup-empty-dirs` | flag | False | Undo sonrası boş klasörleri sil (tree mode) |

---

## ⚙️ Config

Tool standalone — config dosyası yok. Tüm parametreler CLI flag'leri üzerinden ayarlanır. EXIF okuma `pillow` opsiyonel dependency (`uv sync --extra exif`).

---

## 🔌 In-process (library) kullanım

```python
import media_organizer

# Standart akış
files = media_organizer.scan_directory("/path/to/photos", recursive_mode=None)
plan = media_organizer.generate_rename_plan(
    files, prefix="Vacation", include_extension=False, output_dir=None,
)

# Çakışma kontrolü (UI için)
conflicts = media_organizer.check_conflicts(plan)
if conflicts:
    print(f"⚠ {len(conflicts)} naming çakışması")

# Execute
media_organizer.execute_rename(plan, dry_run=False, mode="rename")
media_organizer.save_report(plan, "rename_report.json", mode="rename")

# Recursive tree mode (alt klasör yapısı korunur)
per_dir = media_organizer.scan_directory("/path", recursive_mode="tree")
plan = media_organizer.generate_tree_rename_plan(
    per_dir, source_root="/path", prefix=None, output_dir="/output",
)

# Undo
media_organizer.undo_from_report(
    "/path/rename_report.json",
    cleanup_empty_dirs=True,
)
```

`media-dataset-prep` meta UI bu yolla in-process kullanır.

---

## 📄 Rapor formatı

```jsonc
{
  "tool": "media-organizer",
  "timestamp": "2026-05-08T22:12:34.567",
  "mode": "rename",
  "total_files": 42,
  "pillow_available": true,
  "renames": [
    {
      "old_path": "/abs/.../IMG_3847.jpg",
      "new_path": "/abs/.../Vacation_1.jpg",
      "old_filename": "IMG_3847.jpg",
      "new_filename": "Vacation_1.jpg",
      "extension": ".jpg",
      "type": "image",
      "time_source": "exif",       // 'exif', 'mtime', or 'name'
      "subdir": "."                 // recursive tree için
    }
  ]
}
```

`renames[]` listesi `--undo` için kullanılır. `time_source` field'ı sıralama gerekçesini gösterir (UI'da preview tablosunda gösterilir).

---

## 🧪 Test

```bash
uv sync --group dev    # pytest + pillow
uv run pytest
```

33 test: scan, plan, execute, undo, cleanup, recursive flat/tree, EXIF.

---

## ⚠️ Limitations

- **Recursive flat + in-place yasak** — kaynak klasör destructive olur, validation engellenir
- Aynı timestamp'li dosyalar için sıralama deterministik değil (alfabetik fallback)
- EXIF DateTimeOriginal yoksa mtime'a düşer; mtime de güvenilir değilse alfabetik
- Undo sadece rapor JSON'dan çalışır — rapor silinirse manuel rename gerek
- `mode=copy + undo` kopyalanan dosyaları siler (kaynakta dokunulmaz); `mode=move + undo` shutil.move ile geri taşır
- HEIC/HEIF format desteği için `pillow-heif` ekstra (varsayılan değil)

---

## 🏷️ Sürüm

**v0.5.1** — `tool` field'ı `save_report`'a eklendi (undo validation için).
`.gitignore` `*_report.json` suffix'ine güncellendi (conventions §uyumlu).

**v0.5.0** — recursive flat/tree modları + `--cleanup-empty-dirs` undo flag.
33 unit test (scan, plan, undo, cleanup, CLI, EXIF).

Önceki: v0.4.x (in-place rename + copy/move + undo, recursive yok).

---

## 📜 Lisans

[MIT](LICENSE)
