import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import ranking

def test_cpu_socket():
    assert ranking.cpu_socket("AMD Ryzen 5 5600 @ 3.50GHz") == "AM4"
    assert ranking.cpu_socket("AMD Ryzen 7 7800X3D @ 4.20GHz") == "AM5"
    assert ranking.cpu_socket("Intel Core i5-10400F @ 2.90GHz") == "LGA1200"
    assert ranking.cpu_socket("Intel Core i5-12400 @ 2.50GHz") == "LGA1700"
    assert ranking.cpu_socket("Intel Core i3-1005G1 @ 1.20GHz") is None

def test_is_current_cpu():
    assert ranking.is_current_cpu("AMD Ryzen 5 5600 @ 3.50GHz")
    assert ranking.is_current_cpu("Intel Core i5-12400 @ 2.50GHz")
    assert not ranking.is_current_cpu("AMD Ryzen 7 2700X @ 3.70GHz")
    assert not ranking.is_current_cpu("Intel Core i7-8700K @ 3.70GHz")

def test_is_current_gpu():
    assert ranking.is_current_gpu("GeForce RTX 5070 Ti")
    assert ranking.is_current_gpu("Radeon RX 6600")
    assert not ranking.is_current_gpu("GeForce RTX 3050 A Laptop GPU")
    assert not ranking.is_current_gpu("Radeon RX 580")

def test_case_fit():
    assert ranking.case_fits_board({"form_factor": "ATX"}, {"form_factor": "ATX Mid Tower"})
    assert not ranking.case_fits_board({"form_factor": "ATX"}, {"form_factor": "MicroATX Mini Tower"})
    assert ranking.case_fits_board({"form_factor": "Mini ITX"}, {"form_factor": "HTPC"})

def test_board_ram():
    assert ranking.board_ram_type({"socket": "AM4"}) == "DDR4"
    assert ranking.board_ram_type({"socket": "LGA1700", "name": "X D4"}) == "DDR4"
    assert ranking.board_ram_type({"socket": "LGA1700", "name": "X"}) is None

def test_psu():
    assert ranking.psu_required_watts({"tdp": 65}, {"score": 10000}) == 65 + 180 + 150