import csv, glob, json, os, re, sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def _num(s):
    if s is None:
        return None
    m = re.search(r"[\d.]+", str(s))
    return float(m.group(0)) if m else None

def parse_mb(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    socket = row.get("Socket / CPU", "").replace("Socket / CPU", "").strip()
    ff = row.get("Form Factor", "").replace("Form Factor", "").strip()
    maxram = _num(row.get("Memory Max", "").replace("Memory Max", ""))
    slots = _num(row.get("Memory Slots", "").replace("Memory Slots", ""))
    price = _num(row.get("Price", "").replace("Add", ""))
    return {
        "category": "motherboard",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "socket": socket,
        "form_factor": ff,
        "ram_slots": int(slots) if slots else None,
        "max_ram_gb": int(maxram) if maxram else None,
        "value": round(1.0 / price, 4) if price else None,
    }

def parse_mem(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price = _num(row.get("Price", "").replace("Add", ""))
    if price is None:
        return None

    # DDR5 export format: Speed=DDR5-6000, Modules=2 x 16GB, Price / GB=$14.687
    speed_raw = (row.get("Speed") or "").replace("Speed", "").strip()
    m = re.match(r"(DDR\d+)-(\d+)", speed_raw, re.I)
    mtype = m.group(1).upper() if m else (row.get("Type") or row.get("Memory Type") or "").replace("Memory Type", "").strip() or None
    speed_mhz = int(m.group(2)) if m else None
    speed_ghz = (speed_mhz / 1000.0) if speed_mhz else None

    modules_raw = (row.get("Modules") or row.get("Number of Modules") or "").replace("Modules", "").strip()
    mm = re.match(r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*GB", modules_raw, re.I)
    modules = int(mm.group(1)) if mm else None
    modsize = float(mm.group(2)) if mm else None
    cap = round(modsize * modules, 2) if (modsize and modules) else None
    # fallback capacity from other columns
    if cap is None:
        cap = _num(row.get("Capacity", "") or row.get("Total Capacity", ""))
    if cap is None and modsize and modules:
        cap = round(modsize * modules, 2)

    ppb = _num((row.get("Price / GB") or "").replace("Price / GB", ""))
    if ppb is None and price and cap:
        ppb = round(price / cap, 4)
    cas = _num((row.get("CAS Latency") or "").replace("CAS Latency", ""))

    return {
        "category": "memory",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "module_type": mtype,
        "modules": modules,
        "module_size_gb": modsize,
        "capacity_gb": cap,
        "speed_ghz": speed_ghz,
        "cas_timing": cas,
        "price_per_gb": ppb,
        "value": round(1.0 / ppb, 4) if ppb else None,
    }

def main(paths):
    motherboards = []
    memories = []
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            hl = " ".join(h.lower() for h in headers)
            is_mem = ("modules" in hl and "speed" in hl) or "memory" in hl or "capacity" in hl or "type" in hl
            for row in reader:
                try:
                    if is_mem and ("Module" in str(headers) or "Capacity" in str(headers) or "Speed" in str(headers)):
                        r = parse_mem(row)
                        if r:
                            memories.append(r)
                    else:
                        motherboards.append(parse_mb(row))
                except Exception as e:
                    print("skip row:", e)
    print(f"Parsed {len(motherboards)} motherboards, {len(memories)} memories")
    # merge into all cache files
    for fn in os.listdir(DATA_DIR):
        if not fn.startswith("cache") or not fn.endswith(".json"):
            continue
        path = os.path.join(DATA_DIR, fn)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        existing_mb = data.get("motherboard", [])
        existing_mem = data.get("memory", [])
        # dedupe by name
        names_mb = {m.get("name") for m in existing_mb}
        for m in motherboards:
            if m["name"] not in names_mb:
                existing_mb.append(m)
                names_mb.add(m["name"])
        names_mem = {m.get("name") for m in existing_mem}
        for m in memories:
            if m["name"] not in names_mem:
                existing_mem.append(m)
                names_mem.add(m["name"])
        data["motherboard"] = existing_mb
        data["memory"] = existing_mem
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print("updated", fn)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_modern_parts.py <csv...>")
        sys.exit(1)
    import glob as _glob
    paths = []
    for a in sys.argv[1:]:
        paths.extend(_glob.glob(a))
    main(paths)