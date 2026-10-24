"""Telegram için görsel kartlar (PNG). Pillow + matplotlib ile gelen DejaVu yazı tipleri (Türkçe karakterler için)."""
import io, os
from PIL import Image, ImageDraw, ImageFont
import matplotlib

FONT_DIR = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
_fc = {}


def F(size, bold=False):
    k = (size, bold)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)
    return _fc[k]


# sayfayla aynı palet
BG = (238, 241, 243); PANEL = (255, 255, 255); INK = (21, 33, 43); MUTED = (93, 107, 117); LINE = (214, 221, 226)
GREEN = (29, 107, 71); GREEN_SOFT = (220, 239, 228); AMBER = (163, 93, 0); AMBER_SOFT = (251, 238, 216)
RED = (163, 64, 44); BLUE = (47, 93, 138); GREY = (138, 150, 160); HEAD = (21, 33, 43)
TIER = {3: (GREEN, GREEN_SOFT, "GÜÇLÜ", "★★★"), 2: (AMBER, AMBER_SOFT, "ORTA", "★★☆")}
W = 1080


def _png(img):
    b = io.BytesIO(); img.save(b, "PNG", optimize=True); return b.getvalue()


def _fit(d, text, font, maxw):
    if d.textlength(text, font=font) <= maxw:
        return text
    while text and d.textlength(text + "…", font=font) > maxw:
        text = text[:-1]
    return text + "…"


def _rr(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def _bar(d, x, y, w, h, p, color):
    _rr(d, (x, y, x + w, y + h), h // 2, LINE)
    if p > 0:
        _rr(d, (x, y, x + max(h, int(w * p)), y + h), h // 2, color)


def _header(d, title, sub):
    d.rectangle((0, 0, W, 150), fill=HEAD)
    d.text((48, 34), title, font=F(46, True), fill=(255, 255, 255))
    d.text((48, 98), sub, font=F(24), fill=(190, 200, 207))


def _wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    return lines


def _footer(d, y, text):
    for ln in _wrap(d, text, F(20), W - 96):
        d.text((48, y), ln, font=F(20), fill=MUTED); y += 30
    return y


def daily_card(title, sub, sections, footer):
    """sections: [(başlık, [satır])]; satır: dict(time, league, home, away, pick, prob, min_odds, tier, note)"""
    rows = sum(len(r) for _, r in sections); n_sec = sum(1 for _, r in sections if r)
    H = 150 + 30 + n_sec * 70 + rows * 178 + 260
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    _header(d, title, sub)
    y = 180
    for head, items in sections:
        if not items:
            continue
        d.text((48, y + 14), head, font=F(30, True), fill=INK); y += 70
        for it in items:
            col, soft, tname, stars = TIER.get(it["tier"], (GREY, LINE, "", ""))
            _rr(d, (36, y, W - 36, y + 162), 18, PANEL, LINE, 2)
            d.rectangle((36, y + 12, 46, y + 150), fill=col)
            # sol: saat + lig
            d.text((70, y + 22), it["time"], font=F(34, True), fill=INK)
            d.text((70, y + 66), _fit(d, it["league"], F(20), 190), font=F(20), fill=MUTED)
            d.text((70, y + 98), stars, font=F(26, True), fill=col)
            d.text((70, y + 130), tname + {3: " · 1 BİRİM", 2: " · ½ BİRİM"}.get(it["tier"], ""), font=F(18, True), fill=col)
            # orta: takımlar + seçim
            x0 = 290
            d.text((x0, y + 18), _fit(d, f"{it['home']} – {it['away']}", F(30, True), 500), font=F(30, True), fill=INK)
            badge = f"OYNA: {it['pick']}"
            bw = int(d.textlength(badge, font=F(28, True))) + 36
            _rr(d, (x0, y + 66, x0 + bw, y + 112), 12, soft)
            d.text((x0 + 18, y + 72), badge, font=F(28, True), fill=col)
            _bar(d, x0, y + 128, 300, 16, it["prob"], col)
            d.text((x0 + 314, y + 120), f"%{round(it['prob'] * 100)} tutar", font=F(22, True), fill=INK)
            # sağ: en az oran
            xr = W - 260
            _rr(d, (xr, y + 22, W - 60, y + 140), 14, BG)
            d.text((xr + 20, y + 32), "iddaa oranı", font=F(20), fill=MUTED)
            d.text((xr + 20, y + 58), f"≥ {it['min_odds']:.2f}".replace(".", ","), font=F(40, True), fill=INK)
            d.text((xr + 20, y + 108), "ise oyna", font=F(20), fill=MUTED)
            if it.get("note"):
                d.text((x0 + 520, y + 22), "", font=F(18), fill=MUTED)
            y += 178
    y = _footer(d, y + 16, footer[0]); y = _footer(d, y + 4, footer[1])
    return _png(img.crop((0, 0, W, y + 30)))


def match_card(m, g, extra_lines):
    """Tek maçın görsel özeti."""
    p = m["p"]; H = 1600
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 230), fill=HEAD)
    d.text((48, 30), _fit(d, f"{m['lgName']} · {m['when']}", F(24), W - 96), font=F(24), fill=(190, 200, 207))
    one = f"{m['home_tr']} – {m['away_tr']}"
    if d.textlength(one, font=F(46, True)) <= W - 96:
        d.text((48, 100), one, font=F(46, True), fill=(255, 255, 255))
    else:
        d.text((48, 72), _fit(d, m["home_tr"], F(46, True), W - 96), font=F(46, True), fill=(255, 255, 255))
        d.text((48, 138), _fit(d, f"– {m['away_tr']}", F(46, True), W - 96), font=F(46, True), fill=(255, 255, 255))
    y = 260
    # öneri
    if g:
        col, soft, tname, stars = TIER.get(g["tier"], (GREY, LINE, "DÜŞÜK GÜVEN", "★☆☆"))
        _rr(d, (36, y, W - 36, y + 170), 20, soft)
        d.text((70, y + 22), f"{stars}  {tname} ÖNERİ", font=F(24, True), fill=col)
        d.text((70, y + 60), f"OYNA: {g['label']}", font=F(44, True), fill=col)
        d.text((70, y + 122), f"Tutma ihtimali %{round(g['prob'] * 100)} · iddaa oranı ≥ {g['minOdds']:.2f} ise oyna, altındaysa geç".replace(".", ",", 1),
               font=F(22), fill=INK)
    else:
        _rr(d, (36, y, W - 36, y + 170), 20, PANEL, LINE, 2)
        d.text((70, y + 40), "Net seçim yok", font=F(40, True), fill=MUTED)
        d.text((70, y + 100), "Hiçbir markette %60'ı geçen seçim yok; bu maçı geçmek daha doğru.", font=F(22), fill=MUTED)
    y += 200
    # MS çubuğu
    _rr(d, (36, y, W - 36, y + 170), 20, PANEL, LINE, 2)
    d.text((70, y + 20), "MAÇ SONUCU", font=F(22, True), fill=MUTED)
    x, w = 70, W - 140
    segs = [(p["1"], GREEN, "1"), (p["X"], GREY, "X"), (p["2"], BLUE, "2")]
    cx = x
    for i, (v, c, lbl) in enumerate(segs):
        sw = int(w * v)
        d.rectangle((cx, y + 62, cx + sw, y + 102), fill=c)
        if sw > 90:
            d.text((cx + 12, y + 68), f"{lbl} %{round(v * 100)}", font=F(24, True), fill=(255, 255, 255))
        cx += sw
    d.text((70, y + 120), f"Çifte şans: 1X %{round(p['1X']*100)} · 12 %{round(p['12']*100)} · X2 %{round(p['X2']*100)}", font=F(22), fill=INK)
    y += 190
    # gol marketleri
    _rr(d, (36, y, W - 36, y + 300), 20, PANEL, LINE, 2)
    d.text((70, y + 20), "GOLLER", font=F(22, True), fill=MUTED)
    items = [("1,5 Üst", p["O15"]), ("2,5 Üst", p["O25"]), ("3,5 Üst", p["O35"]), ("KG Var", p["BTTS"])]
    yy = y + 64
    for lbl, v in items:
        d.text((70, yy), lbl, font=F(24, True), fill=INK)
        _bar(d, 240, yy + 6, 560, 22, v, GREEN if v >= .6 else (AMBER if v >= .5 else GREY))
        d.text((820, yy), f"%{round(v * 100)}", font=F(24, True), fill=INK)
        yy += 54
    y += 320
    # skorlar
    _rr(d, (36, y, W - 36, y + 150), 20, PANEL, LINE, 2)
    d.text((70, y + 20), "EN OLASI SKORLAR", font=F(22, True), fill=MUTED)
    cx = 70
    for a, b, v in m["top"][:5]:
        _rr(d, (cx, y + 60, cx + 170, y + 128), 14, BG)
        d.text((cx + 20, y + 66), f"{a}-{b}", font=F(34, True), fill=INK)
        d.text((cx + 104, y + 78), f"%{round(v * 100)}", font=F(20), fill=MUTED)
        cx += 186
    y += 170
    for ln in extra_lines[:3]:
        d.text((48, y), _fit(d, ln, F(22), W - 96), font=F(22), fill=INK); y += 36
    y = _footer(d, y + 14, "Olasılıklar garanti değildir. Kaybetmeyi göze alamayacağın parayla oynama.")
    return _png(img.crop((0, 0, W, y + 30)))
