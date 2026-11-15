import re
import time
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def _clean_num(s):
    if s is None:
        return None
    s = s.strip().replace(",", "").replace("$", "").replace("*", "").strip()
    if s in ("", "NA", "N/A", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def scrape_cpus():
    items = []
    seen = set()
    for url in ("https://cpubenchmark.net/cpu-list/intel", "https://cpubenchmark.net/cpu-list/amd", "https://cpubenchmark.net/cpu-list/other"):
        time.sleep(1)
        r = requests.get(url, headers=UA, timeout=90)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tables = [t for t in soup.find_all("table") if "CPU Name" in t.get_text()]
        if not tables:
            continue
        table = tables[0]
        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cells) < 5:
                continue
            name = cells[0]
            mark = _clean_num(cells[1])
            rank = _clean_num(cells[2])
            value = _clean_num(cells[3])
            price = _clean_num(cells[4])
            if name in seen:
                continue
            seen.add(name)
            # derive value if missing
            if value is None and mark is not None and price:
                value = round(mark / price, 2)
            low = name.lower()
            if "apple" in low:
                brand = "Apple"
            elif "amd" in low:
                brand = "AMD"
            elif "intel" in low:
                brand = "Intel"
            elif "arm" in low:
                brand = "ARM"
            else:
                brand = name.split()[0]
            items.append({
                "name": name,
                "brand": brand,
                "cores": None,
                "mark": mark,
                "rank": rank,
                "value": value,
                "price": price,
                "source": "PassMark CPU Benchmarks",
                "source_url": url,
            })
    return items

GPU_TIER_URLS = [
    "https://videocardbenchmark.net/high_end_gpus.html",
    "https://videocardbenchmark.net/mid_range_gpus.html",
    "https://videocardbenchmark.net/midlow_range_gpus.html",
    "https://videocardbenchmark.net/low_end_gpus.html",
    "https://videocardbenchmark.net/common_gpus.html",
]

def _parse_tier_page(url):
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    txt = soup.get_text("\n")
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    items = []
    i = 0
    n = len(lines)
    name_keywords = ("GeForce", "Radeon", "Arc ", "Quadro", "RTX", "GTX", "RX ", "Intel ", "Iris", "UHD", "Tesla", "FirePro", "FireGL")
    while i < n:
        l = lines[i]
        is_name = (any(k in l for k in name_keywords) and not l.startswith("(")
                   and not re.fullmatch(r"[\d,]+\*?", l) and not re.fullmatch(r"[\d,]+\.\d{2}\*?", l)
                   and "Average" not in l and "Price" not in l and "Videocard" not in l)
        if is_name:
            name = l
            j = i + 1
            pct = None
            if j < n and lines[j].startswith("("):
                pct = lines[j]; j += 1
            score = None
            if j < n and re.fullmatch(r"[\d,]+", lines[j]):
                score = _clean_num(lines[j]); j += 1
            price = None
            if j < n:
                pl = lines[j]
                if pl == "NA" or re.fullmatch(r"[\d,]+\.\d{2}\*?", pl):
                    price = _clean_num(pl); j += 1
            if score is not None:
                low = name.lower()
                if "geforce" in low or "rtx" in low or "gtx" in low or "quadro" in low or "tesla" in low or "nvidia" in low:
                    brand = "NVIDIA"
                elif "radeon" in low or "rx " in low or "rx-" in low or "amd" in low or "firegl" in low or "firepro" in low or "mobility" in low:
                    brand = "AMD"
                elif "arc" in low or "iris" in low or "uhd" in low or "intel" in low:
                    brand = "Intel"
                else:
                    brand = name.split()[0]
                items.append({
                    "name": name,
                    "brand": brand,
                    "score": score,
                    "price": price,
                    "percent": pct,
                    "source": "PassMark Video Card Benchmarks",
                    "source_url": url,
                })
                i = j
                continue
        i += 1
    return items

def scrape_gpus():
    all_items = []
    seen = set()
    for url in GPU_TIER_URLS:
        time.sleep(1)
        try:
            page_items = _parse_tier_page(url)
        except Exception:
            page_items = []
        for it in page_items:
            if it["name"] in seen:
                continue
            seen.add(it["name"])
            # derive value
            if it["score"] and it["price"]:
                it["value"] = round(it["score"] / it["price"], 2)
            else:
                it["value"] = None
            all_items.append(it)
    return all_items
