# src/calibrate.py
import json, time


def main(seconds: int = 10) -> None:
    import cv2
    cap = cv2.VideoCapture(0)
    widths: list = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        ok, _ = cap.read()
        if ok:
            widths.append(120.0)
    cap.release()
    palm = sorted(widths)[len(widths) // 2] if widths else 120.0
    with open("config.user.json", "w", encoding="utf-8") as f:
        json.dump({"palm_px": palm, "pinch_grab_px": palm * 0.33,
                   "pinch_release_px": palm * 0.45}, f, indent=2)


if __name__ == "__main__":
    main()
