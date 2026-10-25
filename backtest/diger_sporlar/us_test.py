import pickle, collections, numpy as np, math
from scipy.stats import poisson
from scipy.optimize import minimize
G = [m for m in pickle.load(open("us.pkl", "rb")) if m.get("mlh") and m.get("mla")]
def season(d): return f"{d.year-1}-{str(d.year)[2:]}" if d.month < 8 else f"{d.year}-{str(d.year+1)[2:]}"
def row(name, xs):
    if not xs: return
    n = len(xs); w = sum(x[0] for x in xs); ep = sum(x[1] for x in xs); r = [x[0] * (x[2] - 1) - (1 - x[0]) for x in xs if x[2]]
    print(f"  {name:38s} n={n:5d} tuttu %{100*w/n:5.1f} (beklenen %{100*ep/n:5.1f}) ort.oran {np.mean([x[2] for x in xs if x[2]]):.2f} getiri {100*np.mean(r):+5.1f}%")
for sp in ("nba", "nhl"):
    S = [m for m in G if m["sp"] == sp]
    print(f"\n=== {sp.upper()} === oranlı maç {len(S)}, sezonlar {collections.Counter(season(m['date']) for m in S)}")
    bins = collections.defaultdict(list); tiers = collections.defaultdict(list)
    for m in S:
        ph = (1/m["mlh"]) / (1/m["mlh"] + 1/m["mla"])
        fav_h = ph >= .5; p = ph if fav_h else 1 - ph; won = (m["hs"] > m["as_"]) == fav_h; o = m["mlh"] if fav_h else m["mla"]
        b = min(int(p * 20) / 20, .9); bins[b].append((won, p, o))
        t = "Güçlü (≥%75)" if p >= .75 else ("Orta (%65-75)" if p >= .65 else None)
        if t: tiers[t].append((won, p, o)); tiers[t + " " + season(m["date"])].append((won, p, o))
    print(" Maç sonucu (uzatmalar dahil) favori:")
    for b in sorted(bins): row(f"favori %{int(b*100)}-{int(b*100)+5}", bins[b])
    for t in sorted(tiers): row(t, tiers[t])
    if sp == "nba":
        sp_ = []; to = []
        for m in S:
            if m.get("spread") is not None and m.get("hso"):
                mg = m["hs"] - m["as_"] + m["spread"]
                if mg != 0: sp_.append(mg > 0)
            if m.get("total") and m.get("overOdds"):
                t = m["hs"] + m["as_"]
                if t != m["total"]: to.append(t > m["total"])
        print(f" Handikap: ev sahibi kapattı %{100*np.mean(sp_):.1f} (n={len(sp_)}); toplam üst %{100*np.mean(to):.1f} (n={len(to)}) — %52,4 altı -110 oranla kâr etmez")
pickle.dump(G, open("us_odds.pkl", "wb"))
