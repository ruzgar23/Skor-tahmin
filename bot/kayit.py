"""Kayıt (video) modu: KAYIT_MODU=1 iken mesajlarda ve kartlarda bahis talimatları gizlenir.

"OYNA:" yerine "TAHMİN:", "OYNAMA:" yerine "İPTAL:" yazılır; birim önerileri ve
"tekli oyna / kasanın %2'si" gibi oynama talimatları çıkarılır. Olasılıklar, oran
sınırları, karne ve canlı sonuçlar aynen kalır.

Açmak için: Settings → Secrets and variables → Actions → Variables → KAYIT_MODU = 1
Kapatmak için değişkeni silmek ya da 0 yapmak yeterli.
"""
import os
import re

AKTIF = os.environ.get("KAYIT_MODU", "").strip() == "1"

_KURALLAR = [
    (re.compile(r"Tekli oyna; 1 birim = kasanın %2'si\.\s*"), ""),
    (re.compile(r"\s*Kombine yapma, en fazla \S+ birim oyna\."), ""),
    (re.compile(r"\s*·\s*(?:1|½|¼|⅛) birim"), ""),
    (re.compile(r"(?:1|½|¼|⅛) birim\b"), ""),
    (re.compile(r" ise oyna, altındaysa geç"), ""),
    (re.compile(r"OYNAMA:"), "İPTAL:"),
    (re.compile(r"OYNA:"), "TAHMİN:"),
    (re.compile(r"Oyna:"), "Tahmin:"),
]


def temizle(s):
    """Kayıt modu açıksa metinden oynama talimatlarını çıkarır; kapalıysa aynen döndürür."""
    if not AKTIF or not isinstance(s, str):
        return s
    for desen, yeni in _KURALLAR:
        s = desen.sub(yeni, s)
    return s


def _kartlara_uygula():
    """Görsel kartlardaki yazıları da aynı filtreden geçirir (genişlik hesabı dahil, hizalama bozulmasın)."""
    try:
        from PIL import ImageDraw
    except ImportError:
        return
    D = ImageDraw.ImageDraw
    if getattr(D, "_kayit_yamali", False):
        return
    asil_text, asil_len = D.text, D.textlength

    def text(self, xy, metin, *a, **k):
        return asil_text(self, xy, temizle(metin), *a, **k)

    def textlength(self, metin, *a, **k):
        return asil_len(self, temizle(metin), *a, **k)

    D.text, D.textlength, D._kayit_yamali = text, textlength, True


if AKTIF:
    _kartlara_uygula()
