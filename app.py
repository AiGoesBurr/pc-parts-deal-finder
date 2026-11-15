import csv, io, os, re
import urllib.request
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for

from cache import get_data, cache_info

app = Flask(__name__)

CATS = {
    "cpu": {"key": "cpus", "title": "CPUs", "value_col": "value", "value_label": "CPU Value (Mark/$)"},
    "gpu": {"key": "gpus", "title": "GPUs", "value_col": "value", "value_label": "GPU Value (Score/$)"},
    "memory": {"key": "memory", "title": "Memory (RAM)", "value_col": "value", "value_label": "Value (1/$ per GB)"},
    "storage": {"key": "storage", "title": "Storage (SSD/HDD)", "value_col": "value", "value_label": "Value (1/$ per GB)"},
    "psu": {"key": "psu", "title": "Power Supplies", "value_col": "value", "value_label": "Value (W/$)"},
    "motherboard": {"key": "motherboard", "title": "Motherboards", "value_col": "value", "value_label": "Value (1/$)"},
    "case": {"key": "case", "title": "Cases", "value_col": "value", "value_label": "Value (1/$)"},
    "cooler": {"key": "cooler", "title": "CPU Coolers", "value_col": "value", "value_label": "Value (1/$)"},
}

def _rows(cat):
    cache = get_data()
    key = CATS[cat]["key"]
    return cache.get(key, []) if cache else []

@app.route("/")
def index():
    cache = get_data()
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
    get_data(force=True)
    return redirect(request.referrer or url_for("index"))

@app.route("/sources")
def sources():
    info = cache_info(get_data())
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

PC_PART_KEYWORDS = ["ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra", "processor", "cpu", "graphics card", "gpu", "geforce", "radeon", "rtx", "gtx", "rx 6", "rx 7", "rx 9", "motherboard", "ddr4", "ddr5", "ssd", "nvme", "hard drive", "hdd", "power supply", "psu", "cooler", "thermal paste", "pc case"]
SYSTEM_KEYWORDS = ["laptop", "notebook", "chromebook", "macbook", "mac mini", "mac pro", "imac", "prebuilt", "gaming pc", "desktop computer", "desktop pc", "desktop w/", "desktop:", "all-in-one", "thinkpad", "omnibook", "aspire", "yoga", "nitro", "swift", "predator", "helios", "aegis", "loq", "alienware", "omen", "victus", "legion", "ideapad", "thinkcentre", "optiplex", "vostro", "latitude", "precision", "surface", "monitor", "keyboard", "mouse", "headset", "speaker", "webcam", "lego", "drill", "mattress", "smartwatch", "earbuds", "filament", "picture frame", "phone", "tablet", "mini pc", "car refrigerator", "portable fridge", "refrigerator", "beverage", "marine cooler", "soft cooler", "hard cooler", "cooler cup", "mini fridge", "wine cooler", "insulated", "liquid death", "coleman", "stanley", "aurora"]

def _is_pc_part(title):
    low = title.lower()
    if any(x in low for x in SYSTEM_KEYWORDS):
        return False
    return any(k in low for k in PC_PART_KEYWORDS)

def fetch_deals():
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
            if not title or link in seen:
                continue
            if not _is_pc_part(title):
                continue
            seen.add(link)
            deals.append({"title": title, "link": link, "desc": desc})
    return deals[:40]

@app.route("/deals")
def deals():
    return render_template("deals.html", deals=fetch_deals(), cats=CATS)

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
    # warm cache
    try:
        get_data()
    except Exception as e:
        print("warm cache failed:", e)
    app.run(host="0.0.0.0", port=5000, debug=False)
