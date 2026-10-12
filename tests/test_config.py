def test_load_config_defaults():
    from src.util import load_config
    cfg = load_config("config.json")
    assert cfg["dry_run"] is True
    assert cfg["cooldown_s"] == 0.45
    assert cfg["monitors"]["total_w"] == 4480


def test_load_config_with_overlay(tmp_path):
    import json
    from src.util import load_config_with_overlay
    base = tmp_path / "config.json"
    user = tmp_path / "config.user.json"
    base.write_text(json.dumps({"dry_run": True, "cooldown_s": 0.45,
                                "pinch_grab_px": 40}), encoding="utf-8")
    user.write_text(json.dumps({"cooldown_s": 0.9, "palm_px": 120.0}),
                    encoding="utf-8")
    cfg = load_config_with_overlay(str(base), str(user))
    assert cfg["cooldown_s"] == 0.9
    assert cfg["pinch_grab_px"] == 40
    assert cfg["palm_px"] == 120.0
    cfg2 = load_config_with_overlay(str(base), str(tmp_path / "missing.json"))
    assert cfg2["cooldown_s"] == 0.45
    assert cfg2["pinch_grab_px"] == 40
