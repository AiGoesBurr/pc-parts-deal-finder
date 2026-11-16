import csv, io, os, re
import urllib.request
import xml.etree.ElementTree as ET
import json as _json

IMAGE_CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "images.json")
_image_cache = {}
try:
    if os.path.exists(IMAGE_CACHE_PATH):
        _image_cache = _json.load(open(IMAGE_CACHE_PATH, encoding="utf-8"))
except Exception:
    _image_cache = {}
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, has_request_context

from cache import get_data, cache_info, get_price_history, is_scraping

app = Flask(__name__)

@app.context_processor
def inject_region():
    if has_request_context():
        reg = _region()
    else:
        reg = "us"
    cache = get_data(region=reg)
    sym = "$"
    if cache:
        sym = cache.get("_currency_symbol", "$")
    return {"region": reg, "currency_symbol": sym}

CATS = {
    "cpu": {"key": "cpus", "title": "CPUs", "value_col": "value", "value_label": "CPU Value (Mark/$)"},
    "gpu": {"key": "gpus", "title": "GPUs", "value_col": "value", "value_label": "GPU Value (Score/$)"},
    "memory": {"key": "memory", "title": "Memory (RAM)", "value_col": "value", "value_label": "Value (1/$ per GB)"},
    "storage": {"key": "storage", "title": "Storage (SSD/HDD)", "value_col": "value", "value_label": "Value (1/$ per GB)"},
    "psu": {"key": "psu", "title": "Power Supplies", "value_col": "value", "value_label": "Value (W/$)"},
    "motherboard": {"key": "motherboard", "title": "Motherboards", "value_col": "value", "value_label": "Value (1/$)"},
    "case": {"key": "case", "title": "Cases", "value_col": "value", "value_label": "Value (1/$)"},
    "cooler": {"key": "cooler", "title": "CPU Coolers", "value_col": "value", "value_label": "Value (1/$)"},
    "prebuilt": {"key": "prebuilts", "title": "Prebuilt PCs", "value_col": "value", "value_label": "Value (1/$)"},
    "monitor": {"key": "monitor", "title": "Monitors", "value_col": "value", "value_label": "Value (1/$)"},
    "keyboard": {"key": "keyboard", "title": "Keyboards", "value_col": "value", "value_label": "Value (1/$)"},
    "mouse": {"key": "mouse", "title": "Mice", "value_col": "value", "value_label": "Value (1/$)"},
    "headphones": {"key": "headphones", "title": "Headphones", "value_col": "value", "value_label": "Value (1/$)"},
}

def _region():
    if has_request_context():
        return request.args.get("region", "us")
    return "us"

def _rows(cat):
    cache = get_data(region=_region())
    if not cache:
        return []
    key = CATS[cat]["key"]
    return cache.get(key, []) if isinstance(cache.get(key), list) else []

@app.route("/")
def index():
    cache = get_data(region=_region())
    info = cache_info(cache)
    # top picks
    def top(key, n=6):
        rows = cache.get(key, []) if cache else []
        rows = [r for r in rows if r.get("value")]
        rows.sort(key=lambda r: r.get("value") or 0, reverse=True)
        return rows[:n]
    top_cpu = top("cpus")
    top_gpu = top("gpus")
    # memory/storage best by price_per_gb asc
    mem = [r for r in (cache.get("memory", []) if cache else []) if r.get("price_per_gb")]
    mem.sort(key=lambda r: r["price_per_gb"])
    stor = [r for r in (cache.get("storage", []) if cache else []) if r.get("price_per_gb")]
    stor.sort(key=lambda r: r["price_per_gb"])
    psu = [r for r in (cache.get("psu", []) if cache else []) if r.get("price_per_watt")]
    psu.sort(key=lambda r: r["price_per_watt"])
    return render_template("index.html", info=info, top_cpu=top_cpu, top_gpu=top_gpu,
                           top_mem=mem[:6], top_stor=stor[:6], top_psu=psu[:6], cats=CATS)

@app.route("/category/<cat>")
def category(cat):
    if cat not in CATS:
        return redirect(url_for("index"))
    return render_template("category.html", cat=cat, meta=CATS[cat], cats=CATS)

@app.route("/api/data/<cat>")
def api_data(cat):
    if cat not in CATS:
        return jsonify({"error": "unknown category"}), 404
    rows = _rows(cat)
    q = (request.args.get("q") or "").strip().lower()
    if q:
        rows = [r for r in rows if q in (r.get("name") or "").lower() or q in (r.get("brand") or "").lower() or q in str(r.get("model") or "").lower()]
    # price range
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")
    try:
        if min_price not in (None, ""):
            mn = float(min_price)
            rows = [r for r in rows if (r.get("price") is not None) and r.get("price") >= mn]
    except ValueError:
        pass
    try:
        if max_price not in (None, ""):
            mx = float(max_price)
            rows = [r for r in rows if (r.get("price") is not None) and r.get("price") <= mx]
    except ValueError:
        pass
    # cores range (cpu)
    min_cores = request.args.get("min_cores")
    max_cores = request.args.get("max_cores")
    try:
        if min_cores not in (None, ""):
            mn = int(min_cores)
            rows = [r for r in rows if (r.get("cores") is not None) and r.get("cores") >= mn]
    except ValueError:
        pass
    try:
        if max_cores not in (None, ""):
            mx = int(max_cores)
            rows = [r for r in rows if (r.get("cores") is not None) and r.get("cores") <= mx]
    except ValueError:
        pass
    # vram/length range (gpu)
    min_vram = request.args.get("min_vram")
    max_vram = request.args.get("max_vram")
    try:
        if min_vram not in (None, ""):
            mn = float(min_vram)
            rows = [r for r in rows if (r.get("vram_gb") is not None) and r.get("vram_gb") >= mn]
    except ValueError:
        pass
    try:
        if max_vram not in (None, ""):
            mx = float(max_vram)
            rows = [r for r in rows if (r.get("vram_gb") is not None) and r.get("vram_gb") <= mx]
    except ValueError:
        pass
    min_length = request.args.get("min_length")
    max_length = request.args.get("max_length")
    try:
        if min_length not in (None, ""):
            mn = float(min_length)
            rows = [r for r in rows if (r.get("length") is not None) and r.get("length") >= mn]
    except ValueError:
        pass
    try:
        if max_length not in (None, ""):
            mx = float(max_length)
            rows = [r for r in rows if (r.get("length") is not None) and r.get("length") <= mx]
    except ValueError:
        pass
    # filters
    for f in request.args:
        if f.startswith("filter_"):
            col = f[len("filter_"):]
            val = request.args.get(f)
            if val:
                rows = [r for r in rows if str(r.get(col)) == val]
    sort = request.args.get("sort", "value")
    order = request.args.get("order", "desc")
    reverse = order == "desc"

    def is_none(r):
        return r.get(sort) is None

    # separate nulls to end regardless of order
    non_null = [r for r in rows if r.get(sort) is not None]
    nulls = [r for r in rows if r.get(sort) is None]

    sample = non_null[0].get(sort) if non_null else None
    if isinstance(sample, str):
        non_null.sort(key=lambda r: str(r.get(sort)).lower(), reverse=reverse)
    else:
        non_null.sort(key=lambda r: r.get(sort), reverse=reverse)
    rows_sorted = non_null + nulls

    offset = int(request.args.get("offset", 0))
    limit = int(request.args.get("limit", 200))
    page = rows_sorted[offset:offset+limit]
    return jsonify({"total": len(rows_sorted), "rows": page, "cat": cat})

@app.route("/api/meta/<cat>")
def api_meta(cat):
    if cat not in CATS:
        return jsonify({"error": "unknown"}), 404
    rows = _rows(cat)
    # distinct values for some fields
    meta = {}
    for col in ("brand", "storage_type", "efficiency", "module_type", "form_factor", "socket"):
        from collections import Counter
        c = Counter(str(r.get(col)) for r in rows if r.get(col) not in (None, ""))
        # keep values that appear at least 5 times, sorted by frequency then name
        vals = [v for v, n in c.most_common() if n >= 5]
        vals = sorted(set(vals))
        if vals:
            meta[col] = vals
    return jsonify(meta)

@app.route("/refresh")
def refresh():
    get_data(force=True, region=_region())
    return redirect(request.referrer or url_for("index"))

@app.route("/sources")
def sources():
    info = cache_info(get_data(region=_region()))
    return render_template("sources.html", info=info, cats=CATS)

@app.route("/export/<cat>.csv")
def export_csv(cat):
    if cat not in CATS:
        return "not found", 404
    rows = _rows(cat)
    if not rows:
        return "no data", 404
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={cat}.csv"})

PC_PART_KEYWORDS = ["ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra", "processor", "cpu", "graphics card", "gpu", "geforce", "radeon", "rtx", "gtx", "rx 6", "rx 7", "rx 9", "motherboard", "ddr4", "ddr5", "ssd", "nvme", "hard drive", "hdd", "power supply", "psu", "cpu cooler", "aio cooler", "liquid cooler", "thermal paste", "pc case"]
SYSTEM_KEYWORDS = ["laptop", "notebook", "chromebook", "macbook", "mac mini", "mac pro", "imac", "prebuilt", "gaming pc", "desktop computer", "desktop pc", "desktop w/", "desktop:", "all-in-one", "thinkpad", "omnibook", "aspire", "yoga", "nitro", "swift", "predator", "helios", "aegis", "loq", "alienware", "omen", "victus", "legion", "ideapad", "thinkcentre", "optiplex", "vostro", "latitude", "precision", "surface", "monitor", "keyboard", "mouse", "headset", "speaker", "webcam", "lego", "drill", "mattress", "smartwatch", "earbuds", "filament", "picture frame", "phone", "tablet", "mini pc", "car refrigerator", "portable fridge", "refrigerator", "beverage", "scanner", "soft-sided", "soft cooler", "hard cooler", "can cooler", "ozark", "trail", "insulated", "removable hard liner", "marine cooler", "3d", "printer", "marine cooler", "soft cooler", "hard cooler", "cooler cup", "mini fridge", "wine cooler", "insulated", "liquid death", "coleman", "stanley", "aurora"]

def _is_pc_part(title):
    low = title.lower()
    if any(x in low for x in SYSTEM_KEYWORDS):
        return False
    return any(k in low for k in PC_PART_KEYWORDS)

import re as _re

def _parse_price(title):
    m = _re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", title)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None

def fetch_deals(sort="newest"):
    queries = ["cpu", "gpu", "ssd", "motherboard", "power supply", "cooler", "ram"]
    seen = set()
    deals = []
    for q in queries:
        url = "https://slickdeals.net/newsearch.php?src=SearchBarV2&q=" + q.replace(" ", "+") + "&searcharea=deals&searchin=first&rss=1"
        try:
            import requests
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            if not title or link in seen:
                continue
            if not _is_pc_part(title):
                continue
            seen.add(link)
            deals.append({"title": title, "link": link, "desc": desc, "pubDate": pub, "price": _parse_price(title)})
    # sort
    if sort == "oldest":
        deals.sort(key=lambda d: d.get("pubDate") or "", reverse=False)
    elif sort == "price_asc":
        deals.sort(key=lambda d: (d.get("price") is None, d.get("price") or 0))
    elif sort == "price_desc":
        deals.sort(key=lambda d: (d.get("price") is None, -(d.get("price") or 0)))
    else:  # newest
        deals.sort(key=lambda d: d.get("pubDate") or "", reverse=True)
    return deals[:40]

@app.route("/deals")
def deals():
    sort = request.args.get("sort", "newest")
    return render_template("deals.html", deals=fetch_deals(sort), sort=sort, cats=CATS)

@app.route("/compat")
def compat():
    return render_template("compat.html", cats=CATS)

@app.route("/watchlist")
def watchlist():
    return render_template("watchlist.html", cats=CATS)

@app.route("/leaderboard")
def leaderboard():
    cache = get_data(region=_region())
    boards = {}
    if cache:
        for cat, meta in CATS.items():
            rows = [r for r in (cache.get(meta["key"], []) or []) if r.get("value")]
            rows.sort(key=lambda r: r.get("value") or 0, reverse=True)
            boards[cat] = (meta, rows[:15])
    return render_template("leaderboard.html", boards=boards, cats=CATS)

@app.route("/savedbuilds")
def savedbuilds():
    return render_template("savedbuilds.html", cats=CATS)

@app.route("/buildtemplates")
def buildtemplates():
    return render_template("buildtemplates.html", cats=CATS)

@app.route("/build")
def build():
    return render_template("build.html", cats=CATS)

@app.route("/compare")
def compare():
    cat = request.args.get("cat", "cpu")
    if cat not in CATS:
        cat = "cpu"
    return render_template("compare.html", cat=cat, meta=CATS[cat], cats=CATS)

def _fetch_image_url(q, link=None):
    cache_key = q + "|" + (link or "")
    if cache_key in _image_cache:
        return _image_cache[cache_key]
    url = None
    # 1. Slickdeals deal page og:image (most accurate for prebuilts/deals)
    if link and "slickdeals.net" in link:
        try:
            import requests
            r = requests.get(link, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=15)
            m = re.search(r'<meta property="og:image" content="([^"]+)"', r.text)
            if m:
                url = m.group(1)
        except Exception:
            url = None
    # 2. Amazon first product image
    if not url:
        try:
            import cloudscraper
            s = cloudscraper.create_scraper()
            aq = q
            low = q.lower()
            if any(w in low for w in ["ryzen", "core i", "core ultra", "xeon", "threadripper", "epyc"]):
                aq = q + " processor"
            elif any(w in low for w in ["rtx", "gtx", "radeon", "geforce", "arc a", "arc b"]):
                aq = q + " graphics card"
            r = s.get("https://www.amazon.com/s?k=" + urllib.request.quote(aq), timeout=20)
            m = re.search(r'<img[^>]*class="s-image"[^>]*src="([^"]+)"', r.text)
            if m:
                url = m.group(1)
        except Exception:
            url = None
    # 3. Manufacturer-domain Bing image (fallback)
    if not url:
        try:
            import requests
            low = q.lower()
            domain = None
            if "amd" in low or "ryzen" in low or "radeon" in low: domain = "amd.com"
            elif "intel" in low: domain = "intel.com"
            elif "nvidia" in low or "geforce" in low or "rtx" in low or "gtx" in low: domain = "nvidia.com"
            elif "corsair" in low: domain = "corsair.com"
            elif "crucial" in low: domain = "crucial.com"
            elif "samsung" in low: domain = "samsung.com"
            elif "seagate" in low: domain = "seagate.com"
            elif "kingston" in low: domain = "kingston.com"
            if domain:
                r = requests.get("https://www.bing.com/images/search?q=" + urllib.request.quote("site:" + domain + " " + q), headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=15)
                imgs = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', r.text)
                if imgs:
                    url = imgs[0]
        except Exception:
            url = None
    # 4. General Bing image search (last resort)
    if not url:
        try:
            import requests
            r = requests.get("https://www.bing.com/images/search?q=" + urllib.request.quote(q + " product"), headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=15)
            imgs = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', r.text)
            if imgs:
                url = imgs[0]
        except Exception:
            url = None
    _image_cache[cache_key] = url
    try:
        os.makedirs(os.path.dirname(IMAGE_CACHE_PATH), exist_ok=True)
        _json.dump(_image_cache, open(IMAGE_CACHE_PATH, "w", encoding="utf-8"))
    except Exception:
        pass
    return url

@app.route("/api/status")
def api_status():
    return jsonify({"scraping": is_scraping()})

@app.route("/api/history")
def api_history():
    cat = request.args.get("cat", "")
    name = request.args.get("name", "")
    if not cat or not name:
        return jsonify({"history": []})
    return jsonify({"history": get_price_history(cat, name)})

@app.route("/api/liveprice")
def api_liveprice():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"price": None})
    try:
        import cloudscraper, re
        s = cloudscraper.create_scraper()
        # infer type
        aq = q
        low = q.lower()
        if any(w in low for w in ["ryzen", "core i", "core ultra", "xeon", "threadripper", "epyc"]):
            aq = q + " processor"
        elif any(w in low for w in ["rtx", "gtx", "radeon", "geforce", "arc a", "arc b"]):
            aq = q + " graphics card"
        r = s.get("https://www.amazon.com/s?k=" + urllib.request.quote(aq), timeout=20)
        # find the first product block price: look for "a-price" with whole+fraction
        m = re.search(r'class="a-price"[^>]*>.*?<span class="a-offscreen">\$([\d,]+\.\d{2})</span>', r.text, re.S)
        if m:
            return jsonify({"price": float(m.group(1).replace(",", ""))})
        # fallback: first price in text
        prices = re.findall(r'\$\s*([\d,]+\.\d{2})', r.text)
        if prices:
            return jsonify({"price": float(prices[0].replace(",", ""))})
    except Exception:
        pass
    return jsonify({"price": None})

@app.route("/api/image")
def api_image():
    q = request.args.get("q", "").strip()
    link = request.args.get("link", "").strip() or None
    if not q:
        return ("", 204)
    url = _fetch_image_url(q, link)
    if not url:
        return ("", 204)
    from flask import redirect
    return redirect(url, code=302)

@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip().lower()
    results = {}
    if q:
        for cat, meta in CATS.items():
            rows = [r for r in _rows(cat) if q in (r.get("name") or "").lower() or q in (r.get("brand") or "").lower() or q in str(r.get("model") or "").lower()]
            if rows:
                results[cat] = (meta, rows[:60])
    return render_template("search.html", q=request.args.get("q") or "", results=results, cats=CATS)

if __name__ == "__main__":
    # trigger background scrape (non-blocking)
    get_data(region="us")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
