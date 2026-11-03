"""ESPN olay listesinden (keyEvents) gol ve kırmızı kart dakikaları — korner şartı olmadan, tüm liglerde.
Gol sayısı skorla tutmayan maçlar elenir. Canlı gol pazarlarının (İY, takım golü, sıradaki gol) testi için.
Kullanım: python -I backtest/goal_events.py <çıktı.pkl> [başlangıç YYYYMM]"""
import sys, os, json, gzip, re, time, pickle, urllib.request, collections
import concurrent.futures as cf
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import espn

B = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
OUT = sys.argv[1]; START = sys.argv[2] if len(sys.argv) > 2 else "202308"


def g(u):
    for t in range(4):
        try:
            b = urllib.request.urlopen(u, timeout=40).read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1 + 2 * t)
    return None


def months():
    y, m = int(START[:4]), int(START[4:]); t = date.today()
    while (y, m) <= (t.year, t.month):
        if m not in (6, 7): yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_events(job):
    lg, slug, ym = job
    j = g(f"{B}{slug}/scoreboard?dates={ym}&limit=500") or {}
    out = []
    for e in j.get("events", []):
        c = e["competitions"][0]
        if c["status"]["type"]["state"] != "post": continue
        s = {x["homeAway"]: x for x in c["competitors"]}
        out.append(dict(lg=lg, id=e["id"], date=e["date"][:10], home=s["home"]["team"]["displayName"],
                        away=s["away"]["team"]["displayName"], hid=s["home"]["team"]["id"], aid=s["away"]["team"]["id"],
                        hs=int(s["home"].get("score") or 0), as_=int(s["away"].get("score") or 0)))
    return out


MIN = re.compile(r"(\d+)'(?:\s*\+\s*(\d+)')?")


def minute(c):
    m = MIN.match((c.get("time") or c.get("clock") or {}).get("displayValue") or "")
    if not m: return None
    return int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0) * 0.0  # uzatma dakikası devre sonuna sayılır


def summary(m):
    try:
        j = g(f"{B}{espn.SLUG[m['lg']]}/summary?event={m['id']}")
        if not j: return None
        goals, reds = [], []
        for k in j.get("keyEvents") or []:
            t = (k.get("type") or {}).get("text", "").lower(); tm = (k.get("team") or {}).get("displayName")
            mn = minute(k); side = "h" if tm == m["home"] else ("a" if tm == m["away"] else None)
            if mn is None: continue
            if t.startswith(("goal", "own goal", "penalty - scored")):
                goals.append((mn, side))
            elif "red card" in t:
                reds.append((mn, side))
        if len(goals) != m["hs"] + m["as_"] or any(s is None for _, s in goals + reds): return None
        if sum(s == "h" for _, s in goals) != m["hs"]: return None
        m.update(goals=sorted(goals), reds=sorted(reds))
        return m
    except Exception:
        return None


jobs = [(lg, slug, ym) for lg, slug in espn.SLUG.items() for ym in months()]
with cf.ThreadPoolExecutor(12) as ex:
    M = [x for r in ex.map(month_events, jobs) for x in r]
M = list({m["id"]: m for m in M}.values())
print("biten maç", len(M), flush=True)
with cf.ThreadPoolExecutor(16) as ex:
    R = [m for m in ex.map(summary, M) if m]
R.sort(key=lambda m: m["date"])
pickle.dump(R, open(OUT, "wb"))
print("doğrulanmış maç", len(R), collections.Counter(m["lg"] for m in R).most_common(), flush=True)
