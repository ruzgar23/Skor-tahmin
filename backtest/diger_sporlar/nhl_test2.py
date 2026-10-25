import pickle, collections, numpy as np
from scipy.stats import poisson
from scipy.optimize import minimize
G = [m for m in pickle.load(open("us_odds.pkl", "rb")) if m["sp"] == "nhl" and m.get("book") == "DraftKings" and m.get("stype") == 2]
K = 12; ks = np.arange(K)
import sys
D = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
def mat(lh, la):
    M = np.outer(poisson.pmf(ks, lh), poisson.pmf(ks, la)); M[np.diag_indices(K)] *= D; return M / M.sum()
def reg(lh, la):
    M = mat(lh, la); return np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum(), M
def fit(ph, tot, pover):
    def loss(v):
        lh, la = np.exp(v); p1, px, p2, M = reg(lh, la)
        pw = p1 + px * lh / (lh + la)  # uzatma/penaltıda gol oranına göre
        l = (pw - ph) ** 2
        if tot is not None and pover is not None:
            tt = np.add.outer(ks, ks); l += (M[tt > tot].sum() - pover) ** 2
        else: l += 0.01 * (lh + la - 6) ** 2
        return l
    r = minimize(loss, [np.log(3.1), np.log(2.9)], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-10})
    return np.exp(r.x)
rows = []
for m in G:
    ph = (1/m["mlh"]) / (1/m["mlh"] + 1/m["mla"])
    po = None
    if m.get("overOdds") and m.get("underOdds"): po = (1/m["overOdds"]) / (1/m["overOdds"] + 1/m["underOdds"])
    lh, la = fit(ph, m.get("total"), po); p1, px, p2, M = reg(lh, la)
    tt = np.add.outer(ks, ks)
    # gerçek normal süre sonucu: uzatmaya gittiyse beraberlik
    if m["ot"]: r1 = rX = r2 = None; res = "X"; rh = ra = min(m["hs"], m["as_"])
    else: res = "1" if m["hs"] > m["as_"] else "2"; rh, ra = m["hs"], m["as_"]
    rows.append(dict(m=m, ph=ph, p={"1": p1, "X": px, "2": p2, "1X": p1 + px, "X2": px + p2, "O55": M[tt > 5.5].sum(), "U55": M[tt < 5.5].sum(), "O45": M[tt > 4.5].sum(), "U65": M[tt < 6.5].sum()},
                     res=res, tot=rh + ra))
print("NHL DraftKings normal sezon maçı:", len(rows))
def won(r, k):
    return {"1": r["res"] == "1", "X": r["res"] == "X", "2": r["res"] == "2", "1X": r["res"] != "2", "X2": r["res"] != "1",
            "O55": r["tot"] > 5.5, "U55": r["tot"] < 5.5, "O45": r["tot"] > 4.5, "U65": r["tot"] < 6.5}[k]
print("Normal süre beraberlik: gerçek %{:.1f}, model %{:.1f}".format(100*np.mean([r["res"] == "X" for r in rows]), 100*np.mean([r["p"]["X"] for r in rows])))
print("Normal süre toplam gol 5,5 üstü: gerçek %{:.1f}, model %{:.1f}".format(100*np.mean([r["tot"] > 5.5 for r in rows]), 100*np.mean([r["p"]["O55"] for r in rows])))
for k in ("1X", "X2", "1", "2", "O45", "U55", "U65"):
    b = collections.defaultdict(list)
    for r in rows:
        v = r["p"][k]
        if v >= .55: b[min(int(v * 20) / 20, .85)].append((won(r, k), v))
    for x in sorted(b):
        L = b[x]; print(f"  {k:4s} model %{int(x*100)}+: n={len(L):4d} tuttu %{100*np.mean([a for a, _ in L]):5.1f} beklenen %{100*np.mean([v for _, v in L]):5.1f}")
pickle.dump(rows, open("nhl_rows.pkl", "wb"))
