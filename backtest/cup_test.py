"""Kupa maçlarında (ŞL/AL/KL, 2026) botun maç öncesi seçimleri: ana seçim (core.grade) ve ek seçim (core.extra_pick).
Olasılık botla aynı yoldan: DraftKings oranı (power) → scan.fit_to_market → scan.full_probs (kupa İY payı 0,44).
Kullanım: python -I backtest/cup_test.py <cups.pkl>"""
import sys, os, pickle, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "engine"), os.path.join(HERE, "..", "bot")]
import engine as E, scan, core
R = pickle.load(open(sys.argv[1], "rb"))
main = collections.defaultdict(lambda: [0, 0, 0.0]); ext = collections.defaultdict(lambda: [0, 0, 0.0])
for m in R:
    o = m["o"]; mk = E.fair({k: o[k] for k in "1X2"}, "1X2")
    if o.get("O") and o.get("U") and o.get("line") is not None:
        po = E.fair({"O": o["O"], "U": o["U"]}, ("O", "U"))["O"]
        if abs(o["line"] - 2.5) < 1e-6: mk["O25"] = po
        else: mk["OL"] = (o["line"], po)
    lh, la = scan.fit_to_market(1.4, 1.1, mk, 2.6)
    p, M, top = scan.full_probs(lh, la, 0.44)
    h = dict(p={k: float(v) for k, v in p.items()}, src="piyasa", known=(True, True))
    res = [m["hs"], m["as_"]]; ht = [sum(1 for mn, s in m["goals"] if mn <= 45 and s == x) for x in "ha"]
    g = core.grade(h)
    if g and g["tier"] >= 2:
        w = bool(core.settle(core.LABEL2KEY[g["label"]], res))
        for k in ({3: "Güçlü", 2: "Orta"}[g["tier"]], f"  {g['label']}"):
            z = main[k]; z[0] += 1; z[1] += w; z[2] += g["prob"]
    x = core.extra_pick(h)
    if x:
        w = bool(core.settle_extra(x["label"], res, ht))
        for k in ("TOPLAM", "  " + x["label"]):
            z = ext[k]; z[0] += 1; z[1] += w; z[2] += x["prob"]
print(f"{len(R)} kupa maçı ({dict(collections.Counter(m['lg'] for m in R))})")
for name, d in (("Ana seçimler", main), ("Ek seçimler", ext)):
    print(name)
    for k, z in sorted(d.items(), key=lambda x: (x[0].startswith(" "), -x[1][0])):
        print(f"  {k:22s} {z[1]:4d}/{z[0]:4d} %{100*z[1]/z[0]:.1f} (beklenen %{100*z[2]/z[0]:.1f})")
