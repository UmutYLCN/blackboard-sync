"""French for every text the app shows: English text -> French text.

The keys are the exact strings passed to ``i18n.tr`` / ``ntr`` in the code;
``tests/test_i18n.py`` checks that each one is here with the same ``{fields}``.
``ntr`` picks the one-form only for a count of 1, so a count of 0 takes the
plural form ("0 fichiers").
"""

CATALOG = {
    # Announcements
    "Announcements": "Annonces",
    "Every announcement synced from your current-term courses.":
        "Toutes les annonces synchronisées depuis vos cours du semestre en cours.",
    "No announcements yet. They show up here once they are synced.":
        "Aucune annonce pour l’instant. Elles apparaîtront ici une fois synchronisées.",
    "No date given": "Sans date",
    "Open announcement": "Ouvrir l’annonce",
    "Announcement": "Annonce",

    # Blackboard and the command line
    "Your Blackboard session has expired.": "Votre session Blackboard a expiré.",
    "Blackboard redirected to a sign-in page.": "Blackboard a redirigé vers une page de connexion.",
    "Blackboard answered with a web page instead of data.": "Blackboard a renvoyé une page web au lieu de données.",
    "Blackboard answered a download with a web page.": "Blackboard a répondu à un téléchargement par une page web.",
    "Next: run `blackboard-sync sync` to download your courses.":
        "Étape suivante : lancez `blackboard-sync sync` pour télécharger vos cours.",
    "Blackboard Sync's app data was removed.": "Les données de l’app Blackboard Sync ont été supprimées.",
    "Session OK: signed in as {name}.": "Session valide : connexion en tant que {name}.",
    "Term(s): {terms}": "Semestre(s) : {terms}",
    "No courses found on Blackboard, so the current term could not be determined. "
    "Your courses will be synced as soon as Blackboard lists them.":
        "Aucun cours trouvé sur Blackboard, le semestre en cours n’a donc pas pu être déterminé. "
        "Vos cours seront synchronisés dès que Blackboard les affichera.",
    "none found": "aucun trouvé",
    "Network error talking to Blackboard: {error}": "Erreur réseau lors de l’échange avec Blackboard : {error}",
    "Unexpected error: {error}": "Erreur inattendue : {error}",
    "Error: {error}": "Erreur : {error}",
    "Run `blackboard-sync login` to sign in to Blackboard.":
        "Lancez `blackboard-sync login` pour vous connecter à Blackboard.",

    # Courses
    "Courses": "Cours",
    "This folder is a copy of Blackboard: the files of the ticked courses are matched to Blackboard on every "
    "sync, and deleted or damaged files are downloaded again. To keep files your own way, copy them to another "
    "folder.":
        "Ce dossier est une copie de Blackboard : à chaque synchronisation, les fichiers des cours cochés sont "
        "alignés sur Blackboard, et les fichiers supprimés ou endommagés sont téléchargés à nouveau. Pour "
        "organiser vos fichiers à votre façon, copiez-les dans un autre dossier.",
    "A course you untick is no longer synced and does not show in Calendar or Announcements. Its downloaded "
    "files are not deleted. Tick it again and its missing files come right away.":
        "Un cours décoché n’est plus synchronisé et n’apparaît plus dans Calendrier ni dans Annonces. Ses "
        "fichiers téléchargés ne sont pas supprimés. Cochez-le à nouveau et ses fichiers manquants arrivent "
        "aussitôt.",
    "Courses without a term, such as guidance or orientation pages, are not synced unless you tick them.":
        "Les cours sans semestre, comme les pages d’orientation ou d’accompagnement, ne sont synchronisés que "
        "si vous les cochez.",
    "Your courses are listed here after the first sync.": "Vos cours s’affichent ici après la première synchronisation.",
    # The card before the first download at a school whose current term is not clear
    "Check your courses before the first download": "Vérifiez vos cours avant le premier téléchargement",
    "Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
    "Untick any course you do not want, then confirm. Nothing is downloaded until you do.":
        "Blackboard Sync n’a pas pu déterminer avec certitude le semestre en cours dans cet établissement. "
        "Semestre(s) trouvé(s) : {terms}. Décochez les cours dont vous ne voulez pas, puis confirmez. Rien "
        "n’est téléchargé avant votre confirmation.",
    "Confirm": "Confirmer",
    "Not now": "Plus tard",
    "Waiting for you to confirm the courses to download.": "En attente de votre confirmation des cours à télécharger.",

    # Calendar
    "Calendar": "Calendrier",
    "Due dates are updated during a sync. Times are in this computer's local time.":
        "Les échéances sont mises à jour à chaque synchronisation. Les heures sont à l’heure locale de cet "
        "ordinateur.",
    "Upcoming": "À venir",
    "Past due": "Dépassées",
    "Submissions are not checked; work you already handed in may show here too.":
        "Les rendus ne sont pas vérifiés ; un travail déjà remis peut aussi apparaître ici.",
    "No due dates saved.": "Aucune échéance enregistrée.",
    "Sync to see due dates.": "Synchronisez pour voir les échéances.",
    "Some courses' due dates could not be updated. Earlier ones are shown where there are any.":
        "Les échéances de certains cours n’ont pas pu être mises à jour. Les précédentes sont affichées s’il y "
        "en a.",
    "January": "janvier",
    "February": "février",
    "March": "mars",
    "April": "avril",
    "May": "mai",
    "June": "juin",
    "July": "juillet",
    "August": "août",
    "September": "septembre",
    "October": "octobre",
    "November": "novembre",
    "December": "décembre",
    "Monday": "Lundi",
    "Tuesday": "Mardi",
    "Wednesday": "Mercredi",
    "Thursday": "Jeudi",
    "Friday": "Vendredi",
    "Saturday": "Samedi",
    "Sunday": "Dimanche",
    "Due in 1 hour": "À rendre dans 1 heure",
    "Deadline coming up": "Échéance proche",
    "Today": "Aujourd’hui",
    "Tomorrow": "Demain",
    "{month} {day}": "{day} {month}",
    "{month} {day}, {year}": "{day} {month} {year}",
    "Untitled work": "Travail sans titre",
    "today {time}": "aujourd’hui à {time}",
    "tomorrow {time}": "demain à {time}",
    "yesterday {time}": "hier à {time}",
    "Due: {time}": "Échéance : {time}",

    # Signing in
    "Blackboard Sync – Sign in": "Blackboard Sync – Connexion",
    "The sign-in window was closed before sign-in finished.":
        "La fenêtre de connexion a été fermée avant la fin de la connexion.",
    "The sign-in window needs the Microsoft Edge WebView2 Runtime, which is missing on this computer. Install "
    "it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 or install Google Chrome or Microsoft Edge, then "
    "sign in again.":
        "La fenêtre de connexion nécessite Microsoft Edge WebView2 Runtime, absent de cet ordinateur. "
        "Installez-le depuis https://go.microsoft.com/fwlink/p/?LinkId=2124703 ou installez Google Chrome ou "
        "Microsoft Edge, puis reconnectez-vous.",
    "Sign-in was not completed within {n} minutes.": "La connexion n’a pas abouti en {n} minutes.",
    "The sign-in window is unavailable ({error}); run ./scripts/setup.sh again or install a Chromium-based "
    "browser.":
        "La fenêtre de connexion est indisponible ({error}) ; relancez ./scripts/setup.sh ou installez un "
        "navigateur basé sur Chromium.",
    "The sign-in window is unavailable: {error}": "La fenêtre de connexion est indisponible : {error}",
    "Close Sign-in Window": "Fermer la fenêtre de connexion",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and run "
    "`blackboard-sync login` again.":
        "Le navigateur n’a pas démarré. Si une fenêtre de connexion d’une tentative précédente est encore "
        "ouverte, fermez-la et relancez `blackboard-sync login`.",
    "Sign in to Blackboard in that window. It closes by itself once you are in.":
        "Connectez-vous à Blackboard dans cette fenêtre. Elle se fermera d’elle-même une fois la connexion "
        "établie.",
    "Could not find a supported browser (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, Opera GX, "
    "Chromium or Arc) on this computer.":
        "Aucun navigateur compatible (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, Opera GX, "
        "Chromium ou Arc) n’a été trouvé sur cet ordinateur.",
    "Could not find {browser} on this computer.": "{browser} est introuvable sur cet ordinateur.",
    "Signed in as {name}; session saved ({n} cookies).":
        "Connexion en tant que {name} ; session enregistrée ({n} cookies).",
    "Opening {browser} on {url} ...": "Ouverture de {browser} sur {url}...",
    "Opening the sign-in window on {url} ...": "Ouverture de la fenêtre de connexion sur {url}...",
    "The browser was closed before sign-in finished.": "Le navigateur a été fermé avant la fin de la connexion.",
    "The browser window was closed before sign-in finished.":
        "La fenêtre du navigateur a été fermée avant la fin de la connexion.",
    "Playwright is not installed; see the README's setup steps.":
        "Playwright n’est pas installé ; consultez les étapes d’installation du README.",
    "Unknown browser {name}; use {choices}.": "Navigateur inconnu {name} ; utilisez {choices}.",
    "Could not open {browser}: {error}": "Impossible d’ouvrir {browser} : {error}",
    "Using the app's own sign-in window instead.": "Utilisation de la fenêtre de connexion de l’app à la place.",
    "Could not connect to {browser}: {error}": "Impossible de se connecter à {browser} : {error}",
    "Could not start the browser connection: {error}": "Impossible d’établir la connexion au navigateur : {error}",
    "You are not signed in yet.": "Vous n’êtes pas encore connecté.",
    "The saved session could not be read.": "Impossible de lire la session enregistrée.",
    "The saved session belongs to {url}.": "La session enregistrée appartient à {url}.",
    "Some sign-in data could not be removed; close the sign-in browser if it is still open and sign out again.":
        "Certaines données de connexion n’ont pas pu être supprimées ; fermez le navigateur de connexion s’il "
        "est encore ouvert, puis déconnectez-vous à nouveau.",

    # macOS menus
    "Edit": "Édition",
    "Window": "Fenêtre",
    "Hide Blackboard Sync": "Masquer Blackboard Sync",
    "Hide Others": "Masquer les autres",
    "Show All": "Tout afficher",
    "Quit Blackboard Sync": "Quitter Blackboard Sync",
    "Undo": "Annuler",
    "Redo": "Rétablir",
    "Cut": "Couper",
    "Copy": "Copier",
    "Paste": "Coller",
    "Select All": "Tout sélectionner",
    "Minimize": "Réduire",
    "Close": "Fermer",

    # The menu bar / tray app
    "Blackboard Sync": "Blackboard Sync",
    "Blackboard Sync: syncing": "Blackboard Sync : synchronisation",
    "Blackboard Sync: session expired": "Blackboard Sync : session expirée",
    "Blackboard Sync: error": "Blackboard Sync : erreur",
    "Blackboard Sync: paused": "Blackboard Sync : en pause",
    "Blackboard Sync {version} downloaded": "Blackboard Sync {version} téléchargé",
    "In the window that opened, drag “Blackboard Sync” onto the “Applications” folder and choose “Replace” to "
    "put it in place of the old version. Quit Blackboard Sync first, then open the app again from the "
    "Applications folder. Your settings and downloaded course files are kept.":
        "Dans la fenêtre qui s’est ouverte, faites glisser « Blackboard Sync » sur le dossier « Applications » "
        "et choisissez « Remplacer » pour remplacer l’ancienne version. Quittez d’abord Blackboard Sync, puis "
        "rouvrez l’app depuis le dossier Applications. Vos paramètres et les fichiers de cours téléchargés "
        "sont conservés.",
    "File not found.": "Fichier introuvable.",
    "Could not install the update.": "Impossible d’installer la mise à jour.",
    "Could not install the update": "Impossible d’installer la mise à jour",
    "Could not change the start-at-login setting.": "Impossible de modifier le lancement à l’ouverture de session.",
    "Could not restart Blackboard Sync; quit it and open it again.":
        "Impossible de redémarrer Blackboard Sync ; quittez l’app puis rouvrez-la.",
    "Sign out?": "Se déconnecter ?",
    "All sign-in data is removed; you will need to enter your school details again to sign in. Your downloaded "
    "files are kept.":
        "Toutes les données de connexion sont supprimées ; vous devrez saisir à nouveau les informations de "
        "votre établissement pour vous connecter. Vos fichiers téléchargés sont conservés.",
    "Could not sign out.": "Impossible de se déconnecter.",
    "The update cannot be installed now": "Impossible d’installer la mise à jour maintenant",
    "Later": "Plus tard",
    "The {folder} folder does not exist yet; sync first.":
        "Le dossier {folder} n’existe pas encore ; synchronisez d’abord.",
    "Sign out": "Déconnexion",
    "Cancel": "Annuler",
    "Could not save the update: {error}": "Impossible d’enregistrer la mise à jour : {error}",
    "Could not save the course choice: {error}": "Impossible d’enregistrer le choix des cours : {error}",
    "Could not save the settings: {error}": "Impossible d’enregistrer les paramètres : {error}",
    "timed out": "délai dépassé",
    "Upcoming deadlines": "Échéances à venir",
    "The sync took too long and was stopped.": "La synchronisation a pris trop de temps et a été arrêtée.",
    "exit status {code}": "code de sortie {code}",
    "Could not start the menu bar app: {error}": "Impossible de lancer l’app de la barre des menus : {error}",
    "Blackboard Sync is running in the background": "Blackboard Sync s’exécute en arrière-plan",
    "Right-click the Blackboard Sync icon next to the clock for the menu. If you don't see it, click the ^ "
    "arrow that shows hidden icons.":
        "Faites un clic droit sur l’icône Blackboard Sync à côté de l’horloge pour ouvrir le menu. Si elle "
        "n’apparaît pas, cliquez sur la flèche ^ qui affiche les icônes cachées.",
    "Wait for the running job to finish before updating, then try again.":
        "Attendez la fin de l’opération en cours avant de mettre à jour, puis réessayez.",
    "Could not open the announcement.": "Impossible d’ouvrir l’annonce.",
    "The file or folder does not exist yet; sync first.":
        "Le fichier ou dossier n’existe pas encore ; synchronisez d’abord.",
    "Could not open the file or folder.": "Impossible d’ouvrir le fichier ou le dossier.",
    "Blackboard Sync stopped because of an unexpected error.":
        "Blackboard Sync s’est arrêté en raison d’une erreur inattendue.",
    "The details are in this file:\n{path}": "Les détails se trouvent dans ce fichier :\n{path}",

    # The main window
    "Applications or Launchpad": "le dossier Applications ou le Launchpad",
    "the Start menu": "le menu Démarrer",
    "Uninstall": "Désinstaller",
    "The folder whose files go to the Trash:": "Dossier dont les fichiers iront à la Corbeille :",
    "The folder whose files go to the Recycle Bin:": "Dossier dont les fichiers iront à la Corbeille :",
    "Open the downloaded note": "Ouvrir la note téléchargée",
    "Open in Blackboard": "Ouvrir dans Blackboard",
    "Get started": "Démarrer",
    "Home": "Accueil",
    "Sync activity": "Activité",
    "Settings": "Paramètres",
    "Your course files start here.": "Vos fichiers de cours commencent ici.",
    "Connect your Blackboard account and your course files come to this computer by themselves; no more "
    "checking the site every time.":
        "Connectez votre compte Blackboard et vos fichiers de cours arrivent tout seuls sur cet ordinateur ; "
        "plus besoin de consulter le site à chaque fois.",
    "Let's get started": "C’est parti",
    "Open folder": "Ouvrir le dossier",
    "NEW": "NOUVEAU",
    "Update": "Installer",
    "Update to get the latest version.": "Mettez à jour pour obtenir la dernière version.",
    "Syncing": "Synchro",
    "Session expired": "Session expirée",
    "Not signed in": "Non connecté",
    "Waiting for sign-in": "Connexion en attente",
    "Not synced yet": "Pas encore synchronisé",
    "Downloading your files for the first time…": "Premier téléchargement de vos fichiers…",
    "Unsaved changes": "Non enregistré",
    "View all": "Tout voir",
    "Open": "Ouvrir",
    "Show in folder": "Voir dans le dossier",
    "Recent downloads": "Téléchargements récents",
    "Open calendar": "Voir le calendrier",
    "No upcoming deadlines.": "Aucune échéance à venir.",
    "Nothing downloaded yet.": "Rien de téléchargé pour l’instant.",
    "Pause": "Suspendre",
    "Up to date": "À jour",
    "Syncing…": "Synchronisation…",
    "Paused": "En pause",
    "Sign-in needed": "Connexion requise",
    "Sync did not finish": "Synchro inachevée",
    "Sync did not finish: {error}": "Synchro inachevée : {error}",
    "Name": "Nom",
    "File size": "Taille",
    "Status": "Statut",
    "Good morning": "Bonjour",
    "Good afternoon": "Bon après-midi",
    "Good evening": "Bonsoir",
    "{greeting}, {name}": "{greeting}, {name}",
    "No deadlines this week": "Aucune échéance cette semaine",
    "{n} deadline this week": "{n} échéance cette semaine",
    "{n} deadlines this week": "{n} échéances cette semaine",
    "{n} deadline today": "{n} échéance aujourd’hui",
    "{n} deadlines today": "{n} échéances aujourd’hui",
    "{n} this week": "{n} cette semaine",
    "Choose your school and folder": "Choisissez votre établissement et votre dossier",
    "You decide where the files are saved.": "Vous choisissez où les fichiers sont enregistrés.",
    "Sign in to Blackboard": "Connectez-vous à Blackboard",
    "Your school's sign-in page opens. The first sync starts after you sign in.":
        "La page de connexion de votre établissement s’ouvre. La première synchronisation démarre après votre "
        "connexion.",
    "Your files stay up to date": "Vos fichiers restent à jour",
    "Every hour by default. You can change how often in Settings.":
        "Toutes les heures par défaut. Vous pouvez changer la fréquence dans Paramètres.",
    "You can close this window. To see it again, open Blackboard Sync from {where}.":
        "Vous pouvez fermer cette fenêtre. Pour la rouvrir, lancez Blackboard Sync depuis {where}.",
    "Last synced: {time}": "Dernière synchro : {time}",
    "Last attempt: {time}": "Dernière tentative : {time}",
    "Downloading…": "Téléchargement…",
    "Blackboard Sync {version} is ready": "Blackboard Sync {version} est prêt",
    "Your internet connection seems unstable": "Votre connexion Internet semble instable",
    "syncing": "synchronisé",
    "not syncing": "non synchronisé",

    # The menu and the app's state
    "Sync now": "Synchroniser",
    "Sign in": "Connexion",
    "Waiting for sign-in…": "Connexion en attente…",
    "⚠ Session expired — Sign in": "⚠ Session expirée — Connexion",
    "Nothing new yet": "Rien de nouveau pour l’instant",
    "Pause syncing": "Suspendre la synchro",
    "Resume syncing": "Reprendre la synchro",
    "Settings…": "Paramètres…",
    "Quit": "Quitter",
    "automatic sync off": "synchro auto désactivée",
    "Check now": "Vérifier",
    "Checking for updates…": "Recherche de mises à jour…",
    "Downloading update…": "Téléchargement de la mise à jour…",
    "Successfully downloaded": "Téléchargement réussi",
    "Updated": "Mis à jour",
    "Note saved": "Note enregistrée",
    "Note updated": "Note mise à jour",
    "Announcement saved": "Annonce enregistrée",
    "Announcement updated": "Annonce mise à jour",
    "Waiting for you to sign in in the browser…": "En attente de votre connexion dans le navigateur…",
    "Waiting for you to sign in in the window that opened…": "En attente de votre connexion dans la fenêtre ouverte…",
    "Waiting for you to sign in in {browser}…": "En attente de votre connexion dans {browser}…",
    "new file": "nouveau fichier",
    "new files": "nouveaux fichiers",
    "updated file": "fichier mis à jour",
    "updated files": "fichiers mis à jour",
    "new note": "nouvelle note",
    "new notes": "nouvelles notes",
    "updated note": "note mise à jour",
    "updated notes": "notes mises à jour",
    "new announcement": "nouvelle annonce",
    "new announcements": "nouvelles annonces",
    "updated announcement": "annonce mise à jour",
    "updated announcements": "annonces mises à jour",
    "large file not downloaded": "gros fichier non téléchargé",
    "large files not downloaded": "gros fichiers non téléchargés",
    "nothing new": "rien de nouveau",
    "{n} file": "{n} fichier",
    "{n} files": "{n} fichiers",
    "{n} warning": "{n} alerte",
    "{n} file could not be downloaded": "{n} fichier n’a pas pu être téléchargé",
    "{n} files could not be downloaded": "{n} fichiers n’ont pas pu être téléchargés",
    "{n} course could not be read": "{n} cours n’a pas pu être lu",
    "{n} courses could not be read": "{n} cours n’ont pas pu être lus",
    "Something went wrong during the last sync": "Un problème est survenu lors de la dernière synchro",
    "{n} warnings": "{n} alertes",
    "({n} new)": "({n} nouv.)",
    "No files were moved.": "Aucun fichier n’a été déplacé.",
    "{files} moved to the new folder.": "Fichiers déplacés vers le nouveau dossier : {files}.",
    "{files} moved to the {folder} folder.": "Fichiers déplacés vers le dossier {folder} : {files}.",
    "{files} could not be moved and stayed in the old folder.":
        "Fichiers non déplacés, restés dans l’ancien dossier : {files}.",
    "{files} could not be moved and stayed where they were.": "Fichiers non déplacés, restés à leur place : {files}.",
    "Open {folder} folder": "Ouvrir le dossier {folder}",
    "Blackboard: new content": "Blackboard : nouveau contenu",
    "Click to download the new version.": "Cliquez pour télécharger la nouvelle version.",
    "Blackboard session expired": "Session Blackboard expirée",
    "Choose “Sign in” in the menu to get new files.":
        "Choisissez « Connexion » dans le menu pour recevoir les nouveaux fichiers.",
    "Some files could not be moved": "Certains fichiers n’ont pas pu être déplacés",
    "Another sync is running; trying again shortly.":
        "Une autre synchronisation est en cours ; nouvel essai sous peu.",
    "Another sync is running; the files will be moved shortly.":
        "Une autre synchronisation est en cours ; les fichiers seront déplacés sous peu.",
    "Sign in for the new school.": "Connectez-vous pour le nouvel établissement.",
    "not synced yet": "pas encore synchronisé",
    "synced at {time}": "synchro : {time}",
    "tried at {time}": "essai : {time}",
    "tried at {time} · error": "essai : {time} · erreur",
    "next: {time}": "prochaine : {time}",
    "soon": "bientôt",
    "Checking for new content…": "Recherche de nouveau contenu…",
    "Moving files to the new folder…": "Déplacement des fichiers vers le nouveau dossier…",
    "Moving files to the {folder} folder…": "Déplacement des fichiers vers le dossier {folder}…",
    "Choose “{settings}” to finish setting up": "Choisissez « {settings} » pour terminer la configuration",
    "Blackboard Sync {version} is ready — Update": "Blackboard Sync {version} est prêt — Mettre à jour",
    "Blackboard Sync is up to date": "Blackboard Sync est à jour",
    "You have the latest version ({version}).": "Vous avez la dernière version ({version}).",
    "Your settings and downloaded course files were kept.":
        "Vos paramètres et vos fichiers de cours téléchargés ont été conservés.",
    "Files moved": "Fichiers déplacés",
    "Files moved to the {folder} folder": "Fichiers déplacés vers le dossier {folder}",
    "Could not check for updates": "Impossible de rechercher des mises à jour",
    "Check your internet connection and try again later.":
        "Vérifiez votre connexion Internet et réessayez plus tard.",
    "Blackboard Sync {version} could not be put in place; version {current} is still in use.":
        "Blackboard Sync {version} n’a pas pu être installé ; la version {current} reste utilisée.",
    "Blackboard Sync was updated to {version}": "Blackboard Sync a été mis à jour vers la version {version}",
    "Update available: {version} — Update": "Mise à jour disponible : {version} — Mettre à jour",
    "Could not move the files: {error}": "Impossible de déplacer les fichiers : {error}",
    "Sign-in did not finish: {error}": "La connexion n’a pas abouti : {error}",
    "No courses yet": "Aucun cours pour l’instant",
    "Blackboard: no courses found": "Blackboard : aucun cours trouvé",
    "no courses found": "aucun cours trouvé",

    # Settings
    "Automatic sync": "Synchro automatique",
    "Every 30 minutes": "Toutes les 30 minutes",
    "Every hour": "Toutes les heures",
    "Every 3 hours": "Toutes les 3 heures",
    "Only manually": "Manuellement",
    "Language": "Langue",
    "Danger zone": "Zone de danger",
    "How often Blackboard is checked for new files.":
        "Fréquence de recherche de nouveaux fichiers sur Blackboard.",
    "Keeps syncing in the background after you sign in to the computer.":
        "Continue la synchronisation en arrière-plan après l’ouverture de session sur l’ordinateur.",
    "Looks for a new version once a day.": "Recherche une nouvelle version une fois par jour.",
    "Uninstall Blackboard Sync": "Désinstaller Blackboard Sync",
    "Restart Blackboard Sync to change the language?": "Redémarrer Blackboard Sync pour changer de langue ?",
    "The new language is used once the app starts again.": "La nouvelle langue s’applique au redémarrage de l’app.",
    "Restart now": "Redémarrer",
    "Account": "Compte",
    "Folder": "Dossier",
    "Sync": "Synchro",
    "Updates": "Mises à jour",
    "Your school's Blackboard address": "Adresse Blackboard de votre établissement",
    "School name or https://blackboard.school.edu": "Établissement ou https://blackboard.ecole.fr",
    "If you change the address you need to sign in again for the new school.":
        "Si vous changez d’adresse, vous devrez vous reconnecter pour le nouvel établissement.",
    "Folder to save files in": "Dossier d’enregistrement des fichiers",
    "Files are saved in the University folder inside the folder you choose.":
        "Les fichiers sont enregistrés dans le dossier University à l’intérieur du dossier choisi.",
    "If you change the folder you can move the downloaded files to the new one or download them again.":
        "Si vous changez de dossier, vous pouvez y déplacer les fichiers téléchargés ou les télécharger à "
        "nouveau.",
    "Start when the computer starts": "Lancer au démarrage de l’ordinateur",
    "Check for updates automatically": "Rechercher les mises à jour automatiquement",
    "Automatic re-sign-in": "Reconnexion automatique",
    "Keeps your session alive and signs in again in the background when your school allows it. Your password is never stored.":
        "Maintient votre session active et vous reconnecte en arrière-plan quand votre établissement le "
        "permet. Votre mot de passe n’est jamais enregistré.",
    "Session refreshed automatically": "Session actualisée automatiquement",
    "Could not refresh the session without you: {reason}": "Impossible d’actualiser la session sans vous : {reason}",
    "Another sign-in is in progress; try again in a minute.":
        "Une autre connexion est en cours ; réessayez dans une minute.",
    "Choose…": "Choisir…",
    "Use this folder": "Utiliser ce dossier",
    "Choose the folder to save your course files in.": "Choisissez le dossier où enregistrer vos fichiers de cours.",
    "Save": "Enregistrer",
    "Wait for the running job to finish first.": "Attendez d’abord la fin de l’opération en cours.",
    "The folder was not changed.": "Le dossier n’a pas été modifié.",
    "What should happen to the downloaded files?": "Que faire des fichiers téléchargés ?",
    "Move": "Déplacer",
    "Download again": "Retélécharger",
    "“{folder}” holds {n} file downloaded from Blackboard.":
        "« {folder} » contient {n} fichier téléchargé depuis Blackboard.",
    "“{folder}” holds {n} files downloaded from Blackboard.":
        "« {folder} » contient {n} fichiers téléchargés depuis Blackboard.",
    "{move}: the files are moved to “{folder}”, not downloaded again. Files you added yourself stay in the old "
    "folder.":
        "{move} : les fichiers sont déplacés vers « {folder} », sans être retéléchargés. Les fichiers que vous "
        "avez ajoutés vous-même restent dans l’ancien dossier.",
    "{redownload}: the files are downloaded again into the new folder; the old folder is not touched.":
        "{redownload} : les fichiers sont téléchargés à nouveau dans le nouveau dossier ; l’ancien dossier "
        "reste intact.",
    "Checking…": "Vérification…",
    "Your session expired; sign in again.": "Votre session a expiré ; reconnectez-vous.",
    "Not signed in yet.": "Pas encore connecté.",
    "Version {version}": "Version {version}",
    "Signed in as {name}": "Connecté en tant que {name}",
    "Update to {version}": "Mettre à jour vers {version}",
    "Enter a valid address, for example https://blackboard.school.edu":
        "Saisissez une adresse valide, par exemple https://blackboard.ecole.fr",
    "Enter your school's Blackboard address.": "Saisissez l’adresse Blackboard de votre établissement.",
    "The address must start with https://.": "L’adresse doit commencer par https://.",
    "Choose the folder to save the files in.": "Choisissez le dossier où enregistrer les fichiers.",
    "Enter the folder's full path, for example ~/Documents/University":
        "Saisissez le chemin complet du dossier, par exemple ~/Documents/University",
    "This path is not a folder.": "Ce chemin n’est pas un dossier.",

    # The sync report
    "Would sync {n} course(s) for {terms} into {folder}":
        "Synchroniserait {n} cours pour {terms} dans {folder}",
    "Synced {n} course(s) for {terms} into {folder}": "{n} cours synchronisé(s) pour {terms} dans {folder}",
    "Nothing new.": "Rien de nouveau.",
    "no changes": "aucun changement",
    "Moved {n} file(s) into {folder}": "{n} fichier(s) déplacé(s) vers {folder}",
    "{n} file(s) could not be moved and stayed where they were:":
        "{n} fichier(s) non déplacé(s), laissé(s) à leur place :",
    "no term": "sans semestre",
    "{n} course(s) had changes.": "Changements dans {n} cours.",

    # The sync
    "Could not read {name} ({error}); moved it to {saved} and continued with an empty state. Files already on "
    "disk that match Blackboard's copy are kept as they are, not duplicated.":
        "Impossible de lire {name} ({error}) ; le fichier a été mis de côté sous {saved} et la synchronisation "
        "a continué avec un état vide. Les fichiers déjà sur le disque identiques à la copie de Blackboard "
        "sont conservés tels quels, sans doublon.",
    "Could not read {name} ({error}); it would be set aside on a real sync.":
        "Impossible de lire {name} ({error}) ; il serait mis de côté lors d’une vraie synchronisation.",
    "Blackboard did not identify the signed-in user.": "Blackboard n’a pas identifié l’utilisateur connecté.",
    "Another blackboard-sync run is already in progress.": "Une autre exécution de blackboard-sync est déjà en cours.",
    "Kept folder {old}: could not rename it to {new} because that folder already exists. Move your files into "
    "one of them to finish.":
        "Dossier {old} conservé : impossible de le renommer en {new}, car ce dossier existe déjà. Déplacez vos "
        "fichiers dans l’un des deux pour terminer.",
    "Kept folder {old}: could not rename it to {new} ({error}).":
        "Dossier {old} conservé : impossible de le renommer en {new} ({error}).",
    "Could not read course content: {error}": "Impossible de lire le contenu du cours : {error}",
    "Could not sync announcements: {error}": "Impossible de synchroniser les annonces : {error}",
    "Could not read due dates: {error}": "Impossible de lire les échéances : {error}",
    "Could not read term {term}; using its id as folder name.":
        "Impossible de lire le semestre {term} ; son identifiant sert de nom de dossier.",
    "Skipped course {course}: {error}": "Cours {course} ignoré : {error}",
    "Could not open folder {name}: {error}": "Impossible d’ouvrir le dossier {name} : {error}",
    "Skipped {name}: {error}": "{name} ignoré : {error}",

    # Uninstalling
    "Uninstall Blackboard Sync?": "Désinstaller Blackboard Sync ?",
    "Uninstall app…": "Désinstaller l’app…",
    "Also delete the downloaded course files": "Supprimer aussi les fichiers de cours téléchargés",
    "The app and all of its records, logs, settings and sign-in data are removed, and so is its start-at-login "
    "entry. Downloaded course files are kept unless you tick this option.":
        "L’app et l’ensemble de ses enregistrements, journaux, paramètres et données de connexion sont "
        "supprimés, de même que son lancement à l’ouverture de session. Les fichiers de cours téléchargés sont "
        "conservés, sauf si vous cochez cette option.",
    "Wait for the sync or the folder move to finish before uninstalling.":
        "Attendez la fin de la synchronisation ou du déplacement de dossier avant de désinstaller.",
    "You can uninstall Blackboard Sync from Windows Settings → Apps.":
        "Vous pouvez désinstaller Blackboard Sync depuis Paramètres Windows → Applications.",
    "Remove the app's files yourself.": "Supprimez vous-même les fichiers de l’app.",
    "The download records could not be read; the course files were kept to be safe.":
        "Impossible de lire l’historique des téléchargements ; les fichiers de cours ont été conservés par "
        "précaution.",
    "The app data folder contains the download folder or the home folder; uninstall cancelled.":
        "Le dossier de données de l’app contient le dossier de téléchargement ou le dossier personnel ; "
        "désinstallation annulée.",
    "Quit Blackboard Sync first, or use Uninstall app… in its settings.":
        "Quittez d’abord Blackboard Sync, ou utilisez Désinstaller l’app… dans ses paramètres.",
    "A lock file is a link; the app could not be removed safely.":
        "Un fichier de verrou est un lien ; impossible de supprimer l’app en toute sécurité.",
    "The uninstaller could not be started. Uninstall Blackboard Sync from Windows Settings → Apps; if needed, "
    "delete this folder yourself: {path}":
        "Le programme de désinstallation n’a pas pu démarrer. Désinstallez Blackboard Sync depuis Paramètres "
        "Windows → Applications ; si nécessaire, supprimez vous-même ce dossier : {path}",
    "The app could not be removed; delete it yourself: {error}":
        "Impossible de supprimer l’app ; supprimez-la vous-même : {error}",
    "Could not move an empty folder to the Trash: {path} ({error})":
        "Impossible de placer un dossier vide dans la Corbeille : {path} ({error})",
    "Could not delete a lock file: {name} ({error})": "Impossible de supprimer un fichier de verrou : {name} ({error})",
    "The app could not be moved to the Trash. Delete it in Finder yourself: {path}":
        "Impossible de placer l’app dans la Corbeille. Supprimez-la vous-même dans le Finder : {path}",
    "Could not move a file to the Trash: {path} ({error})":
        "Impossible de placer un fichier dans la Corbeille : {path} ({error})",
    "Could not clear the sign-in data: {error}": "Impossible d’effacer les données de connexion : {error}",
    "Could not remove the start-at-login entry: {error}":
        "Impossible de supprimer le lancement à l’ouverture de session : {error}",
    "Could not clear the app data folder: {path} ({error})":
        "Impossible de vider le dossier de données de l’app : {path} ({error})",
    "Could not move the course files to the Trash: {error}":
        "Impossible de placer les fichiers de cours dans la Corbeille : {error}",
    "Could not delete app data: {path}": "Impossible de supprimer les données de l’app : {path}",
    "The Recycle Bin API could not be loaded; the file was kept.":
        "Impossible de charger l’API de la Corbeille ; le fichier a été conservé.",
    "The file could not be moved to the Recycle Bin; it was kept.":
        "Impossible de placer le fichier dans la Corbeille ; il a été conservé.",
    "The file cannot be recycled; permanent deletion was cancelled.":
        "Le fichier ne peut pas aller dans la Corbeille ; la suppression définitive a été annulée.",
    "The Recycle Bin operation failed: {error}": "L’opération de la Corbeille a échoué : {error}",

    # Updates
    "The update cannot be installed while a sync or a folder move runs; try again once it has finished.":
        "Impossible d’installer la mise à jour pendant une synchronisation ou un déplacement de dossier ; "
        "réessayez une fois l’opération terminée.",
    "the current version is kept.": "la version actuelle est conservée.",
    "Blackboard Sync runs from its disk image, so it cannot update itself.":
        "Blackboard Sync s’exécute depuis son image disque et ne peut donc pas se mettre à jour.",
    "macOS runs Blackboard Sync from a temporary location, so the app cannot update itself.":
        "macOS exécute Blackboard Sync depuis un emplacement temporaire, l’app ne peut donc pas se mettre à "
        "jour.",
    "The folder Blackboard Sync is in cannot be written to, so the app cannot update itself.":
        "Le dossier de Blackboard Sync n’est pas accessible en écriture, l’app ne peut donc pas se mettre à "
        "jour.",
    "This version is unsigned, so the update cannot be verified and installed automatically.":
        "Cette version n’est pas signée : la mise à jour ne peut pas être vérifiée et installée "
        "automatiquement.",
    "The update's disk image could not be opened;": "Impossible d’ouvrir l’image disque de la mise à jour ;",
    "Blackboard Sync was not found in the disk image;": "Blackboard Sync est introuvable dans l’image disque ;",
    "The downloaded update is not the expected Blackboard Sync version;":
        "La mise à jour téléchargée n’est pas la version de Blackboard Sync attendue ;",
    "The update's signature is not valid;": "La signature de la mise à jour n’est pas valide ;",
    "The update is not signed by the Blackboard Sync developer;":
        "La mise à jour n’est pas signée par le développeur de Blackboard Sync ;",
    "The update is not notarized by Apple;": "La mise à jour n’est pas notarisée par Apple ;",
    "The new version could not be copied;": "Impossible de copier la nouvelle version ;",
    "The update could not be started;": "Impossible de lancer la mise à jour ;",
    "Updates are installed through the Microsoft Store.": "Les mises à jour sont installées via le Microsoft Store.",
    "The update could not be verified.": "Impossible de vérifier la mise à jour.",
    "The update does not come from this app's page; it was not downloaded.":
        "La mise à jour ne provient pas de la page de cette app ; elle n’a pas été téléchargée.",
    "The downloaded update could not be verified; it was not installed.":
        "Impossible de vérifier la mise à jour téléchargée ; elle n’a pas été installée.",
    "The update could not be downloaded; check your internet connection.":
        "Impossible de télécharger la mise à jour ; vérifiez votre connexion Internet.",
    "The update could not be downloaded.": "Impossible de télécharger la mise à jour.",
    "Google Calendar needs to be reconnected": "Google Calendar doit être reconnecté",
    "Google Calendar authorization state did not match.": "L’état d’autorisation Google Calendar ne correspond pas.",
    "Google Calendar authorization was cancelled.": "L’autorisation Google Calendar a été annulée.",
    "Google Calendar operation was cancelled.": "L’opération Google Calendar a été annulée.",
    "Set BBSYNC_GOOGLE_CLIENT_ID to your Desktop OAuth client ID.":
        "Définissez BBSYNC_GOOGLE_CLIENT_ID sur l’ID de votre client OAuth de bureau.",
    "A Google Calendar operation is already running.": "Une opération Google Calendar est déjà en cours.",
    "Could not access the Google Calendar credential store.":
        "Impossible d’accéder au stockage des identifiants Google Calendar.",
    "Could not open the browser for Google Calendar.": "Impossible d’ouvrir le navigateur pour Google Calendar.",
    "The saved Google Calendar is not a dedicated secondary calendar.":
        "L’agenda Google Calendar enregistré n’est pas un agenda secondaire dédié.",
    "Sync Blackboard successfully before syncing Google Calendar.":
        "Synchronisez Blackboard avec succès avant de synchroniser Google Calendar.",
    "Google Calendar sync failed.": "La synchronisation Google Calendar a échoué.",
    "Could not reach Google Calendar.": "Impossible de joindre Google Calendar.",
    "Google Calendar authorization timed out.": "Le délai d’autorisation Google Calendar a expiré.",
    "You can close this browser window and return to Blackboard Sync.":
        "Vous pouvez fermer cette fenêtre du navigateur et revenir à Blackboard Sync.",
    "This event is managed by Blackboard Sync.": "Cet événement est géré par Blackboard Sync.",
    "Google Calendar operation failed.": "L’opération Google Calendar a échoué.",
    "Disconnect Google Calendar?": "Déconnecter Google Calendar ?",
    "Access will be revoked and local Calendar connection data removed.":
        "L’accès sera révoqué et les données locales de connexion à l’agenda seront supprimées.",
    "Disconnect": "Déconnecter",
    "Also delete the Blackboard Deadlines calendar from Google": "Supprimer aussi l’agenda Blackboard Deadlines de Google",
    "Reconnect": "Reconnecter",
    "Google Calendar error": "Erreur Google Calendar",
    "Not connected": "Non connecté",
    "Connect to see Blackboard deadlines in Google Calendar.":
        "Connectez-vous pour voir les échéances Blackboard dans Google Calendar.",
    "Connect Google Calendar": "Connecter Google Calendar",
    "Google Calendar operation in progress…": "Opération Google Calendar en cours…",
    "You can cancel while authorization is waiting in the browser.":
        "Vous pouvez annuler pendant que l’autorisation attend dans le navigateur.",
    "Connected": "Connecté",
    "Google Calendar": "Google Calendar",
    "Calendar has not synced yet.": "L’agenda n’a pas encore été synchronisé.",
    "Sends deadlines to a dedicated Blackboard Deadlines calendar. Your other calendars stay private.":
        "Envoie les échéances vers un agenda Blackboard Deadlines dédié. Vos autres agendas restent privés.",
    "Sync calendar now": "Synchroniser l’agenda",
    "Disconnect Google Calendar": "Déconnecter Google Calendar",
    "Last calendar sync: {time}": "Dernière synchro de l’agenda : {time}",
    "Google Calendar returned an invalid response.": "Google Calendar a renvoyé une réponse non valide.",
    "Google requires this Desktop client's secret. Set BBSYNC_GOOGLE_CLIENT_SECRET locally and connect again.":
        "Google exige le secret de ce client de bureau. Définissez BBSYNC_GOOGLE_CLIENT_SECRET localement et "
        "reconnectez-vous.",
    "The calendar's saved ID is missing. Delete the existing Blackboard Deadlines calendar in Google Calendar settings.":
        "L’ID enregistré de l’agenda est manquant. Supprimez l’agenda Blackboard Deadlines existant dans les "
        "paramètres de Google Calendar.",
    "Please wait for the calendar operation to finish.": "Veuillez attendre la fin de l’opération sur l’agenda.",
    # Settings → Appearance (the Windows window)
    "Appearance": "Apparence",
    "Theme": "Thème",
    "System follows the light or dark mode chosen in Windows.":
        "Système suit le mode clair ou sombre choisi dans Windows.",
    "System": "Système",
    "Light": "Clair",
    "Dark": "Sombre",

    # Settings → AI assistant (ai_launcher)
    "AI assistant": "Assistant IA",
    "Continue my last session in this folder": "Reprendre ma dernière session dans ce dossier",
    "When it is off, a new session starts every time.": "Si désactivé, une nouvelle session démarre à chaque fois.",
    "The app only opens a terminal in your course folder. The AI tool runs with your own account and its own "
    "rules.":
        "L’app ouvre seulement un terminal dans votre dossier de cours. L’outil d’IA fonctionne avec votre "
        "propre compte et ses propres règles.",
    "No earlier session here, starting a new one.": "Aucune session précédente ici, démarrage d’une nouvelle.",
    "AI study session": "Réviser avec l’IA",
    "Click a tool to open {term}, continuing your last session there.":
        "Cliquez sur un outil pour ouvrir {term} et y reprendre votre dernière session.",
    "Click a tool to open {term} in a new session.":
        "Cliquez sur un outil pour ouvrir {term} dans une nouvelle session.",
    "Looking for AI tools…": "Recherche d’outils d’IA…",
    "Terminal": "Terminal",
    "The terminal app that opens for AI tools.": "L’app de terminal qui s’ouvre pour les outils d’IA.",
    "Command Prompt": "Invite de commandes",
    "No AI tool is installed. Install Claude Code, Gemini CLI, Codex or Antigravity, then try again.":
        "Aucun outil d’IA n’est installé. Installez Claude Code, Gemini CLI, Codex ou Antigravity, puis "
        "réessayez.",
    "{name} wasn't found. Using {default} instead.": "{name} est introuvable. {default} est utilisé à la place.",
    "Open in {name}": "Ouvrir dans {name}",
    "Opening…": "Ouverture…",
    "{name} is not installed. Install it, then try again.": "{name} n’est pas installé. Installez-le, puis réessayez.",
    "How to install": "Comment l’installer",
    "Try again": "Réessayer",
    "The {term} folder isn't there yet. Sync first.": "Le dossier {term} n’existe pas encore. Synchronisez d’abord.",
    "Could not open a terminal: {error}": "Impossible d’ouvrir un terminal : {error}",
    "Could not open a terminal.": "Impossible d’ouvrir un terminal.",
    "Open {name} in {term}": "Ouvrir {name} dans {term}",

    # NotebookLM
    "Sign in to Google again to keep adding files.": "Reconnectez-vous à Google pour continuer à ajouter des fichiers.",
    "Disconnect Gemini Notebook?": "Déconnecter Gemini Notebook ?",
    "The Google session is deleted from this computer. Files already in Gemini Notebook stay there, and new ones "
    "are no longer added.":
        "La session Google est supprimée de cet ordinateur. Les fichiers déjà dans Gemini Notebook y restent, "
        "et les nouveaux ne sont plus ajoutés.",
    "Connect Gemini Notebook": "Connecter Gemini Notebook",
    "Your course files are added after each sync.": "Vos fichiers de cours sont ajoutés après chaque synchro.",
    "Checking what is already in Gemini Notebook…": "Vérification du contenu de Gemini Notebook…",
    "Sign in to Google in the browser window.": "Connectez-vous à Google dans la fenêtre du navigateur.",
    "Adding {done} of {total}: {file}": "Ajout {done} sur {total} : {file}",
    "Gemini Notebook is reading the new files…": "Gemini Notebook lit les nouveaux fichiers…",
    "All your files are already in Gemini Notebook": "Tous vos fichiers sont déjà dans Gemini Notebook",
    "Checking the connection…": "Vérification de la connexion…",
    "Google took the sign-in, but Gemini Notebook did not open. Try again.":
        "Google a accepté la connexion, mais Gemini Notebook ne s’est pas ouvert. Réessayez.",
    "{n} new file added to your notebooks": "{n} nouveau fichier ajouté à vos notebooks",
    "{n} new files added to your notebooks": "{n} nouveaux fichiers ajoutés à vos notebooks",
    "No new files were added": "Aucun nouveau fichier ajouté",
    "Last checked: {time}": "Dernière vérification : {time}",
    "{n} course blocked": "{n} cours bloqué",
    "{n} courses blocked": "{n} cours bloqués",
    "{n} failed": "{n} en échec",
    "Add new files to Gemini Notebook after each sync":
        "Ajouter les nouveaux fichiers à Gemini Notebook après chaque synchro",
    "Disconnect Gemini Notebook": "Déconnecter Gemini Notebook",
    "Files in Gemini Notebook stay there.": "Les fichiers dans Gemini Notebook y restent.",
    "Unofficial connection: it may stop working if Google changes Gemini Notebook.":
        "Connexion non officielle : elle peut cesser de fonctionner si Google modifie Gemini Notebook.",
    "{course}: {n} over the {limit} source limit; nothing added.":
        "{course} : {n} au-delà de la limite de {limit} sources ; rien n’a été ajouté.",
    "{course}: several notebooks have this name, so it was skipped.":
        "{course} : plusieurs notebooks portent ce nom, le cours a donc été ignoré.",
    "{n} file could not be added; the next sync tries again.":
        "{n} fichier n’a pas pu être ajouté ; la prochaine synchro réessaiera.",
    "{n} files could not be added; the next sync tries again.":
        "{n} fichiers n’ont pas pu être ajoutés ; la prochaine synchro réessaiera.",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and try again.":
        "Le navigateur n’a pas démarré. Si une fenêtre de connexion d’une tentative précédente est encore "
        "ouverte, fermez-la et réessayez.",
    "Gemini Notebook needs Chrome, Edge or Brave to sign in to Google; install one and try again.":
        "Gemini Notebook a besoin de Chrome, Edge ou Brave pour se connecter à Google ; installez-en un et "
        "réessayez.",

    # Store trial and purchase (licensing)
    "Purchases are not available in this build.": "Les achats ne sont pas disponibles dans cette version.",
    "Could not reach the Microsoft Store. Check your internet connection and try again.":
        "Impossible de joindre le Microsoft Store. Vérifiez votre connexion internet et réessayez.",
    "Could not complete the purchase in the Microsoft Store. Try again in a moment.":
        "Impossible de finaliser l’achat dans le Microsoft Store. Réessayez dans un instant.",
    "No purchase was found for this account yet.": "Aucun achat n’a encore été trouvé pour ce compte.",
    "Free trial ended": "Essai gratuit terminé",
    "{n} minute left": "{n} minute restante",
    "{n} minutes left": "{n} minutes restantes",
    "{n} hour left": "{n} heure restante",
    "{n} hours left": "{n} heures restantes",
    "{n} day left": "{n} jour restant",
    "{n} days left": "{n} jours restants",
    "Free trial · {remaining}": "Essai gratuit · {remaining}",
    "Free trial": "Essai gratuit",
    "Buy": "Acheter",
    "Buy for {price}": "Acheter pour {price}",
    "Opening Store…": "Ouverture de la boutique…",
    "Your free trial has ended": "Votre essai gratuit est terminé",
    "Buy Blackboard Sync once ({price}) to keep syncing your courses. Your downloaded files are still in your folder.":
        "Achetez Blackboard Sync une seule fois ({price}) pour continuer à synchroniser vos cours. "
        "Vos fichiers téléchargés restent dans votre dossier.",
    "Buy Blackboard Sync once to keep syncing your courses. Your downloaded files are still in your folder.":
        "Achetez Blackboard Sync une seule fois pour continuer à synchroniser vos cours. "
        "Vos fichiers téléchargés restent dans votre dossier.",
    "I already bought it": "Je l’ai déjà acheté",

    # Mac App Store (App Sandbox, folder bookmark, copy-command, demo mode)
    "Choose a folder…": "Choisissez un dossier…",
    "Choose the folder using “Choose…” so macOS grants access to it.":
        "Choisissez le dossier avec « Choisir… » pour que macOS y autorise l’accès.",
    "Click a tool to copy the terminal command for {term}.":
        "Cliquez sur un outil pour copier la commande de terminal pour {term}.",
    "Copied terminal command for {name} — paste it into Terminal.":
        "Commande de terminal copiée pour {name} — collez-la dans Terminal.",
    "Copy command for {name}": "Copier la commande pour {name}",
    "Copy {name} command for {term}": "Copier la commande {name} pour {term}",
    "Could not copy the command.": "Impossible de copier la commande.",
    # Gemini Notebook through Safari (Mac App Store build)
    "Add new course files whenever you choose.": "Ajoutez les nouveaux fichiers de vos cours quand vous le voulez.",
    "Uses your Google sign-in in Safari.": "Utilise votre connexion Google dans Safari.",
    "Opening Gemini Notebook in Safari…": "Ouverture de Gemini Notebook dans Safari…",
    "Set up in Safari": "Configurer dans Safari",
    "Turn on the Safari extension": "Activez l’extension Safari",
    "Safari > Settings > Extensions > Blackboard Sync": "Safari > Réglages > Extensions > Blackboard Sync",
    "Allow it on notebook.google.com": "Autorisez-la sur notebook.google.com",
    "Click Blackboard Sync in Safari's toolbar: Always Allow":
        "Cliquez sur Blackboard Sync dans la barre de Safari : Toujours autoriser",
    "Sign in to Google in Safari": "Connectez-vous à Google dans Safari",
    "Safari extension": "Extension Safari",
    "Turn on Blackboard Sync in Safari and allow it on notebook.google.com.":
        "Activez Blackboard Sync dans Safari et autorisez-le sur notebook.google.com.",
    "Open Safari Settings": "Ouvrir les réglages de Safari",
    "Turn on the Blackboard Sync extension in Safari, then try again.":
        "Activez l’extension Blackboard Sync dans Safari, puis réessayez.",
    "Safari did not answer. Allow Blackboard Sync on notebook.google.com in Safari, then try again.":
        "Safari n’a pas répondu. Autorisez Blackboard Sync sur notebook.google.com dans Safari, puis réessayez.",
    "Sign in to Google in Safari, then try again.": "Connectez-vous à Google dans Safari, puis réessayez.",
    "The Safari tab closed before all files were added. Sync again to go on.":
        "L’onglet Safari s’est fermé avant l’ajout de tous les fichiers. Synchronisez à nouveau pour continuer.",
    "Could not open Safari.": "Impossible d’ouvrir Safari.",
    "Try the demo": "Essayer la démo",
    "Updates are installed through the App Store.": "Les mises à jour sont installées via l’App Store.",
    "You can uninstall Blackboard Sync from Launchpad or the Applications folder.":
        "Vous pouvez désinstaller Blackboard Sync depuis le Launchpad ou le dossier Applications.",

    # Minimum-version enforcement (min_version)
    "Update required": "Mise à jour requise",
    "Update required — Update": "Mise à jour requise — Mettre à jour",
    "Updating…": "Mise à jour…",
    "Update Blackboard Sync to version {version} or newer to keep syncing your courses. Your downloaded files are still in your folder.":
        "Mettez Blackboard Sync à jour vers la version {version} ou une version plus récente pour continuer à "
        "synchroniser vos cours. Vos fichiers téléchargés restent dans votre dossier.",
    "Update Blackboard Sync to the latest version to keep syncing your courses. Your downloaded files are still in your folder.":
        "Mettez Blackboard Sync à jour vers la dernière version pour continuer à synchroniser vos cours. "
        "Vos fichiers téléchargés restent dans votre dossier.",
    "Blackboard Sync moved to the Mac App Store": "Blackboard Sync est passé sur le Mac App Store",
    "Get Blackboard Sync from the Mac App Store to keep syncing your courses. Your downloaded files are still in your folder.":
        "Téléchargez Blackboard Sync sur le Mac App Store pour continuer à synchroniser vos cours. "
        "Vos fichiers téléchargés restent dans votre dossier.",
    "Open Mac App Store": "Ouvrir le Mac App Store",
    "Could not open the Mac App Store.": "Impossible d’ouvrir le Mac App Store.",
}
