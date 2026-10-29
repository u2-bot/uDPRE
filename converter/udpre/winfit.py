"""Window sizes that fit the screen. uDPRE.exe is not DPI aware: on a laptop, or a display scaled to 125 % / 150 %, Windows
hands it a screen of only 720-864 units, so a window's size and minimum come from the screen as well as from fixed numbers,
and its buttons are packed before its content (a short window then cuts the content, never the buttons)."""


def fit(win, width, height, min_width=None, min_height=None, centre=False):
    """sets `win` to width x height at most what the screen shows (its edges and the taskbar kept clear), its minimum size
    likewise; centre=True also places it in the middle of the screen; -> (width, height)"""
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    w, h = max(200, min(width, sw - 40)), max(200, min(height, sh - 80))
    pos = f'+{max(0, (sw - w) // 2)}+{max(0, (sh - h - 40) // 2)}' if centre else ''
    win.geometry(f'{w}x{h}{pos}')
    if min_width or min_height:
        win.minsize(min(min_width or 200, w), min(min_height or 200, h))
    return w, h
