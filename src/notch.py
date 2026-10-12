"""Top notch pill overlay (Task 5).

All tkinter / drift imports are lazy inside functions so `pytest` and
`import src.notch` work WITHOUT a display.
"""

DISPLAY_WIDTH = 1920
EASE_MS = 120

_ASCII_MAP = {"·": "-", "●": "*", "◉": "(*)", "⇄": "<>",
              "⤢": "+", "■": "#", "❚": "|", "…": "..."}


def ascii_text(text) -> str:
    """cp1252-safe console fallback for notch glyphs (T5b).

    Tk labels render Unicode fine; Windows consoles (cp1252) raise
    UnicodeEncodeError on glyphs like ●/◉/⇄/⤢/■/❚. Map the known ones
    to readable ASCII, then errors="replace" for anything leftover.
    """
    if text is None:
        return ""
    out = "".join(_ASCII_MAP.get(ch, ch) for ch in str(text))
    return out.encode("ascii", errors="replace").decode("ascii")


def create_pill(text):
    """Create a transparent topmost pill centered at the top of DISPLAY1."""
    import tkinter as tk

    from src.drift import notch_text  # lazy: keeps tests display-free

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    # Transparent background; black translucent pill frame.
    root.attributes("-transparentcolor", "grey15")
    root.configure(bg="grey15")
    root.geometry(f"+{(DISPLAY_WIDTH - 220) // 2}+8")

    frame = tk.Frame(root, bg="black", padx=18, pady=6)
    frame.pack()
    label = tk.Label(frame, text=text if text else notch_text("idle"),
                     fg="white", bg="black", font=("Segoe UI", 11))
    label.pack()

    pill = {"root": root, "frame": frame, "label": label,
            "paused": False, "text": label.cget("text")}

    def _toggle_pause(_event=None):
        pill["paused"] = not pill["paused"]
        label.config(text="❚❚ paused" if pill["paused"] else pill["text"])

    root.bind("<Button-1>", _toggle_pause)
    label.bind("<Button-1>", _toggle_pause)
    return pill


def update_pill(pill, text):
    """Update pill text with a 120ms ease-out resize on state change."""
    if pill is None:
        return None
    if text == pill.get("text"):
        return pill

    def _apply():
        pill["label"].config(text=text)
        pill["text"] = text
        try:
            pill["root"].update_idletasks()
        except Exception:
            pass

    try:
        root = pill["root"]
        # Ease-out: two-step resize over EASE_MS total.
        try:
            root.after(EASE_MS // 2, _apply)
        except Exception:
            _apply()
    except Exception:
        pass
    return pill
