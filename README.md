# PC Parts Deal Finder

A small web app that scrapes reliable sources for the best bang-for-your-buck PC parts
and ranks them by value.

## Sources

- **PassMark CPU Benchmarks** (cpubenchmark.net) - CPU Mark, price, CPU Value. Intel, AMD, Apple/ARM and other CPUs.
- **PassMark Video Card Benchmarks** (videocardbenchmark.net) - G3D Mark, price, GPU value across all tier pages.
- **PCPartPicker** (via a community mirror of pcpartpicker.com) - Memory, storage, PSU, motherboard, case, cooler, monitor, keyboard, mouse, headphone prices & specs.
- **TechPowerUp CPU Specs** (techpowerup.com) - CPU core/thread counts and sockets.
- **Slickdeals** (slickdeals.net) - Live PC hardware deals.
- **Amazon / Bing image search** - Product photos (best-effort).
- **ECB daily rates** (ecb.europa.eu) - Currency conversion for non-USD regions.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

On first run the app scrapes all sources (may take ~2-3 minutes) and caches to `data/cache.json`.
Use "Refresh data" in the navbar (or `/refresh`) to re-scrape.

## How "Value" is calculated

Higher Value = better bang for your buck. Rows are sorted by Value descending by default.

- **CPU**: CPU Mark ÷ price (PassMark CPU Value) — more benchmark performance per dollar.
- **GPU**: G3D Mark ÷ price — more graphics performance per dollar.
- **RAM**: 1 ÷ price per GB — cheaper per gigabyte.
- **Storage**: 1 ÷ price per GB — cheaper per gigabyte.
- **PSU**: watts ÷ price — more power per dollar.
- **Motherboard / Case / Cooler**: 1 ÷ price — cheaper.

Entries with no price get a null Value and sort to the bottom.

## Live site

https://pc-parts-an-deals.onrender.com/

## Features

- Dashboard with top value picks per category and a loading banner during background scraping.
- Per-category tables with search, brand/form-factor/storage-type filters, min/max price, min/max cores (CPU), sort, pagination.
- Product images pulled from manufacturer/retailer sources.
- Price change (Δ%) tracking vs. previous scrape, with price history charts per part.
- "Buy" column with live retailer search links (Amazon, Newegg, B&H, Best Buy, Micro Center) for current prices and inventory.
- Live PC hardware deals page (Slickdeals) with newest/price sorting.
- Prebuilt PCs category.
- Build cost calculator with auto-suggest best value build and export to PCPartPicker.
- Saved builds (no account) with save/load/delete.
- Watchlist with price alerts and target prices.
- Build compatibility checker (socket, RAM type, PSU wattage).
- Compare feature for side-by-side component comparison.
- Dark/light theme toggle.
- CSV export per category.
- Source attribution on every row.
- 10-minute cache refresh and GitHub Actions keepalive for free hosting.
