import json


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config_with_overlay(base_path: str, user_path: str) -> dict:
    """Load base config then overlay user-calibration keys (CALIBRATE.md precedence).

    Missing user file -> base unchanged. Present file -> its keys win.
    Pure function: no camera/display/mediapipe imports.
    """
    cfg = load_config(base_path)
    try:
        with open(user_path, "r", encoding="utf-8") as f:
            overlay = json.load(f)
    except FileNotFoundError:
        return dict(cfg)
    merged = dict(cfg)
    merged.update(overlay)
    return merged
