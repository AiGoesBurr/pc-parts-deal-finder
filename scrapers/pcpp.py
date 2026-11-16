import asyncio
from pcpartpicker import API

def _money(m):
    if m is None:
        return None
    try:
        return float(m.amount)
    except Exception:
        try:
            return float(str(m).split()[-1] if hasattr(m, "__str__") else None)
        except Exception:
            return None

def _bytes_gb(b):
    if b is None:
        return None
    try:
        return round(b.total / 1e9, 2)
    except Exception:
        return None

def _clock_ghz(c):
    if c is None:
        return None
    try:
        return round(c.cycles / 1e9, 2)
    except Exception:
        return None

def _rpm(r):
    if r is None:
        return None
    try:
        return {"min": r.min, "max": r.max, "default": r.default}
    except Exception:
        return None

def _db(d):
    if d is None:
        return None
    try:
        return {"min": d.min, "max": d.max, "default": d.default}
    except Exception:
        return None

def _base(p, category):
    return {
        "category": category,
        "brand": getattr(p, "brand", None),
        "model": getattr(p, "model", None),
        "name": f"{getattr(p,'brand',None)} {getattr(p,'model',None)}".strip(),
        "price": _money(getattr(p, "price", None)),
        "source": "PCPartPicker (via pcpartpicker mirror)",
        "source_url": "https://pcpartpicker.com",
    }

def scrape_parts(region="us"):
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    api = API(region)
    data = api.retrieve("memory", "internal-hard-drive", "power-supply", "motherboard", "case", "cpu-cooler",
                        "monitor", "keyboard", "mouse", "headphones")
    result = {"memory": [], "storage": [], "psu": [], "motherboard": [], "case": [], "cooler": [],
              "monitor": [], "keyboard": [], "mouse": [], "headphones": []}

    for p in data.get("memory", []):
        d = _base(p, "memory")
        d.update({
            "module_type": getattr(p, "module_type", None),
            "speed_ghz": _clock_ghz(getattr(p, "speed", None)),
            "modules": getattr(p, "number_of_modules", None),
            "module_size_gb": _bytes_gb(getattr(p, "module_size", None)),
            "capacity_gb": None,
            "price_per_gb": _money(getattr(p, "price_per_gb", None)),
            "cas_timing": getattr(p, "cas_timing", None),
            "error_correction": getattr(p, "error_correction", None),
            "color": getattr(p, "color", None),
        })
        ms = d["module_size_gb"]; nm = d["modules"]
        if ms is not None and nm:
            d["capacity_gb"] = round(ms * nm, 2)
        if d["price_per_gb"] is None and d["price"] and d["capacity_gb"]:
            d["price_per_gb"] = round(d["price"] / d["capacity_gb"], 4)
        if d["price_per_gb"]:
            d["value"] = round(1.0 / d["price_per_gb"], 4)
        else:
            d["value"] = None
        result["memory"].append(d)

    for p in data.get("internal-hard-drive", []):
        d = _base(p, "storage")
        cap = _bytes_gb(getattr(p, "capacity", None))
        d.update({
            "capacity_gb": cap,
            "storage_type": getattr(p, "storage_type", None),
            "form_factor": getattr(p, "form_factor", None),
            "interface": getattr(p, "interface", None),
            "price_per_gb": _money(getattr(p, "price_per_gb", None)),
        })
        if d["price_per_gb"] is None and d["price"] and cap:
            d["price_per_gb"] = round(d["price"] / cap, 4)
        if d["price_per_gb"]:
            d["value"] = round(1.0 / d["price_per_gb"], 4)
        else:
            d["value"] = None
        result["storage"].append(d)

    for p in data.get("power-supply", []):
        d = _base(p, "psu")
        w = getattr(p, "wattage", None)
        d.update({
            "wattage": w,
            "efficiency": getattr(p, "efficiency_rating", None),
            "modular": getattr(p, "modular", None),
            "form_factor": getattr(p, "form_factor", None),
            "price_per_watt": None,
        })
        if d["price"] and w:
            d["price_per_watt"] = round(d["price"] / w, 4)
            d["value"] = round(w / d["price"], 4)
        else:
            d["value"] = None
        result["psu"].append(d)

    for p in data.get("motherboard", []):
        d = _base(p, "motherboard")
        d.update({
            "socket": getattr(p, "socket", None),
            "form_factor": getattr(p, "form_factor", None),
            "ram_slots": getattr(p, "ram_slots", None),
            "max_ram_gb": _bytes_gb(getattr(p, "max_ram", None)),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["motherboard"].append(d)

    for p in data.get("case", []):
        d = _base(p, "case")
        d.update({
            "form_factor": getattr(p, "form_factor", None),
            "color": getattr(p, "color", None),
            "psu_wattage": getattr(p, "psu_wattage", None),
            "side_panel": getattr(p, "side_panel", None),
            "internal_bays": getattr(p, "internal_bays", None),
            "external_bays": getattr(p, "external_bays", None),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["case"].append(d)

    for p in data.get("cpu-cooler", []):
        d = _base(p, "cooler")
        d.update({
            "fan_rpm": _rpm(getattr(p, "fan_rpm", None)),
            "decibels": _db(getattr(p, "decibels", None)),
            "color": getattr(p, "color", None),
            "radiator_size": getattr(p, "radiator_size", None),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["cooler"].append(d)

    for p in data.get("monitor", []):
        d = _base(p, "monitor")
        res = getattr(p, "resolution", None)
        d.update({
            "size": getattr(p, "size", None),
            "resolution": f"{res.width}x{res.height}" if res else None,
            "refresh_rate": getattr(p, "refresh_rate", None),
            "response_time": getattr(p, "response_time", None),
            "panel_type": getattr(p, "panel_type", None),
            "aspect_ratio": getattr(p, "aspect_ratio", None),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["monitor"].append(d)

    for p in data.get("keyboard", []):
        d = _base(p, "keyboard")
        d.update({
            "style": getattr(p, "style", None),
            "switches": getattr(p, "switches", None),
            "backlight": getattr(p, "backlight", None),
            "tenkeyless": getattr(p, "tenkeyless", None),
            "connection": getattr(p, "connection", None),
            "color": getattr(p, "color", None),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["keyboard"].append(d)

    for p in data.get("mouse", []):
        d = _base(p, "mouse")
        d.update({
            "tracking": getattr(p, "tracking", None),
            "connection": getattr(p, "connection", None),
            "max_dpi": getattr(p, "max_dpi", None),
            "hand_orientation": getattr(p, "hand_orientation", None),
            "color": getattr(p, "color", None),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["mouse"].append(d)

    for p in data.get("headphones", []):
        d = _base(p, "headphones")
        fr = getattr(p, "frequency_response", None)
        d.update({
            "form_factor": getattr(p, "form_factor", None),
            "frequency_response": f"{fr.min}-{fr.max} Hz" if fr else None,
            "has_microphone": getattr(p, "has_microphone", None),
            "is_wireless": getattr(p, "is_wireless", None),
            "type": getattr(p, "type", None),
            "color": getattr(p, "color", None),
        })
        if d["price"]:
            d["value"] = round(1.0 / d["price"], 4)
        else:
            d["value"] = None
        result["headphones"].append(d)

    return result

def scrape_gpu_specs(region="us"):
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    api = API(region)
    data = api.retrieve("video-card")
    out = []
    for p in data.get("video-card", []):
        vram_gb = None
        try:
            vram_gb = round(p.vram.total / 1e9, 1)
        except Exception:
            pass
        out.append({"chipset": getattr(p, "chipset", None), "vram_gb": vram_gb, "length": getattr(p, "length", None)})
    return out

def scrape_cpu_cores(region="us"):
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    api = API(region)
    data = api.retrieve("cpu")
    out = []
    for p in data.get("cpu", []):
        out.append({"name": f"{p.brand} {p.model}".strip(), "cores": getattr(p, "cores", None),
                    "socket": getattr(p, "socket", None), "tdp": getattr(p, "tdp", None),
                    "price": _money(getattr(p, "price", None))})
    return out