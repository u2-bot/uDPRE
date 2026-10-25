"""Randomizer distributions: how a new value is drawn from the current one. Specs are plain JSON dicts so a project keeps
them as typed; Numeric(spec) / Choice(spec) sample them with the run's own random.Random.

Every spec has a leading randomization probability p (percent, 0..100): a draw first succeeds with probability p/100 and
otherwise returns the input unchanged. Numeric specs (input x = the current value, output an unbounded integer the caller
conforms to its absolute boundary):
  {'type': 'UC', 'p': P, 'min': A, 'max': B}   uniform integer in [trunc(A), trunc(B)]
  {'type': 'UR', 'p': P, 'min': A, 'max': B}   x + uniform integer in [trunc(A), trunc(B)]
  {'type': 'UP', 'p': P, 'min': A, 'max': B}   uniform integer in [trunc(A*x), trunc(B*x)]
  {'type': 'NC', 'p': P, 'mean': M, 'std': S}  round(N(M, S))
  {'type': 'NR', 'p': P, 'std': S}             round(N(x, S))
  {'type': 'NP', 'p': P, 'std': S}             round(N(x, S*x))
(trunc toward zero, round half to even, parameters rounded to 3 decimals, min/max reordered.)
Item (categorical) specs, output = an id of the option's entity list:
  {'type': 'empirical', 'p': P, 'weights': [[id, w], ...]}   id with probability w / total (negative w = 0)
  {'type': 'uniform', 'p': P, 'include': [id, ...]}          uniform among the included ids
An empty support (total 0 / nothing included) never randomizes.
Text form of numeric specs (the main window's boxes): <p><CODE><arg>[,<arg>], e.g. 100NR12.5, 75UC10,100, 50NC60,20;
code case-insensitive, numbers may carry an exponent, the infinity sign is a number; a text without the leading p means
100%.
"""
import bisect
import math
import re

NUMERIC = ('UC', 'UR', 'UP', 'NC', 'NR', 'NP')
ITEM = ('empirical', 'uniform')
NUMERIC_NAMES = {'UC': 'Uniform, Constant', 'UR': 'Uniform, Relative', 'UP': 'Uniform, Proportional',
                 'NC': 'Normal, Constant', 'NR': 'Normal, Relative', 'NP': 'Normal, Proportional'}
NUMERIC_HELP = {'UC': 'same boundaries for all values: Y ~ U(min, max)', 'UR': 'relative boundaries: Y ~ U(x+min, x+max)',
                'UP': 'proportional boundaries: Y ~ U(x*min, x*max)', 'NC': 'same mean and deviation: Y ~ N(mean, std)',
                'NR': 'same deviation: Y ~ N(x, std)', 'NP': 'proportional deviation: Y ~ N(x, std*x)'}
ITEM_NAMES = {'empirical': 'Empirical', 'uniform': 'Uniform'}
ITEM_HELP = {'empirical': 'each value with probability weight / total weight',
             'uniform': 'every included value equally likely'}
ARGS = {'UC': ('min', 'max'), 'UR': ('min', 'max'), 'UP': ('min', 'max'), 'NC': ('mean', 'std'), 'NR': ('std',),
        'NP': ('std',)}


class DistError(ValueError):
    pass


def r3(v):
    v = float(v)
    return v if math.isinf(v) or math.isnan(v) else round(v, 3)


def clamp_p(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return 100.0
    return 0.0 if math.isnan(p) else max(0.0, min(100.0, p))


def numeric(kind, p=100, **args):
    """-> a normalized numeric spec"""
    kind = kind.upper()
    if kind not in NUMERIC:
        raise DistError(f'unknown distribution {kind}')
    spec = {'type': kind, 'p': r3(clamp_p(p))}
    for a in ARGS[kind]:
        spec[a] = r3(args.get(a, 0))
    if 'min' in spec and spec['min'] > spec['max']:
        spec['min'], spec['max'] = spec['max'], spec['min']
    return spec


def trunc(v):
    if math.isinf(v) or math.isnan(v):
        raise OverflowError
    return int(v)


def pcheck(rng, p):
    return rng.random() * 100.0 < p


class Numeric:
    def __init__(self, spec):
        s = numeric(spec.get('type', 'NR'), spec.get('p', 100), **{k: spec[k] for k in spec if k not in ('type', 'p')})
        self.spec = s
        self.kind = s['type']
        self.p = s['p']

    def draw(self, rng, x):
        """-> the new integer (unbounded); x when the probability check fails"""
        if not pcheck(rng, self.p):
            return x
        s, k = self.spec, self.kind
        try:
            if k in ('UC', 'UR', 'UP'):
                if k == 'UP':
                    a, b = trunc(s['min'] * x), trunc(s['max'] * x)
                else:
                    a, b = trunc(s['min']), trunc(s['max'])
                if a > b:
                    a, b = b, a
                v = rng.randint(a, b)
                return x + v if k == 'UR' else v
            if k == 'NC':
                return round(rng.gauss(s['mean'], abs(s['std'])))
            if k == 'NR':
                return round(rng.gauss(x, abs(s['std'])))
            return round(rng.gauss(x, abs(s['std'] * x)))
        except (OverflowError, ValueError):     # infinite parameters: no usable value
            return x


class Choice:
    """An item distribution restricted to `allowed` ids (None = any id)."""

    def __init__(self, spec, allowed=None):
        self.spec = spec
        self.p = clamp_p(spec.get('p', 100))
        kind = spec.get('type', 'empirical')
        ids, cum, tot = [], [], 0
        if kind == 'uniform':
            for v in sorted({int(v) for v in spec.get('include', [])}):
                if allowed is None or v in allowed:
                    tot += 1
                    ids.append(v)
                    cum.append(tot)
        else:
            for v, w in sorted(weight_pairs(spec.get('weights', []))):
                if w > 0 and (allowed is None or v in allowed):
                    tot += w
                    ids.append(v)
                    cum.append(tot)
        self.ids, self.cum, self.total = ids, cum, tot
        if tot <= 0:
            self.p = 0.0

    def support(self):
        return list(self.ids)

    def pick(self, rng):
        """-> an id of the support (ignores p); None when empty"""
        if self.total <= 0:
            return None
        k = bisect.bisect_right(self.cum, rng.random() * self.total)
        return self.ids[min(k, len(self.ids) - 1)]

    def draw(self, rng, x):
        if not pcheck(rng, self.p):
            return x
        v = self.pick(rng)
        return x if v is None else v


def weight_pairs(w):
    """weights as [[id, w], ...] or {id: w} -> [(int id, int w >= 0)]"""
    items = w.items() if isinstance(w, dict) else w
    out = {}
    for v, n in items:
        try:
            out[int(v)] = out.get(int(v), 0) + max(0, int(round(float(n))))
        except (TypeError, ValueError):
            continue
    return list(out.items())


def empirical(counts, p=100):
    """counts {id: n} -> spec"""
    return {'type': 'empirical', 'p': r3(clamp_p(p)), 'weights': [[int(k), int(v)] for k, v in sorted(counts.items())]}


def uniform(ids, p=100):
    return {'type': 'uniform', 'p': r3(clamp_p(p)), 'include': sorted({int(v) for v in ids})}


def fill(spec, ids):
    """the dialog's Fill button: every weight 12 / every id included"""
    if spec.get('type') == 'uniform':
        return uniform(ids, spec.get('p', 100))
    return empirical({v: 12 for v in ids}, spec.get('p', 100))


def empty(spec):
    """the dialog's Empty button: every weight 0 / nothing included"""
    if spec.get('type') == 'uniform':
        return uniform([], spec.get('p', 100))
    return {'type': 'empirical', 'p': spec.get('p', 100), 'weights': []}


def make(spec, allowed=None):
    """-> a sampler for any spec"""
    if spec.get('type') in ITEM:
        return Choice(spec, allowed)
    return Numeric(spec)


# --- defaults from observations (analyzer) ---------------------------------------------------------------------
def stats(obs):
    n = len(obs)
    if not n:
        return 0, 0, 0, 0.0, 0.0
    mn, mx = min(obs), max(obs)
    mean = sum(obs) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in obs) / (n - 1)) if n > 1 else 0.0
    return mn, mx, (mn + mx) / 2, mean, std


def numeric_defaults(obs):
    """-> {code: spec} of the six numeric types derived from observed values (the active default is 'NR')"""
    mn, mx, mid, mean, std = stats(obs)
    d2 = 2 * mid or 1
    m2 = 2 * mean or 1
    return {'UC': numeric('UC', min=mn, max=mx), 'UR': numeric('UR', min=(mn - mid) / 2, max=(mx - mid) / 2),
            'UP': numeric('UP', min=(mn + mid) / d2, max=(mx + mid) / d2), 'NC': numeric('NC', mean=mean, std=std),
            'NR': numeric('NR', std=std / 2), 'NP': numeric('NP', std=std / m2)}


# --- text syntax -----------------------------------------------------------------------------------------------------------
NUM = r'(?:-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?|-?∞)'
TEXT = re.compile(r'^\s*(' + NUM + r')?\s*(UC|UR|UP|NC|NR|NP)\s*(' + NUM + r')(?:\s*,\s*(' + NUM + r'))?\s*$', re.I)


def _num(s):
    s = s.replace('∞', 'inf')
    return float(s)


def parse_text(text):
    """'100NR12.5' -> spec; raises DistError on anything else (a missing leading probability too)."""
    m = TEXT.match(text or '')
    if not m:
        raise DistError(f'not a distribution: {text!r}')
    p, code, a, b = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
    if p is None:
        raise DistError(f'{text!r}: the randomization probability (the leading number, e.g. 100{code}...) is missing')
    need = len(ARGS[code])
    if (b is None) != (need == 1):
        raise DistError(f'{code} takes {need} number{"s" if need > 1 else ""}')
    vals = [_num(a)] + ([_num(b)] if b is not None else [])
    if need == 2 and code in ('UC', 'UR', 'UP') and vals[0] > vals[1]:
        raise DistError('min is larger than max')
    return numeric(code, _num(p) if p is not None else 100, **dict(zip(ARGS[code], vals)))


def _fmt(v):
    if math.isinf(v):
        return '∞' if v > 0 else '-∞'
    if v == int(v):
        return str(int(v))
    return ('%.3f' % v).rstrip('0').rstrip('.')


def format_text(spec):
    """numeric spec -> '100NR12.5'"""
    s = numeric(spec.get('type', 'NR'), spec.get('p', 100), **{k: spec[k] for k in spec if k not in ('type', 'p')})
    return _fmt(s['p']) + s['type'] + ','.join(_fmt(s[a]) for a in ARGS[s['type']])


def describe(spec):
    t = spec.get('type')
    if t in NUMERIC:
        return f'{NUMERIC_NAMES[t]} - {NUMERIC_HELP[t]}'
    return f'{ITEM_NAMES.get(t, t)} - {ITEM_HELP.get(t, "")}'
