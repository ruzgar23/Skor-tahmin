"""NBA ve NHL: büro payı yöntemi karşılaştırması (oransal / power), botun seçim kurallarıyla.
Kullanım: python -I margin_us.py <us.pkl>   (us.pkl: us.py çıktısı)"""
import sys, os, pickle, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import engine as E, others as O

G = [m for m in pickle.load(open(sys.argv[1], "rb")) if m.get("mlh") and m.get("mla")]


def season(d):
    return f"{d.year - 1}-{str(d.year)[2:]}" if d.month < 8 else f"{d.year}-{str(d.year + 1)[2:]}"


def ph_of(m, meth):
    o = {"h": m["mlh"], "a": m["mla"]}
    if meth == "oransal":
        return (1 / o["h"]) / (1 / o["h"] + 1 / o["a"])
    return E.fair(o, ("h", "a"))["h"]


def show(title, T):
    print(title)
    tot = [0, 0]
    for tier, nm in ((3, "Güçlü"), (2, "Orta")):
        t = T.get(tier, [0, 0, 0.0, 0.0, 0])
        if not t[0]: continue
        tot[0] += t[0]; tot[1] += t[1]
        r = f", getiri %{100 * t[3] / t[4]:+.1f}" if t[4] else ""
        print(f"  {nm:6s} {t[1]:5d} / {t[0]:5d}  %{100 * t[1] / t[0]:.1f}  (beklenen %{100 * t[2] / t[0]:.1f}{r})")
    if tot[0]:
        print(f"  Toplam {tot[1]:5d} / {tot[0]:5d}  %{100 * tot[1] / tot[0]:.1f}")


# ---- NBA (uzatmalar dahil maç sonucu; MS favorisi ≥%75 Güçlü, %65-75 Orta) ----
nba = [m for m in G if m["sp"] == "nba"]
print(f"NBA: oranlı {len(nba)} maç, sezonlar {dict(collections.Counter(season(m['date']) for m in nba))}")
for meth in ("oransal", "power"):
    T = {}
    for m in nba:
        ph = ph_of(m, meth); fav_h = ph >= .5; pr = ph if fav_h else 1 - ph
        tier = 3 if pr >= .75 else (2 if pr >= .65 else 0)
        if not tier: continue
        w = (m["hs"] > m["as_"]) == fav_h; o = m["mlh"] if fav_h else m["mla"]
        t = T.setdefault(tier, [0, 0, 0.0, 0.0, 0]); t[0] += 1; t[1] += w; t[2] += pr; t[3] += (o - 1) if w else -1; t[4] += 1
    show(f"\nNBA · {meth}", T)

# ---- NHL (iddaa: normal süre; bot nhl_probs + nhl_grade ile) ----
nhl = [m for m in G if m["sp"] == "nhl"]
print(f"\nNHL: oranlı {len(nhl)} maç, sezonlar {dict(collections.Counter(season(m['date']) for m in nhl))}")
fam = collections.defaultdict(lambda: [0, 0])
for meth in ("oransal", "power"):
    T = {}
    for m in nhl:
        p = O.nhl_probs(ph_of(m, meth), m.get("total"))
        g = O.nhl_grade(p)
        if not g: continue
        a, b = m["hs"], m["as_"]
        w = bool(O.nhl_settle(g["label"], [a, b], m["ot"]))
        t = T.setdefault(g["tier"], [0, 0, 0.0, 0.0, 0]); t[0] += 1; t[1] += w; t[2] += g["prob"]
        f = fam[(meth, g["tier"], g["label"].split()[0])]; f[0] += 1; f[1] += w
    show(f"\nNHL · {meth}", T)
    for (mm, tier, lb), f in sorted(fam.items()):
        if mm == meth:
            print(f"     {['', '', 'Orta', 'Güçlü'][tier]:6s} {lb:4s} {f[1]:5d} / {f[0]:5d}  %{100 * f[1] / f[0]:.1f}")
