def map_to_desktop(nx: float, ny: float, cfg: dict) -> tuple:
    m = cfg["roi_margin"]
    total_w, total_h = cfg["monitors"]["total_w"], cfg["monitors"]["total_h"]
    cx = min(max((nx - m) / (1.0 - 2 * m), 0.0), 1.0)
    cy = min(max((ny - m) / (1.0 - 2 * m), 0.0), 1.0)
    return (int(cx * total_w), int(cy * total_h))

def which_monitor(x: int, cfg: dict) -> int:
    return 1 if x < cfg["monitors"]["seam_x"] else 2
