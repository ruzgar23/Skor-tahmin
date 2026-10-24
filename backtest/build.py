"""Backtest tabanı: her maç için açılış ve kapanış piyasa olasılıkları (1X2, 2,5, KG) + oranlar."""
import sys, glob, os, pickle, numpy as np
sys.path.insert(0, "/home/claude/skor-tahmin/engine"); import engine as E
D = sys.argv[1]; OUT = sys.argv[2]
RHO = -0.06
# ızgara: lh, la -> marketler
g = np.round(np.arange(0.15, 4.5, 0.025), 4); n = len(g); K = 11
from math import factorial
pois = np.array([[np.exp(-l) * l**k / factorial(k) for k in range(K)] for l in g])  # n x K
LH, LA = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
P1 = np.zeros((n, n)); P2 = np.zeros((n, n)); PO = np.zeros((n, n)); PB = np.zeros((n, n)); PO15 = np.zeros((n, n)); PO35 = np.zeros((n, n))
for i in range(K):
    for j in range(K):
        w = pois[:, i][:, None] * pois[:, j][None, :]
        lh = g[:, None]; la = g[None, :]
        if i == 0 and j == 0: w = w * (1 - lh * la * RHO)
        elif i == 0 and j == 1: w = w * (1 + lh * RHO)
        elif i == 1 and j == 0: w = w * (1 + la * RHO)
        elif i == 1 and j == 1: w = w * (1 - RHO)
        if i > j: P1 += w
        if i < j: P2 += w
        if i + j >= 3: PO += w
        if i + j >= 2: PO15 += w
        if i + j >= 4: PO35 += w
        if i > 0 and j > 0: PB += w
tot = None
def fair3(h, d, a):
    if not (h and d and a) or min(h, d, a) <= 1: return None
    s = 1/h + 1/d + 1/a; return (1/h/s, 1/d/s, 1/a/s)
def fair2(o, u):
    if not (o and u) or min(o, u) <= 1: return None
    s = 1/o + 1/u; return 1/o/s
def fit(p1, p2, po):
    L = (P1 - p1)**2 + (P2 - p2)**2 + ((PO - po)**2 if po is not None else 0)
    k = np.argmin(L); i, j = divmod(k, n)
    return dict(lh=g[i], la=g[j], **{"1": P1[i,j], "2": P2[i,j], "X": 1-P1[i,j]-P2[i,j], "O25": PO[i,j], "BTTS": PB[i,j], "O15": PO15[i,j], "O35": PO35[i,j]})
f = E.fnum
rows = []
for path in sorted(glob.glob(os.path.join(D, "*.csv"))):
    season = os.path.basename(path)[:4]
    for r in E.read_rows(path):
        if not r.get("FTHG") or not r.get("HomeTeam"): continue
        d = E.pdate(r["Date"])
        if not d: continue
        m = dict(lg=r["Div"], season=season, date=d, time=r.get("Time", ""), home=r["HomeTeam"].strip(), away=r["AwayTeam"].strip(),
                 hg=int(float(r["FTHG"])), ag=int(float(r["FTAG"])), ref=r.get("Referee", ""))
        for tag, pre, ou in (("o", "Avg", "Avg"), ("c", "AvgC", "AvgC"), ("po", "PS", "P"), ("pc", "PSC", "PC")):
            fr = fair3(f(r.get(pre+"H")), f(r.get(pre+"D")), f(r.get(pre+"A")))
            fo = fair2(f(r.get(ou+">2.5")), f(r.get(ou+"<2.5")))
            m[tag] = None if fr is None else dict(fit(fr[0], fr[2], fo), raw1=fr[0], rawX=fr[1], raw2=fr[2], rawO=fo)
        # gerçek oranlar (getiri için)
        for k, c in (("1", "H"), ("X", "D"), ("2", "A")):
            m["oA"+k] = f(r.get("Avg"+c)); m["oM"+k] = f(r.get("Max"+c)); m["cA"+k] = f(r.get("AvgC"+c)); m["cM"+k] = f(r.get("MaxC"+c))
        m["oAO"] = f(r.get("Avg>2.5")); m["oAU"] = f(r.get("Avg<2.5")); m["oMO"] = f(r.get("Max>2.5")); m["oMU"] = f(r.get("Max<2.5"))
        m["cAO"] = f(r.get("AvgC>2.5")); m["cAU"] = f(r.get("AvgC<2.5")); m["cMO"] = f(r.get("MaxC>2.5")); m["cMU"] = f(r.get("MaxC<2.5"))
        rows.append(m)
rows.sort(key=lambda m: (m["date"], m["lg"]))
pickle.dump(rows, open(OUT, "wb"))
import collections
print(len(rows), "maç;", collections.Counter(m["season"] for m in rows))
print("açılış var", sum(1 for m in rows if m["o"]), "kapanış var", sum(1 for m in rows if m["c"]), "açılış 2,5 var", sum(1 for m in rows if m["o"] and m["o"]["rawO"]))
