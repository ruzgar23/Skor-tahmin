import pickle, collections, numpy as np, re, sys
M = pickle.load(open("tennis.pkl", "rb")); M.sort(key=lambda m: (m["date"], m["id"]))
CLAY = re.compile(r"Roland|Monte-Carlo|Madrid|Italia|Rome|Barcelona|Hamburg|Rio Open|Argentina|Chile|Estoril|Geneva|Lyon|Bastad|Gstaad|Kitzb|Umag|Houston|Marrakech|Munich|BMW|Bucharest|Palermo|Prague|Rabat|Strasbourg|Charleston|Bogota|Parma|Iasi|Budapest|Lausanne|Cluj|Rouen|Bad Homburg|Croatia|Swedish|Nordea|Generali|Tiriac|Grand Prix Hassan|Copa Colsanitas|Credit One|Emilia", re.I)
GRASS = re.compile(r"Wimbledon|Halle|Terra Wortmann|Queen|cinch|HSBC|s-Hertogenbosch|Libema|Mallorca|Eastbourne|Rothesay|Nottingham|Birmingham|Berlin|ecotrans|Bad Homburg Open", re.I)
def surf(ev): return "grass" if GRASS.search(ev) else ("clay" if CLAY.search(ev) else "hard")
def kf(n): return 250 / (n + 5) ** 0.4
R = collections.defaultdict(lambda: 1500.0); N = collections.Counter(); RS = collections.defaultdict(lambda: 1500.0); NS = collections.Counter()
def p_of(a, b, s, w_s):
    pa = 1 / (1 + 10 ** ((R[b] - R[a]) / 400)); ps = 1 / (1 + 10 ** ((RS[(b, s)] - RS[(a, s)]) / 400))
    return (1 - w_s) * pa + w_s * ps
W_S = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
rows = []
for m in M:
    w, l = m["w"], m["l"]
    if not w or not l: continue
    note = m["notes"].lower()
    if "w/o" in note or "walkover" in note: continue
    s = surf(m["event"])
    p = p_of(w, l, s, W_S)
    ret = "ret" in note or "def." in note
    if m["date"].year >= 2023 and N[w] >= 10 and N[l] >= 10 and not ret:
        fav_won = p >= .5; pf = max(p, 1 - p)
        rows.append((m, pf, fav_won))
    if ret: continue
    for (a, b, x) in ((w, l, 1),):
        e = 1 / (1 + 10 ** ((R[b] - R[a]) / 400))
        R[a] += kf(N[a]) * (1 - e); R[b] -= kf(N[b]) * (1 - e); N[a] += 1; N[b] += 1
        es = 1 / (1 + 10 ** ((RS[(b, s)] - RS[(a, s)]) / 400))
        RS[(a, s)] += kf(NS[(a, s)]) * (1 - es); RS[(b, s)] -= kf(NS[(b, s)]) * (1 - es); NS[(a, s)] += 1; NS[(b, s)] += 1
pf = np.array([r[1] for r in rows]); y = np.array([r[2] for r in rows], float)
ll = -np.mean(y * np.log(pf) + (1 - y) * np.log(1 - pf))
print(f"yüzey ağırlığı {W_S}: değerlendirilen maç {len(rows)}, favori kazandı %{100*y.mean():.1f}, beklenen %{100*pf.mean():.1f}, log-loss {ll:.4f}, Brier {np.mean((pf-y)**2):.4f}")
if len(sys.argv) > 2:
    for lo in (.5, .55, .6, .65, .7, .75, .8, .85, .9):
        k = (pf >= lo) & (pf < lo + .05) if lo < .9 else pf >= lo
        print(f"  favori %{int(lo*100)}-{int(lo*100)+5}: n={k.sum():5d} tuttu %{100*y[k].mean():5.1f} beklenen %{100*pf[k].mean():5.1f}")
    for name, lo, hi in (("Güçlü ≥%80", .8, 1), ("Orta %70-80", .7, .8)):
        for yr in (2023, 2024, 2025, 2026, None):
            k = np.array([(lo <= r[1] < hi) and (yr is None or r[0]["date"].year == yr) for r in rows])
            print(f"  {name} {yr or 'toplam'}: n={k.sum():5d} tuttu %{100*y[k].mean():5.1f} beklenen %{100*pf[k].mean():5.1f}")
    pickle.dump(dict(R=dict(R), N=dict(N), RS=dict(RS)), open("elo.pkl", "wb"))
if len(sys.argv) > 2:
    from scipy.optimize import minimize_scalar
    z = np.log(pf / (1 - pf)); yrs = np.array([r[0]["date"].year for r in rows])
    tr = yrs == 2023
    f = lambda b: -np.mean(y[tr] * np.log(1/(1+np.exp(-b*z[tr]))) + (1-y[tr]) * np.log(1 - 1/(1+np.exp(-b*z[tr]))))
    b = minimize_scalar(f, bounds=(.3, 1.5), method="bounded").x
    pc = 1 / (1 + np.exp(-b * z)); te = ~tr
    print(f"kalibrasyon katsayısı b={b:.3f} (2023'ten öğrenildi), 2024+ log-loss {-np.mean(y[te]*np.log(pc[te])+(1-y[te])*np.log(1-pc[te])):.4f} (ham {-np.mean(y[te]*np.log(pf[te])+(1-y[te])*np.log(1-pf[te])):.4f})")
    for name, lo, hi in (("Güçlü ≥%80", .8, 1), ("Orta %70-80", .7, .8)):
        k = te & (pc >= lo) & (pc < hi)
        print(f"  kalibre {name} 2024+: n={k.sum()} (haftada ~{k.sum()/ (52*2.8):.0f}) tuttu %{100*y[k].mean():.1f} beklenen %{100*pc[k].mean():.1f}")
        for yr in (2024, 2025, 2026):
            k2 = k & (yrs == yr); print(f"     {yr}: n={k2.sum()} tuttu %{100*y[k2].mean():.1f}")
