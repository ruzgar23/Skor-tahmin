"""KG dahil, botun tam seçim kurallarıyla (bot/core.py grade) sayım.
KG olasılığı, adil 1X2 ve 2,5 olasılıklarına uydurulan gol beklentisinden (Poisson + Dixon-Coles) hesaplanır;
botun canlıda yaptığı gibi. Kullanım: python -I backtest/kg_test.py <fd_klasörü>"""
import sys, os, io, contextlib, math
import numpy as np

sys.argv = [sys.argv[0], sys.argv[1]]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "margin_test.py"), encoding="utf-8").read()
with contextlib.redirect_stdout(io.StringIO()):
    exec(src.split("res = {}")[0])  # veri, yöntemler, probs(), won()

RHO = -0.06; K = 11
g = np.round(np.arange(0.15, 4.5, 0.025), 4)
pois = np.array([[math.exp(-l) * l ** k / math.factorial(k) for k in range(K)] for l in g])
P1 = np.zeros((len(g), len(g))); P2 = P1.copy(); PO = P1.copy(); PB = P1.copy()
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
        if i > 0 and j > 0: PB += w
S = P1 + P2 + (1 - P1 - P2)  # normalize gerekmez; ızgara zaten ~1
P1f, P2f, POf, PBf = P1.ravel(), P2.ravel(), PO.ravel(), PB.ravel()


def btts(p):
    k = np.argmin((P1f - p["1"]) ** 2 + (P2f - p["2"]) ** 2 + (POf - p["O"]) ** 2)
    return float(PBf[k])


def grade(p):
    c = []
    k = max(("1", "X", "2"), key=lambda k: p[k]); v = p[k]
    if v >= .70: c.append(("MS", k, v, 3))
    elif v >= .60: c.append(("MS", k, v, 2))
    if p["O"] >= .70: c.append(("2,5 Üst", "O", p["O"], 3))
    elif p["O"] >= .60: c.append(("2,5 Üst", "O", p["O"], 2))
    if p["U"] >= .60: c.append(("2,5 Alt", "U", p["U"], 2))
    if p["B"] >= .60: c.append(("KG Var", "B", p["B"], 2))
    if 1 - p["B"] >= .60: c.append(("KG Yok", "NB", 1 - p["B"], 1))
    if not c: return None
    c.sort(key=lambda t: (-t[3], -t[2])); return c[0]


def hit(m, key):
    a, b = m["hg"], m["ag"]
    if key == "B": return a > 0 and b > 0
    if key == "NB": return not (a > 0 and b > 0)
    return won(m, key)


for srcname in ("Ort. açılış", "Ort. kapanış"):
    for meth in ("oransal", "power"):
        T = {}; F = {}
        for m in R:
            p = probs(m, srcname, meth); p["B"] = btts(p)
            gr = grade(p)
            if not gr: continue
            w = hit(m, gr[1])
            t = T.setdefault(gr[3], [0, 0]); t[0] += 1; t[1] += w
            f = F.setdefault((gr[3], gr[0]), [0, 0]); f[0] += 1; f[1] += w
        print(f"\n{srcname} · {meth}")
        tot = [0, 0]
        for tier, nm in ((3, "Güçlü"), (2, "Orta"), (1, "Zayıf")):
            t = T.get(tier)
            if not t: continue
            if tier >= 2: tot[0] += t[0]; tot[1] += t[1]
            print(f"  {nm:6s} {t[1]:5d} / {t[0]:5d}  %{100*t[1]/t[0]:.1f}")
            for (tt, fam), f in sorted(F.items()):
                if tt == tier:
                    print(f"     {fam:8s} {f[1]:5d} / {f[0]:5d}  %{100*f[1]/f[0]:.1f}")
        print(f"  Güçlü+Orta {tot[1]} / {tot[0]}  %{100*tot[1]/tot[0]:.1f}")
