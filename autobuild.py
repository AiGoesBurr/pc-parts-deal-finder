from ranking import (
    is_eligible, cpu_socket, board_ram_type, board_form_ok, case_fits_board, psu_required_watts,
)

SHARES = {"gpu": 0.32, "cpu": 0.20, "motherboard": 0.11, "memory": 0.08,
          "storage": 0.08, "psu": 0.09, "case": 0.07, "cooler": 0.05}
MULTIPLIERS = (1.25, 1.6, 2.5)
DATA_NOTES = [
    "Our parts data has no AM5 or LGA1700 motherboards and no DDR5 memory, so builds use AM4 (Ryzen 3000/5000) or LGA1200 (Intel 10th/11th gen).",
    "Cooler socket support isn't in our data. Check that the cooler fits your CPU before buying.",
    "Prices come from PassMark and PCPartPicker snapshots and may be out of date. Check the Buy links before you buy.",
]
_results = {}


def _context(cache, budget):
    boards = {}
    for b in cache.get("motherboard", []):
        if is_eligible("motherboard", b) and board_form_ok(b) and (b.get("max_ram_gb") or 16) >= 16:
            boards.setdefault(b.get("socket"), []).append(b)
    rams = {}
    for m in cache.get("memory", []):
        if is_eligible("memory", m) and m.get("price_per_gb"):
            rams.setdefault(m.get("module_type"), []).append(m)
    cpus = []
    for c in cache.get("cpus", []):
        plat = cpu_socket(c.get("name"))
        if plat in boards and is_eligible("cpu", c) and c["price"] <= budget:
            cpus.append((c, plat))
    cpus.sort(key=lambda t: t[0].get("mark") or 0, reverse=True)
    cpu_cap = budget * SHARES["cpu"] * MULTIPLIERS[-1]
    psus = [p for p in cache.get("psu", []) if is_eligible("psu", p)]
    return {
        "cpus": cpus,
        "attempt_cpus": [t for t in cpus if t[0]["price"] <= cpu_cap][:60],
        "boards": boards,
        "rams": rams,
        "gpus": [g for g in cache.get("gpus", []) if is_eligible("gpu", g)],
        "storages": [s for s in cache.get("storage", [])
                     if is_eligible("storage", s) and (s.get("capacity_gb") or 0) >= 500 and s.get("price_per_gb")],
        "psus": psus,
        "psus_sorted": sorted(psus, key=lambda p: p["price"]),
        "cases": [c for c in cache.get("case", []) if is_eligible("case", c)],
        "coolers": [c for c in cache.get("cooler", []) if is_eligible("cooler", c)],
    }


def _best(rows, cap, key, ok=None):
    best, best_key = None, None
    for r in rows:
        price = r.get("price")
        if price is None or price > cap:
            continue
        if ok is not None and not ok(r):
            continue
        k = key(r)
        if k is None:
            continue
        if best_key is None or k > best_key:
            best, best_key = r, k
    return best


def _cheapest(r):
    return -r["price"]


def _per_gb(r):
    return -r["price_per_gb"] if r.get("price_per_gb") else None


def _psu_for(ctx, needed):
    for p in ctx["psus_sorted"]:
        if p["wattage"] >= needed:
            return p
    return None


def _attempt(cpu, plat, budget, mult, ctx):
    def cap(cat):
        return budget * SHARES[cat] * mult
    board = _best(ctx["boards"].get(plat, []), cap("motherboard"), _cheapest)
    if board is None:
        return None
    ram = _best(ctx["rams"].get(board_ram_type(board), []), cap("memory"), _per_gb)
    gpu = _best(ctx["gpus"], cap("gpu"), lambda r: r.get("score"))
    if ram is None or gpu is None:
        return None
    needed = psu_required_watts(cpu, gpu)
    psu = _best(ctx["psus"], cap("psu"), _cheapest, ok=lambda r: (r.get("wattage") or 0) >= needed)
    case = _best(ctx["cases"], cap("case"), _cheapest, ok=lambda r: case_fits_board(board, r))
    storage = _best(ctx["storages"], cap("storage"), _per_gb)
    cooler = _best(ctx["coolers"], cap("cooler"), _cheapest)
    if psu is None or case is None or storage is None or cooler is None:
        return None
    picks = {"cpu": cpu, "gpu": gpu, "motherboard": board, "memory": ram,
             "psu": psu, "case": case, "storage": storage, "cooler": cooler}
    if sum(p["price"] for p in picks.values()) > budget:
        return None
    return picks


def _upgrade(picks, ctx, budget):
    """Swap in a stronger CPU and/or GPU (and a bigger PSU if needed) while staying in budget."""
    base_cpu, base_gpu, base_psu = picks["cpu"], picks["gpu"], picks["psu"]
    platform = cpu_socket(base_cpu.get("name"))
    others = sum(p["price"] for k, p in picks.items() if k not in ("cpu", "gpu", "psu"))
    best = None
    for cpu, plat in ctx["cpus"]:
        if plat != platform or (cpu.get("mark") or 0) < (base_cpu.get("mark") or 0):
            continue
        for gpu in ctx["gpus"]:
            if (gpu.get("score") or 0) < (base_gpu.get("score") or 0):
                continue
            needed = psu_required_watts(cpu, gpu)
            psu = base_psu if base_psu["wattage"] >= needed else _psu_for(ctx, needed)
            if psu is None:
                continue
            if others + cpu["price"] + gpu["price"] + psu["price"] > budget:
                continue
            score = (gpu.get("score") or 0) + (cpu.get("mark") or 0)
            if best is None or score > best[0]:
                best = (score, cpu, gpu, psu)
    if best is not None:
        _, picks["cpu"], picks["gpu"], picks["psu"] = best


def _score(picks):
    return (picks["gpu"].get("score") or 0) + (picks["cpu"].get("mark") or 0)


def _summary(row):
    return {"name": row.get("name"), "brand": row.get("brand"), "price": row.get("price")}


def _build(cache, budget):
    if not cache or not cache.get("cpus"):
        return {"ok": False, "budget": budget, "warnings": DATA_NOTES,
                "message": "Parts data is still loading. Try again in a few minutes."}
    ctx = _context(cache, budget)
    candidates = []
    for mult in MULTIPLIERS:
        for cpu, plat in ctx["attempt_cpus"]:
            picks = _attempt(cpu, plat, budget, mult, ctx)
            if picks is not None:
                candidates.append(picks)
        if candidates:
            break
    candidates.sort(key=_score, reverse=True)
    best = None
    for picks in candidates[:3]:
        _upgrade(picks, ctx, budget)
        total = sum(p["price"] for p in picks.values())
        if total > budget:
            continue
        if best is None or _score(picks) > _score(best[1]):
            best = (total, picks)
    if best is None:
        return {"ok": False, "budget": budget, "warnings": DATA_NOTES,
                "message": "No compatible build fits this budget with the current parts data. Try a higher budget."}
    total, picks = best
    return {
        "ok": True,
        "budget": budget,
        "total": round(total, 2),
        "leftover": round(budget - total, 2),
        "platform": cpu_socket(picks["cpu"].get("name")),
        "picks": {cat: _summary(row) for cat, row in picks.items()},
        "warnings": DATA_NOTES,
    }


def build_within_budget(cache, budget):
    key = (round(budget), (cache or {}).get("_saved_at"))
    if key not in _results:
        _results.clear()
        _results[key] = _build(cache, budget)
    return _results[key]
