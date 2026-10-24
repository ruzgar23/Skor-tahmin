import sys, pickle, numpy as np, collections
sys.path.insert(0, sys.path[0]); from lib import *
from scipy.optimize import minimize
R = [m for m in pickle.load(open(BASE + "feat.pkl", "rb")) if m["o"] and m["c"]]
def resid(name, sel, key, t="o"):
    xs = [(won(m, key) - prob(m, key, t)) for m in R if sel(m)]
    if len(xs) < 30: return
    a = np.array(xs, float); se = a.std() / np.sqrt(len(a))
    print(f"  {name:44s} n={len(a):6d}  gerçekleşen − piyasa = {100*a.mean():+5.2f} puan (±{196*se:.2f})")
print("1) Piyasanın (açılış) olasılığına göre artık etki. ± = %95 güven aralığı. 0'ı içeriyorsa etki yok demektir.")
print(" Ev sahibi kazanır:")
for lo, hi, nm_ in ((-15, -3, "ev ≥3 gün daha az dinlenmiş"), (-2, -1, "ev 1-2 gün az"), (0, 0, "eşit"), (1, 2, "ev 1-2 gün fazla"), (3, 15, "ev ≥3 gün daha fazla dinlenmiş")):
    resid(nm_, lambda m, lo=lo, hi=hi: m["rest_h"] and m["rest_a"] and lo <= m["rest_h"] - m["rest_a"] <= hi, "1")
resid("ev 3 gün veya daha az dinlenmiş", lambda m: m["rest_h"] and m["rest_h"] <= 3, "1")
resid("ev ≤4 gün önce Avrupa'da oynadı", lambda m: m["eub_h"], "1")
resid("deplasman ≤4 gün önce Avrupa'da oynadı (ev kazanır)", lambda m: m["eub_a"], "1")
resid("ev ≤4 gün sonra Avrupa'da oynayacak", lambda m: m["eua_h"], "1")
resid("deplasman ≤4 gün sonra Avrupa'da (ev kazanır)", lambda m: m["eua_a"], "1")
resid("ev sezon sonu hedefsiz", lambda m: m["dead_h"] and not m["dead_a"], "1")
resid("deplasman sezon sonu hedefsiz (ev kazanır)", lambda m: m["dead_a"] and not m["dead_h"], "1")
resid("ikisi de hedefsiz (ev kazanır)", lambda m: m["dead_a"] and m["dead_h"], "1")
print(" 2,5 Üst:")
resid("ikisi de hedefsiz", lambda m: m["dead_a"] and m["dead_h"], "O")
resid("biri ≤4 gün önce Avrupa'da", lambda m: m["eub_h"] or m["eub_a"], "O")
resid("son 14 günde toplam ≥8 maç (iki takım)", lambda m: m["n14_h"] + m["n14_a"] >= 8, "O")
print(" Aynı testler kapanış oranına göre (piyasa sonunda fiyatlıyor mu):")
resid("ev ≤4 gün önce Avrupa'da (kapanış)", lambda m: m["eub_h"], "1", "c")
resid("deplasman hedefsiz (kapanış)", lambda m: m["dead_a"] and not m["dead_h"], "1", "c")
resid("ev hedefsiz (kapanış)", lambda m: m["dead_h"] and not m["dead_a"], "1", "c")
# 2) seçim düzeyinde: aleyhte etken varsa seçim tutma oranı
print("\n2) Seçim düzeyinde (Güçlü+Orta MS seçimleri): aleyhte yorgunluk/motivasyon varsa")
def against(m, key):
    h = key == "1"; a = key == "2"
    if not (h or a): return None
    me, op = ("h", "a") if h else ("a", "h")
    f = []
    if m["eub_" + me] and not m["eub_" + op]: f.append("Avrupa yorgunu")
    if m["dead_" + me] and not m["dead_" + op]: f.append("hedefsiz")
    if m["rest_" + me] and m["rest_" + op] and m["rest_" + op] - m["rest_" + me] >= 3: f.append("az dinlenmiş")
    return f
A = collections.defaultdict(Acc)
for m in R:
    g = grade(m["o"])
    if not g or g[0] != "MS": continue
    f = against(m, g[1])
    if f is None: continue
    A["aleyhte etken var" if f else "aleyhte etken yok"].add(m, g[1], g[2])
    for x in f: A["  - " + x].add(m, g[1], g[2])
for k in A: print(A[k].row(k))
