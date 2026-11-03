"""Birleşik bahisler: MS (ya da çifte şans) + 2,5 Alt/Üst ve MS + KG. Olasılık skor matrisinden (botla aynı yol),
sonuç maç skorundan. Bu pazarlar için geçmiş oran yok: yalnızca isabet ve kalibrasyon ölçülür.
Kullanım: python -I backtest/combo_test.py <fd_klasörü>"""
import sys, os, io, csv, glob, math, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import engine as E
src = open(os.path.join(HERE, "new_markets_test.py"), encoding="utf-8").read()
exec(src[src.index("RHO = -0.06"):src.index("rows = []")])  # ızgara ve lams()

def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None

rows = []
for path in sorted(glob.glob(os.path.join(sys.argv[1], "*", "*.csv"))):
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            try: a, b = int(float(r["FTHG"])), int(float(r["FTAG"]))
            except (KeyError, ValueError, TypeError): continue
            o = {k: fnum(r.get(c)) for k, c in (("1", "AvgH"), ("X", "AvgD"), ("2", "AvgA"), ("O", "Avg>2.5"), ("U", "Avg<2.5"))}
            if all(v and v > 1 for v in o.values()): rows.append((o, a, b))
print(f"{len(rows)} maç\n")
R = {"1": lambda I, J: I > J, "X": lambda I, J: I == J, "2": lambda I, J: I < J,
     "1X": lambda I, J: I >= J, "X2": lambda I, J: I <= J, "12": lambda I, J: I != J}
T = {"2,5 Üst": lambda I, J: I + J >= 3, "2,5 Alt": lambda I, J: I + J <= 2,
     "KG Var": lambda I, J: (I > 0) & (J > 0), "KG Yok": lambda I, J: ~((I > 0) & (J > 0))}
st = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0.0]))
best = collections.defaultdict(lambda: [0, 0, 0.0])
for o, a, b in rows:
    p3 = E.fair(o, ("1", "X", "2")); po = E.fair(o, ("O", "U"))["O"]
    lh, la = lams(p3["1"], p3["2"], po)
    M = E.score_matrix(lh, la, RHO); I, J = np.meshgrid(range(M.shape[0]), range(M.shape[0]), indexing="ij")
    A, B = np.array(a), np.array(b)
    top = None
    for rk, rf in R.items():
        for tk, tf in T.items():
            if rk in ("1X", "X2", "12") and tk.startswith("KG"): continue
            v = float(M[rf(I, J) & tf(I, J)].sum())
            if v >= .50:
                bk = min(int(v * 10) / 10, .8); c = st[f"{rk} & {tk}"][bk]; w = bool(rf(A, B) and tf(A, B))
                c[0] += 1; c[1] += w; c[2] += v
            if .60 <= v < .80 and (top is None or v > top[1]): top = (f"{rk} & {tk}", v, bool(rf(A, B) and tf(A, B)))
    if top:
        c = best[top[0]]; c[0] += 1; c[1] += top[2]; c[2] += top[1]
        c = best["TOPLAM"]; c[0] += 1; c[1] += top[2]; c[2] += top[1]
weeks = 8 * 40
print("Kalibrasyon: tuttu/sayı, gerçek% (beklenen%), haftada")
for k, d in st.items():
    cells = [f"%{int(b*100)}+: {c[1]}/{c[0]} %{100*c[1]/c[0]:.1f} (%{100*c[2]/c[0]:.1f}) {c[0]/weeks:.1f}/hf" for b, c in sorted(d.items()) if c[0] >= 50]
    if cells: print(f"  {k:18s} " + " | ".join(cells))
print("\nMaç başına en olası birleşik seçim (%60–80):")
for k, c in sorted(best.items(), key=lambda x: -x[1][0]):
    print(f"  {k:18s} {c[1]:6d}/{c[0]:6d} %{100*c[1]/c[0]:.1f} (beklenen %{100*c[2]/c[0]:.1f})")
