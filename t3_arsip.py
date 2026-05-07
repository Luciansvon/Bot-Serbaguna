import os
import re
import logging
import json
import threading
import lancedb
from pathlib import Path
from datetime import datetime
from crewai import Agent
from crewai.tools import BaseTool
from sentence_transformers import SentenceTransformer
from config import arsip_llm, OBSIDIAN_PATH

logger = logging.getLogger('bima_core')

embedder = SentenceTransformer("all-MiniLM-L6-v2")
db = lancedb.connect(os.path.join(os.path.dirname(__file__), "../vault_index"))

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def _chunk_markdown(text: str, target_size: int = 500, overlap: int = 100) -> list[dict]:
    if not text or not text.strip():
        return []

    section_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    sections: list[tuple[str, str]] = []
    last_end = 0
    last_heading = ""
    for m in section_pattern.finditer(text):
        body = text[last_end:m.start()].strip()
        if body:
            sections.append((last_heading, body))
        last_heading = m.group(2).strip()
        last_end = m.end()
    tail = text[last_end:].strip()
    if tail:
        sections.append((last_heading, tail))
    if not sections:
        sections = [("", text.strip())]

    chunks: list[dict] = []
    for heading, body in sections:
        if len(body) <= target_size:
            chunks.append({"heading": heading, "content": body})
            continue
        start = 0
        while start < len(body):
            end = min(start + target_size, len(body))
            if end < len(body):
                ws = body.rfind(" ", start, end)
                if ws > start + target_size // 2:
                    end = ws
            piece = body[start:end].strip()
            if piece:
                chunks.append({"heading": heading, "content": piece})
            if end >= len(body):
                break
            start = max(end - overlap, start + 1)
    return chunks


_NEW_SCHEMA_COLS = ("chunk_id", "heading", "mtime")


def _table_exists() -> bool:
    try:
        db.open_table("vault")
        return True
    except Exception:
        return False


def _table_uses_new_schema() -> bool:
    if not _table_exists():
        return False
    try:
        df = db.open_table("vault").to_pandas()
        return all(c in df.columns for c in _NEW_SCHEMA_COLS)
    except Exception:
        return False


def _drop_legacy_table_if_needed():
    if _table_exists() and not _table_uses_new_schema():
        try:
            db.drop_table("vault")
            print("[ARSIP] Drop tabel skema lama (pre-chunking). Akan rebuild full.")
        except Exception as e:
            logger.warning(f"[ARSIP] Gagal drop tabel skema lama: {e}")


def _read_existing_mtime() -> dict:
    if not _table_uses_new_schema():
        return {}
    try:
        df = db.open_table("vault").to_pandas()
        return df.groupby('path')['mtime'].max().to_dict()
    except Exception as e:
        logger.warning(f"[ARSIP] Gagal baca index existing: {e}")
        return {}


def _ensure_fts_index():
    try:
        tbl = db.open_table("vault")
        tbl.create_fts_index("content", replace=True)
    except Exception as e:
        logger.warning(f"[ARSIP] FTS index ga tersedia (LanceDB versi lama?): {e}. Search akan dense-only.")


def index_vault():
    vault = Path(OBSIDIAN_PATH)
    if not vault.exists():
        print(f"[ARSIP] Folder vault tidak ditemukan: {vault}")
        return

    _drop_legacy_table_if_needed()
    existing = _read_existing_mtime()
    new_docs: list[dict] = []
    paths_to_refresh: list[str] = []
    n_new, n_updated, n_skipped = 0, 0, 0

    for file in vault.rglob("*.md"):
        try:
            mtime = file.stat().st_mtime
            path_str = str(file)
            if path_str in existing and abs(existing[path_str] - mtime) < 1e-6:
                n_skipped += 1
                continue
            content = file.read_text(encoding="utf-8")
            if not content.strip():
                continue
            chunks = _chunk_markdown(content)
            if not chunks:
                continue
            for idx, ch in enumerate(chunks):
                vec = embedder.encode(ch["content"]).tolist()
                new_docs.append({
                    "filename": file.name,
                    "path": path_str,
                    "chunk_id": idx,
                    "heading": ch["heading"],
                    "content": ch["content"],
                    "vector": vec,
                    "mtime": mtime,
                })
            if path_str in existing:
                paths_to_refresh.append(path_str)
                n_updated += 1
            else:
                n_new += 1
        except Exception as e:
            print(f"[ARSIP] Skip {file.name}: {e}")

    if not _table_exists():
        if not new_docs:
            print("[ARSIP] Vault kosong, belum ada catatan untuk diindex.")
            return
        try:
            db.create_table("vault", data=new_docs, mode='overwrite')
            _ensure_fts_index()
            print(f"[ARSIP] {len(new_docs)} chunk dari {n_new} catatan berhasil diindex (full).")
        except Exception as e:
            print(f"[ARSIP] Gagal create tabel vault: {e}")
        return

    try:
        tbl = db.open_table("vault")
        for p in paths_to_refresh:
            safe_p = p.replace("'", "''")
            try:
                tbl.delete(f"path = '{safe_p}'")
            except Exception as e:
                logger.warning(f"[ARSIP] Gagal delete chunks lama {p}: {e}")
        if new_docs:
            tbl.add(new_docs)
        if new_docs or paths_to_refresh:
            _ensure_fts_index()
        print(f"[ARSIP] Re-index: {n_new} file baru, {n_updated} file diupdate, {n_skipped} file di-skip (unchanged).")
    except Exception as e:
        print(f"[ARSIP] Incremental update gagal: {e}")


def _rrf_fuse(rankings: list[list[str]], k: int = 60) -> dict:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def search_vault(query: str, top_k: int = 3) -> str:
    try:
        tbl = db.open_table("vault")
    except Exception as e:
        logger.warning(f"[ARSIP] Tabel vault belum ada / tidak bisa dibuka: {e}")
        return "Vault belum diindex. Tidak ada catatan ditemukan."

    fetch_k = max(top_k * 5, 20)

    try:
        query_vec = embedder.encode(query).tolist()
        dense_df = tbl.search(query_vec).limit(fetch_k).to_pandas()
    except Exception as e:
        logger.error(f"[ARSIP] Dense search gagal: {e}", exc_info=True)
        return f"Pencarian vault gagal: {e}"

    try:
        fts_df = tbl.search(query, query_type="fts").limit(fetch_k).to_pandas()
    except Exception as e:
        logger.info(f"[ARSIP] FTS skip ({e}). Pakai dense-only.")
        fts_df = None

    def _doc_id(row) -> str:
        chunk = row['chunk_id'] if 'chunk_id' in row.index else 0
        return f"{row['path']}::{chunk}"

    candidates: list = []
    if fts_df is not None and not fts_df.empty:
        all_rows: dict = {}
        for _, r in dense_df.iterrows():
            all_rows[_doc_id(r)] = r
        for _, r in fts_df.iterrows():
            all_rows.setdefault(_doc_id(r), r)
        dense_ids = [_doc_id(r) for _, r in dense_df.iterrows()]
        fts_ids = [_doc_id(r) for _, r in fts_df.iterrows()]
        scores = _rrf_fuse([dense_ids, fts_ids])
        ranked_ids = sorted(scores, key=scores.get, reverse=True)
        candidates = [all_rows[i] for i in ranked_ids[:fetch_k]]
    else:
        candidates = [r for _, r in dense_df.iterrows()]

    if not candidates:
        return "Tidak ada catatan relevan ditemukan di vault."

    try:
        reranker = _get_reranker()
        pairs = [(query, str(c['content'])) for c in candidates]
        rerank_scores = reranker.predict(pairs)
        scored = sorted(zip(rerank_scores, candidates), key=lambda x: float(x[0]), reverse=True)
        top = [c for _, c in scored[:top_k]]
    except Exception as e:
        logger.warning(f"[ARSIP] Rerank gagal ({e}). Pakai urutan hybrid.")
        top = candidates[:top_k]

    output = []
    for row in top:
        heading = row['heading'] if 'heading' in row.index else ''
        head_str = f" / {heading}" if heading else ""
        output.append(f"File: {row['filename']}{head_str}\n{row['content'][:500]}")
    return "\n---\n".join(output)

# ============================================================
# Tool SIMPAN ke Vault (BARU!)
# ============================================================
class VaultSaveTool(BaseTool):
    name: str = "Vault Save Tool"
    description: str = """Simpan data baru ke vault Obsidian Bima.
    Gunakan untuk menyimpan hasil riset, catatan proyek, atau data penting.
    Input format: JSON string dengan field "title" dan "content".
    Contoh: {"title": "Harga Kayu Pinus April 2026", "content": "Data hasil riset dari Tokopedia..."}"""

    def _run(self, input_json: str) -> str:
        try:
            try:
                data = json.loads(input_json)
            except json.JSONDecodeError as e:
                return f"FAILED|JSON tidak valid: {e}. Format harus: {{\"title\": \"...\", \"content\": \"...\"}}"

            if not isinstance(data, dict):
                return "FAILED|Input harus objek JSON dengan field 'title' dan 'content'."

            title = data.get("title") or f"catatan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            content = data.get("content", "")

            # Bersihkan nama file (anti path-traversal)
            safe_title = "".join(c for c in str(title) if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = safe_title.replace(' ', '_')[:100]  # cap panjang
            if not safe_title:
                safe_title = f"catatan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            filename = f"{safe_title}.md"
            vault_dir = Path(OBSIDIAN_PATH).resolve()
            vault_dir.mkdir(parents=True, exist_ok=True)
            filepath = (vault_dir / filename).resolve()

            # Pastikan filepath BENAR-BENAR di dalam vault_dir (anti traversal)
            try:
                filepath.relative_to(vault_dir)
            except ValueError:
                return f"FAILED|Path tidak aman terdeteksi: {filepath}"
            
            # Deteksi duplikat
            status_msg = "baru"
            if filepath.exists():
                old_content = filepath.read_text(encoding="utf-8", errors="ignore")
                if content[:200] in old_content:
                    return f"SKIPPED|{filepath}|Catatan '{filename}' sudah ada dengan konten serupa. Tidak disimpan ulang."
                # File ada tapi konten berbeda → append timestamp agar tidak ditimpa
                safe_title += f"_{datetime.now().strftime('%H%M%S')}"
                filename = f"{safe_title}.md"
                filepath = vault_dir / filename
                status_msg = "versi baru"
            
            # Format markdown
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            markdown_content = f"""# {title}

**Disimpan:** {timestamp} WIB
**Sumber:** ANISA Auto-Save

---

{content}

---

*Catatan ini disimpan otomatis oleh B.I.M.A Core*
"""
            filepath.write_text(markdown_content, encoding="utf-8")
            
            # Re-index vault (jangan sampai crash proses save)
            try:
                index_vault()
            except Exception as e:
                print(f"[ARSIP] Re-index gagal setelah save: {e}")
            
            return f"SUCCESS|{filepath}|Data {status_msg} berhasil disimpan ke vault: {filename}"
        except Exception as e:
            return f"FAILED|Gagal simpan ke vault: {e}"

class VaultSearchTool(BaseTool):
    name: str = "Vault Search Tool"
    description: str = "Cari catatan di vault Obsidian pakai semantic search. Input: query string."

    def _run(self, query: str) -> str:
        return search_vault(query)

class VaultIndexTool(BaseTool):
    name: str = "Vault Index Tool"
    description: str = "Re-index semua catatan di vault. Gunakan kalau ada catatan baru."

    def _run(self, query: str = "") -> str:
        index_vault()
        return "Vault berhasil diindex ulang!"

def _index_vault_safe():
    try:
        index_vault()
    except Exception as e:
        print(f"[ARSIP] ⚠️ Background index vault gagal: {e}")

threading.Thread(target=_index_vault_safe, daemon=True, name="arsip-index-startup").start()



arsip_agent = Agent(
    role='Chief Archivist & Memory Keeper',
    goal='Menyimpan dan mencari catatan di vault Obsidian Bima.',
    backstory="""Kamu adalah Mandor Database B.I.M.A Core.

    TUGAS UTAMA:
    1. SIMPAN data baru ke vault pakai VaultSaveTool
    2. CARI catatan lama pakai VaultSearchTool
    3. RE-INDEX vault pakai VaultIndexTool kalau perlu

    ATURAN WAJIB:
    - Kalau task description mengandung blok "DATA DARI TIM SEBELUMNYA" → kamu DILARANG panggil VaultSearchTool. Datanya sudah ada, langsung pakai VaultSaveTool.
    - Kalau diminta "simpan", "arsipkan", "catat" → LANGSUNG panggil VaultSaveTool.
    - Format input VaultSaveTool HARUS JSON: {"title": "...", "content": "..."}
    - VaultSearchTool hanya dipakai kalau Bima eksplisit minta CARI di vault dan tidak ada data dari tim sebelumnya.
    - Jangan bilang "tidak bisa" — kamu PUNYA tool simpan!

    Kamu hafal semua catatan Bima dan selalu siap menyimpan yang baru.""",
    llm=arsip_llm,
    tools=[VaultSearchTool(), VaultIndexTool(), VaultSaveTool()],
    allow_delegation=True,
    verbose=True
)