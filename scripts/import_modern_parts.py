import csv, glob, json, os, re, sys, argparse

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
    if cap is None:
        cap = _num(row.get("Capacity", "") or row.get("Total Capacity", ""))

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

def parse_ups(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price = _num(row.get("Price", "").replace("Add", ""))
    if price is None:
        return None
    cap_w = _num((row.get("Capacity (W)") or "").replace("Capacity (W)", ""))
    cap_va = _num((row.get("Capacity (VA)") or "").replace("Capacity (VA)", ""))
    return {
        "category": "ups",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "capacity_w": int(cap_w) if cap_w else None,
        "capacity_va": int(cap_va) if cap_va else None,
        "value": round((cap_va or cap_w or 0) / price, 4) if price else None,
    }

def parse_sound(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price_raw = row.get("Price", "").replace("Add", "").replace("Out of stock", "").strip()
    price = _num(price_raw)
    if price is None:
        return None
    channels = (row.get("Channels") or "").replace("Channels", "").strip() or None
    digital = (row.get("Digital Audio") or "").replace("Digital Audio", "").strip() or None
    snr = (row.get("SNR") or "").replace("SNR", "").strip() or None
    sample_rate = (row.get("Sample Rate") or "").replace("Sample Rate", "").strip() or None
    chipset = (row.get("Chipset") or "").replace("Chipset", "").strip() or None
    interface = (row.get("Interface") or "").replace("Interface", "").strip() or None
    return {
        "category": "sound",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "channels": channels,
        "digital_audio": digital,
        "snr": snr,
        "sample_rate": sample_rate,
        "chipset": chipset,
        "interface": interface,
        "value": round(1.0 / price, 4) if price else None,
    }

def parse_webcam(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price = _num(row.get("Price", "").replace("Add", "").replace("Out of stock", ""))
    if price is None:
        return None
    resolution = (row.get("Resolution") or "").replace("Resolution", "").strip() or None
    connection = (row.get("Connection") or "").replace("Connection", "").strip() or None
    focus = (row.get("Focus Type") or "").replace("Focus Type", "").strip() or None
    fov = (row.get("FOV Angle") or "").replace("FOV Angle", "").strip() or None
    return {
        "category": "webcam",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "resolution": resolution,
        "connection": connection,
        "focus_type": focus,
        "fov": fov,
        "value": round(1.0 / price, 4) if price else None,
    }

def parse_speakers(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price = _num(row.get("Price", "").replace("Add", "").replace("Out of stock", ""))
    if price is None:
        return None
    config = (row.get("Configuration") or "").replace("Configuration", "").strip() or None
    wattage = (row.get("Total Wattage") or "").replace("Total Wattage", "").strip() or None
    freq = (row.get("Frequency Response") or "").replace("Frequency Response", "").strip() or None
    color = (row.get("Color") or "").replace("Color", "").strip() or None
    return {
        "category": "speakers",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "configuration": config,
        "total_wattage": wattage,
        "frequency_response": freq,
        "color": color,
        "value": round(1.0 / price, 4) if price else None,
    }

def parse_external(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price = _num(row.get("Price", "").replace("Add", "").replace("Out of stock", ""))
    if price is None:
        return None
    typ = (row.get("Type") or "").replace("Type", "").strip() or None
    interface = (row.get("Interface") or "").replace("Interface", "").strip() or None
    cap = _num((row.get("Capacity") or "").replace("Capacity", ""))
    ppb = _num((row.get("Price / GB") or "").replace("Price / GB", ""))
    if ppb is None and price and cap:
        ppb = round(price / cap, 4)
    color = (row.get("Color") or "").replace("Color", "").strip() or None
    return {
        "category": "external_storage",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "type": typ,
        "interface": interface,
        "capacity_gb": cap,
        "price_per_gb": ppb,
        "color": color,
        "value": round(1.0 / ppb, 4) if ppb else (round(1.0 / price, 4) if price else None),
    }

def parse_network(row):
    name = re.sub(r"\s*\(\d+\)\s*$", "", row.get("Name", "")).strip()
    price = _num(row.get("Price", "").replace("Add", ""))
    if price is None:
        return None
    protocol = (row.get("Protocol") or "").replace("Protocol", "").strip() or None
    interface = (row.get("Interface") or "").replace("Interface", "").strip() or None
    color = (row.get("Color") or "").replace("Color", "").strip() or None
    return {
        "category": "network",
        "brand": name.split()[0] if name else None,
        "model": None,
        "name": name,
        "price": price,
        "source": "PCPartPicker (manual export)",
        "source_url": "https://pcpartpicker.com",
        "protocol": protocol,
        "interface": interface,
        "color": color,
        "value": round(1.0 / price, 4) if price else None,
    }

def main(paths, refresh_prices=False):
    motherboards = []
    memories = []
    networks = []
    upses = []
    sounds = []
    webcams = []
    speakers = []
    externals = []
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            hl = " ".join(h.lower() for h in headers)
            is_mem = ("modules" in hl and "speed" in hl) or "memory" in hl or "capacity" in hl or "type" in hl
            is_net = "protocol" in hl and "interface" in hl
            is_ups = "capacity (w)" in hl or "capacity (va)" in hl
            is_sound = "channels" in hl and "snr" in hl
            is_webcam = "resolution" in hl and "connection" in hl and "focus type" in hl
            is_speakers = "configuration" in hl and "total wattage" in hl
            is_external = "type" in hl and "interface" in hl and "capacity" in hl
            for row in reader:
                try:
                    if is_external:
                        r = parse_external(row)
                        if r:
                            externals.append(r)
                    elif is_speakers:
                        r = parse_speakers(row)
                        if r:
                            speakers.append(r)
                    elif is_webcam:
                        r = parse_webcam(row)
                        if r:
                            webcams.append(r)
                    elif is_sound:
                        r = parse_sound(row)
                        if r:
                            sounds.append(r)
                    elif is_ups:
                        r = parse_ups(row)
                        if r:
                            upses.append(r)
                    elif is_net:
                        r = parse_network(row)
                        if r:
                            networks.append(r)
                    elif is_mem and ("Module" in str(headers) or "Capacity" in str(headers) or "Speed" in str(headers)):
                        r = parse_mem(row)
                        if r:
                            memories.append(r)
                    else:
                        motherboards.append(parse_mb(row))
                except Exception as e:
                    print("skip row:", e)
    print(f"Parsed {len(motherboards)} motherboards, {len(memories)} memories, {len(networks)} network adapters, {len(upses)} UPS units, {len(sounds)} sound cards, {len(webcams)} webcams, {len(speakers)} speakers, {len(externals)} external storage")
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
        existing_mb = data.get("motherboard", [])
        existing_mem = data.get("memory", [])
        existing_net = data.get("network", [])
        existing_ups = data.get("ups", [])
        existing_sound = data.get("sound", [])
        existing_webcam = data.get("webcam", [])
        existing_speakers = data.get("speakers", [])
        existing_external = data.get("external_storage", [])
        names_mb = {m.get("name"): i for i, m in enumerate(existing_mb)}
        for m in motherboards:
            if m["name"] in names_mb:
                if refresh_prices:
                    idx = names_mb[m["name"]]
                    old = existing_mb[idx]
                    old["price"] = m["price"]
                    if m.get("form_factor"):
                        old["form_factor"] = m["form_factor"]
                    if m.get("socket"):
                        old["socket"] = m["socket"]
                    if m.get("ram_slots"):
                        old["ram_slots"] = m["ram_slots"]
                    if m.get("max_ram_gb"):
                        old["max_ram_gb"] = m["max_ram_gb"]
                    if old.get("price"):
                        old["value"] = round(1.0 / old["price"], 4)
            else:
                existing_mb.append(m)
                names_mb[m["name"]] = len(existing_mb) - 1
        names_mem = {m.get("name"): i for i, m in enumerate(existing_mem)}
        for m in memories:
            if m["name"] in names_mem:
                if refresh_prices:
                    idx = names_mem[m["name"]]
                    old = existing_mem[idx]
                    old["price"] = m["price"]
                    if m.get("module_type"):
                        old["module_type"] = m["module_type"]
                    if m.get("modules"):
                        old["modules"] = m["modules"]
                    if m.get("module_size_gb"):
                        old["module_size_gb"] = m["module_size_gb"]
                    if m.get("capacity_gb"):
                        old["capacity_gb"] = m["capacity_gb"]
                    if m.get("speed_ghz"):
                        old["speed_ghz"] = m["speed_ghz"]
                    if m.get("price_per_gb"):
                        old["price_per_gb"] = m["price_per_gb"]
                    if old.get("price_per_gb"):
                        old["value"] = round(1.0 / old["price_per_gb"], 4)
            else:
                existing_mem.append(m)
                names_mem[m["name"]] = len(existing_mem) - 1
        names_net = {m.get("name"): i for i, m in enumerate(existing_net)}
        for m in networks:
            if m["name"] in names_net:
                if refresh_prices:
                    idx = names_net[m["name"]]
                    old = existing_net[idx]
                    old["price"] = m["price"]
                    if m.get("protocol"):
                        old["protocol"] = m["protocol"]
                    if m.get("interface"):
                        old["interface"] = m["interface"]
                    if m.get("color"):
                        old["color"] = m["color"]
                    if old.get("price"):
                        old["value"] = round(1.0 / old["price"], 4)
            else:
                existing_net.append(m)
                names_net[m["name"]] = len(existing_net) - 1
        names_ups = {m.get("name"): i for i, m in enumerate(existing_ups)}
        for m in upses:
            if m["name"] in names_ups:
                if refresh_prices:
                    idx = names_ups[m["name"]]
                    old = existing_ups[idx]
                    old["price"] = m["price"]
                    if m.get("capacity_w"):
                        old["capacity_w"] = m["capacity_w"]
                    if m.get("capacity_va"):
                        old["capacity_va"] = m["capacity_va"]
                    if old.get("price"):
                        old["value"] = round((old.get("capacity_va") or old.get("capacity_w") or 0) / old["price"], 4)
            else:
                existing_ups.append(m)
                names_ups[m["name"]] = len(existing_ups) - 1
        names_sound = {m.get("name"): i for i, m in enumerate(existing_sound)}
        for m in sounds:
            if m["name"] in names_sound:
                if refresh_prices:
                    idx = names_sound[m["name"]]
                    old = existing_sound[idx]
                    old["price"] = m["price"]
                    if m.get("channels"):
                        old["channels"] = m["channels"]
                    if m.get("snr"):
                        old["snr"] = m["snr"]
                    if m.get("sample_rate"):
                        old["sample_rate"] = m["sample_rate"]
                    if m.get("interface"):
                        old["interface"] = m["interface"]
                    if m.get("chipset"):
                        old["chipset"] = m["chipset"]
                    if old.get("price"):
                        old["value"] = round(1.0 / old["price"], 4)
            else:
                existing_sound.append(m)
                names_sound[m["name"]] = len(existing_sound) - 1
        names_webcam = {m.get("name"): i for i, m in enumerate(existing_webcam)}
        for m in webcams:
            if m["name"] in names_webcam:
                if refresh_prices:
                    idx = names_webcam[m["name"]]
                    old = existing_webcam[idx]
                    old["price"] = m["price"]
                    if m.get("resolution"):
                        old["resolution"] = m["resolution"]
                    if m.get("connection"):
                        old["connection"] = m["connection"]
                    if old.get("price"):
                        old["value"] = round(1.0 / old["price"], 4)
            else:
                existing_webcam.append(m)
                names_webcam[m["name"]] = len(existing_webcam) - 1
        names_speakers = {m.get("name"): i for i, m in enumerate(existing_speakers)}
        for m in speakers:
            if m["name"] in names_speakers:
                if refresh_prices:
                    idx = names_speakers[m["name"]]
                    old = existing_speakers[idx]
                    old["price"] = m["price"]
                    if m.get("configuration"):
                        old["configuration"] = m["configuration"]
                    if m.get("total_wattage"):
                        old["total_wattage"] = m["total_wattage"]
                    if m.get("frequency_response"):
                        old["frequency_response"] = m["frequency_response"]
                    if old.get("price"):
                        old["value"] = round(1.0 / old["price"], 4)
            else:
                existing_speakers.append(m)
                names_speakers[m["name"]] = len(existing_speakers) - 1
        names_external = {m.get("name"): i for i, m in enumerate(existing_external)}
        for m in externals:
            if m["name"] in names_external:
                if refresh_prices:
                    idx = names_external[m["name"]]
                    old = existing_external[idx]
                    old["price"] = m["price"]
                    if m.get("type"):
                        old["type"] = m["type"]
                    if m.get("interface"):
                        old["interface"] = m["interface"]
                    if m.get("capacity_gb"):
                        old["capacity_gb"] = m["capacity_gb"]
                    if m.get("price_per_gb"):
                        old["price_per_gb"] = m["price_per_gb"]
                    if old.get("price_per_gb"):
                        old["value"] = round(1.0 / old["price_per_gb"], 4)
            else:
                existing_external.append(m)
                names_external[m["name"]] = len(existing_external) - 1
        data["motherboard"] = existing_mb
        data["memory"] = existing_mem
        data["network"] = existing_net
        data["ups"] = existing_ups
        data["sound"] = existing_sound
        data["webcam"] = existing_webcam
        data["speakers"] = existing_speakers
        data["external_storage"] = existing_external
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print("updated", fn)
    # keep supplemental dataset in sync
    try:
        mp = {"motherboard": [], "memory": [], "network": [], "ups": [], "sound": [], "webcam": [], "speakers": [], "external_storage": []}
        src = os.path.join(DATA_DIR, "cache_us.json")
        if not os.path.exists(src):
            src = os.path.join(DATA_DIR, "cache.json")
        with open(src, encoding="utf-8") as f:
            d = json.load(f)
        for m in d.get("motherboard", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["motherboard"].append(m)
        for m in d.get("memory", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["memory"].append(m)
        for m in d.get("network", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["network"].append(m)
        for m in d.get("ups", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["ups"].append(m)
        for m in d.get("sound", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["sound"].append(m)
        for m in d.get("webcam", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["webcam"].append(m)
        for m in d.get("speakers", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["speakers"].append(m)
        for m in d.get("external_storage", []):
            if m.get("source") == "PCPartPicker (manual export)":
                mp["external_storage"].append(m)
        out = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "modern_parts.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(mp, f, ensure_ascii=False, indent=2)
        print("updated datasets/modern_parts.json")
    except Exception as e:
        print("dataset sync failed:", e)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--refresh-prices", action="store_true")
    args = parser.parse_args()
    paths = []
    for a in args.paths:
        paths.extend(glob.glob(a))
    main(paths, refresh_prices=args.refresh_prices)