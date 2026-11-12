# Store listing: Turkish (tr-TR)

The primary listing. The package declares `tr-TR` (`packaging/msix/AppxManifest.xml.in`),
so Partner Center offers this language once the package is uploaded. Paste each
block into the Partner Center field with the same name. Limits are those in
Microsoft's [Store listing docs](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/add-and-edit-store-listing-info)
and the [submission checklist](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/create-app-submission#store-listings-page);
the character counts below were measured.

## Product name

`blackboard-sync` (the reserved name; Partner Center selects it from the package).

## Short description

Limit 1,000; only the first 270 are shown in some views. 174 characters.

```text
Blackboard’daki ders dosyalarını, duyuruları ve notları arka planda kendiliğinden bilgisayarına indirir; dönem ve ders klasörleriyle düzenli tutar. Ücretsizdir, kaynak kodu GitHub’da herkese açıktır.
```

## Description

Limit 10,000, plain text, no URLs (Microsoft asks for links in their own fields).

```text
Blackboard’daki ders içeriklerini otomatik olarak bilgisayarına indirir. Her seferinde siteye girip dosyaları tek tek indirmen gerekmez.

blackboard-sync bağımsız bir projedir; Anthology Inc. veya Blackboard ile bağlantılı değildir. “Blackboard” markası bu uygulamaya değil, kendi sahibine aittir.

NASIL ÇALIŞIR
1. Okulunun Blackboard adresini yaz ve dosyaların kaydedileceği klasörü seç.
2. Okulunun kendi giriş sayfasında giriş yap. Girişten sonra ilk senkron başlar.
3. Dosyaların kendiliğinden güncellensin: uygulama varsayılan olarak her saat Blackboard’u kontrol eder.

NELER İNER
• Derslerindeki dosyalar ve ödev yönergelerindeki ekler.
• Duyurular, bağlantılar ve sayfalar, okunabilir Markdown notları olarak.
• Blackboard’da güncellenen dosyalar ve notlar da yenilenir; yeni bir şey inince Windows bildirimi gelir.

DÜZENLİ KLASÖRLER
Dosyalar seçtiğin klasörün içindeki University klasörüne, Blackboard’daki dönem ve ders yapısıyla, okulunun kendi dönem adlarıyla kaydedilir. Uygulama güncel dönemini senkronize eder; ders klasörü ilk dosya yazıldığında açılır. Güncel dönemin belli olmadığı yeni bir okulda uygulama, hiçbir şey indirmeden önce bulduğu dersleri gösterir ve onaylamanı ister. Varsayılan konum Belgeler\University’dir. Klasörü sonradan değiştirirsen indirilmiş dosyaları yeni klasöre taşıyabilir, yeniden indirebilir ya da yalnızca yeni dosyaları alabilirsin.

GENEL BAKIŞ
Ana pencerede son indirilen dosyaları görür, tek tıkla açarsın. “Şimdi senkronize et” ile istediğin an kontrol edebilir, “Klasörü aç” ile University klasörüne gidebilirsin. Pencereyi kapatınca uygulama saatin yanındaki simgeyle çalışmaya devam eder.

TAKVİM VE DUYURULAR
Yaklaşan ödev teslim tarihlerini ve ders duyurularını uygulamada görürsün. Ayarlar’dan isteğe bağlı Google Takvim bağlantısını açarak teslim tarihlerini ayrı bir Blackboard Deadlines takviminde güncel tutabilirsin. Diğer takvimlerin gizli kalır.

NOTEBOOKLM
İsteğe bağlı olarak Ana sayfadaki karttan NotebookLM’i bağlayabilirsin. Her senkrondan sonra indirilen ders dosyaların ve PDF notların her ders için ayrı bir notebook’a eklenir; kaynaklarınla doğrudan çalışır, özet çıkarır veya soru sorabilirsin. “NotebookLM’e ekle” dosyaları istediğin an ekler, “NotebookLM’i aç” notebook’larını açar. Notebook’ta zaten bulunan dosya bir daha eklenmez; Ayarlar’daki “Kopyaları bul” fazla kopyaları listeler. NotebookLM’e Google’ın resmî olmayan bir bağlantısıyla ulaşılır; Google NotebookLM’de değişiklik yaparsa çalışmayabilir. Google oturumun bilgisayarında kalır, Ayarlar’daki “Bağlantıyı kes” onu siler ve ders dosyaların kendi Google hesabına gider.

OTURUM AÇIK KALIR
Uygulama çalışırken Blackboard oturumunu canlı tutar; oturum dolunca okulunun tek oturum açma sayfası üzerinden sessizce yeniden giriş yapar. Okulun şifre ya da iki adımlı doğrulama kodu isterse hiçbir şey doldurulmaz ve her zamanki Giriş yap bildirimi gelir. Ayarlar’dan kapatılabilir.

SİLİNENLER
Daha önce indirip klasörden sildiğin dosyaları seçip yeniden indirebilirsin. Listeden kaldırdığın dosyalar bir daha önerilmez.

AYARLAR
• Otomatik senkron: her 30 dakikada, her saat, her 3 saatte ya da yalnızca elle.
• Bilgisayar açılınca başlat: açılışta pencere açmadan arka planda başlar. Windows Görev Yöneticisi’ndeki Başlangıç uygulamaları bölümünden de kapatılabilir.
• Güncellemeler Microsoft Store üzerinden yüklenir.
• Açık, koyu veya sistem teması; Türkçe ve İngilizce arayüz seçenekleri.

GİZLİLİK
• Şifreni yalnızca okulunun kendi giriş sayfasına yazarsın; uygulama şifreni görmez ve kaydetmez.
• Giriş oturumu, ayarlar ve indirme kayıtları yalnızca kendi bilgisayarında tutulur.
• Uygulama okulunun Blackboard adresine ve yönlendirdiği giriş/dosya adreslerine bağlanır. İsteğe bağlı Google Takvim bağlantısını Ayarlar’dan açarsan, ayrı Blackboard Deadlines takvimini yönetmek için Google’a da bağlanır; ana takvimine erişmez. İsteğe bağlı NotebookLM bağlantısını açarsan ders dosyaların kendi Google hesabındaki NotebookLM’e gönderilir.
• Analiz, reklam veya kullanım takibi yoktur; hesap açman gerekmez.

GEREKSİNİMLER
• Okulunun Blackboard Learn hesabı.
• Türkçe ve İngilizce arayüz seçenekleri.

Ücretsizdir. Kaynak kodu GitHub’da herkese açıktır (tüm hakları saklıdır).
```

## What's new in this version

Limit 1,500. Update from the published Store version 1.5.1 to 1.7.1 (1.6.2 added the redesigned interface, themes, due dates, announcements and Google Calendar):

```text
1.7 ile NotebookLM geliyor: Ana sayfadaki yeni karttan bağla; her senkrondan sonra ders dosyaların her ders için ayrı bir notebook’a eklenir, aynı dosya iki kez eklenmez. Blackboard oturumun dolunca uygulama sessizce yeniden giriş yapar. Artık güncel dönemini senkronize eder, okulunun kendi dönem adlarını korur ve yeni bir okulda ilk indirmeden önce derslerini onaylamanı ister. Okul listesi yaklaşık 143 okula çıktı, boş ders klasörleri artık açılmaz, eski dönemler bölümü kaldırıldı. 1.6’dan gelen yenilenen arayüz, açık/koyu/sistem temaları, teslim tarihleri, duyurular ve Google Takvim de var. Güncellemeler Microsoft Store üzerinden yüklenmeye devam eder.
```

## Product features

Up to 20, 200 characters each, no bullets (the Store adds them).

```text
Yeni ders dosyalarını arka planda kendiliğinden indirir
Ödev yönergelerindeki ekleri de indirir
Duyuruları, bağlantıları ve sayfaları Markdown notu olarak kaydeder
Dönem ve ders klasörleriyle düzenli University klasörü
Yeni dosya inince Windows bildirimi
Yaklaşan teslim tarihleri ve ders duyuruları uygulamada
Ayarlar’dan isteğe bağlı Google Takvim bağlantısı
Açık, koyu ve sistem temaları; Türkçe ve İngilizce arayüz
Otomatik senkron: her 30 dakikada, her saat, her 3 saatte ya da yalnızca elle
Silinenler: klasörden sildiğin dosyaları seçip geri indir
NotebookLM: her senkrondan sonra dosyalar her ders için ayrı notebook’a eklenir
Aynı dosyayı iki kez eklemez; notebook’taki kopyaları bulur
Oturum açık kalır: okulunun tek oturum açma sayfasıyla sessiz yeniden giriş
Güncel dönemi senkronize eder; yeni okulda dersleri onaylatır
Bilgisayar açılınca arka planda başlayabilir
Şifreni görmez; oturumun yalnızca kendi bilgisayarında kalır
Analiz, reklam ve kullanım takibi yok
Ücretsiz, kaynak kodu GitHub’da
```

## Screenshot captions

200 characters each, one per screenshot, in this order. The same text lives in
`screenshots/src/shots.js`. The Turkish listing uses the images in `screenshots/`, the English
listing the English images in `screenshots/en/` (same file names, English titles and app text).

| Image | Caption |
| --- | --- |
| `01-tek-tek.png` | Blackboard’dan dosyaları tek tek mi indiriyorsun? Blackboard Sync, ders dosyalarını arka planda otomatik olarak bilgisayarına indirir. |
| `02-genel-bakis.png` | Ana sayfa: yeni ders dosyaları arka planda kendiliğinden iner. Son indirilenler, duyurular ve yaklaşan teslim tarihleri tek bakışta. |
| `03-teslim-tarihleri.png` | Takvim: yaklaşan teslim tarihleri gün gün listelenir. Teslime 24 saat ve 1 saat kala bildirim gelir. |
| `04-google-takvim.png` | Ayarlar’dan Google Takvim’i bağla: teslim tarihleri ayrı bir Blackboard Deadlines takviminde güncel kalır. Diğer takvimlerin gizli kalır. |
| `05-duyurular.png` | Duyurular: tüm derslerinin Blackboard duyuruları tek listede, en yenisi en üstte. Herhangi birini tek tıkla aç. |
| `06-dersler.png` | Dersler: bu dönemin derslerini gör, istemediğinin işaretini kaldır. İşaretsiz dersler senkronize edilmez; indirilmiş dosyalar silinmez. |
| `07-koyu-tema.png` | Koyu tema: uygulama Windows’un temasını izler ya da Ayarlar’dan açık veya koyu temada kalır. |
| `08-baslangic.png` | Başlangıç: okulunun Blackboard adresini yaz, kayıt klasörünü ve bilgisayar açılınca başlatma seçeneğini belirle, ardından giriş yap. |
| `09-tepsi-menusu.png` | Pencereyi kapatsan da uygulama saatin yanındaki simgeden çalışır. Son senkronu gör, yeni bir senkron başlat veya derslerine ve indirdiklerine ulaş. |
| `10-notebooklm.png` | NotebookLM: İndirilen ders dosyaları her ders için ayrı bir notebook'a otomatik aktarılır. Kaynaklarınla doğrudan çalış, özet çıkar veya soru sor. |

## Trailer title

255 characters at most.

```text
blackboard-sync: Blackboard ders dosyaların, otomatik olarak bilgisayarında
```

## Search terms (Keywords)

Up to 7 terms, 40 characters each, at most 21 unique words in all. 7 terms, 9 unique words.

```text
Blackboard
Blackboard Learn
ders dosyaları
ödev
üniversite
dosya indirme
senkronizasyon
```

## Copyright and trademark info

Limit 200. 192 characters.

```text
© 2026 Umut Yalçın. Tüm hakları saklıdır. blackboard-sync bağımsız bir projedir; Anthology Inc. veya Blackboard ile bağlantılı değildir. “Blackboard” markası bu uygulamaya değil, kendi sahibine aittir.
```

## Additional license terms

Optional. Leave empty: the source is all rights reserved and the Store's standard license applies.

## Developed by

Optional, 255 characters.

```text
Umut Yalçın
```

## İsteğe bağlı Google Takvim gizliliği

Ayarlar’dan bağlandığında Google’a etkinlik başlığı, ders adı, teslim zamanı ve Blackboard bağlantısı gönderilir. Token Windows Kimlik Bilgisi Yöneticisi’nde; eşleme ve durum özel uygulama veri klasöründe saklanır. Ayarlar’dan bağlantıyı kesmek erişimi iptal edip yerel Takvim verilerini siler; isteğe bağlı olarak özel takvimi de silebilirsin. Takvimi korursan yeniden bağlantı için yalnızca gizli olmayan takvim kimliği yerelde tutulur. https://myaccount.google.com/connections üzerinden de erişimi kaldırabilirsin. Google API kullanımı, Limited Use dahil Google API Services User Data Policy’ye uyar.

## İsteğe bağlı NotebookLM gizliliği

Ana sayfadaki NotebookLM kartından bağlandığında, indirilen ders dosyaların ve PDF notların her senkrondan sonra NotebookLM’e eklenir. Google’a Google’ın kendi sayfasında, bir tarayıcı penceresinde giriş yaparsın; uygulama şifreni görmez. Dosyalar kendi Google hesabına gider. Google oturumu ve giriş tarayıcısının verileri bu bilgisayarda kalır; Ayarlar’daki Bağlantıyı kes bunları siler, notebook’ların NotebookLM’de kalır. NotebookLM’e resmî olmayan bir bağlantıyla ulaşılır; Google NotebookLM’de değişiklik yaparsa çalışmayabilir.
