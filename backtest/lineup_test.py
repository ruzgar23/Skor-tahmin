import sys, pickle, numpy as np, collections, datetime as dt
sys.path.insert(0, "/home/claude/skor-tahmin/engine"); import espn
sys.path.insert(0, sys.path[0]); from lib import *
L = pickle.load(open(BASE + "lineups.pkl", "rb")); L = [x for x in L if len(x["xi"]) == 2 and len(x["xi"]["home"]) == 11 and len(x["xi"]["away"]) == 11]
L.sort(key=lambda x: x["date"])
# takım geçmişi (ESPN adı ile)
hist = collections.defaultdict(list)  # team -> [(set ids, gk ids, goals dict)]
feat = {}
for x in L:
    for side, op in (("home", "away"), ("away", "home")):
        t = x[side]; H = hist[t][-8:]
        xi = {p[0] for p in x["xi"][side]}
        if len(H) >= 6:
            cnt = collections.Counter(i for h in H for i in h[0]); gl = collections.Counter()
            for h in H: gl.update(h[2])
            regs = {i for i, c in cnt.items() if c >= 0.75 * len(H)}
            miss = regs - xi
            gk = collections.Counter(i for h in H for i in h[1]).most_common(1)
            gkmiss = bool(gk and gk[0][1] >= 0.75 * len(H) and gk[0][0] not in xi)
            topsc = {i for i, c in gl.items() if c >= 3}
            feat[(x["id"], side)] = dict(miss=len(miss), gk=gkmiss, scorer=len(topsc - xi), regs=len(regs))
        hist[t].append((xi, {p[0] for p in x["xi"][side] if p[2] == "G"}, {p[0]: p[3] for p in x["xi"][side] if p[3]}))
R = [m for m in load() if m["o"] and m["c"] and m["lg"] in {"E0", "E1", "SP1", "I1", "D1", "F1", "T1", "N1", "P1", "SC0"}]
idx = collections.defaultdict(list)
for m in R: idx[(m["lg"], m["date"])].append(m)
teams = collections.defaultdict(set)
for m in R: teams[m["lg"]] |= {m["home"], m["away"]}
nm = {}; hit = 0; rows = []
for x in L:
    d = dt.date.fromisoformat(x["date"][:10])
    for k in ("home", "away"):
        if (x["lg"], x[k]) not in nm: nm[(x["lg"], x[k])] = espn.match_name(x[k], teams[x["lg"]])
    h, a = nm[(x["lg"], x["home"])], nm[(x["lg"], x["away"])]
    for dd in (0, -1, 1):
        cand = [m for m in idx[(x["lg"], d + dt.timedelta(days=dd))] if m["home"] == h and m["away"] == a]
        if cand:
            fh, fa = feat.get((x["id"], "home")), feat.get((x["id"], "away"))
            if fh and fa: rows.append((cand[0], fh, fa))
            hit += 1; break
print("eşleşen maç", hit, "/", len(L), "özellikli", len(rows))
def resid(name, sel, key, t):
    a = np.array([won(m, key) - prob(m, key, t) for m, fh, fa in rows if sel(fh, fa)], float)
    if len(a) < 30: print(f"  {name}: az veri"); return
    print(f"  {name:48s} n={len(a):5d}  {100*a.mean():+5.2f} puan (±{196*a.std()/np.sqrt(len(a)):.2f})")
for t, tn in (("o", "AÇILIŞ oranına göre (kadro belli değilken)"), ("c", "KAPANIŞ oranına göre (kadro açıklandıktan sonra)")):
    print(tn + " — ev sahibi kazanır:")
    resid("ev 3+ düzenli oyuncu eksik, dep. ≤1", lambda fh, fa: fh["miss"] >= 3 and fa["miss"] <= 1, "1", t)
    resid("dep 3+ düzenli oyuncu eksik, ev ≤1", lambda fh, fa: fa["miss"] >= 3 and fh["miss"] <= 1, "1", t)
    resid("ev 2+ fazla eksik", lambda fh, fa: fh["miss"] - fa["miss"] >= 2, "1", t)
    resid("dep 2+ fazla eksik", lambda fh, fa: fa["miss"] - fh["miss"] >= 2, "1", t)
    resid("ev kalecisi değişmiş", lambda fh, fa: fh["gk"] and not fa["gk"], "1", t)
    resid("dep kalecisi değişmiş", lambda fh, fa: fa["gk"] and not fh["gk"], "1", t)
    resid("ev golcüsü yok (son 8'de 3+ gol)", lambda fh, fa: fh["scorer"] > 0 and fa["scorer"] == 0, "1", t)
    resid("dep golcüsü yok", lambda fh, fa: fa["scorer"] > 0 and fh["scorer"] == 0, "1", t)
    print("  2,5 Üst:")
    resid("golcülerden biri yok", lambda fh, fa: fh["scorer"] + fa["scorer"] > 0, "O", t)
    resid("toplam 5+ düzenli eksik", lambda fh, fa: fh["miss"] + fa["miss"] >= 5, "O", t)
# seçim düzeyinde: seçilen tarafın kadrosu eksikse
print("\nSeçim düzeyinde (açılışta seçilen MS favorisi):")
A = collections.defaultdict(Acc)
for m, fh, fa in rows:
    g = grade(m["o"])
    if not g or g[0] != "MS" or g[1] == "X": continue
    me, op = (fh, fa) if g[1] == "1" else (fa, fh)
    worse = me["miss"] - op["miss"] >= 2 or (me["scorer"] > 0) or (me["gk"])
    A["favorinin kadrosu eksik" if worse else "favorinin kadrosu tam"].add(m, g[1], g[2], srcs=("oA", "cA", "cM"))
for k in A: print(A[k].row(k))
