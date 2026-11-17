import html
import json
import os
import sys
import threading

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import images
import app as app_module


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def result(title, murl="https://img.example/a.jpg", purl="https://www.newegg.com/p/abc"):
    return {"t": title, "murl": murl, "purl": purl}


def test_same_part_accepts_the_same_product():
    assert images.same_part("AMD Ryzen 7 7800X3D", "AMD Ryzen 7 7800X3D 8-Core Processor")
    assert images.same_part("AMD Ryzen 7 7800X3D", "Ryzen 7 7800 X3D (8-core)")
    assert images.same_part("Intel Core i5-12400F", "Intel Core i5-12400F Desktop Processor")
    assert images.same_part("NVIDIA GeForce RTX 4070 Ti", "RTX 4070Ti Gaming")
    assert images.same_part("Samsung 990 PRO 2 TB", "Samsung 990 PRO 2TB NVMe SSD")
    assert images.same_part("Corsair Vengeance 32 GB DDR5 6000", "CORSAIR Vengeance DDR5 RAM 32GB 6000MHz")
    assert images.same_part("Patriot Viper II 'Sector 5' Edition 4 GB", "Patriot Viper II Sector 5 Edition 4GB")
    assert images.same_part("Thermalright Peerless Assassin 120 SE", "Thermalright Peerless Assassin 120 SE CPU Cooler")
    assert images.same_part("CORSAIR RM850x 850 W 80+ Gold", "Corsair RM850x 850W 80 Plus Gold")


def test_same_part_rejects_other_models_and_editions():
    assert not images.same_part("AMD Ryzen 7 7800X3D", "AMD Ryzen 9 9950X3D Procesador")
    assert not images.same_part("AMD Ryzen 5 7600", "AMD Ryzen 5 7600X")
    assert not images.same_part("NVIDIA GeForce RTX 4070", "NVIDIA GeForce RTX 4070 Ti")
    assert not images.same_part("NVIDIA GeForce RTX 4070 Ti", "NVIDIA GeForce RTX 4070 Ti SUPER")
    assert not images.same_part("Radeon RX 7900 XTX", "Radeon RX 7900 XT")
    assert not images.same_part("Samsung 990 EVO Plus 2 TB", "Samsung 990 EVO 2TB")
    assert not images.same_part("Samsung 990 PRO 2 TB", "Samsung 990 EVO 2TB")
    assert not images.same_part("Corsair Vengeance 32 GB DDR5 6000", "Corsair Dominator Platinum DDR5 6000")
    assert not images.same_part("Corsair Vengeance 32 GB DDR5 6000", "Corsair Vengeance 16GB DDR5 6000")
    assert not images.same_part("Be quiet! Dark Rock Pro 4", "be quiet! Dark Rock Pro 5 CPU Cooler")
    assert not images.same_part("Crucial CT32G4DFD8266 32 GB", "Celebrity news and photos")
    assert not images.same_part("AMD Ryzen 7 7800X3D", "")


def test_pick_photo_requires_a_retailer_or_maker_page():
    results = [
        result("GeForce RTX 5070 Ti 16GB Graphics Card", murl="https://news.example/x.jpg", purl="https://wccftech.com/story"),
        result("GeForce RTX 5070 Ti 16GB Graphics Card", murl="https://i.example/y.jpg", purl="https://www.newegg.com/p/abc"),
    ]
    assert images.pick_photo("NVIDIA GeForce RTX 5070 Ti", results) == "https://i.example/y.jpg"


def test_pick_photo_skips_insecure_and_unrelated_results():
    results = [
        result("AMD Ryzen 7 7800X3D", murl="http://insecure.example/x.jpg", purl="https://www.amazon.com/dp/1"),
        result("AMD Ryzen 9 9950X3D", murl="https://www.amazon.com/y.jpg", purl="https://www.amazon.com/dp/2"),
    ]
    assert images.pick_photo("AMD Ryzen 7 7800X3D", results) is None


def test_bing_results_parses_the_m_attributes(monkeypatch):
    items = [{"murl": "https://a.example/1.jpg", "purl": "https://www.amazon.com/dp/1", "t": "AMD Ryzen 7 7800X3D & more"}]
    cells = "".join('<a class="iusc" m="%s"></a>' % html.escape(json.dumps(item), quote=True) for item in items)
    monkeypatch.setattr(images.requests, "get", lambda *a, **k: FakeResponse("<html>%s</html>" % cells))
    assert images._bing_results("AMD Ryzen 7 7800X3D") == items


def test_deal_photo_reads_only_slickdeals_pages(monkeypatch):
    def no_fetch(*a, **k):
        raise AssertionError("should not fetch")
    monkeypatch.setattr(images.requests, "get", no_fetch)
    assert images._deal_photo("https://evil.example/page") is None
    assert images._deal_photo("http://[::1") is None


def test_deal_photo_reads_og_image(monkeypatch):
    page = '<html><head><meta property="og:image" content="https://static.slickdeals.net/a.jpg"></head></html>'
    monkeypatch.setattr(images.requests, "get", lambda *a, **k: FakeResponse(page))
    assert images._deal_photo("https://slickdeals.net/f/123-deal") == "https://static.slickdeals.net/a.jpg"


def test_find_photo_caches_misses_and_hits(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "CACHE_PATH", str(tmp_path / "images_v2.json"))
    monkeypatch.setattr(images, "_store", None)
    calls = []

    def lookup(name, link):
        calls.append(name)
        return (None, True)

    monkeypatch.setattr(images, "_lookup", lookup)
    assert images.find_photo("Mystery Part 9000") is None
    assert images.find_photo("Mystery Part 9000") is None
    assert calls == ["Mystery Part 9000"]


def test_lookup_reports_network_failures_as_unsettled(monkeypatch):
    def down(*a, **k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(images.requests, "get", down)
    assert images._lookup("AMD Ryzen 7 7800X3D", None) == (None, False)


def test_lookup_gives_up_when_bing_is_busy(monkeypatch):
    monkeypatch.setattr(images, "_bing_slots", threading.BoundedSemaphore(0))

    def no_fetch(*a, **k):
        raise AssertionError("should not query Bing")
    monkeypatch.setattr(images.requests, "get", no_fetch)
    assert images._lookup("AMD Ryzen 7 7800X3D", None) == (None, False)


def test_find_photo_does_not_cache_failed_lookups(tmp_path, monkeypatch):
    path = tmp_path / "images_v2.json"
    monkeypatch.setattr(images, "CACHE_PATH", str(path))
    monkeypatch.setattr(images, "_store", None)
    calls = []

    def flaky(name, link):
        calls.append(name)
        return (None, False)

    monkeypatch.setattr(images, "_lookup", flaky)
    assert images.find_photo("Some Part") is None
    assert images.find_photo("Some Part") is None
    assert len(calls) == 2
    assert not path.exists()


def test_api_image_redirects_to_a_verified_photo(monkeypatch):
    monkeypatch.setattr(app_module, "find_photo", lambda q, link=None: "https://m.media-amazon.com/images/I/x.jpg")
    r = app_module.app.test_client().get("/api/image?q=AMD+Ryzen+7+7800X3D&cat=cpu")
    assert r.status_code == 302
    assert r.headers["Location"] == "https://m.media-amazon.com/images/I/x.jpg"


def test_api_image_falls_back_to_a_category_placeholder(monkeypatch):
    monkeypatch.setattr(app_module, "find_photo", lambda q, link=None: None)
    r = app_module.app.test_client().get("/api/image?q=Unknown+Part&cat=gpu")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/api/placeholder?cat=gpu")


def test_placeholder_is_a_labelled_svg():
    r = app_module.app.test_client().get("/api/placeholder?cat=memory")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert b">RAM<" in r.data
