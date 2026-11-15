import requests, re
from bs4 import BeautifulSoup
from pcpartpicker import API
def load_pm(url):
    r=requests.get(url, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=30)
    soup=BeautifulSoup(r.text,'html.parser')
    table=[t for t in soup.find_all('table') if 'CPU Name' in t.get_text()][0]
    rows=table.find_all('tr')
    out=[]
    for tr in rows[1:]:
        cells=[c.get_text(strip=True) for c in tr.find_all('td')]
        if cells: out.append(cells[0])
    return out
pm=load_pm('https://cpubenchmark.net/cpu-list/intel')+load_pm('https://cpubenchmark.net/cpu-list/amd')
api=API('us')
data=api.retrieve('cpu')
pp=[(p.brand,p.model,p.cores) for p in data['cpu']]
def model_token(n):
    toks=re.findall(r'[A-Za-z0-9][A-Za-z0-9\-]*', n)
    cand=[t for t in toks if any(c.isdigit() for c in t)]
    if not cand: return None
    return max(cand, key=len).lower()
pm_map={}
for n in pm:
    mt=model_token(n)
    if mt: pm_map.setdefault(mt, n)
pp_map={}
for b,m,c in pp:
    mt=model_token(f"{b} {m}")
    if mt: pp_map.setdefault(mt, (f"{b} {m}", c))
matches=sum(1 for k in pp_map if k in pm_map)
print('pm', len(pm), 'pp', len(pp), 'matches', matches)