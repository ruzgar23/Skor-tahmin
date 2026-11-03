"""Yeni pazarlar: ilk yarı, takım gol alt/üst, Avrupa handikabı (isabet ve kalibrasyon) ve Asya handikabı (kâr).
Olasılıklar botla aynı yoldan: sabah ortalama oranı (power) → gol beklentisi (Poisson + Dixon-Coles) → skor matrisi;
ilk yarı için beklenti * lig ilk yarı payı (yalnızca o maçtan ÖNCEKİ sezonlardan).
Kullanım: python -I backtest/new_markets_test.py <fd_klasörü>"""
import sys, os, io, csv, glob, math, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import engine as E

D = sys.argv[1]
RHO = -0.06; K = 11
g = np.round(np.arange(0.15, 4.5, 0.025), 4); n = len(g)
pois = np.array([[math.exp(-l) * l ** k / math.factorial(k) for k in range(K)] for l in g])
P1 = np.zeros((n, n)); P2 = P1.copy(); PO = P1.copy()
for i in range(K):
    for j in range(K):
        w = pois[:, i][:, None] * pois[:, j][None, :]
        lh, la = g[:, None], g[None, :]
        if (i, j) == (0, 0): w = w * (1 - lh * la * RHO)
        elif (i, j) == (0, 1): w = w * (1 + lh * RHO)
        elif (i, j) == (1, 0): w = w * (1 + la * RHO)
        elif (i, j) == (1, 1): w = w * (1 - RHO)
        if i > j: P1 += w
        if i < j: P2 += w
        if i + j >= 3: PO += w
P1f, P2f, POf = P1.ravel(), P2.ravel(), PO.ravel()


def lams(p1, p2, po):
    k = int(np.argmin((P1f - p1) ** 2 + (P2f - p2) ** 2 + (POf - po) ** 2)); i, j = divmod(k, n)
    return float(g[i]), float(g[j])


def fnum(x):
    try:
        v = float(x); return v
    except (TypeError, ValueError):
        return None


rows = []
for path in sorted(glob.glob(os.path.join(D, "*", "*.csv"))):
    season = os.path.basename(os.path.dirname(path))
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            try:
                a, b, ha, hb = (int(float(r[c])) for c in ("FTHG", "FTAG", "HTHG", "HTAG"))
            except (KeyError, ValueError, TypeError):
                continue
            o = {k: fnum(r.get(c)) for k, c in (("1", "AvgH"), ("X", "AvgD"), ("2", "AvgA"), ("O", "Avg>2.5"), ("U", "Avg<2.5"))}
            if not all(v and v > 1 for v in o.values()):
                continue
            ah = dict(line=fnum(r.get("AHh")), h=fnum(r.get("AvgAHH")), a=fnum(r.get("AvgAHA")),
                      hM=fnum(r.get("MaxAHH")), aM=fnum(r.get("MaxAHA")))
            rows.append(dict(season=season, lg=r["Div"], o=o, a=a, b=b, ha=ha, hb=hb, ah=ah))
rows.sort(key=lambda m: m["season"])
SEAS = sorted({m["season"] for m in rows})

# lig ilk yarı gol payı, yalnızca önceki sezonlardan
htr = {}
for si, s in enumerate(SEAS):
    prev = [m for m in rows if m["season"] < s]
    acc = collections.defaultdict(lambda: [0, 0])
    for m in prev:
        c = acc[m["lg"]]; c[0] += m["ha"] + m["hb"]; c[1] += m["a"] + m["b"]
    for lg, c in acc.items():
        htr[(s, lg)] = c[0] / c[1] if c[1] else 0.45
test = [m for m in rows if m["season"] > SEAS[0]]
print(f"{len(test)} maç ({SEAS[1]}–{SEAS[-1]}; ilk sezon yalnızca ilk yarı payı için)\n")

MK = collections.OrderedDict()   # pazar -> (olasılık fonksiyonu, sonuç fonksiyonu)
def add(name, pf, rf): MK[name] = (pf, rf)
add("İY 1", lambda P: P["H"][0], lambda m: m["ha"] > m["hb"])
add("İY X", lambda P: P["H"][1], lambda m: m["ha"] == m["hb"])
add("İY 2", lambda P: P["H"][2], lambda m: m["ha"] < m["hb"])
add("İY 0,5 Üst", lambda P: P["H"][3], lambda m: m["ha"] + m["hb"] >= 1)
add("İY 0,5 Alt", lambda P: 1 - P["H"][3], lambda m: m["ha"] + m["hb"] == 0)
add("İY 1,5 Üst", lambda P: P["H"][4], lambda m: m["ha"] + m["hb"] >= 2)
add("İY 1,5 Alt", lambda P: 1 - P["H"][4], lambda m: m["ha"] + m["hb"] <= 1)
for side, gi, nm_ in (("Ev", 0, "ev"), ("Dep", 1, "dep")):
    for L in (0.5, 1.5, 2.5):
        add(f"{side} {str(L).replace('.', ',')} Üst", (lambda P, gi=gi, L=L: P["T"][gi][int(L)]),
            (lambda m, gi=gi, L=L: (m["a"] if gi == 0 else m["b"]) > L))
        add(f"{side} {str(L).replace('.', ',')} Alt", (lambda P, gi=gi, L=L: 1 - P["T"][gi][int(L)]),
            (lambda m, gi=gi, L=L: (m["a"] if gi == 0 else m["b"]) < L))
# Avrupa handikabı (favoriye göre): favori -1 kazanır (2+ farkla), favori -1 X2 (en fazla 1 farkla kazanır ya da kazanamaz)
add("Hnd fav -1 kazanır", lambda P: P["F"][0], lambda m: m["fm"] >= 2)
add("Hnd fav -1 X2", lambda P: 1 - P["F"][0], lambda m: m["fm"] <= 1)
add("Hnd fav -2 X2", lambda P: 1 - P["F"][1], lambda m: m["fm"] <= 2)

stats = {k: collections.defaultdict(lambda: [0, 0, 0.0]) for k in MK}
ahres = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])  # eşik -> n, getiri ort, getiri max, kazandı
for m in test:
    p3 = E.fair(m["o"], ("1", "X", "2")); po = E.fair(m["o"], ("O", "U"))["O"]
    lh, la = lams(p3["1"], p3["2"], po)
    M = E.score_matrix(lh, la, RHO); I, J = np.meshgrid(range(M.shape[0]), range(M.shape[0]), indexing="ij")
    r = htr.get((m["season"], m["lg"]), 0.45)
    H = E.score_matrix(lh * r, la * r, 0)
    h = E.markets(H)
    fav_home = p3["1"] >= p3["2"]; diff = (I - J) if fav_home else (J - I)
    m["fm"] = (m["a"] - m["b"]) if fav_home else (m["b"] - m["a"])
    P = dict(H=(h["1"], h["X"], h["2"], 1 - H[0, 0], h["O15"]),
             T=([float(M[I > L].sum()) for L in range(3)], [float(M[J > L].sum()) for L in range(3)]),
             F=(float(M[diff >= 2].sum()), float(M[diff >= 3].sum())))
    for k, (pf, rf) in MK.items():
        v = pf(P)
        if v >= .60:
            b = .60 if v < .70 else (.70 if v < .80 else .80)
            c = stats[k][b]; c[0] += 1; c[1] += rf(m); c[2] += v
    # Asya handikabı: model (1X2+2,5'ten) ile AH piyasası farklı düşündüğünde
    ah = m["ah"]
    ok = (ah["line"] is not None and ah["h"] and ah["a"] and ah["h"] > 1 and ah["a"] > 1
          and 1.01 <= 1 / ah["h"] + 1 / ah["a"] <= 1.10   # bozuk satırlar (ör. 1,91 / 4,11) elenir
          and (ah["hM"] or 0) <= ah["h"] * 1.15 and (ah["aM"] or 0) <= ah["a"] * 1.15)
    if ok:
        lines = [ah["line"]] if (ah["line"] * 4) % 2 == 0 else [ah["line"] - .25, ah["line"] + .25]
        def cover(L, home=True):  # (kazanma, iade) olasılıkları
            mg = (I - J) + L if home else (J - I) - L
            return float(M[mg > 0].sum()), float(M[mg == 0].sum())
        def settle(L, home=True):
            mg = (m["a"] - m["b"]) + L if home else (m["b"] - m["a"]) - L
            return 1.0 if mg > 0 else (0.5 if mg == 0 else 0.0)  # 0.5 = iade
        fair_h = E.fair({"h": ah["h"], "a": ah["a"]}, ("h", "a"))["h"]
        ch = [cover(L) for L in lines]; ph = np.mean([w / (1 - p0) if p0 < 1 else 0.5 for w, p0 in ch])
        for side, pm, pmk, o, oM in (("h", ph, fair_h, ah["h"], ah["hM"]), ("a", 1 - ph, 1 - fair_h, ah["a"], ah["aM"])):
            for th in (0.02, 0.04, 0.06):
                if pm - pmk >= th:
                    ret = retM = 0.0
                    for L in lines:
                        s_ = settle(L, side == "h")
                        f = 1 / len(lines)
                        ret += f * ((o - 1) if s_ == 1 else (0 if s_ == 0.5 else -1))
                        retM += f * (((oM or o) - 1) if s_ == 1 else (0 if s_ == 0.5 else -1))
                    c = ahres[th]; c[0] += 1; c[1] += ret; c[2] += retM; c[3] += ret > 0

weeks = (len(SEAS) - 1) * 40
print("İSABET (seçim olasılığı kovasına göre): tuttu / sayı, gerçek% (beklenen%), haftada seçim")
for k, d in stats.items():
    cells = []
    for b in (.60, .70, .80):
        c = d.get(b)
        if c and c[0] >= 50:
            cells.append(f"%{int(b*100)}+: {c[1]}/{c[0]} %{100*c[1]/c[0]:.1f} (%{100*c[2]/c[0]:.1f}) {c[0]/weeks:.1f}/hf")
    if cells:
        print(f"  {k:20s} " + " | ".join(cells))
print("\nASYA HANDİKABI — model piyasadan farklı düşündüğünde oyna (açılış ort. oran / en iyi oran):")
for th, c in sorted(ahres.items()):
    print(f"  fark ≥ {int(th*100)} puan: {c[0]} bahis, kazandı %{100*c[3]/max(c[0],1):.1f}, getiri ort.oran {100*c[1]/max(c[0],1):+.1f}%, en iyi oran {100*c[2]/max(c[0],1):+.1f}%")

# ---- bota eklenen kural: maç başına en fazla bir ek seçim, %70–80, testte kalibre çıkan ve iddaa'da olan pazarlardan ----
EXTRA = ("İY 0,5 Üst", "İY 1,5 Alt", "Ev 0,5 Üst", "Ev 1,5 Üst", "Ev 1,5 Alt", "Ev 2,5 Alt", "Dep 0,5 Üst",
         "Dep 1,5 Üst", "Dep 1,5 Alt", "Dep 2,5 Alt")  # handikaplı X2 iddaa'da yok (yalnızca 1/X/2)
tot = [0, 0, 0.0]; fam = collections.defaultdict(lambda: [0, 0, 0.0]); bys = collections.defaultdict(lambda: [0, 0])
for m in test:
    p3 = E.fair(m["o"], ("1", "X", "2")); po = E.fair(m["o"], ("O", "U"))["O"]
    lh, la = lams(p3["1"], p3["2"], po)
    M = E.score_matrix(lh, la, RHO); I, J = np.meshgrid(range(M.shape[0]), range(M.shape[0]), indexing="ij")
    r = htr.get((m["season"], m["lg"]), 0.45); H = E.score_matrix(lh * r, la * r, 0); h = E.markets(H)
    fav_home = p3["1"] >= p3["2"]; diff = (I - J) if fav_home else (J - I)
    P = dict(H=(h["1"], h["X"], h["2"], 1 - H[0, 0], h["O15"]),
             T=([float(M[I > L].sum()) for L in range(3)], [float(M[J > L].sum()) for L in range(3)]),
             F=(float(M[diff >= 2].sum()), float(M[diff >= 3].sum())))
    best = None
    for k in EXTRA:
        v = MK[k][0](P)
        if .70 <= v < .80 and (best is None or v > best[1]): best = (k, v)
    if best:
        w = MK[best[0]][1](m)
        tot[0] += 1; tot[1] += w; tot[2] += best[1]; f = fam[best[0]]; f[0] += 1; f[1] += w; f[2] += best[1]
        c = bys[m["season"]]; c[0] += 1; c[1] += w
print(f"\nEK SEÇİM KURALI (maç başına en fazla 1, %70–80): {tot[1]}/{tot[0]} %{100*tot[1]/tot[0]:.1f} (beklenen %{100*tot[2]/tot[0]:.1f}), haftada {tot[0]/weeks:.0f}")
for k, f in sorted(fam.items(), key=lambda x: -x[1][0]):
    print(f"   {k:16s} {f[1]:5d}/{f[0]:5d} %{100*f[1]/f[0]:.1f} (%{100*f[2]/f[0]:.1f})")
print("   sezonlara göre:", ", ".join(f"{s} %{100*c[1]/c[0]:.1f}" for s, c in sorted(bys.items())))
