"""Kart/korner, basketbol, oran hareketi ve kupon değerlendirme."""
import math, re
from datetime import datetime, timedelta, timezone
from scipy.stats import norm as N
import core
from core import e, nm, pct, odds_fmt, ko_local, IST

CARD_MIN = 0.68   # testte "%70+" kart seçimlerinin %71–77'si tuttu
MOVE_MIN = 0.06   # oran hareketi uyarı eşiği (olasılık puanı)
BASKET_SD = {"NBA": (14.0, 22.5), "WNBA": (11.0, 17.0)}


def line_fmt(x):
    return f"{x:.1f}".replace(".", ",")


# ---------- kart / korner ----------
def card_pick(m):
    c = m.get("cards")
    if not c:
        return None
    best = None
    for l, po in c["over"].items():
        b = (c.get("base") or {}).get(l, 0.5)
        for side, p, pb in (("Üst", po, b), ("Alt", 1 - po, 1 - b)):
            gap = p - pb  # lig ortalamasından ne kadar ayrışıyor
            if p >= CARD_MIN and gap >= 0.08 and (not best or gap > best["gap"]):
                best = dict(label=f"Kart {line_fmt(float(l))} {side}", prob=p, minOdds=1.03 / p, gap=gap, base=pb)
    return best


def cards_section(data, day, limit=10):
    rows = []
    for m in core.day_matches(data, day):
        pk = card_pick(m)
        if pk:
            rows.append((m, pk))
    if not rows:
        return ""
    rows.sort(key=lambda x: -x[1]["gap"])
    out = ["🟨 <b>Kart önerileri</b> (lig ortalamasından en çok ayrışan maçlar; testte %70+ seçimlerin %71–77'si tuttu)"]
    for m, pk in rows[:limit]:
        out.append(core.pick_line(m, pk) + f" <i>(lig ort. {pct(pk['base'])})</i>")
    return "\n".join(out) + "\n"


def stat_lines(m):
    out = []
    c = m.get("cards")
    if c:
        out.append(f"Kart (sarı+kırmızı): ort. {line_fmt(c['mean'])} · " +
                   " · ".join(f"{line_fmt(float(l))}Ü {pct(p)}" for l, p in c["over"].items()) + (" · hakem etkisi dahil" if c.get("ref") else ""))
    k = m.get("corners")
    if k:
        out.append(f"Korner: ort. {line_fmt(k['mean'])} · " + " · ".join(f"{line_fmt(float(l))}Ü {pct(p)}" for l, p in k["over"].items())
                   + " <i>(korner tahmini lig ortalamasından çok az iyi; bilgi amaçlı)</i>")
    mv = m.get("move")
    if mv:
        big = [(k_, d) for k_, d in mv["d"].items() if abs(d) >= 0.03]
        if big:
            out.append("Oran hareketi: " + " · ".join(f"{k_} {odds_fmt(mv['open'][k_])}→{odds_fmt(mv['now'][k_])}" for k_, _ in big))
    return out


# ---------- basketbol ----------
def basket_grade(g):
    p = g["p"]; fav = "1" if p["1"] >= p["2"] else "2"; pr = p[fav]
    if pr >= .75: return dict(label=f"MS {fav}", prob=pr, tier=3, minOdds=1.03 / pr)
    if pr >= .65: return dict(label=f"MS {fav}", prob=pr, tier=2, minOdds=1.03 / pr)
    return None


def basket_upcoming(basket, hours=26):
    now = datetime.now(timezone.utc)
    return [g for g in (basket or {}).get("games", [])
            if now < datetime.fromisoformat(g["ko"]) < now + timedelta(hours=hours) and "p" in g]


def basket_line(g):
    p = g["p"]; gr = basket_grade(g)
    s = (f"{ko_local(g).strftime('%d.%m %H:%M')} · <b>{e(g['home'])} – {e(g['away'])}</b> <i>({e(g['lg'])})</i>\n"
         f"   MS 1 {pct(p['1'])} · 2 {pct(p['2'])}")
    if g["odds"].get("spread") is not None:
        s += f" · handikap {line_fmt(g['odds']['spread'])}"
    if p.get("exp_total"):
        s += f" · toplam {line_fmt(p['exp_total'])}"
    if gr:
        s += f"\n   → <b>{e(gr['label'])}</b> {pct(gr['prob'])} · iddaa en az <b>{odds_fmt(gr['minOdds'])}</b> ({core.TIERNAME[gr['tier']]})"
    return s


def basket_section(basket):
    gs = basket_upcoming(basket)
    if not gs:
        return ""
    picks = [g for g in gs if basket_grade(g)]
    out = [f"🏀 <b>Basketbol</b> ({len(gs)} maç; favoriler testte: Güçlü %82, Orta %73 kazandı. Handikap ve alt/üst ~%50, öneri yok)"]
    out += [basket_line(g) for g in sorted(picks, key=lambda g: g["ko"])] or ["Bugün belirgin favori yok."]
    out.append("Tüm basketbol maçları: /basket")
    return "\n".join(out) + "\n"


def basket_message(basket):
    gs = basket_upcoming(basket, hours=48)
    if not gs:
        return "Önümüzdeki 48 saatte basketbol maçı yok."
    return "🏀 <b>Basketbol maçları</b>\n\n" + "\n".join(basket_line(g) for g in sorted(gs, key=lambda g: g["ko"])) + core.FOOTER


def basket_match(basket, q):
    qn = core.norm(q)
    hits = [g for g in basket_upcoming(basket, hours=72) if qn in core.norm(g["home"]) or qn in core.norm(g["away"])]
    if not hits:
        return None
    g = sorted(hits, key=lambda g: g["ko"])[0]; p = g["p"]
    lines = [basket_line(g)]
    if p.get("hcp"):
        lines.append("Handikap (ev sahibi kazanır): " + " · ".join(f"{k.replace('.', ',')} {pct(v)}" for k, v in p["hcp"].items()))
    if p.get("tot"):
        lines.append("Toplam sayı üst: " + " · ".join(f"{k.replace('.', ',')} {pct(v)}" for k, v in p["tot"].items()))
    return "\n".join(lines) + core.link_line()


# ---------- oran hareketi ----------
def move_alerts(data, basket, seen, hours=24):
    """Açılıştan bu yana olasılığı MOVE_MIN kadar artan (oranı düşen) taraflar."""
    now = datetime.now(timezone.utc); out = []
    for m in data.get("matches", []):
        mv = m.get("move"); ko = datetime.fromisoformat(m["ko"])
        if not mv or not (now < ko < now + timedelta(hours=hours)):
            continue
        for k in ("1", "X", "2"):
            if mv["d"][k] >= MOVE_MIN and f"{m['id']}|{k}" not in seen:
                out.append((m, k, mv["open"][k], mv["now"][k], mv["d"][k])); seen[f"{m['id']}|{k}"] = now.isoformat()
    for g in basket_upcoming(basket, hours):
        p = g["p"]
        if p.get("open1") is None:
            continue
        d1 = p["1"] - p["open1"]
        for k, d in (("1", d1), ("2", -d1)):
            if d >= MOVE_MIN and f"{g['id']}|{k}" not in seen:
                o = g["odds"]; old = o["h0"] if k == "1" else o["a0"]; new = o["h"] if k == "1" else o["a"]
                out.append((g, k, old, new, d)); seen[f"{g['id']}|{k}"] = now.isoformat()
    return out


def move_message(items):
    out = ["📉 <b>Oran düşüşü</b> (piyasa açılıştan bu yana belirgin şekilde bir tarafa kaydı)"]
    for m, k, old, new, d in items:
        side = {"1": nm(m["home"]), "2": nm(m["away"]), "X": "Beraberlik"}[k]
        out.append(f"\n{ko_local(m).strftime('%d.%m %H:%M')} · <b>{e(nm(m['home']))} – {e(nm(m['away']))}</b> <i>({e(m['lgName'])})</i>\n"
                   f"   {e(side)}: {odds_fmt(old)} → <b>{odds_fmt(new)}</b> (olasılık +{round(d * 100)} puan)")
    out.append("\n<i>Genelde sakatlık, kadro ya da yoğun para girişi demektir. Oran zaten düştüğü için kendi başına oynama sinyali değildir.</i>")
    return "\n".join(out)


# ---------- kupon ----------
SEL = [
    (r"^(ms)?1$", "1"), (r"^(ms)?x$|^(ms)?0$|^beraber(lik)?$", "X"), (r"^(ms)?2$", "2"),
    (r"^1x$|^1-x$", "1X"), (r"^x2$|^x-2$", "X2"), (r"^12$|^1-2$", "12"),
    (r"^kg(var)?$|^kgv$|^kg-?var$", "BTTS"), (r"^kg-?yok$|^kgy$", "NBTTS"),
    (r"^iy-?1$", "HT1"), (r"^iy-?x$|^iy-?0$", "HTX"), (r"^iy-?2$", "HT2"),
]
OVER = re.compile(r"^(?:(?P<k>kart|korner)-?)?(?P<l>\d+[.,]5)?(?P<s>ü|u|üst|ust|alt|a)(?P<l2>\d+[.,]5)?$")


def parse_sel(tokens):
    """Son 1–3 sözcükten seçim çıkarır: (anahtar, sözcük sayısı)."""
    for n in (3, 2, 1):
        if len(tokens) < n:
            continue
        s = "".join(tokens[-n:]).lower().replace("ı", "i")
        for pat, k in SEL:
            if re.match(pat, s):
                return (k, None, None), n
        m = OVER.match(s.replace("üst", "ü").replace("ust", "ü"))
        if m:
            line = m.group("l") or m.group("l2")
            line = float(line.replace(",", ".")) if line else None
            side = "O" if m.group("s") in ("ü", "u") else "U"
            return ((m.group("k") or "gol"), side, line), n
    return None, 0


def parse_line(raw):
    toks = raw.replace("\t", " ").split()
    odds = None
    if toks and re.match(r"^\d+[.,]\d+$", toks[-1]) and float(toks[-1].replace(",", ".")) > 1:
        # "üst 2.5" gibi bir çizgi değilse orandır (çizgiler ,5 ile biter)
        is_line = re.match(r"^\d+[.,]5$", toks[-1]) and len(toks) >= 2 and toks[-2].lower() in ("üst", "ust", "alt", "ü", "a")
        if not is_line:
            odds = float(toks.pop().replace(",", "."))
    sel, n = parse_sel(toks)
    if not sel:
        return None
    team = " ".join(toks[:-n]).strip()
    return dict(team=team, sel=sel, odds=odds, raw=raw)


def find_match(data, basket, q):
    qn = core.norm(q)
    if len(qn) < 3:
        return None, None
    now = datetime.now(IST)
    fb = [m for m in data.get("matches", []) if ko_local(m) > now - timedelta(hours=2)
          and any(qn in core.norm(x) for x in (nm(m["home"]), nm(m["away"]), m["home"], m["away"]))]
    if fb:
        return sorted(fb, key=lambda m: m["ko"])[0], "futbol"
    bk = [g for g in (basket or {}).get("games", []) if qn in core.norm(g["home"]) or qn in core.norm(g["away"])]
    if bk:
        return sorted(bk, key=lambda g: g["ko"])[0], "basketbol"
    return None, None


def sel_prob(m, kind, sel):
    key, side, line = sel
    if kind == "basketbol":
        p = m["p"]
        if side is None:
            if key in ("1", "2"): return p[key], f"MS {key}"
            return None, "basketbolda bu seçim yok"
        if key != "gol":
            return None, "basketbolda bu seçim yok"
        if line is None: line = p.get("exp_total")
        if line is None: return None, "toplam sayı çizgisi yok"
        sd = BASKET_SD.get(m["lg"], BASKET_SD["NBA"])[1]
        po = float(1 - N.cdf(line, p["exp_total"], sd))
        return (po if side == "O" else 1 - po), f"{line_fmt(line)} {'Üst' if side == 'O' else 'Alt'}"
    p = m["p"]
    if side is None:
        lbl = {"1": "MS 1", "X": "MS X", "2": "MS 2", "1X": "1X", "X2": "X2", "12": "12", "BTTS": "KG Var",
               "NBTTS": "KG Yok", "HT1": "İY 1", "HTX": "İY X", "HT2": "İY 2"}[key]
        return (1 - p["BTTS"] if key == "NBTTS" else p[key]), lbl
    if key == "gol":
        line = line or 2.5
        k = {1.5: "O15", 2.5: "O25", 3.5: "O35"}.get(line)
        if not k: return None, f"{line_fmt(line)} gol çizgisi desteklenmiyor (1,5 · 2,5 · 3,5)"
        return (p[k] if side == "O" else 1 - p[k]), f"{line_fmt(line)} {'Üst' if side == 'O' else 'Alt'}"
    st = m.get("cards" if key == "kart" else "corners")
    if not st: return None, f"bu maç için {key} tahmini yok"
    line = line or (4.5 if key == "kart" else 9.5)
    po = st["over"].get(str(line))
    if po is None: return None, f"{key} {line_fmt(line)} çizgisi yok ({', '.join(line_fmt(float(x)) for x in st['over'])})"
    return (po if side == "O" else 1 - po), f"{key.capitalize()} {line_fmt(line)} {'Üst' if side == 'O' else 'Alt'}"


COUPON_HELP = ("Kullanım (her satıra bir maç: takım, seçim, oran):\n<code>/kupon\ngalatasaray 1 1.85\narsenal 2.5 üst 1.70\nbarcelona kg 1.65\n"
               "fenerbahçe kart 4.5 üst 1.80\nlakers 2 1.95</code>\n\n"
               "Seçimler: 1 · X · 2 · 1X · X2 · 12 · üst/alt (1.5, 2.5, 3.5) · kg · kgyok · iy1/iyx/iy2 · kart 4.5 üst · korner 9.5 alt. "
               "Basketbol: 1 · 2 · üst/alt 225.5")


def coupon_eval(data, basket, body):
    """Kupon satırlarını değerlendirir. Dönüş: (satırlar, özet) ya da (None, None)."""
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    if not lines:
        return None, None
    rows, tot_p, tot_o, all_odds, seen, n_ok, dup = [], 1.0, 1.0, True, set(), 0, False
    for raw in lines[:15]:
        pl = parse_line(raw)
        if not pl:
            rows.append(dict(ok=False, raw=raw, why="Seçim anlaşılamadı.")); all_odds = False; continue
        m, kind = find_match(data, basket, pl["team"])
        if not m:
            rows.append(dict(ok=False, raw=raw, why=f"“{pl['team']}” için yaklaşan maç bulunamadı.")); all_odds = False; continue
        pr, lbl = sel_prob(m, kind, pl["sel"])
        title = f"{nm(m['home'])} – {nm(m['away'])}"
        if pr is None:
            rows.append(dict(ok=False, raw=raw, why=f"{title}: {lbl}")); all_odds = False; continue
        n_ok += 1
        if m["id"] in seen:
            dup = True
        seen.add(m["id"]); tot_p *= pr
        ev = None
        if pl["odds"]:
            tot_o *= pl["odds"]; ev = pr * pl["odds"] - 1
        else:
            all_odds = False
        rows.append(dict(ok=True, title=title, meta=f"{m['lgName']} · {ko_local(m).strftime('%d.%m %H:%M')}"
                         + (" · piyasa oranı yok, yalnızca model" if kind == "futbol" and m.get("src") != "piyasa" else ""),
                         sel=lbl, prob=pr, odds=pl["odds"], ev=ev))
    summ = dict(n=n_ok, p=tot_p, odds=tot_o if all_odds and n_ok else None,
                ev=(tot_p * tot_o - 1) if all_odds and n_ok else None, dup=dup)
    return rows, summ


def coupon_message(data, basket, body):
    rows, s = coupon_eval(data, basket, body)
    if rows is None:
        return COUPON_HELP
    out = ["🧾 <b>Kupon değerlendirmesi</b>"]
    for r in rows:
        if not r["ok"]:
            out.append(f"\n❓ <i>{e(r['raw'])}</i>\n   {e(r['why'])}"); continue
        t = f"\n<b>{e(r['title'])}</b> <i>({e(r['meta'])})</i>\n   {e(r['sel'])}: olasılık {pct(r['prob'])} · adil oran {odds_fmt(1 / r['prob'])}"
        if r["odds"]:
            ev = r["ev"]; tag = "✅ değerli" if ev > 0.03 else ("➖ sınırda" if ev >= -0.03 else "❌ düşük oran")
            t += f"\n   Senin oranın {odds_fmt(r['odds'])} → beklenen {'+' if ev >= 0 else ''}{round(ev * 100)}% {tag}"
        out.append(t)
    if s["dup"]:
        out.append("\n⚠️ Aynı maç kuponda iki kez var; seçimler birbirine bağlı olduğu için toplam olasılık yanıltıcı olur.")
    if s["n"] >= 2:
        out.append(f"\n<b>Kuponun tutma olasılığı: {pct(s['p'])}</b> (yaklaşık {max(1, round(1 / s['p']))} kuponda 1)")
        if s["ev"] is not None:
            out.append(f"Toplam oran {odds_fmt(s['odds'])} · beklenen getiri {'+' if s['ev'] >= 0 else ''}{round(s['ev'] * 100)}%")
        out.append("<i>Maç sayısı arttıkça büro payı her maçta katlanır; kombineler uzun vadede tekli bahislerden daha çok kaybettirir.</i>")
    return "\n".join(out)


# ---------- maç önü teyit ve birim ----------
# Backtest (49 bin maç, 8 sezon): sabah verilen seçimin piyasa olasılığı maça kadar 2 puan ya da daha fazla
# aleyhe kaydıysa o seçim belirgin şekilde daha az tutuyor. Bu seçimleri maç önü iptal etmek tutma oranını
# Güçlü'de %79,7 → %80,5, Orta'da %65,2 → %66,4'e çıkardı; etki 8 sezonun hepsinde aynı yöndeydi.
TEYIT_DROP = 0.02
UNIT = {3: "1 birim", 2: "½ birim"}


def cur_prob(m, g):
    """Aynı seçimin şu anki olasılığı (m: güncel maç verisi, g: sabahki seçim)."""
    p = m["p"]; fam = g["fam"]
    if fam == "MS":
        return p[g["label"].split()[-1]]
    return {"O25": p["O25"], "U25": 1 - p["O25"], "KGV": p["BTTS"], "KGY": 1 - p["BTTS"]}[fam]


def daily_picks(data, day, max_mid=8):
    """Günlük mesajda gönderilen seçimler (görselle aynı seçim kuralı)."""
    graded = [(m, core.grade(m)) for m in core.day_matches(data, day)]
    strong = [x for x in graded if x[1] and x[1]["tier"] == 3]
    mid = sorted([x for x in graded if x[1] and x[1]["tier"] == 2], key=lambda x: -x[1]["prob"])[:max_mid]
    return {m["id"]: dict(fam=g["fam"], label=g["label"], prob=g["prob"], tier=g["tier"], ko=m["ko"],
                          home=m["home"], away=m["away"], lgName=m["lgName"], minOdds=g["minOdds"], lg=m["lg"])
            for m, g in strong + mid}


def teyit_due(picks, now, lo=15, hi=100):
    """Maçına lo..hi dakika kalan, henüz teyit edilmemiş seçimler. Kaçırılanlar sessizce kapanır."""
    due = []
    for k, v in picks.items():
        if v.get("done"):
            continue
        ko = datetime.fromisoformat(v["ko"])
        if ko < now + timedelta(minutes=lo):
            v["done"] = True; v["missed"] = True
        elif ko <= now + timedelta(minutes=hi):
            due.append(k)
    return due


def teyit_message(items):
    ok = [x for x in items if x[1]["ok"]]; bad = [x for x in items if not x[1]["ok"]]
    out = ["⏱ <b>Maç önü teyit</b> (oranlar son kez kontrol edildi)"]
    for m, v in sorted(ok, key=lambda x: x[1]["ko"]):
        out.append(f"\n✅ {ko_local(m).strftime('%H:%M')} <b>{e(nm(m['home']))} – {e(nm(m['away']))}</b>\n"
                   f"   👉 OYNA: <b>{e(v['label'].upper())}</b> · %{round(v['cur'] * 100)} · oran ≥ <b>{odds_fmt(1.03 / v['cur'])}</b> · {UNIT.get(v['tier'], '')}")
    for m, v in sorted(bad, key=lambda x: x[1]["ko"]):
        out.append(f"\n⛔ {ko_local(m).strftime('%H:%M')} <b>{e(nm(m['home']))} – {e(nm(m['away']))}</b>\n"
                   f"   OYNAMA: {e(v['label'])} · ihtimal %{round(v['prob'] * 100)} → %{round(v['cur'] * 100)} düştü")
    out.append("\n<i>Sabahki seçimin ihtimali maça kadar 2 puan ya da daha fazla düştüyse iptal edilir; testte bu seçimler belirgin şekilde daha az tuttu.</i>")
    return "\n".join(out)


def teyit_summary(picks, history, day):
    """Karne için: o günün iptal edilen ve teyitli seçimlerinin sonucu."""
    res = {h["id"]: h.get("res") for h in history if h.get("res")}
    s = {"ok": [0, 0], "bad": [0, 0]}
    for k, v in (picks or {}).items():
        if v.get("cur") is None or ko_local(v).date() != day or not res.get(k):
            continue
        key = core.LABEL2KEY[v["label"]]; won = core.settle(key, res[k])
        if won is None:
            continue
        b = s["ok" if v["ok"] else "bad"]; b[0] += 1; b[1] += won
    return s if (s["ok"][0] or s["bad"][0]) else None


# ---------- canlı seçim karnesi ----------
def live_settle(k, s0, s, final):
    """Canlı seçimin sonucu. s0: bildirim anındaki skor, s: şimdiki skor. final=False iken yalnızca kesinleşenler döner."""
    a, b = s; t = a + b; t0 = s0[0] + s0[1]
    if k == "GOAL" and t > t0: return True
    if k == "NOGOAL" and t > t0: return False
    if k == "BTTS" and a > 0 and b > 0: return True
    if k == "NBTTS" and a > 0 and b > 0: return False
    if k[0] in "OU" and k not in ("1", "X", "2"):
        try:
            line = float(k[1:])
        except ValueError:
            line = None
        if line is not None and t > line:
            return k[0] == "O"
    if not final:
        return None
    return {"1": a > b, "X": a == b, "2": a < b, "1X": a >= b, "X2": a <= b, "12": a != b,
            "BTTS": a > 0 and b > 0, "NBTTS": not (a > 0 and b > 0), "GOAL": t > t0, "NOGOAL": t == t0}.get(
        k, (t > float(k[1:])) == (k[0] == "O") if k[0] in "OU" else None)


def live_won_message(items):
    won = [b for b in items if b["ok"]]; lost = [b for b in items if not b["ok"]]
    out = []
    if won:
        out.append("🏆 <b>WON — canlı seçim tuttu!</b>")
        for b in won:
            out.append(f"✅ <b>{e(nm(b['home']))} {b['res'][0]}-{b['res'][1]} {e(nm(b['away']))}</b> <i>({e(b['lgName'])})</i>\n"
                       f"   {e(b['label'])} · {b['minute']}'de %{round(b['prob'] * 100)} ile verilmişti")
    if lost:
        out.append(("\n" if won else "") + "❌ <b>LOST — canlı seçim tutmadı</b>")
        for b in lost:
            out.append(f"❌ <b>{e(nm(b['home']))} {b['res'][0]}-{b['res'][1]} {e(nm(b['away']))}</b> <i>({e(b['lgName'])})</i>\n"
                       f"   {e(b['label'])} · {b['minute']}'de %{round(b['prob'] * 100)} ile verilmişti")
    return "\n".join(out)


def results_message(items):
    """items: [(v, sonuç metni, tuttu mu)] — günün seçimlerinden biten maçlar."""
    w = sum(1 for _, _, ok in items if ok)
    out = [f"📣 <b>Maç sonuçları</b> · {len(items)} seçimin {w}'i tuttu"]
    for v, txt, ok in items:
        tag = " <i>(maç önü iptal edilmişti)</i>" if v.get("ok") is False and v.get("sport") is None else ""
        out.append(f"{'✅ WON' if ok else '❌ LOST'} · <b>{e(nm(v['home']))} – {e(nm(v['away']))}</b> {e(txt)}\n"
                   f"   {e(v['label'])} %{round(v['prob'] * 100)}{tag}")
    return "\n".join(out)


def live_day(bets, day):
    return sorted([b for b in (bets or {}).values() if b.get("ok") in (True, False)
                   and datetime.fromisoformat(b["ts"]).astimezone(IST).date() == day], key=lambda b: b["ts"])


def live_report_lines(bets, day):
    rows = live_day(bets, day)
    if not rows:
        return []
    w = sum(1 for b in rows if b["ok"])
    out = [f"\n🔴 <b>Canlı seçimler:</b> {len(rows)} seçimin {w}'i tuttu ({pct(w / len(rows))})"]
    for b in rows:
        out.append(f"{'✅' if b['ok'] else '❌'} {e(nm(b['home']))} {b['res'][0]}-{b['res'][1]} {e(nm(b['away']))} · {e(b['label'])} ({b['minute']}') {pct(b['prob'])}")
    return out


# ---------- hokey (NHL) ve tenis ----------
def _surname(n):
    return n.split()[-1] if n else n


def other_label(g):
    """iddaa'daki adıyla seçim etiketi."""
    pk = g.get("pick")
    if not pk:
        return None
    if g["sport"] == "tenis":
        side = "1" if pk["winner"] == g["home"] else "2"
        return f"MS {side} · {_surname(pk['winner']).upper()}"
    return {"1X": "ÇİFTE ŞANS 1X", "X2": "ÇİFTE ŞANS X2", "4,5 Üst": "4,5 ÜST"}.get(pk["label"], pk["label"])


def other_upcoming(basket, hours=26, sport=None, picks_only=False):
    now = datetime.now(timezone.utc)
    gs = [g for g in ((basket or {}).get("other") or {}).get("games", [])
          if now < datetime.fromisoformat(g["ko"]) < now + timedelta(hours=hours)
          and (sport is None or g["sport"] == sport) and (g.get("pick") or not picks_only)]
    return sorted(gs, key=lambda g: g["ko"])


def other_day_picks(basket, day, max_tennis_strong=6, max_tennis_mid=4):
    """O günün hokey ve tenis seçimleri: [(bölüm, [(g, etiket)])]."""
    # takvim günü yerine önümüzdeki 24 saat: NHL maçları Türkiye saatiyle gece oynanır
    gs = other_upcoming(basket, hours=24, picks_only=True)
    hk = [g for g in gs if g["sport"] == "hokey"]
    tn = [g for g in gs if g["sport"] == "tenis"]
    tn = (sorted([g for g in tn if g["pick"]["tier"] == 3], key=lambda g: -g["pick"]["prob"])[:max_tennis_strong]
          + sorted([g for g in tn if g["pick"]["tier"] == 2], key=lambda g: -g["pick"]["prob"])[:max_tennis_mid])
    return [("Hokey (NHL, normal süre)", hk), ("Tenis (ATP/WTA)", sorted(tn, key=lambda g: g["ko"]))]


def other_list_message(basket, sport):
    gs = other_upcoming(basket, hours=30, sport=sport, picks_only=(sport == "tenis"))
    head = {"hokey": "🏒 <b>Hokey (NHL)</b> — iddaa'da hokey MS normal süredir", "tenis": "🎾 <b>Tenis seçimleri</b> (ATP/WTA, Elo modeli)"}[sport]
    if not gs:
        return head + "\n\nÖnümüzdeki 30 saatte " + ("seçim yok." if sport == "tenis" else "maç yok.")
    out = [head, ""]
    for g in gs:
        lab = other_label(g)
        out.append(f"{ko_local(g).strftime('%d.%m %H:%M')} · <b>{e(g['home'])} – {e(g['away'])}</b> <i>({e(g['lgName'])})</i>\n   {e(g['info'])}"
                   + (f"\n   👉 OYNA: <b>{e(lab)}</b> · %{round(g['pick']['prob'] * 100)} · oran ≥ <b>{odds_fmt(g['pick']['minOdds'])}</b> ({core.TIERNAME[g['pick']['tier']]})" if lab else ""))
    return "\n".join(out) + core.FOOTER


def other_picks_store(basket, day):
    """Karne için: günün NBA, hokey ve tenis seçimleri."""
    out = {}
    for sec, gs in other_day_picks(basket, day):
        for g in gs:
            pk = g["pick"]
            out[g["id"]] = dict(sport=g["sport"], label=other_label(g), key=pk["label"], winner=pk.get("winner"), prob=pk["prob"],
                                tier=pk["tier"], ko=g["ko"], home=g["home"], away=g["away"], lgName=g["lgName"], day=str(day))
    for g in basket_upcoming(basket):
        gr = basket_grade(g)
        if gr:
            out[g["id"]] = dict(sport="basketbol", label=gr["label"], key=gr["label"].split()[-1], prob=gr["prob"], tier=gr["tier"],
                                ko=g["ko"], home=g["home"], away=g["away"], lgName=g["lg"], day=str(day))
    return out


def other_settle(v, basket):
    """(sonuç metni, tuttu mu) ya da None."""
    if v["sport"] == "basketbol":
        r = next((g for g in (basket or {}).get("results", []) if g["id"] == v.get("id")), None)
        if not r or not r.get("res"):
            return None
        a, b = r["res"]; return f"{a}-{b}", (a > b) == (v["key"] == "1")
    res = next((g for g in ((basket or {}).get("other") or {}).get("results", []) if g["id"] == v.get("id")), None)
    if not res:
        return None
    if v["sport"] == "tenis":
        return f"kazanan {_surname(res['res_w'])}", res["res_w"] == v["winner"]
    a, b = res["res"]; ot = res.get("ot")
    import others
    ok = others.nhl_settle(v["key"], [a, b], ot)
    return (f"{a}-{b}" + (" (uzatma)" if ot else "")), ok


def other_day_results(opicks, basket, day):
    rows = []
    for k, v in (opicks or {}).items():
        if v.get("day") != str(day):
            continue
        r = v.get("result") or other_settle(dict(v, id=k), basket)
        if r is None or r[1] is None:
            continue
        v["result"] = list(r); rows.append((v, r[0], r[1]))
    return sorted(rows, key=lambda x: x[0]["ko"])
