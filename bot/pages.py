"""Çok satırlı görsel sayfalar: tüm maçlar, basketbol, karne, canlı, oran düşüşü, kupon.
Her sayfa bir başlık bandı, bölüm başlıkları ve satırlardan oluşur; uzun listeler sayfalara bölünür."""
from PIL import Image, ImageDraw
from cards import (F, W, BG, PANEL, INK, MUTED, LINE, GREEN, GREEN_SOFT, AMBER, AMBER_SOFT, RED, BLUE, GREY, HEAD,
                   TIER, _png, _fit, _rr, _bar, _footer)

RED_SOFT = (248, 227, 222)
MAX_H = 2300  # bir sayfanın en fazla yüksekliği (piksel)


def _pct(x):
    return f"%{round(x * 100)}"


def _odds(x):
    return f"{x:.2f}".replace(".", ",")


def paginate(title, sub, blocks, footer, accent=HEAD):
    """blocks: [("head", metin) | ("row", yükseklik, çizim_fonksiyonu(d, y))] -> PNG listesi."""
    pages, cur, h = [], [], 0
    for b in blocks:
        bh = 64 if b[0] == "head" else b[1] + 14
        if cur and h + bh > MAX_H - 330:
            carry = []
            if cur[-1][0] == "head":  # sayfa sonunda tek başına kalan başlık bir sonraki sayfaya geçer
                carry = [cur.pop()]
            pages.append(cur); cur, h = carry, (64 if carry else 0)
            if b[0] == "row":
                last_head = next((x for x in reversed([y for p in pages for y in p]) if x[0] == "head"), None)
                if last_head:
                    cur.append(("head", last_head[1] + " (devam)")); h += 64
        cur.append(b); h += bh
    if cur:
        pages.append(cur)
    out = []
    for k, pg in enumerate(pages, 1):
        H = 150 + 30 + sum(64 if b[0] == "head" else b[1] + 14 for b in pg) + 200
        img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
        d.rectangle((0, 0, W, 150), fill=accent)
        d.text((48, 34), title, font=F(44, True), fill=(255, 255, 255))
        d.text((48, 98), sub + (f" · sayfa {k}/{len(pages)}" if len(pages) > 1 else ""), font=F(24), fill=(200, 208, 214))
        y = 176
        for b in pg:
            if b[0] == "head":
                d.text((48, y + 14), b[1], font=F(28, True), fill=INK); y += 64
            else:
                _rr(d, (36, y, W - 36, y + b[1]), 16, PANEL, LINE, 2)
                b[2](d, y); y += b[1] + 14
        for ln in footer:
            y = _footer(d, y + 8, ln)
        out.append(_png(img.crop((0, 0, W, y + 24))))
    return out


def _stack(d, x, y, w, h, parts):
    """Yatay yığın çubuk: [(oran, renk, etiket)]."""
    cx = x
    for v, col, lbl in parts:
        sw = int(round(w * v))
        if sw <= 0:
            continue
        d.rectangle((cx, y, cx + sw, y + h), fill=col)
        if sw >= 64:
            d.text((cx + 8, y + (h - 20) // 2 - 1), lbl, font=F(18, True), fill=(255, 255, 255))
        cx += sw


def _badge(d, x, y, text, col, soft, size=20):
    tw = int(d.textlength(text, font=F(size, True))) + 24
    _rr(d, (x, y, x + tw, y + size + 16), 10, soft)
    d.text((x + 12, y + 7), text, font=F(size, True), fill=col)
    return tw


# ---------- tüm maçlar ----------
def football_row(m, g, nm):
    p = m["p"]

    def draw(d, y):
        d.text((60, y + 18), m["time"], font=F(26, True), fill=INK)
        d.text((60, y + 54), _fit(d, m["league_short"], F(16), 110), font=F(16), fill=MUTED)
        d.text((190, y + 14), _fit(d, f"{nm(m['home'])} – {nm(m['away'])}", F(26, True), 560), font=F(26, True), fill=INK)
        _stack(d, 190, y + 56, 420, 30, [(p["1"], GREEN, f"1 {_pct(p['1'])}"), (p["X"], GREY, f"X {_pct(p['X'])}"), (p["2"], BLUE, f"2 {_pct(p['2'])}")])
        t = m["top"][0]
        d.text((632, y + 58), f"2,5Ü {_pct(p['O25'])} · KG {_pct(p['BTTS'])}", font=F(18), fill=INK)
        d.text((632, y + 82), f"skor {t[0]}-{t[1]}", font=F(18), fill=MUTED)
        if g and g["tier"] >= 2:
            col, soft, _, stars = TIER[g["tier"]]
            txt = f"{stars} {g['label'].upper()}"
            tw = int(d.textlength(txt, font=F(18, True))) + 24
            _badge(d, W - 60 - tw, y + 12, txt, col, soft, 18)
            d.text((W - 60 - tw, y + 58), f"oran ≥ {_odds(g['minOdds'])}", font=F(18, True), fill=col)
    return ("row", 118, draw)


def basket_row(g, gr):
    p = g["p"]; o = g["odds"]

    def draw(d, y):
        d.text((60, y + 18), g["time"], font=F(26, True), fill=INK)
        d.text((60, y + 54), g["lg"], font=F(16), fill=MUTED)
        d.text((190, y + 14), _fit(d, f"{g['home']} – {g['away']}", F(26, True), 560), font=F(26, True), fill=INK)
        _stack(d, 190, y + 56, 420, 30, [(p["1"], GREEN, f"1 {_pct(p['1'])}"), (p["2"], BLUE, f"2 {_pct(p['2'])}")])
        hs = f"handikap {str(o['spread']).replace('.', ',')}" if o.get("spread") is not None else ""
        tt = f"toplam {str(p['exp_total']).replace('.', ',')}" if p.get("exp_total") else ""
        d.text((632, y + 58), hs, font=F(18), fill=INK); d.text((632, y + 82), tt, font=F(18), fill=MUTED)
        if gr:
            col, soft, _, stars = TIER[gr["tier"]]
            txt = f"{stars} {gr['label'].upper()}"
            tw = int(d.textlength(txt, font=F(18, True))) + 24
            _badge(d, W - 60 - tw, y + 12, txt, col, soft, 18)
            d.text((W - 60 - tw, y + 58), f"oran ≥ {_odds(gr['minOdds'])}", font=F(18, True), fill=col)
    return ("row", 118, draw)


# ---------- karne ----------
def result_row(h, g, ok, nm):
    def draw(d, y):
        col = GREEN if ok else RED
        d.ellipse((60, y + 22, 112, y + 74), fill=col)
        d.text((72, y + 26), "✓" if ok else "✗", font=F(30, True), fill=(255, 255, 255))
        d.text((136, y + 14), _fit(d, f"{nm(h['home'])}  {h['res'][0]}-{h['res'][1]}  {nm(h['away'])}", F(26, True), 620), font=F(26, True), fill=INK)
        d.text((136, y + 56), _fit(d, h["lgName"], F(18), 400), font=F(18), fill=MUTED)
        txt = f"{g['label'].upper()} {_pct(g['prob'])}"
        tw = int(d.textlength(txt, font=F(20, True))) + 24
        _badge(d, W - 60 - tw, y + 24, txt, col, GREEN_SOFT if ok else RED_SOFT)
    return ("row", 96, draw)


def kpi_row(items):
    """items: [(büyük, küçük, renk)]"""
    def draw(d, y):
        w = (W - 120) // len(items)
        for i, (big, small, col) in enumerate(items):
            x = 60 + i * w
            d.text((x, y + 16), big, font=F(44, True), fill=col)
            d.text((x, y + 74), _fit(d, small, F(18), w - 20), font=F(18), fill=MUTED)
    return ("row", 116, draw)


# ---------- canlı ----------
def live_row(m, pk, nm):
    def draw(d, y):
        _rr(d, (56, y + 18, 168, y + 70), 12, RED)
        d.text((112 - d.textlength(m["clock"], font=F(26, True)) / 2, y + 26), m["clock"], font=F(26, True), fill=(255, 255, 255))
        d.text((60, y + 80), _fit(d, m["lgName"], F(16), 120), font=F(16), fill=MUTED)
        score = f"{nm(m['home'])}  {m['score'][0]}-{m['score'][1]}  {nm(m['away'])}"
        d.text((190, y + 14), _fit(d, score, F(28, True), 620), font=F(28, True), fill=INK)
        info = []
        if any(m["reds"]): info.append(f"kırmızı kart {m['reds'][0]}-{m['reds'][1]}")
        st = m.get("stats") or [{}, {}]
        if st[0].get("shotsOnTarget") is not None: info.append(f"isabetli şut {st[0]['shotsOnTarget']}-{st[1]['shotsOnTarget']}")
        if st[0].get("possessionPct"): info.append(f"top %{round(float(st[0]['possessionPct']))}-%{round(float(st[1]['possessionPct']))}")
        d.text((190, y + 54), _fit(d, " · ".join(info), F(18), 560), font=F(18), fill=MUTED)
        if pk:
            _badge(d, 190, y + 84, f"OYNA: {pk['label'].upper()}", GREEN, GREEN_SOFT, 22)
            _rr(d, (W - 250, y + 20, W - 60, y + 118), 14, BG)
            d.text((W - 232, y + 28), f"tutma {_pct(pk['prob'])}", font=F(18), fill=MUTED)
            d.text((W - 232, y + 54), f"≥ {_odds(pk['minOdds'])}", font=F(34, True), fill=INK)
            d.text((W - 232, y + 94), "canlı oran", font=F(16), fill=MUTED)
        else:
            p = m["p"]
            d.text((190, y + 90), f"MS {_pct(p['1'])} / {_pct(p['X'])} / {_pct(p['2'])} · kalan sürede gol {_pct(1 - p['NOGOAL'])}", font=F(18), fill=INK)
    return ("row", 136, draw)


# ---------- oran düşüşü ----------
def move_row(m, side, old, new, dlt, when, nm):
    def draw(d, y):
        d.text((60, y + 16), when, font=F(22, True), fill=INK)
        d.text((60, y + 48), _fit(d, m["lgName"], F(16), 150), font=F(16), fill=MUTED)
        d.text((230, y + 14), _fit(d, f"{nm(m['home'])} – {nm(m['away'])}", F(26, True), 460), font=F(26, True), fill=INK)
        d.text((230, y + 56), _fit(d, f"{side} için oran düştü", F(20), 460), font=F(20), fill=MUTED)
        x = W - 360
        d.text((x, y + 26), _odds(old), font=F(30), fill=MUTED)
        d.text((x + 92, y + 26), "→", font=F(30, True), fill=INK)
        d.text((x + 140, y + 22), _odds(new), font=F(38, True), fill=RED)
        d.text((x, y + 72), f"olasılık +{round(dlt * 100)} puan", font=F(18, True), fill=RED)
    return ("row", 108, draw)


# ---------- kupon ----------
def coupon_row(title, meta, sel, prob, odds, ev):
    def draw(d, y):
        d.text((60, y + 14), _fit(d, title, F(24, True), 600), font=F(24, True), fill=INK)
        d.text((60, y + 48), _fit(d, meta, F(16), 600), font=F(16), fill=MUTED)
        _badge(d, 60, y + 76, sel.upper(), INK, BG, 20)
        _bar(d, 360, y + 86, 220, 16, prob, GREEN if prob >= .6 else AMBER if prob >= .45 else GREY)
        d.text((592, y + 78), _pct(prob), font=F(22, True), fill=INK)
        x = W - 300
        if odds:
            col, soft, tag = (GREEN, GREEN_SOFT, "DEĞERLİ") if ev > .03 else ((AMBER, AMBER_SOFT, "SINIRDA") if ev >= -.03 else (RED, RED_SOFT, "DÜŞÜK ORAN"))
            _rr(d, (x, y + 16, W - 60, y + 124), 14, soft)
            d.text((x + 18, y + 22), f"oranın {_odds(odds)}", font=F(18), fill=MUTED)
            d.text((x + 18, y + 46), f"{'+' if ev >= 0 else ''}{round(ev * 100)}%", font=F(34, True), fill=col)
            d.text((x + 18, y + 92), tag, font=F(16, True), fill=col)
        else:
            d.text((x, y + 40), f"adil oran {_odds(1 / prob)}", font=F(22, True), fill=INK)
    return ("row", 138, draw)


def note_row(text, col=MUTED, h=70):
    def draw(d, y):
        d.text((60, y + (h - 24) // 2), _fit(d, text, F(20), W - 140), font=F(20), fill=col)
    return ("row", h, draw)
