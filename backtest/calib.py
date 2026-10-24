"""Lig bazlı ve genel kalibrasyon, ileriye dönük (önceki sezonlarla öğren, sonraki sezonda dene)."""
import sys, numpy as np, collections
sys.path.insert(0, sys.path[0]); from lib import *
from scipy.optimize import minimize
R = [m for m in load() if m["o"]]
SEAS = sorted({m["season"] for m in R}); LGS = sorted({m["lg"] for m in R})
FAM = {"MS": ("1", "X", "2"), "O25": ("O",), "U25": ("U",), "KGV": ("B",), "KGY": ("NB",)}
def lg_(p): p = min(max(p, 1e-4), 1 - 1e-4); return np.log(p / (1 - p))
def sig(x): return 1 / (1 + np.exp(-x))
def rows(ms, fam):
    X = []
    for m in ms:
        if fam == "MS":
            k, v = pick_ms(m["o"])
        else:
            k = FAM[fam][0]; v = prob(m, k, "o")
        X.append((lg_(v), LGS.index(m["lg"]), won(m, k)))
    return X
def fit(X, ridge=30.0, league=True):
    z = np.array([x[0] for x in X]); li = np.array([x[1] for x in X]); y = np.array([x[2] for x in X], float)
    nL = len(LGS)
    def f(w):
        a, b = w[0], w[1]; u = w[2:] if league else np.zeros(nL)
        q = sig(a + b * z + u[li]); q = np.clip(q, 1e-9, 1 - 1e-9)
        return -np.sum(y * np.log(q) + (1 - y) * np.log(1 - q)) + ridge * np.sum(u ** 2)
    w0 = np.r_[0, 1, np.zeros(nL if league else 0)]
    return minimize(f, w0, method="L-BFGS-B").x
def apply(w, z, li, league=True):
    u = w[2:] if league else np.zeros(len(LGS)); return sig(w[0] + w[1] * z + u[li])
out = collections.defaultdict(lambda: collections.defaultdict(Acc))
ll = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0])
for ti, ts in enumerate(SEAS):
    if ti < 2: continue
    train = [m for m in R if m["season"] < ts]; test = [m for m in R if m["season"] == ts]
    W = {f: (fit(rows(train, f), league=False), fit(rows(train, f))) for f in FAM}
    for m in test:
        cand = {}
        for f in FAM:
            if f == "MS": k, v = pick_ms(m["o"])
            else: k = FAM[f][0]; v = prob(m, k, "o")
            z = lg_(v); li = LGS.index(m["lg"])
            pg = apply(W[f][0], z, li, False); pl = apply(W[f][1], z, li)
            cand[f] = (k, v, pg, pl)
            y = won(m, k); L = ll[f]
            for i, q in enumerate((v, pg, pl)): L[i] += -(y * np.log(q) + (1 - y) * np.log(1 - q))
            L[3] += 1
        for vi, vname in ((1, "piyasa (bugünkü)"), (2, "genel kalibrasyon"), (3, "lig bazlı kalibrasyon")):
            # aynı kurallarla seçim (kural: grade) — olasılıklar değiştirilmiş
            c = []
            k, v = cand["MS"][0], cand["MS"][vi]
            if v >= .70: c.append(("MS", k, v, 3))
            elif v >= .60: c.append(("MS", k, v, 2))
            vo = cand["O25"][vi]; vu = cand["U25"][vi]; vb = cand["KGV"][vi]; vn = cand["KGY"][vi]
            if vo >= .70: c.append(("O25", "O", vo, 3))
            elif vo >= .60: c.append(("O25", "O", vo, 2))
            if vu >= .60: c.append(("U25", "U", vu, 2))
            if vb >= .60: c.append(("KGV", "B", vb, 2))
            if not c: continue
            c.sort(key=lambda t: (-t[3], -t[2])); fam, key, p, tier = c[0]
            out[vname][tier].add(m, key, p); out[vname][(tier, fam)].add(m, key, p)
print("Log-loss (düşük = daha iyi), 2122→2627 ileriye dönük:")
for f, L in ll.items(): print(f"  {f:4s} piyasa {L[0]/L[3]:.4f}  genel {L[1]/L[3]:.4f}  lig bazlı {L[2]/L[3]:.4f}")
for v in out:
    print("\n" + v)
    for k in sorted(out[v], key=lambda k: (str(type(k)), k if isinstance(k, int) else (k[0], k[1]))):
        name = ({3: "GÜÇLÜ toplam", 2: "ORTA toplam"}[k] if isinstance(k, int) else f"  {['','','Orta','Güçlü'][k[0]]} {k[1]}")
        print(out[v][k].row(name))
