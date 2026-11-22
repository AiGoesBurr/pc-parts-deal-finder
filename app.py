import csv, gzip, io, os, logging, json as _json2, threading as _threading
logger = logging.getLogger("pcparts.app")
import xml.etree.ElementTree as ET
from flask import Flask, g, render_template, request, jsonify, Response, redirect, url_for, has_request_context

from cache import get_data, cache_info, get_price_history, is_scraping, REGION_CURRENCY
from images import find_photo
from ranking import is_eligible, board_ram_type, cpu_socket
from autobuild import build_within_budget

app = Flask(__name__)

VISITOR_FILE = os.environ.get("VISITOR_FILE") or os.path.join(os.path.dirname(__file__), "data", "visitors.json")
_visitor_lock = _threading.Lock()


def _visitor_count(increment=False):
    # Optional external store (e.g. Upstash Redis) for persistence across
    # ephemeral deploys. Configure with UPSTASH_REDIS_REST_URL and
    # UPSTASH_REDIS_REST_TOKEN. Falls back to a local file otherwise.
    upstash_url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
    upstash_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if upstash_url and upstash_token:
        try:
            import requests as _rq
            headers = {"Authorization": f"Bearer {upstash_token}"}
            if increment:
                r = _rq.post(upstash_url + "/incr/visitors", headers=headers, timeout=5)
            else:
                r = _rq.get(upstash_url + "/get/visitors", headers=headers, timeout=5)
            r.raise_for_status()
            val = r.json().get("result")
            if val is None:
                return 0
            return int(val)
        except Exception:
            pass  # fall through to local file
    with _visitor_lock:
        try:
            with open(VISITOR_FILE, encoding="utf-8") as f:
                n = int(_json2.load(f).get("count", 0))
        except (OSError, ValueError, AttributeError):
            n = 0
        if increment:
            n += 1
            try:
                os.makedirs(os.path.dirname(VISITOR_FILE), exist_ok=True)
                tmp = VISITOR_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    _json2.dump({"count": n}, f)
                os.replace(tmp, VISITOR_FILE)
            except OSError:
                pass
        return n

@app.after_request
def _set_visitor_cookie(response):
    try:
        if getattr(g, "_set_vcount", False):
            response.set_cookie("vcount", "1", max_age=30*86400, samesite="Lax")
    except Exception:
        pass
    return response


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
    inc = not bool(request.cookies.get("vcount"))
    if inc and has_request_context():
        g._set_vcount = True
    return {"region": reg, "currency_symbol": sym,
            "is_local": has_request_context() and request.remote_addr in ("127.0.0.1", "::1", "localhost"),
            "visitor_count": _visitor_count(increment=inc),
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
    region = request.args.get("region", "us") if has_request_context() else "us"
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
    # top picks
    def top(key, cat, n=6):
        rows = cache.get(key, []) if cache else []
        rows = [r for r in rows if is_eligible(cat, r) and r.get("value")]
        rows.sort(key=lambda r: r.get("value") or 0, reverse=True)
        return rows[:n]
    top_cpu = top("cpus", "cpu")
    top_gpu = top("gpus", "gpu")
    # best by benchmark score, among current parts (price not required)
    best_cpu = [r for r in (cache.get("cpus", []) if cache else []) if r.get("mark") is not None]
    best_cpu.sort(key=lambda r: r.get("mark") or 0, reverse=True)
    best_gpu = [r for r in (cache.get("gpus", []) if cache else []) if r.get("score") is not None]
    best_gpu.sort(key=lambda r: r.get("score") or 0, reverse=True)
    # newest deal
    try:
        newest_deal = (fetch_deals("newest") or [None])[0]
    except Exception:
        newest_deal = None
    # memory/storage/psu best by price, among current priced parts only
    mem = [r for r in (cache.get("memory", []) if cache else []) if is_eligible("memory", r) and r.get("price_per_gb")]
    mem.sort(key=lambda r: r["price_per_gb"])
    stor = [r for r in (cache.get("storage", []) if cache else []) if is_eligible("storage", r) and r.get("price_per_gb")]
    stor.sort(key=lambda r: r["price_per_gb"])
    psu = [r for r in (cache.get("psu", []) if cache else []) if is_eligible("psu", r) and r.get("price_per_watt")]
    psu.sort(key=lambda r: r["price_per_watt"])
    return render_template("index.html", info=info, top_cpu=top_cpu, top_gpu=top_gpu,
                           best_cpu=best_cpu[:5], best_gpu=best_gpu[:5],
                           newest_deal=newest_deal,
                           top_mem=mem[:6], top_stor=stor[:6], top_psu=psu[:6], cats=CATS)

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
                rows = [r for r in rows if str(r.get(col)) == val]
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
    for col in ("brand", "storage_type", "efficiency", "module_type", "form_factor", "socket"):
        from collections import Counter
        c = Counter(str(r.get(col)) for r in rows if r.get(col) not in (None, ""))
        # keep values that appear at least 5 times, sorted by frequency then name
        vals = [v for v, n in c.most_common() if n >= 5]
        vals = sorted(set(vals))
        if vals:
            meta[col] = vals
    return jsonify(meta)

def _authorized(request):
    """Fail closed: require the configured token, allowing only local requests when none is set."""
    expected = os.environ.get("SCRAPE_TOKEN")
    if not expected:
        return request.remote_addr in ("127.0.0.1", "::1", "localhost")
    token = request.headers.get("X-Scrape-Token") or request.form.get("token")
    return token == expected

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
SYSTEM_KEYWORDS = ["laptop", "notebook", "chromebook", "macbook", "mac mini", "mac pro", "imac", "prebuilt", "gaming pc", "desktop computer", "desktop pc", "desktop w/", "desktop:", "all-in-one", "thinkpad", "omnibook", "aspire", "yoga", "nitro", "swift", "predator", "helios", "aegis", "loq", "alienware", "omen", "victus", "legion", "ideapad", "thinkcentre", "optiplex", "vostro", "latitude", "precision", "surface", "lego", "soup", "chowder", "clam", "grocery", "pantry", "drill", "mattress", "smartwatch", "filament", "picture frame", "phone", "tablet", "mini pc", "car refrigerator", "portable fridge", "refrigerator", "beverage", "scanner", "soft-sided", "soft cooler", "hard cooler", "can cooler", "ozark", "trail", "insulated", "removable hard liner", "marine cooler", "3d", "printer", "marine cooler", "soft cooler", "hard cooler", "cooler cup", "mini fridge", "wine cooler", "insulated", "liquid death", "coleman", "stanley", "aurora", "dog", "cat", "pet", "puppy", "kitten", "feeder", "food", "dispenser", "bowl", "fish", "bird", "animal", "poultry", "livestock", "hamster", "rabbit", "reptile", "aquarium", "terrarium", "cage", "kennel", "litter", "groom", "leash", "collar", "treat", "molly", "cody", "disney", "minnie", "mickey", "earring", "earrings", "jewelry", "jewellery", "rhinestone", "necklace", "bracelet", "pendant", "brooch", "hoop earring", "mousetrap", "mouse trap", "rodent", "pest", "toy", "plush", "doll", "collectible", "costume", "cosplay", "apparel", "clothing", "shirt", "hoodie", "sneakers", "boots", "sandals", "perfume", "makeup", "cosmetic", "skincare", "grill", "smoker", "pellet", "charcoal", "bbq", "barbecue", "pit boss", "air fryer", "pressure cooker", "slow cooker", "coffee maker", "espresso", "blender", "toaster", "microwave", "oven", "stove", "dishwasher", "vacuum", "lawn mower", "trimmer", "leaf blower", "generator", "patio", "furniture", "sofa", "mattress", "pillow", "blanket", "curtain", "rug", "lamp", "light bulb", "ceiling fan", "heater", "air conditioner", "humidifier", "dehumidifier", "appliance", "floor-standing", "floorstanding", "floor standing", "home theater", "home cinema", "home audio", "hi-fi", "hifi", "soundbar", "av receiver", "tower speaker", "security camera", "surveillance", "cctv", "ip camera", "doorbell", "dashcam", "trail camera", "action camera", "nvr", "poe camera", "security cam", "reolink", "docking station", "displaylink", "usb-c dock", "usb dock", "usb docking", "usb hub", "thunderbolt dock"]

def _is_pc_part(title):
    low = title.lower()
    if any(x in low for x in SYSTEM_KEYWORDS):
        return False
    has_pc = any(k in low for k in PC_PART_KEYWORDS)
    # PC cases are often titled just "Case"; require a case-like qualifier so
    # things like "case of 8" don't slip through.
    case_qualifiers = ("tower", "atx", "mid", "full", "mini", "micro", "pc case",
                       "computer case", "chassis", "tempered glass", "airflow")
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

import re as _re

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
    ("external_storage", ["nas", "network attached storage", "4-bay", "2-bay",
                          "drive enclosure", "hard drive enclosure", "external storage",
                          "external drive", "external ssd", "external hdd"]),
    ("cpu", ["ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra", "processor", "cpu"]),
    ("gpu", ["graphics card", "gpu", "geforce", "radeon", "rtx", "gtx", "rx 6", "rx 7", "rx 9"]),
    ("memory", ["ddr4", "ddr5", "ram", "memory"]),
    ("storage", ["ssd", "nvme", "hard drive", "hdd"]),
    ("psu", ["power supply", "psu"]),
    ("motherboard", ["motherboard"]),
    ("cooler", ["cooler", "thermal paste"]),
    ("case", ["pc case", " pc case", "tower case", "mid tower", "mini tower"]),
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


def _refresh_deals():
    global _deals_cache
    import time as _t
    deals = []
    seen = set()
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
            if not title or link in seen:
                continue
            if not _is_pc_part(title):
                continue
            seen.add(link)
            deals.append({"title": title, "link": link, "desc": desc, "pubDate": pub, "price": _parse_price(title), "cat": _deal_category(title)})
    _deals_cache = {"at": _t.time(), "data": deals, "loading": False}


def fetch_deals(sort="newest", cat=None):
    import time as _t
    # Serve cached deals immediately; refresh in the background so a cold
    # start can never block the page on Slickdeals requests.
    if not _deals_cache["data"] or (_t.time() - _deals_cache["at"]) > 600:
        with _deals_lock:
            if not _deals_cache.get("loading"):
                _deals_cache["loading"] = True
                _threading.Thread(target=_refresh_deals, daemon=True).start()
    deals = list(_deals_cache["data"])
    # sort (parse dates so weekday names don't scramble the order)
    from email.utils import parsedate_to_datetime
    def when(d):
        try:
            return parsedate_to_datetime(d.get("pubDate") or "")
        except Exception:
            return None
    if cat and cat not in ("", "all", None):
        deals = [d for d in deals if d.get("cat") == cat]
    if sort == "oldest":
        deals.sort(key=lambda d: (when(d) is None, when(d)))
    elif sort == "price_asc":
        deals.sort(key=lambda d: (d.get("price") is None, d.get("price") or 0))
    elif sort == "price_desc":
        deals.sort(key=lambda d: (d.get("price") is None, -(d.get("price") or 0)))
    else:  # newest
        deals.sort(key=lambda d: (when(d) is None, when(d)), reverse=True)
    return deals[:40]

@app.route("/deals")
def deals():
    sort = request.args.get("sort", "newest")
    cat = request.args.get("cat", "all")
    return render_template("deals.html", deals=fetch_deals(sort, cat), sort=sort, cat=cat, cats=CATS)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", cats=CATS)

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
    return jsonify({"price": None, "note": "Live Amazon prices need an Amazon Product Advertising API key, which isn't set up yet."})

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
    urls = ["/", "/deals", "/build", "/compat", "/watchlist", "/leaderboard", "/guide/best-budget-gaming-pc", "/install"]
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
    email = (request.form.get("email") or request.json.get("email") if request.is_json else None or "").strip().lower()
    if not email or "@" not in email or len(email) > 200:
        return jsonify({"ok": False, "message": "Enter a valid email."}), 400
    path = os.path.join(os.path.dirname(__file__), "data", "subscribers.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, encoding="utf-8") as f:
                subs = json.load(f)
        except (OSError, ValueError):
            subs = []
        if email not in subs:
            subs.append(email)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(subs, f)
            os.replace(tmp, path)
    except OSError as e:
        logger.warning("subscribe failed: %s", e)
        return jsonify({"ok": False, "message": "Could not save. Try again."}), 500
    return jsonify({"ok": True, "message": "You're on the list. Thanks!"})


if __name__ == "__main__":
    # trigger background scrape (non-blocking)
    get_data(region="us")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
