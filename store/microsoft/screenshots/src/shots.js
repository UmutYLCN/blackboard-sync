// Store upload order: a text-only promo card, then four Windows captures.
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
      tr: "Genel bakış: Blackboard'daki yeni ders dosyaları arka planda kendiliğinden iner; son indirilenler tek listede.",
      en: "Overview: new course files on Blackboard download in the background; the latest downloads are listed in one place.",
    },
    capture: "Genel bakış after a sync, Son indirilenler list with 10 files",
  },
  {
    id: "03-baslangic",
    title: { tr: ["Okulunu ve klasörünü seç, ", "giriş yap."], en: ["Choose your school and folder, ", "sign in."] },
    caption: {
      tr: "Başlangıç: okulunun Blackboard adresini yaz, kayıt klasörünü ve bilgisayar açılınca başlatma seçeneğini belirle, ardından giriş yap.",
      en: "Getting started: enter your school's Blackboard address, choose a save folder and whether to start with your computer, then sign in.",
    },
    capture: "Başlangıç first-run page: school address, save folder, start with computer and Giriş yap",
  },
  {
    id: "04-ilk-senkron",
    title: { tr: ["Girişten sonra ", "ilk senkron başlar."], en: ["After sign-in, ", "your first sync starts."] },
    caption: {
      tr: "İlk senkron girişten sonra başlar. Genel bakışta yeni içerik kontrol edilirken senkronun sürdüğünü görebilirsin.",
      en: "The first sync starts after sign-in. Overview shows that syncing is in progress while the app checks for new content.",
    },
    capture: "Genel bakış during first sync: Yeni içerik kontrol ediliyor… and Senkron sürüyor",
  },
  {
    id: "05-tepsi-menusu",
    title: { tr: ["Saatin yanında ", "sessizce çalışır."], en: ["Quietly working ", "from your system tray."] },
    caption: {
      tr: "Pencereyi kapatsan da uygulama saatin yanındaki simgeden çalışır. Son senkronu gör, yeni bir senkron başlat veya derslerine ve indirdiklerine ulaş.",
      en: "The app keeps working from the system tray after you close its window. Check the last sync, sync again, or access your courses and recent downloads.",
    },
    capture: "Windows notification-area icon menu: last sync, sync now, courses, recent downloads and University folder",
    compact: true,
  },
];
