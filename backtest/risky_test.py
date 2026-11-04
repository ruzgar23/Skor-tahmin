"""Riskli seçimler (bot/core.py risky_pick): adil oran 1,75–2,00, maç başına en olası tek seçim.
Lig maçları: football-data ortalama açılış oranları (8 sezon). Kupalar: cups.pkl (ESPN, DraftKings, 2026).
MS ve 2,5 seçimlerinde gerçek oranla getiri de hesaplanır. Kullanım: python -I backtest/risky_test.py <fd_klasörü> [cups.pkl]"""
import sys, os, io, csv, glob, math, pickle, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "engine"), os.path.join(HERE, "..", "bot")]
import engine as E, scan, core
src = open(os.path.join(HERE, "new_markets_test.py"), encoding="utf-8").read()
exec(src[src.index("RHO = -0.06"):src.index("rows = []")])  # ızgara ve lams()


def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def hrow(lh, la, htr):
    pp, M, top = scan.full_probs(lh, la, htr)
    return dict(p={k: float(v) for k, v in pp.items()}, M=[[round(float(M[i, j]), 4) for j in range(6)] for i in range(6)],
                src="piyasa", known=(True, True))


def acc(d, g, ok, odd=None):
    for k in ("TOPLAM", "  " + g["label"]):
        z = d[k]; z[0] += 1; z[1] += ok; z[2] += g["prob"]
        if odd: z[3] += (odd - 1) if ok else -1; z[4] += 1


def show(title, d):
    print(title)
    for k, z in sorted(d.items(), key=lambda x: (x[0].startswith(" "), -x[1][0])):
        if z[0] < 20 and k.startswith(" "): continue
        r = f", gerçek ort. oranla getiri %{100*z[3]/z[4]:+.1f}" if z[4] else ""
        print(f"  {k:22s} {z[1]:6d}/{z[0]:6d} %{100*z[1]/z[0]:.1f} (beklenen %{100*z[2]/z[0]:.1f}){r}")


lig = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0]); seas = collections.defaultdict(lambda: [0, 0])
for path in sorted(glob.glob(os.path.join(sys.argv[1], "*", "*.csv"))):
    s = os.path.basename(os.path.dirname(path))
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            try: a, b, ha, hb = (int(float(r[c])) for c in ("FTHG", "FTAG", "HTHG", "HTAG"))
            except (KeyError, ValueError, TypeError): continue
            o = {k: fnum(r.get(c)) for k, c in (("1", "AvgH"), ("X", "AvgD"), ("2", "AvgA"), ("O", "Avg>2.5"), ("U", "Avg<2.5"))}
            if not all(v and v > 1 for v in o.values()): continue
            p3 = E.fair(o, ("1", "X", "2")); po = E.fair(o, ("O", "U"))["O"]
            lh, la = lams(p3["1"], p3["2"], po)
            rp = core.risky_pick(hrow(lh, la, 0.45))
            if not rp: continue
            ok = bool(core.settle_risky(rp["key"], [a, b], [ha, hb]))
            acc(lig, rp, ok, {"1": o["1"], "2": o["2"], "O25": o["O"], "U25": o["U"]}.get(rp["key"]))
            seas[s][0] += 1; seas[s][1] += ok
show(f"LİG MAÇLARI (8 sezon)", lig)
print("  sezonlar:", ", ".join(f"{s} %{100*v[1]/v[0]:.1f}" for s, v in sorted(seas.items())))
if len(sys.argv) > 2:
    cup = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0])
    for m in pickle.load(open(sys.argv[2], "rb")):
        o = m["o"]; mk = E.fair({k: o[k] for k in "1X2"}, "1X2")
        if o.get("O") and o.get("U") and o.get("line") is not None:
            po = E.fair({"O": o["O"], "U": o["U"]}, ("O", "U"))["O"]
            if abs(o["line"] - 2.5) < 1e-6: mk["O25"] = po
            else: mk["OL"] = (o["line"], po)
        lh, la = scan.fit_to_market(1.4, 1.1, mk, 2.6)
        rp = core.risky_pick(hrow(lh, la, 0.44))
        if not rp: continue
        ht = [sum(1 for mn, s_ in m["goals"] if mn <= 45 and s_ == x) for x in "ha"]
        acc(cup, rp, bool(core.settle_risky(rp["key"], [m["hs"], m["as_"]], ht)), {"1": o["1"], "2": o["2"]}.get(rp["key"]))
    show("KUPA MAÇLARI (2026, DraftKings)", cup)
