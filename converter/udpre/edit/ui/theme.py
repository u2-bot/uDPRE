"""uDPRE Studio's look: colors, fonts and the ttk styles of the Editor & Randomizer. Every style is a Studio.* one - the main
uDPRE window shares the Tk style database and keeps its own (default) look."""
import tkinter as tk
from tkinter import font as tkfont, ttk

FONT = 'Segoe UI'
MONO = 'Consolas'
C = {
    'bg': '#ffffff', 'soft': '#f5f7fa', 'line': '#e3e7ee', 'line2': '#cfd6e1', 'text': '#18202b', 'muted': '#5d6b7e',
    'faint': '#94a0b2', 'side': '#161d27', 'side_hover': '#222c3a', 'side_text': '#c7cfdb', 'side_head': '#6f7b8c',
    'side_active': '#2b62d9', 'accent': '#2b62d9', 'accent_hover': '#2353bb', 'accent_soft': '#e8effd',
    'edited': '#e07b00', 'edited_soft': '#fff3e0', 'ok': '#11804a', 'ok_soft': '#e3f6ec', 'danger': '#c0262d',
    'danger_soft': '#fdeceb', 'stripe': '#f8fafc', 'select': '#dce7fd',
}
# type colors by the game's type ids (0 Normal ... 17 Fairy); a mod's extra types fall back to gray
TYPE_COLORS = ['#9a9a78', '#b83b32', '#8f7fd6', '#9b4a99', '#d1ad5b', '#a9963c', '#93a530', '#6c5791', '#9d9db5',
               '#e2742c', '#4f7fe0', '#5fae3f', '#d9b622', '#e8507f', '#6cc3c0', '#6538e0', '#6b5444', '#cc78a6']
STAT_COLORS = [(0, '#e5484d'), (60, '#f08c2e'), (90, '#e6c229'), (110, '#7bc043'), (130, '#2fa36b'), (160, '#1f8bd6')]


def type_color(t):
    return TYPE_COLORS[t] if isinstance(t, int) and 0 <= t < len(TYPE_COLORS) else '#7d8796'


def stat_color(v):
    out = STAT_COLORS[0][1]
    for lo, col in STAT_COLORS:
        if v >= lo:
            out = col
    return out


def text_on(bg):
    """black or white text, whichever reads better on bg"""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    return '#ffffff' if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else '#18202b'


_done = set()


def setup(root):
    """the Studio.* styles (once per Tk interpreter)"""
    key = str(root.tk)
    if key in _done:
        return
    _done.add(key)
    st = ttk.Style(root)
    base = (FONT, 9)
    st.configure('Studio.TFrame', background=C['bg'])
    st.configure('Soft.TFrame', background=C['soft'])
    st.configure('Studio.TLabel', background=C['bg'], foreground=C['text'], font=base)
    st.configure('Muted.TLabel', background=C['bg'], foreground=C['muted'], font=base)
    st.configure('Faint.TLabel', background=C['bg'], foreground=C['faint'], font=(FONT, 8))
    st.configure('Soft.TLabel', background=C['soft'], foreground=C['muted'], font=base)
    st.configure('Title.TLabel', background=C['bg'], foreground=C['text'], font=(FONT, 15, 'bold'))
    st.configure('Record.TLabel', background=C['bg'], foreground=C['text'], font=(FONT, 16, 'bold'))
    st.configure('Section.TLabel', background=C['bg'], foreground=C['text'], font=(FONT, 10, 'bold'))
    st.configure('Error.TLabel', background=C['bg'], foreground=C['danger'], font=base)
    st.configure('Studio.TCheckbutton', background=C['bg'], foreground=C['text'], font=base)
    st.map('Studio.TCheckbutton', background=[('active', C['bg'])])
    st.configure('Studio.TRadiobutton', background=C['bg'], foreground=C['text'], font=base)
    st.map('Studio.TRadiobutton', background=[('active', C['bg'])])
    st.configure('Studio.TSeparator', background=C['line'])
    st.configure('Studio.Treeview', rowheight=24, font=base, background=C['bg'], fieldbackground=C['bg'],
                 foreground=C['text'], borderwidth=0)
    st.configure('Studio.Treeview.Heading', font=(FONT, 9, 'bold'), foreground=C['muted'])
    st.map('Studio.Treeview', background=[('selected', C['select'])], foreground=[('selected', C['text'])])
    st.configure('Studio.TEntry', padding=(4, 3))
    st.configure('Studio.TSpinbox', padding=(4, 2))
    st.configure('Studio.TCombobox', padding=(4, 2))
    st.configure('Studio.Horizontal.TScale', background=C['bg'])
    try:
        tkfont.nametofont('TkDefaultFont')
    except tk.TclError:
        pass
