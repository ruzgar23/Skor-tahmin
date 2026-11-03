"""Yeni canlı pazarların testi: İY sonucu, İY 0,5/1,5 Alt-Üst, takım gol alt/üst, sıradaki gol.
Veri: goal_events.py (ESPN gol ve kırmızı kart dakikaları) + football-data kapanış oranları (maç öncesi gol beklentisi).
Bot kodunu (live.extra_live) doğrudan kullanır; 15–78. dakikalarda her 5 dakikada bir anlık durum.
Kullanım: python -I backtest/live_goal_test.py <goals.pkl> <fd_klasörü>"""
import sys, os, io, csv, glob, math, pickle, collections
import numpy as np
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import engine as E, espn, live as L
src = open(os.path.join(HERE, "new_markets_test.py"), encoding="utf-8").read()
exec(src[src.index("RHO = -0.06"):src.index("rows = []")])  # ızgara ve lams()

G = pickle.load(open(sys.argv[1], "rb"))
FD = collections.defaultdict(list)
for path in glob.glob(os.path.join(sys.argv[2], "*", "*.csv")):
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            d = E.pdate(r.get("Date") or "")
            o = {k: E.fnum(r.get(c)) for k, c in (("1", "AvgCH"), ("X", "AvgCD"), ("2", "AvgCA"), ("O", "AvgC>2.5"), ("U", "AvgC<2.5"))}
            if d and all(v and v > 1 for v in o.values()):
                FD[r["Div"]].append(dict(date=d, home=r["HomeTeam"].strip(), away=r["AwayTeam"].strip(), o=o,
                                         hg=E.fnum(r.get("FTHG")), ag=E.fnum(r.get("FTAG"))))
idx = {}
names = {lg: {x["home"] for x in v} | {x["away"] for x in v} for lg, v in FD.items()}
for lg, v in FD.items():
    for x in v: idx[(lg, x["home"], x["away"], x["date"])] = x
rows = []
for m in G:
    if m["lg"] not in names: continue
    h = espn.match_name(m["home"], names[m["lg"]]); a = espn.match_name(m["away"], names[m["lg"]])
    d0 = date.fromisoformat(m["date"]); x = None
    for dd in (0, -1, 1):
        x = idx.get((m["lg"], h, a, d0 + timedelta(days=dd)))
        if x: break
    if not x or x["hg"] != m["hs"] or x["ag"] != m["as_"]: continue  # skor da tutmalı
    rows.append((m, x))
print(f"ESPN maç {len(G)}, oranla eşleşen (skor kontrollü) {len(rows)}; ligler {dict(collections.Counter(m['lg'] for m, _ in rows))}\n")

MINS = [(t, 1) for t in range(15, 45, 5)] + [(45, 1)] + [(t, 2) for t in range(50, 80, 5)]  # (45, 1) = devre arası
fam = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0.0]))


def famof(k):
    if k.startswith("SHO") or k.startswith("SHU"): return "2Y " + ("Üst" if k[2] == "O" else "Alt") + " " + k[3:]
    if k.startswith("SH"): return "2Y sonucu"
    if k.startswith("IYO") or k.startswith("IYU"): return "İY " + ("Üst" if k[2] == "O" else "Alt") + " " + k[3:]
    if k.startswith("IY"): return "İY sonucu"
    if k.startswith("NEXT"): return "Sıradaki gol"
    return ("Ev" if k[0] == "E" else "Dep") + " gol " + ("Üst" if k[1] == "O" else "Alt")


def outcome(k, m, t):
    ht = [sum(1 for mn, s in m["goals"] if mn <= 45 and s == side) for side in "ha"]
    if k.startswith("SH"):
        a, b = m["hs"] - ht[0], m["as_"] - ht[1]
        if k in ("SH1", "SHX", "SH2"): return {"SH1": a > b, "SHX": a == b, "SH2": a < b}[k]
        return (a + b > float(k[3:])) == (k[2] == "O")
    if k == "IY1": return ht[0] > ht[1]
    if k == "IYX": return ht[0] == ht[1]
    if k == "IY2": return ht[0] < ht[1]
    if k.startswith("IY"): return (sum(ht) > float(k[3:])) == (k[2] == "O")
    if k.startswith("NEXT"):
        nxt = [s for mn, s in m["goals"] if mn > t]
        return bool(nxt) and nxt[0] == ("h" if k == "NEXT1" else "a")
    g = m["hs"] if k[0] == "E" else m["as_"]
    return (g > float(k[2:])) == (k[1] == "O")


SPLIT = sys.argv[3] if len(sys.argv) > 3 else "2025-08-01"   # eğri bu tarihten önceki maçlardan öğrenildi
TEST = [(m, x) for m, x in rows if m["date"] >= SPLIT]
CURVE = L.GOAL_CURVE


def base_outcome(k, m, s0):
    a, b = m["hs"], m["as_"]; t = a + b
    if k in ("1", "X", "2", "1X", "X2", "12"):
        r = "1" if a > b else ("X" if a == b else "2"); return r in k
    if k == "BTTS": return a > 0 and b > 0
    if k == "NBTTS": return not (a > 0 and b > 0)
    if k == "GOAL": return t > s0
    if k == "NOGOAL": return t == s0
    return (t > float(k[1:])) == (k[0] == "O")


def run(curve):
    L.GOAL_CURVE = curve
    fam = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0.0]))
    for m, x in TEST:
        p3 = E.fair(x["o"], ("1", "X", "2")); po = E.fair(x["o"], ("O", "U"))["O"]
        lh, la = lams(p3["1"], p3["2"], po)
        for t, per in MINS:
            hs = sum(1 for mn, s in m["goals"] if mn <= t and s == "h"); as_ = sum(1 for mn, s in m["goals"] if mn <= t and s == "a")
            rh = sum(1 for mn, s in m["reds"] if mn <= t and s == "h"); ra = sum(1 for mn, s in m["reds"] if mn <= t and s == "a")
            htv = [sum(1 for mn, s in m["goals"] if mn <= 45 and s == side) for side in "ha"] if (per == 2 or t == 45) else None
            for k, lab, pr in L.extra_live(lh, la, hs, as_, t, per, rh, ra, htv, t == 45):
                if not (0.70 <= pr <= 0.88): continue
                b = "70-76" if pr < .76 else ("76-82" if pr < .82 else "82-88")
                w = outcome(k, m, t)
                for key in (b, "TOPLAM"):
                    c = fam[famof(k)][key]; c[0] += 1; c[1] += w; c[2] += pr
            p, tl, _, _, _ = L.inplay(lh, la, hs, as_, t, per, rh, ra)
            for pk in L.picks_for(p, tl, t, None, hs + as_):
                w = base_outcome(pk["k"], m, hs + as_); pr = pk["prob"]
                b = "70-76" if pr < .76 else ("76-82" if pr < .82 else "82-88")
                for f in ("MEVCUT: tümü", "MEVCUT: " + ("alt/üst" if pk["k"][0] in "OU" else pk["label"])):
                    for key in (b, "TOPLAM"):
                        c = fam[f][key]; c[0] += 1; c[1] += w; c[2] += pr
    return fam


for name, curve in (("ESKİ (düz dağılım)", None), ("YENİ (gerçek gol eğrisi)", CURVE)):
    fam = run(curve)
    print(f"\n=== {name} · test {SPLIT} sonrası, {len(TEST)} maç ===")
    for f, d in sorted(fam.items()):
        t_ = d["TOPLAM"]
        if t_[0] < 80: continue
        cells = " | ".join(f"{b}: %{100*c[1]/c[0]:.1f} (%{100*c[2]/c[0]:.1f})" for b, c in sorted(d.items()) if b != "TOPLAM" and c[0] >= 50)
        print(f"  {f:34s} {t_[1]:6d}/{t_[0]:6d} %{100*t_[1]/t_[0]:.1f} (beklenen %{100*t_[2]/t_[0]:.1f})   {cells}")
