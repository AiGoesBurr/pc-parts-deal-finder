import json, os
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
for fn in os.listdir(DATA_DIR):
    if not (fn.startswith("cache") and fn.endswith(".json")):
        continue
    path = os.path.join(DATA_DIR, fn)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    mb = data.get("motherboard", [])
    before = len(mb)
    mb = [m for m in mb if (m.get("socket") or "").strip()]
    data["motherboard"] = mb
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(fn, "removed", before - len(mb), "bad rows; now", len(mb))