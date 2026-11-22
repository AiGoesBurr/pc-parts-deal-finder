import re
import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

def scrape_cpu_cores():
    url = "https://www.techpowerup.com/cpu-specs/"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    # find table with 'Cores' header
    target = None
    for t in tables:
        if "Cores" in t.get_text() and "Name" in t.get_text():
            target = t
            break
    if target is None and tables:
        target = tables[-1]
    out = []
    for tr in target.find_all("tr")[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        name = cells[0]
        cores_field = cells[2]  # "8  / 16"
        socket = cells[4] if len(cells) > 4 else None
        tdp_field = cells[7] if len(cells) > 7 else None
        cores = None
        threads = None
        m = re.match(r"(\d+)\s*/\s*(\d+)", cores_field)
        if m:
            cores = int(m.group(1))
            threads = int(m.group(2))
        elif cores_field.isdigit():
            cores = int(cores_field)
        tdp = None
        if tdp_field:
            mm = re.search(r"(\d+)", tdp_field)
            if mm:
                tdp = int(mm.group(1))
        out.append({"name": name, "cores": cores, "threads": threads, "socket": socket, "tdp": tdp})
    return out