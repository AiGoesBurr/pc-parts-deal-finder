import cloudscraper, re
s=cloudscraper.create_scraper()
q='AMD Ryzen 7 7800X3D'
r=s.get('https://www.amazon.com/s?k='+q.replace(' ','+'), timeout=20)
print('status', r.status_code)
# find product image
imgs=re.findall(r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9\._-]+\.jpg', r.text)
print('imgs', len(imgs))
print(imgs[:5])