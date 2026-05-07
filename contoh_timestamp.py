"""
Contoh Plugin: Timestamp Tool
Memberikan waktu dan tanggal saat ini dalam format Indonesia
"""
from crewai.tools import BaseTool

class TimestampTool(BaseTool):
    name: str = "timestamp_tool"
    description: str = "Dapatkan waktu dan tanggal saat ini dalam format Indonesia (WIB)"
    
    def _run(self, input_str: str = "") -> str:
        from datetime import datetime, timezone, timedelta
        wib = timezone(timedelta(hours=7))
        now = datetime.now(wib)
        hari = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"][now.weekday()]
        bulan = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"][now.month-1]
        return f"{hari}, {now.day} {bulan} {now.year} pukul {now.strftime('%H:%M:%S')} WIB"

def create_tool():
    return TimestampTool()
