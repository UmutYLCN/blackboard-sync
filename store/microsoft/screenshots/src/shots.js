// The Store screenshots: one entry per image, in listing order. `id` is also the
// file name of the app capture (windows/<id>.png, or draft-input/<id>.png for a
// draft). `title` is the large caption drawn on the image ([plain, highlighted]);
// `caption` is the text for Partner Center's screenshot caption field (200
// characters at most). `capture` says which Windows screenshot to take.
window.SHOTS = [
  {
    id: "01-genel-bakis",
    title: { tr: ["Ders dosyaların ", "kendiliğinden iner."], en: ["Your course files ", "download themselves."] },
    caption: {
      tr: "Genel bakış: Blackboard'daki yeni ders dosyaları arka planda kendiliğinden iner; son indirilenler tek listede.",
      en: "Overview: new course files on Blackboard download in the background; the latest downloads are listed in one place.",
    },
    capture: "Genel bakış after a sync, Son indirilenler list filled",
  },
  {
    id: "02-ayarlar",
    title: { tr: ["Senkron sıklığını ", "sen seç."], en: ["You choose ", "how often it syncs."] },
    caption: {
      tr: "Genel: okul adresi, kayıt klasörü, otomatik senkron (30 dakikada, saatte, 3 saatte bir ya da yalnızca elle) ve bilgisayar açılınca başlatma.",
      en: "General: school address, download folder, automatic sync (every 30 minutes, hourly, every 3 hours or manual only) and start at sign-in.",
    },
    capture: "Genel page, top: Hesap, Klasör and Genel sections",
  },
  {
    id: "03-silinenler",
    title: { tr: ["Sildiğin dosyaları ", "geri indir."], en: ["Get deleted files ", "back."] },
    caption: {
      tr: "Silinenler: klasörden sildiğin indirilmiş dosyaları seçip yeniden indirebilir ya da listeden kaldırabilirsin.",
      en: "Deleted: pick downloaded files you removed from the folder and download them again, or dismiss them from the list.",
    },
    capture: "Silinenler page with a few deleted files listed",
  },
  {
    id: "04-eski-donemler",
    title: { tr: ["Geçmiş dönemleri ", "tek seferde indir."], en: ["Download a past term ", "in one go."] },
    caption: {
      tr: "Eski dönemler: geçmiş bir dönemin dosyalarını tek seferde indir. Eski dönem bir kez indirilir, güncellenmez.",
      en: "Past terms: download the files of an earlier term in one go. A past term is downloaded once and not kept up to date.",
    },
    capture: "Genel page scrolled to Eski dönemler, a term selected",
  },
  {
    id: "05-klasorler",
    title: { tr: ["Dönem dönem, ders ders: ", "hep düzenli."], en: ["By term, by course: ", "always organised."] },
    caption: {
      tr: "Dosyalar seçtiğin klasördeki University klasörüne, Blackboard'daki dönem ve ders yapısıyla kaydedilir.",
      en: "Files are saved in the University folder inside the folder you choose, by term and course as on Blackboard.",
    },
    capture: "File Explorer on Belgeler\\University, term and course folders expanded",
  },
];
