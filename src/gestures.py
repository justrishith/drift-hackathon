import math


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

def finger_extended(wrist, pip, tip) -> bool:
    return _dist(wrist, tip) > _dist(wrist, pip) * 1.12

def is_pinch(lm: dict, grab_px: float, release_px: float, holding: bool) -> bool:
    d = _dist(lm["thumb_tip"], lm["index_tip"])
    return d < release_px if holding else d < grab_px

def is_fist(lm: dict) -> bool:
    w = lm["wrist"]
    pairs = [("index_pip", "index_tip"), ("middle_pip", "middle_tip"),
             ("ring_pip", "ring_tip"), ("pinky_pip", "pinky_tip")]
    return all(not finger_extended(w, lm[p], lm[t]) for p, t in pairs)


def is_open_palm(lm: dict) -> bool:
    """True when the four long fingers are extended and the hand is not pinching.

    The formula intentionally stays geometric so it works offline on a bare
    laptop with no training/calibration step. Thumb position is noisy across
    cameras, so v1 uses index/middle/ring/pinky extension as the open-palm
    signal and leaves thumb-index distance to pinch detection.
    """
    w = lm["wrist"]
    pairs = [("index_pip", "index_tip"), ("middle_pip", "middle_tip"),
             ("ring_pip", "ring_tip"), ("pinky_pip", "pinky_tip")]
    return all(finger_extended(w, lm[p], lm[t]) for p, t in pairs)

def palm_velocity(hist: list) -> float:
    (x0, t0), (x1, t1) = hist[0], hist[-1]
    dt = max(t1 - t0, 1e-6)
    return abs(x1 - x0) / dt

REQUIRED_KEYS = ("wrist", "thumb_tip", "index_tip", "index_pip",
                 "middle_pip", "middle_tip", "ring_pip", "ring_tip",
                 "pinky_pip", "pinky_tip")


def classify_frame(lm, hist: list, cfg: dict, holding: bool) -> list:
    """Map one frame's landmarks + palm history to state-machine events.

    Pure helper (no camera/display imports). T3-2: incomplete landmark
    dicts are skipped with a log line — never a KeyError into the loop.
    Uses existing is_fist / is_pinch / palm_velocity; pinch spread picks
    the zoom direction (tight -> pinch_in / zoom-out, wider-held spread
    -> pinch_out / zoom-in). Emits a subset of
    ["fist", "palm_show", "push_hold", "swipe_left", "swipe_right",
    "pinch_in", "pinch_out"].
    """
    if not isinstance(lm, dict) or any(k not in lm for k in REQUIRED_KEYS):
        print("drift: incomplete landmarks; skipping frame")
        return []
    try:
        if is_fist(lm):
            return ["fist"]
    except KeyError:
        print("drift: incomplete landmarks; skipping frame")
        return []
    events: list = []
    open_palm = False
    try:
        open_palm = is_open_palm(lm)
        if open_palm:
            events.append("push_hold" if holding else "palm_show")
    except KeyError:
        print("drift: incomplete landmarks; skipping frame")
        return []
    try:
        if hist is not None and len(hist) >= 2:
            if open_palm and palm_velocity(hist) >= cfg.get("swipe_vel_px_s", 900):
                dx = hist[-1][0] - hist[0][0]
                events.append("swipe_right" if dx > 0 else "swipe_left")
    except Exception:
        pass
    try:
        grab_px = cfg.get("pinch_grab_px", 40)
        release_px = cfg.get("pinch_release_px", 55)
        if is_pinch(lm, grab_px, release_px, holding):
            spread = _dist(lm["thumb_tip"], lm["index_tip"])
            events.append("pinch_in" if spread <= grab_px * 0.6 else "pinch_out")
    except KeyError:
        print("drift: incomplete landmarks; skipping frame")
        return []
    except Exception:
        pass
    return events


def hand_bbox(pts: list) -> tuple:
    """Pixel bounding box (x, y, w, h) of hand landmark points. Shape mode."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return (x0, y0, x1 - x0, y1 - y0)


def eye_aspect(outer, inner, upper, lower) -> float:
    """Eye aspect ratio; < ~0.21 means blinked. Points are (x, y) tuples."""
    return _dist(upper, lower) / max(_dist(outer, inner), 1e-6)
