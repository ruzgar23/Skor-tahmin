"""Öneri derecelendirme ve Telegram mesaj biçimleri. Sayfadaki (site/index.html) mantığın aynısı."""
import html, json, os, unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Europe/Istanbul")
def _site_url():
    """SITE_URL değişkeni yoksa GitHub Pages adresini depo adından üretir."""
    u = os.environ.get("SITE_URL", "").strip()
    if u:
        return u.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}"
    return ""


SITE_URL = _site_url()

TR = {"Besiktas": "Beşiktaş", "Fenerbahce": "Fenerbahçe", "Goztep": "Göztepe", "Buyuksehyr": "Başakşehir",
      "Corum": "Çorum", "Eyupspor": "Eyüpspor", "Genclerbirligi": "Gençlerbirliği", "Kasimpasa": "Kasımpaşa",
      "Karagumruk": "Karagümrük", "Ankaragucu": "Ankaragücü", "Istanbulspor": "İstanbulspor",
      "Gaziantep": "Gaziantep FK", "Ad. Demirspor": "Adana Demirspor"}
TIER_LG = {"UCL": 0, "UEL": 0, "UECL": 0, "E0": 1, "SP1": 1, "I1": 1, "D1": 1, "F1": 1, "T1": 1, "N1": 1, "P1": 1,
           "SC0": 1, "G1": 1, "E1": 2, "SP2": 2, "I2": 2, "D2": 2, "F2": 2, "SC1": 2, "E2": 3, "E3": 3, "SC2": 3, "SC3": 3}
TIERNAME = {3: "Güçlü", 2: "Orta", 1: "Düşük güven"}
HIT = {("MS", 3): .80, ("MS", 2): .67, ("O25", 2): .65, ("U25", 2): .63, ("KGV", 2): .64}
UNIT = {3: "1 birim", 2: "½ birim", 4: "½ birim", 5: "¼ birim"}
LABEL2KEY = {"MS 1": "1", "MS X": "X", "MS 2": "2", "2,5 Üst": "O25", "2,5 Alt": "U25", "KG Var": "BTTS", "KG Yok": "NBTTS"}


def e(s):
    return html.escape(str(s), quote=False)


def nm(t):
    return TR.get(t, t)


def pct(x):
    return f"%{round(x * 100)}"


def tr_up(s):
    """Türkçe büyük harf (i → İ)."""
    return s.replace("i", "İ").upper()


def odds_fmt(x):
    return f"{x:.2f}".replace(".", ",")


def pick_of(m):
    p = m["p"]
    return max([("MS 1", p["1"]), ("MS X", p["X"]), ("MS 2", p["2"])], key=lambda t: t[1])


def grade(m):
    p = m["p"]; msk, msp = pick_of(m); c = []
    if msp >= .70: c.append(("MS", msk, msp, 3))
    elif msp >= .60: c.append(("MS", msk, msp, 2))
    # 2,5 Üst en fazla Orta: %70+ seçimler 8 sezonda %70-74 tuttu (MS Güçlü ~%79)
    if p["O25"] >= .60: c.append(("O25", "2,5 Üst", p["O25"], 2))
    if 1 - p["O25"] >= .60: c.append(("U25", "2,5 Alt", 1 - p["O25"], 2))
    if p["BTTS"] >= .60: c.append(("KGV", "KG Var", p["BTTS"], 2))
    if 1 - p["BTTS"] >= .60: c.append(("KGY", "KG Yok", 1 - p["BTTS"], 1))
    if not c:
        return None
    c.sort(key=lambda t: (-t[3], -t[2]))
    fam, label, prob, tier = c[0]
    g = dict(fam=fam, label=label, prob=prob, tier=tier, hit=HIT.get((fam, tier)), minOdds=1.03 / prob)
    if m.get("src") != "piyasa":
        g["tier"] = 1
    if (not m["known"][0] or not m["known"][1]) and not (m.get("cup") and m.get("src") == "piyasa"):
        g["tier"] = 1
    return g


# Ek seçimler (ilk yarı ve takım gol alt/üst): maç başına en fazla bir tane, olasılık %70–80.
# backtest/new_markets_test.py: 24.863 seçimde %76,9 tuttu (beklenen %76,0), 7 sezonun hepsinde %76–78.
EXTRA = (("HTO05", "İY 0,5 Üst", False), ("HTO15", "İY 1,5 Alt", True),
         ("HO05", "Ev gol 0,5 Üst", False), ("HO15", "Ev gol 1,5 Üst", False), ("HO15", "Ev gol 1,5 Alt", True),
         ("HO25", "Ev gol 2,5 Alt", True), ("AO05", "Dep gol 0,5 Üst", False), ("AO15", "Dep gol 1,5 Üst", False),
         ("AO15", "Dep gol 1,5 Alt", True), ("AO25", "Dep gol 2,5 Alt", True))
EXTRA_KEY = {lab: (k, under) for k, lab, under in EXTRA}


def extra_pick(m):
    """Maçın ek seçimi (yalnızca piyasa oranlı maçlarda) ya da None."""
    p = m.get("p") or {}
    if m.get("src") != "piyasa" or not all(m.get("known") or [False]):
        return None
    if m.get("cup"):
        # Avrupa kupalarında güçlü-zayıf farkı büyük, farklı skorlar modelin beklediğinden sık (3+ fark: model %22, gerçek %25);
        # ek seçimler kupalarda %72,6 tuttu (beklenen %76,3; backtest/cup_test.py, 2026, 351 maç). Ana seçimler etkilenmiyor.
        return None
    best = None
    for k, lab, under in EXTRA:
        if k not in p:
            continue
        v = 1 - p[k] if under else p[k]
        if .70 <= v < .80 and (best is None or v > best["prob"]):
            best = dict(fam="EXTRA", label=lab, prob=v, tier=2, minOdds=1.03 / v)
    return best


def settle_extra(label, res, ht=None):
    """Ek seçimin sonucu; ilk yarı seçimleri için devre skoru gerekir."""
    if not res or label not in EXTRA_KEY:
        return None
    k, under = EXTRA_KEY[label]; line = int(k[-2]) + 0.5
    if k.startswith("HT"):
        if not ht:
            return None
        v = ht[0] + ht[1]
    else:
        v = res[0] if k[0] == "H" else res[1]
    return v < line if under else v > line


# Birleşik bahisler (MS / çifte şans + 2,5 Alt-Üst, MS + KG): skor matrisinden.
# backtest/combo_test.py: 29.374 maçta kalibre (%60+ dediği %62–66 tuttu); seçim olarak değil, /mac ve /kupon'da bilgi olarak.
COMBO_RES = {"1": lambda i, j: i > j, "X": lambda i, j: i == j, "2": lambda i, j: i < j,
             "1X": lambda i, j: i >= j, "X2": lambda i, j: i <= j, "12": lambda i, j: i != j}
COMBO_TOT = {("gol", "O", 1.5): ("1,5 Üst", lambda i, j: i + j >= 2), ("gol", "U", 1.5): ("1,5 Alt", lambda i, j: i + j <= 1),
             ("gol", "O", 2.5): ("2,5 Üst", lambda i, j: i + j >= 3), ("gol", "U", 2.5): ("2,5 Alt", lambda i, j: i + j <= 2),
             ("gol", "O", 3.5): ("3,5 Üst", lambda i, j: i + j >= 4), ("gol", "U", 3.5): ("3,5 Alt", lambda i, j: i + j <= 3),
             "BTTS": ("KG Var", lambda i, j: i > 0 and j > 0), "NBTTS": ("KG Yok", lambda i, j: not (i > 0 and j > 0))}
RES_LBL = {"1": "MS 1", "X": "MS X", "2": "MS 2", "1X": "1X", "X2": "X2", "12": "12"}


def combo_prob(m, res, tot):
    """P(sonuç ve toplam/KG) ya da None. m["M"]: 6x6 skor matrisi."""
    M = m.get("M")
    if not M or res not in COMBO_RES or tot not in COMBO_TOT:
        return None
    rf, (_, tf) = COMBO_RES[res], COMBO_TOT[tot]
    s = sum(sum(r) for r in M)
    v = sum(M[i][j] for i in range(len(M)) for j in range(len(M)) if rf(i, j) and tf(i, j))
    return v / s if s else None


def combo_label(res, tot):
    return f"{RES_LBL[res]} & {COMBO_TOT[tot][0]}"


def combo_lines(m):
    """/mac için birleşik bahis olasılıkları: [(başlık, [(etiket, olasılık)])]."""
    def row(pairs):
        out = []
        for res, tot in pairs:
            v = combo_prob(m, res, tot)
            if v is not None:
                out.append((combo_label(res, tot), v))
        return out
    U, A = ("gol", "O", 2.5), ("gol", "U", 2.5)
    rows = [("MS & 2,5", row([("1", U), ("1", A), ("X", A), ("2", U), ("2", A)])),
            ("MS & KG", row([("1", "BTTS"), ("1", "NBTTS"), ("2", "BTTS"), ("2", "NBTTS")])),
            ("Çifte şans & 2,5", row([("1X", U), ("1X", A), ("X2", U), ("X2", A)]))]
    return [(h, r) for h, r in rows if r]


# Riskli seçimler: adil oranı 1,75–2,00 (olasılık %50–57) olan bahislerden maç başına en olası tek seçim.
# Pazarlar backtest/risky_test.py ile seçildi: kalibre çıkmayan KG Yok, 1X & 2,5 Üst ve MS & KG Yok yok.
RISKY_LO, RISKY_HI = 0.50, 1 / 1.75
RISKY_MAX = 8
RISKY_SIMPLE = (("1", "MS 1"), ("2", "MS 2"), ("O25", "2,5 Üst"), ("U25", "2,5 Alt"), ("U35", "3,5 Alt"), ("BTTS", "KG Var"),
                ("HO15", "Ev gol 1,5 Üst"), ("AO15", "Dep gol 1,5 Üst"), ("HTO15", "İY 1,5 Üst"))
RISKY_COMBO = (("1", ("gol", "O", 2.5)), ("2", ("gol", "O", 2.5)), ("12", ("gol", "O", 2.5)), ("X2", ("gol", "O", 2.5)))


def risky_pick(m):
    """Maçın riskli seçimi ya da None: dict(label, key, prob, minOdds, tier=5)."""
    p = m.get("p") or {}
    if m.get("src") != "piyasa" or not all(m.get("known") or [False]):
        return None
    c = []
    for k, lab in RISKY_SIMPLE:
        v = (1 - p["O25"]) if k == "U25" else (1 - p["O35"]) if k == "U35" else p.get(k)
        if v is not None:
            c.append((k, lab, v))
    for res, tot in RISKY_COMBO:
        v = combo_prob(m, res, tot)
        if v is not None:
            c.append((f"C{res}|O25", combo_label(res, tot), v))
    c = [x for x in c if RISKY_LO <= x[2] <= RISKY_HI]
    if not c:
        return None
    k, lab, v = max(c, key=lambda x: x[2])
    return dict(fam="RISKY", key=k, label=lab, prob=v, tier=5, minOdds=1.03 / v)


def settle_risky(key, res, ht=None):
    if not res:
        return None
    a, b = res; t = a + b
    if key.startswith("C"):
        r, _ = key[1:].split("|")
        return COMBO_RES[r](a, b) and t >= 3
    if key == "HTO15":
        return None if not ht else ht[0] + ht[1] >= 2
    return {"1": a > b, "2": a < b, "O25": t >= 3, "U25": t <= 2, "U35": t <= 3, "BTTS": a > 0 and b > 0,
            "HO15": a >= 2, "AO15": b >= 2}.get(key)


def risky_list(matches, n=RISKY_MAX):
    """[(maç, seçim)] olasılığa göre, en fazla n."""
    out = [(m, risky_pick(m)) for m in matches]
    return sorted([x for x in out if x[1]], key=lambda x: -x[1]["prob"])[:n]


RISKY_SINCE = "2026-11-04"  # riskli seçimlerin gönderilmeye başladığı gün; öncesi karnede sayılmaz


def risky_results(history, day):
    if day.isoformat() < RISKY_SINCE:
        return []
    done = [h for h in history if h.get("res") and ko_local(h).date() == day]
    out = []
    for h, g in risky_list(done):
        ok = settle_risky(g["key"], h["res"], h.get("ht"))
        if ok is not None:
            out.append((h, g, ok))
    return out


def risky_message(data, day):
    rows = risky_list(day_matches(data, day))
    head = ["🎲 <b>Riskli seçimler — oran 1,75+</b>",
            "Tutma olasılığı %50–57: 10 seçimin ortalama 5–6'sı tutar. Kombine yapma, en fazla ¼ birim oyna.\n"]
    if not rows:
        return "\n".join(head) + "Bugün bu aralıkta uygun seçim yok."
    out = head + [pick_line(m, g) for m, g in sorted(rows, key=lambda x: ko_local(x[0]))]
    out.append("\n<i>8 sezonluk testte %55 tuttu (beklenen %55). iddaa oranı yazan sınırın altındaysa oynama: "
               "piyasa ortalaması oranla bu seçimler %5 kaybettirdi.</i>")
    return "\n".join(out) + link_line()


def extra_results(history, day):
    """Dünün ek seçim sonuçları: [(maç, seçim, tuttu mu)]."""
    out = []
    for h in sorted(history, key=lambda h: h["ko"]):
        if not h.get("res") or ko_local(h).date() != day:
            continue
        g = extra_pick(h)
        ok = settle_extra(g["label"], h["res"], h.get("ht")) if g else None
        if ok is not None:
            out.append((h, g, ok))
    return out


def settle(k, res):
    if not res: return None
    a, b = res; t = a + b
    return {"1": a > b, "X": a == b, "2": a < b, "O25": t >= 3, "U25": t < 3,
            "BTTS": a > 0 and b > 0, "NBTTS": not (a > 0 and b > 0)}.get(k)


def ko_local(m):
    return datetime.fromisoformat(m["ko"]).astimezone(IST)


def link_line():
    return f'\n🔗 <a href="{SITE_URL}">Tüm maçlar ve ayrıntılar</a>' if SITE_URL else ""


FOOTER = "\n<i>Olasılıklar garanti değildir; %70'lik bir seçim de 10 maçın 3'ünde yatar. Kaybetmeyi göze alamayacağın parayla oynama.</i>"


def pick_line(m, g, with_time=True):
    t = ko_local(m).strftime("%H:%M") + " · " if with_time else ""
    return (f"{t}<b>{e(nm(m['home']))} – {e(nm(m['away']))}</b> <i>({e(m['lgName'])})</i>\n"
            f"   👉 OYNA: <b>{e(g['label'].upper())}</b> · tutma %{round(g['prob'] * 100)} · oran ≥ <b>{odds_fmt(g['minOdds'])}</b> ise"
            + (f" · {UNIT[g['tier']]}" if g['tier'] in UNIT else ""))


def day_matches(data, day):
    return [m for m in data["matches"] if ko_local(m).date() == day and ko_local(m) > datetime.now(IST)]


def daily_message(data, day):
    ms = day_matches(data, day)
    if not ms:
        return None
    graded = [(m, grade(m)) for m in ms]
    strong = sorted([x for x in graded if x[1] and x[1]["tier"] == 3], key=lambda x: (ko_local(x[0]), -x[1]["prob"]))
    mid = sorted([x for x in graded if x[1] and x[1]["tier"] == 2], key=lambda x: (ko_local(x[0]), -x[1]["prob"]))
    d = day.strftime("%d.%m.%Y")
    out = [f"⚽ <b>Günün maçları — {d}</b>", f"{len(ms)} maç tarandı · {len(strong)} güçlü, {len(mid)} orta öneri\n"]
    if strong:
        out.append("🟢 <b>Güçlü öneriler</b> (testte %74–80 tuttu)")
        out += [pick_line(m, g) for m, g in strong]
        out.append("")
    if mid:
        out.append("🟡 <b>Orta öneriler</b> (testte %63–67 tuttu)")
        out += [pick_line(m, g) for m, g in mid[:25]]
        if len(mid) > 25:
            out.append(f"   … ve {len(mid) - 25} maç daha (/orta)")
        out.append("")
    ex = sorted([(m, extra_pick(m)) for m in ms], key=lambda x: -(x[1]["prob"] if x[1] else 0))
    ex = [x for x in ex if x[1]][:6]
    if ex:
        out.append("🔵 <b>Ek seçimler</b> — ilk yarı ve takım golü (testte %77 tuttu)")
        out += [pick_line(m, dict(g, tier=4)) for m, g in sorted(ex, key=lambda x: ko_local(x[0]))]
        out.append("")
    if not strong and not mid:
        out.append("Bugün %60'ı geçen net bir seçim yok.\n")
    out.append("Diğer maçlar için /bugun · tek maç için /mac takım")
    return "\n".join(out) + link_line() + FOOTER


def all_matches_message(data, day):
    ms = sorted(day_matches(data, day), key=lambda m: (TIER_LG.get(m["lg"], 9), m["lgName"], m["ko"]))
    if not ms:
        return "Bugün için kalan maç yok."
    out = [f"📋 <b>Tüm maçlar — {day.strftime('%d.%m.%Y')}</b>", "<i>MS 1/X/2 · 2,5Ü · en olası skor</i>"]
    cur = None
    for m in ms:
        if m["lgName"] != cur:
            cur = m["lgName"]; out.append(f"\n<b>{e(cur)}</b>")
        p = m["p"]; t = m["top"][0]; g = grade(m)
        mark = {3: "🟢", 2: "🟡", 1: "⚪"}.get(g["tier"], "") if g else ""
        out.append(f"{ko_local(m).strftime('%H:%M')} {e(nm(m['home']))} – {e(nm(m['away']))} {mark}\n"
                   f"   {pct(p['1'])}/{pct(p['X'])}/{pct(p['2'])} · 2,5Ü {pct(p['O25'])} · {t[0]}-{t[1]}")
    return "\n".join(out) + link_line()


def tier_list_message(data, day, tier):
    ms = [(m, grade(m)) for m in day_matches(data, day)]
    ms = sorted([x for x in ms if x[1] and x[1]["tier"] == tier], key=lambda x: (ko_local(x[0]), -x[1]["prob"]))
    title = {3: "🟢 Güçlü öneriler", 2: "🟡 Orta öneriler"}[tier]
    if not ms:
        return f"{title}: bugün için yok."
    return f"<b>{title} — {day.strftime('%d.%m.%Y')}</b>\n" + "\n".join(pick_line(m, g) for m, g in ms) + link_line() + FOOTER


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("ı", "i")


def match_message(data, q):
    qn = norm(q)
    hits = [m for m in data["matches"] if ko_local(m) > datetime.now(IST) - timedelta(hours=2)
            and (qn in norm(nm(m["home"])) or qn in norm(nm(m["away"])) or qn in norm(m["home"]) or qn in norm(m["away"]))]
    if not hits:
        return f"“{e(q)}” için yaklaşan maç bulunamadı."
    m = sorted(hits, key=lambda m: m["ko"])[0]; p = m["p"]; g = grade(m)
    tops = ", ".join(f"{a}-{b} {pct(v)}" for a, b, v in m["top"][:4])
    lines = [f"⚽ <b>{e(nm(m['home']))} – {e(nm(m['away']))}</b>",
             f"{e(m['lgName'])} · {ko_local(m).strftime('%d.%m %H:%M')}", "",
             f"MS: 1 {pct(p['1'])} · X {pct(p['X'])} · 2 {pct(p['2'])}",
             f"Çifte şans: 1X {pct(p['1X'])} · 12 {pct(p['12'])} · X2 {pct(p['X2'])}",
             f"Alt/Üst: 1,5Ü {pct(p['O15'])} · 2,5Ü {pct(p['O25'])} · 3,5Ü {pct(p['O35'])}",
             f"KG Var {pct(p['BTTS'])} · İY 1/X/2 {pct(p['HT1'])}/{pct(p['HTX'])}/{pct(p['HT2'])}",
             f"En olası skorlar: {tops}",
             f"Gol beklentisi: {m['lam'][0]:.2f} – {m['lam'][1]:.2f}".replace(".", ",")]
    cl = combo_lines(m)
    if cl:
        lines.append("")
        lines.append("<b>Birleşik bahisler</b> (olasılık · adil oran)")
        for h, r in cl:
            lines.append(" · ".join(f"{lab} {pct(v)} ({odds_fmt(1 / v)})" for lab, v in r if v > 0.02))
    import extra
    lines += extra.stat_lines(m)
    if g:
        lines += ["", f"<b>Öneri: {e(g['label'])} {pct(g['prob'])}</b> · {TIERNAME[g['tier']]}",
                  f"Oynamaya değmesi için iddaa oranı en az <b>{odds_fmt(g['minOdds'])}</b>"]
    else:
        lines += ["", "Bu maçta %60'ı geçen net seçim yok."]
    if len(hits) > 1:
        lines.append(f"\n<i>{len(hits) - 1} maç daha eşleşti; daha ayrıntılı yaz.</i>")
    return "\n".join(lines) + link_line()


def report_message(history, day, picks=None, live_bets=None, opicks=None, basket=None):
    import extra
    lv = extra.live_report_lines(live_bets, day)
    orow = extra.other_day_results(opicks, basket, day)
    if orow:
        ow = sum(1 for _, _, ok in orow if ok)
        lv = [f"\n🏀🏒🎾 <b>Basketbol, hokey, tenis:</b> {len(orow)} seçimin {ow}'i tuttu ({pct(ow / len(orow))})"] + [
            f"{'✅' if ok else '❌'} {e(v['home'])} – {e(v['away'])} · {e(v['label'])} {pct(v['prob'])} · {e(txt)}" for v, txt, ok in orow] + lv
    done = [h for h in history if h.get("res") and ko_local(h).date() == day]
    if not done and not lv:
        return None
    t = {3: [0, 0], 2: [0, 0]}; rows = []
    for h in sorted(done, key=lambda h: h["ko"]):
        g = grade(h)
        if not g or g["tier"] < 2:
            continue
        ok = settle(LABEL2KEY[g["label"]], h["res"])
        if ok is None:
            continue
        t[g["tier"]][0] += 1; t[g["tier"]][1] += ok
        rows.append(f"{'✅' if ok else '❌'} {e(nm(h['home']))} {h['res'][0]}-{h['res'][1]} {e(nm(h['away']))} · "
                    f"{e(g['label'])} {pct(g['prob'])}")
    xr = extra_results(history, day)
    if not rows and not lv and not xr and not risky_results(history, day):
        return None
    head = [f"📊 <b>Karne — {day.strftime('%d.%m.%Y')}</b>"]
    for tier in (3, 2):
        n, k = t[tier]
        if n:
            head.append(f"{TIERNAME[tier]}: {n} seçimin {k}'i tuttu ({pct(k / n)})")
    if xr:
        xw = sum(1 for _, _, ok in xr if ok)
        head.append(f"Ek seçimler (ilk yarı, takım golü): {len(xr)} seçimin {xw}'i tuttu ({pct(xw / len(xr))})")
    rr = risky_results(history, day)
    if rr:
        rw = sum(1 for _, _, ok in rr if ok)
        head.append(f"Riskli seçimler (1,75+): {len(rr)} seçimin {rw}'i tuttu ({pct(rw / len(rr))}; beklenen ~%55)")
    ts = extra.teyit_summary(picks, history, day)
    if ts:
        (n1, w1), (n0, w0) = ts["ok"], ts["bad"]
        head.append(f"Maç önü teyit: {n1} teyitli seçimin {w1}'i tuttu" + (f"; iptal edilen {n0} seçimin {w0}'i tuttu" if n0 else ""))
    xrows = [f"{'✅' if ok else '❌'} {e(nm(h['home']))} {h['res'][0]}-{h['res'][1]} {e(nm(h['away']))} · {e(g['label'])} {pct(g['prob'])}"
             + (f" (İY {h['ht'][0]}-{h['ht'][1]})" if g["label"].startswith("İY") and h.get("ht") else "") for h, g, ok in xr]
    parts = (["\n".join(head)] + (["\n".join(rows)] if rows else []) + (["🔵 <b>Ek seçimler</b>\n" + "\n".join(xrows)] if xrows else [])
             + (["🎲 <b>Riskli seçimler</b>\n" + "\n".join(
                 f"{'✅' if ok else '❌'} {e(nm(h['home']))} {h['res'][0]}-{h['res'][1]} {e(nm(h['away']))} · {e(g['label'])} {pct(g['prob'])}"
                 for h, g, ok in rr)] if rr else [])
             + (["\n".join(lv).strip()] if lv else []))
    return "\n\n".join(parts) + "\n\n<i>Tek günlük sonuç şansa çok bağlıdır.</i>"


def live_alert_message(alerts):
    out = ["🔴 <b>Canlı fırsat adayları</b>"]
    for m, pk in alerts:
        st = m.get("stats") or [{}, {}]
        sot = f" · isabetli şut {st[0].get('shotsOnTarget')}-{st[1].get('shotsOnTarget')}" if st[0].get("shotsOnTarget") is not None else ""
        if m.get("corners"): sot += f" · korner {m['corners'][0]}-{m['corners'][1]}"
        reds = (" 🟥" * m["reds"][0]) + " / " + (" 🟥" * m["reds"][1]) if any(m["reds"]) else ""
        out.append(f"\n<b>{e(m.get('clock') or '')} {e(nm(m['home']))} {m['score'][0]}-{m['score'][1]} {e(nm(m['away']))}</b>"
                   f" <i>({e(m['lgName'])})</i>{reds}{sot}\n"
                   f"   👉 OYNA: <b>{e(pk['label'].upper())}</b> · tutma %{round(pk['prob'] * 100)} · canlı oran ≥ <b>{odds_fmt(pk['minOdds'])}</b> ise")
    out.append("\n<i>İddaa'nın canlı oranı bu sınırın altındaysa oynama; canlı oranlar hızla değişir.</i>")
    return "\n".join(out)


def live_list_message(live):
    ms = live.get("matches", []) if live else []
    gen = datetime.fromisoformat(live["generated"]) if live else None
    if not ms or (gen and datetime.now(timezone.utc) - gen > timedelta(minutes=20)):
        return "Şu an takip edilen canlı maç yok."
    out = [f"🔴 <b>Canlı maçlar</b> · {gen.astimezone(IST).strftime('%H:%M')} itibarıyla"]
    for m in sorted(ms, key=lambda m: (TIER_LG.get(m["lg"], 9), -m["minute"]))[:30]:
        p = m["p"]
        pk = m["picks"][0] if m.get("picks") else None
        out.append(f"\n{e(m.get('clock') or '')} <b>{e(nm(m['home']))} {m['score'][0]}-{m['score'][1]} {e(nm(m['away']))}</b> <i>({e(m['lgName'])})</i>\n"
                   f"   MS {pct(p['1'])}/{pct(p['X'])}/{pct(p['2'])} · kalan sürede gol {pct(1 - p['NOGOAL'])}"
                   + (f"\n   → {e(pk['label'])} {pct(pk['prob'])} · en az {odds_fmt(pk['minOdds'])}" if pk else ""))
    return "\n".join(out) + link_line()


HELP = ("<b>Skor Tahmin Botu</b>\n"
        "Her sabah günün maç önerilerini, maç sırasında canlı fırsat adaylarını ve günün karnesini gönderir.\n\n"
        "/secimler – günün seçimleri (görsel)\n/nasil – nasıl oynanır\n"
        "/bugun – bugünün tüm maçları\n/guclu – güçlü öneriler\n/orta – orta öneriler\n/riskli – riskli ama yüksek oranlı seçimler (1,75+)\n"
        "/canli – şu an oynanan maçlar\n/mac galatasaray – tek maçın ayrıntısı\n/basket – basketbol · /hokey – NHL · /tenis – tenis\n"
        "/kupon – kuponunu değerlendir (her satıra: takım seçim oran)\n/karne – dünün sonuçları (canlı ve diğer sporlar dahil)\n"
        "/dur – bildirimleri kapat · /start – tekrar aç\n\n"
        "<i>Komutlara birkaç dakika içinde cevap verilir. Olasılıklar garanti değildir.</i>")

COMMANDS = [("secimler", "Günün seçimleri (görsel)"), ("nasil", "Nasıl oynanır"), ("bugun", "Bugünün tüm maçları"), ("guclu", "Güçlü öneriler"), ("orta", "Orta öneriler"), ("riskli", "Riskli seçimler (oran 1,75+)"),
            ("canli", "Şu an oynanan maçlar"), ("mac", "Tek maç: /mac takım"), ("basket", "Basketbol maçları"), ("hokey", "Hokey (NHL) maçları"), ("tenis", "Tenis seçimleri"),
            ("kupon", "Kupon değerlendir"), ("karne", "Dünün sonuçları"),
            ("dur", "Bildirimleri kapat"), ("yardim", "Yardım")]
