import requests
from bs4 import BeautifulSoup
from pcpartpicker import API
r=requests.get('https://cpubenchmark.net/cpu-list/amd', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=30)
soup=BeautifulSoup(r.text,'html.parser')
table=[t for t in soup.find_all('table') if 'CPU Name' in t.get_text()][0]
rows=table.find_all('tr')
pm_names=set()
for tr in rows[1:]:
    cells=[c.get_text(strip=True) for c in tr.find_all('td')]
    if len(cells)>=1:
        pm_names.add(cells[0])
print('pm count', len(pm_names))
api=API('us')
data=api.retrieve('cpu')
pp_names=set(f"{p.brand} {p.model}" for p in data['cpu'])
print('pp count', len(pp_names))
# normalize: lowercase, strip clock
import re
def norm(n):
    n=n.lower()
    n=re.sub(r'@\s*[\d\.]+ghz','',n)
    n=re.sub(r'\s+',' ',n).strip()
    return n
pm_norm={norm(n) for n in pm_names}
pp_norm={norm(n) for n in pp_names}
print('intersection', len(pm_norm & pp_norm))
print('sample pm', list(pm_norm)[:5])
print('sample pp', list(pp_norm)[:5])