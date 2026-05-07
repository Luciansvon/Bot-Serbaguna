import os
import json
import logging
import httpx
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from pathlib import Path
from crewai import Agent
from crewai.tools import BaseTool
from crewai_tools import SerperDevTool
from config import intel_llm  # reuse LLM intel; ganti ke saham_llm kalau nanti dibuat

logger = logging.getLogger('bima_core')
search_tool = SerperDevTool()

# === Ticker resolution cache (try .JK probe + persist) ===
_TICKER_CACHE_PATH = Path(__file__).parent.parent / "outputs" / "ticker_cache.json"


def _load_ticker_cache() -> dict:
    if _TICKER_CACHE_PATH.exists():
        try:
            return json.loads(_TICKER_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[TICKER CACHE] Korup, reset: {e}")
            return {}
    return {}


def _save_ticker_cache(cache: dict) -> None:
    try:
        _TICKER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TICKER_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[TICKER CACHE] Gagal save: {e}")


_TICKER_CACHE = _load_ticker_cache()


def _probe_idx_jk(s: str) -> bool:
    """Cek apakah `{s}.JK` ada di yfinance. Return True kalau ada data."""
    try:
        df = yf.Ticker(f"{s}.JK").history(period="5d")
        return not df.empty
    except Exception:
        return False

# ============================================================
# Helper — Normalisasi ticker IDX vs Global
# ============================================================
def normalisasi_ticker(symbol: str) -> str:
    """BBCA → BBCA.JK; AAPL → AAPL; BTC → BTC-USD; ENRG/TKIM/dst → probe `.JK` (cached)."""
    s = symbol.upper().strip()
    # Sudah punya suffix → biarkan
    if s.endswith(".JK") or s.endswith("-USD"):
        return s
    crypto_known = {
        "BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX","DOT","MATIC",
        "LINK","LTC","TRX","TON","SHIB","ATOM","NEAR","UNI","ETC","FIL",
    }
    if s in crypto_known:
        return f"{s}-USD"
    idx_known = {
        "BBCA","BBRI","BMRI","BBNI","TLKM","ASII","UNVR","ICBP","INDF","GGRM",
        "HMSP","KLBF","SMGR","INTP","ANTM","INCO","ADRO","PTBA","ITMG","PGAS",
        "JSMR","WIKA","PTPP","WSKT","ADHI","UNTR","CPIN","JPFA","MAPI","ACES",
        "MYOR","ULTJ","SIDO","KAEF","INAF","MEDC","ENRG","ELSA","ARTO","BRIS",
        "EMTK","BUKA","GOTO","BREN","AMMN","CUAN","TPIA","BRPT","BBYB","BANK",
    }
    if s in idx_known:
        return f"{s}.JK"

    # Cache hit — instant
    if s in _TICKER_CACHE:
        return _TICKER_CACHE[s]

    # Heuristik probe: hanya untuk ticker 3-5 huruf alpha (mirip pattern IDX/global)
    if 3 <= len(s) <= 5 and s.isalpha():
        resolved = f"{s}.JK" if _probe_idx_jk(s) else s
        _TICKER_CACHE[s] = resolved
        _save_ticker_cache(_TICKER_CACHE)
        logger.info(f"[TICKER CACHE] Resolve {s!r} -> {resolved!r}")
        return resolved

    return s

# ============================================================
# Tool 1: Stock Quote — harga real-time + info dasar
# ============================================================
class StockQuoteTool(BaseTool):
    name: str = "Stock Quote Tool"
    description: str = """Ambil harga saham real-time + info dasar (nama, market cap, sektor).
    Support saham IDX (BBCA, TLKM, dst) dan global (AAPL, MSFT, TSLA, dst).
    Input: ticker. Contoh: 'BBCA', 'AAPL', 'TSLA', 'TLKM'"""

    def _run(self, symbol: str) -> str:
        try:
            ticker = normalisasi_ticker(symbol)
            t = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="5d")
            if hist.empty:
                return f"❌ Ticker {ticker} tidak ditemukan / tidak ada data."

            last = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) > 1 else last
            change = last - prev
            change_pct = (change / prev * 100) if prev else 0
            currency = info.get("currency", "USD")
            symbol_currency = "Rp" if currency == "IDR" else "$"

            return (
                f"=== {info.get('longName', ticker)} ({ticker}) ===\n"
                f"💰 Harga: {symbol_currency}{last:,.2f}  ({change:+.2f} / {change_pct:+.2f}%)\n"
                f"📊 Volume: {hist['Volume'].iloc[-1]:,.0f}\n"
                f"🏢 Sektor: {info.get('sector', '-')} | Industri: {info.get('industry', '-')}\n"
                f"💼 Market Cap: {symbol_currency}{info.get('marketCap', 0):,}\n"
                f"📈 52W High: {symbol_currency}{info.get('fiftyTwoWeekHigh', 0):,.2f} | Low: {symbol_currency}{info.get('fiftyTwoWeekLow', 0):,.2f}\n"
                f"⏰ Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        except Exception as e:
            return f"Gagal ambil quote {symbol}: {e}"

# ============================================================
# Tool 2: Technical Analysis — RSI, MACD, SMA, Bollinger
# ============================================================
class TechnicalAnalysisTool(BaseTool):
    name: str = "Technical Analysis Tool"
    description: str = """Analisis teknikal: RSI, MACD, SMA20/50/200, Bollinger Bands, sinyal trend.
    Input: ticker. Contoh: 'BBCA', 'AAPL'"""

    def _run(self, symbol: str) -> str:
        try:
            ticker = normalisasi_ticker(symbol)
            df = yf.Ticker(ticker).history(period="6mo")
            if df.empty or len(df) < 50:
                return f"❌ Data {ticker} tidak cukup untuk analisis teknikal."

            df["RSI"] = ta.rsi(df["Close"], length=14)
            macd = ta.macd(df["Close"])
            df = df.join(macd)
            df["SMA20"] = ta.sma(df["Close"], 20)
            df["SMA50"] = ta.sma(df["Close"], 50)
            if len(df) >= 200:
                df["SMA200"] = ta.sma(df["Close"], 200)
            bb = ta.bbands(df["Close"], length=20)
            df = df.join(bb)

            last = df.iloc[-1]
            close = last["Close"]
            rsi = last["RSI"]
            macd_val = last.get("MACD_12_26_9", 0)
            macd_sig = last.get("MACDs_12_26_9", 0)
            sma20 = last["SMA20"]
            sma50 = last["SMA50"]
            sma200 = last["SMA200"] if "SMA200" in df.columns and pd.notna(last.get("SMA200")) else None
            bb_up = last.get("BBU_20_2.0", 0)
            bb_lo = last.get("BBL_20_2.0", 0)

            # Sinyal
            sinyal = []
            if rsi < 30: sinyal.append("RSI OVERSOLD (potensi rebound)")
            elif rsi > 70: sinyal.append("RSI OVERBOUGHT (potensi koreksi)")
            else: sinyal.append(f"RSI netral ({rsi:.1f})")

            if macd_val > macd_sig: sinyal.append("MACD bullish crossover")
            else: sinyal.append("MACD bearish")

            if close > sma20 > sma50: sinyal.append("Trend NAIK (di atas SMA20 & SMA50)")
            elif close < sma20 < sma50: sinyal.append("Trend TURUN (di bawah SMA20 & SMA50)")
            else: sinyal.append("Trend SIDEWAYS")

            if sma200 and close > sma200: sinyal.append("Long-term BULLISH (di atas SMA200)")
            elif sma200: sinyal.append("Long-term BEARISH (di bawah SMA200)")

            if close <= bb_lo: sinyal.append("Sentuh Bollinger Lower (oversold)")
            elif close >= bb_up: sinyal.append("Sentuh Bollinger Upper (overbought)")

            return (
                f"=== Technical Analysis: {ticker} ===\n"
                f"Close: {close:,.2f}\n"
                f"RSI(14): {rsi:.2f}\n"
                f"MACD: {macd_val:.3f} | Signal: {macd_sig:.3f}\n"
                f"SMA20: {sma20:,.2f} | SMA50: {sma50:,.2f}"
                + (f" | SMA200: {sma200:,.2f}\n" if sma200 else "\n")
                + f"Bollinger: [{bb_lo:,.2f} — {bb_up:,.2f}]\n\n"
                f"📡 SINYAL:\n- " + "\n- ".join(sinyal)
            )
        except Exception as e:
            return f"Gagal TA {symbol}: {e}"

# ============================================================
# Tool 3: Fundamental Analysis — PER, PBV, ROE, EPS, Dividend
# ============================================================
class FundamentalAnalysisTool(BaseTool):
    name: str = "Fundamental Analysis Tool"
    description: str = """Analisis fundamental: PER, PBV, EPS, ROE, DER, dividend yield.
    Input: ticker. Contoh: 'BBCA', 'AAPL'"""

    def _run(self, symbol: str) -> str:
        try:
            ticker = normalisasi_ticker(symbol)
            info = yf.Ticker(ticker).info
            # yfinance kadang ga isi field 'symbol' untuk IDX, jadi fallback: cek currency/quoteType
            if not info or not (info.get("currency") or info.get("quoteType") or info.get("regularMarketPrice")):
                return f"❌ Ticker {ticker} tidak ditemukan."

            # Merge manual override (Bima input dari Stockbit/Ajaib)
            from core.saham_override import get_yf_merged_info, get_override
            info = get_yf_merged_info(ticker, info)
            override_active = bool(get_override(ticker))

            per = info.get("trailingPE")
            pbv = info.get("priceToBook")
            eps = info.get("trailingEps")
            roe = info.get("returnOnEquity")
            der = info.get("debtToEquity")
            div_yield = info.get("dividendYield")
            profit_margin = info.get("profitMargins")
            rev_growth = info.get("revenueGrowth")
            earnings_growth = info.get("earningsGrowth")

            def fmt(v, pct=False, dec=2):
                if v is None: return "-"
                return f"{v*100:.{dec}f}%" if pct else f"{v:.{dec}f}"

            # Verdict fundamental sederhana
            verdict = []
            if per and per < 15: verdict.append("PER murah (<15)")
            elif per and per > 30: verdict.append("PER mahal (>30)")
            if pbv and pbv < 1: verdict.append("PBV undervalued (<1)")
            elif pbv and pbv > 3: verdict.append("PBV mahal (>3)")
            if roe and roe > 0.15: verdict.append("ROE bagus (>15%)")
            elif roe and roe < 0.05: verdict.append("ROE lemah (<5%)")
            if der and der > 200: verdict.append("DER tinggi — risiko hutang")
            if div_yield and div_yield > 0.04: verdict.append(f"Dividend yield menarik ({div_yield*100:.2f}%)")

            override_note = "\n📝 *Pakai override manual dari Bima*" if override_active else ""
            return (
                f"=== Fundamental: {info.get('longName', ticker)} ({ticker}) ==={override_note}\n"
                f"PER (trailing)   : {fmt(per)}\n"
                f"PBV              : {fmt(pbv)}\n"
                f"EPS              : {fmt(eps)}\n"
                f"ROE              : {fmt(roe, pct=True)}\n"
                f"DER              : {fmt(der)}\n"
                f"Profit Margin    : {fmt(profit_margin, pct=True)}\n"
                f"Revenue Growth   : {fmt(rev_growth, pct=True)}\n"
                f"Earnings Growth  : {fmt(earnings_growth, pct=True)}\n"
                f"Dividend Yield   : {fmt(div_yield, pct=True)}\n\n"
                f"📋 CATATAN: " + (", ".join(verdict) if verdict else "Tidak ada flag mencolok.")
            )
        except Exception as e:
            return f"Gagal fundamental {symbol}: {e}"

# ============================================================
# Tool 4: News Sentiment — berita terbaru saham
# ============================================================
class StockNewsTool(BaseTool):
    name: str = "Stock News Tool"
    description: str = """Berita & sentimen terbaru tentang saham via Google.
    Input: ticker atau nama emiten. Contoh: 'BBCA', 'Tesla', 'TLKM'"""

    def _run(self, query: str) -> str:
        try:
            q = f"berita saham {query} terbaru analisis"
            result = search_tool.run(search_query=q)
            return f"=== Berita: {query} ===\n{result}"
        except Exception as e:
            return f"Gagal ambil berita: {e}"

# ============================================================
# Tool 5: Decision Engine — agregator BUY/HOLD/SELL
# ============================================================
class DecisionEngineTool(BaseTool):
    name: str = "Decision Engine Tool"
    description: str = """Agregator final: gabungkan teknikal + fundamental → BUY / HOLD / SELL + skor 0-100.
    PAKAI INI SETELAH menjalankan TechnicalAnalysisTool & FundamentalAnalysisTool.
    Input: ticker. Contoh: 'BBCA'"""

    def _run(self, symbol: str) -> str:
        try:
            ticker = normalisasi_ticker(symbol)
            t = yf.Ticker(ticker)
            df = t.history(period="6mo")
            info = t.info
            if df.empty or len(df) < 50:
                return f"❌ Data tidak cukup untuk {ticker}."

            # Merge manual override (Bima input dari Stockbit/Ajaib)
            from core.saham_override import get_yf_merged_info, get_override
            info = get_yf_merged_info(ticker, info)
            override_active = bool(get_override(ticker))

            score = 50  # netral
            alasan = []

            # --- Teknikal ---
            df["RSI"] = ta.rsi(df["Close"], 14)
            macd = ta.macd(df["Close"]); df = df.join(macd)
            df["SMA20"] = ta.sma(df["Close"], 20)
            df["SMA50"] = ta.sma(df["Close"], 50)
            last = df.iloc[-1]; close = last["Close"]; rsi = last["RSI"]

            if rsi < 30: score += 10; alasan.append("RSI oversold (+10)")
            elif rsi > 70: score -= 10; alasan.append("RSI overbought (-10)")

            if last.get("MACD_12_26_9", 0) > last.get("MACDs_12_26_9", 0):
                score += 8; alasan.append("MACD bullish (+8)")
            else:
                score -= 8; alasan.append("MACD bearish (-8)")

            if close > last["SMA20"] > last["SMA50"]:
                score += 12; alasan.append("Trend uptrend kuat (+12)")
            elif close < last["SMA20"] < last["SMA50"]:
                score -= 12; alasan.append("Trend downtrend (-12)")

            # --- Fundamental ---
            per = info.get("trailingPE"); pbv = info.get("priceToBook")
            roe = info.get("returnOnEquity"); der = info.get("debtToEquity")
            growth = info.get("earningsGrowth")

            if per:
                if per < 15: score += 8; alasan.append(f"PER murah {per:.1f} (+8)")
                elif per > 30: score -= 5; alasan.append(f"PER mahal {per:.1f} (-5)")
            if pbv:
                if pbv < 1: score += 6; alasan.append(f"PBV {pbv:.2f} undervalued (+6)")
                elif pbv > 3: score -= 4; alasan.append(f"PBV {pbv:.2f} mahal (-4)")
            if roe:
                if roe > 0.15: score += 8; alasan.append(f"ROE {roe*100:.1f}% bagus (+8)")
                elif roe < 0.05: score -= 6; alasan.append(f"ROE {roe*100:.1f}% lemah (-6)")
            if der and der > 200: score -= 6; alasan.append(f"DER {der:.0f} tinggi (-6)")
            if growth:
                if growth > 0.1: score += 6; alasan.append(f"Earnings growth {growth*100:.1f}% (+6)")
                elif growth < 0: score -= 6; alasan.append(f"Earnings nyusut {growth*100:.1f}% (-6)")

            score = max(0, min(100, score))

            if score >= 70: keputusan = "🟢 STRONG BUY"
            elif score >= 58: keputusan = "🟢 BUY"
            elif score >= 45: keputusan = "🟡 HOLD"
            elif score >= 30: keputusan = "🔴 SELL"
            else: keputusan = "🔴 STRONG SELL"

            currency = "Rp" if info.get("currency") == "IDR" else "$"
            override_note = "\n📝 *Pakai override fundamental manual*" if override_active else ""
            return (
                f"=== KEPUTUSAN: {ticker} ==={override_note}\n"
                f"Harga saat ini : {currency}{close:,.2f}\n"
                f"Skor           : {score}/100\n"
                f"Keputusan      : {keputusan}\n\n"
                f"📌 Alasan:\n- " + "\n- ".join(alasan) +
                f"\n\n⚠️ Disclaimer: Output ini bukan ajakan beli/jual. Always DYOR & sesuaikan profil risiko."
            )
        except Exception as e:
            return f"Decision engine error: {e}"

# ============================================================
# Saham Agent
# ============================================================
saham_agent = Agent(
    role='Senior Stock Analyst — IDX & Global Markets',
    goal='Memberikan analisis saham objektif (teknikal + fundamental + berita) lalu kasih keputusan BUY/HOLD/SELL berdasarkan data, BUKAN tebakan.',
    backstory="""Kamu analis saham senior B.I.M.A Core. Kamu menguasai pasar IDX (saham .JK)
    dan saham luar negeri (AAPL, TSLA, NVDA, dll). Komunikasi bahasa Indonesia, ramah, pakai emoji.

    ATURAN WAJIB:
    1. SELALU pakai tool — JANGAN ngarang harga atau angka.
    2. Workflow standar untuk setiap permintaan analisis:
       a. StockQuoteTool       → harga & info dasar
       b. TechnicalAnalysisTool → sinyal teknikal
       c. FundamentalAnalysisTool → kesehatan perusahaan
       d. StockNewsTool        → sentimen berita (opsional, kalau diminta)
       e. DecisionEngineTool   → keputusan final BUY/HOLD/SELL
    3. SELALU sertakan disclaimer: ini bukan ajakan investasi, DYOR.
    4. Untuk saham IDX, otomatis tambahkan suffix .JK (sudah di-handle helper).
    5. Kalau Bima minta saran portofolio → minta dia sebut profil risiko & horizon waktu dulu.
    6. Output rapi: gabungkan semua hasil tool, kasih ringkasan eksekutif di akhir.

    Karakter: objektif, data-driven, tapi hangat. Hindari hype. Sebut risiko dengan jujur.""",
    llm=intel_llm,
    tools=[
        StockQuoteTool(),
        TechnicalAnalysisTool(),
        FundamentalAnalysisTool(),
        StockNewsTool(),
        DecisionEngineTool(),
        search_tool,
    ],
    allow_delegation=False,
    verbose=True
)
