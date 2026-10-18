"""Turkish for every text the app shows: English text -> Turkish text.

The keys are the exact strings passed to ``i18n.tr`` / ``ntr`` in the code;
``tests/test_i18n.py`` checks that each one is here with the same ``{fields}``.
Turkish keeps the noun singular after a number, so "1 file" and "2 files" are
both "dosya".
"""

CATALOG = {
    # Announcements
    "Announcements": "Duyurular",
    "Every announcement synced from your current-term courses.":
        "Güncel dönem derslerinizden senkronize edilen tüm duyurular.",
    "No announcements yet. They show up here once they are synced.":
        "Henüz duyuru yok. Duyurular senkronize edildiğinde burada görünecek.",
    "No date given": "Tarih belirtilmemiş",
    "Open announcement": "Duyuruyu aç",
    "Announcement": "Duyuru",

    # Blackboard and the command line
    "Your Blackboard session has expired.": "Blackboard oturumunuzun süresi doldu.",
    "Blackboard redirected to a sign-in page.": "Blackboard bir giriş sayfasına yönlendirdi.",
    "Blackboard answered with a web page instead of data.": "Blackboard veri yerine bir web sayfası döndürdü.",
    "Blackboard answered a download with a web page.": "Blackboard bir indirmeye web sayfasıyla yanıt verdi.",
    "Next: run `blackboard-sync sync` to download your courses.":
        "Sıradaki adım: derslerinizi indirmek için `blackboard-sync sync` çalıştırın.",
    "Blackboard Sync's app data was removed.": "Blackboard Sync uygulama verileri kaldırıldı.",
    "Session OK: signed in as {name}.": "Oturum geçerli: {name} olarak giriş yapıldı.",
    "Term(s): {terms}": "Dönem(ler): {terms}",
    "No past terms to download.": "İndirilebilecek eski dönem yok.",
    "none found": "bulunamadı",
    "Network error talking to Blackboard: {error}": "Blackboard ile bağlantıda ağ hatası: {error}",
    "Unexpected error: {error}": "Beklenmeyen hata: {error}",
    "Error: {error}": "Hata: {error}",
    "Run `blackboard-sync login` to sign in to Blackboard.":
        "Blackboard'a giriş yapmak için `blackboard-sync login` çalıştırın.",

    # Courses
    "Courses": "Dersler",
    "This folder is a copy of Blackboard: the files of the ticked courses are matched to Blackboard on every "
    "sync, and deleted or damaged files are downloaded again. To keep files your own way, copy them to another "
    "folder.":
        "Bu klasör Blackboard'un bir kopyasıdır: işaretli derslerin dosyaları her senkronda Blackboard'la "
        "eşitlenir, silinen veya bozulan dosyalar yeniden indirilir. Dosyaları kendi düzeninize göre saklamak "
        "için başka bir klasöre kopyalayın.",
    "A course you untick is no longer synced and does not show in Calendar or Announcements. Its downloaded "
    "files are not deleted. Tick it again and its missing files come right away.":
        "İşaretini kaldırdığınız ders artık senkronize edilmez, Takvim'de ve Duyurular'da görünmez. İndirilmiş "
        "dosyaları silinmez. Yeniden işaretlediğinizde eksik dosyaları hemen gelir.",
    "Your courses are listed here after the first sync.": "Dersleriniz ilk senkrondan sonra burada listelenir.",

    # Calendar
    "Calendar": "Takvim",
    "Due dates are updated during a sync. Times are in this computer's local time.":
        "Son teslim tarihleri senkron sırasında güncellenir. Saatler bu bilgisayarın yerel saatine göredir.",
    "Upcoming": "Yaklaşan teslimler",
    "Past due": "Tarihi geçenler",
    "Submissions are not checked; work you already handed in may show here too.":
        "Teslim durumu kontrol edilmez; tamamladığınız çalışmalar da burada görünebilir.",
    "No due dates saved.": "Kayıtlı son teslim tarihi yok.",
    "Sync to see due dates.": "Tarihleri görmek için senkronize edin.",
    "Some courses' due dates could not be updated. Earlier ones are shown where there are any.":
        "Bazı derslerin tarihleri güncellenemedi. Varsa önceki kayıtlar gösteriliyor.",
    "January": "Ocak",
    "February": "Şubat",
    "March": "Mart",
    "April": "Nisan",
    "May": "Mayıs",
    "June": "Haziran",
    "July": "Temmuz",
    "August": "Ağustos",
    "September": "Eylül",
    "October": "Ekim",
    "November": "Kasım",
    "December": "Aralık",
    "Monday": "Pazartesi",
    "Tuesday": "Salı",
    "Wednesday": "Çarşamba",
    "Thursday": "Perşembe",
    "Friday": "Cuma",
    "Saturday": "Cumartesi",
    "Sunday": "Pazar",
    "Due in 1 hour": "Teslime 1 saat kaldı",
    "Deadline coming up": "Teslim tarihi yaklaşıyor",
    "Today": "Bugün",
    "Tomorrow": "Yarın",
    "{month} {day}": "{day} {month}",
    "{month} {day}, {year}": "{day} {month} {year}",
    "Untitled work": "Adsız çalışma",
    "today {time}": "bugün {time}",
    "tomorrow {time}": "yarın {time}",
    "yesterday {time}": "dün {time}",
    "Due: {time}": "Teslim: {time}",

    # Signing in
    "Blackboard Sync – Sign in": "Blackboard Sync – Giriş",
    "The sign-in window was closed before sign-in finished.": "Giriş penceresi, giriş tamamlanmadan kapatıldı.",
    "The sign-in window needs the Microsoft Edge WebView2 Runtime, which is missing on this computer. Install "
    "it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 or install Google Chrome or Microsoft Edge, then "
    "sign in again.":
        "Giriş penceresi için bu bilgisayarda eksik olan Microsoft Edge WebView2 Runtime gerekiyor. "
        "https://go.microsoft.com/fwlink/p/?LinkId=2124703 adresinden yükleyin ya da Google Chrome veya "
        "Microsoft Edge kurun, sonra tekrar giriş yapın.",
    "Sign-in was not completed within {n} minutes.": "Giriş {n} dakika içinde tamamlanmadı.",
    "The sign-in window is unavailable ({error}); run ./scripts/setup.sh again or install a Chromium-based "
    "browser.":
        "Giriş penceresi kullanılamıyor ({error}); ./scripts/setup.sh'i yeniden çalıştırın ya da Chromium "
        "tabanlı bir tarayıcı kurun.",
    "The sign-in window is unavailable: {error}": "Giriş penceresi kullanılamıyor: {error}",
    "Close Sign-in Window": "Giriş penceresini kapat",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and run "
    "`blackboard-sync login` again.":
        "Tarayıcı açılmadı. Önceki denemeden kalan bir giriş penceresi açıksa kapatıp `blackboard-sync login` "
        "komutunu yeniden çalıştırın.",
    "Sign in to Blackboard in that window. It closes by itself once you are in.":
        "Açılan pencerede Blackboard'a giriş yapın. Giriş yapınca pencere kendiliğinden kapanır.",
    "Could not find a supported browser (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, Opera GX, "
    "Chromium or Arc) on this computer.":
        "Bu bilgisayarda desteklenen bir tarayıcı (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, "
        "Opera GX, Chromium veya Arc) bulunamadı.",
    "Could not find {browser} on this computer.": "Bu bilgisayarda {browser} bulunamadı.",
    "Signed in as {name}; session saved ({n} cookies).": "{name} olarak giriş yapıldı; oturum kaydedildi ({n} çerez).",
    "Opening {browser} on {url} ...": "{browser} ile {url} açılıyor...",
    "Opening the sign-in window on {url} ...": "{url} için giriş penceresi açılıyor...",
    "The browser was closed before sign-in finished.": "Tarayıcı, giriş tamamlanmadan kapatıldı.",
    "The browser window was closed before sign-in finished.": "Tarayıcı penceresi, giriş tamamlanmadan kapatıldı.",
    "Playwright is not installed; see the README's setup steps.":
        "Playwright kurulu değil; README'deki kurulum adımlarına bakın.",
    "Unknown browser {name}; use {choices}.": "Bilinmeyen tarayıcı {name}; şunlardan birini kullanın: {choices}.",
    "Could not open {browser}: {error}": "{browser} açılamadı: {error}",
    "Using the app's own sign-in window instead.": "Bunun yerine uygulamanın kendi giriş penceresi kullanılıyor.",
    "Could not connect to {browser}: {error}": "{browser} ile bağlantı kurulamadı: {error}",
    "Could not start the browser connection: {error}": "Tarayıcı bağlantısı başlatılamadı: {error}",
    "You are not signed in yet.": "Henüz giriş yapılmadı.",
    "The saved session could not be read.": "Kayıtlı oturum okunamadı.",
    "The saved session belongs to {url}.": "Kayıtlı oturum {url} adresine ait.",
    "Some sign-in data could not be removed; close the sign-in browser if it is still open and sign out again.":
        "Giriş verilerinin bir kısmı silinemedi; açık kalan giriş tarayıcısını kapatıp tekrar çıkış yapın.",

    # macOS menus
    "Edit": "Düzen",
    "Window": "Pencere",
    "Hide Blackboard Sync": "Blackboard Sync'i gizle",
    "Hide Others": "Diğerlerini gizle",
    "Show All": "Tümünü göster",
    "Quit Blackboard Sync": "Blackboard Sync'ten çık",
    "Undo": "Geri al",
    "Redo": "Yinele",
    "Cut": "Kes",
    "Copy": "Kopyala",
    "Paste": "Yapıştır",
    "Select All": "Tümünü seç",
    "Minimize": "Küçült",
    "Close": "Kapat",

    # The menu bar / tray app
    "Blackboard Sync": "Blackboard Sync",
    "Blackboard Sync: syncing": "Blackboard Sync: senkronize ediliyor",
    "Blackboard Sync: session expired": "Blackboard Sync: oturum sona erdi",
    "Blackboard Sync: error": "Blackboard Sync: hata",
    "Blackboard Sync: paused": "Blackboard Sync: duraklatıldı",
    "Blackboard Sync {version} downloaded": "Blackboard Sync {version} indirildi",
    "In the window that opened, drag “Blackboard Sync” onto the “Applications” folder and choose “Replace” to "
    "put it in place of the old version. Quit Blackboard Sync first, then open the app again from the "
    "Applications folder. Your settings and downloaded course files are kept.":
        "Açılan pencerede “Blackboard Sync” simgesini “Applications” klasörüne sürükleyin ve eski sürümün "
        "yerine koymak için “Değiştir”i seçin. Bunun için önce Blackboard Sync'ten çıkmanız gerekir; sonra "
        "uygulamayı Applications klasöründen yeniden açın. Ayarlarınız ve indirdiğiniz ders dosyaları korunur.",
    "File not found.": "Dosya bulunamadı.",
    "Could not install the update.": "Güncelleme yüklenemedi.",
    "Could not install the update": "Güncelleme yüklenemedi",
    "Could not install the update; try again later.": "Güncelleme yüklenemedi; daha sonra tekrar deneyin.",
    "Could not change the start-at-login setting.": "Açılışta başlatma ayarı değiştirilemedi.",
    "Could not restart Blackboard Sync; quit it and open it again.":
        "Blackboard Sync yeniden başlatılamadı; uygulamadan çıkıp yeniden açın.",
    "Sign out?": "Hesaptan çıkış yapılsın mı?",
    "All sign-in data is removed; you will need to enter your school details again to sign in. Your downloaded "
    "files are kept.":
        "Tüm giriş verileri silinir; yeniden giriş yaparken okul bilgilerinizi tekrar girmeniz gerekir. "
        "İndirilen dosyalarınız korunacak.",
    "Could not sign out.": "Hesaptan çıkış yapılamadı.",
    "The update cannot be installed now": "Güncelleme şimdi yüklenemiyor",
    "Later": "Daha sonra",
    "The {folder} folder does not exist yet; sync first.": "{folder} klasörü henüz yok; önce senkronize edin.",
    "Sign out": "Çıkış yap",
    "Cancel": "Vazgeç",
    "Could not save the update: {error}": "Güncelleme kaydedilemedi: {error}",
    "Could not save the course choice: {error}": "Ders seçimi kaydedilemedi: {error}",
    "Could not save the settings: {error}": "Ayarlar kaydedilemedi: {error}",
    "timed out": "zaman aşımı",
    "Could not read the list of past terms.": "Eski dönem listesi okunamadı.",
    "Upcoming deadlines": "Yaklaşan teslim tarihleri",
    "The sync took too long and was stopped.": "Senkron çok uzun sürdü ve durduruldu.",
    "exit status {code}": "çıkış kodu {code}",
    "Could not start the menu bar app: {error}": "Menü çubuğu uygulaması başlatılamadı: {error}",
    "Could not load past terms: {error}": "Eski dönemler yüklenemedi: {error}",
    "Blackboard Sync is running in the background": "Blackboard Sync arka planda çalışıyor",
    "Right-click the Blackboard Sync icon next to the clock for the menu. If you don't see it, click the ^ "
    "arrow that shows hidden icons.":
        "Menü için saatin yanındaki Blackboard Sync simgesine sağ tıklayın. Simge görünmüyorsa gizli "
        "simgeleri gösteren ^ okuna tıklayın.",
    "Wait for the running job to finish before updating.":
        "Güncellemeden önce çalışan işlemin tamamlanmasını bekleyin.",
    "Wait for the running job to finish before updating, then try again.":
        "Güncellemeden önce çalışan işlemin tamamlanmasını bekleyin; sonra tekrar deneyin.",
    "Could not open the announcement.": "Duyuru açılamadı.",
    "The file or folder does not exist yet; sync first.": "Dosya veya klasör henüz yok; önce senkronize edin.",
    "Could not open the file or folder.": "Dosya veya klasör açılamadı.",
    "Blackboard Sync stopped because of an unexpected error.": "Blackboard Sync beklenmeyen bir hata nedeniyle durdu.",
    "The details are in this file:\n{path}": "Ayrıntılar bu dosyada:\n{path}",

    # The main window
    "Applications or Launchpad": "Uygulamalar klasöründen veya Launchpad'den",
    "the Start menu": "Başlat menüsünden",
    "Uninstall": "Kaldır",
    "The folder whose files go to the Trash:": "Çöp Sepeti'ne taşınacak dosyaların klasörü:",
    "The folder whose files go to the Recycle Bin:": "Geri Dönüşüm Kutusu'na taşınacak dosyaların klasörü:",
    "Open the downloaded note": "İndirilen notu aç",
    "Open in Blackboard": "Blackboard'da aç",
    "Get started": "Başlangıç",
    "Home": "Ana sayfa",
    "Sync activity": "Senkron etkinliği",
    "Settings": "Ayarlar",
    "Your course files start here.": "Ders dosyalarınız burada başlayacak.",
    "Connect your Blackboard account and your course files come to this computer by themselves; no more "
    "checking the site every time.":
        "Blackboard hesabınıza bağlanın, ders dosyalarınız kendiliğinden bu bilgisayara insin; siteyi her "
        "seferinde kontrol etmenize gerek kalmasın.",
    "Let's get started": "Başlayalım",
    "Open folder": "Klasörü aç",
    "NEW": "YENİ",
    "Update": "Güncelle",
    "Update to get the latest version.": "En yeni sürüme geçmek için güncelleyin.",
    "Syncing": "Senkron sürüyor",
    "Session expired": "Oturum sona erdi",
    "Not signed in": "Giriş yapılmadı",
    "Waiting for sign-in": "Giriş bekleniyor",
    "Not synced yet": "Henüz senkronize edilmedi",
    "Downloading your files for the first time…": "Dosyalarınız ilk kez indiriliyor…",
    "Unsaved changes": "Kaydedilmemiş değişiklikler",
    "View all": "Tümünü gör",
    "Open": "Aç",
    "Show in folder": "Klasörde göster",
    "Recent downloads": "Son indirilenler",
    "Open calendar": "Takvimi aç",
    "You're all caught up!": "Her şey yolunda!",
    "Things that need your attention will show up here.": "Dikkatinizi gerektiren bir şey burada görünecek.",
    "No upcoming deadlines.": "Yaklaşan teslim yok.",
    "Nothing downloaded yet.": "Henüz indirilen bir şey yok.",
    "Needs your attention": "Dikkatinizi gerektiriyor",
    "Pause": "Duraklat",
    "Up to date": "Güncel",
    "Syncing…": "Senkronize ediliyor…",
    "Paused": "Duraklatıldı",
    "Sign-in needed": "Giriş gerekli",
    "Sync did not finish": "Senkron tamamlanamadı",
    "Sync did not finish: {error}": "Senkron tamamlanamadı: {error}",
    "Name": "Ad",
    "File size": "Dosya boyutu",
    "Status": "Durum",
    "Good morning": "Günaydın",
    "Good afternoon": "İyi günler",
    "Good evening": "İyi akşamlar",
    "No deadlines this week": "Bu hafta teslim tarihi yok",
    "{n} deadline this week": "Bu hafta {n} teslim tarihi",
    "{n} deadlines this week": "Bu hafta {n} teslim tarihi",
    "{n} deadline today": "Bugün {n} teslim tarihi",
    "{n} deadlines today": "Bugün {n} teslim tarihi",
    "{n} this week": "bu hafta {n}",
    "Choose your school and folder": "Okulunuzu ve klasörünüzü seçin",
    "You decide where the files are saved.": "Dosyaların nereye kaydedileceğini siz belirleyin.",
    "Sign in to Blackboard": "Blackboard'a giriş yapın",
    "Your school's sign-in page opens. The first sync starts after you sign in.":
        "Okulunuzun giriş ekranı açılır. Girişten sonra ilk senkron başlar.",
    "Your files stay up to date": "Dosyalarınız kendiliğinden güncellensin",
    "Every hour by default. You can change how often in Settings.":
        "Varsayılan olarak her saat. Sıklığı Ayarlar'dan değiştirebilirsiniz.",
    "You can close this window. To see it again, open Blackboard Sync from {where}.":
        "Bu pencereyi kapatabilirsiniz. Tekrar görmek için Blackboard Sync'i {where} açmanız yeterli.",
    "Last synced: {time}": "Son senkron: {time}",
    "Last attempt: {time}": "Son deneme: {time}",
    "Downloading…": "İndiriliyor…",
    "Sign in to get new files.": "Yeni dosyaları almak için giriş yapın.",
    "Note": "Not",
    "Blackboard Sync {version} is ready": "Blackboard Sync {version} hazır",
    "Blackboard did not return the content; the next sync tries again.":
        "Blackboard içeriği vermedi; sonraki senkronda yeniden denenecek.",
    "Some files could not be downloaded; the next sync tries again.":
        "Bazı dosyalar indirilemedi; sonraki senkronda yeniden denenecek.",
    "Could not read {courses}": "{courses} okunamadı",
    "syncing": "senkronize ediliyor",
    "not syncing": "senkronize edilmiyor",

    # The menu and the app's state
    "Sync now": "Şimdi senkronize et",
    "Loading past terms…": "Eski dönemler yükleniyor…",
    "Sign in": "Giriş yap",
    "Waiting for sign-in…": "Giriş bekleniyor…",
    "⚠ Session expired — Sign in": "⚠ Oturum sona erdi — Giriş yap",
    "Nothing new yet": "Henüz yeni bir şey yok",
    "Pause syncing": "Senkronu duraklat",
    "Resume syncing": "Senkronu sürdür",
    "Settings…": "Ayarlar…",
    "Quit": "Çık",
    "automatic sync off": "otomatik senkron kapalı",
    "Check now": "Şimdi denetle",
    "Checking for updates…": "Güncellemeler denetleniyor…",
    "Downloading update…": "Güncelleme indiriliyor…",
    "Successfully downloaded": "Başarıyla indirildi",
    "Updated": "Güncellendi",
    "Note saved": "Not kaydedildi",
    "Note updated": "Not güncellendi",
    "Announcement saved": "Duyuru kaydedildi",
    "Announcement updated": "Duyuru güncellendi",
    "Waiting for you to sign in in the browser…": "Tarayıcıda giriş yapmanız bekleniyor…",
    "Waiting for you to sign in in the window that opened…": "Açılan pencerede giriş yapmanız bekleniyor…",
    "Waiting for you to sign in in {browser}…": "{browser} penceresinde giriş yapmanız bekleniyor…",
    "new file": "yeni dosya",
    "new files": "yeni dosya",
    "updated file": "güncellenen dosya",
    "updated files": "güncellenen dosya",
    "new note": "yeni not",
    "new notes": "yeni not",
    "updated note": "güncellenen not",
    "updated notes": "güncellenen not",
    "new announcement": "yeni duyuru",
    "new announcements": "yeni duyuru",
    "updated announcement": "güncellenen duyuru",
    "updated announcements": "güncellenen duyuru",
    "large file not downloaded": "büyük dosya indirilmedi",
    "large files not downloaded": "büyük dosya indirilmedi",
    "nothing new": "yeni bir şey yok",
    "{n} file": "{n} dosya",
    "{n} files": "{n} dosya",
    "{n} course": "{n} ders",
    "{n} courses": "{n} ders",
    "{n} warning": "{n} uyarı",
    "{n} warnings": "{n} uyarı",
    "({n} new)": "({n} yeni)",
    "No files were moved.": "Hiçbir dosya taşınmadı.",
    "{files} moved to the new folder.": "{files} yeni klasöre taşındı.",
    "{files} moved to the {folder} folder.": "{files} {folder} klasörüne taşındı.",
    "{files} could not be moved and stayed in the old folder.": "{files} taşınamadı ve eski klasörde kaldı.",
    "{files} could not be moved and stayed where they were.": "{files} taşınamadı ve eski yerinde kaldı.",
    "Open {folder} folder": "{folder} klasörünü aç",
    "Blackboard: new content": "Blackboard: yeni içerik",
    "Click to download the new version.": "Yeni sürümü indirmek için tıklayın.",
    "Blackboard session expired": "Blackboard oturumu sona erdi",
    "Choose “Sign in” in the menu to get new files.": "Yeni dosyaları almak için menüden “Giriş yap”ı seçin.",
    "Sign in and try again to see past terms.": "Eski dönemleri görmek için giriş yapın ve tekrar deneyin.",
    "Some files could not be moved": "Bazı dosyalar taşınamadı",
    "Another sync is running; trying again shortly.": "Başka bir senkron sürüyor; birazdan tekrar denenecek.",
    "Another sync is running; the files will be moved shortly.":
        "Başka bir senkron sürüyor; dosyalar birazdan taşınacak.",
    "Another sync is running; past terms will load again shortly.":
        "Başka bir senkron sürüyor; eski dönemler birazdan yeniden yüklenecek.",
    "Another sync is running; try again to download the past term.":
        "Başka bir senkron sürüyor; eski dönemi indirmek için tekrar deneyin.",
    "Sign in for the new school.": "Yeni okul için giriş yapın.",
    "not synced yet": "henüz senkronize edilmedi",
    "synced at {time}": "{time} senkronize edildi",
    "tried at {time}": "{time} denendi",
    "tried at {time} · error": "{time} denendi · hata",
    "next: {time}": "sonraki: {time}",
    "soon": "birazdan",
    "Checking for new content…": "Yeni içerik kontrol ediliyor…",
    "Moving files to the new folder…": "Dosyalar yeni klasöre taşınıyor…",
    "Moving files to the {folder} folder…": "Dosyalar {folder} klasörüne taşınıyor…",
    "Downloading {term} (past term)…": "{term} indiriliyor (eski dönem)…",
    "Choose “{settings}” to finish setting up": "Kurulumu tamamlamak için “{settings}” seçeneğini seçin",
    "The past term download was paused; download it again.": "Eski dönem indirmesi duraklatıldı; tekrar indirin.",
    "Blackboard Sync {version} is ready — Update": "Blackboard Sync {version} hazır — Güncelle",
    "Blackboard Sync is up to date": "Blackboard Sync güncel",
    "You have the latest version ({version}).": "Kullandığınız sürüm ({version}) en yenisi.",
    "Your settings and downloaded course files were kept.": "Ayarlarınız ve indirdiğiniz ders dosyaları korundu.",
    "Files moved": "Dosyalar taşındı",
    "Files moved to the {folder} folder": "Dosyalar {folder} klasörüne taşındı",
    "Could not check for updates": "Güncellemeler denetlenemedi",
    "Check your internet connection and try again later.":
        "İnternet bağlantınızı kontrol edin ve daha sonra tekrar deneyin.",
    "Blackboard Sync {version} could not be put in place; version {current} is still in use.":
        "Blackboard Sync {version} yerine konamadı; {current} sürümü kullanılmaya devam ediyor.",
    "Blackboard Sync was updated to {version}": "Blackboard Sync {version} sürümüne güncellendi",
    "Update available: {version} — Update": "Güncelleme var: {version} — Güncelle",
    "{term} · {files} downloaded (past term).": "{term} · {files} indirildi (eski dönem).",
    "Could not read the content of {courses}; the past term is not complete, try again.":
        "{courses} içeriği okunamadı; eski dönem tamamlanmadı, tekrar deneyin.",
    "{warnings}; try again for what is missing.": "{warnings}; eksikler için tekrar deneyin.",
    "Blackboard: past term": "Blackboard: eski dönem",
    "Sign in and try again to download the past term.": "Eski dönemi indirmek için giriş yapın ve tekrar deneyin.",
    "Could not download the past term: {error}": "Eski dönem indirilemedi: {error}",
    "Could not move the files: {error}": "Dosyalar taşınamadı: {error}",
    "Sign-in did not finish: {error}": "Giriş tamamlanamadı: {error}",
    "No courses yet": "Henüz ders yok",

    # Settings
    "Automatic sync": "Otomatik senkron",
    "Every 30 minutes": "30 dakikada bir",
    "Every hour": "Saatte bir",
    "Every 3 hours": "3 saatte bir",
    "Only manually": "Yalnızca elle",
    "Language": "Dil",
    "Danger zone": "Tehlikeli bölge",
    "Term": "Dönem",
    "Download the selected term": "Seçilen dönemi indir",
    "How often Blackboard is checked for new files.": "Blackboard'da yeni dosyaların ne sıklıkla aranacağı.",
    "Keeps syncing in the background after you sign in to the computer.":
        "Bilgisayarda oturum açtığınızda arka planda senkronize etmeye devam eder.",
    "Looks for a new version once a day.": "Günde bir kez yeni sürüm arar.",
    "Uninstall Blackboard Sync": "Blackboard Sync'i kaldır",
    "Restart Blackboard Sync to change the language?": "Dili değiştirmek için Blackboard Sync yeniden başlatılsın mı?",
    "The new language is used once the app starts again.": "Yeni dil, uygulama yeniden başladığında kullanılır.",
    "Restart now": "Şimdi yeniden başlat",
    "Account": "Hesap",
    "Folder": "Klasör",
    "Past terms": "Eski dönemler",
    "Sync": "Senkron",
    "Updates": "Güncellemeler",
    "Your school's Blackboard address": "Okulunuzun Blackboard adresi",
    "https://blackboard.school.edu": "https://blackboard.okul.edu.tr",
    "If you change the address you need to sign in again for the new school.":
        "Adresi değiştirirseniz yeni okul için tekrar giriş yapmanız gerekir.",
    "Folder to save files in": "Dosyaların kaydedileceği klasör",
    "Files are saved in the University folder inside the folder you choose.":
        "Dosyalar seçtiğiniz klasörün içindeki University klasörüne kaydedilir.",
    "If you change the folder you can move the downloaded files to the new one or download them again.":
        "Klasörü değiştirirseniz indirilmiş dosyaları yeni klasöre taşımayı ya da yeniden indirmeyi "
        "seçebilirsiniz.",
    "Download past term": "Eski dönemi indir",
    "A past term is downloaded once and not updated.": "Eski dönem bir kez indirilir, güncellenmez.",
    "Sign in to see past terms.": "Eski dönemleri görmek için giriş yapın.",
    "Start when the computer starts": "Bilgisayar açılınca başlat",
    "Check for updates automatically": "Güncellemeleri otomatik denetle",
    "Choose…": "Seç…",
    "Use this folder": "Bu klasörü kullan",
    "Choose the folder to save your course files in.": "Ders dosyalarının kaydedileceği klasörü seçin.",
    "Save": "Kaydet",
    "Wait for the running job to finish first.": "Önce çalışan işlemin tamamlanmasını bekleyin.",
    "The folder was not changed.": "Klasör değiştirilmedi.",
    "What should happen to the downloaded files?": "İndirilen dosyalar ne olsun?",
    "Move": "Taşı",
    "Download again": "Yeniden indir",
    "“{folder}” holds {n} file downloaded from Blackboard.":
        "“{folder}” klasöründe Blackboard'dan indirilmiş {n} dosya var.",
    "“{folder}” holds {n} files downloaded from Blackboard.":
        "“{folder}” klasöründe Blackboard'dan indirilmiş {n} dosya var.",
    "{move}: the files are moved to “{folder}”, not downloaded again. Files you added yourself stay in the old "
    "folder.":
        "{move}: dosyalar “{folder}” klasörüne taşınır, yeniden indirilmez. Kendi eklediğiniz dosyalar eski "
        "klasörde kalır.",
    "{redownload}: the files are downloaded again into the new folder; the old folder is not touched.":
        "{redownload}: dosyalar yeni klasöre yeniden indirilir; eski klasöre dokunulmaz.",
    "Checking…": "Denetleniyor…",
    "Your session expired; sign in again.": "Oturum sona erdi; tekrar giriş yapın.",
    "Not signed in yet.": "Henüz giriş yapılmadı.",
    "Version {version}": "Sürüm {version}",
    "Signed in as {name}": "Giriş yapıldı: {name}",
    "Update to {version}": "{version} sürümüne güncelle",
    "Enter a valid address, for example https://blackboard.school.edu":
        "Geçerli bir adres yazın, örneğin https://blackboard.okul.edu.tr",
    "Enter your school's Blackboard address.": "Okulunuzun Blackboard adresini yazın.",
    "The address must start with https://.": "Adres https:// ile başlamalı.",
    "Choose the folder to save the files in.": "Dosyaların kaydedileceği klasörü seçin.",
    "Enter the folder's full path, for example ~/Documents/University":
        "Klasörü tam yoluyla yazın, örneğin ~/Documents/University",
    "This path is not a folder.": "Bu yol bir klasör değil.",

    # The sync report
    "Would sync {n} course(s) for {terms} into {folder}":
        "{terms} için {n} ders {folder} klasörüne senkronize edilecekti",
    "Synced {n} course(s) for {terms} into {folder}": "{terms} için {n} ders {folder} klasörüne senkronize edildi",
    "Past term: downloaded once, not updated automatically.": "Eski dönem: bir kez indirilir, otomatik güncellenmez.",
    "Nothing new.": "Yeni bir şey yok.",
    "no changes": "değişiklik yok",
    "Moved {n} file(s) into {folder}": "{n} dosya {folder} klasörüne taşındı",
    "{n} file(s) could not be moved and stayed where they were:": "{n} dosya taşınamadı ve eski yerinde kaldı:",
    "no term": "dönem yok",
    "{n} course(s) had changes.": "{n} derste değişiklik var.",

    # The sync
    "Could not read {name} ({error}); moved it to {saved} and continued with an empty state. Files already on "
    "disk that match Blackboard's copy are kept as they are, not duplicated.":
        "{name} okunamadı ({error}); {saved} adıyla kenara alındı ve boş bir kayıtla devam edildi. Diskte "
        "Blackboard'daki kopyayla aynı olan dosyalar olduğu gibi korunur, ikinci kez indirilmez.",
    "Could not read {name} ({error}); it would be set aside on a real sync.":
        "{name} okunamadı ({error}); gerçek bir senkronda kenara alınacak.",
    "Name a single past term to download.": "İndirilecek tek bir eski dönem adı belirtin.",
    "Blackboard did not identify the signed-in user.": "Blackboard giriş yapan kullanıcıyı tanımlamadı.",
    "Another blackboard-sync run is already in progress.": "Başka bir blackboard-sync çalışması zaten sürüyor.",
    "No term named {name}.": "{name} adlı dönem bulunamadı.",
    "{name} is the current term; the normal sync downloads it.":
        "{name} güncel dönem; indirmek için normal senkronu kullanın.",
    "{name} is not a past term that can be downloaded.": "{name} indirilebilecek eski bir dönem değil.",
    "More than one term is named {name}; choose one by its id (--term-id): ":
        "{name} adında birden fazla dönem var; birini kimliğiyle seçin (--term-id): ",
    "Kept folder {old}: could not rename it to {new} because that folder already exists. Move your files into "
    "one of them to finish.":
        "{old} klasörü korundu: {new} olarak yeniden adlandırılamadı, çünkü o klasör zaten var. Tamamlamak "
        "için dosyalarınızı bunlardan birine taşıyın.",
    "Kept folder {old}: could not rename it to {new} ({error}).":
        "{old} klasörü korundu: {new} olarak yeniden adlandırılamadı ({error}).",
    "Could not read course content: {error}": "Ders içeriği okunamadı: {error}",
    "Could not sync announcements: {error}": "Duyurular senkronize edilemedi: {error}",
    "Could not read due dates: {error}": "Teslim tarihleri okunamadı: {error}",
    "Could not read term {term}; using its id as folder name.":
        "{term} dönemi okunamadı; klasör adı olarak kimliği kullanılıyor.",
    "Skipped course {course}: {error}": "{course} dersi atlandı: {error}",
    "Could not open folder {name}: {error}": "{name} klasörü açılamadı: {error}",
    "Skipped {name}: {error}": "{name} atlandı: {error}",

    # Uninstalling
    "Uninstall Blackboard Sync?": "Blackboard Sync kaldırılsın mı?",
    "Uninstall app…": "Uygulamayı kaldır…",
    "Also delete the downloaded course files": "İndirilmiş ders dosyalarını da sil",
    "The app and all of its records, logs, settings and sign-in data are removed, and so is its start-at-login "
    "entry. Downloaded course files are kept unless you tick this option.":
        "Uygulama, tüm uygulama kayıtları, günlükler, ayarlar ve giriş verileri kaldırılır. Bilgisayar açılınca "
        "başlatma kaydı da silinir. İndirilmiş ders dosyaları bu seçeneği işaretlemediğiniz sürece korunur.",
    "Wait for the sync or the folder move to finish before uninstalling.":
        "Kaldırmadan önce senkronizasyonun veya klasör taşıma işleminin tamamlanmasını bekleyin.",
    "You can uninstall Blackboard Sync from Windows Settings → Apps.":
        "Blackboard Sync'i Windows Ayarlar → Uygulamalar bölümünden kaldırabilirsiniz.",
    "Remove the app's files yourself.": "Uygulama dosyalarını elle kaldırın.",
    "The download records could not be read; the course files were kept to be safe.":
        "İndirme kayıtları okunamadı; güvenlik için ders dosyaları korundu.",
    "The app data folder contains the download folder or the home folder; uninstall cancelled.":
        "Uygulama veri klasörü indirme klasörünü veya ev klasörünü içeriyor; kaldırma iptal edildi.",
    "Quit Blackboard Sync first, or use Uninstall app… in its settings.":
        "Önce Blackboard Sync'ten çıkın veya ayarlarındaki Uygulamayı kaldır… seçeneğini kullanın.",
    "A lock file is a link; the app could not be removed safely.":
        "Kilit dosyası bir bağlantı; güvenli kaldırma yapılamadı.",
    "The uninstaller could not be started. Uninstall Blackboard Sync from Windows Settings → Apps; if needed, "
    "delete this folder yourself: {path}":
        "Uygulama kaldırıcısı başlatılamadı. Windows Ayarlar → Uygulamalar bölümünden Blackboard Sync'i "
        "kaldırın; gerekirse bu klasörü elle silin: {path}",
    "The app could not be removed; delete it yourself: {error}": "Uygulama kaldırılamadı; uygulamayı elle silin: {error}",
    "Could not move an empty folder to the Trash: {path} ({error})":
        "Boş klasör Çöp Sepeti'ne taşınamadı: {path} ({error})",
    "Could not delete a lock file: {name} ({error})": "Kilit dosyası silinemedi: {name} ({error})",
    "The app could not be moved to the Trash. Delete it in Finder yourself: {path}":
        "Uygulama Çöp Sepeti'ne taşınamadı. Finder'da bu uygulamayı elle silin: {path}",
    "Could not move a file to the Trash: {path} ({error})": "Dosya Çöp Sepeti'ne taşınamadı: {path} ({error})",
    "Could not clear the sign-in data: {error}": "Giriş verileri temizlenemedi: {error}",
    "Could not remove the start-at-login entry: {error}": "Açılışta başlatma kaydı silinemedi: {error}",
    "Could not clear the app data folder: {path} ({error})": "Uygulama veri klasörü temizlenemedi: {path} ({error})",
    "Could not move the course files to the Trash: {error}": "Ders dosyaları Çöp Sepeti'ne taşınamadı: {error}",
    "Could not delete app data: {path}": "Uygulama verisi silinemedi: {path}",
    "The Recycle Bin API could not be loaded; the file was kept.":
        "Geri Dönüşüm Kutusu API'si yüklenemedi; dosya korundu.",
    "The file could not be moved to the Recycle Bin; it was kept.":
        "Dosya Geri Dönüşüm Kutusu'na taşınamadı; dosya korundu.",
    "The file cannot be recycled; permanent deletion was cancelled.":
        "Dosya geri dönüştürülemiyor; kalıcı silme iptal edildi.",
    "The Recycle Bin operation failed: {error}": "Geri Dönüşüm Kutusu işlemi başarısız: {error}",

    # Updates
    "The update cannot be installed while a sync or a folder move runs; try again once it has finished.":
        "Senkronizasyon veya klasör taşıma sürerken güncelleme yüklenemez; tamamlandıktan sonra tekrar deneyin.",
    "the current version is kept.": "mevcut sürüm korunuyor.",
    "Blackboard Sync runs from its disk image, so it cannot update itself.":
        "Blackboard Sync disk görüntüsünden çalıştığı için kendini güncelleyemiyor.",
    "macOS runs Blackboard Sync from a temporary location, so the app cannot update itself.":
        "macOS, Blackboard Sync'i geçici bir konumdan çalıştırdığı için uygulama kendini güncelleyemiyor.",
    "The folder Blackboard Sync is in cannot be written to, so the app cannot update itself.":
        "Blackboard Sync'in bulunduğu klasöre yazılamadığı için uygulama kendini güncelleyemiyor.",
    "This version is unsigned, so the update cannot be verified and installed automatically.":
        "Bu sürüm imzasız olduğu için güncelleme otomatik doğrulanıp yüklenemiyor.",
    "The update's disk image could not be opened;": "Güncellemenin disk görüntüsü açılamadı;",
    "Blackboard Sync was not found in the disk image;": "Disk görüntüsünde Blackboard Sync bulunamadı;",
    "The downloaded update is not the expected Blackboard Sync version;":
        "İndirilen güncelleme beklenen Blackboard Sync sürümü değil;",
    "The update's signature is not valid;": "Güncellemenin imzası geçersiz;",
    "The update is not signed by the Blackboard Sync developer;":
        "Güncelleme Blackboard Sync geliştiricisi tarafından imzalanmamış;",
    "The update is not notarized by Apple;": "Güncelleme Apple tarafından onaylanmamış (notarization);",
    "The new version could not be copied;": "Yeni sürüm kopyalanamadı;",
    "The update could not be started;": "Güncelleme başlatılamadı;",
    "Updates are installed through the Microsoft Store.": "Güncellemeler Microsoft Store üzerinden yüklenir.",
    "The update could not be verified.": "Güncelleme doğrulanamadı.",
    "The update does not come from this app's page; it was not downloaded.":
        "Güncelleme bu uygulamanın sayfasından gelmiyor; indirilmedi.",
    "The downloaded update could not be verified; it was not installed.":
        "İndirilen güncelleme doğrulanamadı; yüklenmedi.",
    "The update could not be downloaded; check your internet connection.":
        "Güncelleme indirilemedi; internet bağlantınızı kontrol edin.",
    "The update could not be downloaded.": "Güncelleme indirilemedi.",
}
