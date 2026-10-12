#!/usr/bin/env python3
"""Drift Product — Top-Bar Notch + Live Window Control
Runs as a small always-on-top bar at the top of the screen (not a full
window). Controls actual Windows windows with hand gestures.

Usage (from repository root with Python 3.11):
    .\venv311\Scripts\python.exe -m src.app --live

Keyboard:
    Q / Esc = quit the loop
    L = toggle live mode (safe dry-run <-> real OS actions)
    R = reset geometry (detect new monitors)

Hand gestures (single-hand, webcam 0):
    Open palm show              -> idle_ready (enable / resume)
    Open palm push              -> grab focused window
    Fast swipe left/right       -> throw window to other monitor
    Pinch spread (thumb-index)  -> zoom out  (Ctrl + -)
    Pinch close                 -> zoom in   (Ctrl + =)
    Fist held 0.5s              -> freeze / kill-switch
"""
from __future__ import annotations
import argparse
import time
from collections import deque
from src.drift import ema, next_state, notch_text
from src.geometry import map_to_desktop
from src.util import load_config_with_overlay
from src.actuator import Actuator
from src import gestures


def _print_ascii(msg: str) -> None:
    from src.notch import ascii_text
    print(ascii_text(msg))


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Drift — hand-controlled windows")
    p.add_argument("--live", action="store_true", help="real Windows actions (default: dry-run safe)")
    p.add_argument("--dry-run", action="store_true", help="force safe dry-run (default)")
    p.add_argument("--camera", type=int, default=0)
    args = p.parse_args(argv)

    import cv2
    import mediapipe as mp
    from src.notch import create_pill, update_pill, ascii_text

    cfg = load_config_with_overlay("config.json", "config.user.json")
    cfg.setdefault("dry_run", True)
    cfg.setdefault("cooldown_s", 0.45)
    cfg.setdefault("linger_drop_s", 0.4)
    cfg.setdefault("fist_hold_s", 0.5)
    cfg.setdefault("pinch_grab_px", 40)
    cfg.setdefault("pinch_release_px", 55)
    cfg.setdefault("swipe_vel_px_s", 900)
    cfg.setdefault("roi_margin", 0.08)
    cfg.setdefault("monitors", {
        "d1": [1920, 1080], "d2": [2560, 1440],
        "total_w": 4480, "total_h": 1440, "seam_x": 1920,
    })
    if args.live:
        cfg["dry_run"] = False
    if args.dry_run:
        cfg["dry_run"] = True

    actuator = Actuator(cfg)
    state = "disabled"
    timers = {"last": -9.0, "fist_since": 0.0}
    smooth_x = None
    smooth_y = None
    hist: list[tuple[float, float]] = []
    last_seen: float | None = None
    last_open = 0.0
    fps = 0.0
    frames = 0
    fps_t0 = time.monotonic()
    demo_x, demo_y, demo_w, demo_h = 100, 200, 200, 80

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        _print_ascii("drift: no camera available (need webcam at index 0)")
        return 3

    mp_hands = mp.solutions.hands
    drawer = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.55,
        min_tracking_confidence=0.55,
    )

    pill = None
    try:
        pill = create_pill(notch_text(state))
    except Exception as exc:
        print(f"drift: top notch overlay unavailable ({exc}); HUD continues in camera window.")

    _print_ascii("drift: product running. Open palm activates. Q/Esc quits. L toggles live mode. R resets monitors.")
    print(f"dry_run={cfg.get('dry_run', True)}  monitors_total_w={cfg.get('monitors',{}).get('total_w',4480)}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            now = time.monotonic()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
            hand_lm = result.multi_hand_landmarks[0] if result.multi_hand_landmarks else None

            if hand_lm is not None:
                h, w = frame.shape[:2]
                pts = [(p.x * w, p.y * h) for p in hand_lm.landmark]
                lm = {
                    "wrist": pts[0],
                    "thumb_tip": pts[4],
                    "index_tip": pts[8], "index_pip": pts[6],
                    "middle_tip": pts[12], "middle_pip": pts[10],
                    "ring_tip": pts[16], "ring_pip": pts[14],
                    "pinky_tip": pts[20], "pinky_pip": pts[18],
                    "nx": hand_lm.landmark[9].x,
                    "ny": hand_lm.landmark[9].y,
                }
                drawer.draw_landmarks(frame, hand_lm, mp_hands.HAND_CONNECTIONS)
                last_seen = now
                open_palm = False
                try:
                    open_palm = gestures.is_open_palm(lm)
                except Exception:
                    open_palm = False
                if open_palm:
                    last_open = now

                hist.append((float(lm["wrist"][0]), now))
                hist = [(x, t) for x, t in hist if now - t < 0.50][-24:]
                holding = state in ("idle_ready", "grab", "pinch")
                events = gestures.classify_frame(lm, hist, cfg, holding)
                for evt in events:
                    prev = state
                    if state == "frozen" and evt != "palm_show":
                        continue
                    state = next_state(state, evt, now, cfg, timers)
                    if evt == "palm_show" and prev == "disabled":
                        _print_ascii("drift: palm activated")
                    if evt == "push_hold" and prev in ("idle_ready", "idle") and state == "grab":
                        cx, cy = map_to_desktop(lm["nx"], lm["ny"], cfg)
                        active_hwnd = actuator.active_window()
                        actuator.grab(active_hwnd, int(cx), int(cy))
                        demo_x = int(cx)
                        demo_y = int(cy)
                    elif evt in ("swipe_left", "swipe_right"):
                        actuator.throw_to_monitor("left" if evt == "swipe_left" else "right")
                    elif evt in ("pinch_in", "pinch_out", "pinch"):
                        direction = "out" if evt == "pinch_in" else "in"
                        actuator.zoom(direction)
                    elif evt == "fist" and state == "frozen":
                        actuator.drop()

                if state == "grab":
                    cx, cy = map_to_desktop(lm["nx"], lm["ny"], cfg)
                    smooth_x = cx if smooth_x is None else ema(smooth_x, cx, 0.30)
                    smooth_y = cy if smooth_y is None else ema(smooth_y, cy, 0.30)
                    actuator.drag_to(int(smooth_x), int(smooth_y))
                    demo_x = int(smooth_x) - 100
                    demo_y = int(smooth_y) - 30
                    if now - last_open > cfg.get("linger_drop_s", 0.4):
                        state = next_state(state, "release", now, cfg, timers)
                        actuator.drop()
                elif state == "pinch" and not any(e in ("pinch_in", "pinch_out", "pinch") for e in events):
                    state = next_state(state, "release", now, cfg, timers)
            else:
                if state == "grab" and last_seen is not None and now - last_seen > cfg.get("linger_drop_s", 0.4):
                    state = next_state(state, "release", now, cfg, timers)
                    actuator.drop()

            # HUD overlay: notch pill + visible target + mode line.
            h, w = frame.shape[:2]
            pill_w = 280 if state in ("disabled", "idle") else 300
            pill_h = 48
            px = (w - pill_w) // 2
            py = 8
            color_map = {
                "disabled": (80, 80, 90), "idle": (40, 150, 255),
                "idle_ready": (255, 210, 50), "grab": (60, 255, 180),
                "swipe": (255, 80, 230), "pinch": (120, 120, 255),
                "frozen": (60, 60, 255),
            }
            pill_color = color_map.get(state, (255, 255, 255))
            overlay = frame.copy()
            cv2.rectangle(overlay, (px - 18, py - 10), (px + pill_w + 18, py + pill_h + 10), pill_color, -1)
            cv2.addWeighted(overlay, 0.14, frame, 0.86, 0, frame)
            label_txt = (notch_text(state)).encode("ascii", errors="replace").decode("ascii")
            cv2.putText(frame, label_txt, (px + 30, py + 32), cv2.FONT_HERSHEY_DUPLEX, 0.72, (245, 245, 255), 1)

            # Window picker: which focused window Drift controls.
            picked = ""
            try:
                import win32gui
                picked = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                if not picked: picked = "(none focused)"
            except Exception:
                picked = "(dry-run: no window picked)"
            cv2.putText(frame, f"DRIFT WINDOW: {picked[:40]}", (14, h - 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 210, 50), 2)

            # Mode + FPS line.
            frames += 1
            if now - fps_t0 >= 1.0:
                fps = frames / (now - fps_t0)
                frames = 0
                fps_t0 = now
            dry_text = "DRY (SAFE)" if cfg.get("dry_run", True) else "LIVE (REAL ACTIONS)"
            cv2.putText(frame, f"{dry_text}  |  FPS {fps:04.1f}  |  state {state}",
                        (14, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 240, 255), 1)

            # Visible demo target (so dry-run feels like real product interaction).
            target_color = (60, 255, 170) if state == "grab" else (255, 210, 50) if state == "idle_ready" else (255, 255, 255)
            cv2.rectangle(frame, (demo_x, demo_y), (demo_x + 200, demo_y + 80), target_color, 2)
            cv2.putText(frame, "DRIFT TARGET", (demo_x + 18, demo_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (245, 245, 255), 2)
            cv2.putText(frame, "grab / throw / zoom", (demo_x + 18, demo_y + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.42, target_color, 1)

            try:
                update_pill(pill, notch_text(state))
            except Exception:
                pass
            cv2.imshow("Drift — AI Hand Control", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            if key == ord("l") or key == ord("L"):
                cfg["dry_run"] = not cfg.get("dry_run", True)
                actuator.cfg["dry_run"] = cfg.get("dry_run", True)
                _print_ascii(f"drift: {'LIVE' if not cfg['dry_run'] else 'DRY-RUN'} mode toggled")
            if key == ord("r") or key == ord("R"):
                cfg = load_config_with_overlay("config.json", "config.user.json")
                cfg.setdefault("dry_run", True)
                actuator.cfg = cfg
                _print_ascii("drift: config reset")
    finally:
        hands.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
