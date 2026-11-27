"""German for every text the app shows: English text -> German text.

The keys are the exact strings passed to ``i18n.tr`` / ``ntr`` in the code;
``tests/test_i18n.py`` checks that each one is here with the same ``{fields}``.
German has a singular and a plural; ``ntr`` picks the one-form only for a count
of 1, so "1 Datei" but "0 Dateien" and "2 Dateien".
"""

CATALOG = {
    # Announcements
    "Announcements": "Ankündigungen",
    "Every announcement synced from your current-term courses.":
        "Alle Ankündigungen aus deinen Kursen im aktuellen Semester.",
    "No announcements yet. They show up here once they are synced.":
        "Noch keine Ankündigungen. Sie erscheinen hier, sobald sie synchronisiert sind.",
    "No date given": "Kein Datum angegeben",
    "Open announcement": "Ankündigung öffnen",
    "Announcement": "Ankündigung",

    # Blackboard and the command line
    "Your Blackboard session has expired.": "Deine Blackboard-Sitzung ist abgelaufen.",
    "Blackboard redirected to a sign-in page.": "Blackboard hat auf eine Anmeldeseite weitergeleitet.",
    "Blackboard answered with a web page instead of data.": "Blackboard hat statt Daten eine Webseite geliefert.",
    "Blackboard answered a download with a web page.": "Blackboard hat auf einen Download mit einer Webseite geantwortet.",
    "Next: run `blackboard-sync sync` to download your courses.":
        "Als Nächstes: Führe `blackboard-sync sync` aus, um deine Kurse herunterzuladen.",
    "Blackboard Sync's app data was removed.": "Die App-Daten von Blackboard Sync wurden entfernt.",
    "Session OK: signed in as {name}.": "Sitzung OK: angemeldet als {name}.",
    "Term(s): {terms}": "Semester: {terms}",
    "No courses found on Blackboard, so the current term could not be determined. "
    "Your courses will be synced as soon as Blackboard lists them.":
        "Auf Blackboard wurden keine Kurse gefunden, daher konnte das aktuelle Semester nicht bestimmt werden. "
        "Deine Kurse werden synchronisiert, sobald Blackboard sie anzeigt.",
    "none found": "keine gefunden",
    "Network error talking to Blackboard: {error}": "Netzwerkfehler bei der Verbindung zu Blackboard: {error}",
    "Unexpected error: {error}": "Unerwarteter Fehler: {error}",
    "Error: {error}": "Fehler: {error}",
    "Run `blackboard-sync login` to sign in to Blackboard.":
        "Führe `blackboard-sync login` aus, um dich bei Blackboard anzumelden.",

    # Courses
    "Courses": "Kurse",
    "This folder is a copy of Blackboard: the files of the ticked courses are matched to Blackboard on every "
    "sync, and deleted or damaged files are downloaded again. To keep files your own way, copy them to another "
    "folder.":
        "Dieser Ordner ist eine Kopie von Blackboard: Die Dateien der angehakten Kurse werden bei jedem Sync mit "
        "Blackboard abgeglichen, gelöschte oder beschädigte Dateien werden erneut heruntergeladen. Wenn du Dateien "
        "auf deine eigene Art ablegen willst, kopiere sie in einen anderen Ordner.",
    "A course you untick is no longer synced and does not show in Calendar or Announcements. Its downloaded "
    "files are not deleted. Tick it again and its missing files come right away.":
        "Ein Kurs ohne Haken wird nicht mehr synchronisiert und erscheint weder im Kalender noch bei den "
        "Ankündigungen. Seine heruntergeladenen Dateien werden nicht gelöscht. Hakst du ihn wieder an, kommen "
        "fehlende Dateien sofort.",
    "Courses without a term, such as guidance or orientation pages, are not synced unless you tick them.":
        "Kurse ohne Semester, etwa Info- oder Orientierungsseiten, werden nur synchronisiert, wenn du sie anhakst.",
    "Your courses are listed here after the first sync.": "Deine Kurse erscheinen hier nach dem ersten Sync.",
    # The card before the first download at a school whose current term is not clear
    "Check your courses before the first download": "Prüfe deine Kurse vor dem ersten Download",
    "Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
    "Untick any course you do not want, then confirm. Nothing is downloaded until you do.":
        "Blackboard Sync konnte nicht sicher erkennen, welches Semester an dieser Hochschule aktuell ist. "
        "Gefunden: {terms}. Entferne den Haken bei Kursen, die du nicht willst, und bestätige dann. Bis dahin "
        "wird nichts heruntergeladen.",
    "Confirm": "Bestätigen",
    "Not now": "Nicht jetzt",
    "Waiting for you to confirm the courses to download.": "Warte darauf, dass du die Kurse für den Download bestätigst.",

    # Calendar
    "Calendar": "Kalender",
    "Due dates are updated during a sync. Times are in this computer's local time.":
        "Abgabetermine werden beim Sync aktualisiert. Die Zeiten sind in der Ortszeit dieses Computers.",
    "Upcoming": "Anstehend",
    "Past due": "Überfällig",
    "Submissions are not checked; work you already handed in may show here too.":
        "Abgaben werden nicht geprüft; bereits eingereichte Arbeiten können hier auch erscheinen.",
    "No due dates saved.": "Keine Abgabetermine gespeichert.",
    "Sync to see due dates.": "Synchronisiere, um Abgabetermine zu sehen.",
    "Some courses' due dates could not be updated. Earlier ones are shown where there are any.":
        "Die Abgabetermine einiger Kurse konnten nicht aktualisiert werden. Falls vorhanden, werden ältere angezeigt.",
    "January": "Januar",
    "February": "Februar",
    "March": "März",
    "April": "April",
    "May": "Mai",
    "June": "Juni",
    "July": "Juli",
    "August": "August",
    "September": "September",
    "October": "Oktober",
    "November": "November",
    "December": "Dezember",
    "Monday": "Montag",
    "Tuesday": "Dienstag",
    "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag",
    "Friday": "Freitag",
    "Saturday": "Samstag",
    "Sunday": "Sonntag",
    "Due in 1 hour": "In 1 Stunde fällig",
    "Deadline coming up": "Abgabe steht bevor",
    "Today": "Heute",
    "Tomorrow": "Morgen",
    "{month} {day}": "{day}. {month}",
    "{month} {day}, {year}": "{day}. {month} {year}",
    "Untitled work": "Unbenannte Aufgabe",
    "today {time}": "heute {time}",
    "tomorrow {time}": "morgen {time}",
    "yesterday {time}": "gestern {time}",
    "Due: {time}": "Fällig: {time}",

    # Signing in
    "Blackboard Sync – Sign in": "Blackboard Sync – Anmelden",
    "The sign-in window was closed before sign-in finished.":
        "Das Anmeldefenster wurde geschlossen, bevor die Anmeldung abgeschlossen war.",
    "The sign-in window needs the Microsoft Edge WebView2 Runtime, which is missing on this computer. Install "
    "it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 or install Google Chrome or Microsoft Edge, then "
    "sign in again.":
        "Das Anmeldefenster benötigt die Microsoft Edge WebView2 Runtime, die auf diesem Computer fehlt. "
        "Installiere sie über https://go.microsoft.com/fwlink/p/?LinkId=2124703 oder installiere Google Chrome "
        "oder Microsoft Edge und melde dich dann erneut an.",
    "Sign-in was not completed within {n} minutes.": "Die Anmeldung wurde nicht innerhalb von {n} Minuten abgeschlossen.",
    "The sign-in window is unavailable ({error}); run ./scripts/setup.sh again or install a Chromium-based "
    "browser.":
        "Das Anmeldefenster ist nicht verfügbar ({error}); führe ./scripts/setup.sh erneut aus oder installiere "
        "einen Chromium-basierten Browser.",
    "The sign-in window is unavailable: {error}": "Das Anmeldefenster ist nicht verfügbar: {error}",
    "Close Sign-in Window": "Anmeldefenster schließen",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and run "
    "`blackboard-sync login` again.":
        "Der Browser ist nicht gestartet. Wenn noch ein Anmeldefenster von einem früheren Versuch offen ist, "
        "schließe es und führe `blackboard-sync login` erneut aus.",
    "Sign in to Blackboard in that window. It closes by itself once you are in.":
        "Melde dich in diesem Fenster bei Blackboard an. Es schließt sich von selbst, sobald du angemeldet bist.",
    "Could not find a supported browser (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, Opera GX, "
    "Chromium or Arc) on this computer.":
        "Auf diesem Computer wurde kein unterstützter Browser (Google Chrome, Microsoft Edge, Brave, Vivaldi, "
        "Opera, Opera GX, Chromium oder Arc) gefunden.",
    "Could not find {browser} on this computer.": "{browser} wurde auf diesem Computer nicht gefunden.",
    "Signed in as {name}; session saved ({n} cookies).": "Angemeldet als {name}; Sitzung gespeichert ({n} Cookies).",
    "Opening {browser} on {url} ...": "{browser} wird mit {url} geöffnet ...",
    "Opening the sign-in window on {url} ...": "Anmeldefenster für {url} wird geöffnet ...",
    "The browser was closed before sign-in finished.":
        "Der Browser wurde geschlossen, bevor die Anmeldung abgeschlossen war.",
    "The browser window was closed before sign-in finished.":
        "Das Browserfenster wurde geschlossen, bevor die Anmeldung abgeschlossen war.",
    "Playwright is not installed; see the README's setup steps.":
        "Playwright ist nicht installiert; siehe die Einrichtungsschritte in der README.",
    "Unknown browser {name}; use {choices}.": "Unbekannter Browser {name}; verwende {choices}.",
    "Could not open {browser}: {error}": "{browser} konnte nicht geöffnet werden: {error}",
    "Using the app's own sign-in window instead.": "Stattdessen wird das eigene Anmeldefenster der App verwendet.",
    "Could not connect to {browser}: {error}": "Keine Verbindung zu {browser} möglich: {error}",
    "Could not start the browser connection: {error}": "Die Browserverbindung konnte nicht gestartet werden: {error}",
    "You are not signed in yet.": "Du bist noch nicht angemeldet.",
    "The saved session could not be read.": "Die gespeicherte Sitzung konnte nicht gelesen werden.",
    "The saved session belongs to {url}.": "Die gespeicherte Sitzung gehört zu {url}.",
    "Some sign-in data could not be removed; close the sign-in browser if it is still open and sign out again.":
        "Einige Anmeldedaten konnten nicht entfernt werden; schließe den Anmelde-Browser, falls er noch offen ist, "
        "und melde dich erneut ab.",

    # macOS menus
    "Edit": "Bearbeiten",
    "Window": "Fenster",
    "Hide Blackboard Sync": "Blackboard Sync ausblenden",
    "Hide Others": "Andere ausblenden",
    "Show All": "Alle einblenden",
    "Quit Blackboard Sync": "Blackboard Sync beenden",
    "Undo": "Widerrufen",
    "Redo": "Wiederholen",
    "Cut": "Ausschneiden",
    "Copy": "Kopieren",
    "Paste": "Einsetzen",
    "Select All": "Alles auswählen",
    "Minimize": "Minimieren",
    "Close": "Schließen",

    # The menu bar / tray app
    "Blackboard Sync": "Blackboard Sync",
    "Blackboard Sync: syncing": "Blackboard Sync: Sync läuft",
    "Blackboard Sync: session expired": "Blackboard Sync: Sitzung abgelaufen",
    "Blackboard Sync: error": "Blackboard Sync: Fehler",
    "Blackboard Sync: paused": "Blackboard Sync: pausiert",
    "Blackboard Sync {version} downloaded": "Blackboard Sync {version} heruntergeladen",
    "In the window that opened, drag “Blackboard Sync” onto the “Applications” folder and choose “Replace” to "
    "put it in place of the old version. Quit Blackboard Sync first, then open the app again from the "
    "Applications folder. Your settings and downloaded course files are kept.":
        "Ziehe im geöffneten Fenster „Blackboard Sync“ auf den Ordner „Applications“ und wähle „Ersetzen“, "
        "um die alte Version zu ersetzen. Beende vorher Blackboard Sync und öffne die App danach erneut aus dem "
        "Programme-Ordner. Deine Einstellungen und heruntergeladenen Kursdateien bleiben erhalten.",
    "File not found.": "Datei nicht gefunden.",
    "Could not install the update.": "Das Update konnte nicht installiert werden.",
    "Could not install the update": "Update konnte nicht installiert werden",
    "Could not change the start-at-login setting.":
        "Die Einstellung für den Start bei der Anmeldung konnte nicht geändert werden.",
    "Could not restart Blackboard Sync; quit it and open it again.":
        "Blackboard Sync konnte nicht neu gestartet werden; beende die App und öffne sie erneut.",
    "Sign out?": "Abmelden?",
    "All sign-in data is removed; you will need to enter your school details again to sign in. Your downloaded "
    "files are kept.":
        "Alle Anmeldedaten werden entfernt; zum Anmelden musst du die Daten deiner Hochschule erneut eingeben. "
        "Deine heruntergeladenen Dateien bleiben erhalten.",
    "Could not sign out.": "Abmelden fehlgeschlagen.",
    "The update cannot be installed now": "Das Update kann jetzt nicht installiert werden",
    "Later": "Später",
    "The {folder} folder does not exist yet; sync first.":
        "Der Ordner {folder} existiert noch nicht; synchronisiere zuerst.",
    "Sign out": "Abmelden",
    "Cancel": "Abbrechen",
    "Could not save the update: {error}": "Das Update konnte nicht gespeichert werden: {error}",
    "Could not save the course choice: {error}": "Die Kursauswahl konnte nicht gespeichert werden: {error}",
    "Could not save the settings: {error}": "Die Einstellungen konnten nicht gespeichert werden: {error}",
    "timed out": "Zeitüberschreitung",
    "Upcoming deadlines": "Anstehende Abgaben",
    "The sync took too long and was stopped.": "Der Sync hat zu lange gedauert und wurde abgebrochen.",
    "exit status {code}": "Exit-Code {code}",
    "Could not start the menu bar app: {error}": "Die Menüleisten-App konnte nicht gestartet werden: {error}",
    "Blackboard Sync is running in the background": "Blackboard Sync läuft im Hintergrund",
    "Right-click the Blackboard Sync icon next to the clock for the menu. If you don't see it, click the ^ "
    "arrow that shows hidden icons.":
        "Klicke mit der rechten Maustaste auf das Blackboard Sync-Symbol neben der Uhr, um das Menü zu öffnen. "
        "Wenn du es nicht siehst, klicke auf den Pfeil ^, der ausgeblendete Symbole anzeigt.",
    "Wait for the running job to finish before updating, then try again.":
        "Warte vor dem Update, bis der laufende Vorgang abgeschlossen ist, und versuche es dann erneut.",
    "Could not open the announcement.": "Die Ankündigung konnte nicht geöffnet werden.",
    "The file or folder does not exist yet; sync first.":
        "Die Datei oder der Ordner existiert noch nicht; synchronisiere zuerst.",
    "Could not open the file or folder.": "Die Datei oder der Ordner konnte nicht geöffnet werden.",
    "Blackboard Sync stopped because of an unexpected error.":
        "Blackboard Sync wurde wegen eines unerwarteten Fehlers beendet.",
    "The details are in this file:\n{path}": "Die Details stehen in dieser Datei:\n{path}",

    # The main window
    "Applications or Launchpad": "den Programme-Ordner oder Launchpad",
    "the Start menu": "das Startmenü",
    "Uninstall": "Deinstallieren",
    "The folder whose files go to the Trash:": "Ordner, dessen Dateien in den Papierkorb kommen:",
    "The folder whose files go to the Recycle Bin:": "Ordner, dessen Dateien in den Papierkorb kommen:",
    "Open the downloaded note": "Heruntergeladene Notiz öffnen",
    "Open in Blackboard": "In Blackboard öffnen",
    "Get started": "Erste Schritte",
    "Home": "Start",
    "Sync activity": "Aktivität",
    "Settings": "Einstellungen",
    "Your course files start here.": "Hier landen deine Kursdateien.",
    "Connect your Blackboard account and your course files come to this computer by themselves; no more "
    "checking the site every time.":
        "Verbinde dein Blackboard-Konto und deine Kursdateien kommen von selbst auf diesen Computer – ohne dass "
        "du ständig die Website prüfen musst.",
    "Let's get started": "Los geht's",
    "Open folder": "Ordner öffnen",
    "NEW": "NEU",
    "Update": "Updaten",
    "Update to get the latest version.": "Aktualisiere, um die neueste Version zu erhalten.",
    "Syncing": "Sync läuft",
    "Session expired": "Sitzung abgelaufen",
    "Not signed in": "Nicht angemeldet",
    "Waiting for sign-in": "Warte auf Anmeldung",
    "Not synced yet": "Noch kein Sync",
    "Downloading your files for the first time…": "Deine Dateien werden zum ersten Mal geladen…",
    "Unsaved changes": "Nicht gespeichert",
    "View all": "Alle anzeigen",
    "Open": "Öffnen",
    "Show in folder": "Im Ordner zeigen",
    "Recent downloads": "Letzte Downloads",
    "Open calendar": "Kalender öffnen",
    "No upcoming deadlines.": "Keine anstehenden Abgaben.",
    "Nothing downloaded yet.": "Noch nichts heruntergeladen.",
    "Pause": "Pausieren",
    "Up to date": "Aktuell",
    "Syncing…": "Sync läuft…",
    "Paused": "Pausiert",
    "Sign-in needed": "Anmeldung nötig",
    "Sync did not finish": "Sync nicht abgeschlossen",
    "Sync did not finish: {error}": "Sync nicht abgeschlossen: {error}",
    "Name": "Name",
    "File size": "Größe",
    "Status": "Status",
    "Good morning": "Guten Morgen",
    "Good afternoon": "Guten Tag",
    "Good evening": "Guten Abend",
    "{greeting}, {name}": "{greeting}, {name}",
    "No deadlines this week": "Diese Woche keine Abgaben",
    "{n} deadline this week": "{n} Abgabe diese Woche",
    "{n} deadlines this week": "{n} Abgaben diese Woche",
    "{n} deadline today": "{n} Abgabe heute",
    "{n} deadlines today": "{n} Abgaben heute",
    "{n} this week": "{n} diese Woche",
    "Choose your school and folder": "Wähle deine Hochschule und deinen Ordner",
    "You decide where the files are saved.": "Du entscheidest, wo die Dateien gespeichert werden.",
    "Sign in to Blackboard": "Bei Blackboard anmelden",
    "Your school's sign-in page opens. The first sync starts after you sign in.":
        "Die Anmeldeseite deiner Hochschule öffnet sich. Nach der Anmeldung startet der erste Sync.",
    "Your files stay up to date": "Deine Dateien bleiben aktuell",
    "Every hour by default. You can change how often in Settings.":
        "Standardmäßig stündlich. Wie oft, kannst du in den Einstellungen ändern.",
    "You can close this window. To see it again, open Blackboard Sync from {where}.":
        "Du kannst dieses Fenster schließen. Um es wieder zu sehen, öffne Blackboard Sync über {where}.",
    "Last synced: {time}": "Zuletzt synchronisiert: {time}",
    "Last attempt: {time}": "Letzter Versuch: {time}",
    "Downloading…": "Wird geladen…",
    "Blackboard Sync {version} is ready": "Blackboard Sync {version} ist bereit",
    "Your internet connection seems unstable": "Deine Internetverbindung scheint instabil zu sein",
    "syncing": "wird synchronisiert",
    "not syncing": "wird nicht synchronisiert",

    # The menu and the app's state
    "Sync now": "Sync starten",
    "Sign in": "Anmelden",
    "Waiting for sign-in…": "Warte auf Anmeldung…",
    "⚠ Session expired — Sign in": "⚠ Sitzung abgelaufen — Anmelden",
    "Nothing new yet": "Noch nichts Neues",
    "Pause syncing": "Sync pausieren",
    "Resume syncing": "Sync fortsetzen",
    "Settings…": "Einstellungen…",
    "Quit": "Beenden",
    "automatic sync off": "automatischer Sync aus",
    "Check now": "Jetzt prüfen",
    "Checking for updates…": "Suche nach Updates…",
    "Downloading update…": "Update wird geladen…",
    "Successfully downloaded": "Heruntergeladen",
    "Updated": "Aktualisiert",
    "Note saved": "Notiz gespeichert",
    "Note updated": "Notiz aktualisiert",
    "Announcement saved": "Ankündigung gespeichert",
    "Announcement updated": "Ankündigung aktualisiert",
    "Waiting for you to sign in in the browser…": "Warte auf deine Anmeldung im Browser…",
    "Waiting for you to sign in in the window that opened…": "Warte auf deine Anmeldung im geöffneten Fenster…",
    "Waiting for you to sign in in {browser}…": "Warte auf deine Anmeldung in {browser}…",
    "new file": "neue Datei",
    "new files": "neue Dateien",
    "updated file": "aktualisierte Datei",
    "updated files": "aktualisierte Dateien",
    "new note": "neue Notiz",
    "new notes": "neue Notizen",
    "updated note": "aktualisierte Notiz",
    "updated notes": "aktualisierte Notizen",
    "new announcement": "neue Ankündigung",
    "new announcements": "neue Ankündigungen",
    "updated announcement": "aktualisierte Ankündigung",
    "updated announcements": "aktualisierte Ankündigungen",
    "large file not downloaded": "große Datei nicht heruntergeladen",
    "large files not downloaded": "große Dateien nicht heruntergeladen",
    "nothing new": "nichts Neues",
    "{n} file": "{n} Datei",
    "{n} files": "{n} Dateien",
    "{n} warning": "{n} Warnung",
    "{n} file could not be downloaded": "{n} Datei konnte nicht heruntergeladen werden",
    "{n} files could not be downloaded": "{n} Dateien konnten nicht heruntergeladen werden",
    "{n} course could not be read": "{n} Kurs konnte nicht gelesen werden",
    "{n} courses could not be read": "{n} Kurse konnten nicht gelesen werden",
    "Something went wrong during the last sync": "Beim letzten Sync ist etwas schiefgelaufen",
    "{n} warnings": "{n} Warnungen",
    "({n} new)": "({n} neu)",
    "No files were moved.": "Es wurden keine Dateien verschoben.",
    "{files} moved to the new folder.": "In den neuen Ordner verschoben: {files}.",
    "{files} moved to the {folder} folder.": "In den Ordner {folder} verschoben: {files}.",
    "{files} could not be moved and stayed in the old folder.": "Nicht verschoben, im alten Ordner geblieben: {files}.",
    "{files} could not be moved and stayed where they were.": "Nicht verschoben, am alten Ort geblieben: {files}.",
    "Open {folder} folder": "Ordner {folder} öffnen",
    "Blackboard: new content": "Blackboard: neue Inhalte",
    "Click to download the new version.": "Klicke, um die neue Version herunterzuladen.",
    "Blackboard session expired": "Blackboard-Sitzung abgelaufen",
    "Choose “Sign in” in the menu to get new files.": "Wähle im Menü „Anmelden“, um neue Dateien zu erhalten.",
    "Some files could not be moved": "Einige Dateien konnten nicht verschoben werden",
    "Another sync is running; trying again shortly.": "Ein anderer Sync läuft; es wird gleich erneut versucht.",
    "Another sync is running; the files will be moved shortly.":
        "Ein anderer Sync läuft; die Dateien werden gleich verschoben.",
    "Sign in for the new school.": "Melde dich für die neue Hochschule an.",
    "not synced yet": "noch nicht synchronisiert",
    "synced at {time}": "synchronisiert {time}",
    "tried at {time}": "versucht {time}",
    "tried at {time} · error": "versucht {time} · Fehler",
    "next: {time}": "nächster Sync: {time}",
    "soon": "gleich",
    "Checking for new content…": "Suche nach neuen Inhalten…",
    "Moving files to the new folder…": "Dateien werden in den neuen Ordner verschoben…",
    "Moving files to the {folder} folder…": "Dateien werden in den Ordner {folder} verschoben…",
    "Choose “{settings}” to finish setting up": "Wähle „{settings}“, um die Einrichtung abzuschließen",
    "Blackboard Sync {version} is ready — Update": "Blackboard Sync {version} ist bereit — Aktualisieren",
    "Blackboard Sync is up to date": "Blackboard Sync ist aktuell",
    "You have the latest version ({version}).": "Du hast die neueste Version ({version}).",
    "Your settings and downloaded course files were kept.":
        "Deine Einstellungen und heruntergeladenen Kursdateien wurden beibehalten.",
    "Files moved": "Dateien verschoben",
    "Files moved to the {folder} folder": "Dateien in den Ordner {folder} verschoben",
    "Could not check for updates": "Suche nach Updates fehlgeschlagen",
    "Check your internet connection and try again later.":
        "Prüfe deine Internetverbindung und versuche es später erneut.",
    "Blackboard Sync {version} could not be put in place; version {current} is still in use.":
        "Blackboard Sync {version} konnte nicht installiert werden; Version {current} wird weiter verwendet.",
    "Blackboard Sync was updated to {version}": "Blackboard Sync wurde auf {version} aktualisiert",
    "Update available: {version} — Update": "Update verfügbar: {version} — Aktualisieren",
    "Could not move the files: {error}": "Die Dateien konnten nicht verschoben werden: {error}",
    "Sign-in did not finish: {error}": "Anmeldung nicht abgeschlossen: {error}",
    "No courses yet": "Noch keine Kurse",
    "Blackboard: no courses found": "Blackboard: keine Kurse gefunden",
    "no courses found": "keine Kurse gefunden",

    # Settings
    "Automatic sync": "Automatischer Sync",
    "Every 30 minutes": "Alle 30 Minuten",
    "Every hour": "Stündlich",
    "Every 3 hours": "Alle 3 Stunden",
    "Only manually": "Nur manuell",
    "Language": "Sprache",
    "Danger zone": "Gefahrenzone",
    "How often Blackboard is checked for new files.": "Wie oft Blackboard nach neuen Dateien durchsucht wird.",
    "Keeps syncing in the background after you sign in to the computer.":
        "Synchronisiert im Hintergrund weiter, nachdem du dich am Computer angemeldet hast.",
    "Looks for a new version once a day.": "Sucht einmal täglich nach einer neuen Version.",
    "Uninstall Blackboard Sync": "Blackboard Sync deinstallieren",
    "Restart Blackboard Sync to change the language?": "Blackboard Sync neu starten, um die Sprache zu ändern?",
    "The new language is used once the app starts again.": "Die neue Sprache wird nach dem Neustart der App verwendet.",
    "Restart now": "Jetzt neu starten",
    "Account": "Konto",
    "Folder": "Ordner",
    "Sync": "Sync",
    "Updates": "Updates",
    "Your school's Blackboard address": "Blackboard-Adresse deiner Hochschule",
    "School name or https://blackboard.school.edu": "Hochschule oder https://blackboard.uni.de",
    "If you change the address you need to sign in again for the new school.":
        "Wenn du die Adresse änderst, musst du dich für die neue Hochschule erneut anmelden.",
    "Folder to save files in": "Ordner zum Speichern der Dateien",
    "Files are saved in the University folder inside the folder you choose.":
        "Dateien werden im Ordner University innerhalb des gewählten Ordners gespeichert.",
    "If you change the folder you can move the downloaded files to the new one or download them again.":
        "Wenn du den Ordner änderst, kannst du die heruntergeladenen Dateien in den neuen verschieben oder neu "
        "herunterladen.",
    "Start when the computer starts": "Mit dem Computer starten",
    "Check for updates automatically": "Automatisch nach Updates suchen",
    "Automatic re-sign-in": "Automatisch neu anmelden",
    "Keeps your session alive and signs in again in the background when your school allows it. Your password is never stored.":
        "Hält deine Sitzung aktiv und meldet dich im Hintergrund neu an, wenn deine Hochschule das erlaubt. "
        "Dein Passwort wird nie gespeichert.",
    "Session refreshed automatically": "Sitzung automatisch erneuert",
    "Could not refresh the session without you: {reason}": "Sitzung konnte nicht ohne dich erneuert werden: {reason}",
    "Another sign-in is in progress; try again in a minute.":
        "Eine andere Anmeldung läuft; versuche es in einer Minute erneut.",
    "Choose…": "Auswählen…",
    "Use this folder": "Diesen Ordner verwenden",
    "Choose the folder to save your course files in.": "Wähle den Ordner, in dem deine Kursdateien gespeichert werden.",
    "Save": "Speichern",
    "Wait for the running job to finish first.": "Warte zuerst, bis der laufende Vorgang abgeschlossen ist.",
    "The folder was not changed.": "Der Ordner wurde nicht geändert.",
    "What should happen to the downloaded files?": "Was soll mit den heruntergeladenen Dateien passieren?",
    "Move": "Verschieben",
    "Download again": "Neu herunterladen",
    "“{folder}” holds {n} file downloaded from Blackboard.":
        "„{folder}“ enthält {n} von Blackboard heruntergeladene Datei.",
    "“{folder}” holds {n} files downloaded from Blackboard.":
        "„{folder}“ enthält {n} von Blackboard heruntergeladene Dateien.",
    "{move}: the files are moved to “{folder}”, not downloaded again. Files you added yourself stay in the old "
    "folder.":
        "{move}: Die Dateien werden nach „{folder}“ verschoben, nicht neu heruntergeladen. Dateien, die du selbst "
        "hinzugefügt hast, bleiben im alten Ordner.",
    "{redownload}: the files are downloaded again into the new folder; the old folder is not touched.":
        "{redownload}: Die Dateien werden erneut in den neuen Ordner heruntergeladen; der alte Ordner bleibt "
        "unverändert.",
    "Checking…": "Wird geprüft…",
    "Your session expired; sign in again.": "Deine Sitzung ist abgelaufen; melde dich erneut an.",
    "Not signed in yet.": "Noch nicht angemeldet.",
    "Version {version}": "Version {version}",
    "Signed in as {name}": "Angemeldet als {name}",
    "Update to {version}": "Auf {version} aktualisieren",
    "Enter a valid address, for example https://blackboard.school.edu":
        "Gib eine gültige Adresse ein, z. B. https://blackboard.hochschule.de",
    "Enter your school's Blackboard address.": "Gib die Blackboard-Adresse deiner Hochschule ein.",
    "The address must start with https://.": "Die Adresse muss mit https:// beginnen.",
    "Choose the folder to save the files in.": "Wähle den Ordner zum Speichern der Dateien.",
    "Enter the folder's full path, for example ~/Documents/University":
        "Gib den vollständigen Pfad des Ordners ein, z. B. ~/Documents/University",
    "This path is not a folder.": "Dieser Pfad ist kein Ordner.",

    # The sync report
    "Would sync {n} course(s) for {terms} into {folder}":
        "Würde {n} Kurs(e) für {terms} nach {folder} synchronisieren",
    "Synced {n} course(s) for {terms} into {folder}": "{n} Kurs(e) für {terms} nach {folder} synchronisiert",
    "Nothing new.": "Nichts Neues.",
    "no changes": "keine Änderungen",
    "Moved {n} file(s) into {folder}": "{n} Datei(en) nach {folder} verschoben",
    "{n} file(s) could not be moved and stayed where they were:":
        "{n} Datei(en) nicht verschoben, am alten Ort geblieben:",
    "no term": "kein Semester",
    "{n} course(s) had changes.": "{n} Kurs(e) mit Änderungen.",

    # The sync
    "Could not read {name} ({error}); moved it to {saved} and continued with an empty state. Files already on "
    "disk that match Blackboard's copy are kept as they are, not duplicated.":
        "{name} konnte nicht gelesen werden ({error}); als {saved} beiseitegelegt und mit leerem Stand "
        "fortgesetzt. Dateien auf der Festplatte, die der Blackboard-Kopie entsprechen, bleiben unverändert und "
        "werden nicht doppelt angelegt.",
    "Could not read {name} ({error}); it would be set aside on a real sync.":
        "{name} konnte nicht gelesen werden ({error}); bei einem echten Sync würde die Datei beiseitegelegt.",
    "Blackboard did not identify the signed-in user.": "Blackboard hat den angemeldeten Nutzer nicht erkannt.",
    "Another blackboard-sync run is already in progress.": "Ein anderer blackboard-sync-Lauf ist bereits aktiv.",
    "Kept folder {old}: could not rename it to {new} because that folder already exists. Move your files into "
    "one of them to finish.":
        "Ordner {old} beibehalten: Umbenennen in {new} nicht möglich, weil dieser Ordner bereits existiert. "
        "Verschiebe deine Dateien in einen der beiden, um das abzuschließen.",
    "Kept folder {old}: could not rename it to {new} ({error}).":
        "Ordner {old} beibehalten: Umbenennen in {new} nicht möglich ({error}).",
    "Could not read course content: {error}": "Kursinhalte konnten nicht gelesen werden: {error}",
    "Could not sync announcements: {error}": "Ankündigungen konnten nicht synchronisiert werden: {error}",
    "Could not read due dates: {error}": "Abgabetermine konnten nicht gelesen werden: {error}",
    "Could not read term {term}; using its id as folder name.":
        "Semester {term} konnte nicht gelesen werden; seine ID wird als Ordnername verwendet.",
    "Skipped course {course}: {error}": "Kurs {course} übersprungen: {error}",
    "Could not open folder {name}: {error}": "Ordner {name} konnte nicht geöffnet werden: {error}",
    "Skipped {name}: {error}": "{name} übersprungen: {error}",

    # Uninstalling
    "Uninstall Blackboard Sync?": "Blackboard Sync deinstallieren?",
    "Uninstall app…": "App deinstallieren…",
    "Also delete the downloaded course files": "Auch die heruntergeladenen Kursdateien löschen",
    "The app and all of its records, logs, settings and sign-in data are removed, and so is its start-at-login "
    "entry. Downloaded course files are kept unless you tick this option.":
        "Die App und alle ihre Daten, Protokolle, Einstellungen und Anmeldedaten werden entfernt, ebenso ihr "
        "Eintrag für den Start bei der Anmeldung. Heruntergeladene Kursdateien bleiben erhalten, außer du hakst "
        "diese Option an.",
    "Wait for the sync or the folder move to finish before uninstalling.":
        "Warte vor dem Deinstallieren, bis der Sync oder das Verschieben des Ordners abgeschlossen ist.",
    "You can uninstall Blackboard Sync from Windows Settings → Apps.":
        "Du kannst Blackboard Sync in den Windows-Einstellungen → Apps deinstallieren.",
    "Remove the app's files yourself.": "Entferne die Dateien der App selbst.",
    "The download records could not be read; the course files were kept to be safe.":
        "Die Download-Daten konnten nicht gelesen werden; die Kursdateien wurden sicherheitshalber behalten.",
    "The app data folder contains the download folder or the home folder; uninstall cancelled.":
        "Der App-Datenordner enthält den Download-Ordner oder den Benutzerordner; Deinstallation abgebrochen.",
    "Quit Blackboard Sync first, or use Uninstall app… in its settings.":
        "Beende zuerst Blackboard Sync oder nutze „App deinstallieren…“ in den Einstellungen.",
    "A lock file is a link; the app could not be removed safely.":
        "Eine Sperrdatei ist ein Link; die App konnte nicht sicher entfernt werden.",
    "The uninstaller could not be started. Uninstall Blackboard Sync from Windows Settings → Apps; if needed, "
    "delete this folder yourself: {path}":
        "Das Deinstallationsprogramm konnte nicht gestartet werden. Deinstalliere Blackboard Sync über "
        "Windows-Einstellungen → Apps; lösche bei Bedarf diesen Ordner selbst: {path}",
    "The app could not be removed; delete it yourself: {error}":
        "Die App konnte nicht entfernt werden; lösche sie selbst: {error}",
    "Could not move an empty folder to the Trash: {path} ({error})":
        "Leerer Ordner konnte nicht in den Papierkorb verschoben werden: {path} ({error})",
    "Could not delete a lock file: {name} ({error})": "Sperrdatei konnte nicht gelöscht werden: {name} ({error})",
    "The app could not be moved to the Trash. Delete it in Finder yourself: {path}":
        "Die App konnte nicht in den Papierkorb verschoben werden. Lösche sie selbst im Finder: {path}",
    "Could not move a file to the Trash: {path} ({error})":
        "Datei konnte nicht in den Papierkorb verschoben werden: {path} ({error})",
    "Could not clear the sign-in data: {error}": "Anmeldedaten konnten nicht gelöscht werden: {error}",
    "Could not remove the start-at-login entry: {error}":
        "Eintrag für den Start bei der Anmeldung konnte nicht entfernt werden: {error}",
    "Could not clear the app data folder: {path} ({error})":
        "App-Datenordner konnte nicht geleert werden: {path} ({error})",
    "Could not move the course files to the Trash: {error}":
        "Kursdateien konnten nicht in den Papierkorb verschoben werden: {error}",
    "Could not delete app data: {path}": "App-Daten konnten nicht gelöscht werden: {path}",
    "The Recycle Bin API could not be loaded; the file was kept.":
        "Die Papierkorb-API konnte nicht geladen werden; die Datei wurde behalten.",
    "The file could not be moved to the Recycle Bin; it was kept.":
        "Die Datei konnte nicht in den Papierkorb verschoben werden; sie wurde behalten.",
    "The file cannot be recycled; permanent deletion was cancelled.":
        "Die Datei kann nicht in den Papierkorb; endgültiges Löschen wurde abgebrochen.",
    "The Recycle Bin operation failed: {error}": "Papierkorb-Vorgang fehlgeschlagen: {error}",

    # Updates
    "The update cannot be installed while a sync or a folder move runs; try again once it has finished.":
        "Das Update kann nicht installiert werden, während ein Sync oder das Verschieben eines Ordners läuft; "
        "versuche es danach erneut.",
    "the current version is kept.": "die aktuelle Version bleibt erhalten.",
    "Blackboard Sync runs from its disk image, so it cannot update itself.":
        "Blackboard Sync läuft vom Disk-Image aus und kann sich daher nicht selbst aktualisieren.",
    "macOS runs Blackboard Sync from a temporary location, so the app cannot update itself.":
        "macOS führt Blackboard Sync von einem temporären Ort aus, daher kann sich die App nicht selbst "
        "aktualisieren.",
    "The folder Blackboard Sync is in cannot be written to, so the app cannot update itself.":
        "In den Ordner von Blackboard Sync kann nicht geschrieben werden, daher kann sich die App nicht selbst "
        "aktualisieren.",
    "This version is unsigned, so the update cannot be verified and installed automatically.":
        "Diese Version ist nicht signiert, daher kann das Update nicht automatisch geprüft und installiert werden.",
    "The update's disk image could not be opened;": "Das Disk-Image des Updates konnte nicht geöffnet werden;",
    "Blackboard Sync was not found in the disk image;": "Blackboard Sync wurde im Disk-Image nicht gefunden;",
    "The downloaded update is not the expected Blackboard Sync version;":
        "Das heruntergeladene Update ist nicht die erwartete Version von Blackboard Sync;",
    "The update's signature is not valid;": "Die Signatur des Updates ist ungültig;",
    "The update is not signed by the Blackboard Sync developer;":
        "Das Update ist nicht vom Entwickler von Blackboard Sync signiert;",
    "The update is not notarized by Apple;": "Das Update ist nicht von Apple notarisiert;",
    "The new version could not be copied;": "Die neue Version konnte nicht kopiert werden;",
    "The update could not be started;": "Das Update konnte nicht gestartet werden;",
    "Updates are installed through the Microsoft Store.": "Updates werden über den Microsoft Store installiert.",
    "The update could not be verified.": "Das Update konnte nicht verifiziert werden.",
    "The update does not come from this app's page; it was not downloaded.":
        "Das Update stammt nicht von der Seite dieser App; es wurde nicht heruntergeladen.",
    "The downloaded update could not be verified; it was not installed.":
        "Das heruntergeladene Update konnte nicht verifiziert werden; es wurde nicht installiert.",
    "The update could not be downloaded; check your internet connection.":
        "Das Update konnte nicht heruntergeladen werden; prüfe deine Internetverbindung.",
    "The update could not be downloaded.": "Das Update konnte nicht heruntergeladen werden.",
    "Google Calendar needs to be reconnected": "Google Calendar muss neu verbunden werden",
    "Google Calendar authorization state did not match.":
        "Der Autorisierungsstatus von Google Calendar stimmte nicht überein.",
    "Google Calendar authorization was cancelled.": "Die Autorisierung für Google Calendar wurde abgebrochen.",
    "Google Calendar operation was cancelled.": "Der Google Calendar-Vorgang wurde abgebrochen.",
    "Set BBSYNC_GOOGLE_CLIENT_ID to your Desktop OAuth client ID.":
        "Setze BBSYNC_GOOGLE_CLIENT_ID auf die Client-ID deines Desktop-OAuth-Clients.",
    "A Google Calendar operation is already running.": "Ein Google Calendar-Vorgang läuft bereits.",
    "Could not access the Google Calendar credential store.":
        "Auf den Anmeldedatenspeicher für Google Calendar konnte nicht zugegriffen werden.",
    "Could not open the browser for Google Calendar.": "Der Browser für Google Calendar konnte nicht geöffnet werden.",
    "The saved Google Calendar is not a dedicated secondary calendar.":
        "Der gespeicherte Kalender in Google Calendar ist kein eigener Zweitkalender.",
    "Sync Blackboard successfully before syncing Google Calendar.":
        "Synchronisiere Blackboard erfolgreich, bevor du Google Calendar synchronisierst.",
    "Google Calendar sync failed.": "Google Calendar-Sync fehlgeschlagen.",
    "Could not reach Google Calendar.": "Google Calendar ist nicht erreichbar.",
    "Google Calendar authorization timed out.": "Zeitüberschreitung bei der Autorisierung für Google Calendar.",
    "You can close this browser window and return to Blackboard Sync.":
        "Du kannst dieses Browserfenster schließen und zu Blackboard Sync zurückkehren.",
    "This event is managed by Blackboard Sync.": "Dieser Termin wird von Blackboard Sync verwaltet.",
    "Google Calendar operation failed.": "Google Calendar-Vorgang fehlgeschlagen.",
    "Disconnect Google Calendar?": "Google Calendar trennen?",
    "Access will be revoked and local Calendar connection data removed.":
        "Der Zugriff wird widerrufen und die lokalen Kalender-Verbindungsdaten werden entfernt.",
    "Disconnect": "Trennen",
    "Also delete the Blackboard Deadlines calendar from Google": "Auch den Kalender Blackboard Deadlines aus Google löschen",
    "Reconnect": "Neu verbinden",
    "Google Calendar error": "Google Calendar-Fehler",
    "Not connected": "Nicht verbunden",
    "Connect to see Blackboard deadlines in Google Calendar.":
        "Verbinde dich, um Blackboard-Abgaben in Google Calendar zu sehen.",
    "Connect Google Calendar": "Google Calendar verbinden",
    "Google Calendar operation in progress…": "Google Calendar-Vorgang läuft…",
    "You can cancel while authorization is waiting in the browser.":
        "Du kannst abbrechen, solange die Autorisierung im Browser wartet.",
    "Connected": "Verbunden",
    "Google Calendar": "Google Calendar",
    "Calendar has not synced yet.": "Der Kalender wurde noch nicht synchronisiert.",
    "Sends deadlines to a dedicated Blackboard Deadlines calendar. Your other calendars stay private.":
        "Sendet Abgabetermine an einen eigenen Kalender „Blackboard Deadlines“. Deine anderen Kalender bleiben privat.",
    "Sync calendar now": "Kalender synchronisieren",
    "Disconnect Google Calendar": "Google Calendar trennen",
    "Last calendar sync: {time}": "Letzter Kalender-Sync: {time}",
    "Google Calendar returned an invalid response.": "Google Calendar hat eine ungültige Antwort geliefert.",
    "Google requires this Desktop client's secret. Set BBSYNC_GOOGLE_CLIENT_SECRET locally and connect again.":
        "Google verlangt das Secret dieses Desktop-Clients. Setze BBSYNC_GOOGLE_CLIENT_SECRET lokal und verbinde "
        "dich erneut.",
    "The calendar's saved ID is missing. Delete the existing Blackboard Deadlines calendar in Google Calendar settings.":
        "Die gespeicherte ID des Kalenders fehlt. Lösche den vorhandenen Kalender Blackboard Deadlines in den "
        "Einstellungen von Google Calendar.",
    "Please wait for the calendar operation to finish.": "Bitte warte, bis der Kalendervorgang abgeschlossen ist.",
    # Settings → Appearance (the Windows window)
    "Appearance": "Darstellung",
    "Theme": "Design",
    "System follows the light or dark mode chosen in Windows.":
        "System folgt dem in Windows gewählten hellen oder dunklen Modus.",
    "System": "System",
    "Light": "Hell",
    "Dark": "Dunkel",

    # Settings → AI assistant (ai_launcher)
    "AI assistant": "KI-Assistent",
    "Continue my last session in this folder": "Letzte Sitzung in diesem Ordner fortsetzen",
    "When it is off, a new session starts every time.": "Ist das aus, startet jedes Mal eine neue Sitzung.",
    "The app only opens a terminal in your course folder. The AI tool runs with your own account and its own "
    "rules.":
        "Die App öffnet nur ein Terminal in deinem Kursordner. Das KI-Tool läuft mit deinem eigenen Konto und "
        "nach seinen eigenen Regeln.",
    "No earlier session here, starting a new one.": "Hier gibt es keine frühere Sitzung, eine neue wird gestartet.",
    "AI study session": "Lernen mit KI",
    "Click a tool to open {term}, continuing your last session there.":
        "Klicke auf ein Tool, um {term} zu öffnen und dort deine letzte Sitzung fortzusetzen.",
    "Click a tool to open {term} in a new session.":
        "Klicke auf ein Tool, um {term} in einer neuen Sitzung zu öffnen.",
    "Looking for AI tools…": "Suche nach KI-Tools…",
    "Terminal": "Terminal",
    "The terminal app that opens for AI tools.": "Das Terminalprogramm, das sich für KI-Tools öffnet.",
    "Command Prompt": "Eingabeaufforderung",
    "No AI tool is installed. Install Claude Code, Gemini CLI, Codex or Antigravity, then try again.":
        "Kein KI-Tool installiert. Installiere Claude Code, Gemini CLI, Codex oder Antigravity und versuche es erneut.",
    "{name} wasn't found. Using {default} instead.": "{name} wurde nicht gefunden. Stattdessen wird {default} verwendet.",
    "Open in {name}": "In {name} öffnen",
    "Opening…": "Wird geöffnet…",
    "{name} is not installed. Install it, then try again.": "{name} ist nicht installiert. Installiere es und versuche es erneut.",
    "How to install": "Anleitung",
    "Try again": "Erneut versuchen",
    "The {term} folder isn't there yet. Sync first.": "Der Ordner {term} existiert noch nicht. Synchronisiere zuerst.",
    "Could not open a terminal: {error}": "Terminal konnte nicht geöffnet werden: {error}",
    "Could not open a terminal.": "Terminal konnte nicht geöffnet werden.",
    "Open {name} in {term}": "{name} in {term} öffnen",

    # NotebookLM
    "Sign in to Google again to keep adding files.": "Melde dich erneut bei Google an, um weiter Dateien hinzuzufügen.",
    "Disconnect Gemini Notebook?": "Gemini Notebook trennen?",
    "The Google session is deleted from this computer. Files already in Gemini Notebook stay there, and new ones "
    "are no longer added.":
        "Die Google-Sitzung wird von diesem Computer gelöscht. Dateien, die schon in Gemini Notebook sind, "
        "bleiben dort, neue werden nicht mehr hinzugefügt.",
    "Connect Gemini Notebook": "Gemini Notebook verbinden",
    "Sync Gemini Notebook": "Gemini Notebook abgleichen",
    "Your course files are added after each sync.": "Deine Kursdateien werden nach jedem Sync hinzugefügt.",
    "Checking what is already in Gemini Notebook…": "Prüfe, was schon in Gemini Notebook ist…",
    "Sign in to Google in the browser window.": "Melde dich im Browserfenster bei Google an.",
    "Adding {done} of {total}: {file}": "Hinzufügen {done} von {total}: {file}",
    "Gemini Notebook is reading the new files…": "Gemini Notebook liest die neuen Dateien…",
    "Checking the connection…": "Verbindung wird geprüft…",
    "Open Gemini Notebook": "Gemini Notebook öffnen",
    "Google took the sign-in, but Gemini Notebook did not open. Try again.":
        "Google hat die Anmeldung angenommen, aber Gemini Notebook hat sich nicht geöffnet. Versuche es erneut.",
    "{n} new file added to your notebooks": "{n} neue Datei zu deinen Notebooks hinzugefügt",
    "{n} new files added to your notebooks": "{n} neue Dateien zu deinen Notebooks hinzugefügt",
    "No new files were added": "Keine neuen Dateien hinzugefügt",
    "Last checked: {time}": "Zuletzt geprüft: {time}",
    "{n} course blocked": "{n} Kurs blockiert",
    "{n} courses blocked": "{n} Kurse blockiert",
    "{n} failed": "{n} fehlgeschlagen",
    "Add new files to Gemini Notebook after each sync": "Nach jedem Sync neue Dateien zu Gemini Notebook hinzufügen",
    "Disconnect Gemini Notebook": "Gemini Notebook trennen",
    "Files in Gemini Notebook stay there.": "Dateien in Gemini Notebook bleiben dort.",
    "Unofficial connection: it may stop working if Google changes Gemini Notebook.":
        "Inoffizielle Verbindung: Sie kann aufhören zu funktionieren, wenn Google Gemini Notebook ändert.",
    "{course}: {n} over the {limit} source limit; nothing added.":
        "{course}: {n} über dem Limit von {limit} Quellen; nichts hinzugefügt.",
    "{course}: several notebooks have this name, so it was skipped.":
        "{course}: Mehrere Notebooks haben diesen Namen, daher übersprungen.",
    "{n} file could not be added; the next sync tries again.":
        "{n} Datei konnte nicht hinzugefügt werden; der nächste Sync versucht es erneut.",
    "{n} files could not be added; the next sync tries again.":
        "{n} Dateien konnten nicht hinzugefügt werden; der nächste Sync versucht es erneut.",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and try again.":
        "Der Browser ist nicht gestartet. Wenn noch ein Anmeldefenster von einem früheren Versuch offen ist, "
        "schließe es und versuche es erneut.",
    "Gemini Notebook needs Chrome, Edge or Brave to sign in to Google; install one and try again.":
        "Gemini Notebook braucht Chrome, Edge oder Brave für die Google-Anmeldung; installiere einen davon und "
        "versuche es erneut.",

    # NotebookLM: files that may be there already
    "{n} file may already be in Gemini Notebook, so it was not added.":
        "{n} Datei ist möglicherweise schon in Gemini Notebook und wurde daher nicht hinzugefügt.",
    "{n} files may already be in Gemini Notebook, so they were not added.":
        "{n} Dateien sind möglicherweise schon in Gemini Notebook und wurden daher nicht hinzugefügt.",
    "{n} held back": "{n} zurückgehalten",
}
