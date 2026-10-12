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
    from src.gestures import classify_frame
    cfg = {"swipe_vel_px_s": 900, "pinch_grab_px": 40, "pinch_release_px": 55}
    # T3-2: incomplete / missing landmark keys must skip, never KeyError.
    assert classify_frame({"wrist": (0, 0)}, [(0, 0.0), (10, 1.0)], cfg, False) == []
    assert classify_frame(None, [], cfg, False) == []
    # Fist takes precedence even with a fast swipe history.
    assert classify_frame(_fist_lm(), [(0, 0.0), (1000, 0.5)], cfg, False) == ["fist"]
    # Fast open-palm motion -> swipe_right; slow motion -> no swipe.
    assert classify_frame(_open_palm(), [(0, 0.0), (1000, 0.5)], cfg, False) == ["swipe_right"]
    assert classify_frame(_open_palm(), [(1000, 0.0), (0, 0.5)], cfg, False) == ["swipe_left"]
    assert classify_frame(_open_palm(), [(0, 0.0), (10, 1.0)], cfg, False) == []
    # Tight pinch spread -> pinch_in (zoom out); held wider spread -> pinch_out (zoom in).
    assert classify_frame(_open_palm(pinch=True), [(0, 0.0), (1, 1.0)], cfg, False) == ["pinch_in"]
    lm_mid = _open_palm(pinch=True)
    lm_mid["index_tip"] = (47, 0)
    assert classify_frame(lm_mid, [(0, 0.0), (1, 1.0)], cfg, True) == ["pinch_out"]
