import os
import logging
import httpx
import json
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from scrapling.fetchers import Fetcher, StealthyFetcher
from crewai import Agent
from crewai.tools import BaseTool
from crewai_tools import SerperDevTool
from config import intel_llm

logger = logging.getLogger('bima_core')

search_tool = SerperDevTool()
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
}

# ============================================================
# Tool 1: Marketplace Scraper
# ============================================================
class MarketplaceScraper(BaseTool):
    name: str = "Marketplace Scraper Tool"
    description: str = """Scraping harga produk dari Tokopedia dan Shopee real-time.
    Input: nama produk. Contoh: 'kayu pinus 2x4', 'engsel furniture'"""

    def _run(self, query: str) -> str:
        results = []
        try:
            url = f"https://www.tokopedia.com/search?st=product&q={query.replace(' ', '%20')}"
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True, humanize=True, timeout=30000)
            soup = BeautifulSoup(page.body, "html.parser")
            scripts = soup.find_all("script", type="application/ld+json")
            for script in scripts[:3]:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data[:5]:
                            if item.get("@type") == "Product":
                                name = item.get("name", "")
                                price = item.get("offers", {}).get("price", "")
                                results.append(f"[Tokopedia] {name}: Rp {int(float(price)):,}" if price else f"[Tokopedia] {name}")
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.debug(f"[Tokopedia] Skip script JSON-LD invalid: {e}")
            if not results:
                harga_els = soup.find_all(attrs={"data-testid": "spnSRPProdPrice"})
                nama_els = soup.find_all(attrs={"data-testid": "spnSRPProdName"})
                for harga, nama in zip(harga_els[:5], nama_els[:5]):
                    results.append(f"[Tokopedia] {nama.get_text(strip=True)}: {harga.get_text(strip=True)}")
        except Exception as e:
            results.append(f"[Tokopedia] Gagal: {e}")

        try:
            url = f"https://shopee.co.id/search?keyword={query.replace(' ', '%20')}"
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True, humanize=True, timeout=30000)
            soup = BeautifulSoup(page.body, "html.parser")
            scripts = soup.find_all("script", type="application/ld+json")
            for script in scripts[:3]:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get("@type") == "ItemList":
                        for item in data.get("itemListElement", [])[:5]:
                            name = item.get("name", "")
                            price = item.get("offers", {}).get("price", "")
                            results.append(f"[Shopee] {name}: Rp {int(float(price)):,}" if price else f"[Shopee] {name}")
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.debug(f"[Shopee] Skip script JSON-LD invalid: {e}")
        except Exception as e:
            results.append(f"[Shopee] Gagal: {e}")

        if not results:
            return f"❌ Scraping web e-commerce diblokir atau gagal.\nInstruksi Wajib: Segera panggil Search Tool (SerperDevTool) dengan query 'harga {query} tokopedia shopee'."
        return f"=== Marketplace: '{query}' ===\n\n" + "\n".join(results[:10]) + "\n\n💡 Harga bisa berubah sewaktu-waktu."

# ============================================================
# Tool 2: Reddit Scraper
# ============================================================
class RedditScraper(BaseTool):
    name: str = "Reddit Scraper Tool"
    description: str = """Scraping diskusi dari Reddit.
    Input: topik. Contoh: 'japandi furniture DIY', 'crewai tips'"""

    def _run(self, query: str) -> str:
        try:
            url = f"https://www.reddit.com/search.json?q={query.replace(' ', '+')}&sort=relevance&limit=10&type=link"
            headers = {**HEADERS_BROWSER, "Accept": "application/json"}
            resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            if not posts:
                return f"Tidak ada hasil Reddit untuk '{query}'."

            results = [f"=== Reddit: '{query}' ===\n"]
            for post in posts[:7]:
                p = post.get("data", {})
                title = p.get("title", "")
                sub = p.get("subreddit", "")
                score = p.get("score", 0)
                url_post = f"https://reddit.com{p.get('permalink', '')}"
                text = p.get("selftext", "")[:200]
                results.append(
                    f"📌 r/{sub} | ⬆️ {score}\n"
                    f"   {title}\n"
                    f"   {text}{'...' if text else ''}\n"
                    f"   🔗 {url_post}\n"
                )
            return "\n".join(results)
        except Exception as e:
            return f"Gagal scrape Reddit: {e}"

# ============================================================
# Tool 3: GitHub Scraper
# ============================================================
class GitHubScraper(BaseTool):
    name: str = "GitHub Scraper Tool"
    description: str = """Scraping repository dari GitHub.
    Input: keyword. Contoh: 'crewai agent', 'discord bot python'"""

    def _run(self, query: str) -> str:
        try:
            url = f"https://api.github.com/search/repositories?q={query.replace(' ', '+')}&sort=stars&order=desc&per_page=7"
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "BIMA-Core-Intel-Agent"
            }
            resp = httpx.get(url, headers=headers, timeout=15)
            items = resp.json().get("items", [])
            if not items:
                return f"Tidak ada repository GitHub untuk '{query}'."

            results = [f"=== GitHub: '{query}' ===\n"]
            for repo in items:
                results.append(
                    f"⭐ {repo.get('stargazers_count',0):,} | {repo.get('language','?')} | {repo.get('updated_at','')[:10]}\n"
                    f"   📦 {repo.get('full_name','')}\n"
                    f"   {repo.get('description','Tidak ada deskripsi')}\n"
                    f"   🔗 {repo.get('html_url','')}\n"
                )
            return "\n".join(results)
        except Exception as e:
            return f"Gagal scrape GitHub: {e}"

# ============================================================
# Tool 4: X/Twitter Scraper via RapidAPI
# ============================================================
class XScraper(BaseTool):
    name: str = "X Twitter Scraper Tool"
    description: str = """Scraping tweet dari X via RapidAPI.
    Input: keyword. Contoh: 'japandi furniture', 'AI agent 2026'"""

    def _run(self, query: str) -> str:
        if not RAPIDAPI_KEY:
            return "RAPIDAPI_KEY tidak ditemukan di .env"

        try:
            url = "https://twitter135.p.rapidapi.com/v2/Search/"
            headers = {
                "x-rapidapi-host": "twitter135.p.rapidapi.com",
                "x-rapidapi-key": RAPIDAPI_KEY,
            }
            params = {"q": query, "count": "10", "type": "Latest"}
            resp = httpx.get(url, headers=headers, params=params, timeout=15)
            data = resp.json()

            tweets_data = (
                data.get("data", {})
                .get("search_by_raw_query", {})
                .get("search_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )

            tweets = []
            for instruction in tweets_data:
                entries = instruction.get("entries", [])
                for entry in entries:
                    content = entry.get("content", {}).get("itemContent", {})
                    tweet_result = content.get("tweet_results", {}).get("result", {})
                    legacy = tweet_result.get("legacy", {})
                    if legacy:
                        user = tweet_result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                        tweets.append({
                            "text": legacy.get("full_text", "")[:280],
                            "user": user.get("name", "unknown"),
                            "username": user.get("screen_name", ""),
                            "likes": legacy.get("favorite_count", 0),
                            "retweets": legacy.get("retweet_count", 0),
                            "date": legacy.get("created_at", "")
                        })

            if not tweets:
                raise ValueError("Tidak ada tweet ditemukan")

            results = [f"=== X/Twitter: '{query}' ===\n"]
            for t in tweets[:7]:
                results.append(
                    f"🐦 {t['user']} (@{t['username']})\n"
                    f"   {t['text']}\n"
                    f"   ❤️ {t['likes']} | 🔁 {t['retweets']} | 📅 {t['date'][:10]}\n"
                )
            return "\n".join(results)

        except Exception as e1:
            try:
                url = "https://twitter-api45.p.rapidapi.com/search.php"
                headers = {
                    "x-rapidapi-host": "twitter-api45.p.rapidapi.com",
                    "x-rapidapi-key": RAPIDAPI_KEY,
                }
                params = {"query": query, "search_type": "Latest"}
                resp = httpx.get(url, headers=headers, params=params, timeout=15)
                data = resp.json()

                timeline = data.get("timeline", [])
                if not timeline:
                    return f"Tidak ada tweet untuk '{query}'."

                results = [f"=== X/Twitter: '{query}' ===\n"]
                for t in timeline[:7]:
                    text = t.get("text", "")[:280]
                    user = t.get("user", {}).get("name", "unknown")
                    username = t.get("user", {}).get("screen_name", "")
                    likes = t.get("favorite_count", 0)
                    rts = t.get("retweet_count", 0)
                    results.append(
                        f"🐦 {user} (@{username})\n"
                        f"   {text}\n"
                        f"   ❤️ {likes} | 🔁 {rts}\n"
                    )
                return "\n".join(results)

            except Exception as e2:
                return f"Gagal scrape X via RapidAPI.\nError 1: {e1}\nError 2: {e2}\nCoba gunakan SerperDevTool sebagai alternatif."

# ============================================================
# Tool 5: Web Fetch
# ============================================================
class WebFetchTool(BaseTool):
    name: str = "Web Fetch Tool"
    description: str = """Ambil konten dari URL website.
    Input: URL lengkap."""

    def _run(self, url: str) -> str:
        try:
            page = Fetcher.get(url, stealthy_headers=True, follow_redirects=True, timeout=15)
            if page.status >= 400 or len(page.body or '') < 500:
                page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=20000)
            soup = BeautifulSoup(page.body, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 30]
            return f"=== Konten dari {url} ===\n\n" + "\n".join(lines[:100])
        except Exception as e:
            return f"Gagal fetch URL: {e}"

# ============================================================
# Tool: Async Multi-Fetch (Perplexity Style)
# ============================================================
class AsyncMultiFetchTool(BaseTool):
    name: str = "Async Multi-Fetch Tool"
    description: str = """Ambil konten dari BANYAK URL sekaligus secara paralel.
    Input: daftar URL yang dipisahkan dengan koma. Contoh: 'https://web1.com, https://web2.com'"""

    def _run(self, urls_str: str) -> str:
        urls = [u.strip() for u in urls_str.split(',') if u.strip().startswith('http')]
        if not urls:
            return "❌ Tidak ada URL valid."

        try:
            web_tool = WebFetchTool()
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(web_tool._run, urls[:5]))
            return "\n\n".join(results)
        except Exception as e:
            return f"Gagal Multi-Fetch: {e}"

# ============================================================
# Tool 6: Smart Search (Auto-Retry Chain + Cache)
# ============================================================
import sqlite3
from pathlib import Path

CACHE_DB = Path(__file__).parent.parent / "outputs" / "search_cache.db"
CACHE_DB.parent.mkdir(exist_ok=True)

def init_cache_db():
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS search_cache
                     (query TEXT PRIMARY KEY, timestamp REAL, result TEXT)''')

def get_search_cache(query: str):
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            cursor = conn.execute("SELECT timestamp, result FROM search_cache WHERE query=?", (query,))
            row = cursor.fetchone()
            if row:
                return row
    except Exception:
        pass
    return None

def set_search_cache(query: str, result: str):
    import time
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            conn.execute("INSERT OR REPLACE INTO search_cache (query, timestamp, result) VALUES (?, ?, ?)", 
                         (query, time.time(), result))
    except Exception:
        pass

init_cache_db()

class SmartSearchTool(BaseTool):
    name: str = "Smart Search Tool"
    description: str = """Pencarian cerdas dengan auto-retry. Otomatis coba berbagai sumber.
    Cocok untuk: harga produk, info umum, berita terbaru.
    Input: query pencarian. Contoh: 'harga kayu pinus 2026'"""

    def _run(self, query: str) -> str:
        import time
        cache_key = query.lower().strip()
        cached = get_search_cache(cache_key)
        if cached:
            ts, cached_result = cached
            if time.time() - ts < 3600:
                return f"[DARI CACHE]\n{cached_result}"

        # Augmentasi query untuk pertanyaan harga: arahkan Serper ke listing marketplace.
        # DOM scraping Tokopedia/Shopee tidak reliable lagi (CSS hash + lazy render),
        # jadi kita andalkan index Google yang sudah mengekspos harga di SERP.
        kata_harga = ['harga', 'murah', 'beli', 'jual', 'produk', 'toko']
        search_query = query
        if any(k in query.lower() for k in kata_harga) and 'tokopedia' not in query.lower():
            search_query = f"{query} site:tokopedia.com OR site:shopee.co.id OR site:bukalapak.com"

        # Chain 1: Serper (Google Search) — paling reliable
        try:
            result = search_tool.run(search_query=search_query)
            if result and len(str(result)) > 50:
                result_str = str(result)
                set_search_cache(cache_key, result_str)
                return result_str
        except Exception as e:
            print(f"[INTEL] Serper error/habis: {e}")

        # Chain 2: Tavily API (Cadangan jika Serper gagal/habis limit)
        if TAVILY_API_KEY:
            try:
                tavily_url = "https://api.tavily.com/search"
                tavily_data = {
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5
                }
                resp = httpx.post(tavily_url, json=tavily_data, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    res_items = data.get("results", [])
                    if res_items:
                        tavily_res = [f"=== Tavily Search (Fallback): '{query}' ===\n"]
                        for r in res_items:
                            tavily_res.append(f"📌 {r.get('title')}\n   {r.get('content')}\n   🔗 {r.get('url')}\n")
                        result_str = "\n".join(tavily_res)
                        set_search_cache(cache_key, result_str)
                        return result_str
            except Exception as e:
                print(f"[INTEL] Tavily fallback error: {e}")

        return f"❌ Semua sumber gagal untuk query: '{query}'. Coba parafrase pertanyaan."

# ============================================================
# Tool 7: OSINT Deep Search (WHOIS/DNS)
# ============================================================
class OSINTDeepSearchTool(BaseTool):
    name: str = "OSINT Deep Search Tool"
    description: str = """Melakukan background check digital pada sebuah domain/website.
    Mencari tahu siapa pemiliknya, kapan didirikan, dan lokasi servernya.
    Input: nama domain. Contoh: 'bima-core.com' atau 'tokopedia.com'"""

    def _run(self, domain: str) -> str:
        try:
            import socket
            import urllib.request
            
            domain = domain.replace("https://", "").replace("http://", "").split("/")[0].strip()
            
            output = [f"🔍 OSINT Report: {domain}"]
            
            # DNS/IP Lookup
            try:
                ip = socket.gethostbyname(domain)
                output.append(f"🌐 IP Address: {ip}")
                
                # IP Geolocation using ip-api.com (free, no auth)
                geo_resp = httpx.get(f"http://ip-api.com/json/{ip}", timeout=10)
                if geo_resp.status_code == 200:
                    geo = geo_resp.json()
                    output.append(f"📍 Lokasi Server: {geo.get('city')}, {geo.get('country')} (ISP: {geo.get('isp')})")
            except Exception as e:
                logger.debug(f"[OSINT] DNS/geo lookup gagal untuk {domain}: {e}")
                output.append("🌐 IP/Lokasi: Tidak dapat dilacak.")
                
            # WHOIS lookup via rdap
            try:
                rdap_url = f"https://rdap.verisign.com/com/v1/domain/{domain}" if domain.endswith(".com") else f"https://rdap.org/domain/{domain}"
                req = urllib.request.Request(rdap_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    events = data.get("events", [])
                    for e in events:
                        action = e.get("eventAction", "")
                        date = e.get("eventDate", "").split("T")[0]
                        if action == "registration":
                            output.append(f"📅 Didirikan: {date}")
                        elif action == "expiration":
                            output.append(f"⏳ Expired: {date}")
            except Exception as e:
                logger.debug(f"[OSINT] WHOIS lookup gagal untuk {domain}: {e}")
                output.append("📜 WHOIS Data: Privat atau tidak tersedia via RDAP publik.")

            return "\n".join(output)
        except Exception as e:
            return f"Error OSINT: {e}"

# ============================================================
# Intel Agent — VERSI STRICT + SMART
# ============================================================
intel_agent = Agent(
    role='Senior Multi-Platform Intelligence Researcher',
    goal='Mencari data valid dan terbaru dari internet. SELALU pakai tool, JANGAN jawab dari pengetahuan sendiri.',
    backstory="""Kamu adalah mata dan telinga B.I.M.A Core.

    ATURAN WAJIB — LANGGAR = SALAH:
    1. SELALU panggil SALAH SATU tool untuk cari data
    2. JANGAN PERNAH jawab dari pengetahuan sendiri atau "kira-kira"
    3. Kalau Bima minta "saran", "analisis", "rekomendasi" → CARI DATA DULU pakai tool, baru kasih saran berdasarkan data
    4. Kalau tool gagal atau tidak ada data → bilang JUJUR "Maaf Bima, data tidak ditemukan"
    5. JANGAN ngarang data, harga, atau fakta
    6. Setiap jawaban HARUS sebutkan sumber platformnya

    Pilih tool yang tepat:
    - Harga produk         → SmartSearchTool (Google search, otomatis prioritas listing marketplace)
    - Opini / review       → RedditScraper
    - Library / kode       → GitHubScraper
    - Tren & berita X      → XScraper
    - Info umum / Google   → SerperDevTool atau SmartSearchTool
    - Ekstrak 1 URL        → WebFetchTool
    - Ekstrak BANYAK URL   → AsyncMultiFetchTool
    - Lacak Website/Domain → OSINTDeepSearchTool
    - Marketplace scrape   → MarketplaceScraper (HANYA jika user eksplisit minta scraping Tokopedia/Shopee — slow & sering gagal anti-bot, prefer SmartSearchTool)

    Kamu TIDAK PERNAH mengarang data. SELALU pakai tool.""",
    llm=intel_llm,
    tools=[search_tool, SmartSearchTool(), MarketplaceScraper(), RedditScraper(), GitHubScraper(), XScraper(), WebFetchTool(), AsyncMultiFetchTool(), OSINTDeepSearchTool()],
    allow_delegation=True,
    verbose=True
)