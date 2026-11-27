import re

BRONZE_PLUS = {"80+ Bronze", "80+ Silver", "80+ Gold", "80+ Platinum", "80+ Titanium"}
SUPPORTED_PLATFORMS = {"AM4", "AM5", "LGA1200", "LGA1700", "LGA1851"}
PLATFORM_RAM = {"AM4": "DDR4", "LGA1200": "DDR4", "AM5": "DDR5", "LGA1851": "DDR5"}

RYZEN_RE = re.compile(r"Ryzen (?:AI )?(?:\d )?(?:PRO )?(\d)(\d{3})")
INTEL_RE = re.compile(r"Core i([3579])-(\d{4,5})")
ULTRA_RE = re.compile(r"Core Ultra [579] (\d{3})")
MOBILE_RE = re.compile(r"\d{3,5}(?:HX|HK|HS|H|U|Y|P|G\d)(?![A-Za-z0-9])")
# Server and workstation parts are not useful "best value" picks for a desktop
# builder, even when they happen to have a price.
SERVER_RE = re.compile(
    r"EPYC|Threadripper|Xeon|Opteron|Atom|Celeron|Pentium|Athlon|"
    r"Embedded|Workstation|Server",
    re.I,
)
# Only current retail generations are ranked. Older cards are still visible in
# the full table, but they no longer win the "best value" lists.
GPU_RE = re.compile(
    r"GeForce RTX (?:40|50)\d{2}|Radeon RX (?:7|9)\d{3}|Arc [AB]\d{3}",
    re.I,
)
GPU_EXCLUDE_RE = re.compile(
    r"Laptop|Mobile|Max-Q|Notebook|Mobility|Quadro|FirePro|FireGL|Radeon Pro|RTX PRO|Tesla|GRID|Embedded|Vega|Iris|UHD|"
    r"\b\d{4}M\b",
    re.I,
)
PSU_GOOD_RE = re.compile(
    r"SeaSonic|Seasonic|Super Flower|Corsair (?:RM|SF|HX|AX|TX)\d|"
    r"EVGA SuperNOVA|be quiet|MSI MPG|MSI MAG|NZXT C\d|Toughpower GF|"
    r"MWE Gold|Gigabyte UD|AORUS|ROG |TUF |Lian Li|Montech Titan|XPG Core|"
    r"Deepcool P[XM]|Phanteks AMP|SilverStone|Revolution|Hydro G|Focus|"
    r"PRIME|Vertex|Dark Power|Straight Power|Pure Power",
    re.I,
)
PSU_BAD_RE = re.compile(
    r"Apevia|Raidmax|GAMDIAS|Rosewill ARC|Cougar VTE|Gigabyte P-B|EVGA B[AR]\b|"
    r"Great Wall|Huntkey|Segotep|KOLINK|Mars Gaming|Tacens|TooQ|Sharkoon|"
    r"LC-Power|Inter-Tech|Chieftec|Aerocool|Xigmatek|Zalman|Raptor|"
    r"Combat|PowerMan",
    re.I,
)


def _intel_gen(digits):
    return int(digits[:2]) if len(digits) == 5 else int(digits[0])


def cpu_socket(name):
    name = name or ""
    if MOBILE_RE.search(name):
        return None
    m = RYZEN_RE.search(name)
    if m:
        gen = m.group(1)
        if gen in "2345":
            return "AM4"
        if gen in "789":
            return "AM5"
        return None
    m = INTEL_RE.search(name)
    if m:
        gen = _intel_gen(m.group(2))
        if gen in (10, 11):
            return "LGA1200"
        if gen in (12, 13, 14):
            return "LGA1700"
        return None
    m = ULTRA_RE.search(name)
    if m and m.group(1).startswith("2"):
        return "LGA1851"
    return None


def is_current_cpu(name):
    name = name or ""
    if MOBILE_RE.search(name) or SERVER_RE.search(name):
        return False
    m = RYZEN_RE.search(name)
    if m:
        # Ryzen 5000/7000/8000/9000 are the current consumer generations.
        return m.group(1) in "5789"
    m = INTEL_RE.search(name)
    if m:
        return _intel_gen(m.group(2)) >= 12
    return bool(ULTRA_RE.search(name))


def is_current_gpu(name):
    name = name or ""
    if GPU_EXCLUDE_RE.search(name):
        return False
    return bool(GPU_RE.search(name))


def is_quality_psu(r):
    """A conservative shortlist for the front-page value picks.

    The full table still shows every 80+ unit, but the front page should not
    recommend known low-end lines just because they are cheap per watt.
    """
    name = r.get("name") or ""
    if PSU_BAD_RE.search(name):
        return False
    if PSU_GOOD_RE.search(name):
        return True
    return r.get("efficiency") in ("80+ Gold", "80+ Platinum", "80+ Titanium")


def is_nvme_storage(r):
    text = ((r.get("interface") or "") + " " + (r.get("form_factor") or "")).lower()
    return "nvme" in text or "m.2" in text or "m2" in text


def gpu_price_floor(score):
    s = score or 0
    if s < 6000:
        return 50
    if s < 12000:
        return 120
    if s < 18000:
        return 200
    if s < 25000:
        return 350
    return 550


def gpu_power_estimate(score):
    s = score or 0
    if s <= 0:
        return 250
    for limit, watts in ((6000, 120), (12000, 180), (18000, 230), (25000, 290), (30000, 340)):
        if s < limit:
            return watts
    return 450


def psu_required_watts(cpu, gpu):
    return (cpu.get("tdp") or 105) + gpu_power_estimate(gpu.get("score")) + 150


def board_ram_type(board):
    socket = board.get("socket")
    if socket in PLATFORM_RAM:
        return PLATFORM_RAM[socket]
    if socket == "LGA1700":
        name = (board.get("name") or "").upper()
        if "DDR5" in name or " D5" in name:
            return "DDR5"
        if "DDR4" in name or " D4" in name:
            return "DDR4"
    return None


def board_form_ok(board):
    return (board.get("form_factor") or "").lower() in ("atx", "micro atx", "mini itx")


def case_fits_board(board, case):
    ff = (board.get("form_factor") or "").lower()
    cf = (case.get("form_factor") or "").lower().replace(" ", "")
    if ff == "atx":
        return cf.startswith("atx") or ("atx" in cf and "micro" not in cf)
    if ff == "micro atx":
        return "atx" in cf
    if ff == "mini itx":
        return True
    return False


def is_eligible(cat, r):
    """Current, priced parts only. Used for dashboards, leaderboards and auto-build."""
    price = r.get("price")
    if price is None or price <= 0:
        return False
    name = r.get("name") or ""
    if cat == "cpu":
        return is_current_cpu(name) and price >= 40
    if cat == "gpu":
        score = r.get("score") or 0
        return score > 0 and is_current_gpu(name) and price >= gpu_price_floor(score)
    if cat == "memory":
        return r.get("module_type") in ("DDR4", "DDR5") and (r.get("capacity_gb") or 0) >= 16 and price >= 15
    if cat == "storage":
        return r.get("storage_type") == "SSD" and (r.get("capacity_gb") or 0) >= 250 and price >= 20
    if cat == "psu":
        return (r.get("wattage") or 0) >= 450 and r.get("efficiency") in BRONZE_PLUS and price >= 30
    if cat == "motherboard":
        return r.get("socket") in SUPPORTED_PLATFORMS and price >= 60
    if cat == "case":
        return price >= 30 and "test bench" not in (r.get("form_factor") or "").lower()
    if cat == "cooler":
        return price >= 15
    if cat == "network":
        return price >= 10
    if cat == "ups":
        return price >= 30
    if cat == "sound":
        return price >= 10
    if cat == "webcam":
        return price >= 15
    if cat == "speakers":
        return price >= 10
    if cat == "external_storage":
        return price >= 10
    if cat == "router":
        return price >= 20
    if cat == "thermal_paste":
        return price >= 3
    if cat == "surge_protector":
        return price >= 5
    return True
