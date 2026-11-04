"""Tenis set bahisleri (üç setlik maçlar): favori 2-0, toplam set 2,5 Alt/Üst, set alır.
Maç olasılığı botun Elo modelinden (others.Elo, kalibre); set olasılığı s, p = s²(3−2s) çözülerek.
Setler bağımsız değil (üçüncü sete gitme bağımsız varsayımın verdiğinden seyrek): P(3 set) = C · 2s(1−s);
C 2024 maçlarından öğrenilir, 2025+ maçlarında denenir. Favori 2-0 = p − P(3 set)·s.
Elo 2022'den kronolojik güncellenir; 2024+ maçlar değerlendirilir. Beş setlik (Grand Slam erkek ana tablo) maçlar hariç.
Kullanım: python -I tennis_sets_test.py <tennis.pkl>"""
import sys, os, pickle, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import others as O

M = pickle.load(open(sys.argv[1], "rb")); M.sort(key=lambda m: (m["date"], m["id"]))
elo = O.Elo()


def set_p(p):
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if mid * mid * (3 - 2 * mid) < p: lo = mid
        else: hi = mid
    return (lo + hi) / 2


C = float(os.environ.get("SET_C", "1.0"))
st = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0.0]))
fitrows = []
for m in M:
    w, l = m["w"], m["l"]
    if not w or not l: continue
    note = m["notes"].lower()
    if "w/o" in note or "walkover" in note: continue
    ret = "ret" in note or "def." in note
    s = O.surface(m["event"])
    bo5 = m["tour"] == "atp" and m.get("major") and "Qualifying" not in (m.get("rnd") or "")
    sets = [(a, b) for a, b in m["sets"] if a is not None and b is not None]
    if (m["date"].year >= 2024 and not ret and not bo5 and elo.N.get(w, 0) >= 10 and elo.N.get(l, 0) >= 10
            and len(sets) in (2, 3)):
        pw = elo.prob(w, l, s)
        fav_is_w = pw >= 0.5; p = pw if fav_is_w else 1 - pw; sp = set_p(p)
        ws = sum(1 for a, b in sets if a > b); ls_ = len(sets) - ws  # kazananın / kaybedenin set sayısı
        fs, us = (ws, ls_) if fav_is_w else (ls_, ws)
        q = min(C * 2 * sp * (1 - sp), 0.95); f20 = max(p - q * sp, 0.0)
        if m["date"].year == 2024: fitrows.append((2 * sp * (1 - sp), len(sets) == 3))
        mk = {"Favori 2-0": (f20, fs == 2 and us == 0), "Toplam set 2,5 Üst": (q, len(sets) == 3),
              "Toplam set 2,5 Alt": (1 - q, len(sets) == 2), "Sürpriz set alır": (1 - f20, us >= 1),
              "Favori maçı kazanır": (p, fav_is_w)}
        for k, (v, ok) in mk.items():
            b = min(int(v * 10) / 10, 0.9)
            for kk in (b, "TOPLAM"):
                z = st[k][kk]; z[0] += 1; z[1] += ok; z[2] += v
            yb = "2024" if m["date"].year == 2024 else "2025+"
            if v >= 0.6:
                z = st[k]["≥%60 " + yb]; z[0] += 1; z[1] += ok; z[2] += v
    if not ret:
        elo.update(w, l, s)
for k, d in st.items():
    print(k)
    for b, z in sorted(d.items(), key=lambda x: str(x[0])):
        if z[0] >= 100:
            name = f"%{int(b*100)}+" if isinstance(b, float) else b
            print(f"   {name:12s} {z[1]:6d}/{z[0]:6d} %{100*z[1]/z[0]:.1f} (beklenen %{100*z[2]/z[0]:.1f})")

if os.environ.get("FIT"):
    import math
    best = min((sum(-math.log(max(min(c * x, .999), 1e-6)) if y else -math.log(max(1 - c * x, 1e-6)) for x, y in fitrows), c)
               for c in [i / 200 for i in range(100, 220)])
    print(f"2024'ten öğrenilen C = {best[1]:.3f}")
