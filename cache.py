import json, os, time
from datetime import datetime

CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "cache.json")
CACHE_TTL = 1 * 3600  # 1 hour (prices change frequently)

def _ensure_dir():
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)

def load_cache():
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_cache(payload):
    _ensure_dir()
    payload["_saved_at"] = time.time()
    payload["_saved_at_iso"] = datetime.now().isoformat(timespec="seconds")
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f)

def is_stale(cache):
    if not cache:
        return True
    saved = cache.get("_saved_at")
    if not saved:
        return True
    return (time.time() - saved) > CACHE_TTL

def get_data(force=False):
    cache = load_cache()
    if (not force) and cache and not is_stale(cache):
        return cache
    # refresh
    from scrapers.passmark import scrape_cpus, scrape_gpus
    from scrapers.pcpp import scrape_parts
    payload = {}
    try:
        payload["cpus"] = scrape_cpus()
    except Exception as e:
        payload["cpus"] = []
        payload["cpu_error"] = str(e)
    # merge core counts from PCPartPicker where possible
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
        core_map = {}
        for item in scrape_cpu_cores():
            nm = _norm(item.get("name"))
            core_map[nm] = item.get("cores")
            t = _token(item.get("name"))
            if t:
                core_map.setdefault(t, item.get("cores"))
        for c in payload.get("cpus", []):
            if c.get("cores") is not None:
                continue
            cores = core_map.get(_norm(c.get("name")))
            if cores is None:
                cores = core_map.get(_token(c.get("name")))
            c["cores"] = cores
    except Exception as e:
        payload["cpu_core_error"] = str(e)
    try:
        payload["gpus"] = scrape_gpus()
    except Exception as e:
        payload["gpus"] = []
        payload["gpu_error"] = str(e)
    try:
        parts = scrape_parts()
        payload.update(parts)
    except Exception as e:
        payload["parts_error"] = str(e)
    # errors
    for k in ("memory","storage","psu","motherboard","case","cooler"):
        payload.setdefault(k, [])
    save_cache(payload)
    return load_cache()

def cache_info(cache):
    if not cache:
        return {"saved_at": None, "counts": {}}
    counts = {}
    for k in ("cpus","gpus","memory","storage","psu","motherboard","case","cooler"):
        v = cache.get(k)
        counts[k] = len(v) if isinstance(v, list) else 0
    return {"saved_at": cache.get("_saved_at_iso"), "counts": counts}
