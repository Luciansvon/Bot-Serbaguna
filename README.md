# B.I.M.A Core

**Bima Intelligent Memory & Assistant Core** — Personal AI assistant system dengan memori jangka panjang dan arsitektur modular berbasis CrewAI.

## 📋 Overview

BIMA Core adalah sistem AI personal yang dirancang untuk:
- Menyimpan dan mengingat konteks percakapan jangka panjang
- Mengelola tugas-tugas otomatis (backup cloud, organisasi file, dll)
- Mendukung plugin kustom untuk ekstensi fungsionalitas
- Terintegrasi dengan GitHub untuk backup otomatis

## 🏗️ Arsitektur

```
BIMA_CORE/
├── main.py                 # Entry point (Discord bot)
├── t1_manager.py           # Manager agent dengan memory tools
├── mcp_server.py           # MCP server configuration
├── plugin_loader.py        # Hot-reload plugin system
├── memory_engine.py        # SQLite-based memory management
├── cloud_backup.py         # Auto Git sync ke private repo
├── file_organizer.py       # Smart file organization
└── tools/plugins/          # Custom plugin directory
```

## 🔧 Komponen Utama

### 1. Memory Engine (`memory_engine.py`)
- **Storage**: SQLite database (`memory.db`)
- **Fitur**:
  - Session tracking (histori percakapan)
  - Fact storage (fakta jangka panjang tentang user)
  - Auto-migrasi dari JSON ke SQLite
- **API**:
  - `add_session(perintah, hasil)` - Catat sesi baru
  - `add_fact(key, value)` - Simpan fakta penting
  - `get_full_context()` - Ambil semua konteks
  - `get_recent_context(n)` - Ambil N sesi terakhir

### 2. Manager Agent (`t1_manager.py`)
CrewAI Agent dengan custom tools:
- **Memory Read Tool** - Baca konteks memori
- **Memory Write Tool** - Simpan fakta baru
- **Recent History Tool** - Akses histori percakapan
- **Cost Optimizer Tool** - Estimasi token & rekomendasi model

### 3. Plugin System (`plugin_loader.py`)
Hot-reload plugin dari folder `tools/plugins/`:
```python
# Contoh plugin: tools/plugins/contoh_plugin.py
from crewai.tools import BaseTool

class MyTool(BaseTool):
    name: str = "my_custom_tool"
    description: str = "Tool kustom saya"
    
    def _run(self, input_str: str) -> str:
        return f"Hasil: {input_str}"

def create_tool():
    return MyTool()
```

### 4. Cloud Backup (`cloud_backup.py`)
Auto-commit ke private GitHub repo:
- Backup folder: `outputs/`, `memory/`, `Bima_Vault/`, `logs/`
- Exclude: `.env`, `bima_env/`, `__pycache__/`
- Jadwal: Cron job harian (02:00)

### 5. File Organizer (`file_organizer.py`)
Smart sorting folder `outputs/` berdasarkan tipe file:
- `.html` → `dashboards/`
- `.pdf`, `.docx` → `reports/`, `documents/`
- `.xlsx`, `.csv` → `spreadsheets/`
- `.png`, `.jpg`, `.svg` → `images/`, `graphics/`
- `.py` → `scripts/`

## 🚀 Setup & Instalasi

### Prerequisites
- Python 3.8+
- WSL Ubuntu (untuk Windows users)
- Git
- Discord Bot Token (jika menggunakan Discord integration)

### Langkah Instalasi

1. **Clone repository**
```bash
cd /home/bima_lucian/BIMA_CORE
```

2. **Setup virtual environment**
```bash
python3 -m venv bima_env
source bima_env/bin/activate
pip install -r requirements.txt
```

3. **Initialize Git backup (opsional)**
```bash
git init
git remote add origin https://github.com/USERNAME/bima-core-backup.git
git branch -M main
```

4. **Setup environment variables**
Buat file `.env`:
```env
DISCORD_TOKEN=your_discord_bot_token
MANAGER_LLM=gpt-4o-mini
GITHUB_TOKEN=your_github_token
```

5. **Jalankan aplikasi**
```bash
python main.py
```

## 📅 Automation (Cron Jobs)

Edit crontab: `crontab -e`

```bash
# Daily cloud backup at 02:00
0 2 * * * cd /home/bima_lucian/BIMA_CORE && python3 tools/cloud_backup.py

# Daily file organization at midnight
0 0 * * * cd /home/bima_lucian/BIMA_CORE && python3 tools/file_organizer.py
```

## 🛠️ Modules Reference

| Module | Deskripsi |
|--------|-----------|
| `t1_manager.py` | Manager agent dengan memory tools |
| `t2_visual.py` | Visual/data visualization tasks |
| `t3_arsip.py` | Archive management |
| `t4_admin.py` | Administrative tasks |
| `t5_intel.py` | Intelligence/research tasks |
| `t6_lifestyle.py` | Lifestyle & daily tasks |
| `t7_seniman.py` | Creative/artist tasks |
| `t7_html_templates.py` | HTML template generation |
| `t8_mekanik.py` | Mechanical/technical tasks |
| `t9_saham.py` | Stock market analysis |
| `rust_search.py` | Fast search utility (Rust-based) |

## 📝 Memory System

### Session Format
```json
{
  "timestamp": "2026-05-07T12:00:00",
  "perintah": "Buat dashboard penjualan",
  "hasil": "Dashboard berhasil dibuat di outputs/sales_dashboard.html"
}
```

### Facts Format
```json
{
  "proyek_aktif": {
    "value": "Kursi Japandi Modular untuk Pak Sugeng",
    "updated": "2026-05-02"
  }
}
```

## 🔐 Security Notes

- Jangan commit `.env` ke Git (sudah ada di `.gitignore`)
- Backup hanya folder non-sensitif
- Plugin loader skip file yang dimulai dengan `_`

## 📄 License

Private project — Bima Lucian © 2026

## 👤 Developer

**Bima Lucian**
- Email: bimachaktiadi.s@gmail.com
- Location: Pijar Sukma, Semarang
- Tech Stack: Python, CrewAI, SQLite, Discord.py

---

*Last updated: 2026-05-07*
