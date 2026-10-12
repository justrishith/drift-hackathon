def test_dry_run_logs_no_os():
    from src.actuator import Actuator
    cfg = {"dry_run": True, "monitors": {"total_w": 4480, "total_h": 1440, "seam_x": 1920}}
    a = Actuator(cfg)
    a.move_cursor(2240, 720)
    a.grab(1234, 2240, 720)
    a.drag_to(3000, 700)
    assert a.log[0] == ("cursor", 2240, 720)
    assert a.log[1][0] == "grab"
    assert a.log[2] == ("drag", 3000, 700)
