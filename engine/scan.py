"""Tarama: verileri indirir, ülke modellerini fit eder, fikstürdeki tüm maçları tahmin eder
ve data.json yazar.  Kullanım:  python3 scan.py <veri_klasörü> <çıktı.json>"""
import sys, json, math, csv, io, os
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from scipy.optimize import minimize
import engine as E
import espn

P = dict(E.DEFAULT, xi=0.004, lam=6.0, lam_h=60.0, xg_w=0.5, rho=-0.06)
RHO = P["rho"]


def fit_to_market(lh0, la0, mk, total0):
    """Piyasanın adil MS ve 2,5 üst olasılıklarını en iyi veren gol beklentileri."""
    def loss(v):
        lh, la = math.exp(v[0]), math.exp(v[1])
        m = E.markets(E.score_matrix(lh, la, RHO))
        l = (m["1"] - mk["1"]) ** 2 + (m["2"] - mk["2"]) ** 2
        if mk.get("O25") is not None:
            l += (m["O25"] - mk["O25"]) ** 2
        elif mk.get("OL") is not None:
            line, po = mk["OL"]
            M = E.score_matrix(lh, la, RHO); n = M.shape[0]
            pov = sum(M[i, j] for i in range(n) for j in range(n) if i + j > line)
            l += (pov - po) ** 2
        else:
            l += 0.02 * (lh + la - total0) ** 2
        return l
    r = minimize(loss, [math.log(lh0), math.log(la0)], method="Nelder-Mead",
                 options={"xatol": 1e-4, "fatol": 1e-9, "maxiter": 400})
    return math.exp(r.x[0]), math.exp(r.x[1])


def full_probs(lh, la, htr):
    M = E.score_matrix(lh, la, RHO)
    p = E.markets(M)
    p.update({"1X": p["1"] + p["X"], "12": p["1"] + p["2"], "X2": p["X"] + p["2"]})
    H = E.score_matrix(lh * htr, la * htr, 0)
    h = E.markets(H)
    p.update({"HT1": h["1"], "HTX": h["X"], "HT2": h["2"], "HTO05": 1 - H[0, 0], "HTO15": h["O15"]})
    cells = sorted(((M[i, j], i, j) for i in range(8) for j in range(8)), reverse=True)[:8]
    return p, M, [[i, j, round(float(v), 4)] for v, i, j in cells]


def team_context(matches, season="2627"):
    ctx = {}
    by_lg = {}
    for m in matches:
        if m["season"] != season:
            continue
        for side in ("home", "away"):
            t = m[side]; ha = "E" if side == "home" else "D"
            gf, ga = (m["hg"], m["ag"]) if side == "home" else (m["ag"], m["hg"])
            xf, xa = (m["hxg"], m["axg"]) if side == "home" else (m["axg"], m["hxg"])
            c = ctx.setdefault(m["lg"] + "|" + t, dict(name=t, lg=m["lg"], pld=0, w=0, d=0, l=0, gf=0, ga=0,
                               xgf=0.0, xga=0.0, xn=0, H=[0, 0, 0], A=[0, 0, 0], games=[]))
            c["pld"] += 1; c["gf"] += gf; c["ga"] += ga
            r = "G" if gf > ga else ("B" if gf == ga else "M")
            c["w"] += r == "G"; c["d"] += r == "B"; c["l"] += r == "M"
            if xf is not None:
                c["xgf"] += xf; c["xga"] += xa; c["xn"] += 1
            s = c["H"] if side == "home" else c["A"]
            s[0] += 1; s[1] += gf; s[2] += ga
            c["games"].append(dict(d=m["date"].isoformat(), opp=m["away"] if side == "home" else m["home"],
                                   ha=ha, gf=gf, ga=ga, r=r, xf=xf, xa=xa))
    # puan durumu sırası
    for k, c in ctx.items():
        by_lg.setdefault(c["lg"], []).append(c)
    for lg, cs in by_lg.items():
        cs.sort(key=lambda c: (-(3 * c["w"] + c["d"]), -(c["gf"] - c["ga"]), -c["gf"]))
        for i, c in enumerate(cs):
            c["pos"] = i + 1; c["of"] = len(cs)
    out = {}
    for k, c in ctx.items():
        out[k] = dict(name=c["name"], lg=c["lg"], pos=c["pos"], of=c["of"], pld=c["pld"],
                      pts=3 * c["w"] + c["d"], w=c["w"], d=c["d"], l=c["l"], gf=c["gf"], ga=c["ga"],
                      xgf=round(c["xgf"] / c["xn"], 2) if c["xn"] else None,
                      xga=round(c["xga"] / c["xn"], 2) if c["xn"] else None,
                      H=c["H"], A=c["A"], last=c["games"][-6:][::-1])
    return out


def to_istanbul(d, t):
    try:
        hh, mm = map(int, (t or "00:00").split(":"))
        dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo("Europe/London"))
        return dt.astimezone(ZoneInfo("Europe/Istanbul"))
    except Exception:
        return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo("Europe/Istanbul"))


# Avrupa kupaları için ülke gücü (log ölçekte, İngiltere = 0). Yaklaşık; UEFA ülke sıralamasından.
COUNTRY_STR = {"ENG": 0.0, "ESP": -0.04, "ITA": -0.05, "GER": -0.06, "FRA": -0.14, "POR": -0.22,
               "NED": -0.25, "TUR": -0.30, "GRE": -0.38, "SCO": -0.42}
UNKNOWN_CUP = (-0.45, -0.45)  # veri setimizde olmayan ülkelerin kulüpleri


def cup_lambdas(models, home, hlg, away, alg):
    def strength(t, lg):
        if not lg:
            return UNKNOWN_CUP[0], UNKNOWN_CUP[1], False
        c = E.LEAGUE_COUNTRY[lg]; mod = models[c]
        if mod.x is None:
            return UNKNOWN_CUP[0], UNKNOWN_CUP[1], False
        a, d, _, ok = mod.team(t)
        s = COUNTRY_STR.get(c, -0.4)
        return a + s, d + s, ok
    ah, dh, kh = strength(home, hlg); aa, da, ka = strength(away, alg)
    base = math.log(1.32)
    return math.exp(base + 0.12 + ah - da), math.exp(base + aa - dh), (kh, ka)


HIST_P = ("1", "X", "2", "1X", "12", "X2", "O15", "O25", "O35", "BTTS", "HT1", "HTX", "HT2", "HTO05", "HTO15")


def slim(m):
    return dict(id=m["id"], lg=m["lg"], lgName=m["lgName"], ko=m["ko"], home=m["home"], away=m["away"],
                cup=m.get("cup", False), src=m["src"], book=m.get("book"), known=m["known"],
                p={k: m["p"][k] for k in HIST_P if k in m["p"]}, top=m["top"][0])


def update_history(hist, snapshots, results_pool, now, force=False):
    """snapshots: [(üretilme zamanı, maç listesi)] eskiden yeniye. Maç başlamadan önceki son tahmin saklanır."""
    for gen, ms in snapshots:
        for m in ms:
            ko = datetime.fromisoformat(m["ko"])
            if force or ko > gen:
                old = hist.get(m["id"])
                if old and "res" in old:
                    continue
                hist[m["id"]] = slim(m)
    idx = {}
    for r in results_pool:
        idx.setdefault((r["lg"], r["home"], r["away"]), []).append(r)
    settled = 0
    for h in hist.values():
        ko = datetime.fromisoformat(h["ko"])
        if ko > now - timedelta(hours=2) or (h.get("res") and h.get("ht")):
            continue
        for r in idx.get((h["lg"], h["home"], h["away"]), []):
            if abs((r["date"] - ko.astimezone(timezone.utc).date()).days) <= 1:
                if not h.get("res"):
                    settled += 1
                h["res"] = [r["hg"], r["ag"]]
                if r.get("hthg") is not None:
                    h["ht"] = [int(r["hthg"]), int(r["htag"])]
                break
    cutoff = now - timedelta(days=70)
    for k in [k for k, h in hist.items() if datetime.fromisoformat(h["ko"]) < cutoff]:
        del hist[k]
    return settled


def main(datadir, outpath, skip_download=False, prev=None, histpath=None, seed=None):
    if not skip_download:
        E.download(datadir)
    matches = E.load_matches(datadir)
    now = datetime.now(timezone.utc)
    # football-data'ya henüz girmemiş son sonuçları ESPN'den ekle (xG ve oran olmadan)
    names0 = {}
    for m in matches:
        if m["season"] == E.SEASONS[-1]:
            names0.setdefault(m["lg"], set()).update([m["home"], m["away"]])
    last_fd = {}
    for m in matches:
        last_fd[m["lg"]] = max(last_fd.get(m["lg"], m["date"]), m["date"])
    since = min(last_fd.values()) - timedelta(days=1) if last_fd else now.date() - timedelta(days=10)
    have = {(m["lg"], m["home"], m["away"], m["date"]) for m in matches}
    added = 0
    cup_results = []
    try:
        for r in espn.results(names0, min(since, now.date() - timedelta(days=9)), now):
            if r["lg"] in espn.CUPS:
                cup_results.append(r); continue
            if r["date"] < since:
                continue
            if any((r["lg"], r["home"], r["away"], r["date"] + timedelta(days=dd)) in have for dd in (-1, 0, 1)):
                continue
            matches.append(dict(lg=r["lg"], season=E.SEASONS[-1], date=r["date"], home=r["home"], away=r["away"],
                                hg=r["hg"], ag=r["ag"], hthg=None, htag=None, hxg=None, axg=None, odds=None, codds=None))
            added += 1
    except Exception as e:
        print("ESPN sonuçları eklenemedi:", e)
    matches.sort(key=lambda m: m["date"])
    print(f"ESPN'den {added} yeni sonuç eklendi")
    today = now.astimezone(ZoneInfo("Europe/Istanbul")).date()
    models = {c: E.CountryModel(c, matches, today, P) for c in E.COUNTRIES}
    ctx = team_context(matches)

    # football-data fikstürü (test edilmiş ortalama oranlar burada)
    fdx = {}
    for r in E.read_rows(os.path.join(datadir, "fixtures.csv")):
        d = E.pdate(r.get("Date", ""))
        if d and r.get("Div") in E.LEAGUE_NAMES and r.get("HomeTeam"):
            fdx[(r["Div"], r["HomeTeam"].strip(), r["AwayTeam"].strip())] = dict(
                ko=to_istanbul(d, r.get("Time")), avg=E.odds(r, "Avg"), b365=E.odds(r, "B365"), ref=r.get("Referee") or None)

    # ESPN fikstürü (önümüzdeki 8 gün)
    names = {}
    for m in matches:
        if m["season"] == E.SEASONS[-1]:
            names.setdefault(m["lg"], set()).update([m["home"], m["away"]])
    try:
        efx, unmatched = espn.fixtures(names, now=now)
    except Exception as e:
        print("ESPN kullanılamadı:", e); efx, unmatched = [], []
    if unmatched:
        print("Eşleşmeyen takım adları:", unmatched)

    items = {}
    for f in efx:
        key = (f["lg"], f["home"], f["away"])
        items[key] = dict(lg=f["lg"], home=f["home"], away=f["away"], ko=f["ko"].astimezone(ZoneInfo("Europe/Istanbul")),
                          known_names=f["known"], espn=f["odds"], fd=fdx.get(key), hlg=f.get("hlg"), alg=f.get("alg"))
    for key, v in fdx.items():  # ESPN'de olmayan ama football-data'da olan gelecek maçlar
        if key not in items:
            items[key] = dict(lg=key[0], home=key[1], away=key[2], ko=v["ko"], known_names=(True, True), espn=None, fd=v)

    out, teams_needed = [], set()
    for it in items.values():
        if it["ko"] <= now:  # başlamış / oynanmış maçlar listelenmez
            continue
        lg = it["lg"]; home, away = it["home"], it["away"]
        cup = lg in espn.CUPS
        if cup:
            lhm, lam_, kk = cup_lambdas(models, home, it["hlg"], away, it["alg"])
            htr = 0.44
        else:
            mod = models[E.LEAGUE_COUNTRY[lg]]
            if mod.x is None:
                continue
            lhm, lam_ = mod.lambdas(home, away, lg)
            htr = mod.htr.get(lg, 0.44)
            kk = (home in mod.ti, away in mod.ti)
        pm = E.markets(E.score_matrix(lhm, lam_, RHO))
        fd = it["fd"] or {}; eo = it["espn"]
        mk, book, avg = None, None, None
        if fd.get("avg"):
            avg = fd["avg"]; mk = E.fair(avg, "1X2"); book = "Piyasa ortalaması"
            if avg["O25"] and avg["U25"]:
                mk.update(E.fair(avg, ["O25", "U25"]))
        elif eo:
            avg = {"1": eo["1"], "X": eo["X"], "2": eo["2"], "O25": None, "U25": None}
            mk = E.fair(avg, "1X2"); book = eo.get("book") or "DraftKings"
            if eo.get("line") is not None and eo.get("over") and eo.get("under"):
                po = (1 / eo["over"]) / (1 / eo["over"] + 1 / eo["under"])
                if abs(eo["line"] - 2.5) < 1e-6:
                    mk.update(O25=po, U25=1 - po); avg.update(O25=eo["over"], U25=eo["under"])
                else:
                    mk["OL"] = (eo["line"], po)
        lh, la = lhm, lam_
        if mk:
            lh, la = fit_to_market(lhm, lam_, mk, lhm + lam_)
        p, M, top = full_probs(lh, la, htr)
        known = (kk[0] and it["known_names"][0], kk[1] and it["known_names"][1])
        hlg = it.get("hlg") if cup else lg; alg = it.get("alg") if cup else lg
        mk_out = {k: round(v, 4) for k, v in mk.items() if k != "OL"} if mk else None
        out.append(dict(
            id=f"{lg}-{it['ko']:%Y-%m-%d}-{home}-{away}".replace(" ", "_"),
            lg=lg, lgName=(espn.CUP_NAMES[lg] if cup else E.LEAGUE_NAMES[lg]), ko=it["ko"].isoformat(), home=home, away=away,
            cup=cup, hlg=hlg, alg=alg,
            src="piyasa" if mk else "model", book=book, lam=[round(lh, 3), round(la, 3)], lamM=[round(lhm, 3), round(lam_, 3)],
            p={k: round(float(v), 4) for k, v in p.items()},
            pm={k: round(float(pm[k]), 4) for k in ("1", "X", "2", "O25", "BTTS")},
            mk=mk_out, odds=dict(avg=avg, b365=fd.get("b365")),
            M=[[round(float(M[i, j]), 4) for j in range(6)] for i in range(6)], top=top,
            known=known, ref=fd.get("ref"),
        ))
        teams_needed.update([f"{hlg}|{home}", f"{alg}|{away}"])
    out.sort(key=lambda m: (m["ko"], m["lg"]))
    # tahmin geçmişi ve sonuçlar
    if histpath:
        hist = {}
        if os.path.exists(histpath):
            try:
                hist = {h["id"]: h for h in json.load(open(histpath)).get("matches", [])}
            except Exception as e:
                print("history.json okunamadı:", e)
        snaps = []
        for path, force in ([(seed, True)] if seed else []) + ([(prev, False)] if prev else []):
            if path and os.path.exists(path):
                try:
                    pd = json.load(open(path))
                    snaps.append((datetime.fromisoformat(pd["generated"]), pd.get("matches", []), force))
                except Exception as e:
                    print("önceki tarama okunamadı:", e)
        for gen, ms_, force in snaps:
            update_history(hist, [(gen, ms_)], [], now, force=force)
        pool = [dict(lg=m["lg"], home=m["home"], away=m["away"], date=m["date"], hg=m["hg"], ag=m["ag"],
                     hthg=m["hthg"], htag=m["htag"]) for m in matches if m["season"] == E.SEASONS[-1]] + cup_results
        n_set = update_history(hist, [(now, out)], pool, now)
        json.dump(dict(updated=now.isoformat(), matches=sorted(hist.values(), key=lambda h: h["ko"])),
                  open(histpath, "w"), ensure_ascii=False, separators=(",", ":"))
        print(f"Geçmiş: {len(hist)} tahmin, bu taramada {n_set} maç sonuçlandı")
    last_result = max((m["date"] for m in matches), default=None)
    data = dict(generated=now.isoformat(), resultsUpTo=last_result.isoformat() if last_result else None,
                fixtures=dict(start=out[0]["ko"][:10] if out else None, end=out[-1]["ko"][:10] if out else None),
                params=P, leagues={**E.LEAGUE_NAMES, **espn.CUP_NAMES}, matches=out,
                teams={k: v for k, v in ctx.items() if k in teams_needed})
    json.dump(data, open(outpath, "w"), ensure_ascii=False, separators=(",", ":"), default=float)
    from collections import Counter
    print(f"{len(out)} maç yazıldı; kaynak: {dict(Counter(m['book'] or 'model' for m in out))}; "
          f"sonuçlar {data['resultsUpTo']} tarihine kadar; fikstür {data['fixtures']}")


if __name__ == "__main__":
    a = sys.argv
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    main(a[1], a[2], skip_download="--no-download" in a, prev=opt("--prev"), histpath=opt("--history"), seed=opt("--seed"))
