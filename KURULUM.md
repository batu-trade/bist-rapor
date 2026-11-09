# Kurulum ve günlük kullanım

Bu sistem bir kez kurulur; sonra her işlem günü kendi kendine çalışır. Bilgisayarınızın açık olması, Claude Code'un yüklü olması gerekmez.

## Neden GitHub?

| Seçenek | Ücretsiz mi? | Bilgisayar kapalıyken çalışır mı? | Sonuç |
|---|---|---|---|
| **GitHub Actions + GitHub Pages** | Evet (herkese açık depoda dakika sınırı yok) | Evet | **Seçildi**: hem zamanlayıcı hem web sitesi tek hesapta |
| Mac'te zamanlanmış görev / Claude Code | Evet | **Hayır** (Mac açık olmalı) | Uygun değil |
| Google Apps Script | Evet | Evet | Python çalıştıramaz; kod baştan yazılmalı |
| Cloudflare Workers / Pages | Evet | Evet | Python analizi için uygun değil; ikinci hesap gerekir |
| PythonAnywhere ücretsiz | Kısmen | Evet | Ücretsiz planda dış sitelere erişim kısıtlı; zamanlı görev günde 1 |
| VPS / ücretli barındırma | Hayır | Evet | Maliyet kuralınız nedeniyle elendi |

GitHub'ı öğrenmeniz gerekmez: kurulumu sizin adınıza yapıyoruz. Sizin yapmanız gereken tek şey bir GitHub hesabı açmak ve giriş yapmak (hesap açma ve şifre girme işlemlerini güvenlik nedeniyle yalnızca siz yapabilirsiniz).

### Ücretsiz plan sınırları (kontrol edildi)

* GitHub Actions: herkese açık depolarda standart çalıştırıcılar ücretsizdir ve dakika sınırı yoktur. Bir çalıştırma en fazla 6 saat sürebilir (bizimki 2–10 dk).
* Zamanlanmış görevler **tam dakikasında garanti edilmez**; yoğunlukta gecikebilir veya nadiren atlanabilir. Bu yüzden her rapor erken tetiklenir ve kurtarma tetiklemeleri vardır.
* Herkese açık depoda **60 gün hiç işlem olmazsa** zamanlanmış görevler durdurulur. Sistem her işlem günü rapor verisini kaydettiği için bu süre dolmaz.
* GitHub Pages: site boyutu 1 GB, aylık ~100 GB trafik (kişisel kullanım için fazlasıyla yeterli).
* Hiçbir yere kredi kartı girilmez. Ücretli bir özellik açılmaz.

### Gizlilik

* Depo ve site **herkese açıktır ama adresi yalnızca sizdedir**; arama motorlarına kapalıdır (`noindex`).
* Sitede yalnızca piyasa raporları ve simülasyon sonuçları vardır.
* **Kişisel portföyünüz** sitedeki "Portföyüm" sekmesinde yalnızca telefonunuzun tarayıcısında saklanır, hiçbir sunucuya gönderilmez.
* `config/settings.json` içine gerçek para miktarı yazmayın.

## Kurulum adımları

1. **GitHub hesabı** — github.com/signup adresinden ücretsiz hesap açın (e-posta, şifre, kullanıcı adı). Ücretli plan seçmeyin; "Free" yeterli.
2. **Giriş** — Claude uygulamasının içindeki tarayıcıda github.com'a giriş yapın.
3. Gerisini Claude yapar:
   * `bist-rapor` adında herkese açık bir depo oluşturur,
   * iki iş akışı dosyasını (`.github/workflows/reports.yml`, `bootstrap.yml`) ve kod paketini (`setup/bundle.b64`) yükler,
   * paket bulutta açılır, **testler bulutta çalışır**, geçerse kod kaydedilir,
   * Ayarlar → Pages bölümünde kaynak olarak "GitHub Actions" seçilir,
   * ilk rapor elle üretilir ve site adresi doğrulanır.
4. **Telefonda açın** — site adresi: `https://KULLANICI-ADINIZ.github.io/bist-rapor/`
   * iPhone: Safari'de açın → Paylaş → **Ana Ekrana Ekle**
   * Android: Chrome'da açın → ⋮ → **Ana ekrana ekle**

## Günlük kullanım

* Hiçbir şey yapmanız gerekmez. Ana ekrandaki "BIST Rapor" simgesine dokunun.
* **Bugün** sekmesinde dört rapor arasında üstteki düğmelerle geçiş yapın.
* Bir rapor gecikirse, raporda "X dk gecikmeli üretildi" yazar. Kaçırılırsa "kaçırıldı" yazar.
* GitHub, bir çalıştırma hata verirse hesabınızın e-posta adresine **ücretsiz bildirim** gönderir.

## Elle rapor üretmek (isteğe bağlı)

Sitede **Daha → Raporu şimdi elle üret** bağlantısına dokunun → GitHub'da **Run workflow** → rapor türünü seçin → **Run workflow**. Birkaç dakika sonra sitede görünür.

## İzleme listesini değiştirmek (isteğe bağlı)

Sitede **Daha → İzleme listesini düzenle** → GitHub'da açılan dosyada her satıra bir hisse kodu yazın (örn. `KCHOL`) → **Commit changes**. Sonraki rapordan itibaren geçerlidir.

## Bilinen sınırlamalar

* Ücretsiz BIST verisi ~15 dk gecikmelidir. **10:15 raporunda** genellikle yalnızca açılış ve ilk birkaç dakikanın verisi bulunur; bu yüzden gün içi sinyaller genelde 14:00 raporunda çıkar. Sistem bayat veriyle sahte sinyal üretmez.
* KAP'a doğrudan erişilemez; KAP haberleri Google Haberler başlıklarından gelir.
* Temel analiz verisi (Yahoo) BIST şirketleri için eksik olabilir; enflasyon muhasebesi nedeniyle büyüme oranları yaklaşıktır.
* Taranan hisse listesi resmî BIST 100 listesi değildir (yaklaşık 75 likit hisse + izleme listeniz).
* 2027 bayram tarihleri tahminidir; ayrıca sistem tatil gününde veri gelmediğini algılayıp rapor uydurmaz.
* `config/macro.json` (PPK tarihleri, enflasyon) yılda birkaç kez güncellenmelidir; eskiyince raporlar uyarır.
