import requests
from bs4 import BeautifulSoup
from pcpartpicker import API
import re
r=requests.get('https://cpubenchmark.net/cpu-list/amd', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=30)
soup=BeautifulSoup(r.text,'html.parser')
table=[t for t in soup.find_all('table') if 'CPU Name' in t.get_text()][0]
rows=table.find_all('tr')
pm=[]
for tr in rows[1:]:
    cells=[c.get_text(strip=True) for c in tr.find_all('td')]
    if cells: pm.append(cells[0])
api=API('us')
data=api.retrieve('cpu')
pp=[(p.brand,p.model,p.cores) for p in data['cpu']]
def norm(n):
    n=n.lower()
    n=re.sub(r'@\s*[\d\.]+\s*ghz','',n)
    n=re.sub(r'\s+',' ',n).strip()
    return n
# try match by model token (last alphanumeric-ish)
def key(n):
    n=norm(n)
    # remove brand
    for b in ['amd','intel','apple']:
        if n.startswith(b+' '):
            n=n[len(b)+1:]
    return n
pm_map={key(n):n for n in pm}
pp_map={key(f"{b} {m}"): (f"{b} {m}", c) for b,m,c in pp}
matches=0
for k,v in pp_map.items():
    if k in pm_map:
        matches+=1
print('pp entries', len(pp_map), 'matches', matches)
# show a few
shown=0
for k,v in pp_map.items():
    if k in pm_map and shown<10:
        print('MATCH:', v[0], '->', pm_map[k], 'cores', v[1])
        shown+=1