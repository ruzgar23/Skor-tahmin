"""Dinlenme, yoğunluk, Avrupa maçı ve sezon sonu motivasyon özellikleri."""
import sys, pickle, collections, datetime as dt, bisect
sys.path.insert(0, "/home/claude/skor-tahmin/engine"); import espn, engine as E
sys.path.insert(0, sys.path[0]); from lib import *
R = load(); cups = pickle.load(open(BASE + "cups.pkl", "rb"))
names = collections.defaultdict(set)
for m in R: c = E.LEAGUE_COUNTRY[m["lg"]]; names[c] |= {m["home"], m["away"]}
allnames = set().union(*names.values())
BAD = set("cardiffmu interturku apollonlimassol hibernians lincolnredimps arsenaltula lillestrom hamrunspartans interdescaldes dinamobrest interbaku arsenaltivat oxfordcity joveespanol sportingceuta ceutadejunio deportivaceuta stuttgarterkickers hebchamburg marseilleconsolat efreimssainteanne bastiaborgo strasbourgkoenigshoffen excelsiormaassluis rkavvolendam benficaecastelobranco eaststirlingshire stirlinguniversity edinburghu brorarangers berwickrangers clydebank kilwinningrangers cuparhearts dundeenorthend".split())
import re as _re
def bad(n): return espn.norm(n) in BAD or _re.search(r"\b(U\d\d|B|II)$", n.strip()) is not None
cache = {}; dates = collections.defaultdict(list); euro = collections.defaultdict(list); unmatched = collections.Counter()
for slug, country, d, comps in cups:
    for nmx in comps:
        k = (country, nmx)
        if k not in cache:
            if bad(nmx) or (country is None and espn.norm(nmx) in espn.CUP_NO_MATCH): cache[k] = None
            else: cache[k] = espn.match_name(nmx, names[country] if country else allnames, strict=True)
        t = cache[k]
        if t is None: unmatched[nmx] += 1; continue
        day = dt.date.fromisoformat(d); dates[t].append(day)
        if slug.startswith("uefa") and "super" not in slug: euro[t].append(day)
for m in R: dates[m["home"]].append(m["date"]); dates[m["away"]].append(m["date"])
for t in dates: dates[t] = sorted(set(dates[t]))
for t in euro: euro[t] = sorted(set(euro[t]))
print("eşleşen kupa adı", sum(1 for v in cache.values() if v), "eşleşmeyen", sum(1 for v in cache.values() if not v))
print("örnek eşleşmeler:", [(k[1], v) for k, v in list(cache.items()) if v and espn.norm(k[1]) != espn.norm(v)][:25])
def rest(t, d):
    L = dates[t]; i = bisect.bisect_left(L, d)
    prev = L[i-1] if i > 0 else None
    r = (d - prev).days if prev else None
    n14 = i - bisect.bisect_left(L, d - dt.timedelta(days=14))
    return (min(r, 15) if r is not None and r <= 30 else None), n14
def eu(t, d):
    L = euro.get(t, []); i = bisect.bisect_left(L, d)
    before = L[i-1] if i > 0 else None; j = bisect.bisect_right(L, d); after = L[j] if j < len(L) else None
    return (before is not None and (d - before).days <= 4), (after is not None and 0 < (after - d).days <= 4)
# sezon sonu motivasyon
tab = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))  # (lg,season) -> team -> [pts, played]
teams = collections.defaultdict(set)
for m in R: teams[(m["lg"], m["season"])] |= {m["home"], m["away"]}
for m in R:
    key = (m["lg"], m["season"]); T = tab[key]; n = len(teams[key])
    total = 38 if m["lg"] in ("SC0",) else (36 if m["lg"] in ("SC1", "SC2", "SC3") else 2 * (n - 1))
    def dead(t):
        pts, pl = T[t]; rem = total - pl
        if rem > 8 or n < 10 or m["season"] == "2627": return None
        std = sorted((v[0], v[1]) for v in T.values() if True)[::-1]
        if len(std) < n: return None
        up = std[5][0]; down_pts, down_pl = std[n - 3]  # 6. sıra ve küme düşme hattı (sondan 3.)
        can_up = pts + 3 * rem >= up
        can_down = down_pts + 3 * (total - down_pl) >= pts
        return (not can_up) and (not can_down)
    m["dead_h"] = dead(m["home"]); m["dead_a"] = dead(m["away"])
    m["rest_h"], m["n14_h"] = rest(m["home"], m["date"]); m["rest_a"], m["n14_a"] = rest(m["away"], m["date"])
    m["eub_h"], m["eua_h"] = eu(m["home"], m["date"]); m["eub_a"], m["eua_a"] = eu(m["away"], m["date"])
    a, b = m["hg"], m["ag"]
    T[m["home"]][0] += 3 if a > b else (1 if a == b else 0); T[m["away"]][0] += 3 if b > a else (1 if a == b else 0)
    T[m["home"]][1] += 1; T[m["away"]][1] += 1
pickle.dump(R, open(BASE + "feat.pkl", "wb"))
print("ölü maç (ev/dep):", sum(1 for m in R if m["dead_h"]), sum(1 for m in R if m["dead_a"]), "değerlendirilen", sum(1 for m in R if m["dead_h"] is not None))
print("Avrupa sonrası (≤4 gün) ev/dep:", sum(m["eub_h"] for m in R), sum(m["eub_a"] for m in R), " Avrupa öncesi:", sum(m["eua_h"] for m in R), sum(m["eua_a"] for m in R))
print("dinlenme dağılımı (ev):", sorted(collections.Counter(m["rest_h"] for m in R).items(), key=lambda x: (x[0] is None, x[0] or 0))[:20])
