"""Spanish for every text the app shows: English text -> Spanish text.

The keys are the exact strings passed to ``i18n.tr`` / ``ntr`` in the code;
``tests/test_i18n.py`` checks that each one is here with the same ``{fields}``.
Plurals: ``ntr`` picks the one-form only for a count of 1, so "1 archivo" and
"2 archivos" (and "0 archivos") each get their own entry.
"""

CATALOG = {
    # Announcements
    "Announcements": "Anuncios",
    "Every announcement synced from your current-term courses.":
        "Todos los anuncios sincronizados de tus cursos del periodo actual.",
    "No announcements yet. They show up here once they are synced.":
        "Aún no hay anuncios. Aparecerán aquí cuando se sincronicen.",
    "No date given": "Sin fecha",
    "Open announcement": "Abrir anuncio",
    "Announcement": "Anuncio",

    # Blackboard and the command line
    "Your Blackboard session has expired.": "Tu sesión de Blackboard expiró.",
    "Blackboard redirected to a sign-in page.": "Blackboard redirigió a una página de inicio de sesión.",
    "Blackboard answered with a web page instead of data.": "Blackboard respondió con una página web en lugar de datos.",
    "Blackboard answered a download with a web page.": "Blackboard respondió a una descarga con una página web.",
    "Next: run `blackboard-sync sync` to download your courses.":
        "Siguiente paso: ejecuta `blackboard-sync sync` para descargar tus cursos.",
    "Blackboard Sync's app data was removed.": "Se eliminaron los datos de Blackboard Sync.",
    "Session OK: signed in as {name}.": "Sesión válida: sesión iniciada como {name}.",
    "Term(s): {terms}": "Periodo(s): {terms}",
    "No courses found on Blackboard, so the current term could not be determined. "
    "Your courses will be synced as soon as Blackboard lists them.":
        "No se encontraron cursos en Blackboard, así que no se pudo determinar el periodo actual. "
        "Tus cursos se sincronizarán en cuanto aparezcan en Blackboard.",
    "none found": "no se encontró ninguno",
    "Network error talking to Blackboard: {error}": "Error de red al conectar con Blackboard: {error}",
    "Unexpected error: {error}": "Error inesperado: {error}",
    "Error: {error}": "Error: {error}",
    "Run `blackboard-sync login` to sign in to Blackboard.":
        "Ejecuta `blackboard-sync login` para iniciar sesión en Blackboard.",

    # Courses
    "Courses": "Cursos",
    "This folder is a copy of Blackboard: the files of the ticked courses are matched to Blackboard on every "
    "sync, and deleted or damaged files are downloaded again. To keep files your own way, copy them to another "
    "folder.":
        "Esta carpeta es una copia de Blackboard: en cada sincronización, los archivos de los cursos marcados se "
        "igualan con Blackboard, y los archivos borrados o dañados se vuelven a descargar. Para organizar "
        "archivos a tu manera, cópialos a otra carpeta.",
    "A course you untick is no longer synced and does not show in Calendar or Announcements. Its downloaded "
    "files are not deleted. Tick it again and its missing files come right away.":
        "Un curso que desmarques deja de sincronizarse y no aparece en Calendario ni en Anuncios. Sus archivos "
        "descargados no se borran. Si lo vuelves a marcar, sus archivos faltantes llegan enseguida.",
    "Courses without a term, such as guidance or orientation pages, are not synced unless you tick them.":
        "Los cursos sin periodo, como las páginas de orientación o tutoría, no se sincronizan a menos que los marques.",
    "Your courses are listed here after the first sync.": "Tus cursos aparecerán aquí después de la primera sincronización.",
    # The card before the first download at a school whose current term is not clear
    "Check your courses before the first download": "Revisa tus cursos antes de la primera descarga",
    "Blackboard Sync could not be sure which term is current at this school. It found {terms}. "
    "Untick any course you do not want, then confirm. Nothing is downloaded until you do.":
        "Blackboard Sync no pudo determinar con certeza cuál es el periodo actual en esta institución. "
        "Encontró: {terms}. Desmarca los cursos que no quieras y luego confirma. No se descarga nada hasta que "
        "lo hagas.",
    "Confirm": "Confirmar",
    "Not now": "Ahora no",
    "Waiting for you to confirm the courses to download.": "Esperando a que confirmes los cursos que se descargarán.",

    # Calendar
    "Calendar": "Calendario",
    "Due dates are updated during a sync. Times are in this computer's local time.":
        "Las fechas de entrega se actualizan al sincronizar. Las horas están en la hora local de esta computadora.",
    "Upcoming": "Próximas",
    "Past due": "Vencidas",
    "Submissions are not checked; work you already handed in may show here too.":
        "No se revisan las entregas; aquí también pueden aparecer trabajos que ya entregaste.",
    "No due dates saved.": "No hay fechas de entrega guardadas.",
    "Sync to see due dates.": "Sincroniza para ver las fechas de entrega.",
    "Some courses' due dates could not be updated. Earlier ones are shown where there are any.":
        "No se pudieron actualizar las fechas de algunos cursos. Se muestran las anteriores, si las hay.",
    "January": "Enero",
    "February": "Febrero",
    "March": "Marzo",
    "April": "Abril",
    "May": "Mayo",
    "June": "Junio",
    "July": "Julio",
    "August": "Agosto",
    "September": "Septiembre",
    "October": "Octubre",
    "November": "Noviembre",
    "December": "Diciembre",
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
    "Due in 1 hour": "Vence en 1 hora",
    "Deadline coming up": "Se acerca una entrega",
    "Today": "Hoy",
    "Tomorrow": "Mañana",
    "{month} {day}": "{day} de {month}",
    "{month} {day}, {year}": "{day} de {month} de {year}",
    "Untitled work": "Tarea sin título",
    "today {time}": "hoy, {time}",
    "tomorrow {time}": "mañana, {time}",
    "yesterday {time}": "ayer, {time}",
    "Due: {time}": "Vence: {time}",

    # Signing in
    "Blackboard Sync – Sign in": "Blackboard Sync – Iniciar sesión",
    "The sign-in window was closed before sign-in finished.":
        "La ventana de inicio de sesión se cerró antes de terminar.",
    "The sign-in window needs the Microsoft Edge WebView2 Runtime, which is missing on this computer. Install "
    "it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 or install Google Chrome or Microsoft Edge, then "
    "sign in again.":
        "La ventana de inicio de sesión necesita Microsoft Edge WebView2 Runtime, que no está en esta "
        "computadora. Instálalo desde https://go.microsoft.com/fwlink/p/?LinkId=2124703 o instala Google Chrome "
        "o Microsoft Edge, y vuelve a iniciar sesión.",
    "Sign-in was not completed within {n} minutes.": "No se completó el inicio de sesión en {n} minutos.",
    "The sign-in window is unavailable ({error}); run ./scripts/setup.sh again or install a Chromium-based "
    "browser.":
        "La ventana de inicio de sesión no está disponible ({error}); vuelve a ejecutar ./scripts/setup.sh o "
        "instala un navegador basado en Chromium.",
    "The sign-in window is unavailable: {error}": "La ventana de inicio de sesión no está disponible: {error}",
    "Close Sign-in Window": "Cerrar ventana de inicio de sesión",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and run "
    "`blackboard-sync login` again.":
        "El navegador no se abrió. Si sigue abierta una ventana de inicio de sesión de un intento anterior, "
        "ciérrala y vuelve a ejecutar `blackboard-sync login`.",
    "Sign in to Blackboard in that window. It closes by itself once you are in.":
        "Inicia sesión en Blackboard en esa ventana. Se cerrará sola cuando entres.",
    "Could not find a supported browser (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, Opera GX, "
    "Chromium or Arc) on this computer.":
        "No se encontró un navegador compatible (Google Chrome, Microsoft Edge, Brave, Vivaldi, Opera, "
        "Opera GX, Chromium o Arc) en esta computadora.",
    "Could not find {browser} on this computer.": "No se encontró {browser} en esta computadora.",
    "Signed in as {name}; session saved ({n} cookies).":
        "Sesión iniciada como {name}; sesión guardada ({n} cookies).",
    "Opening {browser} on {url} ...": "Abriendo {browser} en {url}...",
    "Opening the sign-in window on {url} ...": "Abriendo la ventana de inicio de sesión en {url}...",
    "The browser was closed before sign-in finished.": "El navegador se cerró antes de terminar el inicio de sesión.",
    "The browser window was closed before sign-in finished.":
        "La ventana del navegador se cerró antes de terminar el inicio de sesión.",
    "Playwright is not installed; see the README's setup steps.":
        "Playwright no está instalado; consulta los pasos de instalación del README.",
    "Unknown browser {name}; use {choices}.": "Navegador desconocido: {name}; usa uno de estos: {choices}.",
    "Could not open {browser}: {error}": "No se pudo abrir {browser}: {error}",
    "Using the app's own sign-in window instead.": "Se usará la ventana de inicio de sesión de la app.",
    "Could not connect to {browser}: {error}": "No se pudo conectar con {browser}: {error}",
    "Could not start the browser connection: {error}": "No se pudo iniciar la conexión con el navegador: {error}",
    "You are not signed in yet.": "Aún no has iniciado sesión.",
    "The saved session could not be read.": "No se pudo leer la sesión guardada.",
    "The saved session belongs to {url}.": "La sesión guardada pertenece a {url}.",
    "Some sign-in data could not be removed; close the sign-in browser if it is still open and sign out again.":
        "No se pudieron borrar algunos datos de inicio de sesión; cierra el navegador de inicio de sesión si "
        "sigue abierto y vuelve a cerrar sesión.",

    # macOS menus
    "Edit": "Edición",
    "Window": "Ventana",
    "Hide Blackboard Sync": "Ocultar Blackboard Sync",
    "Hide Others": "Ocultar otros",
    "Show All": "Mostrar todo",
    "Quit Blackboard Sync": "Salir de Blackboard Sync",
    "Undo": "Deshacer",
    "Redo": "Rehacer",
    "Cut": "Cortar",
    "Copy": "Copiar",
    "Paste": "Pegar",
    "Select All": "Seleccionar todo",
    "Minimize": "Minimizar",
    "Close": "Cerrar",

    # The menu bar / tray app
    "Blackboard Sync": "Blackboard Sync",
    "Blackboard Sync: syncing": "Blackboard Sync: sincronizando",
    "Blackboard Sync: session expired": "Blackboard Sync: sesión expirada",
    "Blackboard Sync: error": "Blackboard Sync: error",
    "Blackboard Sync: paused": "Blackboard Sync: en pausa",
    "Blackboard Sync {version} downloaded": "Blackboard Sync {version} descargado",
    "In the window that opened, drag “Blackboard Sync” onto the “Applications” folder and choose “Replace” to "
    "put it in place of the old version. Quit Blackboard Sync first, then open the app again from the "
    "Applications folder. Your settings and downloaded course files are kept.":
        "En la ventana que se abrió, arrastra “Blackboard Sync” a la carpeta “Applications” y elige “Reemplazar” "
        "para sustituir la versión anterior. Primero sal de Blackboard Sync y luego vuelve a abrir la app desde "
        "la carpeta Aplicaciones. Se conservan tus ajustes y los archivos de tus cursos.",
    "File not found.": "No se encontró el archivo.",
    "Could not install the update.": "No se pudo instalar la actualización.",
    "Could not install the update": "No se pudo instalar la actualización",
    "Could not change the start-at-login setting.": "No se pudo cambiar el ajuste de inicio automático.",
    "Could not restart Blackboard Sync; quit it and open it again.":
        "No se pudo reiniciar Blackboard Sync; sal de la app y vuelve a abrirla.",
    "Sign out?": "¿Cerrar sesión?",
    "All sign-in data is removed; you will need to enter your school details again to sign in. Your downloaded "
    "files are kept.":
        "Se borrarán todos los datos de inicio de sesión; tendrás que volver a ingresar los datos de tu "
        "institución para iniciar sesión. Tus archivos descargados se conservan.",
    "Could not sign out.": "No se pudo cerrar sesión.",
    "The update cannot be installed now": "La actualización no se puede instalar ahora",
    "Later": "Más tarde",
    "The {folder} folder does not exist yet; sync first.":
        "La carpeta {folder} aún no existe; sincroniza primero.",
    "Sign out": "Cerrar sesión",
    "Cancel": "Cancelar",
    "Could not save the update: {error}": "No se pudo guardar la actualización: {error}",
    "Could not save the course choice: {error}": "No se pudo guardar la selección de cursos: {error}",
    "Could not save the settings: {error}": "No se pudieron guardar los ajustes: {error}",
    "timed out": "tiempo agotado",
    "Upcoming deadlines": "Próximas entregas",
    "The sync took too long and was stopped.": "La sincronización tardó demasiado y se detuvo.",
    "exit status {code}": "código de salida {code}",
    "Could not start the menu bar app: {error}": "No se pudo iniciar la app de la barra de menús: {error}",
    "Blackboard Sync is running in the background": "Blackboard Sync se está ejecutando en segundo plano",
    "Right-click the Blackboard Sync icon next to the clock for the menu. If you don't see it, click the ^ "
    "arrow that shows hidden icons.":
        "Haz clic derecho en el icono de Blackboard Sync junto al reloj para ver el menú. Si no lo ves, haz "
        "clic en la flecha ^ que muestra los iconos ocultos.",
    "Wait for the running job to finish before updating, then try again.":
        "Espera a que termine la tarea en curso antes de actualizar y vuelve a intentarlo.",
    "Could not open the announcement.": "No se pudo abrir el anuncio.",
    "The file or folder does not exist yet; sync first.":
        "El archivo o la carpeta aún no existe; sincroniza primero.",
    "Could not open the file or folder.": "No se pudo abrir el archivo o la carpeta.",
    "Blackboard Sync stopped because of an unexpected error.":
        "Blackboard Sync se detuvo por un error inesperado.",
    "The details are in this file:\n{path}": "Los detalles están en este archivo:\n{path}",

    # The main window
    "Applications or Launchpad": "Aplicaciones o Launchpad",
    "the Start menu": "el menú Inicio",
    "Uninstall": "Desinstalar",
    "The folder whose files go to the Trash:": "Carpeta cuyos archivos irán a la Papelera:",
    "The folder whose files go to the Recycle Bin:": "Carpeta cuyos archivos irán a la Papelera de reciclaje:",
    "Open the downloaded note": "Abrir la nota descargada",
    "Open in Blackboard": "Abrir en Blackboard",
    "Get started": "Comenzar",
    "Home": "Inicio",
    "Sync activity": "Actividad",
    "Settings": "Ajustes",
    "Your course files start here.": "Tus archivos de cursos empiezan aquí.",
    "Connect your Blackboard account and your course files come to this computer by themselves; no more "
    "checking the site every time.":
        "Conecta tu cuenta de Blackboard y los archivos de tus cursos llegarán solos a esta computadora; ya no "
        "tendrás que revisar el sitio cada vez.",
    "Let's get started": "Empecemos",
    "Open folder": "Abrir carpeta",
    "NEW": "NUEVO",
    "Update": "Actualizar",
    "Update to get the latest version.": "Actualiza para tener la versión más reciente.",
    "Syncing": "Sincronizando",
    "Session expired": "Sesión expirada",
    "Not signed in": "Sin sesión",
    "Waiting for sign-in": "Esperando inicio de sesión",
    "Not synced yet": "Sin sincronizar",
    "Downloading your files for the first time…": "Descargando tus archivos por primera vez…",
    "Unsaved changes": "Cambios sin guardar",
    "View all": "Ver todo",
    "Open": "Abrir",
    "Show in folder": "Mostrar en carpeta",
    "Recent downloads": "Descargas recientes",
    "Open calendar": "Abrir calendario",
    "No upcoming deadlines.": "No hay entregas próximas.",
    "Nothing downloaded yet.": "Aún no se ha descargado nada.",
    "Pause": "Pausar",
    "Up to date": "Al día",
    "Syncing…": "Sincronizando…",
    "Paused": "En pausa",
    "Sign-in needed": "Inicia sesión",
    "Sync did not finish": "Sincronización incompleta",
    "Sync did not finish: {error}": "Sincronización incompleta: {error}",
    "Name": "Nombre",
    "File size": "Tamaño",
    "Status": "Estado",
    "Good morning": "Buenos días",
    "Good afternoon": "Buenas tardes",
    "Good evening": "Buenas noches",
    "{greeting}, {name}": "{greeting}, {name}",
    "No deadlines this week": "Sin entregas esta semana",
    "{n} deadline this week": "{n} entrega esta semana",
    "{n} deadlines this week": "{n} entregas esta semana",
    "{n} deadline today": "{n} entrega hoy",
    "{n} deadlines today": "{n} entregas hoy",
    "{n} this week": "{n} esta semana",
    "Choose your school and folder": "Elige tu institución y tu carpeta",
    "You decide where the files are saved.": "Tú decides dónde se guardan los archivos.",
    "Sign in to Blackboard": "Inicia sesión en Blackboard",
    "Your school's sign-in page opens. The first sync starts after you sign in.":
        "Se abre la página de inicio de sesión de tu institución. La primera sincronización empieza al "
        "iniciar sesión.",
    "Your files stay up to date": "Tus archivos, siempre al día",
    "Every hour by default. You can change how often in Settings.":
        "Cada hora de forma predeterminada. Puedes cambiar la frecuencia en Ajustes.",
    "You can close this window. To see it again, open Blackboard Sync from {where}.":
        "Puedes cerrar esta ventana. Para volver a verla, abre Blackboard Sync desde {where}.",
    "Last synced: {time}": "Última sincronización: {time}",
    "Last attempt: {time}": "Último intento: {time}",
    "Downloading…": "Descargando…",
    "Blackboard Sync {version} is ready": "Blackboard Sync {version} ya está disponible",
    "Your internet connection seems unstable": "Tu conexión a internet parece inestable",
    "syncing": "se sincroniza",
    "not syncing": "no se sincroniza",

    # The menu and the app's state
    "Sync now": "Sincronizar",
    "Sign in": "Iniciar sesión",
    "Waiting for sign-in…": "Esperando inicio de sesión…",
    "⚠ Session expired — Sign in": "⚠ Sesión expirada — Iniciar sesión",
    "Nothing new yet": "Nada nuevo por ahora",
    "Pause syncing": "Pausar sincronización",
    "Resume syncing": "Reanudar sincronización",
    "Settings…": "Ajustes…",
    "Quit": "Salir",
    "automatic sync off": "sincronización automática desactivada",
    "Check now": "Comprobar",
    "Checking for updates…": "Buscando actualizaciones…",
    "Downloading update…": "Descargando actualización…",
    "Successfully downloaded": "Descargado",
    "Updated": "Actualizado",
    "Note saved": "Nota guardada",
    "Note updated": "Nota actualizada",
    "Announcement saved": "Anuncio guardado",
    "Announcement updated": "Anuncio actualizado",
    "Waiting for you to sign in in the browser…": "Esperando a que inicies sesión en el navegador…",
    "Waiting for you to sign in in the window that opened…": "Esperando a que inicies sesión en la ventana que se abrió…",
    "Waiting for you to sign in in {browser}…": "Esperando a que inicies sesión en {browser}…",
    "new file": "archivo nuevo",
    "new files": "archivos nuevos",
    "updated file": "archivo actualizado",
    "updated files": "archivos actualizados",
    "new note": "nota nueva",
    "new notes": "notas nuevas",
    "updated note": "nota actualizada",
    "updated notes": "notas actualizadas",
    "new announcement": "anuncio nuevo",
    "new announcements": "anuncios nuevos",
    "updated announcement": "anuncio actualizado",
    "updated announcements": "anuncios actualizados",
    "large file not downloaded": "archivo grande sin descargar",
    "large files not downloaded": "archivos grandes sin descargar",
    "nothing new": "nada nuevo",
    "{n} file": "{n} archivo",
    "{n} files": "{n} archivos",
    "{n} warning": "{n} aviso",
    "{n} file could not be downloaded": "No se pudo descargar {n} archivo",
    "{n} files could not be downloaded": "No se pudieron descargar {n} archivos",
    "{n} course could not be read": "No se pudo leer {n} curso",
    "{n} courses could not be read": "No se pudieron leer {n} cursos",
    "Something went wrong during the last sync": "Algo salió mal en la última sincronización",
    "{n} warnings": "{n} avisos",
    "({n} new)": "(nuevos: {n})",
    "No files were moved.": "No se movió ningún archivo.",
    "{files} moved to the new folder.": "Movidos a la nueva carpeta: {files}.",
    "{files} moved to the {folder} folder.": "Movidos a la carpeta {folder}: {files}.",
    "{files} could not be moved and stayed in the old folder.":
        "No se pudieron mover y siguen en la carpeta anterior: {files}.",
    "{files} could not be moved and stayed where they were.":
        "No se pudieron mover y siguen donde estaban: {files}.",
    "Open {folder} folder": "Abrir carpeta {folder}",
    "Blackboard: new content": "Blackboard: contenido nuevo",
    "Click to download the new version.": "Haz clic para descargar la nueva versión.",
    "Blackboard session expired": "La sesión de Blackboard expiró",
    "Choose “Sign in” in the menu to get new files.":
        "Elige “Iniciar sesión” en el menú para recibir archivos nuevos.",
    "Some files could not be moved": "No se pudieron mover algunos archivos",
    "Another sync is running; trying again shortly.":
        "Hay otra sincronización en curso; se volverá a intentar en breve.",
    "Another sync is running; the files will be moved shortly.":
        "Hay otra sincronización en curso; los archivos se moverán en breve.",
    "Sign in for the new school.": "Inicia sesión en la nueva institución.",
    "not synced yet": "sin sincronizar",
    "synced at {time}": "sincronizado: {time}",
    "tried at {time}": "intento: {time}",
    "tried at {time} · error": "intento: {time} · error",
    "next: {time}": "próxima: {time}",
    "soon": "pronto",
    "Checking for new content…": "Buscando contenido nuevo…",
    "Moving files to the new folder…": "Moviendo archivos a la nueva carpeta…",
    "Moving files to the {folder} folder…": "Moviendo archivos a la carpeta {folder}…",
    "Choose “{settings}” to finish setting up": "Elige “{settings}” para terminar la configuración",
    "Blackboard Sync {version} is ready — Update": "Blackboard Sync {version} disponible — Actualizar",
    "Blackboard Sync is up to date": "Blackboard Sync está al día",
    "You have the latest version ({version}).": "Tienes la versión más reciente ({version}).",
    "Your settings and downloaded course files were kept.":
        "Se conservaron tus ajustes y los archivos de tus cursos.",
    "Files moved": "Archivos movidos",
    "Files moved to the {folder} folder": "Archivos movidos a la carpeta {folder}",
    "Could not check for updates": "No se pudo buscar actualizaciones",
    "Check your internet connection and try again later.":
        "Revisa tu conexión a internet y vuelve a intentarlo más tarde.",
    "Blackboard Sync {version} could not be put in place; version {current} is still in use.":
        "No se pudo instalar Blackboard Sync {version}; se sigue usando la versión {current}.",
    "Blackboard Sync was updated to {version}": "Blackboard Sync se actualizó a la versión {version}",
    "Update available: {version} — Update": "Actualización disponible: {version} — Actualizar",
    "Could not move the files: {error}": "No se pudieron mover los archivos: {error}",
    "Sign-in did not finish: {error}": "No se completó el inicio de sesión: {error}",
    "No courses yet": "Aún no hay cursos",
    "Blackboard: no courses found": "Blackboard: no se encontraron cursos",
    "no courses found": "no se encontraron cursos",

    # Settings
    "Automatic sync": "Sincronización automática",
    "Every 30 minutes": "Cada 30 minutos",
    "Every hour": "Cada hora",
    "Every 3 hours": "Cada 3 horas",
    "Only manually": "Solo manual",
    "Language": "Idioma",
    "Danger zone": "Zona de peligro",
    "How often Blackboard is checked for new files.": "Con qué frecuencia se buscan archivos nuevos en Blackboard.",
    "Keeps syncing in the background after you sign in to the computer.":
        "Sigue sincronizando en segundo plano cuando inicias sesión en la computadora.",
    "Looks for a new version once a day.": "Busca una versión nueva una vez al día.",
    "Uninstall Blackboard Sync": "Desinstalar Blackboard Sync",
    "Restart Blackboard Sync to change the language?": "¿Reiniciar Blackboard Sync para cambiar el idioma?",
    "The new language is used once the app starts again.": "El nuevo idioma se aplicará cuando la app vuelva a iniciarse.",
    "Restart now": "Reiniciar ahora",
    "Account": "Cuenta",
    "Folder": "Carpeta",
    "Sync": "Sincronización",
    "Updates": "Actualizaciones",
    "Your school's Blackboard address": "Dirección de Blackboard de tu institución",
    "School name or https://blackboard.school.edu": "Institución o https://blackboard.uni.edu",
    "If you change the address you need to sign in again for the new school.":
        "Si cambias la dirección, tendrás que volver a iniciar sesión en la nueva institución.",
    "Folder to save files in": "Carpeta donde guardar los archivos",
    "Files are saved in the University folder inside the folder you choose.":
        "Los archivos se guardan en la carpeta University dentro de la carpeta que elijas.",
    "If you change the folder you can move the downloaded files to the new one or download them again.":
        "Si cambias la carpeta, puedes mover los archivos descargados a la nueva o volver a descargarlos.",
    "Start when the computer starts": "Abrir al iniciar la computadora",
    "Check for updates automatically": "Buscar actualizaciones automáticamente",
    "Automatic re-sign-in": "Volver a iniciar sesión automáticamente",
    "Keeps your session alive and signs in again in the background when your school allows it. Your password is never stored.":
        "Mantiene tu sesión activa y vuelve a iniciarla en segundo plano cuando tu institución lo permite. "
        "Tu contraseña nunca se guarda.",
    "Session refreshed automatically": "Sesión renovada automáticamente",
    "Could not refresh the session without you: {reason}": "No se pudo renovar la sesión sin tu ayuda: {reason}",
    "Another sign-in is in progress; try again in a minute.":
        "Hay otro inicio de sesión en curso; vuelve a intentarlo en un minuto.",
    "Choose…": "Elegir…",
    "Use this folder": "Usar esta carpeta",
    "Choose the folder to save your course files in.": "Elige la carpeta donde guardar los archivos de tus cursos.",
    "Save": "Guardar",
    "Wait for the running job to finish first.": "Primero espera a que termine la tarea en curso.",
    "The folder was not changed.": "No se cambió la carpeta.",
    "What should happen to the downloaded files?": "¿Qué hacemos con los archivos descargados?",
    "Move": "Mover",
    "Download again": "Volver a descargar",
    "“{folder}” holds {n} file downloaded from Blackboard.":
        "“{folder}” contiene {n} archivo descargado de Blackboard.",
    "“{folder}” holds {n} files downloaded from Blackboard.":
        "“{folder}” contiene {n} archivos descargados de Blackboard.",
    "{move}: the files are moved to “{folder}”, not downloaded again. Files you added yourself stay in the old "
    "folder.":
        "{move}: los archivos se mueven a “{folder}”, sin volver a descargarlos. Los archivos que agregaste tú "
        "se quedan en la carpeta anterior.",
    "{redownload}: the files are downloaded again into the new folder; the old folder is not touched.":
        "{redownload}: los archivos se vuelven a descargar en la nueva carpeta; la anterior no se modifica.",
    "Checking…": "Comprobando…",
    "Your session expired; sign in again.": "Tu sesión expiró; vuelve a iniciar sesión.",
    "Not signed in yet.": "Aún no has iniciado sesión.",
    "Version {version}": "Versión {version}",
    "Signed in as {name}": "Sesión iniciada como {name}",
    "Update to {version}": "Actualizar a {version}",
    "Enter a valid address, for example https://blackboard.school.edu":
        "Escribe una dirección válida, por ejemplo https://blackboard.universidad.edu",
    "Enter your school's Blackboard address.": "Escribe la dirección de Blackboard de tu institución.",
    "The address must start with https://.": "La dirección debe empezar con https://.",
    "Choose the folder to save the files in.": "Elige la carpeta donde guardar los archivos.",
    "Enter the folder's full path, for example ~/Documents/University":
        "Escribe la ruta completa de la carpeta, por ejemplo ~/Documents/University",
    "This path is not a folder.": "Esta ruta no es una carpeta.",

    # The sync report
    "Would sync {n} course(s) for {terms} into {folder}":
        "Se sincronizarían {n} curso(s) de {terms} en {folder}",
    "Synced {n} course(s) for {terms} into {folder}": "Se sincronizaron {n} curso(s) de {terms} en {folder}",
    "Nothing new.": "Nada nuevo.",
    "no changes": "sin cambios",
    "Moved {n} file(s) into {folder}": "Se movieron {n} archivo(s) a {folder}",
    "{n} file(s) could not be moved and stayed where they were:":
        "No se pudieron mover {n} archivo(s), que siguen donde estaban:",
    "no term": "sin periodo",
    "{n} course(s) had changes.": "Hubo cambios en {n} curso(s).",

    # The sync
    "Could not read {name} ({error}); moved it to {saved} and continued with an empty state. Files already on "
    "disk that match Blackboard's copy are kept as they are, not duplicated.":
        "No se pudo leer {name} ({error}); se movió a {saved} y se continuó con un registro vacío. Los archivos "
        "del disco que coinciden con la copia de Blackboard se conservan tal cual, sin duplicarse.",
    "Could not read {name} ({error}); it would be set aside on a real sync.":
        "No se pudo leer {name} ({error}); en una sincronización real se apartaría.",
    "Blackboard did not identify the signed-in user.": "Blackboard no identificó al usuario que inició sesión.",
    "Another blackboard-sync run is already in progress.": "Ya hay otra ejecución de blackboard-sync en curso.",
    "Kept folder {old}: could not rename it to {new} because that folder already exists. Move your files into "
    "one of them to finish.":
        "Se conservó la carpeta {old}: no se pudo cambiar su nombre a {new} porque esa carpeta ya existe. Mueve "
        "tus archivos a una de las dos para terminar.",
    "Kept folder {old}: could not rename it to {new} ({error}).":
        "Se conservó la carpeta {old}: no se pudo cambiar su nombre a {new} ({error}).",
    "Could not read course content: {error}": "No se pudo leer el contenido del curso: {error}",
    "Could not sync announcements: {error}": "No se pudieron sincronizar los anuncios: {error}",
    "Could not read due dates: {error}": "No se pudieron leer las fechas de entrega: {error}",
    "Could not read term {term}; using its id as folder name.":
        "No se pudo leer el periodo {term}; se usa su ID como nombre de carpeta.",
    "Skipped course {course}: {error}": "Se omitió el curso {course}: {error}",
    "Could not open folder {name}: {error}": "No se pudo abrir la carpeta {name}: {error}",
    "Skipped {name}: {error}": "Se omitió {name}: {error}",

    # Uninstalling
    "Uninstall Blackboard Sync?": "¿Desinstalar Blackboard Sync?",
    "Uninstall app…": "Desinstalar app…",
    "Also delete the downloaded course files": "Borrar también los archivos de cursos descargados",
    "The app and all of its records, logs, settings and sign-in data are removed, and so is its start-at-login "
    "entry. Downloaded course files are kept unless you tick this option.":
        "Se eliminan la app y todos sus registros, logs, ajustes y datos de inicio de sesión, además de su "
        "inicio automático. Los archivos de cursos descargados se conservan, a menos que marques esta opción.",
    "Wait for the sync or the folder move to finish before uninstalling.":
        "Espera a que termine la sincronización o el traslado de la carpeta antes de desinstalar.",
    "You can uninstall Blackboard Sync from Windows Settings → Apps.":
        "Puedes desinstalar Blackboard Sync desde Configuración de Windows → Aplicaciones.",
    "Remove the app's files yourself.": "Elimina los archivos de la app manualmente.",
    "The download records could not be read; the course files were kept to be safe.":
        "No se pudieron leer los registros de descarga; por seguridad, se conservaron los archivos de los cursos.",
    "The app data folder contains the download folder or the home folder; uninstall cancelled.":
        "La carpeta de datos de la app contiene la carpeta de descargas o la carpeta personal; se canceló la "
        "desinstalación.",
    "Quit Blackboard Sync first, or use Uninstall app… in its settings.":
        "Primero sal de Blackboard Sync o usa Desinstalar app… en sus ajustes.",
    "A lock file is a link; the app could not be removed safely.":
        "Un archivo de bloqueo es un enlace; no se pudo eliminar la app de forma segura.",
    "The uninstaller could not be started. Uninstall Blackboard Sync from Windows Settings → Apps; if needed, "
    "delete this folder yourself: {path}":
        "No se pudo iniciar el desinstalador. Desinstala Blackboard Sync desde Configuración de Windows → "
        "Aplicaciones; si hace falta, borra esta carpeta manualmente: {path}",
    "The app could not be removed; delete it yourself: {error}":
        "No se pudo eliminar la app; bórrala manualmente: {error}",
    "Could not move an empty folder to the Trash: {path} ({error})":
        "No se pudo mover una carpeta vacía a la Papelera: {path} ({error})",
    "Could not delete a lock file: {name} ({error})": "No se pudo borrar un archivo de bloqueo: {name} ({error})",
    "The app could not be moved to the Trash. Delete it in Finder yourself: {path}":
        "No se pudo mover la app a la Papelera. Bórrala manualmente en Finder: {path}",
    "Could not move a file to the Trash: {path} ({error})":
        "No se pudo mover un archivo a la Papelera: {path} ({error})",
    "Could not clear the sign-in data: {error}": "No se pudieron borrar los datos de inicio de sesión: {error}",
    "Could not remove the start-at-login entry: {error}": "No se pudo quitar el inicio automático: {error}",
    "Could not clear the app data folder: {path} ({error})":
        "No se pudo vaciar la carpeta de datos de la app: {path} ({error})",
    "Could not move the course files to the Trash: {error}":
        "No se pudieron mover los archivos de cursos a la Papelera: {error}",
    "Could not delete app data: {path}": "No se pudieron borrar los datos de la app: {path}",
    "The Recycle Bin API could not be loaded; the file was kept.":
        "No se pudo cargar la API de la Papelera de reciclaje; se conservó el archivo.",
    "The file could not be moved to the Recycle Bin; it was kept.":
        "No se pudo mover el archivo a la Papelera de reciclaje; se conservó.",
    "The file cannot be recycled; permanent deletion was cancelled.":
        "El archivo no se puede enviar a la papelera; se canceló el borrado permanente.",
    "The Recycle Bin operation failed: {error}": "Falló la operación de la Papelera de reciclaje: {error}",

    # Updates
    "The update cannot be installed while a sync or a folder move runs; try again once it has finished.":
        "La actualización no se puede instalar mientras hay una sincronización o un traslado de carpeta en curso; "
        "vuelve a intentarlo cuando termine.",
    "the current version is kept.": "se mantiene la versión actual.",
    "Blackboard Sync runs from its disk image, so it cannot update itself.":
        "Blackboard Sync se está ejecutando desde su imagen de disco, así que no puede actualizarse sola.",
    "macOS runs Blackboard Sync from a temporary location, so the app cannot update itself.":
        "macOS ejecuta Blackboard Sync desde una ubicación temporal, así que la app no puede actualizarse sola.",
    "The folder Blackboard Sync is in cannot be written to, so the app cannot update itself.":
        "No se puede escribir en la carpeta donde está Blackboard Sync, así que la app no puede actualizarse sola.",
    "This version is unsigned, so the update cannot be verified and installed automatically.":
        "Esta versión no está firmada, así que la actualización no se puede verificar ni instalar automáticamente.",
    "The update's disk image could not be opened;": "No se pudo abrir la imagen de disco de la actualización;",
    "Blackboard Sync was not found in the disk image;": "No se encontró Blackboard Sync en la imagen de disco;",
    "The downloaded update is not the expected Blackboard Sync version;":
        "La actualización descargada no es la versión esperada de Blackboard Sync;",
    "The update's signature is not valid;": "La firma de la actualización no es válida;",
    "The update is not signed by the Blackboard Sync developer;":
        "La actualización no está firmada por el desarrollador de Blackboard Sync;",
    "The update is not notarized by Apple;": "La actualización no está notarizada por Apple;",
    "The new version could not be copied;": "No se pudo copiar la nueva versión;",
    "The update could not be started;": "No se pudo iniciar la actualización;",
    "Updates are installed through the Microsoft Store.": "Las actualizaciones se instalan desde Microsoft Store.",
    "The update could not be verified.": "No se pudo verificar la actualización.",
    "The update does not come from this app's page; it was not downloaded.":
        "La actualización no proviene de la página de esta app; no se descargó.",
    "The downloaded update could not be verified; it was not installed.":
        "No se pudo verificar la actualización descargada; no se instaló.",
    "The update could not be downloaded; check your internet connection.":
        "No se pudo descargar la actualización; revisa tu conexión a internet.",
    "The update could not be downloaded.": "No se pudo descargar la actualización.",
    "Google Calendar needs to be reconnected": "Hay que volver a conectar Google Calendar",
    "Google Calendar authorization state did not match.": "El estado de autorización de Google Calendar no coincide.",
    "Google Calendar authorization was cancelled.": "Se canceló la autorización de Google Calendar.",
    "Google Calendar operation was cancelled.": "Se canceló la operación de Google Calendar.",
    "Set BBSYNC_GOOGLE_CLIENT_ID to your Desktop OAuth client ID.":
        "Define BBSYNC_GOOGLE_CLIENT_ID con el ID de tu cliente OAuth de escritorio.",
    "A Google Calendar operation is already running.": "Ya hay una operación de Google Calendar en curso.",
    "Could not access the Google Calendar credential store.":
        "No se pudo acceder al almacén de credenciales de Google Calendar.",
    "Could not open the browser for Google Calendar.": "No se pudo abrir el navegador para Google Calendar.",
    "The saved Google Calendar is not a dedicated secondary calendar.":
        "El Google Calendar guardado no es un calendario secundario dedicado.",
    "Sync Blackboard successfully before syncing Google Calendar.":
        "Sincroniza Blackboard correctamente antes de sincronizar Google Calendar.",
    "Google Calendar sync failed.": "Falló la sincronización de Google Calendar.",
    "Could not reach Google Calendar.": "No se pudo conectar con Google Calendar.",
    "Google Calendar authorization timed out.": "Se agotó el tiempo de autorización de Google Calendar.",
    "You can close this browser window and return to Blackboard Sync.":
        "Puedes cerrar esta ventana del navegador y volver a Blackboard Sync.",
    "This event is managed by Blackboard Sync.": "Este evento lo gestiona Blackboard Sync.",
    "Google Calendar operation failed.": "Falló la operación de Google Calendar.",
    "Disconnect Google Calendar?": "¿Desconectar Google Calendar?",
    "Access will be revoked and local Calendar connection data removed.":
        "Se revocará el acceso y se borrarán los datos locales de conexión del calendario.",
    "Disconnect": "Desconectar",
    "Also delete the Blackboard Deadlines calendar from Google":
        "Borrar también el calendario Blackboard Deadlines de Google",
    "Reconnect": "Reconectar",
    "Google Calendar error": "Error de Google Calendar",
    "Not connected": "Sin conectar",
    "Connect to see Blackboard deadlines in Google Calendar.":
        "Conéctate para ver las entregas de Blackboard en Google Calendar.",
    "Connect Google Calendar": "Conectar Google Calendar",
    "Google Calendar operation in progress…": "Operación de Google Calendar en curso…",
    "You can cancel while authorization is waiting in the browser.":
        "Puedes cancelar mientras la autorización espera en el navegador.",
    "Connected": "Conectado",
    "Google Calendar": "Google Calendar",
    "Calendar has not synced yet.": "El calendario aún no se ha sincronizado.",
    "Sends deadlines to a dedicated Blackboard Deadlines calendar. Your other calendars stay private.":
        "Envía las entregas a un calendario propio llamado Blackboard Deadlines. Tus otros calendarios siguen "
        "siendo privados.",
    "Sync calendar now": "Sincronizar calendario",
    "Disconnect Google Calendar": "Desconectar Google Calendar",
    "Last calendar sync: {time}": "Última sincronización del calendario: {time}",
    "Google Calendar returned an invalid response.": "Google Calendar devolvió una respuesta no válida.",
    "Google requires this Desktop client's secret. Set BBSYNC_GOOGLE_CLIENT_SECRET locally and connect again.":
        "Google requiere el secreto de este cliente de escritorio. Define BBSYNC_GOOGLE_CLIENT_SECRET localmente "
        "y vuelve a conectar.",
    "The calendar's saved ID is missing. Delete the existing Blackboard Deadlines calendar in Google Calendar settings.":
        "Falta el ID guardado del calendario. Borra el calendario Blackboard Deadlines existente en la "
        "configuración de Google Calendar.",
    "Please wait for the calendar operation to finish.": "Espera a que termine la operación del calendario.",
    # Settings → Appearance (the Windows window)
    "Appearance": "Apariencia",
    "Theme": "Tema",
    "System follows the light or dark mode chosen in Windows.":
        "Sistema sigue el modo claro u oscuro elegido en Windows.",
    "System": "Sistema",
    "Light": "Claro",
    "Dark": "Oscuro",

    # Settings → AI assistant (ai_launcher)
    "AI assistant": "Asistente de IA",
    "Continue my last session in this folder": "Continuar mi última sesión en esta carpeta",
    "When it is off, a new session starts every time.": "Si está desactivado, cada vez empieza una sesión nueva.",
    "The app only opens a terminal in your course folder. The AI tool runs with your own account and its own "
    "rules.":
        "La app solo abre una terminal en la carpeta de tus cursos. La herramienta de IA funciona con tu propia "
        "cuenta y sus propias reglas.",
    "No earlier session here, starting a new one.": "No hay una sesión anterior aquí; se inicia una nueva.",
    "AI study session": "Estudia con IA",
    "Click a tool to open {term}, continuing your last session there.":
        "Haz clic en una herramienta para abrir {term} y continuar tu última sesión ahí.",
    "Click a tool to open {term} in a new session.":
        "Haz clic en una herramienta para abrir {term} en una sesión nueva.",
    "Looking for AI tools…": "Buscando herramientas de IA…",
    "Terminal": "Terminal",
    "The terminal app that opens for AI tools.": "La app de terminal que se abre para las herramientas de IA.",
    "Command Prompt": "Símbolo del sistema",
    "No AI tool is installed. Install Claude Code, Gemini CLI, Codex or Antigravity, then try again.":
        "No hay ninguna herramienta de IA instalada. Instala Claude Code, Gemini CLI, Codex o Antigravity y "
        "vuelve a intentarlo.",
    "{name} wasn't found. Using {default} instead.": "No se encontró {name}. Se usará {default}.",
    "Open in {name}": "Abrir en {name}",
    "Opening…": "Abriendo…",
    "{name} is not installed. Install it, then try again.": "{name} no está instalado. Instálalo y vuelve a intentarlo.",
    "How to install": "Cómo instalar",
    "Try again": "Reintentar",
    "The {term} folder isn't there yet. Sync first.": "La carpeta {term} aún no existe. Sincroniza primero.",
    "Could not open a terminal: {error}": "No se pudo abrir una terminal: {error}",
    "Could not open a terminal.": "No se pudo abrir una terminal.",
    "Open {name} in {term}": "Abrir {name} en {term}",

    # NotebookLM
    "Sign in to Google again to keep adding files.": "Vuelve a iniciar sesión en Google para seguir agregando archivos.",
    "Disconnect Gemini Notebook?": "¿Desconectar Gemini Notebook?",
    "The Google session is deleted from this computer. Files already in Gemini Notebook stay there, and new ones "
    "are no longer added.":
        "La sesión de Google se borra de esta computadora. Los archivos que ya están en Gemini Notebook se "
        "quedan ahí, y ya no se agregan nuevos.",
    "Connect Gemini Notebook": "Conectar Gemini Notebook",
    "Your course files are added after each sync.": "Los archivos de tus cursos se agregan después de cada sincronización.",
    "Checking what is already in Gemini Notebook…": "Revisando qué hay ya en Gemini Notebook…",
    "Sign in to Google in the browser window.": "Inicia sesión en Google en la ventana del navegador.",
    "Adding {done} of {total}: {file}": "Agregando {done} de {total}: {file}",
    "Gemini Notebook is reading the new files…": "Gemini Notebook está leyendo los archivos nuevos…",
    "Checking the connection…": "Comprobando la conexión…",
    "Google took the sign-in, but Gemini Notebook did not open. Try again.":
        "Google aceptó el inicio de sesión, pero Gemini Notebook no se abrió. Vuelve a intentarlo.",
    "{n} new file added to your notebooks": "{n} archivo nuevo agregado a tus cuadernos",
    "{n} new files added to your notebooks": "{n} archivos nuevos agregados a tus cuadernos",
    "No new files were added": "No se agregaron archivos nuevos",
    "Last checked: {time}": "Última revisión: {time}",
    "{n} course blocked": "{n} curso bloqueado",
    "{n} courses blocked": "{n} cursos bloqueados",
    "{n} failed": "{n} con error",
    "Add new files to Gemini Notebook after each sync":
        "Agregar archivos nuevos a Gemini Notebook después de cada sincronización",
    "Disconnect Gemini Notebook": "Desconectar Gemini Notebook",
    "Files in Gemini Notebook stay there.": "Los archivos de Gemini Notebook se quedan ahí.",
    "Unofficial connection: it may stop working if Google changes Gemini Notebook.":
        "Conexión no oficial: podría dejar de funcionar si Google cambia Gemini Notebook.",
    "{course}: {n} over the {limit} source limit; nothing added.":
        "{course}: {n} por encima del límite de {limit} fuentes; no se agregó nada.",
    "{course}: several notebooks have this name, so it was skipped.":
        "{course}: hay varios cuadernos con este nombre, así que se omitió.",
    "{n} file could not be added; the next sync tries again.":
        "No se pudo agregar {n} archivo; la próxima sincronización lo volverá a intentar.",
    "{n} files could not be added; the next sync tries again.":
        "No se pudieron agregar {n} archivos; la próxima sincronización lo volverá a intentar.",
    "The browser did not start. If a sign-in window from an earlier attempt is still open, close it and try again.":
        "El navegador no se abrió. Si sigue abierta una ventana de inicio de sesión de un intento anterior, "
        "ciérrala y vuelve a intentarlo.",
    "Gemini Notebook needs Chrome, Edge or Brave to sign in to Google; install one and try again.":
        "Gemini Notebook necesita Chrome, Edge o Brave para iniciar sesión en Google; instala uno y vuelve a "
        "intentarlo.",

    # NotebookLM: files that may be there already
    "{n} file may already be in Gemini Notebook, so it was not added.":
        "Puede que {n} archivo ya esté en Gemini Notebook, así que no se agregó.",
    "{n} files may already be in Gemini Notebook, so they were not added.":
        "Puede que {n} archivos ya estén en Gemini Notebook, así que no se agregaron.",
    "{n} held back": "{n} en espera",

    # Store trial and purchase (licensing)
    "Purchases are not available in this build.": "Las compras no están disponibles en esta compilación.",
    "Could not reach the Microsoft Store. Check your internet connection and try again.":
        "No se pudo conectar con Microsoft Store. Revisa tu conexión a internet y vuelve a intentarlo.",
    "Could not complete the purchase in the Microsoft Store. Try again in a moment.":
        "No se pudo completar la compra en Microsoft Store. Vuelve a intentarlo en un momento.",
    "No purchase was found for this account yet.": "Aún no se encontró ninguna compra para esta cuenta.",
    "Free trial ended": "La prueba gratuita terminó",
    "{n} minute left": "queda {n} minuto",
    "{n} minutes left": "quedan {n} minutos",
    "{n} hour left": "queda {n} hora",
    "{n} hours left": "quedan {n} horas",
    "{n} day left": "queda {n} día",
    "{n} days left": "quedan {n} días",
    "Free trial · {remaining}": "Prueba gratuita · {remaining}",
    "Free trial": "Prueba gratuita",
    "Buy": "Comprar",
    "Buy for {price}": "Comprar por {price}",
    "Opening Store…": "Abriendo la tienda…",
    "Your free trial has ended": "Tu prueba gratuita ha terminado",
    "Buy Blackboard Sync once ({price}) to keep syncing your courses. Your downloaded files are still in your folder.":
        "Compra Blackboard Sync una sola vez ({price}) para seguir sincronizando tus cursos. "
        "Tus archivos descargados siguen en tu carpeta.",
    "Buy Blackboard Sync once to keep syncing your courses. Your downloaded files are still in your folder.":
        "Compra Blackboard Sync una sola vez para seguir sincronizando tus cursos. "
        "Tus archivos descargados siguen en tu carpeta.",
    "I already bought it": "Ya lo compré",

    # Mac App Store (App Sandbox, folder bookmark, copy-command, demo mode)
    "Choose a folder…": "Elige una carpeta…",
    "Choose the folder using “Choose…” so macOS grants access to it.":
        "Elige la carpeta con “Elegir…” para que macOS conceda acceso a ella.",
    "Click a tool to copy the terminal command for {term}.":
        "Haz clic en una herramienta para copiar el comando de terminal de {term}.",
    "Copied terminal command for {name} — paste it into Terminal.":
        "Se copió el comando de terminal de {name}; pégalo en Terminal.",
    "Copy command for {name}": "Copiar comando de {name}",
    "Copy {name} command for {term}": "Copiar comando de {name} para {term}",
    "Could not copy the command.": "No se pudo copiar el comando.",
    "Gemini Notebook sign-in is not available in the Mac App Store version.":
        "El inicio de sesión de Gemini Notebook no está disponible en la versión de Mac App Store.",
    "Try the demo": "Probar la demo",
    "Updates are installed through the App Store.": "Las actualizaciones se instalan desde App Store.",
    "You can uninstall Blackboard Sync from Launchpad or the Applications folder.":
        "Puedes desinstalar Blackboard Sync desde Launchpad o la carpeta Aplicaciones.",

    # Minimum-version enforcement (min_version)
    "Update required": "Actualización obligatoria",
    "Update required — Update": "Actualización obligatoria — Actualizar",
    "Updating…": "Actualizando…",
    "Update Blackboard Sync to version {version} or newer to keep syncing your courses. Your downloaded files are still in your folder.":
        "Actualiza Blackboard Sync a la versión {version} o posterior para seguir sincronizando tus cursos. "
        "Tus archivos descargados siguen en tu carpeta.",
    "Update Blackboard Sync to the latest version to keep syncing your courses. Your downloaded files are still in your folder.":
        "Actualiza Blackboard Sync a la última versión para seguir sincronizando tus cursos. "
        "Tus archivos descargados siguen en tu carpeta.",
    "Blackboard Sync moved to the Mac App Store": "Blackboard Sync se trasladó al Mac App Store",
    "Get Blackboard Sync from the Mac App Store to keep syncing your courses. Your downloaded files are still in your folder.":
        "Obtén Blackboard Sync en el Mac App Store para seguir sincronizando tus cursos. "
        "Tus archivos descargados siguen en tu carpeta.",
    "Open Mac App Store": "Abrir Mac App Store",
    "Could not open the Mac App Store.": "No se pudo abrir el Mac App Store.",
}
