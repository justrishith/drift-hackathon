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
    import time

    def _main() -> None:
        try:
            import cv2
        except ImportError:
            print("drift: opencv (cv2) not installed; camera loop needs Python 3.11 + opencv. Manual-verify only.")
            raise SystemExit(2)
        try:
            import mediapipe as mp
        except ImportError:
            print("drift: mediapipe not installed; camera loop needs Python 3.11 + mediapipe. Manual-verify only.")
            raise SystemExit(2)

        from src.actuator import Actuator
        from src import gestures
        from src import geometry
        from src.util import load_config_with_overlay
        from src.notch import ascii_text

        cfg = load_config_with_overlay("config.json", "config.user.json")

        actuator = Actuator(cfg)
        state = "disabled"
        timers = {"last": -9.0, "fist_since": 0.0}
        smooth = None
        hist: list = []          # palm-x history: [(x_px, t_monotonic)]
        pinch_held = False
        last_seen: float | None = None
        tracker_warned = False

        # Hand tracker: created once, lazily; any failure degrades to a
        # no-gesture loop (honest stub) instead of crashing startup.
        hands = None
        try:
            mp_hands = mp.solutions.hands
            hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                                   min_detection_confidence=0.5)
        except Exception as exc:
            print(f"drift: hand tracker unavailable ({exc}); gesture events paused.")

        def _lm_from_frame(frame):
            """MediaPipe hand_landmarker -> landmarks dict (pixel space).

            Returns None when no hand is visible or the tracker is down.
            Keys match gestures.REQUIRED_KEYS plus nx/ny (palm-centre,
            normalised) for the cursor path. Never raises.
            """
            nonlocal tracker_warned
            if hands is None:
                if not tracker_warned:
                    print("drift: hand tracker unavailable; gesture events paused.")
                    tracker_warned = True
                return None
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = hands.process(rgb)
            except Exception as exc:
                if not tracker_warned:
                    print(f"drift: tracker error ({exc}); gesture events paused.")
                    tracker_warned = True
                return None
            try:
                marks = res.multi_hand_landmarks
                if not marks:
                    return None
                hl = marks[0]
                h, w = frame.shape[:2]
                pts = [(p.x * w, p.y * h) for p in hl.landmark]
                return {"wrist": pts[0], "thumb_tip": pts[4],
                        "index_tip": pts[8], "index_pip": pts[6],
                        "middle_tip": pts[12], "middle_pip": pts[10],
                        "ring_tip": pts[16], "ring_pip": pts[14],
                        "pinky_tip": pts[20], "pinky_pip": pts[18],
                        "nx": hl.landmark[9].x, "ny": hl.landmark[9].y}
            except Exception:
                return None

        def _push_notch() -> None:
            if notch is not None:
                try:
                    from src.notch import update_pill

                    update_pill(notch, notch_text(state))
                except Exception:
                    pass

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("drift: no camera available.")
            raise SystemExit(3)

        # Notch overlay (lazy; degrades gracefully headless).
        notch = None
        try:
            from src import notch as notch_mod

            notch = notch_mod.create_pill(notch_text(state))
        except Exception as exc:  # headless CI / no display
            print(f"drift: notch unavailable ({exc}); continuing headless.")
            notch = None

        print(ascii_text("drift: camera loop running. Make a fist+hold to freeze, palm to resume. Ctrl+C to quit."))
        last_shown = state
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    continue
                t = time.monotonic()
                lm = _lm_from_frame(frame)
                if lm is None:
                    # Linger-drop (F-C): a held grab released off-camera
                    # becomes "release" after linger_drop_s.
                    if (state == "grab" and last_seen is not None
                            and t - last_seen > cfg.get("linger_drop_s", 0.4)):
                        state = next_state(state, "release", t, cfg, timers)
                    if state != last_shown:
                        print(ascii_text(f"drift: {notch_text(state)}"))
                        last_shown = state
                    _push_notch()
                    if cv2.waitKey(1) & 0xFF == 27:  # Esc quits
                        break
                    continue
                last_seen = t
                try:
                    hist.append((float(lm["wrist"][0]), t))
                except Exception:
                    pass
                hist = [(x, tt) for x, tt in hist if t - tt < 0.6][-30:]
                for evt in gestures.classify_frame(lm, hist, cfg, pinch_held):
                    prev = state
                    state = next_state(state, evt, t, cfg, timers)
                    if evt in ("swipe_left", "swipe_right"):
                        actuator.throw_to_monitor("left" if evt == "swipe_left" else "right")
                    elif evt in ("pinch", "pinch_in", "pinch_out"):
                        pinch_held = True
                        if state == "pinch" or prev == "pinch":
                            actuator.zoom("out" if evt == "pinch_in" else "in")
                    elif evt == "fist":
                        pinch_held = False
                if pinch_held and state not in ("pinch", "grab"):
                    try:
                        pinch_held = bool(gestures.is_pinch(
                            lm, cfg.get("pinch_grab_px", 40),
                            cfg.get("pinch_release_px", 55), True))
                    except Exception:
                        pinch_held = False
                # Cursor path: palm-centre -> desktop -> ema smoothing.
                try:
                    if "nx" in lm and "ny" in lm:
                        cx, cy = geometry.map_to_desktop(lm["nx"], lm["ny"], cfg)
                        smooth = cx if smooth is None else ema(smooth, cx)
                        actuator.move_cursor(int(smooth), int(cy))
                except Exception as exc:
                    print(f"drift: cursor path skipped ({exc})")
                if state != last_shown:
                    print(ascii_text(f"drift: {notch_text(state)}"))
                    last_shown = state
                _push_notch()
                if cv2.waitKey(1) & 0xFF == 27:  # Esc quits
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            cv2.destroyAllWindows()

    _main()
