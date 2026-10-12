def test_state_machine_cooldown_and_freeze():
    from src.drift import next_state
    cfg = {"cooldown_s": 0.45, "linger_drop_s": 0.4, "fist_hold_s": 0.5}
    timers = {"last": 0.0, "fist_since": 0.0}
    assert next_state("idle", "palm_show", 1.0, cfg, timers) == "idle_ready"
    assert next_state("idle_ready", "push_hold", 1.5, cfg, timers) == "grab"
    assert next_state("grab", "fist", 2.0, cfg, timers) == "grab"
    assert next_state("grab", "fist", 2.6, cfg, timers) == "frozen"
