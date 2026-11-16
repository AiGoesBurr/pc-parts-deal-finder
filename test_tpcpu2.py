import requests, re
from bs4 import BeautifulSoup
r=requests.get('https://www.techpowerup.com/cpu-specs/', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
soup=BeautifulSoup(r.text,'html.parser')
# find table
table=[t for t in soup.find_all('table')][0]
rows=table.find_all('tr')
print('rows', len(rows))
# parse name and cores
names=[]
for tr in rows[1:]:
    cells=[c.get_text(strip=True) for c in tr.find_all('td')]
    if len(cells)>=3:
        name=cells[0]
        cores=cells[2]
        names.append((name,cores))
print('sample', names[:5])
# match against passmark names
import requests as rq
r2=rq.get('https://cpubenchmark.net/cpu-list/amd', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=30)
soup2=BeautifulSoup(r2.text,'html.parser')
table2=[t for t in soup2.find_all('table') if 'CPU Name' in t.get_text()][0]
pm=[tr.find_all('td')[0].get_text(strip=True) for tr in table2.find_all('tr')[1:] if tr.find_all('td')]
def norm(n):
    n=n.lower(); n=re.sub(r'@\s*[\d\.]+\s*ghz','',n); n=re.sub(r'\s+',' ',n).strip(); return n
def token(n):
    toks=re.findall(r'[A-Za-z0-9][A-Za-z0-9\-]*', n); cand=[t for t in toks if any(c.isdigit() for c in t)]; return max(cand,key=len).lower() if cand else None
tp_map={}
for name,cores in names:
    t=token(name)
    if t: tp_map.setdefault(t, cores)
pm_tokens={token(n): n for n in pm}
matches=sum(1 for t in tp_map if t in pm_tokens)
print('tp entries', len(tp_map), 'matches', matches)