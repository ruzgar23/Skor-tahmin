"""ESPN maç yorumlarından dakika dakika olay verisi: korner, gol, kırmızı kart (her iki takım için).
Yalnızca yorumdaki korner sayısı ESPN istatistiğiyle birebir tutan maçlar saklanır (eksik yorum elenir).
Kullanım: python -I backtest/live_events.py <çıktı.pkl> [başlangıç YYYYMM]"""
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
        return _summary(m)
    except Exception:
        return None


def _summary(m):
    j = g(f"{B}{espn.SLUG[m['lg']]}/summary?event={m['id']}")
    if not j: return None
    box = {}
    for t in (j.get("boxscore") or {}).get("teams", []):
        st = {s["name"]: s.get("displayValue") for s in t.get("statistics", [])}
        try: box[t["team"]["displayName"]] = int(st.get("wonCorners"))
        except (TypeError, ValueError): return None
    if len(box) != 2: return None
    ev = []
    for c in j.get("commentary") or []:
        tx = c.get("text") or ""; mn = minute(c)
        if mn is None: continue
        if tx.startswith("Corner,"):
            team = tx[7:].split(".")[0].strip(); ev.append((mn, "C", team))
        elif tx.startswith("Goal!") or tx.startswith("Own Goal"):
            ev.append((mn, "G", None))
        elif "red card" in tx.lower() or "second yellow" in tx.lower():
            ev.append((mn, "R", tx))
    def side(team):
        if team == m["home"]: return "h"
        if team == m["away"]: return "a"
        # yorumda kısa ad kullanılabilir
        if team and (team in m["home"] or m["home"] in team): return "h"
        if team and (team in m["away"] or m["away"] in team): return "a"
        return None
    cor = [(mn, side(t)) for mn, k, t in ev if k == "C"]
    if any(s is None for _, s in cor): return None
    if sum(s == "h" for _, s in cor) != box.get(m["home"]) or sum(s == "a" for _, s in cor) != box.get(m["away"]): return None
    reds = []
    for mn, k, tx in ev:
        if k != "R": continue
        s = "h" if m["home"] in tx else ("a" if m["away"] in tx else None)
        if s is None: return None  # hangi takımın kırmızısı olduğu anlaşılmıyorsa maçı ele
        reds.append((mn, s))
    # gol dakikaları ve hangi takım: keyEvents daha güvenilir
    goals = []
    for k in j.get("keyEvents") or []:
        if (k.get("type") or {}).get("text", "").lower().startswith(("goal", "own goal", "penalty - scored")):
            tm = (k.get("team") or {}).get("displayName"); mn = minute(k)
            if mn is not None: goals.append((mn, "h" if tm == m["home"] else ("a" if tm == m["away"] else None)))
    if len(goals) != m["hs"] + m["as_"] or any(s is None for _, s in goals): return None
    m.update(corners=sorted(cor), goals=sorted(goals), reds=sorted(reds), ch=box[m["home"]], ca=box[m["away"]])
    return m


jobs = [(lg, slug, ym) for lg, slug in espn.SLUG.items() for ym in months()]
with cf.ThreadPoolExecutor(12) as ex:
    M = [x for r in ex.map(month_events, jobs) for x in r]
M = list({m["id"]: m for m in M}.values())
print("biten maç", len(M), flush=True)
# yorumu olmayan lig-sezonları atla: her ayın ilk maçını yokla
by = collections.defaultdict(list)
for m in M: by[(m["lg"], m["date"][:7])].append(m)
def probe(k):
    for m in by[k][:2]:
        if summary(dict(m)): return k, True
    return k, False
with cf.ThreadPoolExecutor(16) as ex:
    ok = {k for k, v in ex.map(probe, list(by)) if v}
cand = [m for k in ok for m in by[k]]
print("yorumlu lig-ay", len(ok), "/", len(by), "aday maç", len(cand), flush=True)
with cf.ThreadPoolExecutor(16) as ex:
    R = [m for m in ex.map(summary, cand) if m]
R.sort(key=lambda m: m["date"])
pickle.dump(R, open(OUT, "wb"))
print("doğrulanmış maç", len(R), collections.Counter(m["lg"] for m in R).most_common(), flush=True)
