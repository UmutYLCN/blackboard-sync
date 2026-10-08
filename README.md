<p align="center"><img src="assets/banner.png" alt="Blackboard Sync" width="100%"></p>

Yeni ders içeriklerini otomatik indirip Blackboard’daki klasör yapısıyla bilgisayarına kaydeder. Arka planda her saat kontrol eder, yeni bir şey geldiğinde bildirim gösterir.

## Ekran görüntüleri

<!-- Görseller ve video buraya eklenecek -->

## Kurulum

[Son sürümü indir](https://github.com/UmutYLCN/blackboard-sync/releases/latest):

- **macOS:** `.dmg` dosyasını aç, uygulamayı **Applications** klasörüne sürükle. İlk açılışta sağ tık → **Aç**.
- **Windows:** `Setup.exe` dosyasını çalıştır. SmartScreen uyarısı çıkarsa **Ek bilgi → Yine de çalıştır**.

### Terminalden tek komutla

macOS:

```sh
curl -fsSL https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.ps1 | iex
```

İlk açılışta okul adresini ve kayıt klasörünü seç, ardından **Giriş yap**.

## Kayıt klasörü

Dosyalar seçtiğin klasörün içindeki **University** klasörüne, dönem ve ders klasörleri
hâlinde kaydedilir; University klasörünü uygulama kendisi açar. Örneğin iCloud Drive'ı
seçersen dosyalar `iCloud Drive/University/2026-2027 Güz/…` altına iner. Seçtiğin
klasörün adı zaten University ise (varsayılan `Belgeler/University` gibi) içine ikinci bir
University klasörü açılmaz.

Önceki sürümler dönem klasörlerini doğrudan seçilen klasöre koyuyordu
(`iCloud Drive/2026-2027 Güz/…`). Güncellemeden sonraki ilk açılışta veya ilk
senkronizasyonda bu dosyalar bir kez University klasörüne taşınır; yeniden indirilmez.
Taşınamayan bir dosya (başka bir programda açık, ya da University klasöründe aynı adda
farklı bir dosya var) olduğu yerde kalır ve bildirimle haber verilir.

Ayarlar'da klasörü değiştirirsen **Taşı**, **Yeniden indir** ve **Sadece yeni dosyalar**
seçenekleri eski ve yeni klasörlerin University klasörleri arasında çalışır.

## Güncelleme

Yeni sürüm çıkınca bildirim gelir; menüden veya Ayarlar'dan **Güncelle**'ye bas.

- **macOS:** Uygulama yeni sürümü arka planda indirir, imzasını ve Apple onayını
  (notarization) doğrular, eskisinin yerine koyar ve kendini yeniden açar; Finder penceresi
  veya sürükleme gerekmez. Doğrulama başarısız olursa mevcut sürüm korunur. Uygulama
  disk görüntüsünden, yazılamayan bir klasörden çalışıyorsa ya da imzasız eski bir sürümse
  `.dmg` açılır ve uygulamayı **Applications** klasörüne elle sürüklersin.
- **Windows:** Kurulum programı sessizce çalışır ve uygulamayı yeniden başlatır.

Senkronizasyon veya klasör taşıma sürerken güncelleme başlamaz; bittikten sonra tekrar dene.
Ayarların ve indirdiğin ders dosyaları korunur.

## Eski dönem indirme

**Ayarlar…** penceresinin **Genel** sekmesindeki **Eski dönemler** bölümünde listeden
bir dönem seç ve **Eski dönemi indir**'e bas. Liste giriş yapmışken pencere açılınca
yüklenir; güncel dönem listede görünmez. Dosyalar mevcut
kayıt klasöründeki dönem/ders klasörlerine indirilir. Eski dönem bir kez indirilir,
otomatik güncellenmez; tekrar indirmek yalnızca eksik dosyaları tamamlar. Normal
senkron güncel dönemi takip etmeye devam eder.

Terminalden: `blackboard-sync sync --term "2025-2026 - Spring"` (Blackboard'daki
dönem adını kullan). Kullanılabilir adları `blackboard-sync past-terms` ile listele.

## Kaldırma

**Ayarlar…** penceresinin **Güncellemeler** bölümündeki **Uygulamayı kaldır…** düğmesine bas.
Uygulama kayıtları, günlükler, ayarlar, giriş verileri ve açılışta başlatma kaydı silinir.
İndirilmiş ders dosyaları varsayılan olarak korunur. **İndirilmiş ders dosyalarını da sil**
seçeneği yalnızca uygulamanın kayıtlı dosyalarını ve boşalan klasörlerini (boşaldıysa
uygulamanın açtığı University klasörü dahil) Çöp Sepeti’ne / Geri Dönüşüm Kutusu’na taşır;
diğer dosyalar ve seçtiğin kayıt klasörü korunur.
Senkronizasyon veya klasör taşıma sürerken kaldırma yapılamaz.

Terminalden (önce menüden uygulamadan çık):

```sh
blackboard-sync uninstall
# Kayıtlı ders dosyalarını da Çöp Sepeti’ne taşımak için:
blackboard-sync uninstall --delete-course-files
```

Paketli Windows kurulumunda terminal komutu uygulama klasöründeki
`blackboard-sync-cli.exe uninstall` şeklindedir. macOS paketinde
`"/Applications/Blackboard Sync.app/Contents/MacOS/Blackboard Sync" uninstall` kullanılır.
Kaynak koddan kurulumda bu komut verileri temizler; kaynak klasörünü ve sanal ortamı elle kaldır.
Uygulamayı yalnızca Finder’da Çöp Sepeti’ne sürüklemek uygulama verilerini temizlemez.

## Gizlilik

Şifreni yalnızca okulunun kendi giriş sayfasına yazarsın; uygulama şifreni görmez ve hiçbir yere kaydetmez. Saatlik senkron için gereken giriş oturumu yalnızca kendi bilgisayarında tutulur ve hiçbir sunucuya gönderilmez.

Lisans: [MIT](LICENSE).

Blackboard Sync bağımsız bir projedir; Anthology Inc. ile bağlantılı değildir ve onların onayını taşımaz.
