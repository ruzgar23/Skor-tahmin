"""Canlı analiz: o an oynanan maçları ESPN'den alır, maç öncesi gol beklentisini kalan süreye,
skora ve kırmızı kartlara göre günceller; live.json yazar.
Kullanım:  python3 live.py <data.json> <live.json>"""
import sys, json, math, re
from datetime import datetime, timedelta, timezone
import numpy as np
import engine as E
import espn

# Skor durumu ve kırmızı kart çarpanları (kalan süredeki gol hızına).
# STATE: takımın kendi bakışından gol farkı -> çarpan. calibrate_live.py ile ayarlanır.
STATE = {-2: 1.10, -1: 1.15, 0: 1.00, 1: 0.95, 2: 0.95}  # 13.598 maçlık devre arası verisinden
RED_OWN, RED_OPP = 0.67, 1.25
HT_SHARE = 0.46
RHO = -0.06


def minute_of(status):
    """(oynanan dakika, devre) — '45'+2'' gibi değerleri de okur."""
    clock = status.get("displayClock") or ""
    period = status.get("period") or 1
    m = re.match(r"(\d+)'?(?:\+(\d+))?", clock)
    if not m:
        return None, period
    base = int(m.group(1)); extra = int(m.group(2) or 0)
    if status.get("type", {}).get("name") == "STATUS_HALFTIME":
        return 45, 1
    return base + extra * 0.0, period  # uzatma dakikaları devre sonuna sayılır


def done_share(minute, period, h=HT_SHARE):
    if period <= 1:
        return h * min(minute, 45) / 45
    return h + (1 - h) * min(max(minute - 45, 0), 45) / 45


def state_mult(diff):
    return STATE[max(-2, min(2, diff))]


def inplay(lh, la, hs, as_, minute, period, rh=0, ra=0):
    rem = max(1 - done_share(minute, period), 0.0)
    mh = state_mult(hs - as_) * (RED_OWN ** rh) * (RED_OPP ** ra)
    ma = state_mult(as_ - hs) * (RED_OWN ** ra) * (RED_OPP ** rh)
    Lh, La = lh * rem * mh, la * rem * ma
    n = 9
    i = np.arange(n)
    fact = np.array([math.factorial(k) for k in i])
    ph = np.exp(-Lh) * Lh ** i / fact; pa = np.exp(-La) * La ** i / fact
    R = np.outer(ph, pa); R /= R.sum()
    I, J = np.meshgrid(i, i, indexing="ij")
    H, A = I + hs, J + as_
    tot = H + A
    p = {"1": R[H > A].sum(), "X": R[H == A].sum(), "2": R[H < A].sum()}
    p.update({"1X": p["1"] + p["X"], "X2": p["X"] + p["2"], "12": p["1"] + p["2"]})
    p["BTTS"] = R[(H > 0) & (A > 0)].sum()
    p["NOGOAL"] = R[0, 0]
    tot_lines = {}
    cur = hs + as_
    for k in range(cur, cur + 4):
        line = k + 0.5
        tot_lines[f"{line:.1f}"] = float(R[tot > line].sum())
    nxt = 1 - p["NOGOAL"]
    p["NEXT1"] = nxt * Lh / (Lh + La) if Lh + La > 0 else 0
    p["NEXT2"] = nxt * La / (Lh + La) if Lh + La > 0 else 0
    cells = sorted(((R[a, b], a + hs, b + as_) for a in range(6) for b in range(6)), reverse=True)[:5]
    return ({k: float(v) for k, v in p.items()}, tot_lines, [[int(a), int(b), round(float(v), 4)] for v, a, b in cells],
            (round(Lh, 3), round(La, 3)), rem)


def live_market(c):
    od = (c.get("odds") or [None])[0]
    if not od:
        return None
    ml = od.get("moneyline") or {}
    cur = lambda side: espn.american(((ml.get(side) or {}).get("current") or {}).get("odds"))
    o = {"1": cur("home"), "X": cur("draw"), "2": cur("away")}
    out = {}
    if all(o.values()):
        out.update(E.fair(o, "1X2")); out["odds"] = o
    tot = od.get("total") or {}
    ov = (tot.get("over") or {}).get("current") or {}
    un = (tot.get("under") or {}).get("current") or {}
    po, pu = espn.american(ov.get("odds")), espn.american(un.get("odds"))
    line = ov.get("line")
    if po and pu and line:
        try:
            ln = float(str(line).lstrip("ou"))
            out["total"] = dict(line=ln, over=(1 / po) / (1 / po + 1 / pu), oo=po, uo=pu)
        except ValueError:
            pass
    return out or None


def pre_lambdas(c, fd_lams):
    """Maç öncesi gol beklentisi: tarama verisi, yoksa ESPN kapanış oranları."""
    if fd_lams:
        return fd_lams, "tarama"
    eo = espn.parse_odds(c)
    if not eo:
        return None, None
    from scan import fit_to_market
    mk = E.fair({"1": eo["1"], "X": eo["X"], "2": eo["2"]}, "1X2")
    if eo.get("line") is not None and eo.get("over") and eo.get("under"):
        po = (1 / eo["over"]) / (1 / eo["over"] + 1 / eo["under"])
        if abs(eo["line"] - 2.5) < 1e-6:
            mk["O25"] = po
        else:
            mk["OL"] = (eo["line"], po)
    lh, la = fit_to_market(1.4, 1.1, mk, 2.6)
    return (lh, la), "kapanış oranı"


TOP = {"E0", "SP1", "I1", "D1", "F1", "T1", "N1", "P1", "UCL", "UEL", "UECL", "E1", "D2", "SP2", "I2", "F2", "SC0", "G1"}

LABELS = {"1": "MS 1", "X": "MS X", "2": "MS 2", "1X": "Çifte şans 1X", "X2": "Çifte şans X2", "12": "Çifte şans 12",
          "BTTS": "KG Var", "NBTTS": "KG Yok", "GOAL": "Kalan sürede gol olur", "NOGOAL": "Kalan sürede gol olmaz",
          "NEXT1": "Sıradaki golü ev sahibi atar", "NEXT2": "Sıradaki golü deplasman atar"}


def picks_for(p, tl, minute, mkt, cur_goals=0):
    """Canlı seçim adayları: olasılık %72–95 arası (çok kesin olanların oranı oynamaya değmez)."""
    cand = []
    for k in ("1", "X", "2", "1X", "X2", "12"):
        cand.append((k, LABELS[k], p[k]))
    cand += [("BTTS", LABELS["BTTS"], p["BTTS"]), ("NBTTS", LABELS["NBTTS"], 1 - p["BTTS"]),
             ("GOAL", LABELS["GOAL"], 1 - p["NOGOAL"]), ("NOGOAL", LABELS["NOGOAL"], p["NOGOAL"])]
    for line, po in tl.items():
        cand += [(f"O{line}", f"{line.replace('.', ',')} Üst", po), (f"U{line}", f"{line.replace('.', ',')} Alt", 1 - po)]
    out = []
    for k, label, pr in cand:
        if not (0.70 <= pr <= 0.88) or minute is None or minute < 15 or minute > 78:
            continue
        if k.startswith(("O", "U")) and abs(float(k[1:]) - (cur_goals + 0.5)) > 1.01:
            continue  # yalnızca bir sonraki iki gol çizgisi
        warn = None
        if mkt:
            if k in ("1", "X", "2") and k in mkt:
                if abs(mkt[k] - pr) > 0.08:
                    warn = f"Canlı piyasa %{round(mkt[k]*100)} diyor"
            if k.startswith(("O", "U")) and "total" in mkt and abs(mkt["total"]["line"] - float(k[1:])) < 1e-6:
                mp = mkt["total"]["over"] if k[0] == "O" else 1 - mkt["total"]["over"]
                if abs(mp - pr) > 0.08:
                    warn = f"Canlı piyasa %{round(mp*100)} diyor"
        out.append(dict(k=k, label=label, prob=round(pr, 4), minOdds=round(1.05 / pr, 2), warn=warn))
    # tekrarları azalt: çifte şans, MS seçimi varsa gereksiz; en fazla 3 aday
    out.sort(key=lambda x: (x["warn"] is not None, -x["prob"]))
    return out[:2]


def team_reds(c):
    ids = {x["homeAway"]: x["team"]["id"] if "team" in x else x.get("id") for x in c["competitors"]}
    r = {"home": 0, "away": 0}
    for d in c.get("details") or []:
        if d.get("redCard"):
            tid = (d.get("team") or {}).get("id")
            for side, i in ids.items():
                if tid is not None and str(tid) == str(i):
                    r[side] += 1
    return r["home"], r["away"]


def stats_of(x):
    s = {st["name"]: st.get("displayValue") for st in x.get("statistics", [])}
    return {k: s.get(k) for k in ("totalShots", "shotsOnTarget", "possessionPct", "wonCorners")}


def consistent(m):
    """Bizim canlı MS olasılıklarımız canlı piyasayla uyumlu mu (model aynı maçı mı görüyor)?"""
    mk = m.get("market") or {}
    if not all(k in mk for k in "1X2"):
        return False
    return max(abs(mk[k] - m["p"][k]) for k in "1X2") <= 0.06


def main(datapath, outpath, prevpath=None):
    now = datetime.now(timezone.utc)
    notified = {}
    if prevpath:
        try:
            pv = json.load(open(prevpath))
            if datetime.fromisoformat(pv["generated"]) > now - timedelta(hours=12):
                notified = pv.get("notified", {})
        except Exception:
            pass
    try:
        data = json.load(open(datapath))
    except Exception:
        data = {"matches": []}
    names, lam_idx = {}, {}
    for m in data["matches"]:
        names.setdefault(m["lg"], set()).update([m["home"], m["away"]])
        lam_idx[(m["lg"], m["home"], m["away"])] = (m["lam"][0], m["lam"][1], m.get("id"), m["p"])
    days = sorted({now.date(), (now - timedelta(hours=6)).date()})
    slugs = {**espn.SLUG, **espn.CUPS}
    espn.prefetch([(s, d) for s in slugs.values() for d in days])
    out = []
    for lg, slug in slugs.items():
        for ev in espn._events(lg, slug, days, "in"):
            c = ev["competitions"][0]
            sd = {x["homeAway"]: x for x in c["competitors"]}
            hn, an = sd["home"]["team"]["displayName"], sd["away"]["team"]["displayName"]
            try:
                hs, as_ = int(sd["home"]["score"]), int(sd["away"]["score"])
            except (KeyError, ValueError, TypeError):
                continue
            minute, period = minute_of(ev["status"])
            if minute is None:
                continue
            h = espn.match_name(hn, names.get(lg, set())) if lg in names else None
            a = espn.match_name(an, names.get(lg, set())) if lg in names else None
            hit = lam_idx.get((lg, h, a)) if h and a else None
            lams, src = pre_lambdas(c, hit[:2] if hit else None)
            if not lams:
                continue
            rh, ra = team_reds(c)
            p, tl, top, rest, rem = inplay(lams[0], lams[1], hs, as_, minute, period, rh, ra)
            mkt = live_market(c)
            lgname = espn.CUP_NAMES.get(lg) or E.LEAGUE_NAMES.get(lg, lg)
            out.append(dict(
                id=(hit[2] if hit and hit[2] else f"{lg}-{ev['id']}"), eid=ev["id"], slug=slug, lg=lg, lgName=lgname,
                home=h or hn, away=a or an, minute=minute, period=period, clock=ev["status"].get("displayClock"),
                halftime=ev["status"]["type"]["name"] == "STATUS_HALFTIME",
                score=[hs, as_], reds=[rh, ra], stats=[stats_of(sd["home"]), stats_of(sd["away"])],
                pre=dict(lam=[round(lams[0], 3), round(lams[1], 3)], src=src, p=(hit[3] if hit else None)),
                rest=rest, p={k: round(v, 4) for k, v in p.items()}, totals={k: round(v, 4) for k, v in tl.items()},
                top=top, market=mkt, picks=picks_for(p, tl, minute, mkt, hs + as_),
            ))
    out.sort(key=lambda m: (-len(m["picks"]), -m["minute"]))
    alerts = []
    for m in out:
        m["consistent"] = consistent(m)
        if not m["consistent"] or m["lg"] not in TOP:
            continue
        if any(k.startswith(m["id"] + "|") for k in notified):
            continue  # aynı maç için bir kez bildir
        for pk in m["picks"]:
            if pk["warn"]:
                continue
            notified[f"{m['id']}|{pk['k']}"] = now.isoformat()
            alerts.append((m, pk))
            break
    json.dump(dict(generated=now.isoformat(), matches=out, notified=notified,
                   alerts=[dict(id=m["id"], k=pk["k"]) for m, pk in alerts]),
              open(outpath, "w"), ensure_ascii=False, separators=(",", ":"))
    for m, pk in alerts[:6]:
        print(f"BİLDİRİM: {m['clock']} {m['home']} {m['score'][0]}-{m['score'][1]} {m['away']} ({m['lgName']}): "
              f"{pk['label']} %{round(pk['prob']*100)} — iddaa canlı oranı en az {str(pk['minOdds']).replace('.', ',')} ise")
    n_p = sum(1 for m in out if m["picks"])
    print(f"{len(out)} canlı maç; {n_p} maçta canlı seçim adayı")
    for m in out:
        for pk in m["picks"]:
            print(f"  {m['clock']} {m['home']} {m['score'][0]}-{m['score'][1]} {m['away']} ({m['lgName']}): "
                  f"{pk['label']} %{round(pk['prob']*100)}, en az oran {pk['minOdds']}" + (f" — {pk['warn']}" if pk["warn"] else ""))


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[a.index("--prev") + 1] if "--prev" in a else None)
