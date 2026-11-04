"""Yeni ligler (football-data 'new' formatı: DNK, NOR, SWE, FIN, BRA, USA, JPN): botun seçim kuralları.
Bu dosyalarda yalnızca kapanış 1X2 oranları var (alt/üst ve devre skoru yok): gol beklentisi 1X2'ye ve ligin önceki
sezonlardaki gol ortalamasına uydurulur. Ana seçimler (core.grade), riskli (risky_pick) ve çok riskli (long_pick, İY'siz).
Kullanım: python -I backtest/new_leagues_test.py <klasör: KOD.csv dosyaları>"""
import sys, os, io, csv, glob, math, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "engine"), os.path.join(HERE, "..", "bot")]
import engine as E, scan, core
RHO = -0.06; K = 11
g = np.round(np.arange(0.15, 4.5, 0.025), 4); n = len(g)
pois = np.array([[math.exp(-l) * l ** k / math.factorial(k) for k in range(K)] for l in g])
P1 = np.zeros((n, n)); P2 = P1.copy()
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
TOT = (g[:, None] + g[None, :]).ravel(); P1f, P2f = P1.ravel(), P2.ravel()


def lams(p1, p2, total):
    k = int(np.argmin((P1f - p1) ** 2 + (P2f - p2) ** 2 + 0.002 * (TOT - total) ** 2)); i, j = divmod(k, n)
    return float(g[i]), float(g[j])


def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def stats():
    return collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0])


def acc(d, key, ok, pr, odd=None):
    z = d[key]; z[0] += 1; z[1] += ok; z[2] += pr
    if odd: z[3] += (odd - 1) if ok else -1; z[4] += 1


def show(d):
    for k, z in sorted(d.items(), key=lambda x: (x[0][0], x[0][1])):
        r = f", gerçek oranla getiri %{100*z[3]/z[4]:+.1f}" if z[4] else ""
        print(f"   {k[0]:10s} {k[1]:20s} {z[1]:6d}/{z[0]:6d} %{100*z[1]/z[0]:.1f} (beklenen %{100*z[2]/z[0]:.1f}){r}")


ALL = stats(); BYLG = collections.defaultdict(stats)
for path in sorted(glob.glob(os.path.join(sys.argv[1], "*.csv"))):
    code = os.path.basename(path)[:-4]
    rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig", errors="replace")))
    goals = collections.defaultdict(list)
    for r in rows:
        try: goals[r["Season"]].append(int(r["HG"]) + int(r["AG"]))
        except (ValueError, KeyError, TypeError): pass
    seas = sorted(goals)
    for r in rows:
        s = r["Season"]
        if s < "2019" or seas.index(s) < 2: continue
        try: a, b = int(r["HG"]), int(r["AG"])
        except (ValueError, KeyError, TypeError): continue
        o = {k: fnum(r.get(c)) for k, c in (("1", "AvgCH"), ("X", "AvgCD"), ("2", "AvgCA"))}
        if not all(v and v > 1 for v in o.values()): continue
        prev = [x for ps in seas[max(0, seas.index(s) - 2):seas.index(s)] for x in goals[ps]]
        T = sum(prev) / len(prev)
        p3 = E.fair(o, ("1", "X", "2")); lh, la = lams(p3["1"], p3["2"], T)
        pp, M, _ = scan.full_probs(lh, la, 0.45)
        h = dict(p={k: float(v) for k, v in pp.items()}, M=[[round(float(M[i, j]), 4) for j in range(6)] for i in range(6)],
                 src="piyasa", known=(True, True))
        gr = core.grade(h)
        if gr and gr["tier"] >= 2:
            ok = bool(core.settle(core.LABEL2KEY[gr["label"]], [a, b]))
            odd = {"MS 1": o["1"], "MS X": o["X"], "MS 2": o["2"]}.get(gr["label"])
            for d in (ALL, BYLG[code]):
                acc(d, ({3: "Güçlü", 2: "Orta"}[gr["tier"]], "TOPLAM"), ok, gr["prob"], odd)
                acc(d, ({3: "Güçlü", 2: "Orta"}[gr["tier"]], gr["label"]), ok, gr["prob"], odd)
        rp = core.risky_pick(h)
        if rp and rp["key"] != "HTO15":
            ok = bool(core.settle_risky(rp["key"], [a, b])); acc(ALL, ("Riskli", "TOPLAM"), ok, rp["prob"])
        for band in core.LONG_BANDS:
            c = [x for x in core.long_cands(h) if band[1] <= x[2] <= band[2] and not x[0].startswith(("IY", "HF"))]
            if c:
                k, lab, v = max(c, key=lambda x: x[2]); ok = bool(core.settle_long(k, [a, b]))
                acc(ALL, ("Çok riskli", band[0]), ok, v)
print("YENİ LİGLER TOPLAM (2019+)")
show(ALL)
print("\nLig bazında ana seçimler:")
for code, d in sorted(BYLG.items()):
    z3 = d[("Güçlü", "TOPLAM")]; z2 = d[("Orta", "TOPLAM")]
    print(f"   {code}: Güçlü {z3[1]}/{z3[0]} %{100*z3[1]/max(z3[0],1):.1f} (%{100*z3[2]/max(z3[0],1):.1f}) · "
          f"Orta {z2[1]}/{z2[0]} %{100*z2[1]/max(z2[0],1):.1f} (%{100*z2[2]/max(z2[0],1):.1f})")
