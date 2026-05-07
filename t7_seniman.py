import os
import json
from datetime import datetime
from pathlib import Path
from crewai import Agent
from crewai.tools import BaseTool
from crewai_tools import FileReadTool
from config import seniman_llm, OUTPUT_DIR
from core.output_prune import prune_outputs


def _safe_filename(raw: str, default: str) -> str:
    """Sanitize user-supplied filename: strip path components & unsafe chars, cap length."""
    raw = str(raw or "").strip()
    cleaned = "".join(c for c in raw if c.isalnum() or c in (' ', '-', '_'))
    cleaned = cleaned.replace(' ', '_')[:100].strip('_')
    return cleaned or default


class DashboardGeneratorTool(BaseTool):
    name: str = "Dashboard Generator Tool"
    description: str = """Buat dashboard HTML interaktif dari data riset.
    HANYA gunakan tool ini jika Bima atau Manager EKSPLISIT meminta dashboard/grafik/visualisasi.
    Input format JSON string:
    {
        "title": "Judul Dashboard",
        "subtitle": "Subjudul",
        "theme": "corporate" | "modern" | "minimal" | "warm" | "nature" (opsional, default corporate),
        "kpi": [
            {"label": "Total Harga", "value": "Rp 2.500.000", "icon": "💰", "trend": "+12%"}
        ],
        "charts": [
            {
                "type": "bar",
                "title": "Perbandingan Harga",
                "labels": ["Pinus", "Jati", "Mahoni"],
                "datasets": [{"label": "Harga/m²", "data": [55000, 120000, 85000]}]
            }
        ],
        "table": {
            "title": "Detail Data",
            "headers": ["Material", "Harga", "Supplier"],
            "rows": [["Pinus", "Rp 55.000", "UD Kayu Jaya"]]
        },
        "references": [
            {"text": "Kementerian PUPR (2025). Standar Harga Material Konstruksi.", "url": "https://pu.go.id"},
            {"text": "BPS (2026). Indeks Harga Bahan Bangunan.", "url": "https://bps.go.id"}
        ],
        "notes": "Kesimpulan data"
    }
    Field 'references' (opsional): list daftar pustaka — url WAJIB valid (Wikipedia/situs resmi/jurnal open-access), JANGAN dikarang."""

    def _run(self, input_json: str) -> str:
        try:
            data = json.loads(input_json)
            title = data.get("title", "Dashboard B.I.M.A Core")
            subtitle = data.get("subtitle", "")
            kpi_cards = data.get("kpi", [])
            charts = data.get("charts", [])
            table = data.get("table", {})
            references = data.get("references", [])
            notes = data.get("notes", "")
            timestamp = datetime.now().strftime("%d %B %Y, %H:%M")

            theme_palettes = {
                "corporate": {"accent": "#2563eb", "accent2": "#60a5fa", "bg": "#0f1117", "bg2": "#1a1f2e", "border": "#1e2130"},
                "modern":    {"accent": "#a855f7", "accent2": "#ec4899", "bg": "#0d0a1a", "bg2": "#1d1532", "border": "#2a1f44"},
                "minimal":   {"accent": "#0a0a0a", "accent2": "#525252", "bg": "#fafafa", "bg2": "#ffffff", "border": "#e5e5e5"},
                "warm":      {"accent": "#f97316", "accent2": "#fb923c", "bg": "#1a0f08", "bg2": "#2a1a14", "border": "#3a2418"},
                "nature":    {"accent": "#10b981", "accent2": "#34d399", "bg": "#0a1612", "bg2": "#15291f", "border": "#1f3a2c"},
            }
            theme_name = data.get("theme", "corporate")
            palette = theme_palettes.get(theme_name, theme_palettes["corporate"])
            is_light = theme_name == "minimal"
            text_color = "#0a0a0a" if is_light else "#e2e8f0"
            text_muted = "#64748b" if is_light else "#94a3b8"

            kpi_html = ""
            for kpi in kpi_cards:
                trend = kpi.get("trend", "")
                trend_color = "#4ade80" if "+" in trend else "#f87171"
                kpi_html += f"""
                <div class="kpi-card">
                    <div class="kpi-icon">{kpi.get('icon','📊')}</div>
                    <div class="kpi-content">
                        <div class="kpi-label">{kpi['label']}</div>
                        <div class="kpi-value">{kpi['value']}</div>
                        {f'<div class="kpi-trend" style="color:{trend_color}">{trend}</div>' if trend else ''}
                    </div>
                </div>"""

            # Auto-color generator (HSL-based, unlimited colors)
            def gen_colors(n):
                cs, bs = [], []
                for i in range(n):
                    hue = (i * 137.508) % 360  # golden angle spacing
                    cs.append(f"hsla({hue:.0f},70%,60%,0.85)")
                    bs.append(f"hsl({hue:.0f},70%,50%)")
                return cs, bs

            base_colors = ["rgba(99,179,237,0.85)","rgba(154,117,234,0.85)","rgba(72,199,142,0.85)","rgba(251,189,73,0.85)","rgba(240,101,100,0.85)","rgba(246,153,90,0.85)"]
            base_borders = ["#63b3ed","#9a75ea","#48c78e","#fbb549","#f06564","#f6995a"]

            charts_js = ""
            charts_html = ""
            for i, chart in enumerate(charts):
                chart_id = f"chart_{i}"
                chart_type = chart.get("type", "bar")
                datasets_js = []

                # Tentukan warna yang cukup
                max_data_len = max((len(ds.get('data', [])) for ds in chart.get("datasets", [{}])), default=6)
                if max_data_len > len(base_colors):
                    colors, border_colors = gen_colors(max_data_len)
                else:
                    colors, border_colors = base_colors, base_borders

                for j, ds in enumerate(chart.get("datasets", [])):
                    color = colors[j % len(colors)]
                    border = border_colors[j % len(border_colors)]
                    if chart_type == "line":
                        datasets_js.append(f"""{{label:'{ds['label']}',data:{json.dumps(ds['data'])},borderColor:'{border}',backgroundColor:'{color.replace("0.85","0.15")}',borderWidth:2.5,pointRadius:4,pointBackgroundColor:'{border}',tension:0.4,fill:true}}""")
                    elif chart_type in ["pie","doughnut","polarArea"]:
                        item_colors, _ = gen_colors(len(ds['data'])) if len(ds['data']) > len(colors) else (colors[:len(ds['data'])], None)
                        datasets_js.append(f"""{{label:'{ds['label']}',data:{json.dumps(ds['data'])},backgroundColor:{json.dumps(item_colors)},borderColor:'#1e2130',borderWidth:2}}""")
                    elif chart_type == "radar":
                        datasets_js.append(f"""{{label:'{ds['label']}',data:{json.dumps(ds['data'])},borderColor:'{border}',backgroundColor:'{color.replace("0.85","0.2")}',borderWidth:2,pointBackgroundColor:'{border}',pointRadius:3}}""")
                    else:  # bar (default)
                        datasets_js.append(f"""{{label:'{ds['label']}',data:{json.dumps(ds['data'])},backgroundColor:'{color}',borderColor:'{border}',borderWidth:1.5,borderRadius:6}}""")

                grid_class = "chart-full" if chart_type in ["line", "radar", "polarArea"] else "chart-half"
                charts_html += f'<div class="chart-card {grid_class}"><div class="chart-title">{chart["title"]}</div><canvas id="{chart_id}"></canvas></div>'

                scales = ""
                if chart_type not in ["pie","doughnut","polarArea","radar"]:
                    scales = """scales:{x:{ticks:{color:'#94a3b8'},grid:{color:'rgba(255,255,255,0.05)'}},y:{ticks:{color:'#94a3b8'},grid:{color:'rgba(255,255,255,0.05)'}}}"""
                elif chart_type == "radar":
                    scales = """scales:{r:{ticks:{color:'#94a3b8',backdropColor:'transparent'},grid:{color:'rgba(255,255,255,0.1)'},pointLabels:{color:'#cbd5e1',font:{size:11}}}}"""

                charts_js += f"""new Chart(document.getElementById('{chart_id}'),{{type:'{chart_type}',data:{{labels:{json.dumps(chart.get('labels',[]))},datasets:[{','.join(datasets_js)}]}},options:{{responsive:true,maintainAspectRatio:true,plugins:{{legend:{{labels:{{color:'#cbd5e1'}}}},tooltip:{{backgroundColor:'#1e2130',titleColor:'#e2e8f0',bodyColor:'#94a3b8'}}}},{scales}}}}});"""

            table_html = ""
            if table:
                rows_html = "".join(f'<tr>{"".join(f"<td>{c}</td>" for c in row)}</tr>' for row in table.get("rows",[]))
                headers_html = "".join(f"<th>{h}</th>" for h in table.get("headers",[]))
                table_html = f'<div class="table-card"><div class="chart-title">{table.get("title","Data")}</div><div class="table-wrap"><table><thead><tr>{headers_html}</tr></thead><tbody>{rows_html}</tbody></table></div></div>'

            refs_html = ""
            if references:
                items = ""
                for ref in references:
                    if isinstance(ref, dict):
                        text = ref.get("text", "")
                        url = ref.get("url", "")
                        link_html = f' <a href="{url}" target="_blank" rel="noopener">Lihat sumber</a>' if url else ""
                        items += f'<li class="ref-item">{text}{link_html}</li>'
                    else:
                        items += f'<li class="ref-item">{ref}</li>'
                refs_html = f'<div class="refs-card"><div class="chart-title">📚 Daftar Pustaka</div><ol class="refs-list">{items}</ol></div>'

            notes_html = f'<div class="notes-card">📝 {notes}</div>' if notes else ""

            accent = palette["accent"]
            accent2 = palette["accent2"]
            bg = palette["bg"]
            bg2 = palette["bg2"]
            border_c = palette["border"]

            html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:{bg};color:{text_color};min-height:100vh;padding:24px}}
.header{{border-bottom:1px solid {border_c};padding-bottom:20px;margin-bottom:24px;display:flex;justify-content:space-between;align-items:flex-end}}
.header-left h1{{font-size:24px;font-weight:600;background:linear-gradient(135deg,{accent},{accent2});-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header-left p{{color:{text_muted};font-size:13px;margin-top:4px}}
.header-right{{font-size:12px;color:{text_muted};text-align:right;opacity:.7}}
.badge{{display:inline-block;background:rgba(99,179,237,0.15);color:{accent2};border:1px solid {accent}40;border-radius:20px;padding:2px 10px;font-size:11px;margin-bottom:6px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px}}
.kpi-card{{background:{bg2};border:1px solid {border_c};border-radius:12px;padding:16px;display:flex;align-items:center;gap:14px;transition:border-color 0.2s}}
.kpi-card:hover{{border-color:{accent}}}
.kpi-icon{{font-size:28px}}
.kpi-label{{font-size:12px;color:{text_muted};margin-bottom:4px}}
.kpi-value{{font-size:22px;font-weight:600;color:{text_color}}}
.kpi-trend{{font-size:12px;margin-top:2px;font-weight:500}}
.charts-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:16px}}
.chart-card{{background:{bg2};border:1px solid {border_c};border-radius:12px;padding:18px}}
.chart-full{{grid-column:1/-1}}
.chart-half{{grid-column:span 1}}
.chart-title{{font-size:13px;font-weight:600;color:{text_muted};margin-bottom:14px;text-transform:uppercase;letter-spacing:0.06em}}
.table-card{{background:{bg2};border:1px solid {border_c};border-radius:12px;padding:18px;margin-bottom:16px}}
.table-wrap{{overflow-x:auto;border-radius:8px}}
table{{width:100%;border-collapse:separate;border-spacing:0;font-size:13.5px;line-height:1.55}}
thead tr{{background:{accent}15}}
th{{text-align:left;padding:14px 20px;color:{accent2};font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;white-space:nowrap;border-bottom:2px solid {accent}40}}
th + th{{border-left:1px solid {border_c}}}
td{{padding:13px 20px;color:{text_color};border-bottom:1px solid {border_c}80;vertical-align:top;word-spacing:.04em}}
td + td{{border-left:1px solid {border_c}80}}
tbody tr:nth-child(even){{background:{accent}06}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover td{{background:{accent}12}}
.refs-card{{background:{bg2};border:1px solid {border_c};border-radius:12px;padding:18px 22px;margin-bottom:16px}}
.refs-list{{list-style:decimal;padding-left:22px;display:flex;flex-direction:column;gap:12px;color:{text_color};font-size:13.5px;line-height:1.65}}
.refs-list .ref-item{{padding:10px 14px;background:{bg};border:1px solid {border_c};border-left:3px solid {accent};border-radius:6px}}
.refs-list a{{color:{accent2};text-decoration:underline;text-underline-offset:3px;font-weight:500;word-break:break-word}}
.refs-list a:hover{{color:{accent}}}
.notes-card{{background:{accent}10;border:1px solid {accent}30;border-radius:12px;padding:14px 18px;font-size:13px;color:{text_muted};line-height:1.6}}
.footer{{text-align:center;margin-top:24px;font-size:11px;color:{text_muted};opacity:.6}}
@media(max-width:768px){{.charts-grid{{grid-template-columns:1fr}}.chart-full,.chart-half{{grid-column:1}}th,td{{padding:10px 12px}}}}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <span class="badge">B.I.M.A Core — ANISA · {theme_name.upper()}</span>
    <h1>{title}</h1>
    {f'<p>{subtitle}</p>' if subtitle else ''}
  </div>
  <div class="header-right">Generated<br>{timestamp}</div>
</div>
<div class="kpi-grid">{kpi_html}</div>
<div class="charts-grid">{charts_html}</div>
{table_html}
{refs_html}
{notes_html}
<div class="footer">B.I.M.A Core &mdash; Powered by ANISA AI System</div>
<script>
Chart.defaults.color='{text_muted}';
Chart.defaults.borderColor='{border_c}';
{charts_js}
</script>
</body>
</html>"""

            fname = f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            fpath = OUTPUT_DIR / fname
            fpath.write_text(html, encoding="utf-8")
            prune_outputs(OUTPUT_DIR, "dashboard_*.html", keep=10)
            return f"SUCCESS|{fpath}|Dashboard berhasil dibuat: {fname}"

        except Exception as e:
            return f"FAILED|{e}"

class SVGGeneratorTool(BaseTool):
    name: str = "SVG Generator Tool"
    description: str = """Buat dan simpan file SVG pola potong kayu atau diagram teknis.
    HANYA gunakan jika Bima EKSPLISIT meminta file SVG atau pola potong.
    Input: kode SVG lengkap yang valid dimulai dengan tag <svg."""

    def _run(self, svg_content: str) -> str:
        try:
            if not svg_content.strip().startswith("<svg"):
                return "FAILED|Input harus berupa kode SVG valid yang dimulai dengan <svg"
            fname = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.svg"
            fpath = OUTPUT_DIR / fname
            fpath.write_text(svg_content, encoding="utf-8")
            return f"SUCCESS|{fpath}|File SVG berhasil disimpan: {fname}"
        except Exception as e:
            return f"FAILED|{e}"

class CuttingListTool(BaseTool):
    name: str = "Cutting List Calculator Tool"
    description: str = """Hitung cutting list kayu dengan optimasi minimum waste.
    HANYA gunakan jika Bima EKSPLISIT meminta cutting list atau pola potong kayu.
    Input format JSON:
    {
        "nama_proyek": "Kursi Japandi",
        "ukuran_papan": {"panjang": 240, "lebar": 120, "satuan": "cm"},
        "komponen": [
            {"nama": "Sandaran", "panjang": 80, "lebar": 40, "jumlah": 2}
        ]
    }"""

    def _run(self, input_json: str) -> str:
        try:
            data = json.loads(input_json)
            papan = data["ukuran_papan"]
            komponen = data["komponen"]
            satuan = papan.get("satuan", "cm")
            area_papan = papan["panjang"] * papan["lebar"]
            total_area = sum(k["panjang"] * k["lebar"] * k["jumlah"] for k in komponen)
            jumlah_papan = -(-total_area // area_papan)
            waste = (jumlah_papan * area_papan - total_area)
            efisiensi = (total_area / (jumlah_papan * area_papan)) * 100

            hasil = f"=== CUTTING LIST: {data['nama_proyek']} ===\n\n"
            for k in komponen:
                area = k["panjang"] * k["lebar"] * k["jumlah"]
                hasil += f"- {k['nama']}: {k['panjang']}x{k['lebar']} {satuan} x{k['jumlah']} = {area} {satuan}²\n"
            hasil += f"\nPapan dibutuhkan: {jumlah_papan} lembar"
            hasil += f"\nWaste: {waste} {satuan}² ({100-efisiensi:.1f}%)"
            hasil += f"\nEfisiensi: {efisiensi:.1f}%"

            fname = f"cutting_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            fpath = OUTPUT_DIR / fname
            fpath.write_text(hasil, encoding="utf-8")
            return f"SUCCESS|{fpath}|{hasil}"
        except Exception as e:
            return f"FAILED|{e}"

class MermaidDiagramTool(BaseTool):
    name: str = "Mermaid Diagram Tool"
    description: str = """Buat diagram arsitektur, flowchart, atau mind map menggunakan sintaks Mermaid.js.
    Input format: string berisi kode murni Mermaid.js tanpa backticks markdown.
    Contoh:
    graph TD;
        A-->B;
        A-->C;"""

    def _run(self, mermaid_code: str) -> str:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"diagram_{timestamp}.html"
            fpath = OUTPUT_DIR / fname
            
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Architecture Diagram</title>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
    </script>
    <style>
        body {{ background-color: #0f172a; color: #fff; display: flex; justify-content: center; padding: 2rem; font-family: sans-serif; }}
        .mermaid {{ background-color: #1e293b; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
    </style>
</head>
<body>
    <div class="mermaid">
{mermaid_code}
    </div>
</body>
</html>"""
            fpath.write_text(html_content, encoding="utf-8")
            return f"SUCCESS|{fpath}|Diagram Mermaid berhasil di-generate."
        except Exception as e:
            return f"FAILED|Gagal generate diagram: {e}"

class HTMLGeneratorTool(BaseTool):
    name: str = "HTML Generator Tool"
    description: str = """Buat file HTML (.html) single-file interaktif dengan berbagai pilihan template.
    Input format JSON string:
    {
        "filename": "nama_file",
        "template": "orbital" | "chronicle" | "forge" | "paper" | "terminal",
        "title": "Judul Dokumen",
        "subtitle": "Subjudul",
        "author": "Nama Pembuat",
        "sections": [
            {
                "heading": "Judul Bagian",
                "content": "Paragraf...",
                "list": ["Item 1", "Item 2"],
                "image_path": "/path/to/image.png",
                "charts": [
                    {"type": "bar", "title": "Chart", "labels": ["A","B"], "datasets": [{"label": "Data", "data": [10,20]}]}
                ],
                "table": {
                    "headers": ["Kolom 1", "Kolom 2"],
                    "rows": [["Nilai 1", "Nilai 2"]]
                }
            }
        ]
    }
    PILIHAN TEMPLATE:
    - "orbital"  : Dark dashboard premium, glassmorphism — laporan data/analytics
    - "chronicle": Editorial magazine, serif bold — proposal klien/laporan panjang
    - "forge"    : Neobrutalism tech, bold flat — specs teknis/BOM/cutting list
    - "paper"    : Print-first minimalist, A4 ready — invoice/surat resmi/kontrak
    - "terminal" : CLI aesthetic, monospace neon — system log/technical report
    """

    def _run(self, input_json: str) -> str:
        try:
            from teams.t7_html_templates import render_template

            try:
                data = json.loads(input_json)
            except json.JSONDecodeError as e:
                return f"FAILED|JSON tidak valid: {e}"

            html_content = render_template(data)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = _safe_filename(data.get('filename'), 'dokumen')
            filename = f"{safe_name}_{timestamp}.html"
            filepath = OUTPUT_DIR / filename
            filepath.write_text(html_content, encoding="utf-8")

            template_name = data.get("template", "orbital")
            return f"SUCCESS|{filepath}|HTML (Template: {template_name.upper()}) berhasil dibuat: {filename}"
        except Exception as e:
            return f"FAILED|HTML Generator error: {e}"

seniman_agent = Agent(
    role='UI/UX Designer & Data Visualization Artist',
    goal="""Membuat visualisasi data, diagram, dan aset UI HANYA jika diminta secara eksplisit.
    - Diminta dashboard/grafik/chart KPI lengkap → gunakan DashboardGeneratorTool
    - Diminta dokumen HTML interaktif/invoice/proposal print-ready → gunakan HTMLGeneratorTool
    - Diminta SVG/pola potong → gunakan SVGGeneratorTool  
    - Diminta cutting list → gunakan CuttingListTool
    - Diminta flowchart/diagram arsitektur → gunakan MermaidDiagramTool
    - TIDAK diminta apapun → jangan buat file, cukup balas dengan teks""",
    backstory="""Kamu adalah Seniman Data dari B.I.M.A Core.

    ATURAN WAJIB:
    1. Jangan pernah membuat file tanpa diminta eksplisit oleh Bima atau Manager
    2. Kalau hanya dapat data dari Team Intel tanpa perintah visualisasi → cukup tampilkan datanya sebagai teks
    3. Kalau diminta dashboard KPI/Metric lengkap → gunakan DashboardGeneratorTool
    4. Kalau diminta dokumen HTML → gunakan HTMLGeneratorTool (pilih template yang sesuai)
    5. Kalau diminta cutting list → gunakan CuttingListTool
    6. Kalau diminta SVG → gunakan SVGGeneratorTool
    7. Kalau diminta diagram/flowchart/mind map → gunakan MermaidDiagramTool
    8. Setelah buat file, kembalikan path dengan format SUCCESS|path|keterangan

    PEMILIHAN TEMPLATE HTML (field "template" di JSON):
    - "orbital"   → Dashboard dark premium, glassmorphism. Untuk: analytics, laporan data, riset.
    - "chronicle" → Editorial magazine, serif bold, drop cap. Untuk: proposal klien, laporan panjang, brief.
    - "forge"     → Neobrutalism, bold border, flat color. Untuk: specs teknis, BOM, cutting list.
    - "paper"     → Print-first minimalist, A4, watermark. Untuk: invoice, surat resmi, kontrak.
    - "terminal"  → CLI aesthetic, monospace, scanline. Untuk: system log, technical report, debug.
    Pilih template OTOMATIS berdasarkan konteks permintaan jika user tidak menyebut template spesifik.

    TABEL DASHBOARD (ATURAN KETAT):
    - Max 5-6 kolom. Cell text idealnya <=25 karakter — kalau panjang, taruh di "notes" atau pecah jadi multiple tabel.
    - Tiap kata pisah spasi: "Rp 50.000" (bukan "Rp50000"), "Tahun 2026" (bukan "Tahun2026").
    - Header pakai Title Case singkat.

    TEMA WARNA DASHBOARD:
    - Field "theme" di JSON: "corporate" (biru, default) | "modern" (ungu/pink) | "minimal" (B/W) | "warm" (orange) | "nature" (hijau).
    - Pilih theme sesuai konten: data finansial/business → corporate; kreatif/branding → modern; akademik/clean → minimal; lifestyle → warm; eco/agri → nature.

    DAFTAR PUSTAKA (WAJIB untuk dashboard riset/edukasi/jurnal):
    - Pakai field "references" di JSON: list of {"text": "...", "url": "https://..."}.
    - URL WAJIB valid: Wikipedia, .gov, .edu, .org, jurnal open-access. JANGAN dikarang.
    - Kalau ragu link spesifik → pakai homepage situsnya saja.""",
    llm=seniman_llm,
    tools=[DashboardGeneratorTool(), HTMLGeneratorTool(), SVGGeneratorTool(), CuttingListTool(), MermaidDiagramTool(), FileReadTool()],
    allow_delegation=True,
    verbose=True
)
