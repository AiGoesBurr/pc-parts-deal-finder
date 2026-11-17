"""Product photos that are only used when the source page is about the same part.

A Bing image result is kept only when it links to a retailer or maker page whose
title contains every distinctive word and model number from the part name, and the
edition words (Ti, SUPER, XT, Pro, ...) match exactly. Anything else gets a
category placeholder instead.
"""
import html
import json
import logging
import os
import re
import threading
import time
from urllib.parse import quote, urlparse

import requests

logger = logging.getLogger("pcparts.images")

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "images_v2.json")
HIT_TTL = 30 * 86400
MISS_TTL = 3 * 86400
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TRUSTED_LABELS = {
    "amazon", "newegg", "bhphotovideo", "adorama", "microcenter", "walmart", "bestbuy", "pcpartpicker",
    "amd", "intel", "nvidia", "asus", "msi", "gigabyte", "asrock", "corsair", "crucial", "kingston",
    "samsung", "westerndigital", "seagate", "noctua", "be-quiet", "lian-li", "nzxt", "thermaltake",
    "coolermaster", "arctic", "evga", "zotac", "pny", "sapphire", "xfx", "powercolor", "logitech",
    "razer", "steelseries", "hyperx", "dell", "lenovo", "hp", "acer", "lg", "benq", "aoc", "viewsonic",
    "fractal", "seasonic", "thermalright", "deepcool", "phanteks", "gskill", "teamgroup",
}

# Edition words that change which product it is; a title must agree with the name on these.
VARIANTS = {"ti", "super", "xt", "xtx", "gre", "pro", "max", "plus", "ultra", "evo", "xl", "lite", "elite", "se", "x3d"}
# Words that describe a category rather than identify a part.
GENERIC = {
    "amd", "intel", "nvidia", "geforce", "radeon", "core", "cores", "thread", "threads",
    "processor", "processors", "desktop", "gaming", "graphics", "card", "cards", "memory",
    "kit", "edition", "series", "rgb", "black", "white", "with", "and", "for", "the",
    "internal", "solid", "state", "drive", "drives", "hard", "storage", "ssd", "hdd", "nvme",
    "pcie", "gen", "ddr", "usb", "sata", "wifi", "wireless", "motherboard", "board", "cooler",
    "cpu", "gpu", "power", "supply", "modular", "fully", "fan", "fans", "case", "tower", "atx",
    "matx", "itx", "eatx", "mid", "full", "bundle", "retail", "oem", "tray", "box", "new",
    "bulk", "version", "model", "pack", "dual", "channel", "socket", "cache", "boost", "clock",
    "unlocked", "computer", "pc", "tempered", "glass", "airflow", "heatsink", "ram", "dimm",
    "gb", "tb", "mb", "mhz", "ghz", "gbps", "rpm", "nm", "mm", "cm", "inch", "watt", "watts",
    "mt", "ms", "system", "bluetooth", "rev", "color", "colour",
}
_SPEC_LEAD = {"gen", "pcie", "ddr", "usb", "wifi", "sata", "cl", "x", "rev"}
_UNIT_NEXT = {"core", "cores", "thread", "threads", "ghz", "pack", "channel", "fan", "fans", "port", "ports", "slot", "slots", "layer", "layers"}

_WORD = re.compile(r"[a-z0-9]+")
_UNIT = re.compile(r"(\d+)(?:gbps|gb|tb|mb|mhz|ghz|rpm|nm|mm|g|t|m|w)")
_KIT = re.compile(r"\d+x\d+(?:gb|tb|g)?")
_SPEC = re.compile(r"(?:gen|pcie|ddr|usb|wifi|sata|cl|hdmi|dp|x)\d+|m2|2230|2242|2260|2280|22110")
_SUFFIX = re.compile(r"\d+([a-z][a-z0-9]*)")

_bing_slots = threading.BoundedSemaphore(2)
_lock = threading.Lock()
_store = None


def _signature(text):
    """Return (model numbers, distinctive words, edition words) for a part name or page title."""
    text = re.sub(r"\d+\.\d+", " ", (text or "").lower())
    text = re.sub(r"(?<![0-9])80\s*(?:\+|plus)", " 80plus ", text)
    raw = _WORD.findall(text)
    toks = []
    for i, tok in enumerate(raw):
        unit = _UNIT.fullmatch(tok)
        if unit:
            tok = unit.group(1)
        if tok.isdigit():
            prev = raw[i - 1] if i else ""
            nxt = raw[i + 1] if i + 1 < len(raw) else ""
            if prev in _SPEC_LEAD or nxt == "x" or nxt in _UNIT_NEXT:
                continue
        if _KIT.fullmatch(tok) or _SPEC.fullmatch(tok):
            continue
        toks.append(tok)
    model, used = set(), set()
    for i in range(len(toks) - 1):
        if toks[i][-1:].isdigit() and toks[i + 1] in VARIANTS:
            model.add(toks[i] + toks[i + 1])
            used.update((i, i + 1))
    model.update(t for i, t in enumerate(toks) if i not in used and any(c.isdigit() for c in t))
    variants = set()
    for t in toks:
        suffix = _SUFFIX.fullmatch(t)
        if t in VARIANTS:
            variants.add(t)
        elif suffix and suffix.group(1) in VARIANTS:
            variants.add(suffix.group(1))
    words = {t for t in toks if t.isalpha() and len(t) >= 3 and t not in GENERIC and t not in VARIANTS}
    return model, words, variants


def same_part(name, title):
    model, words, variants = _signature(name)
    if not model and not words:
        return False
    t_model, t_words, t_variants = _signature(title)
    return model <= t_model and words <= t_words and variants == t_variants


def _trusted(url):
    host = (urlparse(str(url or "")).hostname or "").lower()
    return any(label in TRUSTED_LABELS for label in host.split("."))


def pick_photo(name, results):
    """Return the image of the first retailer or maker page that is about this part."""
    for r in results:
        if (str(r.get("murl") or "").startswith("https://") and _trusted(r.get("purl"))
                and same_part(name, r.get("t") or "")):
            return r["murl"]
    return None


def _bing_results(query):
    url = "https://www.bing.com/images/search?q=" + quote(query) + "&form=HDRSC2"
    with _bing_slots:
        r = requests.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    results = []
    for m in re.finditer(r'm="(\{.*?\})"', r.text):
        try:
            results.append(json.loads(html.unescape(m.group(1))))
        except ValueError:
            continue
    return results


def _deal_photo(link):
    try:
        host = (urlparse(link).hostname or "").lower()
    except ValueError:
        return None
    if host != "slickdeals.net" and not host.endswith(".slickdeals.net"):
        return None
    try:
        r = requests.get(link, headers=HEADERS, timeout=12)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.info("deal page fetch failed: %s", e)
        return None
    m = re.search(r'<meta property="og:image" content="(https://[^"]+)"', r.text)
    return html.unescape(m.group(1)) if m else None


def _lookup(name, link):
    """Return (url, settled). settled=False means the lookup failed and should be retried later."""
    if link:
        url = _deal_photo(link)
        if url:
            return url, True
    try:
        results = _bing_results(name)
    except requests.RequestException as e:
        logger.info("image search failed for %s: %s", name, e)
        return None, False
    return pick_photo(name, results), True


def _load_store():
    global _store
    if _store is None:
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                _store = json.load(f)
        except (OSError, ValueError):
            _store = {}
    return _store


def _save_store():
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_store, f)
    os.replace(tmp, CACHE_PATH)


def find_photo(name, link=None):
    """Return an image URL verified to show this part, or None."""
    key = " ".join(name.lower().split()) + "|" + (link or "")
    with _lock:
        entry = _load_store().get(key)
    if entry:
        ttl = HIT_TTL if entry.get("url") else MISS_TTL
        if time.time() - entry.get("at", 0) < ttl:
            return entry.get("url") or None
    url, settled = _lookup(name, link)
    if settled:
        with _lock:
            _load_store()[key] = {"url": url or "", "at": time.time()}
            try:
                _save_store()
            except OSError as e:
                logger.warning("could not save image cache: %s", e)
    return url
