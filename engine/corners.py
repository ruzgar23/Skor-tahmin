"""Korner ve kart modeli (ülke bazlı, zamana ağırlıklı, takım saldırı/savunma etkili log-lineer Poisson).
Toplam dağılımı aşırı yayılımı hesaba katmak için negatif binom ile çıkarılır."""
import csv, glob, io, math, os
from datetime import datetime
import numpy as np
from scipy.optimize import minimize
from scipy.stats import nbinom, poisson
import engine as E

STATS = {"corners": ("HC", "AC"), "cards": ("HY", "AY", "HR", "AR")}


def load(dirpath):
    out = []
    for path in sorted(glob.glob(os.path.join(dirpath, "2*.csv"))):
        season = os.path.basename(path)[:4]
        for r in E.read_rows(path):
            if not r.get("FTHG") or not r.get("HomeTeam"):
                continue
            d = E.pdate(r["Date"])
            if not d:
                continue
            f = lambda k: E.fnum(r.get(k))
            hc, ac = f("HC"), f("AC")
            hy, ay, hr, ar = f("HY"), f("AY"), f("HR"), f("AR")
            out.append(dict(lg=r["Div"], season=season, date=d, home=r["HomeTeam"].strip(), away=r["AwayTeam"].strip(),
                            hc=hc, ac=ac,
                            hk=(hy + hr) if hy is not None and hr is not None else None,
                            ak=(ay + ar) if ay is not None and ar is not None else None,
                            ref=(r.get("Referee") or "").strip() or None))
    out.sort(key=lambda m: m["date"])
    return out


class StatModel:
    """y_ev = exp(mu[lig] + ev[lig] + a[ev] - d[dep]),  y_dep = exp(mu[lig] + a[dep] - d[ev])"""

    def __init__(self, country, rows, asof, kind, xi=0.004, lam=8.0):
        hk, ak = ("hc", "ac") if kind == "corners" else ("hk", "ak")
        ms = [m for m in rows if E.LEAGUE_COUNTRY.get(m["lg"]) == country and m["date"] < asof
              and (asof - m["date"]).days < 800 and m[hk] is not None and m[ak] is not None]
        self.ok = len(ms) >= 150
        if not self.ok:
            return
        teams = sorted({m["home"] for m in ms} | {m["away"] for m in ms}); leagues = E.COUNTRIES[country]
        self.ti = {t: i for i, t in enumerate(teams)}; self.li = {l: i for i, l in enumerate(leagues)}
        T, L = len(teams), len(leagues); self.T, self.L = T, L
        h = np.array([self.ti[m["home"]] for m in ms]); a = np.array([self.ti[m["away"]] for m in ms])
        lg = np.array([self.li[m["lg"]] for m in ms])
        w = np.exp(-xi * np.array([(asof - m["date"]).days for m in ms], float))
        yh = np.array([m[hk] for m in ms]); ya = np.array([m[ak] for m in ms])

        def f(x):
            att, de = x[:T], x[T:2 * T]; mu, hl = x[2 * T:2 * T + L], x[2 * T + L:]
            eh = mu[lg] + hl[lg] + att[h] - de[a]; ea = mu[lg] + att[a] - de[h]
            lh, la = np.exp(eh), np.exp(ea)
            nll = np.sum(w * (lh - yh * eh)) + np.sum(w * (la - ya * ea)) + lam * (att @ att + de @ de)
            gh, ga = w * (lh - yh), w * (la - ya); g = np.zeros_like(x)
            g[:T] = np.bincount(h, gh, T) + np.bincount(a, ga, T) + 2 * lam * att
            g[T:2 * T] = -np.bincount(a, gh, T) - np.bincount(h, ga, T) + 2 * lam * de
            g[2 * T:2 * T + L] = np.bincount(lg, gh, L) + np.bincount(lg, ga, L)
            g[2 * T + L:] = np.bincount(lg, gh, L)
            return nll, g
        x0 = np.zeros(2 * T + 2 * L); x0[2 * T:2 * T + L] = math.log(max(np.mean(np.r_[yh, ya]), 0.5))
        self.x = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500}).x
        # aşırı yayılım: toplamın varyansı / ortalaması (ağırlıklı, artıklardan)
        lh = np.exp(self.x[2 * T + L:][lg] + self.x[2 * T:2 * T + L][lg] + self.x[:T][h] - self.x[T:2 * T][a])
        la = np.exp(self.x[2 * T:2 * T + L][lg] + self.x[:T][a] - self.x[T:2 * T][h])
        tot, mu_t = yh + ya, lh + la
        self.disp = float(max(np.sum(w * (tot - mu_t) ** 2) / np.sum(w * mu_t), 1.0))

    def means(self, home, away, lg):
        T, L = self.T, self.L; li = self.li[lg]
        mu, hl = self.x[2 * T + li], self.x[2 * T + L + li]
        g = lambda t, k: self.x[k * T + self.ti[t]] if t in self.ti else 0.0
        return math.exp(mu + hl + g(home, 0) - g(away, 1)), math.exp(mu + g(away, 0) - g(home, 1))


def over_prob(mean, line, disp):
    """P(toplam > line). disp > 1 ise negatif binom (varyans = disp * ortalama)."""
    k = math.floor(line)
    if disp <= 1.02:
        return float(1 - poisson.cdf(k, mean))
    p = 1 / disp; r = mean * p / (1 - p)
    return float(1 - nbinom.cdf(k, r, p))


# --- tarama için yardımcılar ---
LINES = {"corners": (8.5, 9.5, 10.5, 11.5), "cards": (3.5, 4.5, 5.5)}
SHRINK = 0.8  # testte en iyi kalibrasyon


def base_rates(rows, asof):
    """Ülke bazında son ~2 sezonda çizgilerin üstüne çıkma oranı."""
    out = {}
    for c in E.COUNTRIES:
        rs = [m for m in rows if E.LEAGUE_COUNTRY.get(m["lg"]) == c and m["date"] < asof and (asof - m["date"]).days < 800]
        d = {}
        for kind, (hk, ak) in (("corners", ("hc", "ac")), ("cards", ("hk", "ak"))):
            t = [m[hk] + m[ak] for m in rs if m[hk] is not None and m[ak] is not None]
            if len(t) >= 150:
                d[kind] = {str(l): min(max(sum(x > l for x in t) / len(t), 0.03), 0.97) for l in LINES[kind]}
        out[c] = d
    return out


def referee_factors(rows, smodels, asof, k=15.0):
    out = {}
    for c, (_, km) in smodels.items():
        if not km.ok:
            continue
        acc = {}
        for m in rows:
            if E.LEAGUE_COUNTRY.get(m["lg"]) != c or not m["ref"] or m["hk"] is None or m["date"] >= asof or (asof - m["date"]).days >= 800:
                continue
            if m["home"] not in km.ti or m["away"] not in km.ti:
                continue
            a, b = km.means(m["home"], m["away"], m["lg"]); s = acc.setdefault(m["ref"], [0.0, 0.0])
            s[0] += m["hk"] + m["ak"]; s[1] += a + b
        for r, (y, p) in acc.items():
            out[(c, r)] = (y + k * 4.3) / (p + k * 4.3)
    return out


def _shrink(p, base):
    lg = lambda x: math.log(x / (1 - x))
    p = min(max(p, 1e-4), 1 - 1e-4)
    return 1 / (1 + math.exp(-(lg(base) + SHRINK * (lg(p) - lg(base)))))


def predict_match(cm, km, base, refs, home, away, lg, ref=None):
    out = {}
    c = E.LEAGUE_COUNTRY[lg]
    for kind, mod in (("corners", cm), ("cards", km)):
        if not mod.ok or kind not in base:
            continue
        a, b = mod.means(home, away, lg)
        f = refs.get((c, ref), 1.0) if (kind == "cards" and ref) else 1.0
        mu = (a + b) * f
        out[kind] = dict(mean=round(mu, 2), home=round(a * f, 2), away=round(b * f, 2),
                         over={str(l): round(_shrink(over_prob(mu, l, mod.disp), base[kind][str(l)]), 4) for l in LINES[kind]},
                         base={str(l): round(base[kind][str(l)], 4) for l in LINES[kind]},
                         ref=bool(f != 1.0))
    return out
