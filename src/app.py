"""Drift actual product loop: webcam hand control + animated HUD.

Run from the repository root:

    py -3.11 -m src.app          # safe dry-run from config.json
    py -3.11 -m src.app --live   # real Windows cursor/window/zoom actions

The module keeps imports lazy enough for tests to import pure helpers without
opening a camera. The visual surface is an OpenCV HUD so a bare laptop can demo
the product without a dual-monitor rig or separate overlay permissions.
"""

from __future__ import annotations

import argparse
import math
import time
from collections import deque
from dataclasses import dataclass, field

from src.drift import ema, next_state, notch_text
from src.geometry import map_to_desktop
from src.util import load_config_with_overlay


@dataclass
class ActionFeed:
    """Short-lived action messages for the demo HUD."""

    items: deque = field(default_factory=lambda: deque(maxlen=7))

    def add(self, label: str) -> None:
        self.items.appendleft((time.monotonic(), label))

    def alive(self) -> list[tuple[float, str]]:
        now = time.monotonic()
        return [(now - t, label) for t, label in self.items if now - t < 4.0]


@dataclass
class DemoWindow:
    """A visible in-HUD target so dry-run still feels like a real product."""

    x: float = 70.0
    y: float = 170.0
    w: float = 210.0
    h: float = 128.0
    scale: float = 1.0
    pulse_until: float = 0.0

    def drag_to(self, nx: float, ny: float, frame_w: int, frame_h: int) -> None:
        target_x = nx * (frame_w - self.w * self.scale - 40) + 20
        target_y = ny * (frame_h - self.h * self.scale - 120) + 95
        self.x += (target_x - self.x) * 0.30
        self.y += (target_y - self.y) * 0.30

    def throw(self, direction: str, frame_w: int) -> None:
        self.x = 24 if direction == "left" else frame_w - self.w * self.scale - 24
        self.pulse_until = time.monotonic() + 0.35

    def zoom(self, direction: str) -> None:
        if direction == "in":
            self.scale = min(1.45, self.scale + 0.08)
        else:
            self.scale = max(0.70, self.scale - 0.08)
        self.pulse_until = time.monotonic() + 0.28


def _display_config(cfg: dict) -> dict:
    """Prefer the real Windows virtual desktop so bare laptops map correctly."""
    try:
        import win32api

        total_w = win32api.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        total_h = win32api.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        primary_w = win32api.GetSystemMetrics(0)
        primary_h = win32api.GetSystemMetrics(1)
        if total_w > 0 and total_h > 0:
            cfg = dict(cfg)
            cfg["monitors"] = {
                "d1": [primary_w, primary_h],
                "d2": [max(total_w - primary_w, 0), total_h],
                "total_w": total_w,
                "total_h": total_h,
                "seam_x": primary_w,
            }
    except Exception:
        pass
    return cfg


def _rounded_rect(cv2, img, pt1, pt2, color, radius=22, thickness=-1):
    x1, y1 = pt1
    x2, y2 = pt2
    if thickness != -1:
        cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, thickness)
        cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, thickness)
        return
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
    cv2.circle(img, (x1 + radius, y1 + radius), radius, color, -1)
    cv2.circle(img, (x2 - radius, y1 + radius), radius, color, -1)
    cv2.circle(img, (x1 + radius, y2 - radius), radius, color, -1)
    cv2.circle(img, (x2 - radius, y2 - radius), radius, color, -1)


def _state_color(state: str) -> tuple[int, int, int]:
    return {
        "disabled": (80, 80, 90),
        "idle": (255, 150, 40),
        "idle_ready": (255, 210, 50),
        "grab": (60, 255, 180),
        "swipe": (255, 80, 230),
        "pinch": (120, 120, 255),
        "frozen": (60, 60, 255),
    }.get(state, (255, 255, 255))


def _draw_demo_window(cv2, frame, state: str, demo: DemoWindow) -> None:
    now = time.monotonic()
    color = _state_color(state)
    x1, y1 = int(demo.x), int(demo.y)
    x2, y2 = int(demo.x + demo.w * demo.scale), int(demo.y + demo.h * demo.scale)
    overlay = frame.copy()
    pulse = 1.0 if now < demo.pulse_until else 0.0
    glow_pad = int(10 + 18 * pulse)
    _rounded_rect(cv2, overlay, (x1 - glow_pad, y1 - glow_pad), (x2 + glow_pad, y2 + glow_pad), color, 24, -1)
    cv2.addWeighted(overlay, 0.12 + 0.10 * pulse, frame, 0.88 - 0.10 * pulse, 0, frame)
    overlay = frame.copy()
    _rounded_rect(cv2, overlay, (x1, y1), (x2, y2), (18, 20, 32), 18, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y1 + 28), (32, 34, 52), -1)
    for i, c in enumerate(((80, 90, 255), (80, 220, 255), (120, 255, 150))):
        cv2.circle(frame, (x1 + 18 + i * 18, y1 + 14), 6, c, -1)
    cv2.putText(frame, "DRIFT TARGET", (x1 + 18, y1 + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (245, 245, 255), 2)
    cv2.putText(frame, "grab / throw / zoom", (x1 + 18, y1 + 94), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)


def _draw_hud(cv2, frame, state: str, fps: float, dry_run: bool, feed: ActionFeed, trail, demo: DemoWindow):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    color = _state_color(state)

    _draw_demo_window(cv2, frame, state, demo)

    # Apple-style dynamic island: glow + pill + mode text.
    pill_w = 210 if state in ("disabled", "idle") else 360
    pill_h = 58
    x1 = (w - pill_w) // 2
    y1 = 16
    x2 = x1 + pill_w
    y2 = y1 + pill_h
    for i, alpha in enumerate((0.10, 0.08, 0.06)):
        pad = 18 + i * 12
        _rounded_rect(cv2, overlay, (x1 - pad, y1 - pad // 2), (x2 + pad, y2 + pad // 2), color, 30, -1)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        overlay = frame.copy()
    _rounded_rect(cv2, overlay, (x1, y1), (x2, y2), (12, 12, 18), 28, -1)
    cv2.addWeighted(overlay, 0.74, frame, 0.26, 0, frame)
    cv2.circle(frame, (x1 + 30, y1 + pill_h // 2), 8 + int((time.time() * 4) % 4), color, -1)
    cv2.putText(frame, notch_text(state).encode("ascii", "replace").decode("ascii"),
                (x1 + 55, y1 + 37), cv2.FONT_HERSHEY_DUPLEX, 0.78, (245, 245, 255), 1)

    mode = "DRY-RUN + VISIBLE DEMO WINDOW" if dry_run else "LIVE WINDOWS CONTROL"
    cv2.putText(frame, mode, (18, h - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (120, 255, 170) if dry_run else (70, 90, 255), 2)
    cv2.putText(frame, "L toggles live | Q/Esc quits", (18, h - 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (230, 230, 240), 1)
    cv2.putText(frame, f"FPS {fps:04.1f}", (w - 150, h - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 240), 2)

    # Neon trail for wrist/palm movement.
    pts = list(trail)
    for i in range(1, len(pts)):
        age = i / max(len(pts), 1)
        thickness = max(1, int(age * 8))
        cv2.line(frame, pts[i - 1], pts[i], color, thickness)

    # Action feed.
    yy = 104
    for age, label in feed.alive():
        fade = max(0.0, 1.0 - age / 4.0)
        tint = tuple(int(c * fade + 35 * (1 - fade)) for c in color)
        cv2.putText(frame, label, (24, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.64, tint, 2)
        yy += 30


def _landmarks_from_mediapipe(hand_landmarks, w: int, h: int) -> dict:
    pts = [(p.x * w, p.y * h) for p in hand_landmarks.landmark]
    return {
        "wrist": pts[0],
        "thumb_tip": pts[4],
        "index_tip": pts[8], "index_pip": pts[6],
        "middle_tip": pts[12], "middle_pip": pts[10],
        "ring_tip": pts[16], "ring_pip": pts[14],
        "pinky_tip": pts[20], "pinky_pip": pts[18],
        "nx": hand_landmarks.landmark[9].x, "ny": hand_landmarks.landmark[9].y,
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drift hand-control app")
    parser.add_argument("--live", action="store_true", help="turn on real Windows actions (overrides dry_run)")
    parser.add_argument("--dry-run", action="store_true", help="force safe dry-run")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args(argv)

    import cv2
    import mediapipe as mp
    from src import gestures
    from src.actuator import Actuator
    from src.notch import ascii_text, create_pill, update_pill

    cfg = _display_config(load_config_with_overlay("config.json", "config.user.json"))
    if args.live:
        cfg["dry_run"] = False
    if args.dry_run:
        cfg["dry_run"] = True
    cfg.setdefault("grab_hold_s", 0.18)

    actuator = Actuator(cfg)
    feed = ActionFeed()
    state = "disabled"
    timers = {"last": -9.0, "fist_since": 0.0}
    hist: list[tuple[float, float]] = []
    trail = deque(maxlen=32)
    smooth_x = None
    smooth_y = None
    active_hwnd = None
    last_seen = None
    last_open = 0.0
    fps = 0.0
    frames = 0
    fps_t0 = time.monotonic()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("drift: no camera available")
        return 3

    mp_hands = mp.solutions.hands
    drawer = mp.solutions.drawing_utils
    hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                           min_detection_confidence=0.55,
                           min_tracking_confidence=0.55)

    pill = None
    try:
        pill = create_pill(notch_text(state))
    except Exception as exc:
        print(ascii_text(f"drift: top notch unavailable ({exc}); using camera HUD only."))

    print(ascii_text("drift: product loop running. Palm activates/grabs, pinch zooms, swipe throws, fist freezes. Q/Esc quits."))
    feed.add("show open palm to activate")

    # Demo window for visible dry-run feedback.
    demo = DemoWindow()

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
                lm = _landmarks_from_mediapipe(hand_lm, w, h)
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
                        feed.add("activated: palm detected")
                    if evt == "push_hold" and prev in ("idle_ready", "idle") and state == "grab":
                        cx, cy = map_to_desktop(lm["nx"], lm["ny"], cfg)
                        active_hwnd = actuator.active_window()
                        actuator.grab(active_hwnd, cx, cy)
                        demo.drag_to(lm["nx"], lm["ny"], w, h)
                        feed.add("grab window")
                    elif evt in ("swipe_left", "swipe_right"):
                        actuator.throw_to_monitor("left" if evt == "swipe_left" else "right")
                        demo.throw("left" if evt == "swipe_left" else "right", w)
                        feed.add("throw " + ("left" if evt == "swipe_left" else "right"))
                    elif evt in ("pinch_in", "pinch_out", "pinch"):
                        direction = "out" if evt == "pinch_in" else "in"
                        actuator.zoom(direction)
                        demo.zoom(direction)
                        feed.add("zoom " + direction)
                    elif evt == "fist" and state == "frozen":
                        actuator.drop()
                        feed.add("freeze kill-switch")

                if state == "grab":
                    cx, cy = map_to_desktop(lm["nx"], lm["ny"], cfg)
                    smooth_x = cx if smooth_x is None else ema(smooth_x, cx, 0.30)
                    smooth_y = cy if smooth_y is None else ema(smooth_y, cy, 0.30)
                    actuator.drag_to(int(smooth_x), int(smooth_y))
                    demo.drag_to(lm["nx"], lm["ny"], w, h)
                    trail.append((int(lm["wrist"][0]), int(lm["wrist"][1])))
                    if now - last_open > cfg.get("linger_drop_s", 0.4):
                        state = next_state(state, "release", now, cfg, timers)
                        actuator.drop()
                        feed.add("drop window")
                elif state == "pinch" and not any(e in ("pinch_in", "pinch_out", "pinch") for e in events):
                    state = next_state(state, "release", now, cfg, timers)

                if state == "swipe" and now - timers.get("last", 0) > 0.35:
                    state = "idle"
            else:
                if state == "grab" and last_seen is not None and now - last_seen > cfg.get("linger_drop_s", 0.4):
                    state = next_state(state, "release", now, cfg, timers)
                    actuator.drop()
                    feed.add("drop: hand lost")

            frames += 1
            if now - fps_t0 >= 0.5:
                fps = frames / (now - fps_t0)
                frames = 0
                fps_t0 = now

            _draw_hud(cv2, frame, state, fps, cfg.get("dry_run", True), feed, trail, demo)
            try:
                update_pill(pill, notch_text(state))
            except Exception:
                pass
            cv2.imshow("Drift - AI Hand Control", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
    finally:
        hands.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
