"""Canlı bildirim simülasyonu: bot maç başına bir gol bildirimi gönderir (ilk uygun seçim). 15–78. dakika, 5 dk arayla.
Eski sürüm (düz gol dağılımı, yalnızca eski pazarlar) ile yeni sürümü (gerçek gol eğrisi + İY, takım golü, sıradaki gol)
2025-26 maçlarında karşılaştırır. Kullanım: python -I backtest/live_alert_sim.py <goals.pkl> <fd_klasörü>"""
import sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "live_goal_test.py"), encoding="utf-8").read()
exec(src.split("for name, curve in (")[0])
sys.path.insert(0, os.path.join(HERE, "..", "bot"))
import extra as X
MINS1 = [(t, 1) for t in range(15, 45, 5)] + [(45, 1)] + [(t, 2) for t in range(50, 79, 5)]


def ht_of(m): return [sum(1 for mn, s in m["goals"] if mn <= 45 and s == side) for side in "ha"]


def sim(new):
    L.GOAL_CURVE = CURVE if new else None
    L.KGY_FIX, L.D12_FIX = (0.0, 0.02) if new else (0.02, 0.0)
    fam = collections.defaultdict(lambda: [0, 0, 0.0]); unres = 0
    for m, x in TEST:
        p3 = E.fair(x["o"], ("1", "X", "2")); po = E.fair(x["o"], ("O", "U"))["O"]
        lh, la = lams(p3["1"], p3["2"], po)
        for t, per in MINS1:
            hs = sum(1 for mn, s in m["goals"] if mn <= t and s == "h"); as_ = sum(1 for mn, s in m["goals"] if mn <= t and s == "a")
            rh = sum(1 for mn, s in m["reds"] if mn <= t and s == "h"); ra = sum(1 for mn, s in m["reds"] if mn <= t and s == "a")
            p, tl, _, _, _ = L.inplay(lh, la, hs, as_, t, per, rh, ra)
            ex = L.extra_live(lh, la, hs, as_, t, per, rh, ra) if new else None
            pk = L.picks_for(p, tl, t, None, hs + as_, ex)
            if not pk: continue
            pk = pk[0]; k = pk["k"]
            if k.startswith("NEXT"):
                nxt = [s for mn, s in m["goals"] if mn > t]
                w = bool(nxt) and nxt[0] == ("h" if k == "NEXT1" else "a")
            else:
                w = X.live_settle(k, [hs, as_], [m["hs"], m["as_"]], True, None, ht_of(m), False)
            if w not in (True, False): unres += 1; break
            f = ("İY" if k.startswith("IY") else "Takım golü" if k[:2] in ("EO", "EU", "DO", "DU") else
                 "Sıradaki gol" if k.startswith("NEXT") else "Alt/Üst" if k[0] in "OU" else pk["label"])
            for key in (f, "TOPLAM"):
                c = fam[key]; c[0] += 1; c[1] += w; c[2] += pk["prob"]
            break
    return fam, unres


for name, new in (("ESKİ", False), ("YENİ", True)):
    fam, u = sim(new)
    print(f"\n=== {name}: maç başına ilk bildirim, {len(TEST)} maç (2025-26) ===")
    for f, c in sorted(fam.items(), key=lambda x: -x[1][0]):
        print(f"  {f:26s} {c[1]:5d}/{c[0]:5d} %{100*c[1]/c[0]:.1f} (beklenen %{100*c[2]/c[0]:.1f})")
