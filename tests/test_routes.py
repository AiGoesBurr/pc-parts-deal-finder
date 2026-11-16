import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import cache
cache.CACHE_TTL = 10 ** 9
from app import app

def test_pages():
    c = app.test_client()
    paths = ["/", "/category/cpu", "/category/gpu", "/build", "/watchlist", "/deals", "/compat", "/leaderboard"]
    for p in paths:
        assert c.get(p).status_code == 200, p

def test_api_data():
    c = app.test_client()
    r = c.get("/api/data/cpu?eligible=1&limit=5")
    assert r.status_code == 200
    j = r.get_json()
    assert j["total"] >= 0
    assert isinstance(j["rows"], list)