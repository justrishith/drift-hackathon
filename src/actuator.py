class Actuator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.log: list = []
        self._grab = None

    def _real(self) -> bool:
        return not self.cfg.get("dry_run", True)

    def active_window(self):
        """Return the current foreground HWND, or a harmless dry-run placeholder."""
        if self._real():
            import win32gui
            return win32gui.GetForegroundWindow()
        return 0

    def move_cursor(self, x: int, y: int) -> None:
        self.log.append(("cursor", x, y))
        if self._real():
            import win32api
            win32api.SetCursorPos((x, y))

    def grab(self, hwnd: int, cx: int, cy: int) -> None:
        self.log.append(("grab", hwnd, cx, cy))
        if self._real():
            import win32gui
            if not hwnd:
                hwnd = win32gui.GetForegroundWindow()
            rect = win32gui.GetWindowRect(hwnd)
            self._grab = {"hwnd": hwnd, "dx": cx - rect[0], "dy": cy - rect[1]}
        else:
            self._grab = {"hwnd": hwnd, "dx": 100, "dy": 40}

    def drag_to(self, x: int, y: int) -> None:
        self.log.append(("drag", x, y))
        if self._real() and self._grab:
            import win32gui, win32con
            hwnd = self._grab["hwnd"]
            win32gui.SetWindowPos(hwnd, 0, x - self._grab["dx"], y - self._grab["dy"], 0, 0,
                                  win32con.SWP_NOSIZE | win32con.SWP_NOZORDER)

    def zoom(self, direction: str) -> None:
        self.log.append(("zoom", direction))
        if self._real():
            import win32gui, win32con
            hwnd = self.active_window()
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2]-rect[0], rect[3]-rect[1]
                new_w = int(w * 1.15) if direction == "in" else int(w * 0.85)
                new_h = int(h * 1.15) if direction == "in" else int(h * 0.85)
                win32gui.SetWindowPos(hwnd, 0, rect[0], rect[1], new_w, new_h, win32con.SWP_NOZORDER)

    def drop(self) -> None:
        self.log.append(("drop",))
        self._grab = None

    def resize_to(self, w: int, h: int) -> None:
        """Resize latched (or active) window to w x h desktop px. Shape mode."""
        w = max(200, min(int(w), 3840))
        h = max(150, min(int(h), 2160))
        self.log.append(("resize", w, h))
        if self._real():
            import win32gui, win32con
            hwnd = self._grab["hwnd"] if self._grab else self.active_window()
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                win32gui.SetWindowPos(hwnd, 0, rect[0], rect[1], w, h, win32con.SWP_NOZORDER)

    def throw_to_monitor(self, direction: str) -> None:
        """Snap active window to screen half (split-screen). Win+Left/Right."""
        self.log.append(("throw", direction))
        if self._real():
            from pynput.keyboard import Key, Controller
            k = Controller()
            key = Key.left if direction == "left" else Key.right
            with k.pressed(Key.cmd):
                k.press(key)
                k.release(key)
