"""Message files (Message/<language>, Message/common_msbt): one MonoBehaviour (Dpr.Message.MsbtData) per sheet, e.g.
'english_ss_monsname'; each label = wordDataArray of words {patternID, eventID, tagIndex, tagValue, str, strWidth}.

Words: patternID 0 Str, 1 FontTag, 2 ColorTag, 3 SizeTag, 4 CtrlTag, 5 WordTag (a name inserted at run time), 6 SpriteFont,
7 Event; eventID 1 NewLine, 2 Wait, 3 ScrollPage, 4 ScrollLine, 5 CallBack, 7 End. A label in text form:
  {Tn}  WordTag n     <...>  markup word     [n] [p] [s]  NewLine / ScrollPage / ScrollLine     [w:V] [c:V]  Wait / CallBack
Writing text back rebuilds the words the way the game's own files have them: a line's last word carries the line end, the
label's last word ends with End, strWidth = the sum of the glyph advances of Dpr/font/efigs_font (the engine's own measure;
-1 when a character is only in the run-time fallback font - the engine measures those itself).
"""
import re

LANGS = ['english', 'french', 'german', 'italian', 'spanish', 'jpn', 'jpn_kanji', 'korean', 'simp_chinese', 'trad_chinese']
EV_MARK = {1: '[n]', 3: '[p]', 4: '[s]'}
MARK_EV = {'n': 1, 'p': 3, 's': 4}
MARKUP_PID = {'color': 2, 'size': 3, 'font': 1}
TOKEN = re.compile(r'(\{T\d+\}|\[[nps]\]|\[[wc]:[-0-9.e]+\]|<[^<>]*>)')
FONT_BUNDLE = 'Dpr/font/efigs_font'


def fmt_val(v):
    return repr(float(v)) if v != int(v) else str(int(v))


def to_text(label):
    ws = label.get('wordDataArray') or []
    out = []
    last = len(ws) - 1
    for k, w in enumerate(ws):
        p, e = w['patternID'], w['eventID']
        out.append('{T%d}' % w['tagIndex'] if p == 5 else w['str'])
        if p == 7:
            if e in EV_MARK and k < last:
                out.append(EV_MARK[e])
            elif e == 2:
                out.append('[w:%s]' % fmt_val(w['tagValue']))
            elif e == 5:
                out.append('[c:%s]' % fmt_val(w['tagValue']))
        elif e in (1, 3, 4) and k < last:
            out.append(EV_MARK[e])
    return ''.join(out)


def plain(label):
    """the label's visible text without markup (tags as {Tn}); lines joined with a space"""
    t = to_text(label)
    t = re.sub(r'\[[nps]\]', ' ', t)
    t = re.sub(r'\[[wc]:[^\]]*\]', '', t)
    return re.sub(r'<[^<>]*>', '', t)


def tokens(text):
    out = []
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith('{T'):
            out.append(('tag', int(part[2:-1])))
        elif part in ('[n]', '[p]', '[s]'):
            out.append(('brk', part[1]))
        elif part.startswith('[w:') or part.startswith('[c:'):
            out.append(('ev', (part[1], float(part[3:-1]))))
        elif part.startswith('<') and part.endswith('>'):
            out.append(('markup', part))
        else:
            out.append(('text', part))
    return out


def _markup_pid(s):
    m = re.match(r'</?([a-z]+)', s)
    return MARKUP_PID.get(m.group(1) if m else '', 4)


def build_words(text, widths, last_style=(0, 7)):
    """text form -> wordDataArray. last_style = (patternID, eventID) the label's closing word had ((0, 7) a plain End,
    (7, 7) an End event, (7, 1) a description row that ends on a NewLine)."""
    lines, cur = [], []
    for kind, v in tokens(text):
        if kind == 'brk':
            lines.append((cur, v))
            cur = []
        else:
            cur.append((kind, v))
    lines.append((cur, None))
    words = []

    def wd(pid, ev, tag, s, width=None, tv=0.0):
        if width is None:
            width = -1.0 if not s else widths.width(s)
        return {'patternID': pid, 'eventID': ev, 'tagIndex': tag, 'tagValue': float(tv), 'str': s, 'strWidth': float(width)}

    for li, (segs, end) in enumerate(lines):
        final = li == len(lines) - 1
        for kind, v in segs:
            if kind == 'text':
                words.append(wd(0, 0, -1, v))
            elif kind == 'tag':
                words.append(wd(5, 0, v, '', -1.0))
            elif kind == 'markup':
                words.append(wd(_markup_pid(v), 0, -1, v, -1.0))
            elif kind == 'ev':
                k, val = v
                ev = 2 if k == 'w' else 5
                if words and words[-1]['patternID'] == 0 and words[-1]['eventID'] == 0:
                    w = words[-1]
                    w['patternID'], w['eventID'], w['tagValue'] = 7, ev, float(val)
                else:
                    words.append(wd(7, ev, -1, '', -1.0, val))
        last = words[-1] if segs and words else None
        plain_last = last is not None and last['patternID'] == 0 and last['eventID'] == 0
        if not final:
            if plain_last:
                last['patternID'], last['eventID'] = 7, MARK_EV[end]
            else:
                words.append(wd(7, MARK_EV[end], -1, '', 0.0))
        elif plain_last:
            last['patternID'], last['eventID'] = last_style if last_style[0] in (0, 7) else (0, 7)
        elif last is not None and last['eventID'] == 0 and last['patternID'] in (1, 2, 3, 4, 5):
            last['eventID'] = 7
        else:
            words.append(wd(7, 7, -1, '', -1.0))
    return words


def last_style(label):
    ws = label.get('wordDataArray') or []
    return (ws[-1]['patternID'], ws[-1]['eventID']) if ws else (0, 7)


class Widths:
    """strWidth of a string = the TMP glyph advances of the game font (32 pt atlas, no kerning); -1 if a character has no
    glyph in the atlas (the engine then measures it with the fallback font at run time)."""

    def __init__(self, files):
        self.adv = {}
        try:
            b = files.bundle(FONT_BUNDLE)
        except Exception:       # no font bundle in the stack: every width is measured by the engine
            return
        for name in b.names():
            t = b.mono(name)
            if 'm_GlyphTable' not in t or 'm_CharacterTable' not in t:
                continue
            gl = {g['m_Index']: g['m_Metrics']['m_HorizontalAdvance'] for g in t['m_GlyphTable']}
            for c in t['m_CharacterTable']:
                if c['m_GlyphIndex'] in gl:
                    self.adv.setdefault(chr(c['m_Unicode']), gl[c['m_GlyphIndex']])

    def width(self, s):
        tot = 0.0
        for ch in s:
            a = self.adv.get(ch)
            if a is None:
                return -1.0
            tot += a
        import struct
        return struct.unpack('<f', struct.pack('<f', tot))[0]


class Messages:
    """The message sheets of one language as the stack holds them. Sheets live in Message/<lang> or Message/common_msbt
    (species names, Pokedex text and form names are in common_msbt)."""

    def __init__(self, files, lang='english'):
        self.files = files
        self.lang = lang
        self._sheets = {}
        self._index = {}
        self.widths = None

    def _locate(self, sheet):
        for rel in (f'Message/{self.lang}', 'Message/common_msbt'):
            try:
                b = self.files.bundle(rel)
            except Exception:
                continue
            if b.has(sheet):
                return b
        return None

    def sheet(self, short):
        """short = 'ss_monsname' -> the MsbtData tree (None when no file has it)"""
        name = f'{self.lang}_{short}'
        if name not in self._sheets:
            b = self._locate(name)
            self._sheets[name] = b.mono(name) if b else None
        return self._sheets[name]

    def labels(self, short):
        t = self.sheet(short)
        return t.get('labelDataArray', []) if t else []

    def _label_index(self, short):
        if short not in self._index:
            self._index[short] = {lab['labelName']: lab for lab in self.labels(short)}
        return self._index[short]

    def label(self, short, name):
        return self._label_index(short).get(name)

    def text(self, short, name, default=''):
        lab = self.label(short, name)
        return plain(lab) if lab else default

    def by_index(self, short):
        """[plain text] by label position (sheets like ss_monsname are indexed by number)"""
        return [plain(lab) for lab in self.labels(short)]

    def set_text(self, short, name, text):
        """sets a label's text (text form); -> True if the label exists"""
        lab = self.label(short, name)
        if lab is None:
            return False
        if self.widths is None:
            self.widths = Widths(self.files)
        lab['wordDataArray'] = build_words(text, self.widths, last_style(lab))
        return True

    def add_label(self, short, name, text, like=None):
        """appends a label (copying the attributes of label `like`, else of the sheet's last label)"""
        import copy
        t = self.sheet(short)
        if t is None:
            raise KeyError(f'{self.lang}_{short}')
        arr = t['labelDataArray']
        tmpl = self.label(short, like) if like else (arr[-1] if arr else None)
        lab = copy.deepcopy(tmpl) if tmpl else {'labelIndex': 0, 'arrayIndex': 0, 'labelName': name, 'styleInfo': {},
                                                'attributeValueArray': [], 'tagDataArray': [], 'wordDataArray': []}
        lab['labelName'] = name
        lab['labelIndex'] = max((x.get('labelIndex', 0) for x in arr), default=-1) + 1
        lab['arrayIndex'] = len(arr)
        lab['tagDataArray'] = []
        arr.append(lab)
        self._index.pop(short, None)
        self.set_text(short, name, text)
        return lab
