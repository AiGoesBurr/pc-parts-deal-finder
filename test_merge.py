from pcpartpicker import API
api=API("us")
data=api.retrieve("cpu")
print(len(data["cpu"]))
for p in data["cpu"][:5]:
    print(repr(p.brand), repr(p.model), getattr(p,'cores',None))
# passmark sample
import requests
from bs4 import BeautifulSoup
r=requests.get('https://cpubenchmark.net/cpu-list/amd', headers={'User-Agent':'Mozilla/5.0'}, timeout=30)
soup=BeautifulSoup(r.text,'html.parser')
table=[t for t in soup.find_all('table') if 'CPU Name' in t.get_text()][0]
rows=table.find_all('tr')
print('pm sample:', [c.get_text(strip=True) for c in rows[10].find_all('td')])
print('pm name sample2:', [c.get_text(strip=True) for c in rows[100].find_all('td')][:1])
