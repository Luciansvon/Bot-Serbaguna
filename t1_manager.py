import os
from crewai import Agent
from crewai.tools import BaseTool
from memory.memory_engine import (
    add_session, add_fact, get_full_context, get_recent_context, get_all_facts
)
from config import manager_llm

# ============================================================
# Tools Memory
# ============================================================
class MemoryReadTool(BaseTool):
    name: str = "Memory Read Tool"
    description: str = "Ambil konteks memori jangka panjang: histori percakapan dengan Bima dan fakta-fakta yang sudah disimpan. Gunakan ini di awal setiap tugas untuk tahu konteks Bima."

    def _run(self, query: str = "") -> str:
        return get_full_context()

class MemoryWriteTool(BaseTool):
    name: str = "Memory Write Tool"
    description: str = """Simpan fakta penting tentang Bima ke memori jangka panjang.
    Format input: 'key|value'
    Contoh: 'proyek_aktif|Kursi Japandi Modular untuk Pak Sugeng'
    Contoh: 'lokasi_kerja|Pijar Sukma, Semarang'
    Contoh: 'model_kayu_favorit|Pinus & Jati'"""

    def _run(self, input: str) -> str:
        try:
            if "|" not in input:
                return "Format salah. Gunakan: 'key|value'"
            key, value = input.split("|", 1)
            add_fact(key.strip(), value.strip())
            return f"Fakta berhasil disimpan: {key.strip()} = {value.strip()}"
        except Exception as e:
            return f"Gagal simpan fakta: {e}"

class RecentHistoryTool(BaseTool):
    name: str = "Recent History Tool"
    description: str = "Ambil 10 percakapan terakhir dengan Bima. Berguna untuk melanjutkan konteks dari sesi sebelumnya."

    def _run(self, query: str = "") -> str:
        return get_recent_context(10)

class CostOptimizerTool(BaseTool):
    name: str = "Cost Optimizer Tool"
    description: str = """Estimasi biaya token dan rekomendasikan model LLM yang cocok untuk tugas sebelum menugaskan.
    Input format: 'tingkat_kesulitan|panjang_teks'
    Tingkat kesulitan: 'rendah' (chat biasa), 'sedang' (riset/analisis), 'tinggi' (coding/reasoning berat).
    Panjang teks: estimasi jumlah karakter perintah. Contoh input: 'tinggi|5000'"""

    def _run(self, query: str) -> str:
        try:
            parts = query.split("|", 1)
            diff = parts[0].strip().lower()
            length = int(parts[1].strip())
            
            tokens = length / 4
            
            if diff == 'tinggi' or tokens > 10000:
                model = "deepseek-v4-pro"
                cost_per_m = 1.10
            elif diff == 'sedang':
                model = "deepseek-v4-flash"
                cost_per_m = 0.28
            else:
                model = "gemini-3-flash-preview"
                cost_per_m = 0.15
                
            cost = (tokens / 1_000_000) * cost_per_m
            
            return f"📊 Estimasi Cost:\n- Tokens: ~{int(tokens)}\n- Model Ideal: {model}\n- Estimasi Biaya: ${cost:.6f}\nSARAN: Delegasikan ke agen yang memakai spesifikasi terdekat untuk efisiensi."
        except Exception as e:
            return f"Error hitung cost: {e}"

# ============================================================
# Manager Agent
# ============================================================
manager_agent = Agent(
    role='Chief Orchestrator & Task Manager',
    goal="""Menganalisis perintah Bima, mengambil konteks dari memori, memecah tugas menjadi langkah logis,
    mendelegasikan ke agen spesialis, dan menyimpan fakta penting ke memori untuk sesi berikutnya.""",
    backstory="""Kamu adalah Pusat Komando dari sistem AI B.I.M.A Core, asisten pribadi bernama ANISA yang rendah hati (humble) ✨.
    
    Karakteristikmu:
    - Analitis: Selalu membedah masalah secara logis dan mendalam 🧠.
    - Kritis: Tidak ragu memberikan masukan jika ada langkah yang kurang efisien atau berisiko bagi Bima.
    - Hangat: Menggunakan emoji untuk menjaga suasana tetap positif dan ramah.
    
    Kamu punya MEMORI JANGKA PANJANG - kamu ingat semua percakapan dan fakta tentang Bima dari sesi sebelumnya.
    
    Workflow wajib kamu:
    1. SELALU baca memori dulu di awal (MemoryReadTool) untuk tahu konteks Bima 📖.
    2. Analisis permintaan dan berikan saran kritis jika perlu sebelum eksekusi.
    3. Perkirakan biaya token (CostOptimizerTool) untuk efisiensi biaya Bima 💸.
    4. Buat rencana eksekusi dan delegasikan ke agen spesialis yang tepat.
    5. Kalau ada fakta penting baru, SIMPAN ke memori (MemoryWriteTool) 💾.

    Spesialis yang tersedia (delegasi):
    - Saham IDX & global, harga, analisis teknikal/fundamental, BUY/HOLD/SELL → delegasi ke `saham_agent` 📈

    Kamu TIDAK mengeksekusi kode atau mencari data sendiri - itu tugas agen spesialis.""",
    llm=manager_llm,
    tools=[MemoryReadTool(), MemoryWriteTool(), RecentHistoryTool(), CostOptimizerTool()],
    allow_delegation=True,
    verbose=True
)

# Fungsi helper dipanggil dari main.py setelah setiap sesi
def simpan_sesi(perintah: str, hasil: str):
    add_session(perintah, hasil)
