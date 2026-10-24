import sys; sys.path.insert(0, sys.path[0]); from lib import *
R = load()
bins = [(-1, -.06), (-.06, -.03), (-.03, -.01), (-.01, .01), (.01, .03), (.03, .06), (.06, 1)]
A = collections.defaultdict(Acc); B = collections.defaultdict(Acc)
for m in R:
    if not (m["o"] and m["c"]): continue
    g = grade(m["o"])
    if not g or g[0] in ("KGV", "KGY"): continue
    fam, key, p, tier = g; pc = prob(m, key, "c"); mv = pc - p
    for lo, hi in bins:
        if lo <= mv < hi: A[(lo, hi)].add(m, key, pc, srcs=("cA", "cM", "oA"))
    A["tümü"].add(m, key, pc, srcs=("cA", "cM", "oA"))
    # CLV: açılış oranı kapanıştan iyi mi
    oo, co = price(m, key, "oA"), price(m, key, "cA")
    if oo and co: B["clv"].n += 1; B["clv"].w += oo > co; B["clv"].ep += oo / co - 1
print("Seçim açılışta yapılır, sonuç kapanış oranıyla ölçülür. Hareket = kapanış olasılığı − açılış olasılığı")
for k in [b for b in bins] + ["tümü"]:
    a = A[k]; n = a.n
    if not n: continue
    r = " ".join(f"{s}:{100*a.ret[s]/a.rn[s]:+5.1f}%" for s in ("oA", "cA", "cM") if a.rn[s])
    print(f"{str(k):16s} n={n:6d} tuttu %{100*a.w/n:5.1f} (kapanışa göre beklenen %{100*a.ep/n:5.1f})  {r}")
c = B["clv"]; print(f"\nAçılış oranı kapanıştan yüksekti: %{100*c.w/c.n:.1f}  ortalama fiyat farkı {100*c.ep/c.n:+.2f}%")
# Strateji: kapanışa yakın, kapanış olasılıklarıyla yeniden seç
C = collections.defaultdict(Acc)
for m in R:
    if not (m["o"] and m["c"]): continue
    for t, name in (("o", "açılışta seç, açılış oranı"), ("c", "maç önü seç, kapanış oranı")):
        g = grade(m[t])
        if not g or g[0] in ("KGV", "KGY"): continue
        C[(name, g[3])].add(m, g[1], g[2], srcs=(("oA", "oM") if t == "o" else ("cA", "cM")))
print()
for k in sorted(C): a = C[k]; print(f"{k[0]:28s} {'Güçlü' if k[1]==3 else 'Orta ':5s} n={a.n:6d} tuttu %{100*a.w/a.n:5.1f} " + " ".join(f"{s}:{100*a.ret[s]/a.rn[s]:+5.1f}%" for s in a.rn))
# Hareketi takip: kapanışta, açılıştan ≥X güçlenen tarafa oyna (MS)
print("\nHareket takibi (MS, kapanış oranıyla oyna):")
for th in (.03, .05, .08, .12):
    a = Acc()
    for m in R:
        if not (m["o"] and m["c"]): continue
        for k in ("1", "X", "2"):
            if prob(m, k, "c") - prob(m, k, "o") >= th: a.add(m, k, prob(m, k, "c"), srcs=("cA", "cM"))
    print(f"  ≥{th:.2f}: n={a.n:5d} tuttu %{100*a.w/max(a.n,1):5.1f} beklenen %{100*a.ep/max(a.n,1):5.1f} " + " ".join(f"{s}:{100*a.ret[s]/a.rn[s]:+5.1f}%" for s in a.rn))
