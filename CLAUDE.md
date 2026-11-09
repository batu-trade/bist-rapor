# CLAUDE.md — BIST Kişisel Rapor Sistemi

Kullanıcı Türk, teknik bilgisi sınırlı küçük bir yatırımcı. Her zaman **sade Türkçe** konuş, terimleri açıkla.

## Değişmez kurallar
1. **Sıfır maliyet:** ücretli API, abonelik, barındırma, VPS, Anthropic API yok. Ücret doğurabilecek her adım için önce açık onay al.
2. **Bilgisayardan bağımsız:** her şey GitHub Actions + GitHub Pages'te çalışır. Mac'e veya Claude Code'a bağımlılık ekleme.
3. **Telegram ve e-posta yok:** raporlar yalnızca mobil web sitesinde (https://batu-trade.github.io/bist-rapor/).
4. **Dürüst veri:** Yahoo BIST verisi ~15 dk gecikmeli, gerçek zamanlı gösterme. Veri yoksa uydurma, uyar. Kalite düşükse sinyal üretme, öneri zorlama.
5. **Gerçek emir yok, yatırım tavsiyesi yok:** yalnızca simülasyon.
6. **Kişisel portföy sunucuya gitmez** (telefonda localStorage). Depo herkese açık: config'e gerçek para miktarı yazma.
7. **Çalışan sistemi bozma:** her değişiklikte `python -m pytest -q` geçmeden `main`'e koyma.

## Sistem
- Python 3.12, yalnızca standart kütüphane; testler pytest.
- `.github/workflows/reports.yml`: hafta içi erken tetiklenir, `python -m bist plan` rapor saatine (09:45, 10:15, 14:00, 18:15 İstanbul, UTC+3) kadar bekletir, `python -m bist run --slot auto` üretir, `data/` commit edilir, `python -m bist site` Pages'e yayınlar. Mükerrer önleme: `data/state/runs.json`.
- `.github/workflows/bootstrap.yml`: `setup/bundle.b64` (base64 tar.gz) yüklenince paketi açar, testleri koşar, geçerse commit eder. İş akışı dosyaları paketle güncellenemez.
- Kod: `bist/` (yahoo, quality, indicators, market, scanner, intraday, swing, fundamentals, news, risk, paper, reports, site, state), site: `web/`, testler: `tests/`.
- Kullanıcıya gösterilen sayılar `bist/fmt.py` ile Türkçe biçimlenir (`fmt.num`, `fmt.pct`, `fmt.signed`).

## Ayarlar
`config/watchlist.txt` (izleme listesi), `config/settings.json` (risk %0,5 / günlük %1,5, komisyon, kayma, sermaye dağılımı), `config/universe.json` (taranan hisseler — resmî BIST 100 listesi değil), `config/calendar.json` (tatiller; 2027 bayramları tahmini), `config/macro.json` (PPK, TÜFE; elle güncellenir).

## Kontrol
- Çalıştırmalar: https://api.github.com/repos/batu-trade/bist-rapor/actions/workflows/reports.yml/runs
- Durum: `data/state/runs.json`, raporlar: `data/reports/YYYY-MM-DD/<premarket|opening|midday|close>.json`
- Normal: 10:15 raporunun "eksik" kalitede ve gün içi sinyalsiz olması; birkaç dakikalık zamanlayıcı gecikmesi.

## Bilinen kısıtlar
KAP otomatik erişime kapalı → başlıklar Google Haberler RSS'ten. Yahoo temel verileri eksik olabilir; enflasyon muhasebesi nedeniyle büyüme TÜFE ile reelleştirilir. Değerleme yalnızca aynı sektörde kıyaslanır. Ayrıntı: README.md, KURULUM.md, GUNCELLEME.md.
