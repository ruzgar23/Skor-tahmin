"""Kişisel bahis defteri: /oynadim ile kayıt, maç bitince otomatik sonuçlandırma, /defter ile özet.
Kayıtlar iş durumunda (state/run) sohbet bazında tutulur: st["ledger"][chat] = [bahis, ...]."""
import re
from datetime import datetime, timedelta, timezone
import core, extra
from core import e, nm, pct, odds_fmt, ko_local

HELP = ("📒 <b>Bahis defteri</b>\n"
        "Oynadığın bahisleri kaydet, maç bitince bot sonucu kendisi bulur ve kâr/zararını tutar.\n\n"
        "<b>Kayıt</b> (her satıra bir bahis: takım, seçim, oran, tutar):\n"
        "<code>/oynadim galatasaray 1 1.85 100\nbarcelona 1 2.5 üst 2.40 50\narsenal kg 1.70</code>\n"
        "Tutar yazmazsan 1 birim sayılır. Seçimler kupondakiyle aynı: 1 · X · 2 · 1X · X2 · 12 · 2.5 üst/alt · kg · kgyok · "
        "iy1/iyx/iy2 · iy 0.5 üst · korner 9.5 alt · birleşik (1 2.5 üst, 1 kg).\n\n"
        "/defter – özet ve bekleyen bahisler\n/defter sil 3 – 3 numaralı kaydı sil\n\n"
        "<i>Şimdilik yalnızca futbol. Kombine kuponu her maçı ayrı satır olarak yazarak tek tek takip edebilirsin.</i>")
NUM = re.compile(r"^\d+([.,]\d+)?$")


def _split_stake(raw):
    """'... 1.85 100' → ('... 1.85', 100.0). Son iki sözcük sayıysa ve sondan ikincisi orana benziyorsa sonuncusu tutardır."""
    toks = raw.split()
    if len(toks) >= 3 and NUM.match(toks[-1]) and re.match(r"^\d+[.,]\d+$", toks[-2]) and float(toks[-2].replace(",", ".")) > 1:
        return " ".join(toks[:-1]), float(toks[-1].replace(",", "."))
    return raw, 1.0


def _ser(sel):
    """Seçimi JSON'a yazılabilir hale getirir (birleşiklerde iç tuple liste olur)."""
    return [list(x) if isinstance(x, tuple) else x for x in sel]


def _des(sel):
    out = [tuple(x) if isinstance(x, list) else x for x in sel]
    return tuple(out)


def settle(sel, res, ht=None, corners=None):
    """Bahsin sonucu: True/False, iade için 'iade', bilinmiyorsa None."""
    key, side, line = _des(sel)
    if not res:
        return None
    a, b = res; t = a + b
    if key == "COMBO":
        rf = core.COMBO_RES[side]; _, tf = core.COMBO_TOT[line]
        return bool(rf(a, b) and tf(a, b))
    if key == "gol":
        line = line or 2.5
        if abs(t - line) < 1e-9:
            return "iade"
        return (t > line) == (side == "O")
    if key == "iy":
        if not ht: return None
        line = line or 0.5; th = ht[0] + ht[1]
        return (th > line) == (side == "O")
    if key == "korner":
        if not corners: return None
        line = line or 9.5; tc = corners[0] + corners[1]
        if abs(tc - line) < 1e-9:
            return "iade"
        return (tc > line) == (side == "O")
    if key in ("HT1", "HTX", "HT2"):
        if not ht: return None
        return {"HT1": ht[0] > ht[1], "HTX": ht[0] == ht[1], "HT2": ht[0] < ht[1]}[key]
    return {"1": a > b, "X": a == b, "2": a < b, "1X": a >= b, "X2": a <= b, "12": a != b,
            "BTTS": a > 0 and b > 0, "NBTTS": not (a > 0 and b > 0)}.get(key)


def add(st, chat, data, basket, body):
    """Satırları deftere yazar. Dönüş: yanıt metni."""
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    if not lines:
        return HELP
    book = st.setdefault("ledger", {}).setdefault(chat, [])
    nxt = max([b["no"] for b in book] or [0]) + 1
    out = ["📒 <b>Deftere yazıldı</b>"]
    for raw in lines[:15]:
        txt, stake = _split_stake(raw)
        pl = extra.parse_line(txt)
        if not pl:
            out.append(f"\n❓ <i>{e(raw)}</i>\n   Seçim anlaşılamadı. Örnek: galatasaray 1 1.85 100"); continue
        if not pl["odds"]:
            out.append(f"\n❓ <i>{e(raw)}</i>\n   Oranı da yaz (kâr/zarar için gerekli). Örnek: galatasaray 1 1.85 100"); continue
        if pl["sel"][0] == "kart":
            out.append(f"\n❓ <i>{e(raw)}</i>\n   Kart bahisleri defterde sonuçlandırılamıyor (iddaa kart sayımı farklı)."); continue
        m, kind = extra.find_match(data, basket, pl["team"])
        if not m:
            out.append(f"\n❓ <i>{e(raw)}</i>\n   “{e(pl['team'])}” için yaklaşan ya da oynanan maç bulunamadı."); continue
        if kind != "futbol":
            out.append(f"\n❓ <i>{e(raw)}</i>\n   Defter şimdilik yalnızca futbolu takip ediyor."); continue
        pr, lbl = extra.sel_prob(m, kind, pl["sel"])
        if pr is None and pl["sel"][0] == "korner":  # model tahmini yoksa da kaydedilir
            ln = pl["sel"][2] or 9.5
            lbl = f"Korner {extra.line_fmt(ln)} {'Üst' if pl['sel'][1] == 'O' else 'Alt'}"
        elif pr is None:
            out.append(f"\n❓ <i>{e(raw)}</i>\n   {e(nm(m['home']))} – {e(nm(m['away']))}: {e(lbl)}"); continue
        b = dict(no=nxt, mid=m["id"], lg=m["lg"], home=m["home"], away=m["away"], ko=m["ko"], lgName=m["lgName"],
                 sel=_ser(pl["sel"]), label=lbl, odds=pl["odds"], stake=stake, prob=pr,
                 ts=datetime.now(timezone.utc).isoformat(), ok=None)
        book.append(b); nxt += 1
        ev = (pr * pl["odds"] - 1) if pr else None
        tag = "" if ev is None else (" · ✅ değerli" if ev > 0.03 else (" · ➖ sınırda" if ev >= -0.03 else " · ❌ düşük oran"))
        out.append(f"\n#{b['no']} <b>{e(nm(m['home']))} – {e(nm(m['away']))}</b> <i>({ko_local(m).strftime('%d.%m %H:%M')})</i>\n"
                   f"   {e(lbl)} @ {odds_fmt(pl['odds'])} · tutar {_num(stake)}"
                   + (f" · olasılık {pct(pr)}{tag}" if pr else ""))
    out.append("\nMaç bitince sonucu sana bildireceğim. Özet için /defter")
    return "\n".join(out)


def _num(x):
    return (f"{x:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def summary(st, chat, arg=""):
    book = st.setdefault("ledger", {}).setdefault(chat, [])
    m = re.match(r"^\s*sil\s+#?(\d+)\s*$", arg or "")
    if m:
        no = int(m.group(1)); before = len(book)
        book[:] = [b for b in book if b["no"] != no]
        return f"🗑 #{no} silindi." if len(book) < before else f"#{no} numaralı kayıt bulunamadı."
    if not book:
        return HELP
    done = [b for b in book if b["ok"] in (True, False, "iade")]
    pend = [b for b in book if b["ok"] is None]
    staked = sum(b["stake"] for b in done if b["ok"] != "iade")
    ret = sum(b["stake"] * b["odds"] for b in done if b["ok"] is True) + sum(b["stake"] for b in done if b["ok"] == "iade")
    won = sum(1 for b in done if b["ok"] is True); lost = sum(1 for b in done if b["ok"] is False)
    net = ret - sum(b["stake"] for b in done)
    exp_w = sum(b["prob"] for b in done if b.get("prob") and b["ok"] != "iade")
    n_p = sum(1 for b in done if b.get("prob") and b["ok"] != "iade")
    out = ["📒 <b>Bahis defterin</b>"]
    if done:
        out.append(f"Sonuçlanan {len(done)} bahis: {won} kazandı, {lost} kaybetti"
                   + (f", {len(done) - won - lost} iade" if len(done) - won - lost else ""))
        out.append(f"Yatırılan {_num(staked)} · dönen {_num(ret)} · <b>net {'+' if net >= 0 else ''}{_num(net)}</b>"
                   + (f" ({'+' if net >= 0 else ''}{round(100 * net / staked)}%)" if staked else ""))
        if n_p:
            out.append(f"Botun olasılıklarına göre beklenen kazanan: {exp_w:.1f}".replace(".", ",") + f" (gerçek {sum(1 for b in done if b.get('prob') and b['ok'] is True)})")
    if pend:
        out.append(f"\n⏳ <b>Bekleyen {len(pend)} bahis</b>")
        for b in sorted(pend, key=lambda b: b["ko"]):
            out.append(f"#{b['no']} {e(nm(b['home']))} – {e(nm(b['away']))} · {e(b['label'])} @ {odds_fmt(b['odds'])} · {_num(b['stake'])}")
    last = sorted(done, key=lambda b: b.get("done_at", b["ts"]), reverse=True)[:10]
    if last:
        out.append("\n<b>Son sonuçlar</b>")
        for b in last:
            mark = {True: "✅", False: "❌", "iade": "↩️"}[b["ok"]]
            pl = b["stake"] * (b["odds"] - 1) if b["ok"] is True else (0 if b["ok"] == "iade" else -b["stake"])
            out.append(f"{mark} #{b['no']} {e(nm(b['home']))} {b['res'][0]}-{b['res'][1]} {e(nm(b['away']))} · {e(b['label'])} @ {odds_fmt(b['odds'])} "
                       f"({'+' if pl >= 0 else ''}{_num(pl)})")
    out.append("\n<i>Kayıt silmek için: /defter sil 3</i>")
    return "\n".join(out)


def settle_all(st, final_fn, now=None):
    """Biten maçların bahislerini sonuçlandırır. final_fn(lg, home, away, ko) → (skor, devre, korner) ya da None.
    Dönüş: {sohbet: [sonuçlanan bahisler]}."""
    now = now or datetime.now(timezone.utc); out = {}
    cache = {}
    for chat, book in st.get("ledger", {}).items():
        for b in book:
            if b["ok"] is not None:
                continue
            ko = datetime.fromisoformat(b["ko"])
            if now < ko + timedelta(minutes=110):
                continue
            if now > ko + timedelta(days=2):
                b["ok"] = "?"; continue  # sonuç bulunamadı; özete girmez
            k = (b["lg"], b["home"], b["away"], b["ko"])
            if k not in cache:
                cache[k] = final_fn(b["lg"], b["home"], b["away"], ko)
            fin = cache[k]
            if not fin:
                continue
            res, ht, cor = fin
            r = settle(b["sel"], res, ht, cor)
            if r is None:
                if now > ko + timedelta(hours=8):
                    b["ok"] = "?"
                continue
            b["ok"] = r; b["res"] = res; b["done_at"] = now.isoformat()
            out.setdefault(chat, []).append(b)
    return out


def result_message(items):
    out = ["📒 <b>Defter: sonuçlanan bahisler</b>"]
    for b in items:
        mark = {True: "✅ Kazandı", False: "❌ Kaybetti", "iade": "↩️ İade"}[b["ok"]]
        pl = b["stake"] * (b["odds"] - 1) if b["ok"] is True else (0 if b["ok"] == "iade" else -b["stake"])
        out.append(f"\n{mark} · #{b['no']} <b>{e(nm(b['home']))} {b['res'][0]}-{b['res'][1]} {e(nm(b['away']))}</b>\n"
                   f"   {e(b['label'])} @ {odds_fmt(b['odds'])} · {'+' if pl >= 0 else ''}{_num(pl)}")
    out.append("\nToplam durum için /defter")
    return "\n".join(out)
