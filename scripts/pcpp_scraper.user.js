// ==UserScript==
// @name         PCPartPicker Product Exporter
// @namespace    pcparts-deal-finder
// @version      1.0
// @description  Export the current PCPartPicker product table to CSV
// @match        https://pcpartpicker.com/products/*
// @grant        none
// ==/UserScript==

(function () {
  function downloadCSV(filename, rows) {
    const csv = rows.map(r => r.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\n');
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

  function scrape() {
    const tables = Array.from(document.querySelectorAll('table'));
    if (!tables.length) { alert('No table found'); return; }
    const table = tables.reduce((a, b) => a.querySelectorAll('tr').length >= b.querySelectorAll('tr').length ? a : b);
    const headers = Array.from(table.querySelectorAll('thead th, thead td')).map(c => c.textContent.trim());
    const rows = [headers.length ? headers : Array.from(table.querySelector('tr').querySelectorAll('th,td')).map(c=>c.textContent.trim())];
    table.querySelectorAll('tbody tr, tr').forEach(tr => {
      const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
      if (cells.length && cells.some(c => c)) rows.push(cells);
    });
    // de-dupe header row if repeated
    const out = rows.filter((r, i) => i === 0 || r.join('|') !== rows[0].join('|'));
    downloadCSV('pcpartpicker_products.csv', out);
  }

  const btn = document.createElement('button');
  btn.textContent = 'Export table to CSV';
  btn.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:99999;padding:8px 12px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer;';
  btn.onclick = scrape;
  document.body.appendChild(btn);
})();