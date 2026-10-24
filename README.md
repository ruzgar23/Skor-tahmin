# Skor Tahmin Masası

Futbol maçları için olasılık tahminleri: maç sonucu, çifte şans, alt/üst, karşılıklı gol, ilk yarı, en olası skorlar ve maç sırasında canlı analiz. Sonuçlar bir web sayfasında yayınlanır ve bir Telegram botuyla gönderilir. Her şey GitHub Actions üzerinde ücretsiz çalışır; sunucu ya da açık bilgisayar gerekmez.

> Olasılıklar garanti değildir. %70'lik bir seçim de 10 maçın 3'ünde yatar. Kaybetmeyi göze alamayacağın parayla oynama.

## Ne yapar

| Ne zaman | Ne gelir |
|---|---|
| Her sabah 09:30 (TR) | Dünün karnesi ve günün güçlü/orta önerileri (seçim, olasılık, oynamaya değmesi için gereken en düşük iddaa oranı) |
| Maç saatlerinde, 5 dakikada bir | Canlı fırsat adayları: dakika, skor, kartlar, seçim, olasılık, gereken en düşük canlı oran |
| Her zaman (birkaç dakika içinde) | Bot komutları: `/bugun`, `/guclu`, `/orta`, `/canli`, `/mac takım`, `/karne`, `/dur` |

Kapsam: Premier League, Championship, League One/Two, La Liga 1–2, Serie A–B, Bundesliga 1–2, Ligue 1–2, Süper Lig, Eredivisie, Portekiz, İskoçya (4 lig), Yunanistan, Şampiyonlar Ligi, Avrupa Ligi, Konferans Ligi.

## Nasıl çalışır

- **Maç öncesi:** Olasılıkların ana kaynağı, büro payı çıkarılmış piyasa oranlarıdır. KG, ilk yarı ve skor dağılımı bu oranlara uydurulmuş gol beklentisinden (Poisson, Dixon-Coles düzeltmesi) hesaplanır. Oran yoksa maç bazlı model kullanılır: zamana ağırlıklı, rakip gücünü hesaba katan, takıma özel iç saha etkisi olan ve gol ile xG'yi harmanlayan bir model. Bu maçlar "düşük güven" olarak işaretlenir.
- **Güven seviyeleri:** 8.152 maçlık geriye dönük testte güçlü öneriler %74–80, orta öneriler %63–67 tuttu.
- **Canlı:** Maç öncesi gol beklentisi kalan süreye, skora ve kırmızı kartlara göre güncellenir. Ayarlar 13.598 maçlık devre arası verisinden yapıldı. Şut, isabetli şut, korner ve şut konumundan xG de test edildi; tahmini iyileştirmedikleri için modelde yer almıyorlar (2.687 maç, sezon içi eğitim/test ayrımıyla).
- **Kâr kanıtı yok:** Modelin piyasadan farklı düşündüğü bahisleri oynamak testte yaklaşık %15 kaybettirdi. Araç olasılıkları doğru tahmin eder; büroyu yendiğini iddia etmez.

Veri kaynakları: [football-data.co.uk](https://football-data.co.uk) (sonuçlar, oranlar, xG) ve ESPN'in herkese açık skor servisi (fikstür, canlı skor, oranlar). Bu kaynakların kendi kullanım koşulları geçerlidir; proje kişisel ve ticari olmayan kullanım içindir.

## Kendi botunu kur (5 dakika)

1. **Depoyu kopyala:** Sağ üstteki **Fork** düğmesine bas.
2. **Telegram botu oluştur:** Telegram'da [@BotFather](https://t.me/BotFather)'a `/newbot` yaz, ad ver ve verdiği token'ı kopyala.
3. **Token'ı gizli olarak ekle:** Deponda **Settings → Secrets and variables → Actions → New repository secret**. Ad: `TELEGRAM_TOKEN`, değer: token. Token koda ya da sayfaya hiçbir zaman yazılmaz.
4. **Sayfayı aç:** **Settings → Pages → Branch: `gh-pages` / `(root)` → Save.** `gh-pages` dalı ilk çalışmadan sonra oluşur; listede yoksa 5. adımdan sonra tekrar bak.
5. **Otomasyonu başlat:** **Actions** sekmesinde iş akışlarını etkinleştir, sonra **Sabah taraması → Run workflow** ile ilk çalışmayı başlat.
6. **Botuna yaz:** Telegram'da botunu aç ve `/start` gönder. Komutlara birkaç dakika içinde cevap gelir; sabah mesajları ertesi gün başlar.

İsteğe bağlı ayarlar (**Settings → Secrets and variables → Actions → Variables**):

| Değişken | Ne işe yarar |
|---|---|
| `SITE_URL` | Mesajlardaki sayfa linki. Boş bırakılırsa GitHub Pages adresi otomatik kullanılır |
| `TELEGRAM_CHAT_ID` | Ek alıcılar, virgülle ayrılmış. Örn. herkese açık bir kanal: `@kanaladi` (botu kanala yönetici olarak ekle) |

Bota `/start` yazan herkes bildirimleri alır, `/dur` ile kapatır. Abone listesi depoda değil, Actions önbelleğinde tutulur.

## Dosyalar

- `engine/`: model ve veri (`engine.py` model, `scan.py` tarama, `espn.py` fikstür ve canlı veri, `live.py` canlı analiz)
- `bot/`: Telegram botu (`run.py` giriş noktası, `core.py` öneri ve mesaj biçimleri, `tg.py` Telegram API)
- `site/`: web sayfası (`gh-pages` dalına veriyle birlikte yayınlanır; bahis defteri yalnızca ziyaretçinin tarayıcısında saklanır)
- `.github/workflows/`: sabah taraması, canlı takip, bot komutları

## Notlar

- GitHub'ın zamanlanmış çalışmaları yoğun saatlerde birkaç dakika gecikebilir. Canlı takip bu yüzden kendi içinde 5 dakikada bir kontrol eden bir döngü olarak çalışır.
- Herkese açık depolarda Actions süresi ücretsizdir. Gizli bir depoda aylık ücretsiz süre canlı takibe yetmeyebilir; o durumda `live.yml` içindeki `LIVE_EVERY_SEC` değerini `600` yap.
- Bir iş başarısız olursa Actions sekmesinde kırmızı görünür. Telegram'a mesaj gelmiyorsa önce oraya bak.
