import json, os, time, threading, logging
logger = logging.getLogger("pcparts.cache")
from datetime import datetime

REGION_CURRENCY = {"us":"USD","uk":"GBP","ca":"CAD","au":"AUD","de":"EUR","fr":"EUR","es":"EUR","it":"EUR","in":"INR","nz":"NZD","ie":"EUR","be":"EUR","se":"SEK"}
CURRENCY_SYMBOL = {"USD":"$","GBP":chr(163),"CAD":"C$","AUD":"A$","EUR":chr(8364),"INR":chr(8377),"NZD":"NZ$","SEK":"kr"}
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CACHE_TTL = 10 * 60  # 10 minutes
DATA_KEYS = ("cpus","gpus","memory","storage","psu","motherboard","case","cooler","prebuilts","monitor","keyboard","mouse","headphones")

_scrape_lock = threading.Lock()
_scrape_thread = None
_fx_state = {"at": 0.0, "rates": None}


def _valid_region(region):
    return region if region in REGION_CURRENCY else "us"

def _cache_path(region="us"):
    return os.path.join(os.path.dirname(__file__), "data", f"cache_{_valid_region(region)}.json")

def _history_path(region="us"):
    return os.path.join(os.path.dirname(__file__), "data", f"price_history_{_valid_region(region)}.json")

def _ecb_rates():
    import urllib.request
    import xml.etree.ElementTree as ET
    if _fx_state["rates"] and time.time() - _fx_state["at"] < 12 * 3600:
        return _fx_state["rates"]
    with urllib.request.urlopen(ECB_URL, timeout=15) as r:
        root = ET.fromstring(r.read())
    rates = {"EUR": 1.0}
    for el in root.iter():
        cur, rate = el.attrib.get("currency"), el.attrib.get("rate")
        if cur and rate:
            rates[cur] = float(rate)
    _fx_state["rates"], _fx_state["at"] = rates, time.time()
    return rates

def _fx_rate(region):
    """Multiplier from USD to the region's currency, or None when no rate is available."""
    cur = REGION_CURRENCY.get(_valid_region(region), "USD")
    if cur == "USD":
        return 1.0
    try:
        rates = _ecb_rates()
        return rates[cur] / rates["USD"]
    except Exception:
        return None

def _ensure_dir():
    os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)

_mem_cache = {}
def load_cache(region="us"):
    region = _valid_region(region)
    p = _cache_path(region)
    if not os.path.exists(p):
        return None
    try:
        mtime = os.path.getmtime(p)
        entry = _mem_cache.get(region)
        if entry and entry[0] == mtime:
            return entry[1]
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        _mem_cache[region] = (mtime, data)
        return data
    except Exception:
        return None

def save_cache(payload, region="us"):
    region = _valid_region(region)
    _ensure_dir()
    payload["_saved_at"] = time.time()
    payload["_saved_at_iso"] = datetime.now().isoformat(timespec="seconds")
    payload["_region"] = region
    path = _cache_path(region)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def is_stale(cache):
    if not cache:
        return True
    saved = cache.get("_saved_at")
    if not saved:
        return True
    return (time.time() - saved) > CACHE_TTL

def _price_map(cache):
    m = {}
    if not cache:
        return m
    for k in DATA_KEYS:
        pm = {}
        for r in (cache.get(k) or []):
            if isinstance(r, dict) and r.get("name") and r.get("price") is not None:
                pm[r["name"]] = r.get("price")
        if pm:
            m[k] = pm
    return m

def _load_history(region="us"):
    try:
        p = _history_path(region)
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    except Exception:
        pass
    return []

def _save_history(h, region="us"):
    try:
        path = _history_path(region)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        pass

def get_price_history(cat, name, region="us"):
    h = _load_history(_valid_region(region))
    out = []
    for snap in h:
        price = (snap.get("prices", {}).get(cat, {}) or {}).get(name)
        if price is not None:
            out.append({"ts": snap.get("ts"), "price": price})
    return out

def _do_scrape(region="us"):
    global _scrape_thread
    region = _valid_region(region)
    try:
        cache = load_cache(region)
        old_prices = _price_map(cache) if cache else {}
        from scrapers.passmark import scrape_cpus, scrape_gpus
        from scrapers.pcpp import scrape_parts
        payload = {}
        try:
            payload["cpus"] = scrape_cpus()
        except Exception as e:
            payload["cpus"] = []
            payload["cpu_error"] = str(e)
        # merge core counts / socket / tdp from PCPartPicker where possible
        try:
            from scrapers.pcpp import scrape_cpu_cores
            import re
            def _norm(n):
                n = (n or "").lower()
                n = re.sub(r"@\s*[\d\.]+\s*ghz", "", n)
                n = re.sub(r"\s+", " ", n).strip()
                return n
            def _token(n):
                toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", n or "")
                cand = [t for t in toks if any(c.isdigit() for c in t)]
                return max(cand, key=len).lower() if cand else None
            pp_items = scrape_cpu_cores(region)
            core_map = {}
            socket_map = {}
            tdp_map = {}
            for item in pp_items:
                nm = _norm(item.get("name"))
                core_map[nm] = item.get("cores")
                socket_map[nm] = item.get("socket")
                tdp_map[nm] = item.get("tdp")
                t = _token(item.get("name"))
                if t:
                    core_map.setdefault(t, item.get("cores"))
                    socket_map.setdefault(t, item.get("socket"))
                    tdp_map.setdefault(t, item.get("tdp"))
            for c in payload.get("cpus", []):
                nm = _norm(c.get("name"))
                tk = _token(c.get("name"))
                if c.get("cores") is None:
                    cores = core_map.get(nm)
                    if cores is None:
                        cores = core_map.get(tk)
                    c["cores"] = cores
                if c.get("socket") is None:
                    c["socket"] = socket_map.get(nm) or socket_map.get(tk)
                if c.get("tdp") is None:
                    c["tdp"] = tdp_map.get(nm) or tdp_map.get(tk)
        except Exception as e:
            logger.warning("CPU core merge failed: %s", e)
            payload["cpu_core_error"] = str(e)
        # merge cores/threads/socket/tdp from TechPowerUp CPU specs
        try:
            from scrapers.techpowerup import scrape_cpu_cores as scrape_tp
            import re
            def _norm2(n):
                n = (n or "").lower()
                n = re.sub(r"@\s*[\d\.]+\s*ghz", "", n)
                n = re.sub(r"\s+", " ", n).strip()
                return n
            def _token2(n):
                toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", n or "")
                cand = [t for t in toks if any(c.isdigit() for c in t)]
                return max(cand, key=len).lower() if cand else None
            tp_map = {}
            for item in scrape_tp():
                nm = _norm2(item.get("name"))
                tp_map[nm] = item
                t = _token2(item.get("name"))
                if t:
                    tp_map.setdefault(t, item)
            for c in payload.get("cpus", []):
                it = tp_map.get(_norm2(c.get("name"))) or tp_map.get(_token2(c.get("name")))
                if not it:
                    continue
                if c.get("cores") is None and it.get("cores") is not None:
                    c["cores"] = it.get("cores")
                if c.get("threads") is None and it.get("threads") is not None:
                    c["threads"] = it.get("threads")
                if c.get("socket") is None and it.get("socket"):
                    c["socket"] = it.get("socket")
                if c.get("tdp") is None and it.get("tdp") is not None:
                    c["tdp"] = it.get("tdp")
        except Exception as e:
            logger.warning("TechPowerUp merge failed: %s", e)
            payload["techpowerup_error"] = str(e)
        try:
            payload["gpus"] = scrape_gpus()
        except Exception as e:
            logger.warning("GPU scrape failed: %s", e)
            payload["gpus"] = []
            payload["gpu_error"] = str(e)
        # merge vram/length from PCPartPicker where matched (by chipset)
        try:
            from scrapers.pcpp import scrape_gpu_specs
            spec_map = {}
            for s in scrape_gpu_specs(region):
                if s.get("chipset"):
                    spec_map[s["chipset"].lower().strip()] = s
            for g in payload.get("gpus", []):
                if not isinstance(g, dict):
                    continue
                g.setdefault("vram_gb", None)
                g.setdefault("length", None)
                sp = spec_map.get((g.get("name") or "").lower().strip())
                if sp:
                    if g["vram_gb"] is None:
                        g["vram_gb"] = sp.get("vram_gb")
                    if g["length"] is None:
                        g["length"] = sp.get("length")
        except Exception as e:
            logger.warning("GPU spec merge failed: %s", e)
            payload["gpu_spec_error"] = str(e)
        try:
            parts = scrape_parts(region)
            payload.update(parts)
        except Exception as e:
            logger.warning("PCPartPicker scrape failed: %s", e)
            payload["parts_error"] = str(e)
        try:
            from scrapers.prebuilt import scrape_prebuilts
            payload["prebuilts"] = scrape_prebuilts()
        except Exception as e:
            logger.warning("Prebuilt scrape failed: %s", e)
            payload["prebuilts"] = []
            payload["prebuilt_error"] = str(e)
        for k in DATA_KEYS:
            payload.setdefault(k, [])
        # keep the last good data for any source that failed or came back much smaller
        kept = []
        for k in DATA_KEYS:
            new_rows = payload.get(k) or []
            old_rows = (cache or {}).get(k) or []
            if old_rows and len(new_rows) < 0.5 * len(old_rows):
                payload[k] = old_rows
                kept.append(k)
        payload["_kept_previous"] = kept
        # currency conversion: CPU and GPU prices come from PassMark in USD
        rate = _fx_rate(region)
        cur = REGION_CURRENCY.get(region, "USD")
        payload["_currency"] = cur
        payload["_currency_symbol"] = CURRENCY_SYMBOL.get(cur, "$")
        payload["_fx_ok"] = rate is not None
        for k in ("cpus", "gpus"):
            for r in (payload.get(k) or []):
                if not isinstance(r, dict) or r.get("price") is None:
                    continue
                if rate is None:
                    r["price"] = None
                    r["value"] = None
                elif rate != 1.0:
                    r["price"] = round(r["price"] * rate, 2)
                    if k == "cpus" and r.get("mark"):
                        r["value"] = round(r["mark"] / r["price"], 2)
                    elif k == "gpus" and r.get("score"):
                        r["value"] = round(r["score"] / r["price"], 2)
        # annotate price change vs previous scrape
        for k, rows in payload.items():
            if not isinstance(rows, list):
                continue
            prev = old_prices.get(k, {})
            for r in rows:
                if not isinstance(r, dict):
                    continue
                old = prev.get(r.get("name"))
                r["prev_price"] = old
                if old is not None and r.get("price") is not None and old:
                    r["price_change_pct"] = round((r["price"] - old) / old * 100, 2)
                else:
                    r["price_change_pct"] = None
        # append one price history snapshot per day, per region
        try:
            from datetime import date
            today = date.today().isoformat()
            h = _load_history(region)
            if not h or h[-1].get("date") != today:
                snap = {"date": today, "ts": time.time(), "region": region, "prices": {}}
                for k, rows in payload.items():
                    if not isinstance(rows, list):
                        continue
                    pm = {}
                    for r in rows:
                        if isinstance(r, dict) and r.get("name") and r.get("price") is not None:
                            pm[r["name"]] = r["price"]
                    if pm:
                        snap["prices"][k] = pm
                h.append(snap)
                h = h[-90:]
                _save_history(h, region)
        except Exception:
            pass
        save_cache(payload, region)
    finally:
        _scrape_thread = None

def get_data(force=False, region="us"):
    """Serve stored data; refresh on a schedule (/api/scrape), not on every page view."""
    global _scrape_thread
    region = _valid_region(region)
    cache = load_cache(region)
    if (not force) and cache and not is_stale(cache):
        return cache
    if cache is not None and not force:
        # Stale but usable: show it while the scheduled job refreshes in the background.
        return cache
    # No cache yet, or an explicit refresh: start a background scrape.
    with _scrape_lock:
        if _scrape_thread is None or not _scrape_thread.is_alive():
            _scrape_thread = threading.Thread(target=_do_scrape, args=(region,), daemon=True)
            _scrape_thread.start()
    return cache

def is_scraping():
    return _scrape_thread is not None and _scrape_thread.is_alive()

def cache_info(cache):
    if not cache:
        return {"saved_at": None, "counts": {}, "notes": []}
    counts = {}
    for k in DATA_KEYS:
        v = cache.get(k)
        counts[k] = len(v) if isinstance(v, list) else 0
    notes = []
    if cache.get("_fx_ok") is False:
        notes.append("Currency conversion is unavailable right now, so CPU and GPU prices are hidden for this region.")
    kept = cache.get("_kept_previous") or []
    if kept:
        notes.append("Some sources failed on the last refresh, so the last good data is shown for: " + ", ".join(kept) + ".")
    return {"saved_at": cache.get("_saved_at_iso"), "counts": counts, "notes": notes}
