import math
def test_pinch_hysteresis_and_fist():
    from src.gestures import is_pinch, is_fist
    lm_close = {"wrist": (0, 0), "thumb_tip": (0, 0), "index_tip": (10, 0), "index_pip": (0, 50),
                "middle_tip": (5, 5), "ring_tip": (5, 5), "pinky_tip": (5, 5),
                "middle_pip": (0, 50), "ring_pip": (0, 50), "pinky_pip": (0, 50)}
    assert is_pinch(lm_close, 40, 55, False) is True
    lm_mid = dict(lm_close); lm_mid["index_tip"] = (47, 0)
    assert is_pinch(lm_mid, 40, 55, True) is True
    assert is_pinch(lm_mid, 40, 55, False) is False
    assert is_fist(lm_close) is True


def _open_palm(pinch: bool = False):
    lm = {"wrist": (0, 0), "thumb_tip": (0, 0),
          "index_tip": (10, 0) if pinch else (200, 0),
          "index_pip": (0, 50), "index_tip_dup": None,
          "middle_tip": (0, 100), "ring_tip": (0, 100), "pinky_tip": (0, 100),
          "middle_pip": (0, 50), "ring_pip": (0, 50), "pinky_pip": (0, 50)}
    del lm["index_tip_dup"]
    lm["index_tip"] = (10, 0) if pinch else (200, 0)
    return lm


def _fist_lm():
    return {"wrist": (0, 0), "thumb_tip": (0, 0), "index_tip": (10, 0),
            "index_pip": (0, 50), "middle_tip": (5, 5), "ring_tip": (5, 5),
            "pinky_tip": (5, 5), "middle_pip": (0, 50), "ring_pip": (0, 50),
            "pinky_pip": (0, 50)}


def test_classify_frame_guards_thresholds_and_zoom():
    from src.gestures import classify_frame, is_open_palm
    cfg = {"swipe_vel_px_s": 900, "pinch_grab_px": 40, "pinch_release_px": 55}
    # T3-2: incomplete / missing landmark keys must skip, never KeyError.
    assert classify_frame({"wrist": (0, 0)}, [(0, 0.0), (10, 1.0)], cfg, False) == []
    assert classify_frame(None, [], cfg, False) == []
    # Fist takes precedence even with a fast swipe history.
    assert classify_frame(_fist_lm(), [(0, 0.0), (1000, 0.5)], cfg, False) == ["fist"]
    assert is_open_palm(_open_palm()) is True
    # Fast open-palm motion -> swipe_right; slow motion -> no swipe.
    assert classify_frame(_open_palm(), [(0, 0.0), (1000, 0.5)], cfg, False) == ["palm_show", "swipe_right"]
    assert classify_frame(_open_palm(), [(1000, 0.0), (0, 0.5)], cfg, False) == ["palm_show", "swipe_left"]
    assert classify_frame(_open_palm(), [(0, 0.0), (10, 1.0)], cfg, False) == ["palm_show"]
    assert classify_frame(_open_palm(), [(0, 0.0), (10, 1.0)], cfg, True) == ["push_hold"]
    # Tight pinch spread -> pinch_in (zoom out); held wider spread -> pinch_out (zoom in).
    assert classify_frame(_open_palm(pinch=True), [(0, 0.0), (1, 1.0)], cfg, False) == ["pinch_in"]
    lm_mid = _open_palm(pinch=True)
    lm_mid["index_tip"] = (47, 0)
    assert classify_frame(lm_mid, [(0, 0.0), (1, 1.0)], cfg, True) == ["pinch_out"]


def test_extension_ratio_open_vs_fist():
    from src.gestures import extension_ratio
    assert extension_ratio(_open_palm()) > 1.22
    assert extension_ratio(_fist_lm()) < 1.10


def test_splay_burst_clip2_pattern():
    # Calibrated from Camera Roll clip WIN_20261012_20_38_01 (wrist->middle_pip
    # metric): open ~1.30, close 0.61 at t=2.76, burst open 1.29 at t=2.96.
    from src.gestures import is_splay_burst
    burst = [(1.30, 0.0), (1.28, 0.1), (0.61, 0.2), (1.29, 0.3)]
    assert is_splay_burst(burst) is True
    steady_open = [(1.29, 0.0), (1.30, 0.1), (1.28, 0.2), (1.31, 0.3)]
    assert is_splay_burst(steady_open) is False
    slow_open = [(0.90, 0.0), (1.10, 0.5), (1.30, 1.0)]
    assert is_splay_burst(slow_open) is False


def test_hand_bbox_union_two_hands():
    from src.gestures import hand_bbox
    left = [(0, 0), (40, 60)]
    right = [(200, 10), (260, 80)]
    assert hand_bbox(left + right) == (0, 0, 260, 80)


def test_fullscreen_logs_dry_run():
    from src.actuator import Actuator
    a = Actuator({"dry_run": True})
    a.fullscreen()
    assert a.log == [("fullscreen",)]
