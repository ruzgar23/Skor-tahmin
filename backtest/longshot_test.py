"""Çok riskli seçimler: adil oranı 3,20–3,70 ve 5,40–6,20 olan bahisler; maç başına her aralıkta en olası tek seçim.
Adaylar: MS 1/X/2, İY 1/X/2, İY/MS, sonuç & 2,5 Alt-Üst, sonuç & KG, 3,5 Üst, doğru skor. Pazar ailesi bazında kalibrasyon;
MS seçimlerinde gerçek ortalama oranla getiri. Kullanım: python -I backtest/longshot_test.py <fd_klasörü> [cups.pkl]"""
import sys, os, io, csv, glob, math, pickle, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "engine"), os.path.join(HERE, "..", "bot")]
import engine as E, scan, core
src = open(os.path.join(HERE, "new_markets_test.py"), encoding="utf-8").read()
exec(src[src.index("RHO = -0.06"):src.index("rows = []")])
BANDS = {"3,20–3,70": (1 / 3.7, 1 / 3.2), "5,40–6,20": (1 / 6.2, 1 / 5.4)}
FAM_ONLY = os.environ.get("FAM")  # yalnızca bu aileler (virgülle), bot kuralını denemek için


def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def cands(p, M):
    """[(aile, etiket, olasılık, sonuç_fonksiyonu(a, b, ha, hb))]"""
    R3 = {"1": lambda a, b: a > b, "X": lambda a, b: a == b, "2": lambda a, b: a < b}
    out = [("MS", f"MS {k}", p[k], (lambda a, b, ha, hb, f=f: f(a, b))) for k, f in R3.items()]
    out += [("İY", f"İY {k}", p["HT" + k], (lambda a, b, ha, hb, f=f: f(ha, hb))) for k, f in R3.items()]
    for k1, f1 in R3.items():
        for k2, f2 in R3.items():
            out.append(("İY/MS", f"İY/MS {k1}/{k2}", p["HF" + k1 + k2], (lambda a, b, ha, hb, f1=f1, f2=f2: f1(ha, hb) and f2(a, b))))
    h = dict(M=M)
    for res in ("1", "X", "2"):
        for tot, (lab, tf) in core.COMBO_TOT.items():
            if tot not in (("gol", "O", 2.5), ("gol", "U", 2.5), "BTTS", "NBTTS"): continue
            v = core.combo_prob(h, res, tot)
            out.append(("Sonuç & gol", core.combo_label(res, tot), v, (lambda a, b, ha, hb, rf=core.COMBO_RES[res], tf=tf: rf(a, b) and tf(a, b))))
    out.append(("3,5 Üst", "3,5 Üst", p["O35"], lambda a, b, ha, hb: a + b >= 4))
    s = sum(sum(r) for r in M)
    for i in range(6):
        for j in range(6):
            out.append(("Doğru skor", f"Skor {i}-{j}", M[i][j] / s, (lambda a, b, ha, hb, i=i, j=j: a == i and b == j)))
    if FAM_ONLY:
        keep = set(FAM_ONLY.split(","))
        out = [c for c in out if c[0] in keep]
    return out


def run(items, title):
    st = {b: collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0]) for b in BANDS}
    for p, M, a, b, ha, hb, odds in items:
        cs = cands(p, M)
        for bn, (lo, hi) in BANDS.items():
            c = [x for x in cs if lo <= x[2] <= hi]
            if not c: continue
            fam, lab, v, f = max(c, key=lambda x: x[2]); w = bool(f(a, b, ha, hb))
            od = odds.get(lab) if odds else None
            for k in ("TOPLAM", "  " + fam):
                z = st[bn][k]; z[0] += 1; z[1] += w; z[2] += v
                if od: z[3] += (od - 1) if w else -1; z[4] += 1
    print(title)
    for bn, d in st.items():
        print(f" Oran {bn}:")
        for k, z in sorted(d.items(), key=lambda x: (x[0].startswith(" "), -x[1][0])):
            r = f", gerçek ort. oranla getiri %{100*z[3]/z[4]:+.1f} (n={z[4]})" if z[4] else ""
            print(f"   {k:16s} {z[1]:6d}/{z[0]:6d} %{100*z[1]/z[0]:.1f} (beklenen %{100*z[2]/z[0]:.1f}){r}")


items = []
for path in sorted(glob.glob(os.path.join(sys.argv[1], "*", "*.csv"))):
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            try: a, b, ha, hb = (int(float(r[c])) for c in ("FTHG", "FTAG", "HTHG", "HTAG"))
            except (KeyError, ValueError, TypeError): continue
            o = {k: fnum(r.get(c)) for k, c in (("1", "AvgH"), ("X", "AvgD"), ("2", "AvgA"), ("O", "Avg>2.5"), ("U", "Avg<2.5"))}
            if not all(v and v > 1 for v in o.values()): continue
            p3 = E.fair(o, ("1", "X", "2")); po = E.fair(o, ("O", "U"))["O"]
            lh, la = lams(p3["1"], p3["2"], po)
            pp, M, _ = scan.full_probs(lh, la, 0.45)
            items.append((pp, [[float(M[i, j]) for j in range(6)] for i in range(6)], a, b, ha, hb, {"MS 1": o["1"], "MS X": o["X"], "MS 2": o["2"]}))
run(items, f"LİG MAÇLARI ({len(items)} maç, 8 sezon)")
if len(sys.argv) > 2:
    ci = []
    for m in pickle.load(open(sys.argv[2], "rb")):
        o = m["o"]; mk = E.fair({k: o[k] for k in "1X2"}, "1X2")
        if o.get("O") and o.get("U") and o.get("line") is not None:
            po = E.fair({"O": o["O"], "U": o["U"]}, ("O", "U"))["O"]
            if abs(o["line"] - 2.5) < 1e-6: mk["O25"] = po
            else: mk["OL"] = (o["line"], po)
        lh, la = scan.fit_to_market(1.4, 1.1, mk, 2.6); pp, M, _ = scan.full_probs(lh, la, 0.44)
        ht = [sum(1 for mn, s_ in m["goals"] if mn <= 45 and s_ == x) for x in "ha"]
        ci.append((pp, [[float(M[i, j]) for j in range(6)] for i in range(6)], m["hs"], m["as_"], ht[0], ht[1], {"MS 1": o["1"], "MS X": o["X"], "MS 2": o["2"]}))
    run(ci, f"KUPA MAÇLARI ({len(ci)} maç, 2026)")
