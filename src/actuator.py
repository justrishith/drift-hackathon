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
            from pynput.keyboard import Controller, Key
            k = Controller()
            key = "=" if direction == "in" else "-"
            with k.pressed(Key.ctrl):
                k.press(key)
                k.release(key)

    def drop(self) -> None:
        self.log.append(("drop",))
        self._grab = None

    def throw_to_monitor(self, direction: str) -> None:
        self.log.append(("throw", direction))
        if self._real():
            from pynput.keyboard import Key, Controller
            k = Controller()
            key = Key.left if direction == "left" else Key.right
            with k.pressed(Key.shift_l):
                with k.pressed(Key.cmd):
                    k.press(key)
                    k.release(key)
