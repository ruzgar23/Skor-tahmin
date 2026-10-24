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
HIT = {("MS", 3): .80, ("MS", 2): .67, ("O25", 3): .74, ("O25", 2): .65, ("U25", 2): .63, ("KGV", 2): .64}
UNIT = {3: "1 birim", 2: "½ birim"}
LABEL2KEY = {"MS 1": "1", "MS X": "X", "MS 2": "2", "2,5 Üst": "O25", "2,5 Alt": "U25", "KG Var": "BTTS", "KG Yok": "NBTTS"}


def e(s):
    return html.escape(str(s), quote=False)


def nm(t):
    return TR.get(t, t)


def pct(x):
    return f"%{round(x * 100)}"


def odds_fmt(x):
    return f"{x:.2f}".replace(".", ",")


def pick_of(m):
    p = m["p"]
    return max([("MS 1", p["1"]), ("MS X", p["X"]), ("MS 2", p["2"])], key=lambda t: t[1])


def grade(m):
    p = m["p"]; msk, msp = pick_of(m); c = []
    if msp >= .70: c.append(("MS", msk, msp, 3))
    elif msp >= .60: c.append(("MS", msk, msp, 2))
    if p["O25"] >= .70: c.append(("O25", "2,5 Üst", p["O25"], 3))
    elif p["O25"] >= .60: c.append(("O25", "2,5 Üst", p["O25"], 2))
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


def report_message(history, day, picks=None):
    done = [h for h in history if h.get("res") and ko_local(h).date() == day]
    if not done:
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
    if not rows:
        return None
    head = [f"📊 <b>Karne — {day.strftime('%d.%m.%Y')}</b>"]
    for tier in (3, 2):
        n, k = t[tier]
        if n:
            head.append(f"{TIERNAME[tier]}: {n} seçimin {k}'i tuttu ({pct(k / n)})")
    import extra
    ts = extra.teyit_summary(picks, history, day)
    if ts:
        (n1, w1), (n0, w0) = ts["ok"], ts["bad"]
        head.append(f"Maç önü teyit: {n1} teyitli seçimin {w1}'i tuttu" + (f"; iptal edilen {n0} seçimin {w0}'i tuttu" if n0 else ""))
    return "\n".join(head) + "\n\n" + "\n".join(rows) + "\n\n<i>Tek günlük sonuç şansa çok bağlıdır.</i>"


def live_alert_message(alerts):
    out = ["🔴 <b>Canlı fırsat adayları</b>"]
    for m, pk in alerts:
        st = m.get("stats") or [{}, {}]
        sot = f" · isabetli şut {st[0].get('shotsOnTarget')}-{st[1].get('shotsOnTarget')}" if st[0].get("shotsOnTarget") is not None else ""
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
        "/bugun – bugünün tüm maçları\n/guclu – güçlü öneriler\n/orta – orta öneriler\n"
        "/canli – şu an oynanan maçlar\n/mac galatasaray – tek maçın ayrıntısı\n/basket – basketbol maçları\n"
        "/kupon – kuponunu değerlendir (her satıra: takım seçim oran)\n/karne – dünün sonuçları\n"
        "/dur – bildirimleri kapat · /start – tekrar aç\n\n"
        "<i>Komutlara birkaç dakika içinde cevap verilir. Olasılıklar garanti değildir.</i>")

COMMANDS = [("secimler", "Günün seçimleri (görsel)"), ("nasil", "Nasıl oynanır"), ("bugun", "Bugünün tüm maçları"), ("guclu", "Güçlü öneriler"), ("orta", "Orta öneriler"),
            ("canli", "Şu an oynanan maçlar"), ("mac", "Tek maç: /mac takım"), ("basket", "Basketbol maçları"),
            ("kupon", "Kupon değerlendir"), ("karne", "Dünün sonuçları"),
            ("dur", "Bildirimleri kapat"), ("yardim", "Yardım")]
