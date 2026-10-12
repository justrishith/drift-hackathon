# CALIBRATE.md — Drift v1 calibration + soak verification

## 10s calibration procedure

1. Sit centred in front of the webcam, palm open facing the camera at normal
   use distance.
2. From `drift/`, run: `venv\Scripts\python.exe -m src.calibrate`
   (default capture window: 10 seconds).
3. Keep the open palm steady and in frame for the full 10 seconds.
4. The script writes `config.user.json` (user overlay only) with:
   `palm_px` (median), `pinch_grab_px` (= palm × 0.33),
   `pinch_release_px` (= palm × 0.45).
5. Never edit `config.json` — user overlay (`config.user.json`) takes
   precedence at runtime.
6. Live capture: **UNVERIFIED** pending Python 3.11 + webcam
   (no camera in this environment; capture was not run).

## 10-minute soak checklist

Dry-run first (`dry_run: true` in `config.json`):

- [ ] Run Drift in dry-run for 10 minutes of normal hand use.
- [ ] Zero stuck grabs in the Actuator log.
- [ ] Pinch grab/release thresholds feel correct with the calibrated overlay.

Then live (mark all live steps **UNVERIFIED** pending Python 3.11 + webcam):

- [ ] **UNVERIFIED** — Swipe crosses `seam_x=1920` both ways
      (primary → secondary and back).
- [ ] **UNVERIFIED** — Fist always freezes cursor/action.
- [ ] **UNVERIFIED** — Notch reflects state correctly throughout soak.

Note: automated verification in this environment covers import + full test
suite only. All live-camera steps require a webcam host and are UNVERIFIED.
