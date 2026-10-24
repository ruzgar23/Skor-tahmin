"""ESPN fikstür kaynağı: önümüzdeki günlerin maçları + (varsa) DraftKings oranları.
Takım adları football-data adlarına eşlenir."""
import json, gzip, re, unicodedata, difflib, urllib.request
from datetime import datetime, timedelta, timezone

SLUG = {"E0": "eng.1", "E1": "eng.2", "E2": "eng.3", "E3": "eng.4", "SP1": "esp.1", "SP2": "esp.2",
        "I1": "ita.1", "I2": "ita.2", "D1": "ger.1", "D2": "ger.2", "F1": "fra.1", "F2": "fra.2",
        "T1": "tur.1", "N1": "ned.1", "P1": "por.1", "SC0": "sco.1", "SC1": "sco.2", "SC2": "sco.3",
        "SC3": "sco.4", "G1": "gre.1"}

CUPS = {"UCL": "uefa.champions", "UEL": "uefa.europa", "UECL": "uefa.europa.conf"}
CUP_NAMES = {"UCL": "Şampiyonlar Ligi", "UEL": "Avrupa Ligi", "UECL": "Konferans Ligi"}

# ESPN adı (normalize) -> football-data adı; otomatik eşleşmenin kaçırdıkları
ALIAS = {
    "manchestercity": "Man City", "manchesterunited": "Man United", "nottinghamforest": "Nott'm Forest",
    "wolverhamptonwanderers": "Wolves", "sheffieldwednesday": "Sheffield Weds", "sheffieldunited": "Sheffield United",
    "queensparkrangers": "QPR", "westbromwichalbion": "West Brom", "brightonhovealbion": "Brighton",
    "tottenhamhotspur": "Tottenham", "newcastleunited": "Newcastle", "westhamunited": "West Ham",
    "leicestercity": "Leicester", "ipswichtown": "Ipswich", "lutontown": "Luton", "hullcity": "Hull",
    "stokecity": "Stoke", "cardiffcity": "Cardiff", "swanseacity": "Swansea", "norwichcity": "Norwich",
    "coventrycity": "Coventry", "birminghamcity": "Birmingham", "prestonnorthend": "Preston",
    "atleticomadrid": "Ath Madrid", "athleticclub": "Ath Bilbao", "athleticbilbao": "Ath Bilbao",
    "realbetis": "Betis", "realsociedad": "Sociedad", "celtavigo": "Celta", "rayovallecano": "Vallecano",
    "deportivolacoruna": "La Coruna", "espanyol": "Espanol", "alaves": "Alaves",
    "internazionale": "Inter", "acmilan": "Milan", "asroma": "Roma",
    "bayernmunich": "Bayern Munich", "borussiadortmund": "Dortmund", "bayerleverkusen": "Leverkusen",
    "borussiamonchengladbach": "M'gladbach", "eintrachtfrankfurt": "Ein Frankfurt", "rbleipzig": "RB Leipzig",
    "fckoln": "FC Koln", "werderbremen": "Werder Bremen", "vfbstuttgart": "Stuttgart", "tsghoffenheim": "Hoffenheim",
    "parissaintgermain": "Paris SG", "olympiquemarseille": "Marseille", "olympiquelyonnais": "Lyon",
    "asmonaco": "Monaco", "stadebrestois29": "Brest", "staderennais": "Rennes",
    "istanbulbasaksehir": "Buyuksehyr", "basaksehir": "Buyuksehyr", "goztepe": "Goztep",
    "caykurrizespor": "Rizespor", "corumfk": "Corum", "gaziantepfk": "Gaziantep", "amedsportif": "Amedspor",
    "psveindhoven": "PSV Eindhoven", "feyenoordrotterdam": "Feyenoord", "ajaxamsterdam": "Ajax",
    "sportingcp": "Sp Lisbon", "sportinglisbon": "Sp Lisbon", "fcporto": "Porto", "sportingbraga": "Sp Braga",
    "celtic": "Celtic", "rangers": "Rangers", "heartofmidlothian": "Hearts", "hibernian": "Hibernian",
    "athletic": "Ath Bilbao", "deportivo": "La Coruna", "celtafortuna": "Celta B", "cologne": "FC Koln",
    "ayrunited": "Ayr", "realracingclub": "Santander", "racingsantander": "Santander", "sportinggijon": "Sp Gijon",
    "braga": "Sp Braga", "olympiacos": "Olympiakos", "paok": "PAOK", "aekathens": "AEK",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " ")
    s = re.sub(r"\b(fc|cf|afc|sc|ac|ssc|sv|vfl|vfb|cd|ud|sd|rcd|rc|club|calcio|1\.|as|osc|sk|spor kulubu)\b", " ", s)
    return re.sub(r"[^a-z]", "", s)


def get(slug, day, tries=3):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={day:%Y%m%d}"
    for t in range(tries):
        try:
            b = urllib.request.urlopen(url, timeout=25).read(); break
        except Exception:
            if t == tries - 1:
                raise
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return json.loads(b)


def american(o):
    try:
        v = float(str(o).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    return 1 + (v / 100 if v > 0 else 100 / -v)


def parse_odds(c):
    od = (c.get("odds") or [None])[0]
    if not od:
        return None
    ml = od.get("moneyline") or {}
    pick = lambda side: american(((ml.get(side) or {}).get("close") or (ml.get(side) or {}).get("open") or {}).get("odds"))
    o = {"1": pick("home"), "X": pick("draw"), "2": pick("away")}
    if not all(o.values()):
        return None
    tot = od.get("total") or {}
    line = od.get("overUnder")
    ov = ((tot.get("over") or {}).get("close") or {}).get("odds")
    un = ((tot.get("under") or {}).get("close") or {}).get("odds")
    o["line"] = float(line) if line is not None else None
    o["over"], o["under"] = american(ov), american(un)
    o["book"] = (od.get("provider") or {}).get("name", "ESPN")
    return o


def match_name(name, cands, strict=False):
    k = norm(name)
    if k in ALIAS and ALIAS[k] in cands:
        return ALIAS[k]
    nm = {norm(c): c for c in cands}
    if k in nm:
        return nm[k]
    for nk, c in nm.items():  # biri diğerini içeriyorsa
        if len(nk) >= (5 if strict else 4) and (nk in k or (not strict and k in nk)):
            return c
    best = difflib.get_close_matches(k, list(nm), 1, 0.86 if strict else 0.6)
    return nm[best[0]] if best else None


# Kupalarda adı bizim liglerdeki bir takıma benzeyen ama başka kulüp olanlar
CUP_NO_MATCH = {"redstarbelgrade", "crvenazvezda", "spartaprague", "slaviaprague", "unionstgilloise"}


def resolve(lg, name, team_names):
    """(football-data adı, takımın ligi) ya da (None, None). Kupalarda tüm liglerde arar."""
    if lg not in SLUG and norm(name) in CUP_NO_MATCH:
        return None, None
    if lg in SLUG:
        r = match_name(name, team_names.get(lg, set()))
        return (r, lg) if r else (None, None)
    owner = {}
    for l, ns in team_names.items():
        for n in ns:
            owner.setdefault(n, l)
    r = match_name(name, set(owner), strict=True)
    return (r, owner[r]) if r else (None, None)


_CACHE = {}


def prefetch(pairs, workers=16):
    """(slug, gün) çiftlerini paralel indirip önbelleğe alır."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [p for p in set(pairs) if p not in _CACHE]
    def one(p):
        try:
            return p, get(*p)
        except Exception as e:
            print("ESPN alınamadı", p[0], p[1], e); return p, None
    with ThreadPoolExecutor(workers) as ex:
        for p, d in ex.map(one, todo):
            _CACHE[p] = d


def _events(lg, slug, days_iter, state):
    seen = set()
    days_iter = list(days_iter)
    prefetch([(slug, d) for d in days_iter])
    for day in days_iter:
        data = _CACHE.get((slug, day))
        if not data:
            continue
        for ev in data.get("events", []):
            if ev["id"] in seen or ev.get("status", {}).get("type", {}).get("state") != state:
                continue
            seen.add(ev["id"])
            yield ev


def fixtures(team_names, days=8, now=None):
    """team_names: lig -> o ligde görülen football-data takım adları kümesi."""
    now = now or datetime.now(timezone.utc)
    out, unmatched = [], []
    ds = [(now + timedelta(days=i)).date() for i in range(days)]
    prefetch([(slug, d) for slug in {**SLUG, **CUPS}.values() for d in ds])
    for lg, slug in {**SLUG, **CUPS}.items():
        for ev in _events(lg, slug, ds, "pre"):
            c = ev["competitions"][0]
            side = {x["homeAway"]: x["team"]["displayName"] for x in c["competitors"]}
            h, hlg = resolve(lg, side["home"], team_names)
            a, alg = resolve(lg, side["away"], team_names)
            if lg in SLUG and (not h or not a):
                unmatched.append((lg, side["home"] if not h else None, side["away"] if not a else None))
            ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            out.append(dict(lg=lg, ko=ko, home=h or side["home"], away=a or side["away"], hlg=hlg, alg=alg,
                            espn=(side["home"], side["away"]), known=(bool(h), bool(a)), odds=parse_odds(c)))
    return out, unmatched


def results(team_names, since, now=None, cups=True):
    """since tarihinden bugüne biten maçlar. Kupa maçlarında eşleşmeyen takımlar ESPN adıyla döner."""
    now = now or datetime.now(timezone.utc)
    out = []
    days = [since + timedelta(days=i) for i in range(max((now.date() - since).days + 1, 0))]
    slugs = {**SLUG, **CUPS} if cups else SLUG
    prefetch([(slug, d) for slug in slugs.values() for d in days])
    for lg, slug in slugs.items():
        for ev in _events(lg, slug, days, "post"):
            c = ev["competitions"][0]
            sd = {x["homeAway"]: x for x in c["competitors"]}
            hn, an = sd["home"]["team"]["displayName"], sd["away"]["team"]["displayName"]
            h, _ = resolve(lg, hn, team_names); a, _ = resolve(lg, an, team_names)
            if lg in SLUG and (not h or not a):
                continue
            try:
                hg, ag = int(sd["home"]["score"]), int(sd["away"]["score"])
            except (KeyError, ValueError, TypeError):
                continue
            ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            out.append(dict(lg=lg, date=ko.date(), home=h or hn, away=a or an, hg=hg, ag=ag))
    return out
