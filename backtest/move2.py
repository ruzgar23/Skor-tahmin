import sys; sys.path.insert(0, sys.path[0]); from lib import *
R = load()
print("Filtre: açılıştaki seçim, kapanışa kadar aleyhine ≥X kaydıysa iptal. Sezon sezon tutma oranı (Güçlü+Orta, KG hariç)")
for th in (None, .03, .02, .01):
    row = []; tot = Acc()
    for s in sorted({m["season"] for m in R}):
        a = Acc()
        for m in R:
            if m["season"] != s or not (m["o"] and m["c"]): continue
            g = grade(m["o"])
            if not g or g[0] in ("KGV", "KGY"): continue
            mv = prob(m, g[1], "c") - g[2]
            if th is not None and mv <= -th: continue
            a.add(m, g[1], g[2], srcs=("oA", "cA")); tot.add(m, g[1], g[2], srcs=("oA", "cA"))
        row.append(f"{s}:{100*a.w/a.n:4.1f}")
    print(f"{'yok' if th is None else '-'+str(th):5s} n={tot.n:6d} tuttu %{100*tot.w/tot.n:5.1f} getiri(açılış ort.) {100*tot.ret['oA']/tot.rn['oA']:+5.1f}% kapanış {100*tot.ret['cA']/tot.rn['cA']:+5.1f}% | " + " ".join(row))
print("\nHareketi takip ≥0.08 (MS), sezonlara göre getiri (kapanış ort. oran):")
for s in sorted({m["season"] for m in R}):
    a = Acc()
    for m in R:
        if m["season"] != s or not (m["o"] and m["c"]): continue
        for k in ("1", "X", "2"):
            if prob(m, k, "c") - prob(m, k, "o") >= .08: a.add(m, k, prob(m, k, "c"), srcs=("cA",))
    if a.n: print(f"  {s} n={a.n:4d} tuttu %{100*a.w/a.n:5.1f} getiri {100*a.ret['cA']/a.rn['cA']:+6.1f}%")
