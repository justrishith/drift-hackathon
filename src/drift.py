"""Drift gesture state machine + camera loop (Task 5).

Pure functions (next_state / notch_text / ema) are import-safe: no camera,
mediapipe, display, or OS calls at module scope. The camera loop lives
entirely under `if __name__ == "__main__":` with lazy imports.
"""


def next_state(state: str, evt: str, t: float, cfg: dict, timers: dict) -> str:
    if t - timers.get("last", -9.0) < cfg["cooldown_s"] and evt in ("swipe_left", "swipe_right", "pinch_out", "pinch_in", "pinch"):
        return state
    if evt == "palm_show" and state in ("disabled", "idle"):
        timers["last"] = t
        return "idle_ready"
    if evt == "push_hold" and state in ("idle_ready", "idle"):
        timers["last"] = t
        return "grab"
    if evt == "release" and state == "grab":
        timers["last"] = t
        return "idle"
    if evt in ("swipe_left", "swipe_right") and state in ("idle", "idle_ready", "grab"):
        timers["last"] = t
        return "swipe"
    if evt == "fist":
        if timers.get("fist_since", 0.0) == 0.0:
            timers["fist_since"] = t
            return state
        if t - timers["fist_since"] >= cfg["fist_hold_s"]:
            timers["fist_since"] = 0.0
            return "frozen"
        return state
    if evt == "palm_show" and state == "frozen":
        return "idle_ready"
    # Fix-wave additive path (T5-4a): pinch events reach the "pinch" state
    # so notch shows zoom + the loop fires Actuator.zoom. No existing branch
    # above is modified; prior tests never send pinch events.
    if evt in ("pinch", "pinch_in", "pinch_out") and state in ("idle", "idle_ready", "grab", "swipe"):
        timers["last"] = t
        return "pinch"
    if evt == "release" and state == "pinch":
        timers["last"] = t
        return "idle"
    return state


def notch_text(state: str) -> str:
    return {"disabled": "· drift", "idle": "● drift", "idle_ready": "● drift ready",
            "grab": "◉ push", "swipe": "⇄ throw", "pinch": "⤢ zoom", "frozen": "■ frozen"}.get(state, "● drift")


def ema(prev: float, cur: float, alpha: float = 0.35) -> float:
    return alpha * cur + (1.0 - alpha) * prev


if __name__ == "__main__":
    from src.app import run

    raise SystemExit(run())
