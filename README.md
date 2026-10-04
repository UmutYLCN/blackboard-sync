# Blackboard Sync

Yeni ders içeriklerini otomatik indirip Blackboard’daki klasör yapısıyla bilgisayarına kaydeder. Arka planda her saat kontrol eder, yeni bir şey geldiğinde bildirim gösterir.

## Kurulum

[Son sürümü indir](https://github.com/UmutYLCN/blackboard-sync/releases/latest):

- **macOS:** `Blackboard-Sync-<version>.dmg` dosyasını aç, **Blackboard Sync** uygulamasını **Uygulamalar (Applications)** klasörüne sürükle. İlk açılışta sağ tık → **Aç** seçeneğini kullan.
- **Windows:** `Blackboard-Sync-<version>-Setup.exe` dosyasını çalıştır ve kurulumu tamamla. SmartScreen uyarısı çıkarsa **Ek bilgi → Yine de çalıştır** seçeneğini kullan.

Python kurman gerekmez. Bilgisayarında Chrome, Edge, Brave, Opera, Vivaldi gibi bir tarayıcı varsa giriş onda açılır; yoksa uygulamanın kendi penceresinde açılır, tarayıcı gerekmez. İlk açılışta okulunun Blackboard adresini ve kayıt klasörünü seç, **Giriş yap** düğmesine bas ve açılan pencerede girişini tamamla.

## Kullanım

macOS’ta menü çubuğundaki, Windows’ta saatin yanındaki simgeden (Windows’ta simge görünmüyorsa saatin yanındaki **^** okuna, yani gizli simgelere bak):

- **Şimdi senkronize et** ile hemen kontrol et.
- **Dersler**, **Son indirilenler** ve kayıt klasörünün adını taşıyan **… klasörünü aç** ile içeriklerine ulaş.
- **Ayarlar…** penceresinde hesabını (okul adresi, giriş/çıkış), klasörü (**Silinenleri tekrar indir** ile bilgisayarından sildiğin dosyaları geri indirme), **Bilgisayar açılınca başlat** seçeneğini ve güncellemeleri yönet.

Windows’ta uygulamayı Başlat menüsünden tekrar açınca ayarlar penceresi gelir. Bir sorun olursa ayrıntılar `%APPDATA%\blackboard-sync\windows-tray.log` dosyasındadır (Win+R’ye `%APPDATA%\blackboard-sync` yazıp Enter’a bas).

Güncellemeler varsayılan olarak otomatik denetlenir; **Ayarlar…** penceresindeki **Şimdi denetle** ile elle de denetleyebilirsin. Yeni sürüm varsa menüde **Güncelleme var: … — Güncelle** satırı çıkar.

## Gizlilik

Şifreni yalnızca okulunun giriş sayfasına yazarsın; uygulama şifreni görmez ve saklamaz. Oturumun sadece bu bilgisayarda saklanır.

Lisans: [MIT](LICENSE). Geliştirme ve komut satırı kullanımı: [geliştirici rehberi](docs/DEVELOPMENT.md).
