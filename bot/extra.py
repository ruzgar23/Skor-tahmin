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
    out = [f"🏀 <b>Basketbol</b> ({len(gs)} maç; favoriler testte %64–85 kazandı. Handikap ve alt/üst ~%50, öneri yok)"]
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


def coupon_message(data, basket, body):
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    if not lines:
        return ("Kullanım (her satıra bir maç: takım, seçim, oran):\n<code>/kupon\ngalatasaray 1 1.85\narsenal 2.5 üst 1.70\nbarcelona kg 1.65\n"
                "fenerbahçe kart 4.5 üst 1.80\nlakers 2 1.95</code>\n\n"
                "Seçimler: 1 · X · 2 · 1X · X2 · 12 · üst/alt (1.5, 2.5, 3.5) · kg · kgyok · iy1/iyx/iy2 · kart 4.5 üst · korner 9.5 alt. "
                "Basketbol: 1 · 2 · üst/alt 225.5")
    out = ["🧾 <b>Kupon değerlendirmesi</b>"]
    tot_p, tot_o, all_odds, seen, n_ok = 1.0, 1.0, True, set(), 0
    for raw in lines[:15]:
        pl = parse_line(raw)
        if not pl:
            out.append(f"\n❓ <i>{e(raw)}</i>\n   Seçim anlaşılamadı."); all_odds = False; continue
        m, kind = find_match(data, basket, pl["team"])
        if not m:
            out.append(f"\n❓ <i>{e(raw)}</i>\n   “{e(pl['team'])}” için yaklaşan maç bulunamadı."); all_odds = False; continue
        pr, lbl = sel_prob(m, kind, pl["sel"])
        title = f"{e(nm(m['home']))} – {e(nm(m['away']))}"
        if pr is None:
            out.append(f"\n❓ <b>{title}</b>\n   {e(lbl)}"); all_odds = False; continue
        n_ok += 1
        if m["id"] in seen:
            out.append(f"\n⚠️ <b>{title}</b> kuponda iki kez var; aynı maçın seçimleri birbirine bağlıdır, toplam olasılık yanıltıcı olur.")
        seen.add(m["id"])
        tot_p *= pr
        s = f"\n<b>{title}</b> <i>({e(m['lgName'])}, {ko_local(m).strftime('%d.%m %H:%M')})</i>\n   {e(lbl)}: olasılık {pct(pr)} · adil oran {odds_fmt(1 / pr)}"
        if pl["odds"]:
            tot_o *= pl["odds"]; ev = pr * pl["odds"] - 1
            tag = "✅ değerli" if ev > 0.03 else ("➖ sınırda" if ev >= -0.03 else "❌ düşük oran")
            s += f"\n   Senin oranın {odds_fmt(pl['odds'])} → beklenen {'+' if ev >= 0 else ''}{round(ev * 100)}% {tag}"
        else:
            all_odds = False
        if kind == "futbol" and m.get("src") != "piyasa":
            s += "\n   <i>(piyasa oranı yok, olasılık yalnızca modelden)</i>"
        out.append(s)
    if n_ok >= 2:
        out.append(f"\n<b>Kuponun tutma olasılığı: {pct(tot_p)}</b> (yaklaşık {max(1, round(1 / tot_p))} kuponda 1)")
        if all_odds:
            ev = tot_p * tot_o - 1
            out.append(f"Toplam oran {odds_fmt(tot_o)} · beklenen getiri {'+' if ev >= 0 else ''}{round(ev * 100)}%"
                       + (" ✅" if ev > 0.03 else " ❌" if ev < -0.03 else ""))
        out.append("<i>Maç sayısı arttıkça büro payı her maçta katlanır; kombineler uzun vadede tekli bahislerden daha çok kaybettirir.</i>")
    return "\n".join(out)
