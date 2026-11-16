import requests
from bs4 import BeautifulSoup
r=requests.get('https://www.techpowerup.com/cpu-specs/', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
soup=BeautifulSoup(r.text,'html.parser')
tables=soup.find_all('table')
print('tables', len(tables))
for i,t in enumerate(tables):
    rows=t.find_all('tr')
    print('table',i,'rows',len(rows))
    if rows and len(rows)>1:
        print('  header', [c.get_text(strip=True) for c in rows[0].find_all(['th','td'])][:6])
        print('  row1', [c.get_text(strip=True) for c in rows[1].find_all(['th','td'])][:6])