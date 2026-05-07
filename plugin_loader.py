"""
B.I.M.A Core — Plugin Loader
Hot-reload custom tools dari folder tools/plugins/

Cara pakai:
1. Buat file .py di tools/plugins/
2. File harus punya fungsi create_tool() yang return instance BaseTool
3. Plugin otomatis di-load saat sistem start

Contoh plugin (tools/plugins/contoh_plugin.py):
    from crewai.tools import BaseTool
    class MyTool(BaseTool):
        name: str = "my_custom_tool"
        description: str = "Tool kustom saya"
        def _run(self, input_str: str) -> str:
            return f"Hasil: {input_str}"
    def create_tool():
        return MyTool()
"""
import os
import sys
import importlib.util
from pathlib import Path

PLUGINS_DIR = Path(__file__).parent / "plugins"

def load_plugins():
    """Scan folder plugins/ dan load semua tool yang ditemukan"""
    PLUGINS_DIR.mkdir(exist_ok=True)
    
    loaded_tools = []
    errors = []
    
    for py_file in sorted(PLUGINS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue  # Skip __init__.py, __pycache__, dll
        
        module_name = f"plugins.{py_file.stem}"
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(py_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Cari fungsi create_tool()
            if hasattr(module, "create_tool"):
                tool = module.create_tool()
                loaded_tools.append(tool)
                print(f"  [PLUGIN] ✅ Loaded: {tool.name} ({py_file.name})")
            
            # Atau cari fungsi create_tools() yang return list
            elif hasattr(module, "create_tools"):
                tools = module.create_tools()
                for t in tools:
                    loaded_tools.append(t)
                    print(f"  [PLUGIN] ✅ Loaded: {t.name} ({py_file.name})")
            
            else:
                print(f"  [PLUGIN] ⚠️ Skip {py_file.name}: tidak ada create_tool() atau create_tools()")
        
        except Exception as e:
            errors.append((py_file.name, str(e)))
            print(f"  [PLUGIN] ❌ Error loading {py_file.name}: {e}")
    
    total = len(loaded_tools)
    if total > 0:
        print(f"  [PLUGIN] 🎉 {total} plugin(s) berhasil dimuat!")
    else:
        print(f"  [PLUGIN] 📂 Tidak ada plugin di {PLUGINS_DIR}")
    
    if errors:
        print(f"  [PLUGIN] ⚠️ {len(errors)} plugin gagal dimuat")
    
    return loaded_tools

if __name__ == "__main__":
    print("🔌 B.I.M.A Core — Plugin Scanner")
    print(f"   Scanning: {PLUGINS_DIR}\n")
    tools = load_plugins()
    print(f"\n   Total tools: {len(tools)}")
