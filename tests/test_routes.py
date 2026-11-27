import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import cache
cache.CACHE_TTL = 10 ** 9
from app import app
import app as app_module

def test_pages():
    c = app.test_client()
    paths = ["/", "/category/cpu", "/category/gpu", "/build", "/watchlist", "/deals", "/compat", "/leaderboard", "/methodology", "/sources", "/privacy", "/savedbuilds", "/buildtemplates"]
    for p in paths:
        assert c.get(p).status_code == 200, p

def test_api_data():
    c = app.test_client()
    r = c.get("/api/data/cpu?eligible=1&limit=5")
    assert r.status_code == 200
    j = r.get_json()
    assert j["total"] >= 0
    assert isinstance(j["rows"], list)


def test_trust_fixes():
    c = app.test_client()
    home = c.get("/").get_data(as_text=True)
    assert "Visitors:" not in home
    assert "EPYC" not in home
    assert "Best value CPUs" in home
    assert "Email alerts are not available yet" not in home

    deep = c.get("/category/cpu?q=Ryzen").get_data(as_text=True)
    assert 'value="Ryzen"' in deep

    sub = c.post("/api/subscribe", data={"email": "test@example.com"})
    assert sub.status_code == 503
    live = c.get("/api/liveprice?q=rtx+5070")
    assert live.status_code == 410


def test_deal_classifier_and_dedupe():
    assert not app_module._is_pc_part("Narst Smart Baby Video Monitor")
    assert not app_module._is_pc_part("TORRAS COOLiFY Cyber AI Neck Air Conditioner")
    assert not app_module._is_pc_part("GIGABYTE GAMING A16 16\" RTX 5070 Laptop")
    assert not app_module._is_pc_part("ORZbb Mini Magnetic Tiles Road Set with Travel Case")
    assert not app_module._is_pc_part("DJI Mic Mini Charging Case")
    assert not app_module._is_pc_part("ECO-WORTHY 24V 100Ah LiFePO4 Metal-Case Batteries")
    assert app_module._is_pc_part("AMD Ryzen 7 9800X3D Desktop Processor")
    assert app_module._is_pc_part("be quiet! Shadow Base 800 FX Mid-Tower ATX Gaming Case")
    assert app_module._deal_category("be quiet! Shadow Base 800 FX Mid-Tower ATX Gaming Case") == "case"
    assert (app_module._canonical_deal_key("https://slickdeals.net/f/123-deal?utm_source=rss")
            == app_module._canonical_deal_key("https://slickdeals.net/f/123-deal/"))
    dell_a = app_module._deal_model_key('Dell S3426DW 34" 3440x1440 Monitor', 179.99)
    dell_b = app_module._deal_model_key("Dell 34 WQHD Monitor - S3426DW", 179.99)
    assert dell_a and dell_a == dell_b
    assert app_module._deal_model_key("GeForce RTX 5070", 599.99) is None
    assert app_module._deal_model_key("Radeon RX 9070", 599.99) is None


def test_refresh_auth_fails_closed(monkeypatch):
    monkeypatch.delenv("SCRAPE_TOKEN", raising=False)
    monkeypatch.delenv("ENABLE_REFRESH", raising=False)
    c = app.test_client()
    assert c.post("/refresh").status_code == 403
    assert c.post("/api/scrape").status_code == 403