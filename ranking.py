import re

BRONZE_PLUS = {"80+ Bronze", "80+ Silver", "80+ Gold", "80+ Platinum", "80+ Titanium"}
SUPPORTED_PLATFORMS = {"AM4", "AM5", "LGA1200", "LGA1700", "LGA1851"}
PLATFORM_RAM = {"AM4": "DDR4", "LGA1200": "DDR4", "AM5": "DDR5", "LGA1851": "DDR5"}

RYZEN_RE = re.compile(r"Ryzen (?:AI )?(?:\d )?(?:PRO )?(\d)(\d{3})")
INTEL_RE = re.compile(r"Core i([3579])-(\d{4,5})")
ULTRA_RE = re.compile(r"Core Ultra [579] (\d{3})")
MOBILE_RE = re.compile(r"\d{3,5}(?:HX|HK|HS|H|U|Y|P|G\d)(?![A-Za-z0-9])")
GPU_RE = re.compile(r"GeForce RTX (\d{4})|GeForce GTX 16\d{2}|Radeon RX (\d{4})|Arc [AB]\d{3}")
GPU_EXCLUDE_RE = re.compile(
    r"Laptop|Mobile|Max-Q|Notebook|Mobility|Quadro|FirePro|FireGL|Radeon Pro|RTX PRO|Tesla|GRID|Embedded|Vega|Iris|UHD",
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
    if MOBILE_RE.search(name):
        return False
    m = RYZEN_RE.search(name)
    if m:
        return m.group(1) in "345789"
    m = INTEL_RE.search(name)
    if m:
        return _intel_gen(m.group(2)) >= 10
    return bool(ULTRA_RE.search(name))


def is_current_gpu(name):
    name = name or ""
    if GPU_EXCLUDE_RE.search(name):
        return False
    m = GPU_RE.search(name)
    if not m:
        return False
    if m.group(1):
        return m.group(1)[0] in "2345"
    if m.group(2):
        return m.group(2)[0] in "56789"
    return True


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
    return True
