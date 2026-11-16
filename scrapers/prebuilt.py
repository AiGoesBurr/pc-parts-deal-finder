import re
import requests

SYSTEM_WORDS = ["laptop", "notebook", "chromebook", "macbook", "tablet", "phone", "monitor", "keyboard", "mouse"]
BRANDS = ["hp", "dell", "lenovo", "acer", "asus", "msi", "alienware", "omen", "victus", "ideacentre", "inspiron", "optiplex", "vostro", "thinkcentre", "mac mini", "msi", "corsair", "ibuypower", "cyberpower", "skytech", "clx"]

def _parse_price(title):
    m = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", title)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None

def _is_prebuilt(title):
    low = title.lower()
    if any(w in low for w in SYSTEM_WORDS):
        return False
    if "desktop" in low and any(b in low for b in BRANDS):
        return True
    if any(w in low for w in ["gaming desktop", "prebuilt", "desktop pc", "desktop computer", "gaming pc", "tower pc", "desktop tower"]):
        return True
    return False

def scrape_prebuilts():
    queries = ["gaming desktop", "prebuilt pc", "gaming pc"]
    seen = set()
    out = []
    for q in queries:
        url = "https://slickdeals.net/newsearch.php?src=SearchBarV2&q=" + q.replace(" ", "+") + "&searcharea=deals&searchin=first&rss=1"
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=20)
            r.raise_for_status()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            if not title or link in seen:
                continue
            if not _is_prebuilt(title):
                continue
            seen.add(link)
            price = _parse_price(title)
            brand = title.split()[0] if title.split() else None
            out.append({
                "name": title,
                "brand": brand,
                "price": price,
                "value": (round(1.0 / price, 4) if price else None),
                "source": "Slickdeals",
                "source_url": link,
                "link": link,
                "prev_price": None,
                "price_change_pct": None,
            })
    return out[:60]