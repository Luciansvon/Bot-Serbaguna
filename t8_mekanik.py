import os
import re
import sys
import subprocess
import tempfile
import traceback
from pathlib import Path
from crewai import Agent
from crewai.tools import BaseTool
from crewai_tools import FileReadTool
from config import mekanik_llm, OUTPUT_DIR, BASE_DIR

# Deteksi OS untuk Python path
if sys.platform == "win32":
    PYTHON_PATH = os.path.join(str(BASE_DIR), "bima_env", "Scripts", "python.exe")
else:
    PYTHON_PATH = os.path.join(str(BASE_DIR), "bima_env", "bin", "python3")

# Fallback jika venv spesifik tidak ditemukan
if not os.path.exists(PYTHON_PATH):
    PYTHON_PATH = sys.executable
    print(f"[MEKANIK] ⚠️ bima_env tidak ditemukan, fallback ke system Python: {PYTHON_PATH}")

class CodeExecutorTool(BaseTool):
    name: str = "Code Executor Tool"
    description: str = """Eksekusi kode Python dan kembalikan hasilnya.
    Jika error, kembalikan pesan error lengkap untuk dianalisis dan diperbaiki.
    Input: kode Python yang ingin dieksekusi."""

    def _run(self, code: str) -> str:
        try:
            # Tulis ke temp file
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py',
                dir=str(OUTPUT_DIR),
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(code)
                temp_path = f.name

            # Wrapper eksekusi aman (Sandboxing sederhana)
            safe_wrapper = f"""
import sys
try:
    import resource
    # Limit memori 256MB dan CPU Time 15 detik untuk mencegah hang/bomb
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
except ImportError:
    pass # Fallback jika bukan sistem Unix
with open(r"{temp_path}", "r", encoding="utf-8") as f:
    exec(f.read(), {{"__name__": "__main__"}})
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='_wrapper.py', dir=str(OUTPUT_DIR), delete=False, encoding='utf-8') as f:
                f.write(safe_wrapper)
                wrapper_path = f.name

            # Eksekusi dengan timeout 20 detik
            result = subprocess.run(
                [PYTHON_PATH, wrapper_path],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(OUTPUT_DIR)
            )

            # Hapus temp file
            os.unlink(temp_path)
            os.unlink(wrapper_path)

            if result.returncode == 0:
                output = result.stdout or "(Kode jalan sukses, tidak ada output)"
                return f"✅ SUKSES:\n{output}"
            else:
                return f"❌ ERROR (exit code {result.returncode}):\n{result.stderr}"

        except subprocess.TimeoutExpired:
            try:
                os.unlink(temp_path)
                os.unlink(wrapper_path)
            except:
                pass
            return "❌ TIMEOUT: Kode berjalan lebih dari 20 detik, dihentikan."
        except Exception as e:
            return f"❌ GAGAL EKSEKUSI: {e}\n{traceback.format_exc()}"

class AutoRetryTool(BaseTool):
    name: str = "Auto Retry Debug Tool"
    description: str = """Eksekusi kode Python dengan auto-retry otomatis hingga 5 kali jika error.
    Tool ini akan: eksekusi → baca error → perbaiki → eksekusi lagi sampai sukses.
    Input: kode Python yang ingin dieksekusi dan di-debug otomatis."""

    def _run(self, code: str) -> str:
        max_retry = 5
        current_code = code
        history = []

        for attempt in range(1, max_retry + 1):
            print(f"[MEKANIK] Percobaan {attempt}/{max_retry}...")

            # Tulis ke temp file
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py',
                dir=str(OUTPUT_DIR),
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(current_code)
                temp_path = f.name

            safe_wrapper = f"""
import sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
except ImportError:
    pass
with open(r"{temp_path}", "r", encoding="utf-8") as f:
    exec(f.read(), {{"__name__": "__main__"}})
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='_wrapper.py', dir=str(OUTPUT_DIR), delete=False, encoding='utf-8') as f:
                f.write(safe_wrapper)
                wrapper_path = f.name

            try:
                result = subprocess.run(
                    [PYTHON_PATH, wrapper_path],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    cwd=str(OUTPUT_DIR)
                )
                os.unlink(temp_path)
                os.unlink(wrapper_path)

                if result.returncode == 0:
                    output = result.stdout or "(Sukses tanpa output)"
                    return f"""✅ BERHASIL di percobaan {attempt}/{max_retry}!

Output:
{output}

Riwayat debug:
{chr(10).join(history) if history else 'Langsung sukses tanpa error!'}"""

                else:
                    error_msg = result.stderr
                    history.append(f"Percobaan {attempt}: {error_msg[:200]}")
                    print(f"[MEKANIK] Error: {error_msg[:200]}")

                    if attempt < max_retry:
                        # Auto-install dimatikan (mitigasi supply-chain risk dari prompt injection).
                        # Module hilang akan diserahkan ke LLM fix di bawah untuk refactor ke stdlib.
                        module_match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", error_msg)
                        if module_match:
                            pkg = module_match.group(1).split('.')[0]
                            history.append(f"Percobaan {attempt}: Module '{pkg}' tidak ada — minta LLM refactor ke stdlib.")

                        # Minta LLM perbaiki kode
                        import httpx, json
                        fix_prompt = f"""Kode Python ini error:

```python
{current_code}
```

Error message:
{error_msg}

Panduan perbaikan:
- Jika ImportError/ModuleNotFoundError → ganti dengan library standar atau tambahkan try/except
- Jika FileNotFoundError → periksa path, gunakan os.path.exists() untuk cek dulu
- Jika TypeError/ValueError → periksa tipe data dan konversi yang benar
- Jika IndexError/KeyError → tambahkan pengecekan boundary/key existence

Perbaiki kode tersebut.
KEMBALIKAN HANYA kode Python yang sudah diperbaiki, tanpa penjelasan, tanpa markdown backticks."""

                        try:
                            resp = httpx.post(
                                "https://openrouter.ai/api/v1/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
                                    "Content-Type": "application/json"
                                },
                                json={
                                    "model": "deepseek/deepseek-chat",
                                    "messages": [{"role": "user", "content": fix_prompt}],
                                    "max_tokens": 2000
                                },
                                timeout=30
                            )
                            fixed = resp.json()["choices"][0]["message"]["content"].strip()
                            # Bersihkan markdown kalau ada
                            if fixed.startswith("```"):
                                lines = fixed.split("\n")
                                fixed = "\n".join(lines[1:-1])
                            current_code = fixed
                            print(f"[MEKANIK] Kode diperbaiki, coba lagi...")
                        except Exception as e:
                            history.append(f"Gagal auto-fix: {e}")

            except subprocess.TimeoutExpired:
                try:
                    os.unlink(temp_path)
                    os.unlink(wrapper_path)
                except:
                    pass
                history.append(f"Percobaan {attempt}: TIMEOUT")
            except Exception as e:
                history.append(f"Percobaan {attempt}: {e}")

        return f"""❌ GAGAL setelah {max_retry} percobaan.

Riwayat error:
{chr(10).join(history)}

Kode terakhir yang dicoba:
{current_code}

Bima perlu cek manual ya! 🔧"""

class FileSaverTool(BaseTool):
    name: str = "File Saver Tool"
    description: str = """Simpan konten ke file di folder outputs.
    Input format: 'nama_file.ekstensi|konten file'
    Contoh: 'hasil.py|print("hello world")'"""

    def _run(self, input_str: str) -> str:
        try:
            if "|" not in input_str:
                return "Format salah. Gunakan: 'nama_file|konten'"
            filename, content = input_str.split("|", 1)
            filepath = OUTPUT_DIR / filename.strip()
            filepath.write_text(content.strip(), encoding="utf-8")
            return f"SUCCESS|{filepath}|File berhasil disimpan: {filename.strip()}"
        except Exception as e:
            return f"FAILED|{e}"

class GitAutomationTool(BaseTool):
    name: str = "Git Automation Tool"
    description: str = """Melakukan operasi Git pada repository (BIMA_CORE).
    Perintah yang didukung:
    - 'status' : melihat status file yang berubah
    - 'commit|pesan commit' : melakukan git add . dan git commit
    - 'push' : melakukan git push ke remote
    Contoh input: 'commit|Memperbaiki bug pada file utils.py' atau 'status'"""

    def _run(self, command_str: str) -> str:
        try:
            parts = command_str.split('|', 1)
            cmd = parts[0].strip().lower()
            
            if cmd == 'status':
                result = subprocess.run(["git", "status"], capture_output=True, text=True, cwd=str(BASE_DIR))
                return result.stdout or result.stderr
            elif cmd == 'commit':
                if len(parts) < 2:
                    return "Gagal: Pesan commit harus disertakan. Contoh: 'commit|Perbaiki bug'"
                msg = parts[1].strip()
                subprocess.run(["git", "add", "."], cwd=str(BASE_DIR))
                result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, cwd=str(BASE_DIR))
                return f"Commit berhasil:\n{result.stdout}"
            elif cmd == 'push':
                result = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=str(BASE_DIR))
                return f"Push berhasil:\n{result.stdout or result.stderr}"
            else:
                return "Perintah Git tidak dikenal. Gunakan 'status', 'commit|pesan', atau 'push'."
        except Exception as e:
            return f"Error eksekusi Git: {e}"

class SecurityScannerTool(BaseTool):
    name: str = "Security Scanner Tool"
    description: str = """Scan file Python untuk bug dan celah keamanan sebelum dijalankan.
    Input format: path lokal ke file .py
    Alat ini akan menjalankan 'flake8' dan 'bandit'."""

    def _run(self, filepath: str) -> str:
        try:
            if not os.path.exists(filepath):
                return f"File tidak ditemukan: {filepath}"
            
            output = []
            # Flake8 (Syntax/Style)
            f8 = subprocess.run([PYTHON_PATH, "-m", "flake8", filepath], capture_output=True, text=True)
            if f8.stdout:
                output.append(f"⚠️ Warning (Flake8):\n{f8.stdout[:500]}")
                
            # Bandit (Security)
            bnd = subprocess.run([PYTHON_PATH, "-m", "bandit", "-r", filepath], capture_output=True, text=True)
            if "No issues identified" in bnd.stdout:
                output.append("✅ Security (Bandit): Aman!")
            elif bnd.stdout:
                output.append(f"❌ Security Issue (Bandit):\n{bnd.stdout[:1000]}")
                
            if not output:
                return "✅ Kode bersih dari syntax error dan aman."
            return "\n\n".join(output)
        except Exception as e:
            return f"Error saat scanning (pastikan flake8 & bandit terinstall): {e}"

mekanik_agent = Agent(
    role='SRE & Auto-Healing Code Mechanic',
    goal='Mengeksekusi kode Python, membaca error log, memperbaiki bug secara otomatis dengan loop retry, memastikan kode berjalan sempurna, dan melakukan version control (Git).',
    backstory="""Kamu adalah Tukang Ledeng Terminal dari B.I.M.A Core.
    Kamu punya 5 senjata:
    1. CodeExecutorTool - untuk test run kode sekali
    2. AutoRetryTool - untuk auto-debug loop sampai 5x sampai sukses
    3. FileSaverTool - untuk simpan hasil kode yang sudah bersih
    4. GitAutomationTool - untuk commit & push kode otomatis
    5. SecurityScannerTool - untuk periksa kode sebelum dieksekusi agar tahan hack
    
    Workflow wajib kamu:
    1. Terima kode dari Team Seniman atau Bima
    2. (Opsional) Scan dulu dengan SecurityScannerTool jika kodenya berisiko
    3. Coba eksekusi dengan CodeExecutorTool
    4. Kalau error, langsung switch ke AutoRetryTool
    5. Kalau sukses, simpan kode final dengan FileSaverTool
    6. Laporkan hasil: apa yang error, berapa kali retry, dan hasil akhirnya
    7. JIKA diminta, kamu bisa otomatis 'commit' hasil kerjamu ke Git!
    
    Kamu TIDAK PERNAH menyerah sebelum 5x percobaan.""",
    llm=mekanik_llm,
    tools=[CodeExecutorTool(), AutoRetryTool(), FileSaverTool(), GitAutomationTool(), SecurityScannerTool(), FileReadTool()],
    allow_delegation=True,
    verbose=True
)
