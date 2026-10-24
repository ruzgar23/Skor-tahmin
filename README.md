# Skor Tahmin Masası

Futbol maçları için olasılık tahminleri: maç sonucu, çifte şans, alt/üst, karşılıklı gol, ilk yarı, en olası skorlar ve maç sırasında canlı analiz. Sonuçlar bir web sayfasında yayınlanır ve bir Telegram botuyla gönderilir. Her şey GitHub Actions üzerinde ücretsiz çalışır; sunucu ya da açık bilgisayar gerekmez.

> Olasılıklar garanti değildir. %70'lik bir seçim de 10 maçın 3'ünde yatar. Kaybetmeyi göze alamayacağın parayla oynama.

## Ne yapar

| Ne zaman | Ne gelir |
|---|---|
| Her sabah 09:30 (TR) | Dünün karnesi ve günün güçlü/orta önerileri (seçim, olasılık, oynamaya değmesi için gereken en düşük iddaa oranı) |
| Maç saatlerinde, 5 dakikada bir | Canlı fırsat adayları: dakika, skor, kartlar, seçim, olasılık, gereken en düşük canlı oran |
| Gün içinde | Oran düşüşü uyarıları: bir maçın oranı açılıştan bu yana belirgin şekilde düşerse |
| Her zaman (birkaç saniye içinde) | Bot komutları: `/secimler`, `/bugun`, `/guclu`, `/orta`, `/canli`, `/mac takım`, `/basket`, `/kupon`, `/karne`, `/nasil`, `/dur` |

Mesajlar görsel kartlar olarak gelir: her seçimde "OYNA" talimatı, tutma ihtimali çubuğu, güven yıldızları ve oynamaya değmesi için gereken en düşük iddaa oranı yazar. Çok sayfalı listeler kaydırılabilir albüm olarak gönderilir.

**Kupon değerlendirme:** Bota her satıra bir maç gelecek şekilde kuponunu yaz:

```
/kupon
galatasaray 1 1.85
arsenal 2.5 üst 1.70
fenerbahçe kart 4.5 üst 1.80
lakers 2 1.95
```

Bot her seçimin olasılığını, oranının değerli olup olmadığını ve kuponun toplam tutma olasılığını söyler.

Kapsam (futbol): Premier League, Championship, League One/Two, La Liga 1–2, Serie A–B, Bundesliga 1–2, Ligue 1–2, Süper Lig, Eredivisie, Portekiz, İskoçya (4 lig), Yunanistan, Şampiyonlar Ligi, Avrupa Ligi, Konferans Ligi. Basketbol: NBA ve WNBA.

## Nasıl çalışır

- **Maç öncesi:** Olasılıkların ana kaynağı, büro payı çıkarılmış piyasa oranlarıdır. KG, ilk yarı ve skor dağılımı bu oranlara uydurulmuş gol beklentisinden (Poisson, Dixon-Coles düzeltmesi) hesaplanır. Oran yoksa maç bazlı model kullanılır: zamana ağırlıklı, rakip gücünü hesaba katan, takıma özel iç saha etkisi olan ve gol ile xG'yi harmanlayan bir model. Bu maçlar "düşük güven" olarak işaretlenir.
- **Güven seviyeleri:** 8.152 maçlık geriye dönük testte güçlü öneriler %74–80, orta öneriler %63–67 tuttu.
- **Canlı:** Maç öncesi gol beklentisi kalan süreye, skora ve kırmızı kartlara göre güncellenir. Ayarlar 13.598 maçlık devre arası verisinden yapıldı. Şut, isabetli şut, korner ve şut konumundan xG de test edildi; tahmini iyileştirmedikleri için modelde yer almıyorlar (2.687 maç, sezon içi eğitim/test ayrımıyla).
- **Kart:** Takım ve hakem bazlı model. Lig ortalamasına göre %3–5 daha iyi tahmin ediyor; "%70+" seçimlerin %71–77'si tuttu (2025-26, 6.783 maç). Kart için piyasa oranı verisi yok.
- **Korner:** Tahmin gösterilir ama öneri verilmez; testte lig ortalamasından yalnızca çok az iyi çıktı.
- **Basketbol:** Olasılıklar DraftKings oranlarından. Geçen sezon %75+ favoriler %76–85, %65–75 favoriler %64–76 kazandı (1.064 NBA maçı). Handikap ve alt/üst çizgileri ~%50 olduğu için öneri verilmez.
- **Oran hareketi:** Açılış ile güncel oran arasında olasılığı 6 puandan fazla değişen taraflar bildirilir. Bu bir bilgi, oynama sinyali değil.
- **Kâr kanıtı yok:** Modelin piyasadan farklı düşündüğü bahisleri oynamak testte yaklaşık %15 kaybettirdi. Araç olasılıkları doğru tahmin eder; büroyu yendiğini iddia etmez.

Veri kaynakları: [football-data.co.uk](https://football-data.co.uk) (sonuçlar, oranlar, xG) ve ESPN'in herkese açık skor servisi (fikstür, canlı skor, oranlar). Bu kaynakların kendi kullanım koşulları geçerlidir; proje kişisel ve ticari olmayan kullanım içindir.

## Kendi botunu kur (5 dakika)

1. **Depoyu kopyala:** Sağ üstteki **Fork** düğmesine bas.
2. **Telegram botu oluştur:** Telegram'da [@BotFather](https://t.me/BotFather)'a `/newbot` yaz, ad ver ve verdiği token'ı kopyala.
3. **Token'ı gizli olarak ekle:** Deponda **Settings → Secrets and variables → Actions → New repository secret**. Ad: `TELEGRAM_TOKEN`, değer: token. Token koda ya da sayfaya hiçbir zaman yazılmaz.
4. **Sayfayı aç:** **Settings → Pages → Branch: `gh-pages` / `(root)` → Save.** `gh-pages` dalı ilk çalışmadan sonra oluşur; listede yoksa 5. adımdan sonra tekrar bak.
5. **Otomasyonu başlat:** **Actions** sekmesinde iş akışlarını etkinleştir, sonra **Bot → Run workflow** ile ilk çalışmayı başlat. Bundan sonra bot kendini sürekli yeniden başlatır.
6. **Botuna yaz:** Telegram'da botunu aç ve `/start` gönder. Komutlara birkaç dakika içinde cevap gelir; sabah mesajları ertesi gün başlar.

İsteğe bağlı ayarlar (**Settings → Secrets and variables → Actions → Variables**):

| Değişken | Ne işe yarar |
|---|---|
| `SITE_URL` | Mesajlardaki sayfa linki. Boş bırakılırsa GitHub Pages adresi otomatik kullanılır |
| `TELEGRAM_CHAT_ID` | Ek alıcılar, virgülle ayrılmış. Örn. herkese açık bir kanal: `@kanaladi` (botu kanala yönetici olarak ekle) |

Bota `/start` yazan herkes bildirimleri alır, `/dur` ile kapatır. Abone listesi depoda değil, Actions önbelleğinde tutulur.

## Dosyalar

- `engine/`: model ve veri (`engine.py` gol modeli, `scan.py` tarama, `espn.py` fikstür ve canlı veri, `live.py` canlı analiz, `corners.py` kart ve korner, `nba.py` basketbol)
- `bot/`: Telegram botu (`run.py` giriş noktası, `core.py` öneri ve mesaj biçimleri, `extra.py` kupon, kart, basketbol ve oran hareketi, `tg.py` Telegram API)
- `site/`: web sayfası (`gh-pages` dalına veriyle birlikte yayınlanır; bahis defteri yalnızca ziyaretçinin tarayıcısında saklanır)
- `.github/workflows/bot.yml`: tek sürekli iş. Komutları dinler, canlı takip yapar, sabah taramasını çalıştırır; ~55 dakikada bir kendini yeniden başlatır

## Notlar

- GitHub'ın zamanlanmış çalışmaları saatlerce gecikebildiği için bot zamanlayıcıya güvenmez: her çalıştırma sonunda bir sonrakini kendisi başlatır. Zamanlayıcı (30 dakikada bir) yalnızca zincir koparsa devreye girer.
- Herkese açık depolarda Actions süresi ücretsizdir. Bot sürekli çalıştığı için gizli bir depoda aylık ücretsiz süre yetmez; depoyu herkese açık tut.
- Bir iş başarısız olursa Actions sekmesinde kırmızı görünür. Telegram'a mesaj gelmiyorsa önce oraya bak.

## Maç önü teyit ve birim (backtest ile eklendi)
- Sabah gönderilen seçimler maça ~1 saat kala güncel oranla tekrar kontrol edilir. İhtimali 2 puan ya da daha fazla düşen seçim **iptal** edilir.
  49 bin maçlık 8 sezonluk testte bu, Güçlü seçimlerin tutma oranını %79,7 → %80,5'e, Orta seçimlerinkini %65,2 → %66,4'e çıkardı.
- Birim önerisi: Güçlü 1 birim, Orta ½ birim (1 birim = kasanın %2'si).
- Yorgunluk, Avrupa maçı, sezon sonu motivasyonu, ilk 11 eksikleri ve lig bazlı ayar da test edildi; piyasa bunları zaten fiyatladığı için eklenmedi. Testler `backtest/` klasöründe.
