// The three available Windows captures, in Store listing order. `id` also names
// the PNG in windows/. Titles are drawn by template.html; captions are for
// Partner Center (at most 200 characters). Ship the Turkish-titled images for
// both listing languages. Add further shots only when Windows captures exist.
window.SHOTS = [
  {
    id: "01-genel-bakis",
    title: { tr: ["Ders dosyaların ", "kendiliğinden iner."], en: ["Your course files ", "download themselves."] },
    caption: {
      tr: "Genel bakış: Blackboard'daki yeni ders dosyaları arka planda kendiliğinden iner; son indirilenler tek listede.",
      en: "Overview: new course files on Blackboard download in the background; the latest downloads are listed in one place.",
    },
    capture: "Genel bakış after a sync, Son indirilenler list with 10 files",
  },
  {
    id: "02-baslangic",
    title: { tr: ["Okulunu ve klasörünü seç, ", "giriş yap."], en: ["Choose your school and folder, ", "sign in."] },
    caption: {
      tr: "Başlangıç: okulunun Blackboard adresini yaz, kayıt klasörünü ve bilgisayar açılınca başlatma seçeneğini belirle, ardından giriş yap.",
      en: "Getting started: enter your school's Blackboard address, choose a save folder and whether to start with your computer, then sign in.",
    },
    capture: "Başlangıç first-run page: school address, save folder, start with computer and Giriş yap",
  },
  {
    id: "03-ilk-senkron",
    title: { tr: ["Girişten sonra ", "ilk senkron başlar."], en: ["After sign-in, ", "your first sync starts."] },
    caption: {
      tr: "İlk senkron girişten sonra başlar. Genel bakışta yeni içerik kontrol edilirken senkronun sürdüğünü görebilirsin.",
      en: "The first sync starts after sign-in. Overview shows that syncing is in progress while the app checks for new content.",
    },
    capture: "Genel bakış during first sync: Yeni içerik kontrol ediliyor… and Senkron sürüyor",
  },
];
