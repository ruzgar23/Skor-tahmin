"""Skor Tahmin Masası - maç bazlı model motoru.

Model (ülke bazlı ortak fit, alt ligler dahil):
  log λ_ev  = mu[lig] + ev[lig] + evTakım[ev] + hücum[ev] - savunma[dep]
  log λ_dep = mu[lig] + hücum[dep] - savunma[ev]
Maçlar zamanla üstel azalan ağırlık alır (exp(-xi * gün)).
Hedef değer: gol, ya da xG olan maçlarda (1-w)*gol + w*xG.
Tahminde düşük skorlar için Dixon-Coles düzeltmesi (rho) uygulanır.
"""
import csv, io, math, glob, os, urllib.request
from datetime import datetime, date
import numpy as np
from scipy.optimize import minimize

BASE = "https://football-data.co.uk"
COUNTRIES = {
    "ENG": ["E0", "E1", "E2", "E3"], "ESP": ["SP1", "SP2"], "ITA": ["I1", "I2"],
    "GER": ["D1", "D2"], "FRA": ["F1", "F2"], "TUR": ["T1"], "NED": ["N1"],
    "POR": ["P1"], "SCO": ["SC0", "SC1", "SC2", "SC3"], "GRE": ["G1"],
}
LEAGUE_NAMES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "SP1": "La Liga", "SP2": "La Liga 2", "I1": "Serie A", "I2": "Serie B",
    "D1": "Bundesliga", "D2": "2. Bundesliga", "F1": "Ligue 1", "F2": "Ligue 2",
    "T1": "Süper Lig", "N1": "Eredivisie", "P1": "Primeira Liga",
    "SC0": "İskoçya Premiership", "SC1": "İskoçya Championship", "SC2": "İskoçya League One",
    "SC3": "İskoçya League Two", "G1": "Yunanistan Süper Lig",
}
LEAGUE_COUNTRY = {l: c for c, ls in COUNTRIES.items() for l in ls}
SEASONS = ["2324", "2425", "2526", "2627"]
DEFAULT = dict(xi=0.0025, lam=2.0, lam_h=20.0, xg_w=0.5, rho=-0.06)


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pdate(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def download(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    got = []
    for s in SEASONS:
        for ls in COUNTRIES.values():
            for l in ls:
                p = os.path.join(dirpath, f"{s}-{l}.csv")
                # geçmiş sezonları bir kez indir; bu sezonu her seferinde tazele
                if os.path.exists(p) and s != SEASONS[-1]:
                    continue
                try:
                    urllib.request.urlretrieve(f"{BASE}/mmz4281/{s}/{l}.csv", p); got.append(p)
                except Exception as e:
                    print("indirilemedi", s, l, e)
    urllib.request.urlretrieve(f"{BASE}/fixtures.csv", os.path.join(dirpath, "fixtures.csv"))
    return got


def read_rows(path):
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        return list(csv.DictReader(fh))


def odds(r, prefix):
    """Ortalama piyasa oranları. prefix 'Avg' (maç öncesi) ya da 'AvgC' (kapanış)."""
    o = {"1": fnum(r.get(prefix + "H")), "X": fnum(r.get(prefix + "D")), "2": fnum(r.get(prefix + "A")),
         "O25": fnum(r.get(prefix + ">2.5")), "U25": fnum(r.get(prefix + "<2.5"))}
    for k in list(o):
        if o[k] is not None and o[k] <= 1.0:
            o[k] = None
    return o if (o["1"] and o["X"] and o["2"]) else None


def load_matches(dirpath):
    out = []
    for path in sorted(glob.glob(os.path.join(dirpath, "2*.csv"))):
        season = os.path.basename(path)[:4]
        for r in read_rows(path):
            if not r.get("FTHG") or not r.get("HomeTeam"):
                continue
            d = pdate(r["Date"])
            if not d:
                continue
            out.append(dict(
                lg=r["Div"], season=season, date=d, home=r["HomeTeam"].strip(), away=r["AwayTeam"].strip(),
                hg=int(float(r["FTHG"])), ag=int(float(r["FTAG"])),
                hthg=fnum(r.get("HTHG")), htag=fnum(r.get("HTAG")),
                hxg=fnum(r.get("HxG")), axg=fnum(r.get("AxG")),
                odds=odds(r, "Avg"), codds=odds(r, "AvgC"),
            ))
    out.sort(key=lambda m: m["date"])
    return out


class CountryModel:
    def __init__(self, country, matches, asof, p=DEFAULT):
        self.country, self.asof, self.p = country, asof, p
        ms = [m for m in matches if LEAGUE_COUNTRY.get(m["lg"]) == country and m["date"] < asof
              and (asof - m["date"]).days < 1100]
        self.n = len(ms)
        teams = sorted({m["home"] for m in ms} | {m["away"] for m in ms})
        leagues = COUNTRIES[country]
        self.ti = {t: i for i, t in enumerate(teams)}
        self.li = {l: i for i, l in enumerate(leagues)}
        T, L = len(teams), len(leagues)
        self.T, self.L = T, L
        if not ms:
            self.x = None
            return
        h = np.array([self.ti[m["home"]] for m in ms]); a = np.array([self.ti[m["away"]] for m in ms])
        lg = np.array([self.li[m["lg"]] for m in ms])
        days = np.array([(asof - m["date"]).days for m in ms], float)
        w = np.exp(-p["xi"] * days)
        def target(g, xg):
            return g if xg is None else (1 - p["xg_w"]) * g + p["xg_w"] * xg
        yh = np.array([target(m["hg"], m["hxg"]) for m in ms]); ya = np.array([target(m["ag"], m["axg"]) for m in ms])
        lam, lam_h = p["lam"], p["lam_h"]
        # Alt ligi veri setinde olmayan ülkelerde, sonradan katılan (yükselen) takımların
        # başlangıç beklentisi ortalamanın biraz altı.
        c = np.zeros(T)
        if len(leagues) == 1:
            first = {}
            for m in ms:
                for t in (m["home"], m["away"]):
                    first.setdefault(t, m["date"])
            d0 = ms[0]["date"]
            for t, d in first.items():
                if (d - d0).days > 60:
                    c[self.ti[t]] = p.get("promo", -0.15)
        self.center = c

        def f(x):
            att, de, ht = x[:T], x[T:2*T], x[2*T:3*T]
            mu, hl = x[3*T:3*T+L], x[3*T+L:3*T+2*L]
            eh = mu[lg] + hl[lg] + ht[h] + att[h] - de[a]
            ea = mu[lg] + att[a] - de[h]
            lh, la = np.exp(eh), np.exp(ea)
            nll = np.sum(w * (lh - yh * eh)) + np.sum(w * (la - ya * ea))
            ac, dc = att - c, de - c
            nll += lam * (ac @ ac + dc @ dc) + lam_h * (ht @ ht)
            gh, ga = w * (lh - yh), w * (la - ya)
            g = np.zeros_like(x)
            g[:T] = np.bincount(h, gh, T) + np.bincount(a, ga, T) + 2 * lam * ac
            g[T:2*T] = -np.bincount(a, gh, T) - np.bincount(h, ga, T) + 2 * lam * dc
            g[2*T:3*T] = np.bincount(h, gh, T) + 2 * lam_h * ht
            g[3*T:3*T+L] = np.bincount(lg, gh, L) + np.bincount(lg, ga, L)
            g[3*T+L:] = np.bincount(lg, gh, L)
            return nll, g

        x0 = np.zeros(3 * T + 2 * L); x0[3*T:3*T+L] = 0.3; x0[3*T+L:] = 0.15
        res = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500})
        self.x = res.x
        # ilk yarı gol payı (lig bazlı)
        self.htr = {}
        for l in leagues:
            hm = [m for m in ms if m["lg"] == l and m["hthg"] is not None]
            ft = sum(m["hg"] + m["ag"] for m in hm)
            self.htr[l] = (sum(m["hthg"] + m["htag"] for m in hm) / ft) if ft else 0.44

    def team(self, t):
        T = self.T
        i = self.ti.get(t)
        if i is None:  # ülke verisinde hiç olmayan takım: zayıf varsay
            return -0.25, -0.25, 0.0, False
        return self.x[i], self.x[T + i], self.x[2*T + i], True

    def lambdas(self, home, away, lg, neutral=False):
        T, L = self.T, self.L
        li = self.li[lg]
        mu, hl = self.x[3*T + li], self.x[3*T + L + li]
        ah, dh, hh, _ = self.team(home); aa, da, _, _ = self.team(away)
        hadv = 0 if neutral else hl + hh
        return math.exp(mu + hadv + ah - da), math.exp(mu + aa - dh)


def score_matrix(lh, la, rho, maxg=10):
    i = np.arange(maxg + 1)
    ph = np.exp(-lh) * lh ** i / np.array([math.factorial(k) for k in i])
    pa = np.exp(-la) * la ** i / np.array([math.factorial(k) for k in i])
    M = np.outer(ph, pa)
    if rho:
        M[0, 0] *= 1 - lh * la * rho; M[0, 1] *= 1 + lh * rho
        M[1, 0] *= 1 + la * rho; M[1, 1] *= 1 - rho
    return M / M.sum()


def markets(M):
    n = M.shape[0]; I, J = np.meshgrid(range(n), range(n), indexing="ij")
    tot = I + J
    p = {"1": M[I > J].sum(), "X": M[I == J].sum(), "2": M[I < J].sum(),
         "O15": M[tot >= 2].sum(), "O25": M[tot >= 3].sum(), "O35": M[tot >= 4].sum(),
         "BTTS": M[(I > 0) & (J > 0)].sum()}
    return {k: float(v) for k, v in p.items()}


def fair(o, keys):
    s = sum(1 / o[k] for k in keys)
    return {k: (1 / o[k]) / s for k in keys}
