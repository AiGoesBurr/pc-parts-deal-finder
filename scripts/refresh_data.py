"""Refresh the US parts cache and write a gzipped snapshot for GitHub Actions.

Run locally or from CI:
    python scripts/refresh_data.py
"""
import gzip
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import cache  # noqa: E402


def _gzip(src):
    if not os.path.exists(src):
        return None
    dst = src + ".gz"
    tmp = dst + ".tmp"
    with open(src, "rb") as f_in, gzip.open(tmp, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.replace(tmp, dst)
    return dst


def main():
    cache._do_scrape("us")
    src = cache._cache_path("us")
    out = _gzip(src)
    print("wrote", out)

    # Refresh the bundled TechPowerUp CPU core snapshot. If TechPowerUp is
    # blocked from CI, keep the existing snapshot rather than failing.
    try:
        from scrapers.techpowerup import scrape_cpu_cores
        data = scrape_cpu_cores()
        if data:
            out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "cpu_cores.json")
            mapped = {
                item["name"]: {
                    "cores": item.get("cores"),
                    "threads": item.get("threads"),
                    "socket": item.get("socket"),
                    "tdp": item.get("tdp"),
                }
                for item in data
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(mapped, f, ensure_ascii=False, indent=2)
            print("wrote", out_path)
    except Exception as e:
        print("cpu cores refresh skipped:", e)


if __name__ == "__main__":
    main()