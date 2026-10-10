<p align="center"><img src="assets/banner.png" alt="Blackboard Sync" width="100%"></p>

Blackboard’daki ders içeriklerini otomatik olarak bilgisayarına indirir.

🌐 **Web sitesi:** [blackboard-sync.umutyalcin.workers.dev](https://blackboard-sync.umutyalcin.workers.dev)

## Özellikler

- **Otomatik indirme:** Arka planda her saat kontrol eder, yeni bir şey geldiğinde bildirim gösterir.
- **Düzenli klasörler:** Dosyalar Blackboard’daki dönem ve ders yapısıyla **University** klasörüne kaydedilir.
- **Silinenler sekmesi:** Yanlışlıkla sildiğin dosyaları seçip geri indirebilirsin.
- **Eski dönem indirme:** Geçmiş bir dönemin dosyalarını tek seferde indirebilirsin.
- **Tek tıkla güncelleme:** Yeni sürüm çıkınca bildirim gelir, **Güncelle**’ye basman yeter.
- **Kolay kaldırma:** Ayarlar’dan uygulamayı ve verilerini tek düğmeyle kaldırabilirsin.

## Kurulum

[Son sürümü indir](https://github.com/UmutYLCN/blackboard-sync/releases/latest):

- **macOS:** `.dmg` dosyasını aç, uygulamayı **Applications** klasörüne sürükle.
- **Windows:** `Setup.exe` dosyasını çalıştır. SmartScreen uyarısı çıkarsa **Ek bilgi → Yine de çalıştır**.

Ya da terminalden tek komutla:

```sh
# macOS
curl -fsSL https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.ps1 | iex
```

İlk açılışta okul adresini ve kayıt klasörünü seç, ardından **Giriş yap**. Ayrıntılar ve terminal komutları için [Kullanım kılavuzu](docs/KULLANIM.md).

## Gizlilik

Şifreni yalnızca okulunun kendi giriş sayfasına yazarsın; uygulama şifreni görmez ve hiçbir yere kaydetmez. Giriş oturumu yalnızca kendi bilgisayarında tutulur ve hiçbir sunucuya gönderilmez.

---

Lisans: [MIT](LICENSE).

Blackboard Sync bağımsız bir projedir; Anthology Inc. ile bağlantılı değildir ve onların onayını taşımaz.
