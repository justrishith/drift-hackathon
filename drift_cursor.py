#!/usr/bin/env python3
"""Drift grabber cursor — follows the mouse, shows latch state from drift_state.json.
Open ring = free, filled red = latched onto a window. Sits at the pointer tip.
"""
import tkinter as tk
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "drift_state.json")

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.configure(bg="#000000")
root.geometry("28x28+0+0")

cv = tk.Canvas(root, width=28, height=28, bg="#000000", highlightthickness=0)
cv.pack()
ring = cv.create_oval(4, 4, 24, 24, outline="#ff2a2a", width=2)
dot = cv.create_oval(10, 10, 18, 18, fill="#ff2a2a", outline="")
cv.itemconfig(dot, state="hidden")
tip = cv.create_polygon(2, 2, 12, 9, 2, 16, fill="#ffffff", outline="#ff2a2a")


def tick():
    latched = False
    try:
        with open(STATE_PATH) as f:
            dd = json.load(f)
        latched = str(dd.get("state", "")).lower() == "grab"
    except Exception:
        pass
    cv.itemconfig(dot, state="normal" if latched else "hidden")
    cv.itemconfig(ring, width=3 if latched else 2)
    try:
        import win32api
        x, y = win32api.GetCursorPos()
        root.geometry(f"28x28+{x + 14}+{y + 14}")
    except Exception:
        pass
    root.after(80, tick)


tick()
root.mainloop()
