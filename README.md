# PC Parts Deal Finder

A small web app that scrapes reliable sources for the best bang-for-your-buck PC parts
and ranks them by value.

## Sources

- **PassMark CPU Benchmarks** (cpubenchmark.net) - CPU Mark, price, CPU Value. Intel, AMD, Apple/ARM and other CPUs.
- **PassMark Video Card Benchmarks** (videocardbenchmark.net) - G3D Mark, price, GPU value across all tier pages.
- **PCPartPicker** (via the community mirror used by the `pcpartpicker` package) - Memory, storage, PSU, motherboard, case, cooler prices and specs.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

On first run the app scrapes all sources (may take ~2-3 minutes) and caches to `data/cache.json`.
Use "Refresh data" in the navbar (or `/refresh`) to re-scrape.

## Features

- Dashboard with top value picks per category.
- Per-category tables with search, brand filter, sort, pagination.
- Derived value metrics: CPU/GPU score per dollar, RAM $/GB, storage $/GB, PSU $/W, and 1/price for other parts.
- "Buy" column with live retailer search links (Amazon, Newegg, B&H) for current prices and inventory.
- Live PC hardware deals page (Slickdeals).
- CSV export per category.
- Source attribution on every row.
