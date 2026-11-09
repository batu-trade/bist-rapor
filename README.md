# BIST Kişisel Yatırım Asistanı

Her işlem günü Borsa İstanbul için **dört Türkçe rapor** üreten, raporları telefondan açılan bir web sitesinde yayınlayan, **tamamen ücretsiz** ve **bilgisayarınızdan bağımsız** çalışan kişisel sistem.

> Yatırım tavsiyesi değildir. Gerçek emir göndermez. Veriler ücretsiz ve gecikmelidir.

## Ne yapar?

| Saat (İstanbul) | Rapor | İçerik |
|---|---|---|
| 09:45 | Açılış öncesi | Önceki kapanış, küresel piyasalar, gece haberleri, KAP başlıkları, ekonomik takvim, izlenecek hisseler, destek/direnç, senaryolar, riskler |
| 10:15 | Açılış sonrası | Endeks açılışı, ilk hacim, en güçlü/zayıf hisseler, sektörler, gün içi sinyaller, 09:45'e göre değişim |
| 14:00 | Gün ortası | Yön, açılıştan beri değişim, gün içi + swing fırsatları, sektör rotasyonu, geçersiz kalan sinyaller, simülasyon portföyü |
| 18:15 | Kapanış | Kapanış, sektörler, hacim, KAP, sinyal performansı, simülasyon sonuçları, swing listesi, uzun vade değişiklikleri, yarının görünümü |

Ayrıca sitede: hisse arama ve detay sayfaları, gün içi / swing / uzun vade fırsat listeleri, **yalnızca telefonunuzda saklanan** portföy takibi, pozisyon büyüklüğü hesaplayıcı, rapor arşivi, haberler, veri kalitesi ve sistem durumu, terimler sözlüğü.

## Nasıl çalışır?

```
GitHub Actions (ücretsiz bulut zamanlayıcı)
   └─ python -m bist run      -> Yahoo Finance, TCMB, Google Haberler'den veri çeker, analiz eder,
                                  data/ klasörüne rapor JSON'u yazar (git'e kaydeder)
   └─ python -m bist site     -> web/ + data/ -> statik site
   └─ GitHub Pages            -> https://KULLANICI.github.io/DEPO/  (telefonda aç, ana ekrana ekle)
```

* Bilgisayarınızın açık olması gerekmez; Claude Code gerekmez.
* Ek Python paketi gerekmez (yalnızca standart kütüphane). Testler için `pytest`.

## Dürüstlük kuralları

* Yahoo'nun BIST verisi **yaklaşık 15 dakika gecikmelidir**; gerçek zamanlı gösterilmez. Gecikme her raporda ölçülür.
* Veri kalitesi her raporda gösterilir: Güvenilir / Gecikmeli / Eksik / Bayat / Veri yok. Kalite düşükse sinyal üretilmez.
* Veri alınamazsa rapor uydurulmaz; açık bir uyarı yayınlanır.
* Her bilgi etiketlidir: doğrulanmış veri, hesaplanmış gösterge, algoritmik yorum, olası senaryo.
* Rapor geç üretildiyse gerçek üretim saati ve gecikme yazılır.
* KAP otomatik erişime kapalıdır ve ücretsiz API sunmaz; KAP ile ilgili **haber başlıkları** Google Haberler RSS'ten alınır ve doğrulama için KAP'a yönlendirilir.

## Klasörler

| Yol | Açıklama |
|---|---|
| `bist/` | Analiz kodu (veri, göstergeler, tarayıcı, gün içi, swing, temel analiz, haber, risk, simülasyon, raporlar, site) |
| `web/` | Mobil web sitesi (PWA) |
| `config/watchlist.txt` | İzleme listeniz (her satıra bir hisse kodu) |
| `config/settings.json` | Risk ve sermaye ayarları |
| `config/universe.json` | Taranan hisse evreni ve sektörler (resmî endeks listesi değildir) |
| `config/calendar.json` | BIST tatil ve yarım gün takvimi |
| `config/macro.json` | PPK tarihleri ve yıllık enflasyon (elle güncellenir) |
| `data/` | Bulutta üretilen raporlar, durum, simülasyon defteri (otomatik) |
| `tests/` | Testler |

Kurulum: [KURULUM.md](KURULUM.md) · Güncelleme ve değişiklik: [GUNCELLEME.md](GUNCELLEME.md)
