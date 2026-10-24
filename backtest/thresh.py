import sys, numpy as np, collections
sys.path.insert(0, sys.path[0]); from lib import *
R = [m for m in load() if m["o"]]
weeks = len({(m["date"].isocalendar()[0], m["date"].isocalendar()[1]) for m in R})
print("MS favorisi, açılış olasılığı eşiğine göre (tüm sezonlar):")
for lo in (.60, .65, .70, .75, .80, .85):
    a = Acc(); od = []
    for m in R:
        k, v = pick_ms(m["o"])
        if v >= lo:
            a.add(m, k, v); o = price(m, k, "oA"); od.append(o or np.nan)
    print(f"  ≥%{int(lo*100)}: haftada ~{a.n/weeks:5.1f} seçim, tuttu %{100*a.w/a.n:5.1f}, ort. oran {np.nanmean(od):.2f}, getiri ort.oran {100*a.ret['oA']/a.rn['oA']:+5.1f}%  en iyi oran {100*a.ret['oM']/a.rn['oM']:+5.1f}%")
print("\nBirim (stake) karşılaştırması, MS + 2,5 seçimleri (KG oranı yok), açılış ort. oran:")
def run(stake):
    bank = 0; peak = 0; dd = 0; staked = 0
    for m in R:
        g = grade(m["o"])
        if not g or g[0] in ("KGV", "KGY"): continue
        o = price(m, g[1], "oA")
        if not o: continue
        s = stake(g)
        if not s: continue
        staked += s; bank += s * (o - 1) if won(m, g[1]) else -s
        peak = max(peak, bank); dd = max(dd, peak - bank)
    return staked, bank, dd
for name, f in (("Hepsine 1 birim", lambda g: 1), ("Güçlü 2, Orta 1", lambda g: 2 if g[3] == 3 else 1), ("Sadece Güçlü, 1 birim", lambda g: 1 if g[3] == 3 else 0)):
    st, b, dd = run(f); print(f"  {name:24s} yatırılan {st:7.0f} birim, net {b:+7.0f} ({100*b/st:+.1f}%), en büyük düşüş {dd:.0f} birim")
