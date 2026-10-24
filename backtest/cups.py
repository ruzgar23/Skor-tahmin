"""ESPN'den kupa maçlarının tarihleri (dinlenme günü için)."""
import urllib.request, json, gzip, pickle, concurrent.futures as cf, sys
CUPS = {"uefa.champions": None, "uefa.europa": None, "uefa.europa.conf": None, "uefa.champions_qual": None, "uefa.europa_qual": None,
        "uefa.europa.conf_qual": None, "uefa.super_cup": None, "eng.fa": "ENG", "eng.league_cup": "ENG", "eng.trophy": "ENG", "eng.charity": "ENG",
        "esp.copa_del_rey": "ESP", "esp.super_cup": "ESP", "ger.dfb_pokal": "GER", "ger.super_cup": "GER", "ita.coppa_italia": "ITA", "ita.super_cup": "ITA",
        "fra.coupe_de_france": "FRA", "fra.super_cup": "FRA", "ned.cup": "NED", "ned.supercup": "NED", "por.taca.portugal": "POR", "sco.tennents": "SCO", "sco.cis": "SCO", "sco.challenge": "SCO"}
months = [f"{y}{m:02d}" for y in range(2019, 2027) for m in range(1, 13) if "201907" <= f"{y}{m:02d}" <= "202610"]
def g(job):
    s, mo = job
    u = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{s}/scoreboard?dates={mo}&limit=900"
    for t in range(3):
        try:
            b = urllib.request.urlopen(u, timeout=40).read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            j = json.loads(b); break
        except Exception as e:
            j = None
    out = []
    for e in (j or {}).get("events", []):
        c = e["competitions"][0]
        if c.get("status", {}).get("type", {}).get("state") == "pre": continue
        out.append((s, CUPS[s], e["date"][:10], [x["team"]["displayName"] for x in c["competitors"]]))
    return out
jobs = [(s, m) for s in CUPS for m in months]
with cf.ThreadPoolExecutor(12) as ex: res = [x for r in ex.map(g, jobs) for x in r]
pickle.dump(res, open(sys.argv[1], "wb"))
import collections; print(len(res), collections.Counter(r[0] for r in res))
