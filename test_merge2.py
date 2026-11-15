import requests
r=requests.get('https://cpubenchmark.net/cpu-list/amd', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=30)
print('status', r.status_code, len(r.text))
print('CPU Name' in r.text)
from bs4 import BeautifulSoup
soup=BeautifulSoup(r.text,'html.parser')
print('tables', len(soup.find_all('table')))
for t in soup.find_all('table'):
    print(t.get_text()[:80].replace('\n',' '))
