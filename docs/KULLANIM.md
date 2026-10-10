# Kullanım kılavuzu

Kurulum için [README](../README.md)'ye bak. Bu sayfa uygulamanın ayrıntılı kullanımını anlatır.

## Ana pencere

Blackboard Sync'i **Applications** veya **Launchpad**'den (Windows'ta **Başlat** menüsünden)
açınca ana pencere açılır; uygulama zaten çalışıyorsa aynı pencere öne gelir. Soldaki
bölümler: ilk girişe kadar **Başlangıç**, sonra **Genel bakış** (hesap, son senkron,
**Şimdi senkronize et**, **Klasörü aç**, son indirilenler), **Genel** (ayarlar) ve
**Silinenler**. Menüdeki **Ayarlar…** aynı pencereyi **Genel** bölümünde açar.

Pencereyi kapatınca uygulama kapanmaz: menü çubuğundaki (Windows'ta saatin yanındaki)
simgeyle çalışmaya ve senkronize etmeye devam eder. Bilgisayar açılınca kendiliğinden
başlayan uygulama pencere açmaz. Tamamen kapatmak için simgenin menüsünden **Çık**'ı seç.

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

## Silinenler

Ana pencerenin **Silinenler** bölümü, kayıt klasöründen silinmiş indirilmiş
dosyaları listeler. Geri istediklerini seçip **Seçilenleri indir**'e bas; **Listeden kaldır**
ile kaldırdığın dosyalar bir daha önerilmez.

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

Ana pencerenin **Genel** bölümündeki **Eski dönemler** kısmında listeden
bir dönem seç ve **Eski dönemi indir**'e bas. Liste giriş yapmışken **Genel** bölümü açılınca
yüklenir; güncel dönem listede görünmez. Dosyalar mevcut
kayıt klasöründeki dönem/ders klasörlerine indirilir. Eski dönem bir kez indirilir,
otomatik güncellenmez; tekrar indirmek yalnızca eksik dosyaları tamamlar. Normal
senkron güncel dönemi takip etmeye devam eder.

Terminalden: `blackboard-sync sync --term "2025-2026 - Spring"` (Blackboard'daki
dönem adını kullan). Kullanılabilir adları `blackboard-sync past-terms` ile listele.

## Kaldırma

Ana pencerenin **Genel** bölümündeki **Güncellemeler** kısmında **Uygulamayı kaldır…** düğmesine bas.
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
