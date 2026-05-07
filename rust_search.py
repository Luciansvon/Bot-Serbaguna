"""
B.I.M.A Core — Rust Search Tool (CrewAI Plugin)
Wrapper Python untuk binary Rust `bima_search` yang sudah dikompilasi.
Bisa dipakai sebagai tool untuk Team Arsip atau Agent manapun.
"""
import subprocess
import json
from pathlib import Path
from crewai.tools import BaseTool

BIMA_SEARCH_BIN = Path(__file__).parent.parent / "bima_search"
SEARCH_INDEX_DIR = Path(__file__).parent.parent / "search_index"
SOURCE_DIR = Path(__file__).parent.parent

class RustSearchTool(BaseTool):
    name: str = "rust_search_tool"
    description: str = (
        "Pencarian cepat berbasis Rust (Tantivy) di seluruh file project B.I.M.A Core. "
        "Gunakan untuk mencari isi dokumen, kode, catatan, atau output berdasarkan kata kunci. "
        "Input: kata kunci pencarian. Output: daftar file yang cocok beserta snippetnya."
    )
    
    def _run(self, query: str) -> str:
        if not BIMA_SEARCH_BIN.exists():
            return "❌ Binary bima_search belum dikompilasi. Jalankan: cd tools/bima_search && cargo build --release"
        
        if not SEARCH_INDEX_DIR.exists():
            # Auto-index jika belum ada
            try:
                subprocess.run(
                    [str(BIMA_SEARCH_BIN), "index",
                     "--source", str(SOURCE_DIR),
                     "--index-dir", str(SEARCH_INDEX_DIR)],
                    capture_output=True, text=True, timeout=120
                )
            except Exception as e:
                return f"❌ Gagal membuat index: {e}"
        
        try:
            result = subprocess.run(
                [str(BIMA_SEARCH_BIN), "search",
                 "--query", query,
                 "--index-dir", str(SEARCH_INDEX_DIR),
                 "--format", "json",
                 "--limit", "10"],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                return f"❌ Search error: {result.stderr}"
            
            data = json.loads(result.stdout)
            
            # Format hasil yang mudah dibaca agen
            output = f"🔍 Ditemukan {data['total_results']} hasil untuk \"{data['query']}\" ({data['search_time_ms']}ms)\n\n"
            
            for i, r in enumerate(data['results'], 1):
                output += f"{i}. {r['filename']} (relevansi: {r['score']:.1f})\n"
                output += f"   Path: {r['filepath']}\n"
                output += f"   Isi: {r['snippet'][:200]}...\n\n"
            
            return output
            
        except subprocess.TimeoutExpired:
            return "❌ Pencarian timeout (>30s). Coba query lebih spesifik."
        except json.JSONDecodeError:
            return f"❌ Output tidak valid: {result.stdout[:200]}"
        except Exception as e:
            return f"❌ Error: {e}"


class RustReindexTool(BaseTool):
    name: str = "rust_reindex_tool"
    description: str = (
        "Re-index ulang seluruh file project untuk memperbarui pencarian Rust. "
        "Gunakan setelah ada file baru atau perubahan besar. Input: apapun."
    )
    
    def _run(self, input_str: str = "") -> str:
        if not BIMA_SEARCH_BIN.exists():
            return "❌ Binary bima_search belum dikompilasi."
        
        try:
            result = subprocess.run(
                [str(BIMA_SEARCH_BIN), "index",
                 "--source", str(SOURCE_DIR),
                 "--index-dir", str(SEARCH_INDEX_DIR)],
                capture_output=True, text=True, timeout=120
            )
            
            # Ambil stats
            stats_result = subprocess.run(
                [str(BIMA_SEARCH_BIN), "stats",
                 "--index-dir", str(SEARCH_INDEX_DIR)],
                capture_output=True, text=True, timeout=10
            )
            
            stats = json.loads(stats_result.stdout) if stats_result.returncode == 0 else {}
            
            return (
                f"✅ Re-index selesai!\n"
                f"   Total dokumen: {stats.get('total_docs', '?')}\n"
                f"   Ukuran index: {stats.get('index_size_kb', '?')} KB"
            )
        except Exception as e:
            return f"❌ Error saat re-index: {e}"


def create_tools():
    """Plugin loader hook — return list of tools"""
    return [RustSearchTool(), RustReindexTool()]
