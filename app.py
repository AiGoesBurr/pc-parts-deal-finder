import csv, gzip, io, os, logging, threading as _threading, time as _time, re as _re
logger = logging.getLogger("pcparts.app")
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from flask import Flask, g, render_template, request, jsonify, Response, redirect, url_for, has_request_context

from cache import get_data, cache_info, get_price_history, is_scraping, REGION_CURRENCY
from images import find_photo
from ranking import is_eligible, is_quality_psu, is_nvme_storage, board_ram_type, cpu_socket
from autobuild import build_within_budget

app = Flask(__name__)

def _as_datetime(value):
    """Best-effort conversion of epoch seconds, ISO strings and RSS dates."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@app.template_filter("num")
def num_filter(value, decimals=2):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value if value not in (None, "") else ""
    if abs(number - round(number)) < 1e-9:
        decimals = 0
    return f"{number:,.{decimals}f}"


@app.template_filter("money")
def money_filter(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    symbol = getattr(g, "currency_symbol", None) or "$"
    return f"{symbol}{num_filter(number, 2)}"


@app.template_filter("ago")
def ago_filter(value):
    dt = _as_datetime(value)
    if not dt:
        return value or ""
    seconds = max(0, (datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(seconds // 86400)
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return dt.strftime("%b %d, %Y")


# Retailer search links per region. Only well-known, stable search URLs are
# listed; Google Shopping fills the gap where a local retailer URL is not
# guaranteed to be stable. "cls" maps to a Bootstrap button style.
RETAILERS = {
    "us": [
        {"name": "Amazon", "url": "https://www.amazon.com/s?k={q}", "cls": "primary"},
        {"name": "Newegg", "url": "https://www.newegg.com/p/pl?d={q}", "cls": "success"},
        {"name": "B&H", "url": "https://www.bhphotovideo.com/c/search?Ntt={q}", "cls": "info"},
        {"name": "Best Buy", "url": "https://www.bestbuy.com/site/searchpage.jsp?st={q}", "cls": "warning"},
        {"name": "Micro Center", "url": "https://www.microcenter.com/search/search_results.aspx?Ntt={q}", "cls": "secondary"},
    ],
    "uk": [
        {"name": "Amazon UK", "url": "https://www.amazon.co.uk/s?k={q}", "cls": "primary"},
        {"name": "eBay UK", "url": "https://www.ebay.co.uk/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=uk&hl=en&q={q}", "cls": "light"},
    ],
    "ca": [
        {"name": "Amazon CA", "url": "https://www.amazon.ca/s?k={q}", "cls": "primary"},
        {"name": "Newegg CA", "url": "https://www.newegg.ca/p/pl?d={q}", "cls": "success"},
        {"name": "eBay CA", "url": "https://www.ebay.ca/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=ca&hl=en&q={q}", "cls": "light"},
    ],
    "au": [
        {"name": "Amazon AU", "url": "https://www.amazon.com.au/s?k={q}", "cls": "primary"},
        {"name": "eBay AU", "url": "https://www.ebay.com.au/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=au&hl=en&q={q}", "cls": "light"},
    ],
    "de": [
        {"name": "Amazon DE", "url": "https://www.amazon.de/s?k={q}", "cls": "primary"},
        {"name": "eBay DE", "url": "https://www.ebay.de/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=de&hl=de&q={q}", "cls": "light"},
    ],
    "fr": [
        {"name": "Amazon FR", "url": "https://www.amazon.fr/s?k={q}", "cls": "primary"},
        {"name": "eBay FR", "url": "https://www.ebay.fr/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=fr&hl=fr&q={q}", "cls": "light"},
    ],
    "es": [
        {"name": "Amazon ES", "url": "https://www.amazon.es/s?k={q}", "cls": "primary"},
        {"name": "eBay ES", "url": "https://www.ebay.es/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=es&hl=es&q={q}", "cls": "light"},
    ],
    "it": [
        {"name": "Amazon IT", "url": "https://www.amazon.it/s?k={q}", "cls": "primary"},
        {"name": "eBay IT", "url": "https://www.ebay.it/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=it&hl=it&q={q}", "cls": "light"},
    ],
    "in": [
        {"name": "Amazon IN", "url": "https://www.amazon.in/s?k={q}", "cls": "primary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=in&hl=en&q={q}", "cls": "light"},
    ],
    "nz": [
        {"name": "Amazon AU", "url": "https://www.amazon.com.au/s?k={q}", "cls": "primary"},
        {"name": "Mighty Ape", "url": "https://www.mightyape.co.nz/search?q={q}", "cls": "success"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=nz&hl=en&q={q}", "cls": "light"},
    ],
    "ie": [
        {"name": "Amazon IE", "url": "https://www.amazon.ie/s?k={q}", "cls": "primary"},
        {"name": "eBay IE", "url": "https://www.ebay.ie/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=ie&hl=en&q={q}", "cls": "light"},
    ],
    "be": [
        {"name": "Amazon BE", "url": "https://www.amazon.com.be/s?k={q}", "cls": "primary"},
        {"name": "eBay BE", "url": "https://www.ebay.be/sch/i.html?_nkw={q}", "cls": "secondary"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=be&hl=nl&q={q}", "cls": "light"},
    ],
    "se": [
        {"name": "Amazon SE", "url": "https://www.amazon.se/s?k={q}", "cls": "primary"},
        {"name": "Komplett SE", "url": "https://www.komplett.se/search?q={q}", "cls": "success"},
        {"name": "Google Shopping", "url": "https://www.google.com/search?tbm=shop&gl=se&hl=sv&q={q}", "cls": "light"},
    ],
}


@app.after_request
def _gzip_response(response):
    try:
        accept = (request.headers.get("Accept-Encoding") or "")
    except Exception:
        accept = ""
    if "gzip" not in accept.lower():
        return response
    if response.status_code >= 400 or response.direct_passthrough:
        return response
    ctype = (response.mimetype or "")
    if not (ctype.startswith("text/") or ctype in ("application/json", "application/javascript", "image/svg+xml", "application/xml")):
        return response
    data = response.get_data()
    if not data or len(data) < 500:
        return response
    gz = gzip.compress(data, compresslevel=6)
    response.set_data(gz)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(gz))
    response.headers["Vary"] = "Accept-Encoding"
    return response

@app.after_request
def _persist_region(response):
    """Remember the chosen region so internal links keep the same market."""
    try:
        wanted = request.args.get("region")
        if wanted in REGION_CURRENCY:
            response.set_cookie("region", wanted, max_age=365 * 86400, samesite="Lax")
    except Exception:
        pass
    return response


@app.context_processor
def inject_region():
    if has_request_context():
        reg = _region()
    else:
        reg = "us"
    cache = get_data(region=reg)
    sym = "$"
    saved_ts = None
    if cache:
        sym = cache.get("_currency_symbol", "$")
        saved_ts = cache.get("_saved_at")
    is_local = has_request_context() and request.remote_addr in ("127.0.0.1", "::1", "localhost")
    g.currency_symbol = sym
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    available_regions = []
    for r in REGION_CURRENCY:
        if (os.path.exists(os.path.join(data_dir, f"cache_{r}.json"))
                or os.path.exists(os.path.join(data_dir, f"cache_{r}.json.gz"))):
            available_regions.append(r)
    age_days = None
    if saved_ts:
        age_days = max(0.0, (_time.time() - float(saved_ts)) / 86400)
    return {"region": reg, "currency_symbol": sym,
            "is_local": is_local,
            "show_refresh": os.environ.get("ENABLE_REFRESH") == "1",
            "retailers": RETAILERS.get(reg, RETAILERS["us"]),
            "available_regions": available_regions,
            "region_has_data": reg in available_regions,
            "data_saved_ts": saved_ts,
            "data_age_days": age_days,
            "prices_are_recent": age_days is not None and age_days <= 14,
            "adsense_client": os.environ.get("ADSENSE_CLIENT", "ca-pub-2012616805883507")}

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
    "network": {"key": "network", "title": "Network Adapters", "value_col": "value", "value_label": "Value (1/$)"},
    "ups": {"key": "ups", "title": "UPS / Battery Backups", "value_col": "value", "value_label": "Value (VA/$)"},
    "sound": {"key": "sound", "title": "Sound Cards", "value_col": "value", "value_label": "Value (1/$)"},
    "webcam": {"key": "webcam", "title": "Webcams", "value_col": "value", "value_label": "Value (1/$)"},
    "speakers": {"key": "speakers", "title": "Computer Speakers", "value_col": "value", "value_label": "Value (1/$)"},
    "external_storage": {"key": "external_storage", "title": "External Storage", "value_col": "value", "value_label": "Value (1/$ per GB)"},
    "router": {"key": "router", "title": "Routers", "value_col": "value", "value_label": "Value (1/$)"},
    "thermal_paste": {"key": "thermal_paste", "title": "Thermal Paste", "value_col": "value", "value_label": "Value (1/$)"},
    "surge_protector": {"key": "surge_protector", "title": "Surge Protectors", "value_col": "value", "value_label": "Value (1/$)"},
}

def _region():
    region = (request.args.get("region")
              or request.cookies.get("region")
              or "us") if has_request_context() else "us"
    return region if region in REGION_CURRENCY else "us"

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
    age_days = None
    if cache and cache.get("_saved_at"):
        age_days = max(0.0, (_time.time() - float(cache["_saved_at"])) / 86400)
    prices_are_recent = age_days is not None and age_days <= 14

    # Top value picks. These use the same eligibility rules as the category
    # pages, so server CPUs and old GPU generations cannot win the front page.
    def top(key, cat, n=6, extra=None):
        rows = cache.get(key, []) if cache else []
        rows = [r for r in rows if is_eligible(cat, r) and r.get("value")]
        if extra:
            rows = [r for r in rows if extra(r)]
        rows.sort(key=lambda r: r.get("value") or 0, reverse=True)
        return rows[:n]

    top_cpu = top("cpus", "cpu") if prices_are_recent else []
    top_gpu = top("gpus", "gpu") if prices_are_recent else []
    top_stor = top("storage", "storage", extra=is_nvme_storage) if prices_are_recent else []
    top_psu = top("psu", "psu", extra=is_quality_psu) if prices_are_recent else []

    # Newest deal
    try:
        newest_deal = (fetch_deals("newest") or [None])[0]
    except Exception:
        newest_deal = None

    # RAM/storage/PSU best by unit price, among current priced parts only.
    mem = [r for r in (cache.get("memory", []) if cache else []) if is_eligible("memory", r) and r.get("price_per_gb")]
    mem.sort(key=lambda r: r["price_per_gb"])
    if not prices_are_recent:
        top_cpu = top_gpu = top_stor = top_psu = []
    top_mem = mem[:6] if prices_are_recent else []

    # Compact category directory: cheapest eligible price rather than a raw
    # row count, which is more useful when deciding where to start.
    cat_stats = {}
    for key, meta in CATS.items():
        rows = cache.get(meta["key"], []) if cache else []
        prices = [r.get("price") for r in rows if is_eligible(key, r) and r.get("price")]
        cat_stats[key] = {"title": meta["title"], "count": len(rows),
                          "from": min(prices) if (prices and prices_are_recent) else None}

    return render_template("index.html", info=info, top_cpu=top_cpu, top_gpu=top_gpu,
                           newest_deal=newest_deal,
                           top_mem=top_mem, top_stor=top_stor, top_psu=top_psu,
                           cat_stats=cat_stats, cats=CATS,
                           prices_are_recent=prices_are_recent, data_age_days=age_days)

@app.route("/category/<cat>")
def category(cat):
    if cat not in CATS:
        return redirect(url_for("index"))
    return render_template("category.html", cat=cat, meta=CATS[cat], cats=CATS)

def _sort_key(v):
    if v is None:
        return None
    if isinstance(v, dict):
        for k in ("default", "max", "min"):
            if isinstance(v.get(k), (int, float)):
                return (0, float(v[k]))
        return None
    if isinstance(v, (int, float)):
        return (0, float(v))
    return (1, str(v).lower())

@app.route("/api/data/<cat>")
def api_data(cat):
    if cat not in CATS:
        return jsonify({"error": "unknown category"}), 404
    rows = _rows(cat)
    if request.args.get("eligible") == "1":
        rows = [r for r in rows if is_eligible(cat, r)]
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
                rows = [r for r in rows if str(r.get(col)).lower() == str(val).lower()]
    sort = request.args.get("sort", "value")
    order = request.args.get("order", "desc")
    reverse = order == "desc"
    keyed = [(r, _sort_key(r.get(sort))) for r in rows]
    non_null = [(r, k) for r, k in keyed if k is not None]
    nulls = [r for r, k in keyed if k is None]
    non_null.sort(key=lambda t: t[1], reverse=reverse)
    rows_sorted = [r for r, _ in non_null] + nulls

    try:
        offset = max(0, int(request.args.get("offset", 0)))
        limit = max(1, min(100000, int(request.args.get("limit", 200))))
    except ValueError:
        offset, limit = 0, 200
    page = rows_sorted[offset:offset+limit]
    return jsonify({"total": len(rows_sorted), "rows": page, "cat": cat})

@app.route("/api/meta/<cat>")
def api_meta(cat):
    if cat not in CATS:
        return jsonify({"error": "unknown"}), 404
    rows = _rows(cat)
    # distinct values for some fields
    meta = {}
    for col in ("brand", "storage_type", "efficiency", "module_type", "form_factor", "socket", "panel_type"):
        from collections import Counter
        c = Counter(str(r.get(col)) for r in rows if r.get(col) not in (None, ""))
        # keep values that appear at least 5 times, sorted by frequency then name
        vals = [v for v, n in c.most_common() if n >= 5]
        vals = sorted(set(vals))
        if vals:
            meta[col] = vals
    return jsonify(meta)

def _authorized(request):
    """Fail closed: require the configured token, or explicit local opt-in."""
    expected = os.environ.get("SCRAPE_TOKEN")
    if expected:
        token = request.headers.get("X-Scrape-Token") or request.form.get("token")
        return token == expected
    # No token configured. Never trust a proxied 127.0.0.1 address on a public
    # host; require an explicit local opt-in instead.
    if os.environ.get("ENABLE_REFRESH") != "1":
        return False
    return request.remote_addr in ("127.0.0.1", "::1", "localhost")

@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    if not _authorized(request):
        return "forbidden", 403
    get_data(force=True, region=_region())
    return jsonify({"started": True})

@app.route("/refresh", methods=["POST"])
def refresh():
    if not _authorized(request):
        return "forbidden", 403
    get_data(force=True, region=_region())
    return redirect(request.referrer or url_for("index"))

@app.route("/install")
def install():
    return render_template("install.html", cats=CATS)

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

PC_PART_KEYWORDS = ["ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra", "processor", "cpu", "graphics card", "gpu", "geforce", "radeon", "rtx", "gtx", "rx 6", "rx 7", "rx 9", "motherboard", "ddr4", "ddr5", "ssd", "nvme", "hard drive", "hdd", "power supply", "psu", "cpu cooler", "aio cooler", "liquid cooler", "thermal paste", "pc case", "monitor", "keyboard", "mouse", "headphones", "headset", "speaker", "webcam", "network adapter", "wifi", "bluetooth", "ups", "battery backup", "sound card", "external storage", "external drive", "ram", "memory", "router", "mesh wifi", "surge protector"]

_deals_cache = {"at": 0.0, "data": [], "loading": False}
_deals_lock = _threading.Lock()
SYSTEM_KEYWORDS = ["lifepo4", "solar panel", "solar generator", "power station", "inverter", "car battery", "marine battery", "12v battery", "trolling motor", "gaming a16", "gaming a18", "rog zephyrus", "rog flow", "tuf gaming a1", "tuf gaming f1", "apple m4", "apple m5", "unified memory", "handheld", "anbernic", "emulator", "retro handheld", "game console", "raspberry pi", "office chair", "gaming chair", "desk", "baby", "infant", "toddler", "nursery", "stroller", "toothbrush", "flosser", "hair dryer", "flat iron", "curling iron", "shaver", "epilator", "handbag", "backpack", "luggage", "duvet", "comforter", "pillowcase", "slipper", "slippers", "laptop", "notebook", "chromebook", "macbook", "mac mini", "mac pro", "imac", "prebuilt", "gaming pc", "desktop computer", "desktop pc", "desktop w/", "desktop:", "all-in-one", "thinkpad", "omnibook", "aspire", "yoga", "nitro", "swift", "predator", "helios", "aegis", "loq", "alienware", "omen", "victus", "legion", "ideapad", "thinkcentre", "optiplex", "vostro", "latitude", "precision", "surface", "lego", "soup", "chowder", "clam", "grocery", "pantry", "drill", "mattress", "smartwatch", "filament", "picture frame", "phone", "tablet", "mini pc", "car refrigerator", "portable fridge", "refrigerator", "beverage", "scanner", "soft-sided", "soft cooler", "hard cooler", "can cooler", "ozark", "trail", "insulated", "removable hard liner", "marine cooler", "3d", "printer", "marine cooler", "soft cooler", "hard cooler", "cooler cup", "mini fridge", "wine cooler", "insulated", "liquid death", "coleman", "stanley", "aurora", "dog", "cat", "pet", "puppy", "kitten", "feeder", "food", "dispenser", "bowl", "fish", "bird", "animal", "poultry", "livestock", "hamster", "rabbit", "reptile", "aquarium", "terrarium", "cage", "kennel", "litter", "groom", "leash", "collar", "treat", "molly", "cody", "disney", "minnie", "mickey", "earring", "earrings", "jewelry", "jewellery", "rhinestone", "necklace", "bracelet", "pendant", "brooch", "hoop earring", "mousetrap", "mouse trap", "rodent", "pest", "toy", "plush", "doll", "collectible", "costume", "cosplay", "apparel", "clothing", "shirt", "hoodie", "beanie", "headwear", "wearable", "sneakers", "boots", "sandals", "perfume", "makeup", "cosmetic", "skincare", "grill", "smoker", "pellet", "charcoal", "bbq", "barbecue", "pit boss", "air fryer", "pressure cooker", "slow cooker", "coffee maker", "espresso", "blender", "toaster", "microwave", "oven", "stove", "dishwasher", "vacuum", "lawn mower", "trimmer", "leaf blower", "generator", "patio", "furniture", "sofa", "mattress", "pillow", "blanket", "curtain", "rug", "lamp", "light bulb", "ceiling fan", "heater", "air conditioner", "humidifier", "dehumidifier", "appliance", "floor-standing", "floorstanding", "floor standing", "home theater", "home cinema", "home audio", "hi-fi", "hifi", "soundbar", "av receiver", "tower speaker", "portable speaker", "waterproof speaker", "outdoor speaker", "bluetooth speaker", "carabiner", "security camera", "surveillance", "cctv", "ip camera", "doorbell", "dashcam", "dash cam", "dash camera", "trail camera", "action camera", "nvr", "poe camera", "security cam", "reolink", "docking station", "displaylink", "usb-c dock", "usb dock", "usb docking", "usb hub", "thunderbolt dock", "projector", "carplay", "android auto", "car adapter", "blood glucose", "glucose", "co2", "air quality", "humidity", "blood pressure", "heart rate", "oximeter", "thermometer", "woodworking", "ryobi", "cordless router", "trim router", "plunge router", "compact router", "wallet", "rfid", "credit card", "card holder"]

def _has_negative_keyword(low):
    """Match negative keywords on word boundaries.

    Substring matching used to reject "Ryzen 9800X3D" because it contains
    "3d", and "headphones" because it contains "phone". Boundaries keep the
    filters precise without losing the broad phrases.
    """
    for word in SYSTEM_KEYWORDS:
        if _re.search(r"(?<![a-z0-9])" + _re.escape(word) + r"(?![a-z0-9])", low):
            return True
    return False


def _is_pc_part(title):
    low = title.lower()
    if _has_negative_keyword(low):
        return False
    has_pc = any(k in low for k in PC_PART_KEYWORDS)
    # PC cases are often titled just "Case"; require a case-like qualifier so
    # things like "case of 8" don't slip through.
    case_qualifiers = ("tower", "atx", "itx", "matx", "eatx", "pc case", "computer case",
                       "chassis", "tempered glass", "airflow", "mid-tower", "full-tower")
    if "case" in low and any(q in low for q in case_qualifiers):
        has_pc = True
    if not has_pc:
        return False
    # "power supply" is a common false positive (e.g. pet feeders, gadgets
    # that merely mention a dual power supply). Only treat it as a PC part
    # when the title actually looks like a power supply, unless another PC
    # keyword is also present.
    psu_terms = ("power supply", "psu")
    if any(t in low for t in psu_terms):
        other_pc = any(k in low for k in PC_PART_KEYWORDS if k not in psu_terms)
        if not other_pc:
            if not (_re.search(r"\d+\s*w\b", low)
                    or any(tok in low for tok in ("atx", "sfx", "modular", "80+", "80 plus",
                                                  "bronze", "gold", "platinum", "titanium",
                                                  "semi-modular", "full modular"))):
                return False
    return True

def _parse_price(title):
    m = _re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", title)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None

DEAL_CAT_RULES = [
    ("thermal_paste", ["thermal paste", "thermal compound", "thermal grease", "thermal putty"]),
    ("cooler", ["cpu cooler", "aio cooler", "liquid cooler", "air cooler", "water cooler",
                "cpu fan", "aio pump", "liquid cooling"]),
    ("external_storage", ["nas", "network attached storage", "4-bay", "2-bay", "terramaster", "synology", "qnap",
                          "drive enclosure", "hard drive enclosure", "external storage",
                          "external drive", "external ssd", "external hdd"]),
    ("cpu", ["ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra", "processor", "cpu"]),
    ("gpu", ["graphics card", "gpu", "geforce", "radeon", "rtx", "gtx", "rx 6", "rx 7", "rx 9"]),
    ("memory", ["ddr4", "ddr5", "ram", "memory"]),
    ("storage", ["ssd", "nvme", "hard drive", "hdd"]),
    ("psu", ["power supply", "psu"]),
    ("motherboard", ["motherboard"]),
    ("cooler", ["cooler", "thermal paste"]),
    ("case", ["pc case", "computer case", "tower case", "mid tower", "mid-tower", "mini tower", "full-tower", "atx case", "matx", "itx", "chassis"]),
    ("monitor", ["monitor"]),
    ("keyboard", ["keyboard"]),
    ("mouse", ["mouse"]),
    ("headphones", ["headphones", "headset", "earbuds"]),
    ("speakers", ["speaker"]),
    ("webcam", ["webcam"]),
    ("router", ["router", "mesh wifi", "mesh system", "wi-fi 7 router", "wi-fi 6 router"]),
    ("network", ["network adapter", "wifi", "wi-fi", "bluetooth adapter"]),
    ("surge_protector", ["surge protector", "surge strip", "power strip", "surge suppression"]),
    ("ups", ["ups", "battery backup", "uninterruptible"]),
    ("sound", ["sound card"]),
    ("external_storage", ["external storage", "external drive", "external ssd", "external hdd"]),
]


def _deal_category(title):
    low = (title or "").lower()
    for cat, kws in DEAL_CAT_RULES:
        if any(k in low for k in kws):
            return cat
    return "other"


DEAL_MERCHANTS = [
    "Amazon", "Newegg", "Best Buy", "B&H", "Walmart", "Target", "Micro Center", "Microcenter",
    "Adorama", "Dell", "Lenovo", "HP", "eBay", "Costco", "Samsung", "Monoprice",
    "Corsair", "Logitech", "Razer", "Newegg Business",
]


def _canonical_deal_key(link):
    """Ignore tracking parameters so the same deal is only listed once."""
    try:
        parts = urlsplit(link)
    except ValueError:
        return (link or "").strip().lower()
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = (parts.path or "").rstrip("/").lower()
    return host + path


def _deal_merchant(title, desc=""):
    text = f"{title} {desc}"
    for name in DEAL_MERCHANTS:
        if _re.search(r"\b" + _re.escape(name) + r"\b", text, _re.I):
            return name
    return "Slickdeals"


def _deal_image(desc):
    m = _re.search(r'<img[^>]+src=["\'](https://[^"\']+)["\']', desc or "", _re.I)
    if m:
        return m.group(1).replace("&amp;", "&")
    m = _re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://[^"\']+)["\']', desc or "", _re.I)
    return m.group(1).replace("&amp;", "&") if m else None


def _deal_model_key(title, price):
    """Catch the same listing reposted with a different title/link.

    Only distinctive model tokens are used, never common spec tokens such as
    "rtx5070" or "ddr5", so two different cards at the same price are kept.
    """
    if price is None:
        return None
    spec = _re.compile(r"^(?:rtx|gtx|rx|arc|ddr|pcie|atx|wifi|gen|usb|hdmi|dp)\d", _re.I)
    candidates = []
    for token in _re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{3,}", title or ""):
        low = token.lower()
        if not (_re.search(r"[a-z]", low) and _re.search(r"\d", low)):
            continue
        if _re.fullmatch(r"\d+x\d+", low) or spec.match(low) or _re.fullmatch(r"\d+(?:gb|tb|hz|w|mm)", low):
            continue
        candidates.append(low)
    if not candidates:
        return None
    model = max(candidates, key=len)
    if len(model) < 5:
        return None
    return f"model|{_deal_category(title)}|{model}|{round(float(price), 2)}"


def _deal_title_key(title, price):
    text = _re.sub(r"\$[\d,.]+", " ", (title or "").lower())
    text = " ".join(_re.sub(r"[^a-z0-9]+", " ", text).split()[:14])
    if not text:
        return None
    return f"title|{text}|{round(float(price), 2) if price is not None else 'na'}"


def _refresh_deals():
    global _deals_cache
    deals = []
    seen = {}
    queries = ["cpu", "gpu", "ssd", "motherboard", "power supply", "cooler", "ram",
               "monitor", "keyboard", "mouse", "headphones", "case", "network adapter",
               "wifi", "router", "ups", "sound card", "webcam", "speakers", "external storage",
               "external drive", "thermal paste", "surge protector"]
    for q in queries:
        url = "https://slickdeals.net/newsearch.php?src=SearchBarV2&q=" + q.replace(" ", "+") + "&searcharea=deals&searchin=first&rss=1"
        try:
            import requests
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=5)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            if not (link.startswith("http://") or link.startswith("https://")):
                continue
            if not _is_pc_part(title):
                continue
            price = _parse_price(title) or _parse_price(desc)
            link_key = _canonical_deal_key(link)
            title_key = _deal_title_key(title, price)
            model_key = _deal_model_key(title, price)
            if link_key in seen:
                existing = deals[seen[link_key]]
                if price and not existing.get("price"):
                    existing.update({"price": price, "desc": desc or existing.get("desc"),
                                     "image": existing.get("image") or _deal_image(desc),
                                     "pubDate": pub or existing.get("pubDate")})
                continue
            if (title_key and title_key in seen) or (model_key and model_key in seen):
                continue
            seen[link_key] = len(deals)
            if title_key:
                seen[title_key] = len(deals)
            if model_key:
                seen[model_key] = len(deals)
            deals.append({
                "title": title,
                "link": link,
                "desc": desc,
                "pubDate": pub,
                "price": price,
                "cat": _deal_category(title),
                "merchant": _deal_merchant(title, desc),
                "image": _deal_image(desc),
            })
    _deals_cache = {"at": _time.time(), "data": deals, "loading": False}


def fetch_deals(sort="newest", cat=None):
    # Serve cached deals immediately; refresh in the background so a cold
    # start can never block the page on Slickdeals requests.
    if not _deals_cache["data"] or (_time.time() - _deals_cache["at"]) > 600:
        with _deals_lock:
            if not _deals_cache.get("loading"):
                _deals_cache["loading"] = True
                _threading.Thread(target=_refresh_deals, daemon=True).start()
    deals = list(_deals_cache["data"])

    def when(d):
        return _as_datetime(d.get("pubDate")) or datetime.min.replace(tzinfo=timezone.utc)

    if cat and cat not in ("", "all", None):
        deals = [d for d in deals if d.get("cat") == cat]
    if sort == "oldest":
        deals.sort(key=when)
    elif sort == "price_asc":
        deals.sort(key=lambda d: (d.get("price") is None, d.get("price") or 0))
    elif sort == "price_desc":
        deals.sort(key=lambda d: (d.get("price") is None, -(d.get("price") or 0)))
    else:  # newest
        deals.sort(key=when, reverse=True)
    return deals[:240]


@app.route("/deals")
def deals():
    sort = request.args.get("sort", "newest")
    cat = request.args.get("cat", "all")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 24
    all_deals = fetch_deals(sort, cat)
    total = len(all_deals)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    return render_template("deals.html", deals=all_deals[(page - 1) * per_page:page * per_page],
                           sort=sort, cat=cat, cats=CATS, page=page, pages=pages, total=total,
                           per_page=per_page, deals_updated=_deals_cache.get("at"),
                           deals_loading=bool(_deals_cache.get("loading")))

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", cats=CATS)


@app.route("/methodology")
def methodology():
    return render_template("methodology.html", cats=CATS)

@app.route("/ads.txt")
def ads_txt():
    pub = os.environ.get("ADSENSE_CLIENT", "ca-pub-2012616805883507").replace("ca-pub-", "pub-")
    body = f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n"
    return Response(body, mimetype="text/plain")

@app.route("/compat")
def compat():
    return render_template("compat.html", cats=CATS)

@app.route("/watchlist")
def watchlist():
    return render_template("watchlist.html", cats=CATS)

def _part_spec(cat, r):
    """Short human-readable specs for leaderboard rows."""
    def add(v):
        if v not in (None, "", 0):
            bits.append(str(v))
    bits = []
    name = r.get("name") or ""
    if cat == "cpu":
        m = _re.search(r"Ryzen [3579] (\d)(\d{3})", name, _re.I)
        if m:
            add("Ryzen " + m.group(1) + "000")
        else:
            m = _re.search(r"Core (?:Ultra )?[579] (\d{3})", name, _re.I)
            if m:
                add("Core Ultra " + m.group(1)[0] + "00")
            else:
                m = _re.search(r"Core i[3579]-(\d{4,5})", name, _re.I)
                if m:
                    d = m.group(1)
                    add((d[:2] if len(d) == 5 else d[0]) + "th gen")
        add(r.get("socket"))
        if r.get("cores"):
            add(str(r["cores"]) + "C/" + str(r.get("threads") or "?") + "T")
        if r.get("tdp"):
            add(str(r["tdp"]) + "W")
    elif cat == "gpu":
        m = _re.search(r"(RTX|GTX)\s*(\d{2})\d{2}", name, _re.I)
        if m:
            add(m.group(1).upper() + " " + m.group(2) + " series")
        m = _re.search(r"RX\s*(\d)\d{3}", name, _re.I)
        if m:
            add("RX " + m.group(1) + "000 series")
        if r.get("vram_gb"):
            add(str(r["vram_gb"]) + "GB VRAM")
        if r.get("length"):
            add(str(r["length"]) + "mm")
    elif cat == "motherboard":
        add(r.get("socket"))
        add(board_ram_type(r))
        add(r.get("form_factor"))
        if r.get("ram_slots"):
            add(str(r["ram_slots"]) + " slots")
        if r.get("max_ram_gb"):
            add("max " + str(r["max_ram_gb"]) + "GB")
    elif cat == "memory":
        add(r.get("module_type"))
        if r.get("capacity_gb"):
            add(str(r["capacity_gb"]) + "GB")
        if r.get("speed_ghz"):
            add(str(r["speed_ghz"]) + "GHz")
        if r.get("cas_timing"):
            add("CL" + str(r["cas_timing"]))
    elif cat == "storage":
        add(r.get("storage_type"))
        if r.get("capacity_gb"):
            add(str(r["capacity_gb"]) + "GB")
        add(r.get("interface"))
    elif cat == "psu":
        if r.get("wattage"):
            add(str(r["wattage"]) + "W")
        add(r.get("efficiency"))
        add(r.get("modular"))
    elif cat == "case":
        add(r.get("form_factor"))
        add(r.get("color"))
    elif cat == "cooler":
        if r.get("radiator_size"):
            add(str(r["radiator_size"]) + "mm")
        if r.get("decibels"):
            add(str(r["decibels"]) + "dB")
    elif cat == "monitor":
        if r.get("size"):
            add(str(r["size"]) + '"')
        add(r.get("resolution"))
        if r.get("refresh_rate"):
            add(str(r["refresh_rate"]) + "Hz")
        add(r.get("panel_type"))
    elif cat == "keyboard":
        add(r.get("style"))
        add(r.get("switches"))
        add(r.get("connection"))
    elif cat == "mouse":
        add(r.get("tracking"))
        add(r.get("connection"))
        if r.get("max_dpi"):
            add(str(r["max_dpi"]) + " DPI")
    elif cat == "headphones":
        add(r.get("form_factor"))
        add("Wireless" if r.get("is_wireless") else "Wired")
    elif cat == "network":
        add(r.get("protocol"))
        add(r.get("interface"))
    elif cat == "router":
        add(r.get("wireless_standard"))
        add(r.get("bands"))
        add(r.get("speed"))
        add(r.get("ports"))
    elif cat == "ups":
        if r.get("capacity_va"):
            add(str(r["capacity_va"]) + "VA")
        if r.get("capacity_w"):
            add(str(r["capacity_w"]) + "W")
    elif cat == "sound":
        add(r.get("channels"))
        add(r.get("snr"))
        add(r.get("sample_rate"))
        add(r.get("interface"))
    elif cat == "webcam":
        add(r.get("resolution"))
        add(r.get("connection"))
    elif cat == "speakers":
        add(r.get("configuration"))
        add(r.get("total_wattage"))
        add(r.get("frequency_response"))
    elif cat == "external_storage":
        add(r.get("type"))
        add(r.get("interface"))
        if r.get("capacity_gb"):
            add(str(r["capacity_gb"]) + "GB")
    elif cat == "surge_protector":
        if r.get("outlets"):
            add(str(r["outlets"]) + " outlets")
        if r.get("joule_rating"):
            add(str(r["joule_rating"]) + "J")
    elif cat == "thermal_paste":
        add(r.get("brand"))
    return " · ".join(bits) if bits else "—"


@app.route("/leaderboard")
def leaderboard():
    cache = get_data(region=_region())
    boards = {}
    if cache:
        for cat, meta in CATS.items():
            rows = [r for r in (cache.get(meta["key"], []) or []) if is_eligible(cat, r) and r.get("value")]
            rows.sort(key=lambda r: r.get("value") or 0, reverse=True)
            boards[cat] = (meta, [dict(r, _spec=_part_spec(cat, r)) for r in rows[:15]])
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

@app.route("/sw.js")
def service_worker():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, "static"), "sw.js", mimetype="application/javascript")

@app.route("/api/status")
def api_status():
    return jsonify({"scraping": is_scraping()})

@app.route("/api/history")
def api_history():
    cat = request.args.get("cat", "")
    name = request.args.get("name", "")
    if not cat or not name:
        return jsonify({"history": []})
    return jsonify({"history": get_price_history(cat, name, _region())})

@app.route("/api/liveprice")
def api_liveprice():
    return jsonify({"price": None, "note": "Live retailer prices are not available. Use the retailer links shown in the table."}), 410

PLACEHOLDER_LABELS = {"cpu": "CPU", "gpu": "GPU", "memory": "RAM", "storage": "SSD", "psu": "PSU",
                      "motherboard": "BOARD", "case": "CASE", "cooler": "COOLER", "prebuilt": "PC",
                      "monitor": "MONITOR", "keyboard": "KEYS", "mouse": "MOUSE", "headphones": "AUDIO",
                      "network": "NET", "ups": "UPS", "sound": "SND", "webcam": "CAM", "speakers": "SPK", "external_storage": "EXT", "router": "RTR", "thermal_paste": "TP", "surge_protector": "SRG"}

@app.route("/api/image")
def api_image():
    q = request.args.get("q", "").strip()[:200]
    link = request.args.get("link", "").strip() or None
    cat = request.args.get("cat", "")
    if not q:
        return ("", 204)
    url = find_photo(q, link)
    if url:
        return redirect(url, code=302)
    return redirect(url_for("api_placeholder", cat=cat), code=302)

@app.route("/api/placeholder")
def api_placeholder():
    label = PLACEHOLDER_LABELS.get(request.args.get("cat", ""), "PART")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
           '<rect width="96" height="96" rx="8" fill="#0f172a"/>'
           '<text x="48" y="54" text-anchor="middle" font-family="Arial,sans-serif" '
           'font-size="15" font-weight="700" fill="#64748b">' + label + '</text></svg>')
    return Response(svg, mimetype="image/svg+xml")

@app.route("/api/autobuild")
def api_autobuild():
    try:
        budget = float(request.args.get("budget", "1000"))
    except ValueError:
        return jsonify({"ok": False, "message": "Budget must be a number."}), 400
    if budget < 300 or budget > 10000:
        return jsonify({"ok": False, "message": "Choose a budget between 300 and 10,000."}), 400
    cache = get_data(region=_region()) or {}
    return jsonify(build_within_budget(cache, budget))

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

@app.route("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    urls = ["/", "/deals", "/build", "/compat", "/watchlist", "/leaderboard", "/guide/best-budget-gaming-pc", "/install", "/methodology", "/sources"]
    for k in CATS:
        urls.append("/category/" + k)
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        body.append("  <url><loc>%s%s</loc></url>" % (base, u))
    body.append("</urlset>")
    return Response("\n".join(body), mimetype="application/xml")


@app.route("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    return Response("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % base, mimetype="text/plain")


@app.route("/guide/best-budget-gaming-pc")
def guide_budget():
    return render_template("guide_budget.html", cats=CATS)


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    # There is no email provider wired up yet. Do not collect addresses we
    # cannot deliver to, and do not promise a digest that will never arrive.
    return jsonify({
        "ok": False,
        "message": "Email alerts are not available yet. Use the watchlist or check the deals page for now.",
    }), 503


if __name__ == "__main__":
    # trigger background scrape (non-blocking)
    get_data(region="us")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
