"""Verilerden görsel kartları ve sade metin mesajlarını üretir."""
from datetime import datetime, timedelta, timezone
import core, extra, cards
from core import nm, ko_local

AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def tr_date(d):
    return f"{d.day} {AY[d.month - 1]} {GUN[d.weekday()]}"


def _row(m, pick, prob, min_odds, tier, league=None):
    return dict(time=ko_local(m).strftime("%H:%M"), league=league or m["lgName"], home=nm(m["home"]), away=nm(m["away"]),
                pick=pick.upper(), prob=prob, min_odds=min_odds, tier=tier)


def daily_sections(data, basket, day, max_mid=8, max_cards=4):
    ms = core.day_matches(data, day)
    graded = [(m, core.grade(m)) for m in ms]
    strong = sorted([x for x in graded if x[1] and x[1]["tier"] == 3], key=lambda x: (x[0]["ko"], -x[1]["prob"]))
    mid = sorted([x for x in graded if x[1] and x[1]["tier"] == 2], key=lambda x: -x[1]["prob"])[:max_mid]
    mid.sort(key=lambda x: x[0]["ko"])
    secs = [("Güçlü seçimler", [_row(m, g["label"], g["prob"], g["minOdds"], 3) for m, g in strong]),
            ("Orta seçimler", [_row(m, g["label"], g["prob"], g["minOdds"], 2) for m, g in mid])]
    kr = []
    for m in ms:
        pk = extra.card_pick(m)
        if pk:
            kr.append((m, pk))
    kr.sort(key=lambda x: -x[1]["gap"])
    secs.append(("Kart seçimleri", [_row(m, pk["label"], pk["prob"], pk["minOdds"], 2) for m, pk in kr[:max_cards]]))
    bk = []
    for g in extra.basket_upcoming(basket):
        gr = extra.basket_grade(g)
        if gr:
            short = lambda s: s.split()[-1] if s.split()[-1] not in ("Blazers",) else "Trail Blazers"
            bk.append(dict(time=ko_local(g).strftime("%H:%M"), league=g["lg"], home=short(g["home"]), away=short(g["away"]),
                           pick=gr["label"].upper(), prob=gr["prob"], min_odds=gr["minOdds"], tier=gr["tier"]))
    secs.append(("Basketbol (NBA)", sorted(bk, key=lambda r: r["time"])))
    return secs, len(ms)


def daily_images(data, basket, day, per_page=8):
    """Günün seçimlerini en fazla per_page satırlık resimlere böler."""
    secs, n = daily_sections(data, basket, day)
    total = sum(len(r) for _, r in secs)
    if not total:
        return []
    pages, cur, cnt = [], [], 0
    for head, rows in secs:
        i = 0
        while i < len(rows):
            take = rows[i:i + (per_page - cnt)]
            cur.append((head if i == 0 else head + " (devam)", take)); cnt += len(take); i += len(take)
            if cnt >= per_page:
                pages.append(cur); cur, cnt = [], 0
    if cur:
        pages.append(cur)
    out = []
    for k, pg in enumerate(pages, 1):
        sub = f"{tr_date(day)} · {total} seçim" + (f" · sayfa {k}/{len(pages)}" if len(pages) > 1 else "")
        out.append(cards.daily_card("GÜNÜN SEÇİMLERİ", sub, pg,
                   ("İddaa oranı kartta yazan sınırın altındaysa o maçı geç. Tekli oyna, her bahse kasanın küçük ve aynı bir payını (örn. %2) koy.",
                    "Olasılıklar garanti değildir; %70'lik seçim de 10 maçın 3'ünde yatar.")))
    return out


def how_to():
    return ("<b>Nasıl kullanılır?</b>\n"
            "1️⃣ Karttaki maçı iddaa'da bul, <b>OYNA</b> yazan seçime bak.\n"
            "2️⃣ İddaa'nın oranını karttaki <b>≥ oran</b> ile karşılaştır.\n"
            "3️⃣ İddaa oranı <b>eşit ya da yüksekse</b> oyna; düşükse o maçı geç.\n"
            "4️⃣ Tekli oyna, her bahse kasanın küçük ve aynı bir payını koy (örn. %2).\n"
            "★★★ Güçlü: testte %74–80 tuttu · ★★☆ Orta: %63–67 tuttu\n"
            "Ayrıntı: /mac takım · kupon kontrolü: /kupon")


def daily_text(data, basket, day):
    """Görselin altına kısa, kopyalanabilir liste."""
    secs, n = daily_sections(data, basket, day)
    out = [f"⚽ <b>Günün seçimleri — {tr_date(day)}</b>"]
    for head, rows in secs:
        if not rows:
            continue
        out.append(f"\n<b>{head}</b>")
        for r in rows:
            star = "★★★" if r["tier"] == 3 else "★★☆"
            out.append(f"{r['time']} {core.e(r['home'])} – {core.e(r['away'])}\n"
                       f"   👉 <b>{core.e(r['pick'])}</b> · %{round(r['prob']*100)} · oran ≥ <b>{core.odds_fmt(r['min_odds'])}</b> {star}")
    if len(out) == 1:
        out.append("Bugün belirgin bir seçim yok; zorlama.")
    return "\n".join(out) + core.link_line()


def match_image(data, q):
    qn = core.norm(q)
    hits = [m for m in data.get("matches", []) if ko_local(m) > datetime.now(core.IST) - timedelta(hours=2)
            and (qn in core.norm(nm(m["home"])) or qn in core.norm(nm(m["away"])) or qn in core.norm(m["home"]) or qn in core.norm(m["away"]))]
    if not hits:
        return None
    m = dict(sorted(hits, key=lambda m: m["ko"])[0])
    m["home_tr"], m["away_tr"] = nm(m["home"]), nm(m["away"])
    lk = ko_local(m); m["when"] = f"{lk.day} {AY[lk.month - 1]} {lk.strftime('%H:%M')}"
    g = core.grade(m)
    if g:
        g = dict(g); g["label"] = g["label"].upper()
    lines = []
    if m.get("cards"):
        c = m["cards"]; lines.append(f"Kart ortalaması {c['mean']:.1f} · 4,5 üst %{round(c['over'].get('4.5', 0)*100)}".replace(".", ","))
        pk = extra.card_pick(m)
        if pk: lines[-1] += f" · öneri: {pk['label']} %{round(pk['prob']*100)}"
    mv = m.get("move")
    if mv:
        big = [k for k, d in mv["d"].items() if abs(d) >= .03]
        if big:
            lines.append("Oran hareketi: " + " · ".join(f"MS {k} {core.odds_fmt(mv['open'][k])}→{core.odds_fmt(mv['now'][k])}" for k in big))
    return cards.match_card(m, g, lines)
