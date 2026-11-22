import csv, glob, json, os, re, sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ROOT = os.path.dirname(os.path.dirname(__file__))


def _num(s):
    if s is None:
        return None
    m = re.search(r"[\d.]+", str(s))
    return float(m.group(0)) if m else None


def _wireless(name):
    n = name.lower()
    for pat, label in [
        (r"wi-?fi\s*7|802\.11be|\bbe\d{3,4}\b", "Wi-Fi 7"),
        (r"wi-?fi\s*6e|802\.11ax.*6e", "Wi-Fi 6E"),
        (r"wi-?fi\s*6|802\.11ax|\bax\d{3,4}\b", "Wi-Fi 6"),
        (r"wi-?fi\s*5|802\.11ac|\bac\d{3,4}\b", "Wi-Fi 5"),
        (r"802\.11n|\bn\d{3,4}\b", "Wi-Fi 4"),
    ]:
        if re.search(pat, n):
            return label
    return None


def _bands(name):
    n = name.lower()
    if "quad" in n and "band" in n:
        return "Quad-Band"
    if "tri" in n and "band" in n:
        return "Tri-Band"
    if "dual" in n and "band" in n:
        return "Dual-Band"
    if "single" in n and "band" in n:
        return "Single-Band"
    return None


def _speed(name):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:gbps|g\s*bps|gb/s)", name, re.I)
    return m.group(1) + " Gbps" if m else None


def _ports(name):
    m = re.search(r"(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*g\b", name, re.I)
    if m:
        return f"{m.group(1)}x {m.group(2)}G"
    if re.search(r"\b10g\b", name, re.I):
        return "10G"
    if re.search(r"\b2\.5g\b", name, re.I):
        return "2.5G"
    if re.search(r"gigabit", name, re.I):
        return "Gigabit"
    return None


def parse_thermal(row):
    name = (row.get("Name") or "").strip()
    price = _num(row.get("Price"))
    if not name or price is None:
        return None
    link = (row.get("Link") or "").strip()
    rating = (row.get("Rating") or "").replace("(", "").replace(")", "").strip() or None
    promo = (row.get("Promo") or "").strip() or None
    return {
        "category": "thermal_paste",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "Newegg",
        "source_url": link,
        "link": link,
        "rating": rating,
        "promo": promo,
        "value": round(1.0 / price, 4) if price else None,
    }


def parse_router(row):
    name = (row.get("Name") or "").strip()
    price = _num(row.get("Price"))
    if not name or price is None:
        return None
    link = (row.get("Link") or "").strip()
    rating = (row.get("Rating") or "").replace("(", "").replace(")", "").strip() or None
    promo = (row.get("Promo") or "").strip() or None
    return {
        "category": "router",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "Newegg",
        "source_url": link,
        "link": link,
        "rating": rating,
        "promo": promo,
        "wireless_standard": _wireless(name),
        "bands": _bands(name),
        "speed": _speed(name),
        "ports": _ports(name),
        "value": round(1.0 / price, 4) if price else None,
    }


def main(paths):
    routers = []
    thermals = []
    for path in paths:
        is_thermal = "thermal" in os.path.basename(path).lower()
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = [h or "" for h in (reader.fieldnames or [])]
            if "Name" not in headers or "Price" not in headers:
                print("skip (not Newegg CSV):", path)
                continue
            for row in reader:
                if is_thermal:
                    r = parse_thermal(row)
                    if r:
                        thermals.append(r)
                else:
                    r = parse_router(row)
                    if r:
                        routers.append(r)
    print("Parsed", len(routers), "Newegg routers,", len(thermals), "thermal pastes")

    for fn in os.listdir(DATA_DIR):
        if not (fn.startswith("cache") and fn.endswith(".json")):
            continue
        path = os.path.join(DATA_DIR, fn)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        existing = data.get("router", [])
        names = {m.get("name"): i for i, m in enumerate(existing)}
        for r in routers:
            if r["name"] in names:
                old = existing[names[r["name"]]]
                old["price"] = r["price"]
                if r.get("link"):
                    old["link"] = r["link"]
                    old["source_url"] = r["link"]
                if r.get("rating"):
                    old["rating"] = r["rating"]
                if r.get("promo"):
                    old["promo"] = r["promo"]
                if old.get("price"):
                    old["value"] = round(1.0 / old["price"], 4)
            else:
                existing.append(r)
                names[r["name"]] = len(existing) - 1
        data["router"] = existing
        existing_t = data.get("thermal_paste", [])
        names_t = {m.get("name"): i for i, m in enumerate(existing_t)}
        for r in thermals:
            if r["name"] in names_t:
                old = existing_t[names_t[r["name"]]]
                old["price"] = r["price"]
                if r.get("link"):
                    old["link"] = r["link"]
                    old["source_url"] = r["link"]
                if r.get("rating"):
                    old["rating"] = r["rating"]
                if r.get("promo"):
                    old["promo"] = r["promo"]
                if old.get("price"):
                    old["value"] = round(1.0 / old["price"], 4)
            else:
                existing_t.append(r)
                names_t[r["name"]] = len(existing_t) - 1
        data["thermal_paste"] = existing_t
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print("updated", fn)

    # sync supplemental dataset
    try:
        src = os.path.join(DATA_DIR, "cache_us.json")
        if not os.path.exists(src):
            src = os.path.join(DATA_DIR, "cache.json")
        with open(src, encoding="utf-8") as f:
            d = json.load(f)
        out_path = os.path.join(ROOT, "datasets", "modern_parts.json")
        try:
            with open(out_path, encoding="utf-8") as f:
                mp = json.load(f)
        except Exception:
            mp = {}
        mp["router"] = [m for m in d.get("router", []) if m.get("source") in ("PCPartPicker (manual export)", "Newegg")]
        mp["thermal_paste"] = [m for m in d.get("thermal_paste", []) if m.get("source") in ("PCPartPicker (manual export)", "Newegg")]
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(mp, f, ensure_ascii=False, indent=2)
        print("updated datasets/modern_parts.json")
    except Exception as e:
        print("dataset sync failed:", e)


if __name__ == "__main__":
    paths = []
    for a in sys.argv[1:]:
        paths.extend(glob.glob(a))
    main(paths)
