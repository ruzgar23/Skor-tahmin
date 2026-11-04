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

## Canlı karne, hokey ve tenis
- Gönderilen canlı seçimler takip edilir. Tutan seçim için anında **WON** bildirimi gelir. Tüm canlı seçimler (tutan ve tutmayan) ertesi sabahki karnede yer alır.
- **Hokey (NHL):** iddaa'da hokeyde maç sonucu normal süreye göre (uzatmasız) belirlenir. Olasılıklar DraftKings oranlarından, beraberliği gerçeğe göre artırılmış bir Poisson modeliyle hesaplanır.
  2025-26 testinde 1X/X2 seçimleri %75 üstünde %84, 4,5 Üst seçimleri %80 üstünde %83 tuttu. Komut: `/hokey`.
- **Tenis (ATP/WTA):** ESPN'deki ~46 bin tekler maçından Elo modeli (genel + yüzey). 2024-26 testinde %80 üstü favoriler %86, %70-80 arası favoriler %74 kazandı.
  Tenis için geçmiş oran verisi olmadığından kârlılık test edilemedi. Komut: `/tenis`.
- **NBA:** 2025-26 testinde (1.164 maç) Güçlü (≥%75) seçimler %82, Orta (%65-75) seçimler %73 kazandı. Handikap ve alt/üst ~%50 tuttuğu için bunlara öneri verilmez.
- Testler `backtest/diger_sporlar/` klasöründe.

## Büro payı yöntemi (backtest ile değişti)
- Adil olasılık artık **power** yöntemiyle hesaplanıyor (önceden oransal). 25.907 maçlık testte (2019-26, 12 lig) oransal yöntem %65+ favorilerin olasılığını 2–4 puan düşük gösteriyordu; power ile fark 0–1,5 puana indi ve log-loss tüm kaynaklarda iyileşti.
- Etkisi: daha fazla maç Güçlü eşiğini geçer (haftada ~10,6 → ~13,2), Güçlü tutma oranı %79,8 → %78,3 olur ama gösterilen olasılık gerçeğe daha yakındır. Ortalama orana göre getiri değişmedi (her iki yöntemde ≈ −%1,3).
- Pinnacle oranları piyasa ortalamasından çok az daha isabetli; fark seçimlere yansımadığı için kaynak değiştirilmedi. Maça yakın (kapanış) oranlar belirgin şekilde daha iyi; teyit adımı bu yüzden işe yarıyor.
- Test: `python -I backtest/margin_test.py <football-data klasörü>` (klasör yapısı: `<sezon>/<lig>.csv`).

## Canlı korner, kural düzeltmeleri ve canlı veri kaydı
- **Canlı korner:** 55–80. dakika arasında korner alt/üst seçimi (maç başına bir kez; yalnızca testte verisi olan liglerde: Premier League, Championship, La Liga 1–2, Serie A, Eredivisie, Ligue 1, Portekiz, Bundesliga). Kalan korner; takımların maç öncesi korner beklentisi, maç içi tempo, skor durumu (geride olan %17 fazla, önde olan %21 az), kırmızı kartlar ve ~6,8 dakikalık uzatma ile hesaplanır.
  ESPN anlatımlarından 7.092 maçlık testte (2023-25 öğrenme, 2025-26 test) seçimlerin %83,4'ü tuttu (beklenen %83,5). Süper Lig'de dakika verisi olmadığı için orada şimdilik öneri verilmez; canlı veri kaydı biriktikçe eklenecek. Test: `backtest/live_events.py` + `backtest/live_corner_test.py`.
- **2,5 Üst artık en fazla Orta:** %70 üstü 2,5 Üst seçimleri 8 sezonda %70–74 tutuyordu (MS Güçlü ~%79). Güçlü seçimler artık yalnızca MS: %78,7.
- **Canlı KG Yok:** olasılığı 2 puan düşürülerek gösterilir (devre arası testinde ~2 puan iyimserdi). Düzeltme sonrası %77,9 tuttu, beklenen %77,7.
- **Canlı veri kaydı:** her canlı kontrolde dakika, skor, korner, kart ve şut sayıları `state/run/live_log/` altına aylık dosyalara yazılır (yalnızca değişen anlar). Bu veri birikince Süper Lig ve kart pazarları da test edilebilecek.

## Ek seçimler: ilk yarı ve takım golü
- Günün seçimlerinde yeni bölüm: **İY 0,5 Üst, İY 1,5 Alt, Ev/Dep gol 0,5–1,5 Üst, Ev/Dep gol 1,5–2,5 Alt**. Maç başına en fazla bir ek seçim, olasılığı %70–80 arası, günde en çok 6 tane; karnede ayrıca sayılır.
- 7 sezonluk testte (24.863 seçim) %76,9 tuttu (beklenen %76,0); her sezon %76–78. Bot kodu 2025-26'da %76,5 tuttu. Test: `backtest/new_markets_test.py`.
- **Eklenmeyenler:** Asya handikabında model ile piyasa farkından kâr çıkmadı (−%6 / −%9). Handikaplı çifte şans iddaa'da olmadığından Avrupa handikabı eklenmedi. İY maç sonucu çok az seçim üretiyor.

## Canlı: gerçek gol eğrisi ve yeni pazarlar
- **Gol zamanlaması:** Canlı model artık golleri dakikalara eşit dağıtmıyor; ESPN'deki 13.401 maçın (36.548 gol) gerçek dağılımını kullanıyor. Goller devre sonlarına doğru artıyor, %4'ü ilk yarı, %8'i maç sonu uzatmasında atılıyor. Eski model kalan golü düşük tahmin ediyordu: takım gol Alt seçimleri beklenenden 2 puan, İY 0,5 Alt 7 puan az tutuyordu; şimdi sapma 0–1 puan.
- **Yeni canlı pazarlar:** İY sonucu, İY 0,5/1,5 Alt-Üst (yalnızca ilk yarıda), Ev/Dep gol Alt-Üst, sıradaki golü kim atar. İlk yarı seçimleri devre skoruyla (maç olaylarından) sonuçlandırılır.
- **Düzeltmeler:** Çifte şans 12 olasılığı 2 puan düşük gösterilir (her iki dönemde de ~2 puan iyimserdi); KG Yok düzeltmesi gerçek eğriyle gereksiz kaldığı için kaldırıldı.
- **Bildirim simülasyonu (2025-26, 4.642 maç, maç başına ilk bildirim):** eski sürüm %82,4, yeni sürüm %84,5 tuttu (beklenen %83,0). Test: `backtest/goal_events.py`, `backtest/live_goal_test.py`, `backtest/live_alert_sim.py`.

## Birleşik bahisler (/mac ve /kupon)
- `/mac takım`: MS & 2,5 Alt/Üst, MS & KG, çifte şans & 2,5 olasılıkları ve adil oranları.
- `/kupon`: `galatasaray 1 2.5 üst 2.40`, `barcelona 1 kg 3.10`, `arsenal 1x 2.5 alt 2.05`, `lazio iy 1.5 alt 1.40` gibi satırlar.
- Günlük seçim olarak verilmez: 8 sezonda %60+ olasılıklı birleşik seçim haftada birkaç tane ve Orta seviyesinde (%65) tutuyor. Test: `backtest/combo_test.py`.

## İkinci yarı bahisleri ve devre arası bildirimi
- **Yeni canlı pazarlar:** 2Y sonucu (1/X/2) ve 2Y 0,5/1,5 Alt-Üst; devre arasında ve ikinci yarıda, devre skoru (maç olaylarından) biliniyorsa. Sonuç, devreden sonraki gollerle belirlenir.
- **Devre arası bildirimi:** Her maç için devre arasında bir kez, ikinci yarı pazarlarından %70–88 arası en olası seçim (gol ve korner bildirimlerinden ayrı). Testte 2025-26'da %79,8 (beklenen %79,1), 2023-25'te %79,7 (beklenen %78,9) tuttu; çoğu "2Y 0,5 Üst".
- 2Y sonucu 2023-25'te kalibre, 2025-26'da ~3 puan iyimserdi; iki dönemin ortalaması kadar (1,5 puan) düşük gösterilir. 2Y 0,5 Üst %77,9 (beklenen %77,2), 2Y 1,5 Alt %78,8 (beklenen %78,3).

## Kupalarda ek seçim yok
- Avrupa kupalarında (ŞL, AL, KL) ek seçimler (İY, takım golü) verilmez. 2026'daki 351 kupa maçında (ESPN, DraftKings oranları) ek seçimler %72,6 tuttu, beklenen %76,3'tü. Sebep: kupalarda güçlü-zayıf farkı büyük, maçların %25'i 3+ farkla bitiyor (liglerde %15) ve model bunu ~3 puan az tahmin ediyor; özellikle favorinin "gol Alt" seçimleri tutmuyor.
- Kupalarda ana seçimler etkilenmiyor: Güçlü %82,9 (beklenen %80,0), Orta %65,7 (beklenen %65,3). Test: `backtest/cup_events.py`, `backtest/cup_test.py`.

## Riskli seçimler (/riskli, oran 1,75+)
- Adil oranı 1,75–2,00 (tutma olasılığı %50–57) olan bahislerden maç başına en olası tek seçim, günde en çok 8 tane: MS 1/2, 2,5 Alt/Üst, 3,5 Alt, KG Var, Ev/Dep gol 1,5 Üst, İY 1,5 Üst ve birleşikler (MS 1/MS 2/12/X2 & 2,5 Üst). Testte kalibre çıkmayan KG Yok, 1X & 2,5 Üst ve MS & KG Yok listede yok.
- Her sabah ayrı kart olarak gönderilir, `/riskli` ile istenir, karnede ayrı sayılır. Birim: ¼.
- Test (`backtest/risky_test.py`): lig maçlarında 24.840 seçimin %55,2'si tuttu (beklenen %54,6; 8 sezonun hepsinde %54–57,5); kupalarda 311 seçimin %59,8'i (beklenen %54,5). Piyasa ortalaması oranla oynandığında getiri −%4,7: kâr ancak iddaa oranı kartta yazan sınırın üstündeyse mümkün.
