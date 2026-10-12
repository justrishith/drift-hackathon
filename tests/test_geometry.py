def test_map_center_and_seam():
    from src.geometry import map_to_desktop, which_monitor
    cfg = {"roi_margin": 0.08, "monitors": {"total_w": 4480, "total_h": 1440, "seam_x": 1920}}
    x, y = map_to_desktop(0.5, 0.5, cfg)
    assert x == 2240
    assert y == 720
    assert which_monitor(100, cfg) == 1
    assert which_monitor(3000, cfg) == 2
