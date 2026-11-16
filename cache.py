import json, os, time, threading
from datetime import datetime

REGION_CURRENCY = {"us":"USD","uk":"GBP","ca":"CAD","au":"AUD","de":"EUR","fr":"EUR","es":"EUR","it":"EUR","in":"INR","nz":"NZD","ie":"EUR","be":"EUR","se":"SEK"}
CURRENCY_SYMBOL = {"USD":"$","GBP":chr(163),"CAD":"C$","AUD":"A$","EUR":chr(8364),"INR":chr(8377),"NZD":"NZ$","SEK":"kr"}

def _cache_path(region="us"):
    return os.path.join(os.path.dirname(__file__), "data", f"cache_{region}.json")

def _fx_rate(region):
    if region == "us":
        return 1.0
    cur = REGION_CURRENCY.get(region, "USD")
    if cur == "USD":
        return 1.0
    try:
        import urllib.request, json
        url = f"https://api.exchangerate.host/latest?base=USD&symbols={cur}"
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read())
        return float(d["rates"][cur])
    except Exception:
        return 1.0

CACHE_TTL = 10 * 60  # 10 minutes

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "data", "price_history.json")

_scrape_lock = threading.Lock()
_scrape_thread = None
_scrape_region = "us"

def _ensure_dir():
    os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)

def load_cache(region="us"):
    p = _cache_path(region)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_cache(payload, region="us"):
    _ensure_dir()
    payload["_saved_at"] = time.time()
    payload["_saved_at_iso"] = datetime.now().isoformat(timespec="seconds")
    payload["_region"] = region
    with open(_cache_path(region), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

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
    for k in ("cpus","gpus","memory","storage","psu","motherboard","case","cooler","prebuilts"):
        pm = {}
        for r in (cache.get(k) or []):
            if isinstance(r, dict) and r.get("name") and r.get("price") is not None:
                pm[r["name"]] = r.get("price")
        if pm:
            m[k] = pm
    return m

def _load_history():
    try:
        if os.path.exists(HISTORY_PATH):
            return json.load(open(HISTORY_PATH, encoding="utf-8"))
    except Exception:
        pass
    return []

def _save_history(h):
    try:
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        json.dump(h, open(HISTORY_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

def get_price_history(cat, name):
    h = _load_history()
    out = []
    for snap in h:
        price = (snap.get("prices", {}).get(cat, {}) or {}).get(name)
        if price is not None:
            out.append({"ts": snap.get("ts"), "price": price})
    return out

def _do_scrape(region="us"):
    global _scrape_thread
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
            payload["techpowerup_error"] = str(e)
        try:
            payload["gpus"] = scrape_gpus()
        except Exception as e:
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
            payload["gpu_spec_error"] = str(e)
        try:
            parts = scrape_parts(region)
            payload.update(parts)
        except Exception as e:
            payload["parts_error"] = str(e)
        try:
            from scrapers.prebuilt import scrape_prebuilts
            payload["prebuilts"] = scrape_prebuilts()
        except Exception as e:
            payload["prebuilts"] = []
            payload["prebuilt_error"] = str(e)
        for k in ("memory","storage","psu","motherboard","case","cooler","prebuilts"):
            payload.setdefault(k, [])
        # currency conversion for non-USD regions
        rate = _fx_rate(region)
        cur = REGION_CURRENCY.get(region, "USD")
        payload["_currency"] = cur
        payload["_currency_symbol"] = CURRENCY_SYMBOL.get(cur, "$")
        if rate != 1.0:
            for k in ("cpus","gpus"):
                for r in (payload.get(k) or []):
                    if isinstance(r, dict) and r.get("price") is not None:
                        r["price"] = round(r["price"] * rate, 2)
                        if r.get("value") is not None and r.get("price"):
                            # recompute value with converted price
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
        # append price history snapshot (one per day)
        try:
            from datetime import date
            today = date.today().isoformat()
            h = _load_history()
            if not h or h[-1].get("date") != today:
                snap = {"date": today, "ts": time.time(), "prices": {}}
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
                _save_history(h)
        except Exception:
            pass
        save_cache(payload, region)
    finally:
        global _scrape_thread, _scrape_region
        _scrape_thread = None
        _scrape_region = region

def get_data(force=False, region="us"):
    global _scrape_thread, _scrape_region
    cache = load_cache(region)
    if (not force) and cache and not is_stale(cache):
        return cache
    with _scrape_lock:
        if _scrape_thread is None or not _scrape_thread.is_alive():
            _scrape_region = region
            _scrape_thread = threading.Thread(target=_do_scrape, args=(region,), daemon=True)
            _scrape_thread.start()
    return cache

def is_scraping():
    return _scrape_thread is not None and _scrape_thread.is_alive()

def cache_info(cache):
    if not cache:
        return {"saved_at": None, "counts": {}}
    counts = {}
    for k in ("cpus","gpus","memory","storage","psu","motherboard","case","cooler","prebuilts"):
        v = cache.get(k)
        counts[k] = len(v) if isinstance(v, list) else 0
    return {"saved_at": cache.get("_saved_at_iso"), "counts": counts}