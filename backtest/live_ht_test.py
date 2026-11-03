"""Canlı analiz, devre arası testi: maç öncesi kapanış oranından gol beklentisi, devre skoru ile live.inplay
ve live.picks_for (botun canlı seçim kuralları), sonuç maç sonu skoruyla. Kırmızı kart dakikası veride yok:
kartlar hesaba katılmaz; ikinci yarıda kırmızı kart gören maçlar ayrıca gösterilir.
Kullanım: python -I backtest/live_ht_test.py <fd_klasörü>"""
import sys, os, io, csv, glob, math, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import engine as E, live as L

D = sys.argv[1]
RHO = -0.06; K = 11
g = np.round(np.arange(0.15, 4.5, 0.025), 4)
pois = np.array([[math.exp(-l) * l ** k / math.factorial(k) for k in range(K)] for l in g])
P1 = np.zeros((len(g), len(g))); P2 = P1.copy(); PO = P1.copy()
for i in range(K):
    for j in range(K):
        w = pois[:, i][:, None] * pois[:, j][None, :]
        lh, la = g[:, None], g[None, :]
        if (i, j) == (0, 0): w = w * (1 - lh * la * RHO)
        elif (i, j) == (0, 1): w = w * (1 + lh * RHO)
        elif (i, j) == (1, 0): w = w * (1 + la * RHO)
        elif (i, j) == (1, 1): w = w * (1 - RHO)
        if i > j: P1 += w
        if i < j: P2 += w
        if i + j >= 3: PO += w
P1f, P2f, POf = P1.ravel(), P2.ravel(), PO.ravel(); n = len(g)


def lams(p1, p2, po):
    k = int(np.argmin((P1f - p1) ** 2 + (P2f - p2) ** 2 + (POf - po) ** 2)); i, j = divmod(k, n)
    return float(g[i]), float(g[j])


def prop(o, keys):
    s = sum(1 / o[k] for k in keys); return {k: (1 / o[k]) / s for k in keys}


def won(k, a, b, ha, hb):
    t = a + b
    if k in ("1", "X", "2", "1X", "X2", "12"):
        r = "1" if a > b else ("X" if a == b else "2"); return r in k
    if k == "BTTS": return a > 0 and b > 0
    if k == "NBTTS": return not (a > 0 and b > 0)
    if k == "GOAL": return t > ha + hb
    if k == "NOGOAL": return t == ha + hb
    if k[0] == "O": return t > float(k[1:])
    if k[0] == "U": return t < float(k[1:])


def fnum(x):
    try:
        v = float(x); return v if v > 1 else None
    except (TypeError, ValueError):
        return None


rows = []
for path in sorted(glob.glob(os.path.join(D, "*", "*.csv"))):
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            try:
                a, b, ha, hb = (int(float(r[c])) for c in ("FTHG", "FTAG", "HTHG", "HTAG"))
            except (KeyError, ValueError, TypeError):
                continue
            o = {k: fnum(r.get(c)) for k, c in (("1", "AvgCH"), ("X", "AvgCD"), ("2", "AvgCA"), ("O", "AvgC>2.5"), ("U", "AvgC<2.5"))}
            if not all(o.values()):
                continue
            try:
                reds2 = int(float(r.get("HR") or 0)) + int(float(r.get("AR") or 0))
            except ValueError:
                reds2 = 0
            rows.append((o, a, b, ha, hb, reds2))
print(f"Kapanış oranı ve devre skoru olan {len(rows)} maç\n")

for meth, fair in (("oransal", prop), ("power", E.fair)):
    first = collections.defaultdict(lambda: [0, 0, 0.0]); allp = collections.defaultdict(lambda: [0, 0, 0.0])
    reds = [0, 0]; nm = 0
    for o, a, b, ha, hb, rd in rows:
        p3 = fair(o, ("1", "X", "2")); po = fair(o, ("O", "U"))["O"]
        lh, la = lams(p3["1"], p3["2"], po)
        p, tl, _, _, _ = L.inplay(lh, la, ha, hb, 45, 1)
        pk = L.picks_for(p, tl, 45, None, ha + hb)
        if not pk: continue
        nm += 1
        for i, x in enumerate(pk):
            w = won(x["k"], a, b, ha, hb); fam = x["label"]
            for d in ((allp,) if i else (first, allp)):
                c = d[fam]; c[0] += 1; c[1] += w; c[2] += x["prob"]
                c = d["TOPLAM"]; c[0] += 1; c[1] += w; c[2] += x["prob"]
            if i == 0 and rd: reds[0] += 1; reds[1] += w
    print(f"=== {meth} === seçim çıkan maç {nm}")
    for title, d in (("Botun ilk seçimi", first), ("Gönderilen tüm seçimler (en fazla 2)", allp)):
        print(f" {title}:")
        for fam, c in sorted(d.items(), key=lambda x: -x[1][0]):
            if c[0] >= 30 or fam == "TOPLAM":
                print(f"   {fam:30s} {c[1]:6d} / {c[0]:6d}  %{100*c[1]/c[0]:.1f}  (beklenen %{100*c[2]/c[0]:.1f})")
    print(f" Kırmızı kartlı maçlarda ilk seçim: {reds[1]} / {reds[0]}  %{100*reds[1]/max(reds[0],1):.1f}\n")
