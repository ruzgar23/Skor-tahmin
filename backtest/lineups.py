"""ESPN'den geçmiş maçların ilk 11'leri (seçili ligler, 2023-08 .. bugün)."""
import urllib.request, json, gzip, pickle, concurrent.futures as cf, sys, time
LG = {"E0": "eng.1", "E1": "eng.2", "SP1": "esp.1", "I1": "ita.1", "D1": "ger.1", "F1": "fra.1", "T1": "tur.1", "N1": "ned.1", "P1": "por.1", "SC0": "sco.1"}
months = [f"{y}{m:02d}" for y in range(2023, 2027) for m in range(1, 13) if "202307" <= f"{y}{m:02d}" <= "202610"]
def g(u):
    for t in range(4):
        try:
            b = urllib.request.urlopen(u, timeout=40).read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1 + t)
    return None
def month(job):
    lg, mo = job; j = g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LG[lg]}/scoreboard?dates={mo}&limit=900") or {}
    out = []
    for e in j.get("events", []):
        c = e["competitions"][0]
        if c.get("status", {}).get("type", {}).get("state") != "post": continue
        hm = {x["homeAway"]: x["team"]["displayName"] for x in c["competitors"]}
        out.append((lg, e["id"], e["date"], hm.get("home"), hm.get("away")))
    return out
with cf.ThreadPoolExecutor(12) as ex: evs = [x for r in ex.map(month, [(l, m) for l in LG for m in months]) for x in r]
evs = list({e[1]: e for e in evs}.values()); print("maç", len(evs), flush=True)
def summ(e):
    lg, eid, d, h, a = e
    s = g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LG[lg]}/summary?event={eid}")
    if not s: return None
    out = dict(lg=lg, id=eid, date=d, home=h, away=a, xi={})
    for r in s.get("rosters", []):
        st = []
        for p in r.get("roster", []):
            if p.get("starter"):
                gl = 0
                for x in p.get("stats", []) or []:
                    if x.get("name") == "totalGoals": gl = x.get("value", 0)
                st.append((p["athlete"]["id"], p["athlete"]["displayName"], (p.get("position") or {}).get("abbreviation", ""), gl))
        out["xi"][r.get("homeAway")] = st
    return out
res = []; done = 0
with cf.ThreadPoolExecutor(16) as ex:
    for r in ex.map(summ, evs):
        done += 1
        if r: res.append(r)
        if done % 1000 == 0: print(done, flush=True); pickle.dump(res, open(sys.argv[1], "wb"))
pickle.dump(res, open(sys.argv[1], "wb")); print("bitti", len(res), "ilk 11 olan", sum(1 for r in res if len(r["xi"]) == 2))
