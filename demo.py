#!/usr/bin/env python3
"""Hackathon entrypoint for Drift.

This runs the real product loop in safe dry-run mode by default: webcam hand
tracking, animated Dynamic-Island HUD, action feed, gesture state machine, and
dry-run Windows actuator logs. Use `--live` only when you want real OS actions.
"""

from src.app import run


if __name__ == "__main__":
    raise SystemExit(run())
