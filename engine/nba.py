"""NBA: ESPN fikstür ve DraftKings oranları; olasılıklar piyasadan.
Sayı farkı ~ Normal(-spread, SD), toplam ~ Normal(overUnder, SD); NBA SD 2025-26 sezonunun 1.064 maçından ölçüldü.
Güven: MS favorisi ≥%75 güçlü (testte %76–85 kazandı), %65–75 orta (%64–76). Handikap/alt-üst ~%50: öneri yok."""
import json, gzip, urllib.request, time, sys
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from scipy.stats import norm

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/"
LEAGUES = {"NBA": "nba", "WNBA": "wnba"}
SD = {"NBA": (14.0, 22.5), "WNBA": (11.0, 17.0)}  # (sayı farkı, toplam)
TR = {"Los Angeles Lakers": "LA Lakers", "LA Clippers": "LA Clippers"}


def get(path):
    for t in range(3):
        try:
            b = urllib.request.urlopen(BASE + path, timeout=25).read()
            if b[:2] == b'\x1f\x8b': b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1)
    return None


def american(o):
    try:
        v = float(str(o).replace("+", ""))
    except (TypeError, ValueError):
        return None
    return None if v == 0 else 1 + (v / 100 if v > 0 else 100 / -v)


def parse_odds(c):
    od = (c.get("odds") or [None])[0]
    if not od:
        return None
    ml = od.get("moneyline") or {}
    def side(s, when):
        return american(((ml.get(s) or {}).get(when) or {}).get("odds"))
    h, a = side("home", "close") or side("home", "open"), side("away", "close") or side("away", "open")
    h0, a0 = side("home", "open"), side("away", "open")
    spread = od.get("spread"); ou = od.get("overUnder")
    if spread is None:
        ps = ((od.get("pointSpread") or {}).get("home") or {}).get("close") or {}
        try: spread = float(ps.get("line"))
        except (TypeError, ValueError): spread = None
    out = dict(h=h, a=a, h0=h0, a0=a0, spread=spread, total=ou, book=(od.get("provider") or {}).get("name", "DraftKings"))
    return out if (h and a) or spread is not None else None


def probs(o, lg="NBA"):
    """Piyasadan olasılıklar."""
    SD_MARGIN, SD_TOTAL = SD.get(lg, SD["NBA"])
    if o.get("h") and o.get("a"):
        ph = (1 / o["h"]) / (1 / o["h"] + 1 / o["a"])
    else:
        ph = float(norm.cdf(-o["spread"] / SD_MARGIN))
    exp_margin = -o["spread"] if o.get("spread") is not None else float(norm.ppf(ph) * SD_MARGIN)
    p = {"1": ph, "2": 1 - ph, "exp_margin": exp_margin}
    if o.get("spread") is not None:
        p["hcp"] = {}
        for d in (-6, -3, 0, 3, 6):
            line = o["spread"] + d  # ev sahibi handikabı (örn. -5,5)
            p["hcp"][f"{line:+.1f}"] = float(1 - norm.cdf(-line, exp_margin, SD_MARGIN))  # ev sahibi handikapla kazanır
    if o.get("total") is not None:
        p["exp_total"] = float(o["total"]); p["tot"] = {}
        for d in (-10, -5, 0, 5, 10):
            line = o["total"] + d
            p["tot"][f"{line:.1f}"] = float(1 - norm.cdf(line, o["total"], SD_TOTAL))
    if o.get("h0") and o.get("a0"):
        p["open1"] = (1 / o["h0"]) / (1 / o["h0"] + 1 / o["a0"])
    return p


def grade(m):
    p = m["p"]; fav = "1" if p["1"] >= p["2"] else "2"; pr = p[fav]
    label = f"MS {fav}"
    if pr >= .75: return dict(label=label, k=fav, prob=pr, tier=3, minOdds=1.03 / pr)
    if pr >= .65: return dict(label=label, k=fav, prob=pr, tier=2, minOdds=1.03 / pr)
    return None


def fixtures(days=2, now=None):
    now = now or datetime.now(timezone.utc)
    ds = [(now + timedelta(days=i)).date() for i in range(-1, days + 1)]
    out = []
    pairs = [(lg, s, d) for lg, s in LEAGUES.items() for d in ds]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda t: (t, get(f"{t[1]}/scoreboard?dates={t[2]:%Y%m%d}")), pairs))
    seen = set()
    for (lg, s, d), sb in res:
        for ev in (sb or {}).get("events", []):
            if ev["id"] in seen: continue
            seen.add(ev["id"])
            c = ev["competitions"][0]; sd = {x["homeAway"]: x for x in c["competitors"]}
            ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            st = ev["status"]["type"]["state"]
            item = dict(id=f"{lg}-{ev['id']}", eid=ev["id"], lg=lg, lgName=lg, sport="basketbol", ko=ko.isoformat(),
                        home=sd["home"]["team"]["displayName"], away=sd["away"]["team"]["displayName"], state=st)
            if st == "post":
                try: item["res"] = [int(sd["home"]["score"]), int(sd["away"]["score"])]
                except (KeyError, ValueError, TypeError): pass
            o = parse_odds(c)
            if o:
                item["odds"] = o; item["p"] = probs(o, lg)
            out.append(item)
    return out


def scan(outpath):
    allg = fixtures()
    now = datetime.now(timezone.utc)
    upcoming = [g for g in allg if g["state"] == "pre" and "p" in g and datetime.fromisoformat(g["ko"]) > now]
    done = [g for g in allg if g["state"] == "post" and g.get("res")]
    upcoming.sort(key=lambda g: g["ko"])
    json.dump(dict(generated=now.isoformat(), games=upcoming, results=done), open(outpath, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"NBA: {len(upcoming)} yaklaşan maç, {len(done)} biten maç")
    return upcoming, done


if __name__ == "__main__":
    scan(sys.argv[1])
