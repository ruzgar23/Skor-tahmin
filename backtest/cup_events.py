"""Avrupa kupaları (ŞL, AL, KL; SLUGS ile milli maçlar da): ESPN gol dakikaları + maç öncesi DraftKings oranları (pickcenter; 2026'dan itibaren var).
Ek seçimlerin ve canlı modelin kupalarda testi için. Kullanım: python -I backtest/cup_events.py <çıktı.pkl> [başlangıç YYYYMM]"""
import sys, os, json, gzip, re, time, pickle, urllib.request, collections
import concurrent.futures as cf
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
import espn
B = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
OUT = sys.argv[1]; START = sys.argv[2] if len(sys.argv) > 2 else "202601"
MIN = re.compile(r"(\d+)'")


def g(u):
    for t in range(4):
        try:
            b = urllib.request.urlopen(u, timeout=40).read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1 + 2 * t)
    return None


def am(o):
    try: v = float(str(o).replace("+", ""))
    except (TypeError, ValueError): return None
    return None if v == 0 else 1 + (v / 100 if v > 0 else 100 / -v)


def months():
    y, m = int(START[:4]), int(START[4:]); t = date.today()
    while (y, m) <= (t.year, t.month):
        yield f"{y}{m:02d}"; y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month(job):
    lg, slug, ym = job; j = g(f"{B}{slug}/scoreboard?dates={ym}&limit=500") or {}
    out = []
    for e in j.get("events", []):
        c = e["competitions"][0]
        if c["status"]["type"]["state"] != "post": continue
        s = {x["homeAway"]: x for x in c["competitors"]}
        out.append(dict(lg=lg, slug=slug, id=e["id"], date=e["date"][:10], home=s["home"]["team"]["displayName"],
                        away=s["away"]["team"]["displayName"], hs=int(s["home"].get("score") or 0), as_=int(s["away"].get("score") or 0)))
    return out


def summ(m):
    try:
        j = g(f"{B}{m['slug']}/summary?event={m['id']}")
        if not j: return None
        pc = (j.get("pickcenter") or [None])[0]
        if not pc: return None
        o = {"1": am((pc.get("homeTeamOdds") or {}).get("moneyLine")), "X": am((pc.get("drawOdds") or {}).get("moneyLine")),
             "2": am((pc.get("awayTeamOdds") or {}).get("moneyLine")), "line": pc.get("overUnder"),
             "O": am(pc.get("overOdds")), "U": am(pc.get("underOdds"))}
        if not all(o[k] for k in "1X2"): return None
        goals, reds = [], []
        for k in j.get("keyEvents") or []:
            t = (k.get("type") or {}).get("text", "").lower(); tm = (k.get("team") or {}).get("displayName")
            mm = MIN.match(((k.get("clock") or {}).get("displayValue") or "")); side = "h" if tm == m["home"] else ("a" if tm == m["away"] else None)
            if not mm: continue
            if t.startswith(("goal", "own goal", "penalty - scored")): goals.append((float(mm.group(1)), side))
            elif "red card" in t: reds.append((float(mm.group(1)), side))
        # uzatmalı / penaltılı maçlarda skor 90 dakikayı göstermeyebilir: yalnızca 90'da biten ve tutarlı maçlar
        if len(goals) != m["hs"] + m["as_"] or any(s is None for _, s in goals + reds) or any(mn > 95 for mn, _ in goals): return None
        if sum(s == "h" for _, s in goals) != m["hs"]: return None
        m.update(o=o, goals=sorted(goals), reds=sorted(reds)); return m
    except Exception:
        return None


# İsteğe bağlı: SLUGS="NAT_NL:uefa.nations,NAT_FR:fifa.friendly" ile başka turnuvalar (ör. milli maçlar)
SL = dict(x.split(":") for x in os.environ["SLUGS"].split(",")) if os.environ.get("SLUGS") else espn.CUPS
jobs = [(lg, slug, ym) for lg, slug in SL.items() for ym in months()]
with cf.ThreadPoolExecutor(8) as ex: M = [x for r in ex.map(month, jobs) for x in r]
M = list({m["id"]: m for m in M}.values()); print("biten maç", len(M), flush=True)
with cf.ThreadPoolExecutor(12) as ex: R = [m for m in ex.map(summ, M) if m]
R.sort(key=lambda m: m["date"]); pickle.dump(R, open(OUT, "wb"))
print("oranlı ve doğrulanmış", len(R), collections.Counter(m["lg"] for m in R), flush=True)
