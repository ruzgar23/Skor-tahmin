"""Canlı analiz: o an oynanan maçları ESPN'den alır, maç öncesi gol beklentisini kalan süreye,
skora ve kırmızı kartlara göre günceller; live.json yazar.
Kullanım:  python3 live.py <data.json> <live.json>"""
import sys, os, json, math, re
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
# Kalibrasyon düzeltmeleri (gerçek gol eğrisiyle; 2023-25 ve 2025-26'da aynı yönde): çifte şans 12 ~2 puan iyimser.
# KG Yok için eski -2 puan düzeltmesi düz dağılım içindi; gerçek eğriyle gerek kalmadı.
KGY_FIX = 0.0
D12_FIX = 0.02

# Canlı korner (backtest/live_corner_test.py, ESPN anlatımlarından 7.092 maç, 2023-25 öğrenme / 2025-26 test).
# Kalan korner (her takım) = kalan_süre * [(1-w)*maç öncesi beklenti + w*maç içi tempo] * skor durumu * kırmızı kart;
# toplam negatif binom. 55–80. dakika seçimleri testte %83,4 tuttu (beklenen %83,5).
CORNER = dict(share=0.922, w=0.1654, behind=0.1573, ahead=-0.2363, red_own=-0.4209, red_opp=0.4693, stop=6.75, r=24.05)
CORNER_MIN, CORNER_MAX = 55, 80
# Yalnızca testte yeterli dakika verisi olan ligler (Süper Lig'de ESPN korner dakikası vermiyor; veri birikince eklenecek)
CORNER_LEAGUES = {"E0", "E1", "SP1", "SP2", "I1", "N1", "F1", "P1", "D1"}


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


# Gollerin dakikaya göre birikimli payı (0..90; 45 ve 90 uzatma golleri dahil). ESPN, 2023-25, 13.401 maç, 36.548 gol.
# Goller devre sonlarına doğru artar ve %4'ü ilk yarı, %8'i maç sonu uzatmasında atılır; eski düz dağılım kalan golü
# düşük tahmin ediyordu (backtest/live_goal_test.py). None ise eski düz dağılım kullanılır.
GOAL_CURVE = [0.0, 0.0046, 0.0114, 0.0192, 0.0279, 0.0366, 0.0454, 0.0544, 0.0647, 0.0741, 0.0831, 0.0927, 0.1028, 0.112, 0.1212, 0.1305, 0.1398, 0.1492, 0.1582, 0.1669, 0.1767, 0.1853, 0.1946, 0.2052, 0.2146, 0.2243, 0.2338, 0.2428, 0.2523, 0.2614, 0.2718, 0.2821, 0.2918, 0.3015, 0.3109, 0.3205, 0.3295, 0.3393, 0.3495, 0.3581, 0.3672, 0.3759, 0.3858, 0.3954, 0.405, 0.4452, 0.4511, 0.4611, 0.4706, 0.4818, 0.4928, 0.5037, 0.5153, 0.527, 0.538, 0.5494, 0.5611, 0.5727, 0.5837, 0.5957, 0.6073, 0.6195, 0.6303, 0.6412, 0.6532, 0.6644, 0.6749, 0.6851, 0.6956, 0.7056, 0.7168, 0.7276, 0.7386, 0.7487, 0.7585, 0.7687, 0.7791, 0.7901, 0.8002, 0.8107, 0.8213, 0.8317, 0.8426, 0.8526, 0.8627, 0.8737, 0.8839, 0.895, 0.9056, 0.9167, 1.0]


def done_share(minute, period, h=HT_SHARE):
    if GOAL_CURVE is None:
        if period <= 1:
            return h * min(minute, 45) / 45
        return h + (1 - h) * min(max(minute - 45, 0), 45) / 45
    t = int(minute)
    t = min(max(t, 0), 45) if period <= 1 else min(max(t, 45), 90)
    return GOAL_CURVE[t]


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


def _pois(L, n=9):
    i = np.arange(n)
    return np.exp(-L) * L ** i / np.array([math.factorial(k) for k in i])


def extra_live(lh, la, hs, as_, minute, period, rh=0, ra=0):
    """Ek canlı pazarlar: [(anahtar, etiket, olasılık)].
    İlk yarı (yalnızca 1. yarıda): İY sonucu, İY 0,5/1,5 Alt-Üst. Takım golü: ev/dep bir sonraki iki çizgi. Sıradaki gol."""
    mh = state_mult(hs - as_) * (RED_OWN ** rh) * (RED_OPP ** ra)
    ma = state_mult(as_ - hs) * (RED_OWN ** ra) * (RED_OPP ** rh)
    out = []
    rem = max(1 - done_share(minute, period), 0.0)
    Lh, La = lh * rem * mh, la * rem * ma
    ph, pa = _pois(Lh), _pois(La)
    for side, cur, pv, tag, nm_ in (("E", hs, ph, "Ev", "ev"), ("D", as_, pa, "Dep", "dep")):
        cdf = np.cumsum(pv)
        for k in range(cur, cur + 2):           # çizgi = k + 0,5: kalan gol ≥ k - cur + 1
            line = k + 0.5; need = k - cur + 1
            po = float(1 - cdf[need - 1])
            out += [(f"{side}O{line}", f"{tag} gol {str(line).replace('.', ',')} Üst", po),
                    (f"{side}U{line}", f"{tag} gol {str(line).replace('.', ',')} Alt", 1 - po)]
    nog = float(ph[0] * pa[0])
    if Lh + La > 0:
        out += [("NEXT1", LABELS["NEXT1"], (1 - nog) * Lh / (Lh + La)), ("NEXT2", LABELS["NEXT2"], (1 - nog) * La / (Lh + La))]
    if period == 1 and minute < 45:
        r1 = max(done_share(45, 1) - done_share(minute, 1), 0.0)
        R = np.outer(_pois(lh * r1 * mh), _pois(la * r1 * ma)); R /= R.sum()
        I, J = np.meshgrid(range(R.shape[0]), range(R.shape[0]), indexing="ij")
        H, A = I + hs, J + as_
        out += [("IY1", "İY 1", float(R[H > A].sum())), ("IYX", "İY X", float(R[H == A].sum())), ("IY2", "İY 2", float(R[H < A].sum()))]
        for line in (0.5, 1.5):
            if hs + as_ < line:
                po = float(R[H + A > line].sum())
                out += [(f"IYO{line}", f"İY {str(line).replace('.', ',')} Üst", po), (f"IYU{line}", f"İY {str(line).replace('.', ',')} Alt", 1 - po)]
    return out


def ht_score(c):
    """İlk yarı skoru, maç olaylarından (45+ uzatma golleri ilk yarıya sayılır). Tutarsızsa None."""
    ids = {str((x.get("team") or {}).get("id") or x.get("id")): x["homeAway"] for x in c["competitors"]}
    h = a = fh = fa = 0
    for d in c.get("details") or []:
        if not d.get("scoringPlay"):
            continue
        m = re.match(r"(\d+)", ((d.get("clock") or {}).get("displayValue") or ""))
        side = ids.get(str((d.get("team") or {}).get("id")))
        if not m or side is None:
            return None
        fh += side == "home"; fa += side == "away"
        if int(m.group(1)) <= 45:
            h += side == "home"; a += side == "away"
    try:
        sc = {x["homeAway"]: int(x["score"]) for x in c["competitors"]}
    except (KeyError, ValueError, TypeError):
        return None
    # her golün takımı skorla birebir tutmalı (kendi kalesine gollerde yanlış takım yazılırsa sonuç verilmez)
    return [h, a] if (fh, fa) == (sc.get("home"), sc.get("away")) else None


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
            out["total"] = dict(line=ln, over=E.fair({"O": po, "U": pu}, ("O", "U"))["O"], oo=po, uo=pu)
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
        po = E.fair({"O": eo["over"], "U": eo["under"]}, ("O", "U"))["O"]
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


def picks_for(p, tl, minute, mkt, cur_goals=0, extra=None):
    """Canlı seçim adayları: olasılık %70–88 arası (çok kesin olanların oranı oynamaya değmez).
    extra: extra_live() çıktısı (İY, takım golü, sıradaki gol)."""
    cand = []
    for k in ("1", "X", "2", "1X", "X2", "12"):
        cand.append((k, LABELS[k], p[k] - (D12_FIX if k == "12" else 0)))
    cand += list(extra or [])
    cand += [("BTTS", LABELS["BTTS"], p["BTTS"]), ("NBTTS", LABELS["NBTTS"], 1 - p["BTTS"] - KGY_FIX),
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


def corner_pick(pre_h, pre_a, ch, ca, hs, as_, minute, period, rh=0, ra=0):
    """Canlı korner alt/üst seçimi (yalnızca ikinci yarı, 55–80. dakika). pre_*: maç öncesi korner beklentisi."""
    if period < 2 or minute is None or not (CORNER_MIN <= minute <= CORNER_MAX) or not pre_h or not pre_a:
        return None
    from scipy.stats import nbinom
    k = CORNER; t = float(minute)
    rem = max(90 - t + k["stop"], 0) / 90 * k["share"]
    w = k["w"] * t / 90
    bh = (1 - w) * pre_h + w * ch / (t / 90); ba = (1 - w) * pre_a + w * ca / (t / 90)
    d = max(-2, min(2, hs - as_))
    sh = math.exp(k["behind"] * max(-d, 0) + k["ahead"] * max(d, 0))
    sa = math.exp(k["behind"] * max(d, 0) + k["ahead"] * max(-d, 0))
    mh = rem * bh * sh * math.exp(k["red_own"] * rh + k["red_opp"] * ra)
    ma = rem * ba * sa * math.exp(k["red_own"] * ra + k["red_opp"] * rh)
    mt = mh + ma; r = k["r"]; cur = ch + ca
    best = None
    for j in range(7):
        line = cur + j + 0.5
        po = float(1 - nbinom.cdf(j, r, r / (r + mt)))  # kalan korner ≥ j+1
        for key, lab, pr in ((f"CO{line}", "Üst", po), (f"CU{line}", "Alt", 1 - po)):
            if 0.70 <= pr <= 0.88 and (best is None or pr > best["prob"]):
                best = dict(k=key, label=f"Korner {str(line).replace('.', ',')} {lab}", prob=round(pr, 4),
                            minOdds=round(1.05 / pr, 2), warn=None, exp=round(cur + mt, 1))
    return best


def team_cards(c):
    """Sarı ve kırmızı kart sayıları (ev, dep) — maç olay listesinden."""
    ids = {x["homeAway"]: str((x.get("team") or {}).get("id") or x.get("id")) for x in c["competitors"]}
    y = {"home": 0, "away": 0}
    for d in c.get("details") or []:
        if d.get("yellowCard"):
            tid = str((d.get("team") or {}).get("id"))
            for side, i in ids.items():
                if tid == i:
                    y[side] += 1
    return y["home"], y["away"]


def corners_of(c):
    sd = {x["homeAway"]: x for x in c["competitors"]}
    try:
        return [int(stats_of(sd["home"])["wonCorners"]), int(stats_of(sd["away"])["wonCorners"])]
    except (KeyError, TypeError, ValueError):
        return None


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


def log_snapshots(logdir, out, now, seen):
    """Canlı maç verisini biriktirir (ileride korner, kart ve gol dakikası testleri için).
    Her maç için yalnızca değişen anlar yazılır: ay başına bir JSONL dosyası (state/run/live_log/AAAA-AA.jsonl)."""
    os.makedirs(logdir, exist_ok=True)
    rows = []
    for m in out:
        st = m.get("stats") or [{}, {}]
        snap = [m["minute"], m["period"], *m["score"], *(m.get("corners") or [None, None]), *(m.get("cards") or [None, None]),
                *m["reds"], st[0].get("totalShots"), st[1].get("totalShots"), st[0].get("shotsOnTarget"), st[1].get("shotsOnTarget")]
        key = str(m["eid"]); sig = json.dumps(snap[2:])
        if seen.get(key) == sig:
            continue
        seen[key] = sig
        rows.append(dict(t=now.isoformat(timespec="seconds"), eid=m["eid"], lg=m["lg"], home=m["home"], away=m["away"],
                         pre=m["pre"]["lam"], s=snap))
    if rows:
        with open(os.path.join(logdir, f"{now:%Y-%m}.jsonl"), "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    # artık canlı olmayan maçların imzalarını unut
    return {k: v for k, v in seen.items() if k in {str(m["eid"]) for m in out}}


def main(datapath, outpath, prevpath=None, logdir=None):
    now = datetime.now(timezone.utc)
    notified = {}; seen = {}
    if prevpath:
        try:
            pv = json.load(open(prevpath))
            if datetime.fromisoformat(pv["generated"]) > now - timedelta(hours=12):
                notified = pv.get("notified", {}); seen = pv.get("logseen", {})
        except Exception:
            pass
    try:
        data = json.load(open(datapath))
    except Exception:
        data = {"matches": []}
    names, lam_idx = {}, {}
    for m in data["matches"]:
        names.setdefault(m["lg"], set()).update([m["home"], m["away"]])
        cor = m.get("corners") or {}
        lam_idx[(m["lg"], m["home"], m["away"])] = (m["lam"][0], m["lam"][1], m.get("id"), m["p"], (cor.get("home"), cor.get("away")))
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
            cor = corners_of(c)
            cpk = None
            if cor and hit and lg in CORNER_LEAGUES:
                cpk = corner_pick(hit[4][0], hit[4][1], cor[0], cor[1], hs, as_, minute, period, rh, ra)
            lgname = espn.CUP_NAMES.get(lg) or E.LEAGUE_NAMES.get(lg, lg)
            out.append(dict(
                id=(hit[2] if hit and hit[2] else f"{lg}-{ev['id']}"), eid=ev["id"], slug=slug, lg=lg, lgName=lgname,
                home=h or hn, away=a or an, minute=minute, period=period, clock=ev["status"].get("displayClock"),
                halftime=ev["status"]["type"]["name"] == "STATUS_HALFTIME",
                score=[hs, as_], reds=[rh, ra], stats=[stats_of(sd["home"]), stats_of(sd["away"])],
                pre=dict(lam=[round(lams[0], 3), round(lams[1], 3)], src=src, p=(hit[3] if hit else None)),
                rest=rest, p={k: round(v, 4) for k, v in p.items()}, totals={k: round(v, 4) for k, v in tl.items()},
                top=top, market=mkt, picks=picks_for(p, tl, minute, mkt, hs + as_,
                                                     extra_live(lams[0], lams[1], hs, as_, minute, period, rh, ra)),
                ht=ht_score(c) if (period >= 2 or ev["status"]["type"]["name"] == "STATUS_HALFTIME") else None,
                corners=cor, cards=list(team_cards(c)), cpicks=[cpk] if cpk else [],
            ))
    out.sort(key=lambda m: (-len(m["picks"]), -m["minute"]))
    alerts = []
    for m in out:
        m["consistent"] = consistent(m)
        # korner: maç başına bir kez (gol seçiminden bağımsız); maç öncesi korner beklentisi olan üst liglerde
        for pk in m["cpicks"]:
            if not any(k.startswith(m["id"] + "|C") for k in notified):
                notified[f"{m['id']}|{pk['k']}"] = now.isoformat()
                alerts.append((m, pk))
        if not m["consistent"] or m["lg"] not in TOP:
            continue
        if any(k.startswith(m["id"] + "|") and not k.startswith(m["id"] + "|C") for k in notified):
            continue  # aynı maç için bir kez bildir
        for pk in m["picks"]:
            if pk["warn"]:
                continue
            notified[f"{m['id']}|{pk['k']}"] = now.isoformat()
            alerts.append((m, pk))
            break
    if logdir:
        try:
            seen = log_snapshots(logdir, out, now, seen)
        except Exception as e:  # kayıt hatası canlı analizi durdurmasın
            print("canlı kayıt yazılamadı:", e)
    json.dump(dict(generated=now.isoformat(), matches=out, notified=notified, logseen=seen,
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
