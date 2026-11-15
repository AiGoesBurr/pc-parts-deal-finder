import json, os, time
from datetime import datetime

CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "cache.json")
CACHE_TTL = 6 * 3600  # 6 hours

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
