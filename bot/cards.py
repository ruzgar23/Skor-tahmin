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
BLUE_SOFT = (222, 233, 244)
TIER = {3: (GREEN, GREEN_SOFT, "GÜÇLÜ", "★★★"), 2: (AMBER, AMBER_SOFT, "ORTA", "★★☆"), 4: (BLUE, BLUE_SOFT, "EK SEÇİM", ""),
        5: ((176, 42, 92), (248, 222, 232), "RİSKLİ", ""),
        6: ((168, 56, 20), (252, 226, 212), "ÇOK RİSKLİ", "")}
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


# Spor başına başlık rengi: her spor ayrı görselde, rengiyle ayırt edilir
SPORT = {"futbol": ((21, 33, 43), "FUTBOL"), "basketbol": ((190, 84, 20), "BASKETBOL"),
         "hokey": ((24, 96, 150), "HOKEY"), "tenis": ((104, 58, 150), "TENİS"), "riskli": ((120, 24, 60), "RİSKLİ"), "cokriskli": ((40, 18, 12), "ÇOK RİSKLİ")}


def _header(d, title, sub, fill=HEAD):
    d.rectangle((0, 0, W, 150), fill=fill)
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
    for ln in _wrap(d, text, F(26), W - 96):
        d.text((48, y), ln, font=F(26), fill=MUTED); y += 38
    return y


def daily_card(title, sub, sections, footer, accent=HEAD):
    """sections: [(başlık, [satır])]; satır: dict(time, league, home, away, pick, prob, min_odds, tier, note)"""
    # Telefonda görsel ~1/3 boyuta küçülür: en küçük yazı 26 px. Kart başına üç satır:
    # (1) saat · lig ve güven, (2) maç, (3) büyük seçim + olasılık, sağda en düşük oran.
    # Güven yalnızca renkle (sol şerit + seçim kutusu) gösterilir; yıldız ve çubuk yok.
    rows = sum(len(r) for _, r in sections); n_sec = sum(1 for _, r in sections if r)
    CH = 236
    H = 150 + 30 + n_sec * 78 + rows * (CH + 18) + 320
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    _header(d, title, sub, accent)
    y = 180
    for head, items in sections:
        if not items:
            continue
        d.text((48, y + 16), head, font=F(34, True), fill=INK); y += 78
        for it in items:
            col, soft, tname, _ = TIER.get(it["tier"], (GREY, LINE, "", ""))
            _rr(d, (36, y, W - 36, y + CH), 20, PANEL, LINE, 2)
            d.rectangle((36, y + 14, 48, y + CH - 14), fill=col)
            x0, xr = 76, W - 76
            # 1: saat · lig  |  güven · birim
            conf = tname + {3: " · 1 birim", 2: " · ½ birim", 4: " · ½ birim", 5: " · ¼ birim", 6: " · ⅛ birim"}.get(it["tier"], "")
            cw = d.textlength(conf, font=F(26, True))
            d.text((xr - cw, y + 22), conf, font=F(26, True), fill=col)
            d.text((x0, y + 22), _fit(d, f"{it['time']} · {it['league']}", F(26), xr - cw - x0 - 24), font=F(26), fill=MUTED)
            # 2: maç
            d.text((x0, y + 62), _fit(d, f"{it['home']} – {it['away']}", F(36, True), xr - x0), font=F(36, True), fill=INK)
            # 3: seçim kutusu + olasılık
            pick = _fit(d, it["pick"], F(40, True), 520)
            bw = int(d.textlength(pick, font=F(40, True))) + 44
            _rr(d, (x0, y + 128, x0 + bw, y + 200), 14, soft)
            d.text((x0 + 22, y + 140), pick, font=F(40, True), fill=col)
            d.text((x0 + bw + 22, y + 140), f"%{round(it['prob'] * 100)}", font=F(40, True), fill=INK)
            # sağ alt: en düşük oran
            ov = f"{it['min_odds']:.2f}".replace(".", ",")
            ow = d.textlength(ov, font=F(40, True))
            d.text((xr - ow, y + 152), ov, font=F(40, True), fill=INK)
            lb = "iddaa en az"
            d.text((xr - d.textlength(lb, font=F(26)), y + 118), lb, font=F(26), fill=MUTED)
            y += CH + 18
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
    shown = 0
    for ln in extra_lines[:4]:  # uzun satırlar (maç yorumu) alt satıra geçer; en fazla 7 satır
        for part in _wrap(d, ln, F(24), W - 96):
            if shown >= 7:
                break
            d.text((48, y), part, font=F(24), fill=INK); y += 36; shown += 1
        y += 8
    y = _footer(d, y + 14, "Olasılıklar garanti değildir. Kaybetmeyi göze alamayacağın parayla oynama.")
    return _png(img.crop((0, 0, W, y + 30)))
