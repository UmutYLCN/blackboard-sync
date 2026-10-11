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
Blackboard’daki ders dosyalarını, duyuruları ve notları arka planda kendiliğinden bilgisayarına indirir; dönem ve ders klasörleriyle düzenli tutar. Ücretsiz ve açık kaynaklı.
```

## Description

Limit 10,000, plain text, no URLs (Microsoft asks for links in their own fields). 2,490 characters.

```text
Blackboard’daki ders içeriklerini otomatik olarak bilgisayarına indirir. Her seferinde siteye girip dosyaları tek tek indirmen gerekmez.

blackboard-sync bağımsız bir projedir; Anthology Inc. veya Blackboard ile bağlantılı değildir, onlar tarafından onaylanmamış veya desteklenmemektedir. “Blackboard”, sahibinin ticari markasıdır.

NASIL ÇALIŞIR
1. Okulunun Blackboard adresini yaz ve dosyaların kaydedileceği klasörü seç.
2. Okulunun kendi giriş sayfasında giriş yap. Girişten sonra ilk senkron başlar.
3. Dosyaların kendiliğinden güncellensin: uygulama varsayılan olarak her saat Blackboard’u kontrol eder.

NELER İNER
• Derslerindeki dosyalar ve ödev yönergelerindeki ekler.
• Duyurular, bağlantılar ve sayfalar, okunabilir Markdown notları olarak.
• Blackboard’da güncellenen dosyalar ve notlar da yenilenir; yeni bir şey inince Windows bildirimi gelir.

DÜZENLİ KLASÖRLER
Dosyalar seçtiğin klasörün içindeki University klasörüne, Blackboard’daki dönem ve ders yapısıyla kaydedilir. Varsayılan konum Belgeler\University’dir. Klasörü sonradan değiştirirsen indirilmiş dosyaları yeni klasöre taşıyabilir, yeniden indirebilir ya da yalnızca yeni dosyaları alabilirsin.

GENEL BAKIŞ
Ana pencerede son indirilen dosyaları görür, tek tıkla açarsın. “Şimdi senkronize et” ile istediğin an kontrol edebilir, “Klasörü aç” ile University klasörüne gidebilirsin. Pencereyi kapatınca uygulama saatin yanındaki simgeyle çalışmaya devam eder.

SİLİNENLER
Daha önce indirip klasörden sildiğin dosyaları seçip yeniden indirebilirsin. Listeden kaldırdığın dosyalar bir daha önerilmez.

ESKİ DÖNEMLER
Geçmiş bir dönemin dosyalarını tek seferde indirebilirsin. Eski dönem bir kez indirilir, güncellenmez.

AYARLAR
• Otomatik senkron: her 30 dakikada, her saat, her 3 saatte ya da yalnızca elle.
• Bilgisayar açılınca başlat: açılışta pencere açmadan arka planda başlar. Windows Görev Yöneticisi’ndeki Başlangıç uygulamaları bölümünden de kapatılabilir.
• Güncellemeler Microsoft Store üzerinden yüklenir.

GİZLİLİK
• Şifreni yalnızca okulunun kendi giriş sayfasına yazarsın; uygulama şifreni görmez ve kaydetmez.
• Giriş oturumu, ayarlar ve indirme kayıtları yalnızca kendi bilgisayarında tutulur.
• Uygulama yalnızca okulunun Blackboard adresine (ve onun yönlendirdiği giriş ve dosya adreslerine) bağlanır.
• Analiz, reklam veya kullanım takibi yoktur; hesap açman gerekmez.

GEREKSİNİMLER
• Okulunun Blackboard Learn hesabı.
• Uygulamanın arayüzü Türkçedir.

Ücretsiz ve açık kaynaklıdır (MIT Lisansı).
```

## What's new in this version

Limit 1,500. Microsoft: "If this is the first time you're submitting your app, leave this
field blank." Leave it empty for the first submission; use this from the first update on,
edited to that release:

```text
İlk Microsoft Store sürümü. Güncellemeler artık Microsoft Store üzerinden yüklenir; uygulamayı Windows Ayarlar → Uygulamalar bölümünden kaldırabilirsin.
```

## Product features

Up to 20, 200 characters each, no bullets (the Store adds them).

```text
Yeni ders dosyalarını arka planda kendiliğinden indirir
Ödev yönergelerindeki ekleri de indirir
Duyuruları, bağlantıları ve sayfaları Markdown notu olarak kaydeder
Dönem ve ders klasörleriyle düzenli University klasörü
Yeni dosya inince Windows bildirimi
Otomatik senkron: her 30 dakikada, her saat, her 3 saatte ya da yalnızca elle
Silinenler: klasörden sildiğin dosyaları seçip geri indir
Eski dönemlerin dosyalarını tek seferde indir
Bilgisayar açılınca arka planda başlayabilir
Şifreni görmez; oturumun yalnızca kendi bilgisayarında kalır
Analiz, reklam ve kullanım takibi yok
Ücretsiz ve açık kaynaklı
```

## Screenshot captions

200 characters each, one per screenshot, in this order. The same text lives in
`screenshots/src/shots.js`.

| Image | Caption |
| --- | --- |
| `01-genel-bakis.png` | Genel bakış: Blackboard'daki yeni ders dosyaları arka planda kendiliğinden iner; son indirilenler tek listede. |
| `02-ayarlar.png` | Genel: okul adresi, kayıt klasörü, otomatik senkron (30 dakikada, saatte, 3 saatte bir ya da yalnızca elle) ve bilgisayar açılınca başlatma. |
| `03-silinenler.png` | Silinenler: klasörden sildiğin indirilmiş dosyaları seçip yeniden indirebilir ya da listeden kaldırabilirsin. |
| `04-eski-donemler.png` | Eski dönemler: geçmiş bir dönemin dosyalarını tek seferde indir. Eski dönem bir kez indirilir, güncellenmez. |
| `05-klasorler.png` | Dosyalar seçtiğin klasördeki University klasörüne, Blackboard'daki dönem ve ders yapısıyla kaydedilir. |

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

Limit 200. 131 characters.

```text
© 2026 Umut Yalçın. MIT Lisansı. Anthology Inc. veya Blackboard ile bağlantılı değildir. “Blackboard”, sahibinin ticari markasıdır.
```

## Additional license terms

Optional. Leave empty: the app is MIT-licensed and the Store's standard license applies.
(If the maintainer wants the MIT text here, paste `LICENSE` as is.)

## Developed by

Optional, 255 characters.

```text
Umut Yalçın
```
