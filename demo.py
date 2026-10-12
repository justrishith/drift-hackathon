#!/usr/bin/env python3
"""
Drift v1 — Hand-Gesture Window Controller (Hackathon Demo)
===========================================================

AI: MediaPipe Tasks hand_landmarker (21 landmarks) classifies
open-palm, pinch, fist, and swipe in real-time.

On a bare laptop: console output only — no OS window calls
(dry-run mode). Run `py -3.11 demo.py` to try it.

Usage:
    py -3.11 demo.py

Controls (console-displayed, no OS calls in demo mode):
  - Open-palm → "idle_ready" (gesture detected, ready to grab)
  - Pinch spread → "pinch" (zoom out)
  - Pinch close → "pinch_release" (zoom in)
  - Fist held → "frozen" (kill-switch)
  - Space or ESC to exit
"""

import sys
import time
import json
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

def load_config(path="config.json"):
    """Load drift config from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _dist(a, b):
    """Euclidean distance between two (x,y) points."""
    import math
    return math.hypot(a[0] - b[0], a[1] - b[1])

def finger_extended(wrist, pip, tip, lm):
    """Check if a finger is extended using handcontrol formula."""
    return _dist(lm["wrist"], lm[tip]) > _dist(lm["wrist"], lm[pip]) * 1.12

def is_pinch(lm, grab_px, release_px, holding):
    """Hysteretic pinch detection."""
    d = _dist(lm["thumb_tip"], lm["index_tip"])
    return d < (release_px if holding else grab_px)

def is_fist(lm):
    """Check if hand is in a fist (all fingers folded)."""
    w = lm["wrist"]
    pairs = [("index_pip", "index_tip"), ("middle_pip", "middle_tip"),
             ("ring_pip", "ring_tip"), ("pinky_pip", "pinky_tip")]
    return all(not finger_extended(w, lm[p], lm[t]) for p, t in pairs)

def palm_velocity(hist):
    """Px/s based on x-position history."""
    if len(hist) < 2:
        return 0.0
    (x0, _), (x1, t1) = hist[0], hist[-1]
    dt = max(t1 - hist[0][1], 1e-6)
    return abs(x1 - x0) / dt

def main():
    print("""
 ██████╗ ██████╗  ██████╗ ██████╗  ██████╗ ██████╗ 
██╔════╝██╔═══██╗██╔═══██╗██╔══██╗██╔══██╗██╔══██╗
██║     ██║   ██║██║   ██║██████╔╝██████╔╝██████╔╝
██║     ██║   ██║██║   ██║██╔══██╗██╔══██╗██╔══██╗
╚██████╗╚██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝
 ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝""")
    print("\nDrift v1 — Hand Gesture Classifier (demo mode)")
    print("=" * 50)
    print("Press ESC or Q to quit\n")

    # Load config
    try:
        cfg = load_config()
    except FileNotFoundError:
        cfg = {
            "dry_run": True,
            "cooldown_s": 0.45,
            "linger_drop_s": 0.4,
            "fist_hold_s": 0.5,
            "pinch_grab_px": 40,
            "pinch_release_px": 55,
            "swipe_vel_px_s": 900,
            "roi_margin": 0.08,
            "monitors": {"d1": [1920, 1080], "d2": [2560, 1440], "total_w": 4480, "total_h": 1440, "seam_x": 1920}
        }
        print("Using default config (no config.json found)")

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    import cv2
    import numpy as np

    # Configure hand landmarker
    base_options = mp_python.BaseOptions(model_asset_path=None)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=1,
        running_mode=mp_python.RunningMode.LIVE_STREAM,
        result_callback=None,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector = vision.HandLandmarker.create_from_options(options)

    # OpenCV camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam. Quitting.")
        return

    # State machine (simplified, console-mode)
    state = "disabled"
    timers = {"last": 0.0, "fist_since": 0.0}
    pinch_history = []
    velocity_history = []

    fps_history = []
    frame_count = 0
    t0 = time.time()

    print("\nCamera started. Make sure your hand is visible.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Failed to grab frame")
                break

            # Flip for mirror view
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape

            # Convert to MediaPipe Image
            mp_image = mp_python.Image(image_format=mp_python.ImageFormat.SRGB, data=rgb)

            # Detect
            detection_time_ms = int(time.time() * 1000)
            result = detector.detect(mp_image, detection_time_ms)

            now = time.time()

            # --- State machine (console-visible) ---
            if result.hand_landmarks:
                lm = result.hand_landmarks[0]  # single hand

                # Convert landmarks to dict with pixel coords
                landm = {}
                for i, lm_pt in enumerate(lm):
                    # MediaPipe landmark indices
                    landm[i] = (lm_pt.x * w, lm_pt.y * h)

                # Simplified mapping using known landmark indices
                # 0=wrist, 4=thumb_tip, 8=index_tip, 6=index_pip, 
                # 12=middle_tip, 10=middle_pip, 16=ring_tip, 14=ring_pip,
                # 20=pinky_tip, 18=pinky_pip

                # Build dict with named keys (matching gestures module expectations)
                named_lm = {
                    "wrist": (landm[0][0], landm[0][1]),
                    "thumb_tip": (landm[4][0], landm[4][1]),
                    "index_tip": (landm[8][0], landm[8][1]),
                    "index_pip": (landm[6][0], landm[6][1]),
                    "middle_tip": (landm[12][0], landm[12][1]),
                    "middle_pip": (landm[10][0], landm[10][1]),
                    "ring_tip": (landm[16][0], landm[16][1]),
                    "ring_pip": (landm[14][0], landm[14][1]),
                    "pinky_tip": (landm[20][0], landm[20][1]),
                    "pinky_pip": (landm[18][0], landm[18][1]),
                }

                # Gesture classification
                pinch_holding = True  # simplified
                pinch = is_pinch(named_lm, cfg.get("pinch_grab_px", 40),
                                 cfg.get("pinch_release_px", 55), pinch_holding)
                fist = is_fist(named_lm)

                # State transitions (console display)
                if state == "disabled" and fist:
                    state = "idle_ready"
                    print(f"[{now:.1f}] STATE: {state}  (fist detected — enable with open-palm)")
                elif state == "idle_ready" and not fist:
                    state = "idle"
                elif state == "idle" and pinch:
                    state = "pinch"
                    print(f"[{now:.1f}] STATE: {state}  (pinch — zoom out)")
                elif state == "pinch" and not pinch:
                    state = "idle"
                    print(f"[{now:.1f}] STATE: {state}  (pinch released — zoom in)")
                elif state == "idle" and fist and (now - timers.get("fist_since", 0) >= cfg.get("fist_hold_s", 0.5)):
                    state = "frozen"
                    timers["fist_since"] = now
                    print(f"[{now:.1f}] STATE: {state}  (fist held 0.5s — kill-switch engaged)")
                elif state == "frozen" and not fist:
                    state = "idle_ready"
                    print(f"[{now:.1f}] STATE: {state}  (fist released — ready)")

                # Draw landmarks on frame for video
                for landmark in lm:
                    cx, cy = int(landmark.x * w), int(landmark.y * h)
                    cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)

            # FPS display
            frame_count += 1
            if now - t0 >= 1.0:
                fps = frame_count / (now - t0)
                fps_history.append(fps)
                if len(fps_history) > 10:
                    fps_history.pop(0)
                avg_fps = sum(fps_history) / len(fps_history) if fps_history else 0
                print(f"\rFPS: {avg_fps:.1f}  |  State: {state}", end="", flush=True)
                frame_count = 0
                t0 = now

            # Show console state on frame (semi-transparent overlay)
            overlay = frame.copy()
            cv2.rectangle(overlay, (10, 10), (500, 80), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
            cv2.putText(frame, f"Drift v1 | State: {state} | FPS: {avg_fps:.1f}",
                       (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Show window
            cv2.imshow("Drift — Hand Gesture Classifier", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q') or key == ord(' '):  # ESC, Q, Space
                break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"\n\nFinal state: {state}")
        print("Bye! 👋")

if __name__ == "__main__":
    main()