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
                   ("İddaa oranı kartta yazan sınırın altındaysa o maçı geç. Tekli oyna; 1 birim = kasanın %2'si. Maçtan ~1 saat önce gelen teyit mesajında İPTAL yazanı oynama.",
                    "Olasılıklar garanti değildir; %70'lik seçim de 10 maçın 3'ünde yatar.")))
    return out


def how_to():
    return ("<b>Nasıl kullanılır?</b>\n"
            "1️⃣ Karttaki maçı iddaa'da bul, <b>OYNA</b> yazan seçime bak.\n"
            "2️⃣ İddaa'nın oranını karttaki <b>≥ oran</b> ile karşılaştır.\n"
            "3️⃣ İddaa oranı <b>eşit ya da yüksekse</b> oyna; düşükse o maçı geç.\n"
            "4️⃣ Tekli oyna. 1 birim = kasanın %2'si: Güçlü 1 birim, Orta ½ birim.\n"
            "5️⃣ Maçtan ~1 saat önce <b>teyit</b> mesajı gelir; ⛔ OYNAMA yazanı oynama.\n"
            "★★★ Güçlü: testte %80 tuttu · ★★☆ Orta: %65 tuttu (teyitle %81 / %66)\n"
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
                       f"   👉 <b>{core.e(r['pick'])}</b> · %{round(r['prob']*100)} · oran ≥ <b>{core.odds_fmt(r['min_odds'])}</b> {star} · {core.UNIT[r['tier']]}")
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


# ---------- çok sayfalı görseller ----------
import pages as PG

SHORT_LG = {"Premier League": "Premier L.", "İskoçya Premiership": "İskoçya 1", "İskoçya Championship": "İskoçya 2",
            "İskoçya League One": "İskoçya 3", "İskoçya League Two": "İskoçya 4", "Yunanistan Süper Lig": "Yunanistan",
            "Şampiyonlar Ligi": "Şamp. Ligi", "Konferans Ligi": "Konf. Ligi", "2. Bundesliga": "Bundesliga 2"}
FOOT = ("★★★ güçlü (testte %74–80 tuttu) · ★★☆ orta (%63–67). Oran, yazan sınırın altındaysa oynama.",
        "Olasılıklar garanti değildir. Kaybetmeyi göze alamayacağın parayla oynama.")


def _short(s):
    w = s.split()
    return w[-1] if len(w) > 1 and w[-1] not in ("Blazers",) else (" ".join(w[-2:]) if len(w) > 1 else s)


def all_matches_images(data, basket, day):
    """Bugünün tüm maçları (futbol + basketbol), lig lig."""
    ms = sorted(core.day_matches(data, day), key=lambda m: (core.TIER_LG.get(m["lg"], 9), m["lgName"], m["ko"]))
    blocks, cur = [], None
    for m in ms:
        if m["lgName"] != cur:
            cur = m["lgName"]; blocks.append(("head", cur))
        mm = dict(m, time=ko_local(m).strftime("%H:%M"), league_short=SHORT_LG.get(m["lgName"], m["lgName"]))
        blocks.append(PG.football_row(mm, core.grade(m), nm))
    bk = sorted(extra.basket_upcoming(basket, hours=30), key=lambda g: g["ko"])
    if bk:
        blocks.append(("head", "Basketbol · " + ", ".join(sorted({g["lg"] for g in bk}))))
        for g in bk:
            gg = dict(g, time=ko_local(g).strftime("%H:%M"), home=_short(g["home"]), away=_short(g["away"]))
            blocks.append(PG.basket_row(gg, extra.basket_grade(g)))
    if not blocks:
        return []
    n = len(ms) + len(bk)
    return PG.paginate("BUGÜNÜN MAÇLARI", f"{tr_date(day)} · {n} maç (futbol + basketbol)", blocks, FOOT)


def report_images(history, day, picks=None, live_bets=None):
    done = [h for h in history if h.get("res") and ko_local(h).date() == day]
    rows, t = [], {3: [0, 0], 2: [0, 0]}
    for h in sorted(done, key=lambda h: h["ko"]):
        g = core.grade(h)
        if not g or g["tier"] < 2:
            continue
        ok = core.settle(core.LABEL2KEY[g["label"]], h["res"])
        if ok is None:
            continue
        t[g["tier"]][0] += 1; t[g["tier"]][1] += ok
        rows.append(PG.result_row(h, g, ok, nm))
    lv = extra.live_day(live_bets, day)
    if not rows and not lv:
        return []
    k = []
    for tier, name in ((3, "güçlü"), (2, "orta")):
        n, w = t[tier]
        if n:
            k.append((f"{w}/{n}", f"{name} seçim tuttu (%{round(100 * w / n)})", PG.GREEN if w / n >= .6 else PG.AMBER))
    tot_n = t[3][0] + t[2][0]; tot_w = t[3][1] + t[2][1]
    if tot_n:
        k.append((f"%{round(100 * tot_w / tot_n)}", "maç öncesi tutma oranı", PG.INK))
    if lv:
        lw = sum(1 for b in lv if b["ok"])
        k.append((f"{lw}/{len(lv)}", f"canlı seçim tuttu (%{round(100 * lw / len(lv))})", PG.GREEN if lw / len(lv) >= .7 else PG.AMBER))
    blocks = [PG.kpi_row(k)]
    ts = extra.teyit_summary(picks, history, day)
    if ts:
        (n1, w1), (n0, w0) = ts["ok"], ts["bad"]
        blocks.append(PG.note_row(f"Maç önü teyitli seçimler: {w1}/{n1} tuttu" + (f" · iptal edilenler: {w0}/{n0} tuttu" if n0 else ""), PG.INK, 56))
    if rows:
        blocks += [("head", "Maç öncesi seçimler")] + rows
    if lv:
        blocks.append(("head", "Canlı seçimler"))
        for b in lv:
            h = dict(home=b["home"], away=b["away"], res=b["res"], lgName=f"{b['lgName']} · {b['minute']}'de verildi, skor {b['s0'][0]}-{b['s0'][1]}")
            blocks.append(PG.result_row(h, dict(label=b["label"], prob=b["prob"]), b["ok"], nm))
    return PG.paginate("DÜNÜN KARNESİ", tr_date(day), blocks, ("Tek günlük sonuç şansa çok bağlıdır; asıl ölçü uzun dönem test.",))


def live_images(matches, title="CANLI FIRSATLAR", sub=None):
    """matches: [(m, pick ya da None)]"""
    if not matches:
        return []
    blocks = [PG.live_row(dict(m, clock=("İY" if m.get("halftime") else (m.get("clock") or ""))), pk, nm) for m, pk in matches]
    return PG.paginate(title, sub or datetime.now(core.IST).strftime("%H:%M itibarıyla"), blocks,
                       ("Canlı oran, yazan sınırın altındaysa oynama; canlı oranlar saniyeler içinde değişir.",), accent=(120, 36, 24))


def live_list_images(live):
    ms = live.get("matches", []) if live else []
    gen = datetime.fromisoformat(live["generated"]) if live else None
    if not ms or (gen and datetime.now(timezone.utc) - gen > timedelta(minutes=20)):
        return []
    ms = sorted(ms, key=lambda m: (core.TIER_LG.get(m["lg"], 9), -m["minute"]))[:24]
    return live_images([(m, (m.get("picks") or [None])[0]) for m in ms], "CANLI MAÇLAR",
                       f"{gen.astimezone(core.IST).strftime('%H:%M')} itibarıyla · {len(ms)} maç")


def move_images(items):
    if not items:
        return []
    blocks = []
    for m, k, old, new, dl in items:
        side = {"1": nm(m["home"]), "2": nm(m["away"]), "X": "Beraberlik"}[k]
        mm = dict(m, lgName=m.get("lgName", m.get("lg", "")))
        blocks.append(PG.move_row(mm, side, old, new, dl, ko_local(m).strftime("%d.%m %H:%M"), nm))
    return PG.paginate("ORAN DÜŞÜŞÜ", "Piyasa açılıştan bu yana belirgin şekilde bir tarafa kaydı", blocks,
                       ("Genelde sakatlık, kadro ya da yoğun para girişi demektir. Oran zaten düştüğü için kendi başına oynama sinyali değildir.",),
                       accent=(110, 30, 20))


def coupon_images(data, basket, body):
    rows, s = extra.coupon_eval(data, basket, body)
    if rows is None:
        return []
    blocks = []
    for r in rows:
        if r["ok"]:
            blocks.append(PG.coupon_row(r["title"], r["meta"], r["sel"], r["prob"], r["odds"], r["ev"] or 0))
        else:
            blocks.append(PG.note_row(f"?  {r['raw']}  —  {r['why']}", PG.RED))
    if s["n"] >= 2:
        items = [(f"%{round(s['p'] * 100)}", f"kuponun tutma olasılığı (~{max(1, round(1 / s['p']))} kuponda 1)", PG.INK)]
        if s["ev"] is not None:
            items.append((PG._odds(s["odds"]), "toplam oran", PG.INK))
            items.append((f"{'+' if s['ev'] >= 0 else ''}{round(s['ev'] * 100)}%", "beklenen getiri",
                          PG.GREEN if s["ev"] > .03 else (PG.AMBER if s["ev"] >= -.03 else PG.RED)))
        blocks = [PG.kpi_row(items)] + blocks
    foot = ["Kombinede büro payı her maçta katlanır; uzun vadede tekli bahisten daha çok kaybettirir."]
    if s["dup"]:
        foot.insert(0, "Aynı maç kuponda iki kez var; seçimler birbirine bağlı, toplam olasılık yanıltıcı olur.")
    return PG.paginate("KUPON DEĞERLENDİRMESİ", f"{s['n']} maç", blocks, tuple(foot))


def basket_match_images(basket, q):
    qn = core.norm(q)
    gs = [g for g in extra.basket_upcoming(basket, hours=72) if qn in core.norm(g["home"]) or qn in core.norm(g["away"])]
    if not gs:
        return []
    g = sorted(gs, key=lambda g: g["ko"])[0]
    blocks = [("head", g["lg"])]
    gg = dict(g, time=ko_local(g).strftime("%H:%M"), home=_short(g["home"]), away=_short(g["away"]))
    blocks.append(PG.basket_row(gg, extra.basket_grade(g)))
    p = g["p"]
    if p.get("hcp"):
        blocks.append(PG.note_row("Handikap (ev sahibi kazanır): " + " · ".join(f"{k.replace('.', ',')} %{round(v*100)}" for k, v in p["hcp"].items()), PG.INK))
    if p.get("tot"):
        blocks.append(PG.note_row("Toplam sayı üst: " + " · ".join(f"{k.replace('.', ',')} %{round(v*100)}" for k, v in p["tot"].items()), PG.INK))
    return PG.paginate(f"{_short(g['home']).upper()} – {_short(g['away']).upper()}", f"{g['lg']} · {tr_date(ko_local(g).date())}", blocks,
                       ("Handikap ve alt/üst çizgileri ~%50'dir; bu marketlerde öneri verilmez.",))


def teyit_images(items):
    if not items:
        return []
    items = sorted(items, key=lambda x: (not x[1]["ok"], x[1]["ko"]))
    blocks = [PG.teyit_row(m, v, ko_local(m).strftime("%H:%M"), nm) for m, v in items]
    n_ok = sum(1 for _, v in items if v["ok"])
    return PG.paginate("MAÇ ÖNÜ TEYİT", f"{n_ok} seçim geçerli · {len(items) - n_ok} iptal", blocks,
                       ("Sabahki seçimin ihtimali maça kadar 2 puan ya da daha fazla düştüyse iptal edilir; testte bu seçimler belirgin şekilde daha az tuttu.",),
                       accent=(21, 60, 50))


def live_won_images(items):
    if not items:
        return []
    blocks = []
    for b in items:
        h = dict(home=b["home"], away=b["away"], res=b["res"], lgName=f"{b['lgName']} · {b['minute']}'de verildi, skor {b['s0'][0]}-{b['s0'][1]}")
        blocks.append(PG.result_row(h, dict(label=b["label"], prob=b["prob"]), True, nm))
    return PG.paginate("WON · CANLI SEÇİM TUTTU", f"{len(items)} canlı seçim kazandı", blocks,
                       ("Canlı seçimlerin tamamı (tutan ve tutmayan) ertesi sabah karnede.",), accent=(29, 107, 71))
