"""Ed25519 signatures (RFC 8032), pure Python: uDPRE checks the signature of the mod catalogue with the public key it ships,
so a pack can only come from whoever holds the private key (the catalogue lists the SHA-256 of every file it points at).
Slow (tens of milliseconds a signature) and not constant-time - only ever used to sign / verify the catalogue, never secrets
on a shared machine."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)


def _xrecover(y):
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = x * I % P
    if x % 2 != 0:
        x = P - x
    return x


_BY = 4 * pow(5, P - 2, P) % P
_B = (_xrecover(_BY) % P, _BY % P, 1, _xrecover(_BY) * _BY % P)
_ZERO = (0, 1, 1, 0)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = t1 * 2 * D * t2 % P
    d = z1 * 2 * z2 % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % P, g * h % P, f * g % P, e * h % P


def _mul(s, p):
    q = _ZERO
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _encode(p):
    x, y, z, _t = p
    zi = pow(z, P - 2, P)
    x, y = x * zi % P, y * zi % P
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decode(s):
    if len(s) != 32:
        raise ValueError('bad point length')
    y = int.from_bytes(s, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= P:
        raise ValueError('bad point')
    x = _xrecover(y)
    if (x * x * -1 + y * y - 1 - D * x * x * y * y) % P != 0:
        raise ValueError('point not on the curve')
    if x & 1 != sign:
        x = P - x
    return x, y, 1, x * y % P


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), 'little')


def _secret(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    """32-byte seed (the private key) -> 32-byte public key"""
    a, _ = _secret(seed)
    return _encode(_mul(a, _B))


def sign(seed, msg):
    a, prefix = _secret(seed)
    pub = _encode(_mul(a, _B))
    r = _h(prefix + msg) % L
    rp = _encode(_mul(r, _B))
    k = _h(rp + pub + msg) % L
    s = (r + k * a) % L
    return rp + int.to_bytes(s, 32, 'little')


def verify(pub, msg, sig):
    """True when sig (64 bytes) is pub's signature of msg"""
    try:
        if len(sig) != 64 or len(pub) != 32:
            return False
        a = _decode(pub)
        rp = _decode(sig[:32])
        s = int.from_bytes(sig[32:], 'little')
        if s >= L:
            return False
        k = _h(sig[:32] + pub + msg) % L
        left = _mul(s, _B)
        right = _add(rp, _mul(k, a))
        return _encode(left) == _encode(right)
    except ValueError:
        return False
