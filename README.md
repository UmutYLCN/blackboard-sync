# Blackboard Sync

Yeni ders içeriklerini otomatik indirip Blackboard’daki klasör yapısıyla bilgisayarına kaydeder. Arka planda her saat kontrol eder, yeni bir şey geldiğinde bildirim gösterir.

## Kurulum

[Son sürümü indir](https://github.com/UmutYLCN/blackboard-sync/releases/latest):

- **macOS:** `Blackboard-Sync-<version>.dmg` dosyasını aç, **Blackboard Sync** uygulamasını **Uygulamalar (Applications)** klasörüne sürükle. İlk açılışta sağ tık → **Aç** seçeneğini kullan.
- **Windows:** `Blackboard-Sync-<version>-Setup.exe` dosyasını çalıştır ve kurulumu tamamla. SmartScreen uyarısı çıkarsa **Ek bilgi → Yine de çalıştır** seçeneğini kullan.

Giriş için bilgisayarında Chrome, Edge, Brave, Vivaldi, Opera, Opera GX, Chromium veya Arc (macOS) gibi Chromium tabanlı bir tarayıcı bulunmalı; Python kurman gerekmez. İlk açılışta okulunun Blackboard adresini ve kayıt klasörünü seç, **Giriş yap** düğmesine bas ve tarayıcıda girişini tamamla.

## Kullanım

macOS’ta menü çubuğundaki, Windows’ta saatin yanındaki simgeden:

- **Şimdi senkronize et** ile hemen kontrol et; **Silinenleri tekrar indir** ile bilgisayarından sildiğin dosyaları geri indir.
- **Okul klasörünü aç** ve **Son indirilenler** ile içeriklerine ulaş.
- **Ayarlar…** ile okul adresini, klasörü ve **Bilgisayar açılınca başlat** seçeneğini değiştir.

Güncellemeler varsayılan olarak otomatik denetlenir. Menüdeki sürüm satırından elle de denetleyebilir, yeni sürüm varsa **Güncelle** seçeneğini kullanabilirsin.

## Gizlilik

Şifren hiçbir zaman uygulamadan geçmez; girişini tarayıcıda yaparsın. Oturumun sadece bu bilgisayarda saklanır.

Lisans: [MIT](LICENSE). Geliştirme ve komut satırı kullanımı: [geliştirici rehberi](docs/DEVELOPMENT.md).
