import json
import base64
from pathlib import Path
from datetime import datetime

def generate_chart_js(chart, chart_id, palette, template_type):
    c_type = chart.get("type", "bar")
    c_title = chart.get("title", "")
    c_labels = json.dumps(chart.get("labels", []))
    c_datasets = chart.get("datasets", [])
    
    js_datasets = []
    for i, ds in enumerate(c_datasets):
        color = palette[i % len(palette)]
        bg_color = color + "80"
        
        # terminal template uses outline only mostly, orbital uses glow
        border_width = 2
        if template_type == 'terminal':
            bg_color = "transparent"
        elif template_type == 'forge':
            border_width = 3
            bg_color = color
            
        if c_type in ['pie', 'doughnut']:
            bg_color = [p+"80" for p in palette[:len(chart.get("labels",[]))]]
            color = palette[:len(chart.get("labels",[]))]
            if template_type == 'forge':
                bg_color = color
        
        js_datasets.append(f"""{{
            label: '{ds.get("label", "")}',
            data: {json.dumps(ds.get("data", []))},
            backgroundColor: {json.dumps(bg_color)},
            borderColor: {json.dumps(color)},
            borderWidth: {border_width}
        }}""")
    
    # Custom options based on template
    grid_color = "rgba(0,0,0,0.1)"
    text_color = "#333"
    if template_type in ['orbital', 'terminal']:
        grid_color = "rgba(255,255,255,0.1)"
        text_color = "#ccc"
    if template_type == 'terminal':
        text_color = "#0f0"
        grid_color = "rgba(0, 255, 0, 0.2)"
        
    script = f"""
    new Chart(document.getElementById('{chart_id}'), {{
        type: '{c_type}',
        data: {{ labels: {c_labels}, datasets: [{','.join(js_datasets)}] }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            color: '{text_color}',
            plugins: {{
                title: {{ display: {'true' if c_title else 'false'}, text: '{c_title}', color: '{text_color}' }},
                legend: {{ labels: {{ color: '{text_color}' }} }}
            }},
            scales: {{"pie":{{}},"doughnut":{{}}}}['{c_type}'] || {{
                x: {{ ticks: {{ color: '{text_color}' }}, grid: {{ color: '{grid_color}' }} }},
                y: {{ ticks: {{ color: '{text_color}' }}, grid: {{ color: '{grid_color}' }} }}
            }}
        }}
    }});
    """
    return script

def render_template(data: dict) -> str:
    template = data.get("template", "orbital").lower()
    title = data.get("title", "Dokumen HTML")
    subtitle = data.get("subtitle", "")
    author = data.get("author", "B.I.M.A Core")
    date_str = datetime.now().strftime('%d %B %Y')
    
    # Common variables
    chart_scripts = []
    chart_counter = 0
    sections_html = ""

    # CSS and Palette Logic
    if template == "chronicle":
        palette = ["#1f2937", "#4b5563", "#9ca3af", "#d1d5db", "#374151"]
        font_url = "https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Source+Sans+Pro:wght@400;600&display=swap"
        css = """
        :root { --bg: #fdfbf7; --text: #2d3748; --accent: #2b6cb0; --border: #e2e8f0; }
        body { background: var(--bg); color: var(--text); font-family: 'Source Sans Pro', sans-serif; line-height: 1.8; margin: 0; padding: 0; }
        .container { max-width: 900px; margin: 40px auto; background: #fff; padding: 60px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 6px solid #1a202c; }
        .header-section { text-align: left; margin-bottom: 3rem; border-bottom: 2px solid #1a202c; padding-bottom: 2rem; }
        .header-section h1 { font-family: 'Playfair Display', serif; font-size: 3.5rem; color: #1a202c; margin: 0 0 10px 0; line-height: 1.2; }
        .header-section p.subtitle { font-family: 'Playfair Display', serif; font-size: 1.5rem; font-style: italic; color: #4a5568; margin-bottom: 1rem; }
        .meta { text-transform: uppercase; letter-spacing: 1px; font-size: 0.85rem; color: #718096; }
        .card { margin-bottom: 3rem; }
        h2 { font-family: 'Playfair Display', serif; font-size: 2rem; color: #1a202c; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        p { margin-bottom: 1.5rem; font-size: 1.1rem; }
        .card > p:first-of-type::first-letter { font-family: 'Playfair Display', serif; font-size: 3.5rem; float: left; line-height: 1; margin-right: 12px; font-weight: bold; color: #1a202c; }
        table { width: 100%; border-collapse: collapse; margin: 2rem 0; font-size: 1rem; }
        th, td { border-bottom: 1px solid var(--border); padding: 12px 15px; text-align: left; }
        th { font-weight: 600; color: #1a202c; text-transform: uppercase; font-size: 0.9rem; letter-spacing: 0.5px; border-bottom: 2px solid #1a202c; }
        .chart-container { height: 400px; margin: 2rem 0; }
        .img-container img { max-width: 100%; border-radius: 4px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        ul { margin-bottom: 1.5rem; padding-left: 20px; }
        li { margin-bottom: 0.5rem; font-size: 1.1rem; }
        """
    elif template == "forge":
        palette = ["#000000", "#FF4500", "#FFD700", "#1E90FF", "#32CD32"]
        font_url = "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700&display=swap"
        css = """
        :root { --bg: #f0f0f0; --text: #000; --primary: #FFD700; --border: #000; }
        body { background: var(--bg); color: var(--text); font-family: 'Space Grotesk', sans-serif; line-height: 1.6; margin: 0; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header-section { background: var(--primary); border: 4px solid var(--border); box-shadow: 8px 8px 0px var(--border); padding: 40px; margin-bottom: 40px; }
        .header-section h1 { font-size: 3rem; text-transform: uppercase; margin: 0 0 10px 0; border-bottom: 4px solid var(--border); padding-bottom: 10px; }
        .header-section p.subtitle { font-size: 1.5rem; font-weight: bold; margin-bottom: 20px; }
        .meta { background: #fff; display: inline-block; padding: 5px 15px; border: 2px solid var(--border); font-weight: bold; }
        .card { background: #fff; border: 4px solid var(--border); box-shadow: 8px 8px 0px var(--border); padding: 30px; margin-bottom: 40px; transition: transform 0.2s; }
        .card:hover { transform: translate(-4px, -4px); box-shadow: 12px 12px 0px var(--border); }
        h2 { font-size: 2rem; text-transform: uppercase; background: #000; color: #fff; display: inline-block; padding: 5px 15px; margin-top: 0; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; border: 2px solid var(--border); }
        th, td { border: 2px solid var(--border); padding: 15px; text-align: left; }
        th { background: var(--primary); font-weight: bold; text-transform: uppercase; font-size: 1.1rem; }
        .chart-container { height: 400px; margin: 30px 0; border: 4px solid var(--border); padding: 20px; background: #fff; }
        .img-container img { max-width: 100%; border: 4px solid var(--border); }
        ul { list-style: none; padding-left: 0; }
        li { position: relative; padding-left: 30px; margin-bottom: 10px; font-weight: bold; }
        li::before { content: '■'; position: absolute; left: 0; color: #FF4500; }
        """
    elif template == "paper":
        palette = ["#000000", "#333333", "#666666", "#999999", "#CCCCCC"]
        font_url = "https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=Open+Sans:wght@400;600&display=swap"
        css = """
        :root { --bg: #e5e5e5; }
        body { background: var(--bg); color: #000; font-family: 'Open Sans', sans-serif; margin: 0; padding: 40px 20px; line-height: 1.5; }
        .container { max-width: 21cm; margin: 0 auto; background: #fff; padding: 2cm; box-shadow: 0 0 10px rgba(0,0,0,0.1); position: relative; }
        .watermark { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-45deg); font-size: 8rem; color: rgba(0,0,0,0.03); font-family: 'Merriweather', serif; font-weight: bold; white-space: nowrap; pointer-events: none; z-index: 0; }
        .header-section { display: flex; flex-direction: column; align-items: flex-start; border-bottom: 2px solid #000; padding-bottom: 20px; margin-bottom: 30px; position: relative; z-index: 1; }
        .header-section h1 { font-family: 'Merriweather', serif; font-size: 2.5rem; margin: 0; text-transform: uppercase; letter-spacing: 2px; }
        .header-section p.subtitle { font-size: 1.2rem; margin: 10px 0 0 0; color: #555; }
        .meta { margin-top: 20px; font-size: 0.9rem; color: #333; }
        .card { margin-bottom: 30px; position: relative; z-index: 1; }
        h2 { font-family: 'Merriweather', serif; font-size: 1.5rem; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 0; text-transform: uppercase; letter-spacing: 1px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.95rem; }
        th, td { border: 1px solid #000; padding: 10px; text-align: left; }
        th { background: #f5f5f5; font-weight: 600; }
        .chart-container { height: 350px; margin: 20px 0; }
        .img-container { text-align: center; }
        .img-container img { max-width: 100%; filter: grayscale(100%); border: 1px solid #000; }
        @media print {
            body { background: #fff; padding: 0; }
            .container { box-shadow: none; max-width: 100%; padding: 0; }
        }
        """
    elif template == "terminal":
        palette = ["#00ff00", "#00cc00", "#009900", "#006600", "#00ffcc"]
        font_url = "https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&display=swap"
        css = """
        :root { --bg: #0a0a0a; --text: #00ff00; --dim: #006600; }
        body { background: var(--bg); color: var(--text); font-family: 'Fira Code', monospace; margin: 0; padding: 20px; line-height: 1.4; }
        .container { max-width: 1200px; margin: 0 auto; border: 1px solid var(--dim); padding: 20px; position: relative; }
        .container::before { content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06)); background-size: 100% 2px, 3px 100%; pointer-events: none; z-index: 100; }
        .header-section { margin-bottom: 40px; border-bottom: 1px dashed var(--dim); padding-bottom: 20px; }
        .header-section h1 { font-size: 2rem; margin: 0; text-transform: uppercase; }
        .header-section h1::before { content: '> '; color: #fff; }
        .header-section p.subtitle { font-size: 1.2rem; color: var(--dim); margin: 10px 0 0 0; }
        .meta { margin-top: 15px; font-size: 0.9rem; opacity: 0.8; }
        .card { margin-bottom: 40px; }
        h2 { font-size: 1.5rem; margin-top: 0; border-bottom: 1px solid var(--dim); padding-bottom: 5px; }
        h2::before { content: '[ '; color: #fff; }
        h2::after { content: ' ]'; color: #fff; }
        p, li { text-shadow: 0 0 2px rgba(0,255,0,0.4); }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { border: 1px dashed var(--dim); padding: 10px; text-align: left; }
        th { color: #fff; }
        .chart-container { height: 350px; margin: 20px 0; border: 1px solid var(--dim); padding: 10px; }
        .img-container img { max-width: 100%; border: 1px solid var(--text); filter: sepia(100%) hue-rotate(80deg) saturate(400%); }
        ul { list-style-type: square; color: #fff; }
        li { color: var(--text); }
        """
    else: # orbital (default)
        palette = ["#0ea5e9", "#8b5cf6", "#ec4899", "#14b8a6", "#f59e0b"]
        font_url = "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap"
        css = """
        :root { --bg: #0f1117; --card-bg: rgba(26, 31, 46, 0.6); --text: #e2e8f0; --dim: #94a3b8; --border: rgba(255,255,255,0.1); --accent: #0ea5e9; }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; margin: 0; padding: 30px; line-height: 1.6; background-image: radial-gradient(circle at top right, rgba(14,165,233,0.1), transparent 40%), radial-gradient(circle at bottom left, rgba(139,92,246,0.1), transparent 40%); min-height: 100vh; }
        .container { max-width: 1100px; margin: 0 auto; }
        .header-section { margin-bottom: 40px; padding: 40px; background: var(--card-bg); border-radius: 20px; border: 1px solid var(--border); backdrop-filter: blur(12px); text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .header-section h1 { font-size: 3rem; margin: 0 0 10px 0; background: linear-gradient(135deg, #0ea5e9, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .header-section p.subtitle { font-size: 1.2rem; color: var(--dim); margin: 0 0 20px 0; }
        .meta { display: inline-block; padding: 8px 16px; background: rgba(255,255,255,0.05); border-radius: 20px; font-size: 0.9rem; color: var(--dim); }
        .card { background: var(--card-bg); border-radius: 20px; border: 1px solid var(--border); backdrop-filter: blur(12px); padding: 30px; margin-bottom: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
        h2 { font-size: 1.8rem; margin-top: 0; margin-bottom: 20px; color: #fff; display: flex; align-items: center; gap: 10px; }
        h2::before { content: ''; display: block; width: 12px; height: 12px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px var(--accent); }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; border-radius: 10px; overflow: hidden; }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: rgba(255,255,255,0.05); color: #fff; font-weight: 600; }
        tr:hover td { background: rgba(255,255,255,0.02); }
        .chart-container { height: 350px; margin: 20px 0; }
        .img-container img { max-width: 100%; border-radius: 12px; border: 1px solid var(--border); }
        ul { padding-left: 20px; }
        li { margin-bottom: 8px; color: var(--dim); }
        """

    # Build sections
    for sec in data.get("sections", []):
        sections_html += '<div class="card">'
        if sec.get("heading"):
            sections_html += f"<h2>{sec['heading']}</h2>"
        if sec.get("content"):
            sections_html += f"<p>{sec['content'].replace(chr(10), '<br>')}</p>"
        if sec.get("list"):
            sections_html += "<ul>"
            for item in sec["list"]:
                sections_html += f"<li>{item}</li>"
            sections_html += "</ul>"
            
        if sec.get("image_path"):
            img_path = Path(sec["image_path"])
            if img_path.exists():
                try:
                    ext = img_path.suffix.lower().replace('.', '')
                    if ext == 'jpg': ext = 'jpeg'
                    b64 = base64.b64encode(img_path.read_bytes()).decode('utf-8')
                    sections_html += f'<div class="img-container"><img src="data:image/{ext};base64,{b64}" alt="Image"></div>'
                except Exception:
                    pass
                    
        if sec.get("charts"):
            for chart in sec["charts"]:
                chart_id = f"chart_{chart_counter}"
                sections_html += f'<div class="chart-container"><canvas id="{chart_id}"></canvas></div>'
                chart_scripts.append(generate_chart_js(chart, chart_id, palette, template))
                chart_counter += 1
                
        if sec.get("table"):
            sections_html += "<table><thead><tr>"
            tbl = sec["table"]
            for idx, h in enumerate(tbl.get("headers", [])):
                sections_html += f"<th>{h}</th>"
            sections_html += "</tr></thead><tbody>"
            for row in tbl.get("rows", []):
                sections_html += "<tr>"
                for cell in row:
                    sections_html += f"<td>{cell}</td>"
                sections_html += "</tr>"
            sections_html += "</tbody></table>"
            
        sections_html += "</div>"

    watermark = '<div class="watermark">DRAFT / INVOICE</div>' if template == 'paper' else ''

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link href="{font_url}" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        {css}
        .print-btn {{ position: fixed; bottom: 20px; right: 20px; background: #333; color: #fff; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; z-index: 1000; font-family: sans-serif; }}
        @media print {{ .print-btn {{ display: none; }} }}
    </style>
</head>
<body>
    {watermark}
    <button class="print-btn" onclick="window.print()">🖨️ Print</button>
    <div class="container">
        <div class="header-section">
            <h1>{title}</h1>
            {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
            <div class="meta">
                <strong>{author}</strong> | {date_str}
            </div>
        </div>
        {sections_html}
    </div>
    <script>
        window.onload = function() {{
            {chr(10).join(chart_scripts)}
        }};
    </script>
</body>
</html>"""
    return html
