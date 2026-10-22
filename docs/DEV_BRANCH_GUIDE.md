# Blackboard Sync - dev branch'inde geliştirme kuralları

Repo: https://github.com/UmutYLCN/blackboard-sync

1. Çalışma branch'i `dev`. `main`'e doğrudan gönderim yapma ve `main`'e PR açma.
2. Başlamadan önce güncel dev'i çek:
   ```sh
   git checkout dev && git pull origin dev
   ```
3. Her iş için dev'den ayrı bir branch aç:
   ```sh
   git checkout -b feat/kisa-aciklama
   ```
   Hata düzeltmesi için `fix/...` kullan.
4. Küçük ve tek konulu tut: bir PR bir işi yapsın; başkasının üzerinde çalıştığı dosyaları gereksiz yere değiştirme.
5. Bitince branch'i GitHub'a gönder ve PR aç. PR'ın hedefi (base) mutlaka `dev` olsun. Açıklamaya ne değiştirdiğini ve nasıl denediğini kısaca yaz.
6. PR'ı kendin birleştirme; birleştirmeyi sadece proje sahibi yapar.
7. Çakışma çıkarsa kendi branch'ine dev'i al:
   ```sh
   git fetch origin && git merge origin/dev
   ```
   Çakışmaları çöz, tekrar gönder.
8. Gizli bilgi (şifre, anahtar, çerez, kişisel dosya) asla commit etme.

**Yapay zekâ kodlama araçlarına not:** “Sadece dev'den branch aç, PR'ı dev'e aç, main'e dokunma, kendi başına birleştirme.”
