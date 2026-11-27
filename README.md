# PC Parts Deal Finder

A small Flask app that aggregates PC part prices and benchmarks, ranks them by
value, and lists filtered PC hardware deals.

## Sources

- **PassMark CPU Benchmarks** (cpubenchmark.net) - CPU Mark and CPU prices.
- **PassMark Video Card Benchmarks** (videocardbenchmark.net) - G3D Mark and prices.
- **PCPartPicker** (via a community mirror) - part prices and specs.
- **TechPowerUp CPU Specs** - core/thread counts and sockets.
- **Slickdeals** - US PC hardware deals.
- **ECB daily rates** - currency conversion for non-USD regions.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

On first run the app scrapes all sources (may take a few minutes) and caches the
result. The scheduler and the GitHub Actions workflow keep the US snapshot up to
date. Other regions are collected on demand when a visitor selects them; until a
snapshot exists, the page says so rather than showing US prices in another
currency.

The manual refresh button is disabled by default. To show it on a private
instance, set `ENABLE_REFRESH=1`. `/refresh` and `/api/scrape` also require
`SCRAPE_TOKEN` in production.

## How value is calculated

Higher value means more performance per dollar. Rows are sorted by value
descending by default; rows without a real price are pushed to the bottom.

- **CPU**: CPU Mark / price.
- **GPU**: G3D Mark / price.
- **RAM / storage**: 1 / price per GB.
- **PSU**: watts / price.
- **Motherboard / case / cooler**: 1 / price.

Front-page picks use quality floors:

- Consumer CPUs only: Ryzen 5000/7000/8000/9000, Intel 12th gen or newer.
- Current GPUs only: RTX 40/50, RX 7000/9000, Intel Arc A/B.
- NVMe storage only on the front page; the full table still includes SATA.
- 80+ Bronze or better PSUs, excluding known low-end lines from the top picks.
- Prices older than 14 days pause the value rankings instead of showing stale
  numbers as current.
- Price changes over 50% are hidden as likely source changes.

## Features

- Dashboard with current best-value CPU/GPU/NVMe/PSU picks and region-aware
  retailer links.
- Category tables with search, brand, price, category-specific filters, sorting,
  pagination and CSV export.
- Price history charts where at least two snapshots exist.
- Slickdeals feed filtered to PC parts, deduplicated, with merchant names,
  relative timestamps, pagination and USD labels.
- Build calculator with auto-suggest, budget auto-build, compatibility checks and
  shareable URLs.
- Saved builds, local watchlist, compare selections and theme choice stored in
  browser local storage.
- No account required.
- Cookie consent gate: no advertising script loads unless the visitor accepts.
- Accessibility/SEO checks: Lighthouse 100/100/100 on the dashboard and category
  pages.

## What is intentionally not promised

- Prices are estimates from public sources, not live retailer inventory.
- There is no email newsletter or email price-alert service yet. The watchlist
  checks target prices when you open the watchlist page.
- Advertising is loaded only after consent. A Google-certified CMP is still
  recommended for EEA/UK traffic before running ads there.
- Individual part detail pages are not implemented yet. Category links deep-link
  to a filtered category view.
