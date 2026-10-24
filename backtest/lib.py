import pickle, numpy as np, collections
import os
BASE = os.environ.get("BT_DIR", "bt/")
def load(): return pickle.load(open(BASE + "base.pkl", "rb"))
def pick_ms(p):
    k = max(("1", "X", "2"), key=lambda k: p[k]); return k, p[k]
def cands(p):
    c = []; k, v = pick_ms(p)
    if v >= .70: c.append(("MS", k, v, 3))
    elif v >= .60: c.append(("MS", k, v, 2))
    if p["O25"] >= .70: c.append(("O25", "O", p["O25"], 3))
    elif p["O25"] >= .60: c.append(("O25", "O", p["O25"], 2))
    if 1 - p["O25"] >= .60: c.append(("U25", "U", 1 - p["O25"], 2))
    if p["BTTS"] >= .60: c.append(("KGV", "B", p["BTTS"], 2))
    if 1 - p["BTTS"] >= .60: c.append(("KGY", "NB", 1 - p["BTTS"], 1))
    return c
def grade(p):
    c = cands(p)
    if not c: return None
    c.sort(key=lambda t: (-t[3], -t[2])); return c[0]
def won(m, key):
    a, b = m["hg"], m["ag"]; t = a + b
    return {"1": a > b, "X": a == b, "2": a < b, "O": t >= 3, "U": t < 3, "B": a > 0 and b > 0, "NB": not (a > 0 and b > 0)}[key]
def price(m, key, src):  # src: oA, oM, cA, cM
    return m.get(src + {"1": "1", "X": "X", "2": "2", "O": "O", "U": "U"}.get(key, "?"))
def prob(m, key, t):
    p = m[t]
    if p is None: return None
    return {"1": p["1"], "X": p["X"], "2": p["2"], "O": p["O25"], "U": 1 - p["O25"], "B": p["BTTS"], "NB": 1 - p["BTTS"]}[key]
class Acc:
    def __init__(s): s.n = 0; s.w = 0; s.pn = 0; s.ret = collections.defaultdict(float); s.rn = collections.defaultdict(int); s.ep = 0
    def add(s, m, key, p, srcs=("oA", "oM", "cA")):
        w = won(m, key); s.n += 1; s.w += w; s.ep += p
        for src in srcs:
            o = price(m, key, src)
            if o: s.rn[src] += 1; s.ret[src] += (o - 1) if w else -1
    def row(s, name):
        if not s.n: return f"{name:34s} n=0"
        r = " ".join(f"{k}:{100*s.ret[k]/s.rn[k]:+5.1f}%" for k in ("oA", "oM", "cA") if s.rn[k])
        return f"{name:34s} n={s.n:6d} tuttu %{100*s.w/s.n:5.1f} (beklenen %{100*s.ep/s.n:5.1f})  getiri {r}"
