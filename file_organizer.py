"""
B.I.M.A Core — Smart File Organizer
Otomatis merapikan folder outputs/ berdasarkan tipe dan tanggal.

Jalankan manual:  python file_organizer.py
Atau via cron:    crontab -e → 0 0 * * * cd /home/bima_lucian/BIMA_CORE && python3 tools/file_organizer.py
"""
import os, shutil, time
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"

# Mapping ekstensi ke kategori folder
CATEGORIES = {
    ".html": "dashboards",
    ".pdf": "reports",
    ".xlsx": "spreadsheets",
    ".docx": "documents",
    ".csv": "spreadsheets",
    ".svg": "graphics",
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".py": "scripts",
    ".txt": "notes",
}

# File yang TIDAK boleh dipindah
SKIP_FILES = {"pet_event.json"}

def organize():
    if not OUTPUT_DIR.exists():
        print("❌ Folder outputs/ tidak ditemukan!")
        return

    moved = 0
    skipped = 0

    for f in OUTPUT_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name in SKIP_FILES:
            skipped += 1
            continue

        ext = f.suffix.lower()
        category = CATEGORIES.get(ext, "others")

        # Ambil tanggal dari modification time
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        date_folder = mtime.strftime("%Y-%m-%d")

        # Buat struktur: outputs/2026-04-29/dashboards/
        dest_dir = OUTPUT_DIR / date_folder / category
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / f.name
        if dest_path.exists():
            # Tambah timestamp jika nama sudah ada
            stem = f.stem
            dest_path = dest_dir / f"{stem}_{int(time.time())}{ext}"

        shutil.move(str(f), str(dest_path))
        print(f"  📂 {f.name} → {date_folder}/{category}/")
        moved += 1

    print(f"\n✅ Selesai! {moved} file dirapikan, {skipped} file di-skip.")

if __name__ == "__main__":
    print("🧹 B.I.M.A Core — Smart File Organizer")
    print(f"   Target: {OUTPUT_DIR}\n")
    organize()
