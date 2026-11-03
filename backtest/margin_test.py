"""Marj çıkarma yöntemi ve oran kaynağı karşılaştırması.

Kaynaklar: piyasa ortalaması (Avg) ve Pinnacle (PS), açılış ve kapanış.
Yöntemler: oransal (mevcut fair()), Shin, power.
Ölçüler: log-loss / Brier (1X2 ve 2,5), kalibrasyon, botun seçim kurallarıyla isabet ve getiri.
Kullanım: python -I margin_test.py <fd_klasörü>
"""
import sys, os, csv, io, glob, math, collections
import numpy as np
from scipy.optimize import brentq

D = sys.argv[1]


def fnum(x):
    try:
        v = float(x); return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


# ---------- marj çıkarma ----------
def prop(o):
    q = [1 / x for x in o]; s = sum(q); return [v / s for v in q]


def shin(o):
    q = [1 / x for x in o]; B = sum(q)
    def p_of(z):
        return [(math.sqrt(z * z + 4 * (1 - z) * v * v / B) - z) / (2 * (1 - z)) for v in q]
    f = lambda z: sum(p_of(z)) - 1
    try:
        z = brentq(f, 0.0, 0.4)
    except ValueError:
        return prop(o)
    p = p_of(z); s = sum(p); return [v / s for v in p]


def power(o):
    q = [1 / x for x in o]
    f = lambda k: sum(v ** k for v in q) - 1
    try:
        k = brentq(f, 0.5, 3.0)
    except ValueError:
        return prop(o)
    return [v ** k for v in q]


METHODS = {"oransal": prop, "shin": shin, "power": power}
SOURCES = {"Ort. açılış": ("Avg", "Avg"), "Pinnacle açılış": ("PS", "P"),
           "Ort. kapanış": ("AvgC", "AvgC"), "Pinnacle kapanış": ("PSC", "PC")}

# ---------- veri ----------
rows = []
for path in sorted(glob.glob(os.path.join(D, "*", "*.csv"))):
    season = os.path.basename(os.path.dirname(path))
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if not r.get("FTHG") or not r.get("HomeTeam"):
                continue
            try:
                hg, ag = int(float(r["FTHG"])), int(float(r["FTAG"]))
            except ValueError:
                continue
            m = dict(season=season, lg=r["Div"], hg=hg, ag=ag, odds={})
            for name, (p3, p2) in SOURCES.items():
                o3 = [fnum(r.get(p3 + c)) for c in "HDA"]
                o2 = [fnum(r.get(p2 + ">2.5")), fnum(r.get(p2 + "<2.5"))]
                m["odds"][name] = (o3 if all(o3) else None, o2 if all(o2) else None)
            # getiri için ödenen oranlar (botun kullanıcısı ortalama oranı bulur; en iyi oran üst sınır)
            m["pay"] = {k: {"1": fnum(r.get(p + "H")), "X": fnum(r.get(p + "D")), "2": fnum(r.get(p + "A")),
                            "O": fnum(r.get(p + ">2.5")), "U": fnum(r.get(p + "<2.5"))}
                        for k, p in (("ort", "Avg"), ("max", "Max"), ("ortC", "AvgC"), ("maxC", "MaxC"))}
            rows.append(m)

# karşılaştırma adil olsun: tüm kaynaklarda 1X2 ve 2,5 oranı olan maçlar
R = [m for m in rows if all(m["odds"][s][0] and m["odds"][s][1] for s in SOURCES)]
print(f"Toplam {len(rows)} maç, tüm kaynaklarda tam oranı olan {len(R)} maç, "
      f"sezonlar {sorted({m['season'] for m in R})}, ligler {len({m['lg'] for m in R})}\n")


def outcome(m):
    a, b = m["hg"], m["ag"]; return ("1" if a > b else "X" if a == b else "2"), a + b >= 3


def won(m, key):
    a, b = m["hg"], m["ag"]
    return {"1": a > b, "X": a == b, "2": a < b, "O": a + b >= 3, "U": a + b < 3}[key]


def probs(m, src, meth):
    o3, o2 = m["odds"][src]
    p3 = METHODS[meth](o3); po = METHODS[meth](o2)[0]
    return {"1": p3[0], "X": p3[1], "2": p3[2], "O": po, "U": 1 - po}


def grade(p):
    """Botun kuralları (backtest/lib.py cands/grade), KG hariç: MS ve 2,5."""
    c = []
    k = max(("1", "X", "2"), key=lambda k: p[k]); v = p[k]
    if v >= .70: c.append(("MS", k, v, 3))
    elif v >= .60: c.append(("MS", k, v, 2))
    if p["O"] >= .70: c.append(("2,5Ü", "O", p["O"], 3))
    elif p["O"] >= .60: c.append(("2,5Ü", "O", p["O"], 2))
    if p["U"] >= .60: c.append(("2,5A", "U", p["U"], 2))
    if not c: return None
    c.sort(key=lambda t: (-t[3], -t[2])); return c[0]


res = {}
for src in SOURCES:
    for meth in METHODS:
        ll3 = br3 = ll2 = 0.0
        tiers = {3: [0, 0, 0.0, 0.0, 0, 0.0, 0], 2: [0, 0, 0.0, 0.0, 0, 0.0, 0]}  # n, w, ep, ret_ort, n_ort, ret_max, n_max
        fav = collections.defaultdict(lambda: [0, 0, 0.0])  # favori olasılık kovası: n, w, ep
        for m in R:
            p = probs(m, src, meth); y3, yo = outcome(m)
            ll3 += -math.log(max(p[y3], 1e-9)); br3 += sum((p[k] - (k == y3)) ** 2 for k in "1X2")
            ll2 += -math.log(max(p["O"] if yo else p["U"], 1e-9))
            k = max("1X2", key=lambda k: p[k]); b = min(int(p[k] * 20) / 20, 0.85)
            fv = fav[b]; fv[0] += 1; fv[1] += won(m, k); fv[2] += p[k]
            g = grade(p)
            if g:
                t = tiers[g[3]]; w = won(m, g[1]); t[0] += 1; t[1] += w; t[2] += g[2]
                cl = "C" if "kapanış" in src else ""  # seçimin yapıldığı andaki oranla öde
                for i, kk in ((3, "ort" + cl), (5, "max" + cl)):
                    o = m["pay"][kk][g[1]]
                    if o: t[i] += (o - 1) if w else -1; t[i + 1] += 1
        n = len(R)
        res[(src, meth)] = dict(ll3=ll3 / n, br3=br3 / n, ll2=ll2 / n, tiers=tiers, fav=dict(fav))

seasons = len({m["season"] for m in R}); weeks = seasons * 40
print("1) DOĞRULUK (düşük = daha iyi)")
print(f"{'kaynak':18s} {'yöntem':8s} {'log-loss 1X2':>13s} {'Brier 1X2':>10s} {'log-loss 2,5':>13s}")
for (src, meth), r in res.items():
    print(f"{src:18s} {meth:8s} {r['ll3']:13.5f} {r['br3']:10.5f} {r['ll2']:13.5f}")

print("\n2) BOTUN SEÇİM KURALLARIYLA (MS + 2,5; KG hariç)")
print(f"{'kaynak':18s} {'yöntem':8s} {'seviye':6s} {'seçim/hf':>8s} {'tuttu':>7s} {'beklenen':>9s} {'getiri ort.oran':>16s} {'getiri en iyi oran':>19s}")
for (src, meth), r in res.items():
    for tier, nm in ((3, "Güçlü"), (2, "Orta")):
        t = r["tiers"][tier]
        if not t[0]: continue
        print(f"{src:18s} {meth:8s} {nm:6s} {t[0]/weeks:8.1f} {100*t[1]/t[0]:6.1f}% {100*t[2]/t[0]:8.1f}% "
              f"{100*t[3]/max(t[4],1):+15.1f}% {100*t[5]/max(t[6],1):+18.1f}%")

print("\n3) KALİBRASYON — MS favorisi (gerçek tutma − tahmin, puan; 0'a yakın = doğru)")
buckets = [.50, .55, .60, .65, .70, .75, .80, .85]
print(f"{'kaynak':18s} {'yöntem':8s} " + " ".join(f"{'≥%'+str(int(b*100)):>7s}" for b in buckets))
for (src, meth), r in res.items():
    cells = []
    for b in buckets:
        fv = r["fav"].get(b)
        cells.append(f"{100*(fv[1]-fv[2])/fv[0]:+6.1f}" if fv and fv[0] >= 150 else "     -")
    print(f"{src:18s} {meth:8s} " + " ".join(f"{c:>7s}" for c in cells))
print("\n(kova sayıları, Ort. açılış/oransal):", {f"%{int(b*100)}": res[('Ort. açılış','oransal')]['fav'].get(b, [0])[0] for b in buckets})
