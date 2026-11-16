import requests
r=requests.get('https://www.techpowerup.com/cpu-specs/', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
t=r.text
print('Ryzen count', t.count('Ryzen'))
print('Core i7 count', t.count('Core i7'))
# check for table rows
import re
print('tr count', t.count('<tr'))
print('td count', t.count('<td'))
# find a cpu name
idx=t.find('Ryzen 7 7800X3D')
print(repr(t[idx-50:idx+100]) if idx!=-1 else 'not found')