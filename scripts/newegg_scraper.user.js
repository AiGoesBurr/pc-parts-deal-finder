// ==UserScript==
// @name         Newegg Product Exporter
// @namespace    pcparts-deal-finder
// @version      1.0
// @description  Export Newegg search/category results to CSV
// @match        https://www.newegg.com/*
// @grant        none
// ==/UserScript==

(function () {
  function csvEscape(v) {
    return '"' + String(v == null ? '' : v).replace(/"/g, '""').replace(/\s+/g, ' ').trim() + '"';
  }

  function downloadCSV(filename, rows) {
    const csv = rows.map(r => r.map(csvEscape).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function text(el) {
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  }

  function scrape() {
    const cells = Array.from(document.querySelectorAll('.item-cell, .item-container, [class*="item-cell"]'));
    const rows = [['Name', 'Price', 'Rating', 'Promo', 'Link']];
    const seen = new Set();
    for (const cell of cells) {
      const titleEl = cell.querySelector('.item-title, a.item-title, [class*="item-title"]');
      const name = text(titleEl);
      if (!name || seen.has(name)) continue;
      seen.add(name);
      const priceRaw = text(cell.querySelector('.price-current, [class*="price-current"]'));
      const price = priceRaw.replace(/[^0-9.]/g, '');
      const rating = text(cell.querySelector('.item-rating, [class*="item-rating"]'));
      const promo = text(cell.querySelector('.item-promo, [class*="item-promo"]'));
      const link = titleEl && titleEl.href ? titleEl.href : (cell.querySelector('a') || {}).href || '';
      rows.push([name, price, rating, promo, link]);
    }
    if (rows.length < 2) { alert('No products found on this page.'); return; }
    downloadCSV('newegg_products.csv', rows);
  }

  const btn = document.createElement('button');
  btn.textContent = 'Export Newegg to CSV';
  btn.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:99999;padding:8px 12px;background:#f7981d;color:#111;border:none;border-radius:6px;font-size:14px;font-weight:700;cursor:pointer;';
  btn.onclick = scrape;
  document.body.appendChild(btn);
})();
