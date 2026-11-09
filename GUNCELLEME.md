# İleride güncelleme veya değişiklik

Claude Code'u Mac'inizden kaldırsanız da sistem çalışmaya devam eder. Değişiklik istediğinizde üç yol var; en kolayından zoruna:

## 1. Claude Code (web) — önerilen, bilgisayar gerekmez

1. Telefondan veya herhangi bir tarayıcıdan **claude.ai/code** adresine gidin (mevcut Claude aboneliğiniz yeterli, ek ücret yok).
2. İlk seferde GitHub hesabınızı bağlayın ve `bist-rapor` deposunu seçin.
3. Ne istediğinizi Türkçe yazın, örneğin:
   * "İzleme listeme KCHOL ve SAHOL'u ekle."
   * "Kapanış raporuna altın fiyatı yorumu ekle."
   * "config/macro.json'daki PPK tarihlerini 2027 takvimine göre güncelle."
4. Claude değişikliği yapar, testleri çalıştırır ve depoya kaydeder. Sonraki rapor yeni kodla üretilir.

## 2. Normal Claude sohbeti (claude.ai) + GitHub web düzenleyici

1. claude.ai'de yeni sohbet açın ve şunu yapıştırın:
   > "GitHub'daki bist-rapor depomda (Python, GitHub Actions ile çalışan BIST rapor sistemi) şu değişikliği yapmak istiyorum: … Hangi dosyada neyi değiştirmeliyim? Değişecek dosyanın tam yeni halini ver."
2. İlgili dosyanın içeriğini GitHub'dan kopyalayıp sohbete ekleyin (dosyayı açın → kopyala simgesi).
3. Claude'un verdiği yeni içeriği GitHub'da dosyayı açıp kalem simgesiyle düzenleyerek yapıştırın → **Commit changes**.

## 3. Basit ayar değişiklikleri (Claude gerekmez)

| Ne değişecek | Dosya | Nasıl |
|---|---|---|
| İzleme listesi | `config/watchlist.txt` | Her satıra bir kod |
| İşlem başı risk, günlük zarar sınırı, komisyon | `config/settings.json` → `risk` | Sayıyı değiştirin (ör. `0.5`) |
| Sermaye dağılımı (simülasyon) | `config/settings.json` → `capital_split_pct` | Yüzdeler |
| Taranan hisseler / sektörler | `config/universe.json` | Satır ekleyin/silin |
| Tatil günleri | `config/calendar.json` | `"2027-xx-xx": "Ad"` |
| PPK tarihleri, enflasyon | `config/macro.json` | Tarih/sayı |

GitHub'da dosyayı açın → kalem (✏️) → değiştirin → **Commit changes**.

## Bir şey bozulursa

* Sitede **Daha → Veri kaynağı ve sistem durumu** sayfası son çalışmaları ve hataları gösterir.
* GitHub hata durumunda e-posta gönderir.
* Yapılan her değişiklik geri alınabilir: GitHub'da dosya → **History** → önceki sürüm.
* Claude Code (web)'e "Son değişiklikten sonra raporlar hata veriyor, düzelt" yazmanız yeterlidir.

## Maliyet

Bu yolların hiçbiri ek ücret gerektirmez. Claude'a API anahtarı vermeyin; sistem Anthropic API kullanmaz.
