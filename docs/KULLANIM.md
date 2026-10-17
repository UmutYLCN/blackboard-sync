# Kullanım kılavuzu

Kurulum için [README](../README.md)'ye bak. Bu sayfa uygulamanın ayrıntılı kullanımını anlatır.

## Ana pencere

Blackboard Sync'i **Applications** veya **Launchpad**'den (Windows'ta **Başlat** menüsünden)
açınca ana pencere açılır; uygulama zaten çalışıyorsa aynı pencere öne gelir. Pencere Google
Drive'ın masaüstü uygulaması gibi düzenlenmiştir. Solda üstte **Klasörü aç** düğmesi, altında
bölümler durur: ilk girişe kadar **Başlangıç**, sonra **Home**, **Sync activity**, **Announcements**,
**Dersler** ve **Takvim**. Sağ üstte üç yuvarlak düğme vardır: **Duraklat / Devam et**,
**Ayarlar** (dişli) ve hesabın (baş harfler; tıklayınca hesap menüsü). Menüdeki **Ayarlar…** aynı
pencereyi **Ayarlar** sayfasında açar.

- **Home** özet bir sayfadır: senkronun durumu (**Güncel**, **Senkronize ediliyor…**, **Duraklatıldı**,
  **Giriş gerekli**; senkron sürerken bulut → klasör animasyonu), son indirilenler,
  dikkat gerektirenler ile en yeni duyurular ve yaklaşan teslim tarihleri.
- **Sync activity** senkronun getirdiği her dosyayı, notu ve duyuruyu yeniden eskiye doğru boyutu
  ve durumuyla listeler; satıra tıklayınca dosya kendi uygulamasında açılır.
- **Announcements** (duyurular) en üstte dikkat gerektirenleri (oturum sona erdi, güncelleme,
  tamamlanamayan senkron, uyarılar), altında derslerin tüm duyurularını gösterir.

**Duraklat** düğmesi çalışan senkronu hemen durdurur ve siz **Devam et**'e basana kadar
otomatik senkron yapılmaz; durum yeniden başlatmada da korunur. Devam edince bir senkron hemen
başlar. Menü çubuğu menüsünde de **Senkronu duraklat / sürdür** vardır.

Pencereyi kapatınca uygulama kapanmaz: menü çubuğundaki (Windows'ta saatin yanındaki)
simgeyle çalışmaya ve senkronize etmeye devam eder. Bilgisayar açılınca kendiliğinden
başlayan uygulama pencere açmaz. Tamamen kapatmak için simgenin menüsünden **Çık**'ı seç.

## Takvim

**Takvim**, senkronize edilen derslerin ödev, sınav ve diğer notlandırılan
çalışmalarını son teslim tarihine göre gün gün gösterir. Yaklaşan tarihler en
yakından başlar; tarihi geçenler ayrı görünür. Saatler bilgisayarının yerel
saatidir. Bir çalışmaya tıklayınca indirilmiş notu varsa açılır; yoksa
Blackboard açılır. İçerik bağlantısı olmayan not sütunlarında dersin notlar
sayfası açılır.

**Hatırlatma:** bir çalışmanın son teslim tarihine 24 saat ve 1 saat kala
bildirim gelir (her biri bir kez). Bilgisayar o sırada kapalıysa açıldığında
yalnızca en yakın hatırlatma gösterilir. Dersler'de işaretini kaldırdığın
derslerden hatırlatma gelmez.

Tarihler senkron sırasında güncellenir; bu sayfayı açmak internet isteği
göndermez. Okul bir dersin not sütunlarına erişimi kapatırsa önceki kayıtlar
korunur ve sayfada güncellenemeyen dersler olduğu belirtilir. Yalnızca
Blackboard'un açıkça bildirdiği son teslim tarihleri gösterilir. Teslim durumu
kontrol edilmediği için tamamladığın çalışmalar da tarihi geçenler arasında
görünebilir.

## Kayıt klasörü

Dosyalar seçtiğin klasörün içindeki **University** klasörüne, dönem ve ders klasörleri
hâlinde kaydedilir; University klasörünü uygulama kendisi açar. Örneğin iCloud Drive'ı
seçersen dosyalar `iCloud Drive/University/2026-2027 Güz/…` altına iner. Seçtiğin
klasörün adı zaten University ise (varsayılan `Belgeler/University` gibi) içine ikinci bir
University klasörü açılmaz.

Video ve ses kayıtları indirilmez; notlarında Blackboard bağlantısı görünür. 500 MB'tan
büyük diğer dosyalar da indirilmez. Notta dosyanın boyutu ve Blackboard'da açma bağlantısı
yer alır; senkron özeti bu şekilde atlanan dosyaların sayısını gösterir. Blackboard'da
dosya değişirse sonraki senkron yeni sürümü yeniden değerlendirir.

Önceki sürümler dönem klasörlerini doğrudan seçilen klasöre koyuyordu
(`iCloud Drive/2026-2027 Güz/…`). Güncellemeden sonraki ilk açılışta veya ilk
senkronizasyonda bu dosyalar bir kez University klasörüne taşınır; yeniden indirilmez.
Taşınamayan bir dosya (başka bir programda açık, ya da University klasöründe aynı adda
farklı bir dosya var) olduğu yerde kalır ve bildirimle haber verilir.

University klasörü Blackboard'un bir kopyasıdır: bir dosyayı silersen ya da dosya bozulursa
(boş kalırsa, yarım inerse) bir sonraki senkronda yeniden indirilir. Kendi düzenin için
dosyaları başka bir klasöre kopyala. Senin değiştirdiğin bir dosyanın (örneğin üzerine not
aldığın bir PDF) üzerine hiçbir zaman yazılmaz; Blackboard'da yeni sürümü çıkarsa yanına
`ad (2).pdf` olarak iner.

Ayarlar'da klasörü değiştirirsen **Taşı** dosyaları yeni klasöre taşır, **Yeniden indir**
ise eski klasöre dokunmadan dosyaları yeni klasöre yeniden indirir.

## Dersler

Ana pencerenin **Dersler** bölümü güncel dönemdeki derslerini birer onay kutusuyla
listeler. İşaretli dersler senkronize edilir; yeni bir ders çıkınca o da kendiliğinden
işaretli gelir. İstemediğin bir dersin işaretini kaldır: o ders artık hiç senkronize
edilmez (Blackboard'a o ders için istek gönderilmez), **Takvim**, **Announcements** ve son
indirilenler listesinde görünmez. Daha önce indirilmiş dosyaları silinmez. Tekrar
işaretlersen eksik dosyaları hemen başlayan senkronda iner.

Liste ilk senkrondan sonra dolar. Eski dönemler bu listede yer almaz; onları
**Ayarlar** sayfasındaki **Eski dönemler** kısmından ayrıca indirirsin.

## Duyurular

Ana pencerenin **Announcements** (duyurular) bölümü, güncel dönem derslerinden senkronize edilen tüm
duyuruları en yeniden başlayarak listeler. Her kartta ders adı, başlık, tarih ve kısa
bir önizleme bulunur. Kartı seçince kayıtlı not açılır; not bilgisayarda yoksa
Blackboard'daki dersin duyurular sayfası açılır.

Liste yerel senkron verilerinden açılır; bu bölüme geçmek Blackboard'a yeni bir
istek göndermez. Önceki sürümden güncellediysen duyurular sonraki senkronun ardından
listelenir. Eski dönem arşivlerinin duyuruları bu listede görünmez.

## Güncelleme

Yeni sürüm çıkınca bildirim gelir; ana pencerenin **Başlangıç / Home** sayfasında
yeni sürümü gösteren bir kart çıkar. **Son indirilenler** listesinin üstündeki
**Güncelle** düğmesine bas; menüden veya **Ayarlar** sayfasından da güncelleyebilirsin.
Microsoft Store sürümünde bu kart gösterilmez; güncellemeleri Store yükler.

- **macOS:** Uygulama yeni sürümü arka planda indirir, imzasını ve Apple onayını
  (notarization) doğrular, eskisinin yerine koyar ve kendini yeniden açar; Finder penceresi
  veya sürükleme gerekmez. Doğrulama başarısız olursa mevcut sürüm korunur. Uygulama
  disk görüntüsünden, yazılamayan bir klasörden çalışıyorsa ya da imzasız eski bir sürümse
  `.dmg` açılır ve uygulamayı **Applications** klasörüne elle sürüklersin.
- **Windows:** Kurulum programı sessizce çalışır ve uygulamayı yeniden başlatır.

Senkronizasyon veya klasör taşıma sürerken güncelleme başlamaz; bittikten sonra tekrar dene.
Ayarların ve indirdiğin ders dosyaları korunur.

## Eski dönem indirme

Ana pencerenin **Ayarlar** sayfasındaki **Eski dönemler** kısmında listeden
bir dönem seç ve **Eski dönemi indir**'e bas. Liste giriş yapmışken **Ayarlar** sayfası açılınca
yüklenir; güncel dönem listede görünmez. Dosyalar mevcut
kayıt klasöründeki dönem/ders klasörlerine indirilir: her dönemin kendi klasörü
güncel dönemin klasörünün yanında açılır (ör. `2026-2027 Güz` ile `2025-2026 Bahar`
yan yana). Blackboard aynı dönemi hem Türkçe hem İngilizce adla gösterse de
(`2025-2026 Bahar` / `2025-2026 Spring`) tek dönem ve tek klasör olur; aynı ders iki
kez listelense de bir kez indirilir. Eski dönem bir kez indirilir,
otomatik güncellenmez; tekrar indirmek yalnızca eksik dosyaları tamamlar. Bir dersin
içeriği okunamazsa (ör. erişim kapalı) bu bildirilir ve tekrar denemek eksikleri
tamamlar. Normal senkron güncel dönemi takip etmeye devam eder.

Terminalden: `blackboard-sync sync --term "2025-2026 Bahar"` (Türkçe ya da İngilizce
dönem adı olur) veya `blackboard-sync sync --term-id <kimlik>`. Kullanılabilir
dönemleri ve kimliklerini `blackboard-sync past-terms` ile listele.

## Kaldırma

Ana pencerenin **Ayarlar** sayfasındaki **Güncellemeler** kısmında **Uygulamayı kaldır…** düğmesine bas.
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
