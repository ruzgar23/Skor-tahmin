"""ESPN: ATP/WTA tekler maç sonuçları (Elo için)."""
import urllib.request, json, gzip, pickle, sys, time, datetime as dt, concurrent.futures as cf
def g(u):
    for t in range(4):
        try:
            b = urllib.request.urlopen(u, timeout=40).read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1 + t)
    return None
days = []; d = dt.date(2022, 1, 1)
while d <= dt.date(2026, 10, 24): days.append(d); d += dt.timedelta(days=1)
def day(job):
    tour, d = job; j = g(f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard?dates={d:%Y%m%d}") or {}
    out = []
    for e in j.get("events", []):
        for gr in e.get("groupings", []):
            if "Singles" not in gr["grouping"]["displayName"]: continue
            for c in gr["competitions"]:
                if c["status"]["type"]["name"] != "STATUS_FINAL": continue
                cdate = (c.get("date") or c.get("startDate") or "")[:10]
                if cdate and cdate != f"{d:%Y-%m-%d}": continue  # turnuva olayı birden çok günde tekrar görünür
                ps = c["competitors"]
                if len(ps) != 2 or not any(p.get("winner") for p in ps): continue
                w = [p for p in ps if p.get("winner")][0]; l = [p for p in ps if not p.get("winner")][0]
                sets = [(a.get("value"), b.get("value")) for a, b in zip(w.get("linescores", []), l.get("linescores", []))]
                out.append(dict(tour=tour, id=c["id"], date=d, event=e["name"], major=e.get("major"), rnd=(c.get("round") or {}).get("displayName", ""),
                                w=(w.get("athlete") or {}).get("displayName"), l=(l.get("athlete") or {}).get("displayName"), sets=sets,
                                notes=" ".join(n.get("text", "") for n in c.get("notes", []))))
    return out
with cf.ThreadPoolExecutor(12) as ex: M = [x for r in ex.map(day, [(t, d) for t in ("atp", "wta") for d in days]) for x in r]
M = list({m["id"]: m for m in M}.values()); M.sort(key=lambda m: m["date"])
pickle.dump(M, open(sys.argv[1], "wb"))
import collections; print(len(M), collections.Counter((m["tour"], m["date"].year) for m in M))
