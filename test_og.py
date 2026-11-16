import requests, re
url='https://slickdeals.net/f/20301615-dewalt-atomic-20v-max-2-tool-combo-kit-w-5-8-sds-plus-hammer-drill-5ah-2ah-batteries-charger-299-free-shipping'
r=requests.get(url, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
print('status', r.status_code)
m=re.search(r'<meta property="og:image" content="([^"]+)"', r.text)
print('og:image', m.group(1) if m else None)
m2=re.search(r'<meta name="twitter:image" content="([^"]+)"', r.text)
print('twitter:image', m2.group(1) if m2 else None)