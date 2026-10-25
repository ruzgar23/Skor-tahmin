"""ESPN: NBA ve NHL geçmiş maçlar + maç öncesi oranlar (summary pickcenter)."""
import urllib.request, json, gzip, pickle, sys, time, datetime as dt, concurrent.futures as cf
SP = {"nba": "basketball/nba", "nhl": "hockey/nhl"}
def g(u):
    for t in range(4):
        try:
            b = urllib.request.urlopen(u, timeout=40).read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1 + t)
    return None
def am(o):
    try: v = float(str(o).replace("+", ""))
    except (TypeError, ValueError): return None
    return None if v == 0 else 1 + (v / 100 if v > 0 else 100 / -v)
days = []
d = dt.date(2023, 10, 1)
while d <= dt.date(2026, 10, 24):
    if d.month not in (7, 8, 9): days.append(d)
    d += dt.timedelta(days=1)
def day(job):
    sp, d = job; j = g(f"https://site.api.espn.com/apis/site/v2/sports/{SP[sp]}/scoreboard?dates={d:%Y%m%d}") or {}
    out = []
    for e in j.get("events", []):
        c = e["competitions"][0]
        if c["status"]["type"]["state"] != "post": continue
        s = {x["homeAway"]: x for x in c["competitors"]}
        try: hs, as_ = int(s["home"]["score"]), int(s["away"]["score"])
        except Exception: continue
        out.append(dict(sp=sp, id=e["id"], date=d, home=s["home"]["team"]["displayName"], away=s["away"]["team"]["displayName"],
                        hs=hs, as_=as_, ot=c["status"]["period"] > (4 if sp == "nba" else 3), stype=e.get("season", {}).get("type")))
    return out
with cf.ThreadPoolExecutor(12) as ex: G = [x for r in ex.map(day, [(s, d) for s in SP for d in days]) for x in r]
print("maç", len(G), flush=True)
def summ(m):
    s = g(f"https://site.api.espn.com/apis/site/v2/sports/{SP[m['sp']]}/summary?event={m['id']}") or {}
    pc = s.get("pickcenter") or []
    for p in pc:
        h, a = p.get("homeTeamOdds") or {}, p.get("awayTeamOdds") or {}
        mlh, mla = am(h.get("moneyLine")), am(a.get("moneyLine"))
        if mlh and mla:
            m.update(book=(p.get("provider") or {}).get("name"), mlh=mlh, mla=mla, spread=p.get("spread"), total=p.get("overUnder"),
                     overOdds=am(p.get("overOdds")), underOdds=am(p.get("underOdds")), hso=am(h.get("spreadOdds")), aso=am(a.get("spreadOdds")))
            break
    return m
with cf.ThreadPoolExecutor(16) as ex: G = list(ex.map(summ, G))
pickle.dump(G, open(sys.argv[1], "wb"))
import collections; print("oranlı", collections.Counter((m["sp"], m["date"].year) for m in G if m.get("mlh")))
