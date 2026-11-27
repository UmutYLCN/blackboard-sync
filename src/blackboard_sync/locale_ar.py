"""Arabic (Modern Standard) for every text the app shows: English text -> Arabic text.

The keys are the exact strings passed to ``i18n.tr`` / ``ntr`` in the code;
``tests/test_i18n.py`` checks that each one is here with the same ``{fields}``.
``ntr`` has only a one-form and a many-form, so the many-form uses the plural
that reads correctly for the counts the app shows (usually 2 or more); numbers
are shown as Western digits.
"""

CATALOG = {
    # Announcements
    "Announcements": "الإعلانات",
    "Every announcement synced from your current-term courses.":
        "كل الإعلانات التي تمت مزامنتها من مقررات الفصل الدراسي الحالي.",
    "No announcements yet. They show up here once they are synced.":
        "لا توجد إعلانات بعد. ستظهر هنا بعد مزامنتها.",
    "No date given": "بلا تاريخ",
    "Open announcement": "فتح الإعلان",
    "Announcement": "إعلان",

    # Blackboard and the command line
    "Your Blackboard session has expired.": "انتهت صلاحية جلستك في Blackboard.",
    "Blackboard redirected to a sign-in page.": "أعاد Blackboard التوجيه إلى صفحة تسجيل الدخول.",
    "Blackboard answered with a web page instead of data.": "ردّ Blackboard بصفحة ويب بدلًا من البيانات.",
    "Blackboard answered a download with a web page.": "ردّ Blackboard على طلب التنزيل بصفحة ويب.",
    "Next: run `blackboard-sync sync` to download your courses.":
        "الخطوة التالية: شغّل `blackboard-sync sync` لتنزيل مقرراتك.",
    "Blackboard Sync's app data was removed.": "تمت إزالة بيانات تطبيق Blackboard Sync.",
    "Session OK: signed in as {name}.": "الجلسة صالحة: تم تسجيل الدخول باسم {name}.",
    "Term(s): {terms}": "الفصول الدراسية: {terms}",
    "No courses found on Blackboard, so the current term could not be determined. "
    "Your courses will be synced as soon as Blackboard lists them.":
        "لم يُعثر على أي مقررات في Blackboard، لذا تعذّر تحديد الفصل الدراسي الحالي. "
        "ستتم مزامنة مقرراتك فور ظهورها في Blackboard.",
    "none found": "لم يُعثر على شيء",
    "Network error talking to Blackboard: {error}": "خطأ في الشبكة أثناء الاتصال بـ Blackboard: {error}",
    "Unexpected error: {error}": "خطأ غير متوقع: {error}",
    "Error: {error}": "خطأ: {error}",
    "Run `blackboard-sync login` to sign in to Blackboard.":
        "شغّل `blackboard-sync login` لتسجيل الدخول إلى Blackboard.",

    # Courses
    "Courses": "المقررات",
    "This folder is a copy of Blackboard: the files of the ticked courses are matched to Blackboard on every "
    "sync, and deleted or damaged files are downloaded again. To keep files your own way, copy them to another "
    "folder.":
        "هذا المجلد نسخة من Blackboard: تُطابَق ملفات المقررات المحددة مع Blackboard في كل مزامنة، "
        "ويُعاد تنزيل الملفات المحذوفة أو التالفة. للاحتفاظ بالملفات بطريقتك الخاصة، انسخها إلى مجلد آخر.",
    "A course you untick is no longer synced and does not show in Calendar or Announcements. Its downloaded "
    "files are not deleted. Tick it again and its missing files come right away.":
        "المقرر الذي تلغي تحديده لا تتم مزامنته بعد ذلك، ولا يظهر في التقويم أو الإعلانات. لا تُحذف "
        "ملفاته التي نُزّلت. حدّده مرة أخرى وستصل ملفاته الناقصة فورًا.",
    "Courses without a term, such as guidance or orientation pages, are not synced unless you tick them.":
        "المقررات التي ليس لها فصل دراسي، مثل صفحات الإرشاد أو التهيئة، لا تتم مزامنتها إلا إذا حددتها.",
    "Your courses are listed here after the first sync.": "تظهر مقرراتك هنا بعد أول مزامنة.",
    # The card before the first download at a school whose current term is not clear
    "Check your courses before the first download": "راجع مقرراتك قبل أول تنزيل",
    "Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
    "Untick any course you do not want, then confirm. Nothing is downloaded until you do.":
        "لم يتمكن Blackboard Sync من التأكد من الفصل الدراسي الحالي في هذه الجامعة. الفصول التي وجدها: {terms}. "
        "ألغِ تحديد أي مقرر لا تريده، ثم أكّد. لن يُنزَّل أي شيء حتى تؤكد.",
    "Confirm": "تأكيد",
    "Not now": "ليس الآن",
    "Waiting for you to confirm the courses to download.": "بانتظار تأكيدك للمقررات المراد تنزيلها.",

    # Calendar
    "Calendar": "التقويم",
    "Due dates are updated during a sync. Times are in this computer's local time.":
        "تُحدَّث مواعيد التسليم أثناء المزامنة. الأوقات بالتوقيت المحلي لهذا الحاسوب.",
    "Upcoming": "القادمة",
    "Past due": "انتهى موعدها",
    "Submissions are not checked; work you already handed in may show here too.":
        "لا يتم التحقق من حالة التسليم؛ قد تظهر هنا أيضًا أعمال سلّمتها بالفعل.",
    "No due dates saved.": "لا توجد مواعيد تسليم محفوظة.",
    "Sync to see due dates.": "زامِن لعرض مواعيد التسليم.",
    "Some courses' due dates could not be updated. Earlier ones are shown where there are any.":
        "تعذّر تحديث مواعيد التسليم لبعض المقررات. تُعرض المواعيد السابقة إن وُجدت.",
    "January": "يناير",
    "February": "فبراير",
    "March": "مارس",
    "April": "أبريل",
    "May": "مايو",
    "June": "يونيو",
    "July": "يوليو",
    "August": "أغسطس",
    "September": "سبتمبر",
    "October": "أكتوبر",
    "November": "نوفمبر",
    "December": "ديسمبر",
    "Monday": "الاثنين",
    "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء",
    "Thursday": "الخميس",
    "Friday": "الجمعة",
    "Saturday": "السبت",
    "Sunday": "الأحد",
    "Due in 1 hour": "التسليم بعد ساعة",
    "Deadline coming up": "موعد التسليم يقترب",
    "Today": "اليوم",
    "Tomorrow": "غدًا",
    "{month} {day}": "{day} {month}",
    "{month} {day}, {year}": "{day} {month} {year}",
    "Untitled work": "عمل بلا عنوان",
    "today {time}": "اليوم {time}",
    "tomorrow {time}": "غدًا {time}",
    "yesterday {time}": "أمس {time}",
    "Due: {time}": "التسليم: {time}",

    # Signing in
    "Blackboard Sync – Sign in": "Blackboard Sync – تسجيل الدخول",
    "The sign-in window was closed before sign-in finished.": "أُغلقت نافذة تسجيل الدخول قبل اكتمال تسجيل الدخول.",
    "The sign-in window needs the Microsoft Edge WebView2 Runtime, which is missing on this computer. Install "
    "it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 or install Google Chrome or Microsoft Edge, then "
    "sign in again.":
        "تحتاج نافذة تسجيل الدخول إلى Microsoft Edge WebView2 Runtime، وهو غير مثبّت على هذا الحاسوب. "
        "ثبّته من https://go.microsoft.com/fwlink/p/?LinkId=2124703 أو ثبّت Google Chrome أو "
        "Microsoft Edge، ثم سجّل الدخول مرة أخرى.",
    "Sign-in was not completed within {n} minutes.": "لم يكتمل تسجيل الدخول خلال {n} دقائق.",
    "The sign-in window is unavailable ({error}); run ./scripts/setup.sh again or install a Chromium-based "
    "browser.":
        "نافذة تسجيل الدخول غير متاحة ({error})؛ شغّل ./scripts/setup.sh مرة أخرى أو ثبّت متصفحًا "
        "مبنيًا على Chromium.",
    "The sign-in window is unavailable: {error}": "نافذة تسجيل الدخول غير متاحة: {error}",
    "Close Sign-in Window": "إغلاق نافذة تسجيل الدخول",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and run "
    "`blackboard-sync login` again.":
        "لم يبدأ المتصفح. إذا كانت نافذة تسجيل دخول من محاولة سابقة لا تزال مفتوحة، فأغلقها وشغّل "
        "`blackboard-sync login` مرة أخرى.",
    "Sign in to Blackboard in that window. It closes by itself once you are in.":
        "سجّل الدخول إلى Blackboard في تلك النافذة. ستُغلق تلقائيًا بعد دخولك.",
    "Could not find a supported browser (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, Opera GX, "
    "Chromium or Arc) on this computer.":
        "تعذّر العثور على متصفح مدعوم (Google Chrome أو Microsoft Edge أو Brave أو Vivaldi أو Opera أو "
        "Opera GX أو Chromium أو Arc) على هذا الحاسوب.",
    "Could not find {browser} on this computer.": "تعذّر العثور على {browser} على هذا الحاسوب.",
    "Signed in as {name}; session saved ({n} cookies).":
        "تم تسجيل الدخول باسم {name}؛ وحُفظت الجلسة ({n} من ملفات تعريف الارتباط).",
    "Opening {browser} on {url} ...": "جارٍ فتح {url} في {browser}...",
    "Opening the sign-in window on {url} ...": "جارٍ فتح نافذة تسجيل الدخول على {url}...",
    "The browser was closed before sign-in finished.": "أُغلق المتصفح قبل اكتمال تسجيل الدخول.",
    "The browser window was closed before sign-in finished.": "أُغلقت نافذة المتصفح قبل اكتمال تسجيل الدخول.",
    "Playwright is not installed; see the README's setup steps.":
        "Playwright غير مثبّت؛ راجع خطوات الإعداد في ملف README.",
    "Unknown browser {name}; use {choices}.": "متصفح غير معروف: {name}؛ استخدم أحد الخيارات التالية: {choices}.",
    "Could not open {browser}: {error}": "تعذّر فتح {browser}: {error}",
    "Using the app's own sign-in window instead.": "سيتم استخدام نافذة تسجيل الدخول الخاصة بالتطبيق بدلًا من ذلك.",
    "Could not connect to {browser}: {error}": "تعذّر الاتصال بـ {browser}: {error}",
    "Could not start the browser connection: {error}": "تعذّر بدء الاتصال بالمتصفح: {error}",
    "You are not signed in yet.": "لم تسجّل الدخول بعد.",
    "The saved session could not be read.": "تعذّرت قراءة الجلسة المحفوظة.",
    "The saved session belongs to {url}.": "الجلسة المحفوظة تخص {url}.",
    "Some sign-in data could not be removed; close the sign-in browser if it is still open and sign out again.":
        "تعذّرت إزالة بعض بيانات تسجيل الدخول؛ أغلق متصفح تسجيل الدخول إن كان لا يزال مفتوحًا، ثم سجّل الخروج مرة أخرى.",

    # macOS menus
    "Edit": "تحرير",
    "Window": "نافذة",
    "Hide Blackboard Sync": "إخفاء Blackboard Sync",
    "Hide Others": "إخفاء الآخرين",
    "Show All": "إظهار الكل",
    "Quit Blackboard Sync": "إنهاء Blackboard Sync",
    "Undo": "تراجع",
    "Redo": "إعادة",
    "Cut": "قص",
    "Copy": "نسخ",
    "Paste": "لصق",
    "Select All": "تحديد الكل",
    "Minimize": "تصغير",
    "Close": "إغلاق",

    # The menu bar / tray app
    "Blackboard Sync": "Blackboard Sync",
    "Blackboard Sync: syncing": "Blackboard Sync: جارٍ المزامنة",
    "Blackboard Sync: session expired": "Blackboard Sync: انتهت الجلسة",
    "Blackboard Sync: error": "Blackboard Sync: خطأ",
    "Blackboard Sync: paused": "Blackboard Sync: متوقف مؤقتًا",
    "Blackboard Sync {version} downloaded": "تم تنزيل Blackboard Sync {version}",
    "In the window that opened, drag “Blackboard Sync” onto the “Applications” folder and choose “Replace” to "
    "put it in place of the old version. Quit Blackboard Sync first, then open the app again from the "
    "Applications folder. Your settings and downloaded course files are kept.":
        "في النافذة التي فُتحت، اسحب “Blackboard Sync” إلى مجلد “التطبيقات” (Applications) واختر “استبدال” "
        "ليحل محل الإصدار القديم. أنهِ Blackboard Sync أولًا، ثم افتح التطبيق مرة أخرى من مجلد التطبيقات. "
        "ستبقى إعداداتك وملفات المقررات التي نزّلتها كما هي.",
    "File not found.": "الملف غير موجود.",
    "Could not install the update.": "تعذّر تثبيت التحديث.",
    "Could not install the update": "تعذّر تثبيت التحديث",
    "Could not change the start-at-login setting.": "تعذّر تغيير إعداد التشغيل عند تسجيل الدخول.",
    "Could not restart Blackboard Sync; quit it and open it again.":
        "تعذّرت إعادة تشغيل Blackboard Sync؛ أنهِه ثم افتحه مرة أخرى.",
    "Sign out?": "تسجيل الخروج؟",
    "All sign-in data is removed; you will need to enter your school details again to sign in. Your downloaded "
    "files are kept.":
        "ستُزال جميع بيانات تسجيل الدخول، وستحتاج إلى إدخال بيانات جامعتك مرة أخرى لتسجيل الدخول. "
        "ستبقى ملفاتك التي نزّلتها.",
    "Could not sign out.": "تعذّر تسجيل الخروج.",
    "The update cannot be installed now": "لا يمكن تثبيت التحديث الآن",
    "Later": "لاحقًا",
    "The {folder} folder does not exist yet; sync first.": "المجلد {folder} غير موجود بعد؛ زامِن أولًا.",
    "Sign out": "تسجيل الخروج",
    "Cancel": "إلغاء",
    "Could not save the update: {error}": "تعذّر حفظ التحديث: {error}",
    "Could not save the course choice: {error}": "تعذّر حفظ اختيار المقررات: {error}",
    "Could not save the settings: {error}": "تعذّر حفظ الإعدادات: {error}",
    "timed out": "انتهت المهلة",
    "Upcoming deadlines": "مواعيد التسليم القادمة",
    "The sync took too long and was stopped.": "استغرقت المزامنة وقتًا طويلًا فتم إيقافها.",
    "exit status {code}": "رمز الخروج {code}",
    "Could not start the menu bar app: {error}": "تعذّر تشغيل تطبيق شريط القوائم: {error}",
    "Blackboard Sync is running in the background": "Blackboard Sync يعمل في الخلفية",
    "Right-click the Blackboard Sync icon next to the clock for the menu. If you don't see it, click the ^ "
    "arrow that shows hidden icons.":
        "انقر بزر الماوس الأيمن على أيقونة Blackboard Sync بجوار الساعة لفتح القائمة. إن لم تظهر، "
        "انقر على السهم ^ الذي يعرض الأيقونات المخفية.",
    "Wait for the running job to finish before updating, then try again.":
        "انتظر حتى تنتهي العملية الجارية قبل التحديث، ثم حاول مرة أخرى.",
    "Could not open the announcement.": "تعذّر فتح الإعلان.",
    "The file or folder does not exist yet; sync first.": "الملف أو المجلد غير موجود بعد؛ زامِن أولًا.",
    "Could not open the file or folder.": "تعذّر فتح الملف أو المجلد.",
    "Blackboard Sync stopped because of an unexpected error.": "توقف Blackboard Sync بسبب خطأ غير متوقع.",
    "The details are in this file:\n{path}": "التفاصيل في هذا الملف:\n{path}",

    # The main window
    "Applications or Launchpad": "مجلد التطبيقات أو Launchpad",
    "the Start menu": "قائمة ابدأ",
    "Uninstall": "إزالة التثبيت",
    "The folder whose files go to the Trash:": "المجلد الذي ستُنقل ملفاته إلى سلة المهملات:",
    "The folder whose files go to the Recycle Bin:": "المجلد الذي ستُنقل ملفاته إلى سلة المحذوفات:",
    "Open the downloaded note": "فتح الملاحظة المنزّلة",
    "Open in Blackboard": "فتح في Blackboard",
    "Get started": "البدء",
    "Home": "الرئيسية",
    "Sync activity": "نشاط المزامنة",
    "Settings": "الإعدادات",
    "Your course files start here.": "ملفات مقرراتك تبدأ من هنا.",
    "Connect your Blackboard account and your course files come to this computer by themselves; no more "
    "checking the site every time.":
        "اربط حسابك في Blackboard وستصل ملفات مقرراتك إلى هذا الحاسوب تلقائيًا؛ لا حاجة بعد الآن "
        "لتفقد الموقع في كل مرة.",
    "Let's get started": "لنبدأ",
    "Open folder": "فتح المجلد",
    "NEW": "جديد",
    "Update": "تحديث",
    "Update to get the latest version.": "حدّث التطبيق للحصول على أحدث إصدار.",
    "Syncing": "جارٍ المزامنة",
    "Session expired": "انتهت الجلسة",
    "Not signed in": "غير مسجّل الدخول",
    "Waiting for sign-in": "بانتظار تسجيل الدخول",
    "Not synced yet": "لم تتم المزامنة بعد",
    "Downloading your files for the first time…": "جارٍ تنزيل ملفاتك للمرة الأولى…",
    "Unsaved changes": "تغييرات غير محفوظة",
    "View all": "عرض الكل",
    "Open": "فتح",
    "Show in folder": "إظهار في المجلد",
    "Recent downloads": "آخر التنزيلات",
    "Open calendar": "فتح التقويم",
    "No upcoming deadlines.": "لا توجد مواعيد تسليم قادمة.",
    "Nothing downloaded yet.": "لم يُنزَّل شيء بعد.",
    "Pause": "إيقاف مؤقت",
    "Up to date": "محدَّث",
    "Syncing…": "جارٍ المزامنة…",
    "Paused": "متوقف مؤقتًا",
    "Sign-in needed": "يلزم تسجيل الدخول",
    "Sync did not finish": "لم تكتمل المزامنة",
    "Sync did not finish: {error}": "لم تكتمل المزامنة: {error}",
    "Name": "الاسم",
    "File size": "حجم الملف",
    "Status": "الحالة",
    "Good morning": "صباح الخير",
    "Good afternoon": "طاب يومك",
    "Good evening": "مساء الخير",
    "{greeting}, {name}": "{greeting}، {name}",
    "No deadlines this week": "لا مواعيد تسليم هذا الأسبوع",
    "{n} deadline this week": "{n} موعد تسليم هذا الأسبوع",
    "{n} deadlines this week": "{n} مواعيد تسليم هذا الأسبوع",
    "{n} deadline today": "{n} موعد تسليم اليوم",
    "{n} deadlines today": "{n} مواعيد تسليم اليوم",
    "{n} this week": "{n} هذا الأسبوع",
    "Choose your school and folder": "اختر جامعتك والمجلد",
    "You decide where the files are saved.": "أنت تحدد مكان حفظ الملفات.",
    "Sign in to Blackboard": "سجّل الدخول إلى Blackboard",
    "Your school's sign-in page opens. The first sync starts after you sign in.":
        "ستُفتح صفحة تسجيل الدخول في جامعتك. تبدأ أول مزامنة بعد تسجيل دخولك.",
    "Your files stay up to date": "ملفاتك تبقى محدَّثة",
    "Every hour by default. You can change how often in Settings.":
        "كل ساعة افتراضيًا. يمكنك تغيير عدد المرات من الإعدادات.",
    "You can close this window. To see it again, open Blackboard Sync from {where}.":
        "يمكنك إغلاق هذه النافذة. لعرضها مرة أخرى، افتح Blackboard Sync من {where}.",
    "Last synced: {time}": "آخر مزامنة: {time}",
    "Last attempt: {time}": "آخر محاولة: {time}",
    "Downloading…": "جارٍ التنزيل…",
    "Blackboard Sync {version} is ready": "Blackboard Sync {version} جاهز",
    "Your internet connection seems unstable": "يبدو أن اتصالك بالإنترنت غير مستقر",
    "syncing": "تتم المزامنة",
    "not syncing": "لا تتم المزامنة",

    # The menu and the app's state
    "Sync now": "زامِن الآن",
    "Sign in": "تسجيل الدخول",
    "Waiting for sign-in…": "بانتظار تسجيل الدخول…",
    "⚠ Session expired — Sign in": "⚠ انتهت الجلسة — سجّل الدخول",
    "Nothing new yet": "لا جديد بعد",
    "Pause syncing": "إيقاف المزامنة مؤقتًا",
    "Resume syncing": "استئناف المزامنة",
    "Settings…": "الإعدادات…",
    "Quit": "إنهاء",
    "automatic sync off": "المزامنة التلقائية متوقفة",
    "Check now": "تحقق الآن",
    "Checking for updates…": "جارٍ البحث عن تحديثات…",
    "Downloading update…": "جارٍ تنزيل التحديث…",
    "Successfully downloaded": "تم التنزيل بنجاح",
    "Updated": "تم التحديث",
    "Note saved": "تم حفظ الملاحظة",
    "Note updated": "تم تحديث الملاحظة",
    "Announcement saved": "تم حفظ الإعلان",
    "Announcement updated": "تم تحديث الإعلان",
    "Waiting for you to sign in in the browser…": "بانتظار تسجيل دخولك في المتصفح…",
    "Waiting for you to sign in in the window that opened…": "بانتظار تسجيل دخولك في النافذة التي فُتحت…",
    "Waiting for you to sign in in {browser}…": "بانتظار تسجيل دخولك في {browser}…",
    "new file": "ملف جديد",
    "new files": "ملفات جديدة",
    "updated file": "ملف محدَّث",
    "updated files": "ملفات محدَّثة",
    "new note": "ملاحظة جديدة",
    "new notes": "ملاحظات جديدة",
    "updated note": "ملاحظة محدَّثة",
    "updated notes": "ملاحظات محدَّثة",
    "new announcement": "إعلان جديد",
    "new announcements": "إعلانات جديدة",
    "updated announcement": "إعلان محدَّث",
    "updated announcements": "إعلانات محدَّثة",
    "large file not downloaded": "ملف كبير لم يُنزَّل",
    "large files not downloaded": "ملفات كبيرة لم تُنزَّل",
    "nothing new": "لا جديد",
    "{n} file": "{n} ملف",
    "{n} files": "{n} ملفات",
    "{n} warning": "{n} تنبيه",
    "{n} file could not be downloaded": "تعذّر تنزيل {n} ملف",
    "{n} files could not be downloaded": "تعذّر تنزيل {n} ملفات",
    "{n} course could not be read": "تعذّرت قراءة {n} مقرر",
    "{n} courses could not be read": "تعذّرت قراءة {n} مقررات",
    "Something went wrong during the last sync": "حدثت مشكلة أثناء آخر مزامنة",
    "{n} warnings": "{n} تنبيهات",
    "({n} new)": "({n} جديد)",
    "No files were moved.": "لم يُنقل أي ملف.",
    "{files} moved to the new folder.": "نُقلت {files} إلى المجلد الجديد.",
    "{files} moved to the {folder} folder.": "نُقلت {files} إلى المجلد {folder}.",
    "{files} could not be moved and stayed in the old folder.": "تعذّر نقل {files} وبقيت في المجلد القديم.",
    "{files} could not be moved and stayed where they were.": "تعذّر نقل {files} وبقيت في مكانها.",
    "Open {folder} folder": "فتح المجلد {folder}",
    "Blackboard: new content": "Blackboard: محتوى جديد",
    "Click to download the new version.": "انقر لتنزيل الإصدار الجديد.",
    "Blackboard session expired": "انتهت جلسة Blackboard",
    "Choose “Sign in” in the menu to get new files.": "اختر “تسجيل الدخول” من القائمة لجلب الملفات الجديدة.",
    "Some files could not be moved": "تعذّر نقل بعض الملفات",
    "Another sync is running; trying again shortly.": "توجد مزامنة أخرى قيد التشغيل؛ ستتم المحاولة مجددًا بعد قليل.",
    "Another sync is running; the files will be moved shortly.":
        "توجد مزامنة أخرى قيد التشغيل؛ ستُنقل الملفات بعد قليل.",
    "Sign in for the new school.": "سجّل الدخول إلى الجامعة الجديدة.",
    "not synced yet": "لم تتم المزامنة بعد",
    "synced at {time}": "آخر مزامنة: {time}",
    "tried at {time}": "آخر محاولة: {time}",
    "tried at {time} · error": "آخر محاولة: {time} · خطأ",
    "next: {time}": "التالية: {time}",
    "soon": "قريبًا",
    "Checking for new content…": "جارٍ البحث عن محتوى جديد…",
    "Moving files to the new folder…": "جارٍ نقل الملفات إلى المجلد الجديد…",
    "Moving files to the {folder} folder…": "جارٍ نقل الملفات إلى المجلد {folder}…",
    "Choose “{settings}” to finish setting up": "اختر “{settings}” لإكمال الإعداد",
    "Blackboard Sync {version} is ready — Update": "Blackboard Sync {version} جاهز — تحديث",
    "Blackboard Sync is up to date": "Blackboard Sync محدَّث",
    "You have the latest version ({version}).": "لديك أحدث إصدار ({version}).",
    "Your settings and downloaded course files were kept.": "تم الاحتفاظ بإعداداتك وملفات المقررات التي نزّلتها.",
    "Files moved": "تم نقل الملفات",
    "Files moved to the {folder} folder": "تم نقل الملفات إلى المجلد {folder}",
    "Could not check for updates": "تعذّر البحث عن تحديثات",
    "Check your internet connection and try again later.":
        "تحقق من اتصالك بالإنترنت وحاول مرة أخرى لاحقًا.",
    "Blackboard Sync {version} could not be put in place; version {current} is still in use.":
        "تعذّر تثبيت Blackboard Sync {version}؛ لا يزال الإصدار {current} قيد الاستخدام.",
    "Blackboard Sync was updated to {version}": "تم تحديث Blackboard Sync إلى {version}",
    "Update available: {version} — Update": "يتوفر تحديث: {version} — تحديث",
    "Could not move the files: {error}": "تعذّر نقل الملفات: {error}",
    "Sign-in did not finish: {error}": "لم يكتمل تسجيل الدخول: {error}",
    "No courses yet": "لا توجد مقررات بعد",
    "Blackboard: no courses found": "Blackboard: لم يُعثر على مقررات",
    "no courses found": "لم يُعثر على مقررات",

    # Settings
    "Automatic sync": "المزامنة التلقائية",
    "Every 30 minutes": "كل 30 دقيقة",
    "Every hour": "كل ساعة",
    "Every 3 hours": "كل 3 ساعات",
    "Only manually": "يدويًا فقط",
    "Language": "اللغة",
    "Danger zone": "منطقة الخطر",
    "How often Blackboard is checked for new files.": "عدد مرات البحث عن ملفات جديدة في Blackboard.",
    "Keeps syncing in the background after you sign in to the computer.":
        "يواصل المزامنة في الخلفية بعد تسجيل دخولك إلى الحاسوب.",
    "Looks for a new version once a day.": "يبحث عن إصدار جديد مرة واحدة يوميًا.",
    "Uninstall Blackboard Sync": "إزالة Blackboard Sync",
    "Restart Blackboard Sync to change the language?": "إعادة تشغيل Blackboard Sync لتغيير اللغة؟",
    "The new language is used once the app starts again.": "ستُستخدم اللغة الجديدة عند إعادة تشغيل التطبيق.",
    "Restart now": "إعادة التشغيل الآن",
    "Account": "الحساب",
    "Folder": "المجلد",
    "Sync": "المزامنة",
    "Updates": "التحديثات",
    "Your school's Blackboard address": "عنوان Blackboard لجامعتك",
    "School name or https://blackboard.school.edu": "اسم الجامعة أو https://blackboard.uni.edu.sa",
    "If you change the address you need to sign in again for the new school.":
        "إذا غيّرت العنوان فستحتاج إلى تسجيل الدخول مرة أخرى للجامعة الجديدة.",
    "Folder to save files in": "مجلد حفظ الملفات",
    "Files are saved in the University folder inside the folder you choose.":
        "تُحفظ الملفات في مجلد University داخل المجلد الذي تختاره.",
    "If you change the folder you can move the downloaded files to the new one or download them again.":
        "إذا غيّرت المجلد يمكنك نقل الملفات المنزّلة إلى المجلد الجديد أو تنزيلها مرة أخرى.",
    "Start when the computer starts": "التشغيل عند بدء تشغيل الحاسوب",
    "Check for updates automatically": "البحث عن التحديثات تلقائيًا",
    "Automatic re-sign-in": "إعادة تسجيل الدخول تلقائيًا",
    "Keeps your session alive and signs in again in the background when your school allows it. Your password is never stored.":
        "يُبقي جلستك نشطة ويعيد تسجيل الدخول في الخلفية عندما تسمح جامعتك بذلك. لا تُحفظ كلمة المرور أبدًا.",
    "Session refreshed automatically": "تم تجديد الجلسة تلقائيًا",
    "Could not refresh the session without you: {reason}": "تعذّر تجديد الجلسة دون تدخلك: {reason}",
    "Another sign-in is in progress; try again in a minute.": "توجد عملية تسجيل دخول أخرى قيد التنفيذ؛ حاول مرة أخرى بعد دقيقة.",
    "Choose…": "اختيار…",
    "Use this folder": "استخدام هذا المجلد",
    "Choose the folder to save your course files in.": "اختر المجلد الذي ستُحفظ فيه ملفات مقرراتك.",
    "Save": "حفظ",
    "Wait for the running job to finish first.": "انتظر حتى تنتهي العملية الجارية أولًا.",
    "The folder was not changed.": "لم يتغير المجلد.",
    "What should happen to the downloaded files?": "ماذا تريد أن تفعل بالملفات المنزّلة؟",
    "Move": "نقل",
    "Download again": "إعادة التنزيل",
    "“{folder}” holds {n} file downloaded from Blackboard.":
        "يحتوي “{folder}” على {n} ملف تم تنزيله من Blackboard.",
    "“{folder}” holds {n} files downloaded from Blackboard.":
        "يحتوي “{folder}” على {n} ملفات تم تنزيلها من Blackboard.",
    "{move}: the files are moved to “{folder}”, not downloaded again. Files you added yourself stay in the old "
    "folder.":
        "{move}: تُنقل الملفات إلى “{folder}” ولا يُعاد تنزيلها. تبقى الملفات التي أضفتها بنفسك في "
        "المجلد القديم.",
    "{redownload}: the files are downloaded again into the new folder; the old folder is not touched.":
        "{redownload}: يُعاد تنزيل الملفات في المجلد الجديد؛ ولا يُمَس المجلد القديم.",
    "Checking…": "جارٍ التحقق…",
    "Your session expired; sign in again.": "انتهت جلستك؛ سجّل الدخول مرة أخرى.",
    "Not signed in yet.": "لم تسجّل الدخول بعد.",
    "Version {version}": "الإصدار {version}",
    "Signed in as {name}": "مسجّل الدخول باسم {name}",
    "Update to {version}": "التحديث إلى {version}",
    "Enter a valid address, for example https://blackboard.school.edu":
        "أدخل عنوانًا صالحًا، مثل https://blackboard.university.edu.sa",
    "Enter your school's Blackboard address.": "أدخل عنوان Blackboard لجامعتك.",
    "The address must start with https://.": "يجب أن يبدأ العنوان بـ https://.",
    "Choose the folder to save the files in.": "اختر المجلد الذي ستُحفظ فيه الملفات.",
    "Enter the folder's full path, for example ~/Documents/University":
        "أدخل المسار الكامل للمجلد، مثل ~/Documents/University",
    "This path is not a folder.": "هذا المسار ليس مجلدًا.",

    # The sync report
    "Would sync {n} course(s) for {terms} into {folder}":
        "كانت ستتم مزامنة {n} من المقررات للفصل {terms} في {folder}",
    "Synced {n} course(s) for {terms} into {folder}": "تمت مزامنة {n} من المقررات للفصل {terms} في {folder}",
    "Nothing new.": "لا جديد.",
    "no changes": "لا تغييرات",
    "Moved {n} file(s) into {folder}": "تم نقل {n} من الملفات إلى {folder}",
    "{n} file(s) could not be moved and stayed where they were:": "تعذّر نقل {n} من الملفات وبقيت في مكانها:",
    "no term": "بلا فصل دراسي",
    "{n} course(s) had changes.": "حدثت تغييرات في {n} من المقررات.",

    # The sync
    "Could not read {name} ({error}); moved it to {saved} and continued with an empty state. Files already on "
    "disk that match Blackboard's copy are kept as they are, not duplicated.":
        "تعذّرت قراءة {name} ({error})؛ نُقل إلى {saved} واستمرت العملية بحالة فارغة. الملفات الموجودة "
        "على القرص والمطابقة لنسخة Blackboard تبقى كما هي ولا تُكرَّر.",
    "Could not read {name} ({error}); it would be set aside on a real sync.":
        "تعذّرت قراءة {name} ({error})؛ سيُنقل جانبًا عند مزامنة فعلية.",
    "Blackboard did not identify the signed-in user.": "لم يحدد Blackboard المستخدم المسجّل دخوله.",
    "Another blackboard-sync run is already in progress.": "يوجد تشغيل آخر لـ blackboard-sync قيد التنفيذ بالفعل.",
    "Kept folder {old}: could not rename it to {new} because that folder already exists. Move your files into "
    "one of them to finish.":
        "تم الإبقاء على المجلد {old}: تعذّرت إعادة تسميته إلى {new} لأن هذا المجلد موجود بالفعل. "
        "انقل ملفاتك إلى أحدهما لإتمام العملية.",
    "Kept folder {old}: could not rename it to {new} ({error}).":
        "تم الإبقاء على المجلد {old}: تعذّرت إعادة تسميته إلى {new} ({error}).",
    "Could not read course content: {error}": "تعذّرت قراءة محتوى المقرر: {error}",
    "Could not sync announcements: {error}": "تعذّرت مزامنة الإعلانات: {error}",
    "Could not read due dates: {error}": "تعذّرت قراءة مواعيد التسليم: {error}",
    "Could not read term {term}; using its id as folder name.":
        "تعذّرت قراءة الفصل الدراسي {term}؛ سيُستخدم معرّفه اسمًا للمجلد.",
    "Skipped course {course}: {error}": "تم تخطي المقرر {course}: {error}",
    "Could not open folder {name}: {error}": "تعذّر فتح المجلد {name}: {error}",
    "Skipped {name}: {error}": "تم تخطي {name}: {error}",

    # Uninstalling
    "Uninstall Blackboard Sync?": "إزالة Blackboard Sync؟",
    "Uninstall app…": "إزالة التطبيق…",
    "Also delete the downloaded course files": "حذف ملفات المقررات المنزّلة أيضًا",
    "The app and all of its records, logs, settings and sign-in data are removed, and so is its start-at-login "
    "entry. Downloaded course files are kept unless you tick this option.":
        "سيُزال التطبيق وجميع سجلاته وملفات السجل والإعدادات وبيانات تسجيل الدخول، وكذلك إدخال التشغيل "
        "عند تسجيل الدخول. تبقى ملفات المقررات المنزّلة ما لم تحدد هذا الخيار.",
    "Wait for the sync or the folder move to finish before uninstalling.":
        "انتظر حتى تنتهي المزامنة أو نقل المجلد قبل إزالة التثبيت.",
    "You can uninstall Blackboard Sync from Windows Settings → Apps.":
        "يمكنك إزالة Blackboard Sync من إعدادات Windows ← التطبيقات.",
    "Remove the app's files yourself.": "أزل ملفات التطبيق بنفسك.",
    "The download records could not be read; the course files were kept to be safe.":
        "تعذّرت قراءة سجلات التنزيل؛ تم الاحتفاظ بملفات المقررات احتياطًا.",
    "The app data folder contains the download folder or the home folder; uninstall cancelled.":
        "مجلد بيانات التطبيق يحتوي على مجلد التنزيل أو المجلد الرئيسي للمستخدم؛ تم إلغاء إزالة التثبيت.",
    "Quit Blackboard Sync first, or use Uninstall app… in its settings.":
        "أنهِ Blackboard Sync أولًا، أو استخدم “إزالة التطبيق…” في إعداداته.",
    "A lock file is a link; the app could not be removed safely.":
        "أحد ملفات القفل عبارة عن رابط؛ تعذّرت إزالة التطبيق بأمان.",
    "The uninstaller could not be started. Uninstall Blackboard Sync from Windows Settings → Apps; if needed, "
    "delete this folder yourself: {path}":
        "تعذّر تشغيل أداة إزالة التثبيت. أزل Blackboard Sync من إعدادات Windows ← التطبيقات؛ "
        "وإن لزم الأمر، احذف هذا المجلد بنفسك: {path}",
    "The app could not be removed; delete it yourself: {error}": "تعذّرت إزالة التطبيق؛ احذفه بنفسك: {error}",
    "Could not move an empty folder to the Trash: {path} ({error})":
        "تعذّر نقل مجلد فارغ إلى سلة المهملات: {path} ({error})",
    "Could not delete a lock file: {name} ({error})": "تعذّر حذف ملف القفل: {name} ({error})",
    "The app could not be moved to the Trash. Delete it in Finder yourself: {path}":
        "تعذّر نقل التطبيق إلى سلة المهملات. احذفه بنفسك من Finder: {path}",
    "Could not move a file to the Trash: {path} ({error})": "تعذّر نقل ملف إلى سلة المهملات: {path} ({error})",
    "Could not clear the sign-in data: {error}": "تعذّر مسح بيانات تسجيل الدخول: {error}",
    "Could not remove the start-at-login entry: {error}": "تعذّرت إزالة إدخال التشغيل عند تسجيل الدخول: {error}",
    "Could not clear the app data folder: {path} ({error})": "تعذّر مسح مجلد بيانات التطبيق: {path} ({error})",
    "Could not move the course files to the Trash: {error}": "تعذّر نقل ملفات المقررات إلى سلة المهملات: {error}",
    "Could not delete app data: {path}": "تعذّر حذف بيانات التطبيق: {path}",
    "The Recycle Bin API could not be loaded; the file was kept.":
        "تعذّر تحميل واجهة سلة المحذوفات البرمجية؛ تم الاحتفاظ بالملف.",
    "The file could not be moved to the Recycle Bin; it was kept.":
        "تعذّر نقل الملف إلى سلة المحذوفات؛ تم الاحتفاظ به.",
    "The file cannot be recycled; permanent deletion was cancelled.":
        "لا يمكن نقل الملف إلى سلة المحذوفات؛ تم إلغاء الحذف النهائي.",
    "The Recycle Bin operation failed: {error}": "فشلت عملية سلة المحذوفات: {error}",

    # Updates
    "The update cannot be installed while a sync or a folder move runs; try again once it has finished.":
        "لا يمكن تثبيت التحديث أثناء المزامنة أو نقل المجلد؛ حاول مرة أخرى بعد انتهائها.",
    "the current version is kept.": "تم الإبقاء على الإصدار الحالي.",
    "Blackboard Sync runs from its disk image, so it cannot update itself.":
        "يعمل Blackboard Sync من صورة القرص، لذا لا يمكنه تحديث نفسه.",
    "macOS runs Blackboard Sync from a temporary location, so the app cannot update itself.":
        "يشغّل macOS تطبيق Blackboard Sync من موقع مؤقت، لذا لا يمكن للتطبيق تحديث نفسه.",
    "The folder Blackboard Sync is in cannot be written to, so the app cannot update itself.":
        "لا يمكن الكتابة في المجلد الذي يوجد فيه Blackboard Sync، لذا لا يمكن للتطبيق تحديث نفسه.",
    "This version is unsigned, so the update cannot be verified and installed automatically.":
        "هذا الإصدار غير موقَّع، لذا لا يمكن التحقق من التحديث وتثبيته تلقائيًا.",
    "The update's disk image could not be opened;": "تعذّر فتح صورة القرص الخاصة بالتحديث؛",
    "Blackboard Sync was not found in the disk image;": "لم يُعثر على Blackboard Sync في صورة القرص؛",
    "The downloaded update is not the expected Blackboard Sync version;":
        "التحديث المنزّل ليس إصدار Blackboard Sync المتوقع؛",
    "The update's signature is not valid;": "توقيع التحديث غير صالح؛",
    "The update is not signed by the Blackboard Sync developer;":
        "التحديث غير موقَّع من مطوّر Blackboard Sync؛",
    "The update is not notarized by Apple;": "التحديث غير موثَّق من Apple (notarization)؛",
    "The new version could not be copied;": "تعذّر نسخ الإصدار الجديد؛",
    "The update could not be started;": "تعذّر بدء التحديث؛",
    "Updates are installed through the Microsoft Store.": "تُثبَّت التحديثات عبر Microsoft Store.",
    "The update could not be verified.": "تعذّر التحقق من التحديث.",
    "The update does not come from this app's page; it was not downloaded.":
        "التحديث لا يأتي من صفحة هذا التطبيق؛ لم يتم تنزيله.",
    "The downloaded update could not be verified; it was not installed.":
        "تعذّر التحقق من التحديث المنزّل؛ لم يتم تثبيته.",
    "The update could not be downloaded; check your internet connection.":
        "تعذّر تنزيل التحديث؛ تحقق من اتصالك بالإنترنت.",
    "The update could not be downloaded.": "تعذّر تنزيل التحديث.",
    "Google Calendar needs to be reconnected": "يجب إعادة ربط Google Calendar",
    "Google Calendar authorization state did not match.": "لم تتطابق حالة تفويض Google Calendar.",
    "Google Calendar authorization was cancelled.": "تم إلغاء تفويض Google Calendar.",
    "Google Calendar operation was cancelled.": "تم إلغاء عملية Google Calendar.",
    "Set BBSYNC_GOOGLE_CLIENT_ID to your Desktop OAuth client ID.": "اضبط BBSYNC_GOOGLE_CLIENT_ID على معرّف عميل OAuth لتطبيق سطح المكتب الخاص بك.",
    "A Google Calendar operation is already running.": "توجد عملية Google Calendar قيد التشغيل بالفعل.",
    "Could not access the Google Calendar credential store.": "تعذّر الوصول إلى مخزن بيانات اعتماد Google Calendar.",
    "Could not open the browser for Google Calendar.": "تعذّر فتح المتصفح لـ Google Calendar.",
    "The saved Google Calendar is not a dedicated secondary calendar.": "تقويم Google Calendar المحفوظ ليس تقويمًا ثانويًا مخصصًا.",
    "Sync Blackboard successfully before syncing Google Calendar.": "أكمل مزامنة Blackboard بنجاح قبل مزامنة Google Calendar.",
    "Google Calendar sync failed.": "فشلت مزامنة Google Calendar.",
    "Could not reach Google Calendar.": "تعذّر الوصول إلى Google Calendar.",
    "Google Calendar authorization timed out.": "انتهت مهلة تفويض Google Calendar.",
    "You can close this browser window and return to Blackboard Sync.": "يمكنك إغلاق نافذة المتصفح هذه والعودة إلى Blackboard Sync.",
    "This event is managed by Blackboard Sync.": "يُدار هذا الحدث بواسطة Blackboard Sync.",
    "Google Calendar operation failed.": "فشلت عملية Google Calendar.",
    "Disconnect Google Calendar?": "قطع الاتصال بـ Google Calendar؟",
    "Access will be revoked and local Calendar connection data removed.": "سيُلغى الوصول وتُحذف بيانات اتصال التقويم المحلية.",
    "Disconnect": "قطع الاتصال",
    "Also delete the Blackboard Deadlines calendar from Google": "حذف تقويم Blackboard Deadlines من Google أيضًا",
    "Reconnect": "إعادة الربط",
    "Google Calendar error": "خطأ في Google Calendar",
    "Not connected": "غير متصل",
    "Connect to see Blackboard deadlines in Google Calendar.": "اربط الحساب لعرض مواعيد التسليم في Blackboard على Google Calendar.",
    "Connect Google Calendar": "ربط Google Calendar",
    "Google Calendar operation in progress…": "جارٍ تنفيذ عملية Google Calendar…",
    "You can cancel while authorization is waiting in the browser.": "يمكنك الإلغاء أثناء انتظار التفويض في المتصفح.",
    "Connected": "متصل",
    "Google Calendar": "Google Calendar",
    "Calendar has not synced yet.": "لم تتم مزامنة التقويم بعد.",
    "Sends deadlines to a dedicated Blackboard Deadlines calendar. Your other calendars stay private.": "يرسل مواعيد التسليم إلى تقويم مخصص باسم Blackboard Deadlines. تبقى تقاويمك الأخرى خاصة.",
    "Sync calendar now": "زامِن التقويم الآن",
    "Disconnect Google Calendar": "قطع الاتصال بـ Google Calendar",
    "Last calendar sync: {time}": "آخر مزامنة للتقويم: {time}",
    "Google Calendar returned an invalid response.": "أعاد Google Calendar استجابة غير صالحة.",
    "Google requires this Desktop client's secret. Set BBSYNC_GOOGLE_CLIENT_SECRET locally and connect again.": "يطلب Google القيمة السرية لعميل سطح المكتب هذا. اضبط BBSYNC_GOOGLE_CLIENT_SECRET محليًا ثم أعد الربط.",
    "The calendar's saved ID is missing. Delete the existing Blackboard Deadlines calendar in Google Calendar settings.": "المعرّف المحفوظ للتقويم مفقود. احذف تقويم Blackboard Deadlines الحالي من إعدادات Google Calendar.",
    "Please wait for the calendar operation to finish.": "يُرجى الانتظار حتى تنتهي عملية التقويم.",
    # Settings → Appearance (the Windows window)
    "Appearance": "المظهر",
    "Theme": "السمة",
    "System follows the light or dark mode chosen in Windows.": "خيار “النظام” يتبع الوضع الفاتح أو الداكن المحدد في Windows.",
    "System": "النظام",
    "Light": "فاتح",
    "Dark": "داكن",

    # Settings → AI assistant (ai_launcher)
    "AI assistant": "مساعد الذكاء الاصطناعي",
    "Continue my last session in this folder": "متابعة آخر جلسة لي في هذا المجلد",
    "When it is off, a new session starts every time.": "عند إيقافه، تبدأ جلسة جديدة في كل مرة.",
    "The app only opens a terminal in your course folder. The AI tool runs with your own account and its own "
    "rules.":
        "يفتح التطبيق نافذة طرفية في مجلد مقرراتك فقط. تعمل أداة الذكاء الاصطناعي بحسابك الخاص "
        "ووفق قواعدها الخاصة.",
    "No earlier session here, starting a new one.": "لا توجد جلسة سابقة هنا، جارٍ بدء جلسة جديدة.",
    "AI study session": "المذاكرة بالذكاء الاصطناعي",
    "Click a tool to open {term}, continuing your last session there.":
        "انقر على أداة لفتح {term} ومتابعة آخر جلسة لك هناك.",
    "Click a tool to open {term} in a new session.":
        "انقر على أداة لفتح {term} في جلسة جديدة.",
    "Looking for AI tools…": "جارٍ البحث عن أدوات الذكاء الاصطناعي…",
    "Terminal": "الطرفية",
    "The terminal app that opens for AI tools.": "تطبيق الطرفية الذي يُفتح لأدوات الذكاء الاصطناعي.",
    "Command Prompt": "موجه الأوامر",
    "No AI tool is installed. Install Claude Code, Gemini CLI, Codex or Antigravity, then try again.":
        "لا توجد أداة ذكاء اصطناعي مثبّتة. ثبّت Claude Code أو Gemini CLI أو Codex أو Antigravity، ثم حاول مرة أخرى.",
    "{name} wasn't found. Using {default} instead.": "لم يُعثر على {name}. سيُستخدم {default} بدلًا منه.",
    "Open in {name}": "فتح في {name}",
    "Opening…": "جارٍ الفتح…",
    "{name} is not installed. Install it, then try again.": "{name} غير مثبّت. ثبّته ثم حاول مرة أخرى.",
    "How to install": "طريقة التثبيت",
    "Try again": "إعادة المحاولة",
    "The {term} folder isn't there yet. Sync first.": "المجلد {term} غير موجود بعد. زامِن أولًا.",
    "Could not open a terminal: {error}": "تعذّر فتح الطرفية: {error}",
    "Could not open a terminal.": "تعذّر فتح الطرفية.",
    "Open {name} in {term}": "فتح {name} في {term}",

    # NotebookLM
    "Sign in to Google again to keep adding files.": "سجّل الدخول إلى Google مرة أخرى لمواصلة إضافة الملفات.",
    "Disconnect Gemini Notebook?": "قطع الاتصال بـ Gemini Notebook؟",
    "The Google session is deleted from this computer. Files already in Gemini Notebook stay there, and new ones "
    "are no longer added.":
        "ستُحذف جلسة Google من هذا الحاسوب. تبقى الملفات الموجودة في Gemini Notebook هناك، "
        "ولن تُضاف ملفات جديدة بعد الآن.",
    "Connect Gemini Notebook": "ربط Gemini Notebook",
    "Your course files are added after each sync.": "تُضاف ملفات مقرراتك بعد كل مزامنة.",
    "Checking what is already in Gemini Notebook…": "جارٍ التحقق مما هو موجود في Gemini Notebook…",
    "Sign in to Google in the browser window.": "سجّل الدخول إلى Google في نافذة المتصفح.",
    "Adding {done} of {total}: {file}": "جارٍ إضافة {done} من {total}: {file}",
    "Gemini Notebook is reading the new files…": "يقرأ Gemini Notebook الملفات الجديدة…",
    "Checking the connection…": "جارٍ التحقق من الاتصال…",
    "Google took the sign-in, but Gemini Notebook did not open. Try again.":
        "قبل Google تسجيل الدخول، لكن Gemini Notebook لم يُفتح. حاول مرة أخرى.",
    "{n} new file added to your notebooks": "تمت إضافة {n} ملف جديد إلى دفاترك",
    "{n} new files added to your notebooks": "تمت إضافة {n} ملفات جديدة إلى دفاترك",
    "No new files were added": "لم تُضَف ملفات جديدة",
    "Last checked: {time}": "آخر تحقق: {time}",
    "{n} course blocked": "{n} مقرر محظور",
    "{n} courses blocked": "{n} مقررات محظورة",
    "{n} failed": "{n} فشلت",
    "Add new files to Gemini Notebook after each sync": "إضافة الملفات الجديدة إلى Gemini Notebook بعد كل مزامنة",
    "Disconnect Gemini Notebook": "قطع الاتصال بـ Gemini Notebook",
    "Files in Gemini Notebook stay there.": "تبقى الملفات الموجودة في Gemini Notebook هناك.",
    "Unofficial connection: it may stop working if Google changes Gemini Notebook.":
        "اتصال غير رسمي: قد يتوقف عن العمل إذا غيّرت Google خدمة Gemini Notebook.",
    "{course}: {n} over the {limit} source limit; nothing added.":
        "{course}: تجاوز الحد البالغ {limit} مصدرًا بمقدار {n}؛ لم تتم إضافة أي شيء.",
    "{course}: several notebooks have this name, so it was skipped.":
        "{course}: توجد عدة دفاتر بهذا الاسم، لذا تم تخطيه.",
    "{n} file could not be added; the next sync tries again.":
        "تعذّرت إضافة {n} ملف؛ ستعيد المزامنة التالية المحاولة.",
    "{n} files could not be added; the next sync tries again.":
        "تعذّرت إضافة {n} ملفات؛ ستعيد المزامنة التالية المحاولة.",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and try again.":
        "لم يبدأ المتصفح. إذا كانت نافذة تسجيل دخول من محاولة سابقة لا تزال مفتوحة، فأغلقها وحاول مرة أخرى.",
    "Gemini Notebook needs Chrome, Edge or Brave to sign in to Google; install one and try again.":
        "يحتاج Gemini Notebook إلى Chrome أو Edge أو Brave لتسجيل الدخول إلى Google؛ "
        "ثبّت أحدها وحاول مرة أخرى.",

    # NotebookLM: files that may be there already
    "{n} file may already be in Gemini Notebook, so it was not added.":
        "قد يكون {n} ملف موجودًا بالفعل في Gemini Notebook، لذا لم تتم إضافته.",
    "{n} files may already be in Gemini Notebook, so they were not added.":
        "قد تكون {n} ملفات موجودة بالفعل في Gemini Notebook، لذا لم تتم إضافتها.",
    "{n} held back": "{n} مؤجَّلة",

    # Store trial and purchase (licensing)
    "Purchases are not available in this build.": "عمليات الشراء غير متاحة في هذا الإصدار.",
    "Could not reach the Microsoft Store. Check your internet connection and try again.":
        "تعذّر الوصول إلى Microsoft Store. تحقّق من اتصالك بالإنترنت وحاول مرة أخرى.",
    "Could not complete the purchase in the Microsoft Store. Try again in a moment.":
        "تعذّر إتمام الشراء في Microsoft Store. حاول مرة أخرى بعد قليل.",
    "No purchase was found for this account yet.": "لم يُعثر على عملية شراء لهذا الحساب بعد.",
    "Free trial ended": "انتهت الفترة التجريبية المجانية",
    "{n} minute left": "{n} دقيقة متبقية",
    "{n} minutes left": "{n} دقائق متبقية",
    "{n} hour left": "{n} ساعة متبقية",
    "{n} hours left": "{n} ساعات متبقية",
    "{n} day left": "{n} يوم متبقٍّ",
    "{n} days left": "{n} أيام متبقية",
    "Free trial · {remaining}": "فترة تجريبية مجانية · {remaining}",
    "Free trial": "فترة تجريبية مجانية",
    "Buy": "شراء",
    "Buy for {price}": "شراء مقابل {price}",
    "Opening Store…": "جارٍ فتح المتجر…",
    "Your free trial has ended": "انتهت فترتك التجريبية المجانية",
    "Buy Blackboard Sync once ({price}) to keep syncing your courses. Your downloaded files are still in your folder.":
        "اشترِ Blackboard Sync مرة واحدة ({price}) لمواصلة مزامنة مقرراتك. "
        "ملفاتك المحمّلة لا تزال في مجلدك.",
    "Buy Blackboard Sync once to keep syncing your courses. Your downloaded files are still in your folder.":
        "اشترِ Blackboard Sync مرة واحدة لمواصلة مزامنة مقرراتك. "
        "ملفاتك المحمّلة لا تزال في مجلدك.",
    "I already bought it": "اشتريته بالفعل",

    # Mac App Store (App Sandbox, folder bookmark, copy-command, demo mode)
    "Choose a folder…": "اختر مجلدًا…",
    "Choose the folder using “Choose…” so macOS grants access to it.":
        "اختر المجلد باستخدام “اختيار…” حتى يمنح macOS إذن الوصول إليه.",
    "Click a tool to copy the terminal command for {term}.":
        "انقر على أداة لنسخ أمر الطرفية الخاص بـ {term}.",
    "Copied terminal command for {name} — paste it into Terminal.":
        "تم نسخ أمر الطرفية لـ {name} — الصقه في الطرفية.",
    "Copy command for {name}": "نسخ الأمر لـ {name}",
    "Copy {name} command for {term}": "نسخ أمر {name} لـ {term}",
    "Could not copy the command.": "تعذّر نسخ الأمر.",
    "Gemini Notebook sign-in is not available in the Mac App Store version.":
        "تسجيل الدخول إلى Gemini Notebook غير متاح في إصدار Mac App Store.",
    "Try the demo": "جرّب الوضع التجريبي",
    "Updates are installed through the App Store.": "تُثبَّت التحديثات عبر App Store.",
    "You can uninstall Blackboard Sync from Launchpad or the Applications folder.":
        "يمكنك إزالة تثبيت Blackboard Sync من Launchpad أو من مجلد التطبيقات.",

    # Minimum-version enforcement (min_version)
    "Update required": "التحديث مطلوب",
    "Update required — Update": "التحديث مطلوب — تحديث",
    "Updating…": "جارٍ التحديث…",
    "Update Blackboard Sync to version {version} or newer to keep syncing your courses. Your downloaded files are still in your folder.":
        "حدِّث Blackboard Sync إلى الإصدار {version} أو أحدث لمواصلة مزامنة مقرراتك. "
        "ملفاتك المحمّلة لا تزال في مجلدك.",
    "Update Blackboard Sync to the latest version to keep syncing your courses. Your downloaded files are still in your folder.":
        "حدِّث Blackboard Sync إلى أحدث إصدار لمواصلة مزامنة مقرراتك. "
        "ملفاتك المحمّلة لا تزال في مجلدك.",
    "Blackboard Sync moved to the Mac App Store": "انتقل Blackboard Sync إلى Mac App Store",
    "Get Blackboard Sync from the Mac App Store to keep syncing your courses. Your downloaded files are still in your folder.":
        "احصل على Blackboard Sync من Mac App Store لمواصلة مزامنة مقرراتك. "
        "ملفاتك المحمّلة لا تزال في مجلدك.",
    "Open Mac App Store": "فتح Mac App Store",
    "Could not open the Mac App Store.": "تعذّر فتح Mac App Store.",
}
