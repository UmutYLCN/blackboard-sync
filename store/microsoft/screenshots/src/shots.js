// Store upload order: a text-only promo card, then eight Windows captures (capture.py).
// `id` names the output PNG and, for captures, the PNG in windows/. `kind: "card"`
// needs no image input. Title parts are [plain, highlighted, optional suffix].
// Captions are at most 200 characters. Ship Turkish titles for both listings.
window.SHOTS = [
  {
    id: "01-tek-tek",
    kind: "card",
    title: {
      tr: ["Blackboard’dan dosyaları\n", "tek tek", " mi indiriyorsun?"],
      en: ["Still downloading files\n", "one by one", "?"],
    },
    subtitle: { tr: "Buna artık gerek yok.", en: "You no longer have to." },
    caption: {
      tr: "Blackboard’dan dosyaları tek tek mi indiriyorsun? Blackboard Sync, ders dosyalarını arka planda otomatik olarak bilgisayarına indirir.",
      en: "Still downloading Blackboard files one by one? Blackboard Sync automatically downloads your course files to your computer in the background.",
    },
  },
  {
    id: "02-genel-bakis",
    title: { tr: ["Ders dosyaların ", "kendiliğinden iner."], en: ["Your course files ", "download themselves."] },
    caption: {
      tr: "Ana sayfa: yeni ders dosyaları arka planda kendiliğinden iner. Son indirilenler, duyurular ve yaklaşan teslim tarihleri tek bakışta.",
      en: "Home: new course files download in the background. Recent downloads, announcements and upcoming due dates at a glance.",
    },
    capture: "Ana sayfa after a sync: greeting, Güncel, recent files, announcements and upcoming due dates",
  },
  {
    id: "03-teslim-tarihleri",
    title: { tr: ["Teslim tarihlerini ", "kaçırma."], en: ["Never miss ", "a due date."] },
    caption: {
      tr: "Takvim: yaklaşan teslim tarihleri gün gün listelenir. Teslime 24 saat ve 1 saat kala bildirim gelir.",
      en: "Calendar: upcoming due dates, day by day. A notification comes 24 hours and 1 hour before each one is due.",
    },
    capture: "Takvim page: upcoming due dates grouped by day",
  },
  {
    id: "04-google-takvim",
    title: { tr: ["Teslim tarihlerin ", "Google Takvim’inde."], en: ["Your due dates in ", "Google Calendar."] },
    caption: {
      tr: "Ayarlar’dan Google Takvim’i bağla: teslim tarihleri ayrı bir Blackboard Deadlines takviminde güncel kalır. Diğer takvimlerin gizli kalır.",
      en: "Connect Google Calendar in Settings: due dates stay up to date in a separate Blackboard Deadlines calendar. Your other calendars stay private.",
    },
    capture: "Ayarlar: Görünüm (theme) and Google Takvim connected",
  },
  {
    id: "05-duyurular",
    title: { tr: ["Tüm duyurular ", "tek yerde."], en: ["Every announcement ", "in one place."] },
    caption: {
      tr: "Duyurular: tüm derslerinin Blackboard duyuruları tek listede, en yenisi en üstte. Herhangi birini tek tıkla aç.",
      en: "Announcements: every course’s Blackboard announcements in one list, newest first. Open any of them in one click.",
    },
    capture: "Duyurular page with three announcements",
  },
  {
    id: "06-dersler",
    title: { tr: ["Hangi derslerin ineceğini ", "sen seç."], en: ["You choose ", "which courses sync."] },
    caption: {
      tr: "Dersler: bu dönemin derslerini gör, istemediğinin işaretini kaldır. İşaretsiz dersler senkronize edilmez; indirilmiş dosyalar silinmez.",
      en: "Courses: see this term’s courses and untick the ones you don’t want. Unticked courses are not synced; downloaded files are not deleted.",
    },
    capture: "Dersler page: five courses, one turned off",
  },
  {
    id: "07-koyu-tema",
    title: { tr: ["Açık mı, koyu mu? ", "Sen seç."], en: ["Light or dark? ", "Your choice."] },
    caption: {
      tr: "Koyu tema: uygulama Windows’un temasını izler ya da Ayarlar’dan açık veya koyu temada kalır.",
      en: "Dark theme: the app follows your Windows theme, or stays light or dark from Settings.",
    },
    capture: "Ana sayfa in the dark theme",
  },
  {
    id: "08-baslangic",
    title: { tr: ["Okulunu ve klasörünü seç, ", "giriş yap."], en: ["Choose your school and folder, ", "sign in."] },
    caption: {
      tr: "Başlangıç: okulunun Blackboard adresini yaz, kayıt klasörünü ve bilgisayar açılınca başlatma seçeneğini belirle, ardından giriş yap.",
      en: "Getting started: enter your school's Blackboard address, choose a save folder and whether to start with your computer, then sign in.",
    },
    capture: "Başlangıç first-run page: school address, save folder, start with computer and Giriş yap",
  },
  {
    id: "09-tepsi-menusu",
    title: { tr: ["Saatin yanında ", "sessizce çalışır."], en: ["Quietly working ", "from your system tray."] },
    caption: {
      tr: "Pencereyi kapatsan da uygulama saatin yanındaki simgeden çalışır. Son senkronu gör, yeni bir senkron başlat veya derslerine ve indirdiklerine ulaş.",
      en: "The app keeps working from the system tray after you close its window. Check the last sync, sync again, or access your courses and recent downloads.",
    },
    capture: "Notification-area menu above the taskbar, with the tray icon",
    compact: true,
  },
];
