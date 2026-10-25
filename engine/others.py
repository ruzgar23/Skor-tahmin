"""Hokey (NHL) ve tenis (ATP/WTA): fikstür, olasılık, seçim. Çıktı: other.json {games, results}.

Backtest (backtest/README):
- NHL, normal süre (iddaa hokeyde MS normal süredir): olasılıklar DraftKings para çizgisi ve toplam çizgisinden,
  beraberliği gerçeğe göre artıran Poisson modeliyle (D=1.6) çıkarıldı. 2025-26 sezonunda 1X/X2 %75 üstü %84,
  4,5 Üst %80 üstü %83 tuttu.
- Tenis: ESPN'deki 2022'den bugüne ~46 bin ATP/WTA tekler maçından Elo (genel + yüzey, %30 yüzey ağırlığı),
  2023 ile kalibre edildi (b=0.859). 2024-26'da kalibre %80 üstü favoriler %86, %70-80 arası %74 kazandı.
  Tenis için tarihsel oran yok; bu yüzden kâr testi yapılamadı, "oran ≥" sınırı bu yüzden önemli.
"""
import json, math, os, re, sys, time, gzip, urllib.request
from datetime import datetime, timedelta, timezone, date
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.stats import poisson
from scipy.optimize import minimize

API = "https://site.api.espn.com/apis/site/v2/sports/"
HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "tennis_elo.json")


def get(path):
    for t in range(3):
        try:
            b = urllib.request.urlopen(API + path, timeout=25).read()
            if b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            time.sleep(1 + t)
    return None


def american(o):
    try:
        v = float(str(o).replace("+", ""))
    except (TypeError, ValueError):
        return None
    return None if v == 0 else 1 + (v / 100 if v > 0 else 100 / -v)


def grade_from(cands, strong, mid):
    """cands: [(etiket, olasılık)] → en iyi seçim (önce kademe, sonra olasılık)."""
    best = None
    for label, pr in cands:
        tier = 3 if pr >= strong.get(label.split()[0], 1.1) else (2 if pr >= mid.get(label.split()[0], 1.1) else 0)
        if tier and (best is None or (tier, pr) > (best["tier"], best["prob"])):
            best = dict(label=label, prob=pr, tier=tier, minOdds=1.03 / pr)
    return best


# ---------- NHL ----------
K = 12; KS = np.arange(K); D_INFL = 1.6


def _mat(lh, la):
    M = np.outer(poisson.pmf(KS, lh), poisson.pmf(KS, la)); M[np.diag_indices(K)] *= D_INFL
    return M / M.sum()


def nhl_probs(ph, total, pover=0.5):
    """ph: ev sahibinin (uzatmalar dahil) kazanma olasılığı. Normal süre olasılıkları döner."""
    tt = np.add.outer(KS, KS)

    def loss(v):
        lh, la = np.exp(v); M = _mat(lh, la)
        p1, px = np.tril(M, -1).sum(), np.trace(M)
        l = (p1 + px * lh / (lh + la) - ph) ** 2
        l += (M[tt > total].sum() - pover) ** 2 if total else 0.01 * (lh + la - 6) ** 2
        return l
    r = minimize(loss, [math.log(3.1), math.log(2.9)], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-10})
    lh, la = np.exp(r.x); M = _mat(lh, la)
    p1, px, p2 = float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())
    return {"1": p1, "X": px, "2": p2, "1X": p1 + px, "X2": px + p2, "O45": float(M[tt > 4.5].sum()),
            "O55": float(M[tt > 5.5].sum()), "U55": float(M[tt < 5.5].sum()), "U65": float(M[tt < 6.5].sum()),
            "lam": [round(float(lh), 2), round(float(la), 2)]}


def nhl_grade(p):
    c = [("1X", p["1X"]), ("X2", p["X2"]), ("4,5 Üst", p["O45"])]
    return grade_from(c, {"1X": .75, "X2": .75, "4,5": .80}, {"1X": .70, "X2": .70, "4,5": .75})


def nhl(days):
    out, res = [], []
    for d in days:
        j = get(f"hockey/nhl/scoreboard?dates={d:%Y%m%d}") or {}
        for ev in j.get("events", []):
            c = ev["competitions"][0]; sd = {x["homeAway"]: x for x in c["competitors"]}
            st = ev["status"]["type"]["state"]
            g = dict(id=f"NHL-{ev['id']}", eid=ev["id"], sport="hokey", lg="NHL", lgName="NHL", ko=ev["date"].replace("Z", "+00:00"),
                     home=sd["home"]["team"]["displayName"], away=sd["away"]["team"]["displayName"], state=st)
            if st == "post":
                try:
                    g["res"] = [int(sd["home"]["score"]), int(sd["away"]["score"])]; g["ot"] = c["status"]["period"] > 3
                    res.append(g)
                except (KeyError, ValueError, TypeError):
                    pass
                continue
            od = (c.get("odds") or [None])[0]
            if st != "pre" or not od:
                continue
            ml = od.get("moneyline") or {}
            def side(s):
                x = ml.get(s) or {}
                return american((x.get("close") or {}).get("odds")) or american((x.get("open") or {}).get("odds"))
            h, a = side("home"), side("away")
            if not (h and a):
                continue
            ph = (1 / h) / (1 / h + 1 / a)
            p = nhl_probs(ph, od.get("overUnder"))
            g.update(p=p, pick=nhl_grade(p), odds=dict(h=h, a=a, total=od.get("overUnder")),
                     info=f"Normal süre: 1 %{round(p['1']*100)} · X %{round(p['X']*100)} · 2 %{round(p['2']*100)} · 5,5 Üst %{round(p['O55']*100)}")
            out.append(g)
    return out, res


def nhl_settle(label, res, ot):
    a, b = res
    if ot:
        a = b = min(a, b)  # uzatmaya gittiyse normal süre berabere bitti
    t = a + b
    return {"1X": a >= b, "X2": a <= b, "1": a > b, "2": a < b, "4,5 Üst": t > 4.5, "5,5 Üst": t > 5.5}.get(label)


# ---------- Tenis ----------
CLAY = re.compile(r"Roland|Monte-Carlo|Madrid|Italia|Rome|Barcelona|Hamburg|Rio Open|Argentina|Chile|Estoril|Geneva|Lyon|Bastad|Gstaad|Kitzb|Umag|Houston|Marrakech|Munich|BMW|Bucharest|Palermo|Prague|Rabat|Strasbourg|Charleston|Bogota|Parma|Iasi|Budapest|Lausanne|Cluj|Rouen|Croatia|Swedish|Nordea|Generali|Tiriac|Hassan|Colsanitas|Credit One|Emilia", re.I)
GRASS = re.compile(r"Wimbledon|Halle|Terra Wortmann|Queen|cinch|HSBC|Hertogenbosch|Libema|Mallorca|Eastbourne|Rothesay|Nottingham|Birmingham|Berlin|ecotrans|Bad Homburg", re.I)
W_SURF = 0.3; CAL_B = 0.859; MIN_N = 10


def surface(ev):
    return "grass" if GRASS.search(ev) else ("clay" if CLAY.search(ev) else "hard")


class Elo:
    def __init__(self, d=None):
        d = d or {}
        self.R = d.get("R", {}); self.N = d.get("N", {}); self.RS = d.get("RS", {}); self.NS = d.get("NS", {})
        self.last = d.get("last", "2021-12-31")

    @staticmethod
    def k(n):
        return 250 / (n + 5) ** 0.4

    def prob(self, a, b, s):
        """a'nın kazanma olasılığı (kalibre)."""
        pa = 1 / (1 + 10 ** ((self.R.get(b, 1500) - self.R.get(a, 1500)) / 400))
        ps = 1 / (1 + 10 ** ((self.RS.get(f"{b}|{s}", 1500) - self.RS.get(f"{a}|{s}", 1500)) / 400))
        p = min(max((1 - W_SURF) * pa + W_SURF * ps, 1e-4), 1 - 1e-4)
        z = math.log(p / (1 - p)) * CAL_B
        return 1 / (1 + math.exp(-z))

    def update(self, w, l, s):
        for R, N, kw, kl in ((self.R, self.N, w, l), (self.RS, self.NS, f"{w}|{s}", f"{l}|{s}")):
            rw, rl = R.get(kw, 1500.0), R.get(kl, 1500.0); e = 1 / (1 + 10 ** ((rl - rw) / 400))
            R[kw] = round(rw + self.k(N.get(kw, 0)) * (1 - e), 2); R[kl] = round(rl - self.k(N.get(kl, 0)) * (1 - e), 2)
            N[kw] = N.get(kw, 0) + 1; N[kl] = N.get(kl, 0) + 1

    def dump(self):
        return dict(last=self.last, R=self.R, N=self.N, RS=self.RS, NS=self.NS)


def tennis_day(tour, d):
    """O günün tekler maçları: (bitenler, oynanacaklar)."""
    j = get(f"tennis/{tour}/scoreboard?dates={d:%Y%m%d}") or {}
    fin, pre = [], []
    for e in j.get("events", []):
        for gr in e.get("groupings", []):
            if "Singles" not in gr["grouping"]["displayName"]:
                continue
            for c in gr["competitions"]:
                ps = c.get("competitors", [])
                if len(ps) != 2:
                    continue
                names = [(p.get("athlete") or {}).get("displayName") for p in ps]
                if not all(names):
                    continue
                st = c["status"]["type"]
                base = dict(cid=c["id"], event=e["name"], date=(c.get("date") or "")[:10], rnd=(c.get("round") or {}).get("displayName", ""),
                            ko=(c.get("date") or e["date"]).replace("Z", "+00:00"), names=names,
                            note=" ".join(n.get("text", "") for n in c.get("notes", [])).lower())
                if st["name"] == "STATUS_FINAL" and any(p.get("winner") for p in ps):
                    w = 0 if ps[0].get("winner") else 1
                    fin.append(dict(base, w=names[w], l=names[1 - w], sets=[(a.get("value"), b.get("value")) for a, b in
                                                                            zip(ps[w].get("linescores", []), ps[1 - w].get("linescores", []))]))
                elif st["state"] == "pre":
                    pre.append(base)
    return fin, pre


def load_elo():
    for p in (os.path.join(os.environ.get("FD_DIR", ""), "tennis_elo.json"), SEED):
        try:
            return Elo(json.load(open(p)))
        except Exception:
            continue
    return Elo()


def tennis(now):
    elo = load_elo()
    last = date.fromisoformat(elo.last); today = now.date()
    upd = [last + timedelta(days=i) for i in range(1, (today - last).days + 1)]
    days = sorted(set(upd) | {today - timedelta(days=1), today})  # dün ve bugün her zaman: karne için sonuçlar
    with ThreadPoolExecutor(8) as ex:
        hist = list(ex.map(lambda t: (t, tennis_day(*t)), [(tr, d) for d in days for tr in ("atp", "wta")]))
    seen = set(); results = []
    for (tr, d), (fin, _) in sorted(hist, key=lambda x: x[0][1]):
        for m in fin:
            if m["cid"] in seen or (m["date"] and m["date"] != f"{d:%Y-%m-%d}"):
                continue
            seen.add(m["cid"])
            if "w/o" in m["note"] or "walkover" in m["note"]:
                continue
            results.append(dict(id=f"T-{m['cid']}", res_w=m["w"], date=m["date"]))
            if d > last and d < today and "ret" not in m["note"]:
                elo.update(m["w"], m["l"], surface(m["event"]))
    if upd:
        elo.last = str(max(last, today - timedelta(days=1)))
    try:
        fd = os.environ.get("FD_DIR")
        if fd:
            os.makedirs(fd, exist_ok=True); json.dump(elo.dump(), open(os.path.join(fd, "tennis_elo.json"), "w"))
    except Exception:
        pass
    games = []; gseen = set()
    for d in (today, today + timedelta(days=1)):
        for tr in ("atp", "wta"):
            _, pre = tennis_day(tr, d)
            for m in pre:
                if m["cid"] in gseen:
                    continue
                gseen.add(m["cid"])
                a, b = m["names"]
                if datetime.fromisoformat(m["ko"]) < now:
                    continue
                s = surface(m["event"]); pa = elo.prob(a, b, s)
                known = elo.N.get(a, 0) >= MIN_N and elo.N.get(b, 0) >= MIN_N
                fav, pr = (a, pa) if pa >= .5 else (b, 1 - pa)
                pick = None
                if known and pr >= .70:
                    pick = dict(label=f"{fav} kazanır", winner=fav, prob=pr, tier=3 if pr >= .80 else 2, minOdds=1.03 / pr)
                games.append(dict(id=f"T-{m['cid']}", sport="tenis", lg=tr.upper(), lgName=f"{tr.upper()} · {m['event']}", ko=m["ko"],
                                  home=a, away=b, state="pre", p={"1": pa, "2": 1 - pa}, pick=pick, known=known,
                                  info=f"{a} %{round(pa*100)} – {b} %{round((1-pa)*100)} · {dict(hard='sert', clay='toprak', grass='çim')[s]} kort"
                                       + ("" if known else " · az maç verisi, öneri yok")))
    return games, results


def scan(outpath, now=None):
    now = now or datetime.now(timezone.utc)
    days = [(now + timedelta(days=i)).date() for i in (-1, 0, 1)]
    games, results = [], []
    try:
        g, r = nhl(days); games += g; results += r
    except Exception as e:
        print("NHL alınamadı:", e)
    try:
        g, r = tennis(now); games += g; results += r
    except Exception as e:
        print("tenis alınamadı:", e)
    games = [g for g in games if datetime.fromisoformat(g["ko"]) > now]
    games.sort(key=lambda g: g["ko"])
    json.dump(dict(generated=now.isoformat(), games=games, results=results), open(outpath, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"Diğer sporlar: {sum(1 for g in games if g['sport']=='hokey')} hokey, {sum(1 for g in games if g['sport']=='tenis')} tenis maçı; "
          f"{sum(1 for g in games if g.get('pick'))} seçim")
    return games


if __name__ == "__main__":
    scan(sys.argv[1])
