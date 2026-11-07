# User guide

See the [README](../README.md) for installation. This page explains how to use the app in detail.

## Main window

Open Blackboard Sync from **Applications** or **Launchpad** (on Windows, from the **Start** menu)
and the main window opens; if the app is already running, the same window comes to the front. The
window is laid out like Google Drive's desktop app. The **Open folder** button is at the top left,
with the sections below it: **Get started** until you first sign in, then **Home**, **Sync activity**,
**Announcements**, **Courses** and **Calendar**. At the top right are round buttons: **Pause / Resume**,
**Settings** (the gear) and your account (your initials; click for the account menu). **Settings…**
in the menu opens the same window on the **Settings** page.

- **Home** is a summary: the sync state (**Up to date**, **Syncing…**, **Paused**, **Sign-in needed**;
  an animation of files flying into a folder while a sync runs), the latest downloads, what needs your
  attention with the newest announcements, and the upcoming due dates. On a Mac and on Windows, a
  **NotebookLM** card sits under the sync state (see [NotebookLM](#notebooklm-mac-and-windows)).
- **Sync activity** lists every file, note and announcement a sync brought, newest first, with its
  size and status; click a row to open the file in its own app.
- **Announcements** shows what needs your attention at the top (session expired, an update, a sync that
  did not finish, warnings) and all course announcements below.

The **Pause** button stops a running sync right away, and no automatic sync runs until you press
**Resume** (the same button, now a play symbol), as in Google Drive. The pause is kept across restarts.
When you resume, a sync starts right away. The menu bar menu also has **Pause syncing / Resume syncing**.

Closing the window does not quit the app: it keeps running and syncing from its icon in the menu bar
(on Windows, next to the clock). When the app starts with the computer it does not open a window. To
quit completely, choose **Quit** in the icon's menu.

## Language

The app is in English by default. To switch to Turkish, open **Settings**, choose **Türkçe** under
**Language** in the **Sync** section and press **Save**. The language is used once the app starts again;
Blackboard Sync offers to restart right away. Downloaded files, notes and folder names do not change.

## Theme (Windows)

On Windows, **Settings → Appearance → Theme** chooses the main window's colors: **System** follows the
light or dark mode set in Windows, **Light** and **Dark** keep one. The change applies at once and is saved
right away, without **Save**. macOS follows the system's appearance.

## Calendar

**Calendar** shows the assignments, exams and other graded work of your synced courses day by day,
by due date. Upcoming dates start with the nearest; past ones are shown separately. Times are your
computer's local time. Click an item to open its downloaded note if there is one; otherwise Blackboard
opens. For grade columns without a content link, the course's grades page opens.

**Reminders:** you get a notification 24 hours and 1 hour before a due date (once each). If the
computer was off at the time, only the nearest reminder is shown when it starts. Courses you unticked
in Courses send no reminders.

Due dates are updated during a sync; opening this page sends no internet request. If the school
closes access to a course's grade columns, the earlier records are kept and the page says which courses
could not be updated. Only due dates that Blackboard states explicitly are shown. Submissions are not
checked, so work you already handed in may show among the past due items too.

## Download folder

Files are saved in a **University** folder inside the folder you choose, in term and course folders;
the app creates the University folder itself. For example, if you choose iCloud Drive, files go to
`iCloud Drive/University/2026-2027 Güz/…`. If the folder you choose is already called University (like
the default `Documents/University`), no second University folder is created inside it.

Video and audio recordings are not downloaded; their notes show a Blackboard link. Other files larger
than 500 MB are not downloaded either. The note shows the file's size and a link to open it in
Blackboard, and the sync summary counts the files skipped this way. If the file changes on Blackboard,
the next sync looks at the new version again.

Earlier versions put the term folders straight into the chosen folder (`iCloud Drive/2026-2027 Güz/…`).
On the first launch or first sync after updating, these files are moved into the University folder
once; they are not downloaded again. A file that cannot be moved (open in another program, or a
different file with the same name already in the University folder) stays where it is, and a
notification tells you.

The University folder is a copy of Blackboard: if you delete a file or it gets damaged (empty or only
half downloaded), the next sync downloads it again. Copy files to another folder to organize them your
own way. A file you changed (for example a PDF you annotated) is never overwritten; if Blackboard has a
new version, it is downloaded next to it as `name (2).pdf`.

If you change the folder in Settings, **Move** moves the files to the new folder, while **Download
again** downloads them into the new folder without touching the old one.

## Courses

The **Courses** section of the main window lists your current-term courses, each with a checkbox.
Ticked courses are synced; a new course comes ticked by itself. Untick a course you don't want: it is
no longer synced at all (no request is sent to Blackboard for it), and it does not show in **Calendar**,
**Announcements** or the recent downloads. Files downloaded earlier are not deleted. Tick it again and
its missing files arrive with the sync that starts right away.

The list fills after the first sync.

## Staying signed in (Mac and Windows)

A Blackboard session runs out after a while, but your school's single sign-on usually lasts much longer.
With **Automatic re-sign-in** on (Settings, Sync; on by default), the app handles this for you:

- While it runs, it checks your session every 25 minutes or so with one small request, which also keeps
  the session alive. Nothing is sent while you are signed out or paused.
- When the session has ended or is about to, the app signs in again in the background, with no window,
  using the same private browser profile as **Sign in**. If your school still knows you, this takes a few
  seconds and the sync goes on. Home then shows **Session refreshed automatically**.
- If your school wants you (a password, a two-factor code, choosing an account), nothing is filled in. You
  get the usual notification and sign in with **Sign in**, as before. After a failed try the app waits at
  least 10 minutes before trying again.

Your password is never seen or stored. How long this keeps working depends on your school. Microsoft
sign-ins often last longer if you choose "Stay signed in" when you sign in. It does not work if you signed
in through the app's own window, or if Arc is your only supported browser. Turn the setting off to go back
to signing in by hand.

## Announcements

The **Announcements** section of the main window lists every announcement synced from your
current-term courses, newest first. Each card shows the course name, title, date and a short preview.
Choose a card to open the saved note; if the note is not on the computer, the course's announcements
page on Blackboard opens.

The list comes from the local sync data; switching to this section sends no new request to
Blackboard. If you updated from an earlier version, announcements are listed after the next sync.

## Updates

When a new version is out you get a notification, and a card about it appears on the **Get started /
Home** page of the main window. Press its **Update** button; you can also update from the menu or the
**Settings** page. The Microsoft Store version does not show this card; the Store installs updates.

- **macOS:** The app downloads the new version in the background, verifies its signature and Apple
  notarization, puts it in place of the old one and opens itself again; no Finder window or dragging is
  needed. If verification fails, the current version is kept. If the app runs from its disk image, from a
  folder it cannot write to, or is an older unsigned version, the `.dmg` opens and you drag the app into
  **Applications** yourself.
- **Windows:** The installer runs silently and restarts the app.

An update does not start while a sync or a folder move runs; try again once it has finished. Your
settings and downloaded course files are kept.

## Uninstalling

Press **Uninstall app…** in **Updates** on the **Settings** page of the main window. The app's records,
logs, settings, sign-in data and start-at-login entry are deleted. Downloaded course files are kept by
default. **Also delete the downloaded course files** moves only the files the app recorded and the
folders they leave empty (including the University folder the app created, if it is empty) to the Trash
/ Recycle Bin; other files and the download folder you chose are kept. You cannot uninstall while a sync
or a folder move runs.

From the terminal (quit the app from its menu first):

```sh
blackboard-sync uninstall
# To also move the recorded course files to the Trash:
blackboard-sync uninstall --delete-course-files
```

In the packaged Windows install the terminal command is `blackboard-sync-cli.exe uninstall` in the app
folder. The macOS package uses `"/Applications/Blackboard Sync.app/Contents/MacOS/Blackboard Sync" uninstall`.
When installed from source, this command clears the data; remove the source folder and virtual
environment yourself. Only dragging the app to the Trash in Finder does not clear the app's data.

## Google Calendar (optional)

Open **Settings → Google Calendar → Connect Google Calendar** (macOS and Windows). Consent
opens in your browser; you can cancel in the app while it waits. Connection and
Disconnect take effect immediately, independently of the settings Save/Cancel
buttons. A Google Desktop OAuth client must first be configured by the developer;
see [Google Calendar setup](GOOGLE_CALENDAR_SETUP.md).

After each successful Blackboard sync, the app sends deadline changes to its
separate **Blackboard Deadlines** calendar. **Sync calendar now** sends the cached
deadlines without downloading Blackboard data. Pause stops automatic Calendar
updates too; Resume runs Blackboard first, then Calendar. Hidden courses are
excluded and their managed events are removed on the next Calendar run. Events
are 30 minutes long, ending at the deadline, without Google reminders by default.
The app already supplies its own 24-hour and 1-hour deadline notifications.
Deleted Blackboard deadlines are removed from Google; passing a due date alone
does not remove an existing event. Deadlines over 14 days old are not newly added.
If you delete the dedicated calendar, the next run recreates it.

Google receives the event title, course name, due time, Blackboard link, and
technical identifiers for matching the app's events. The app never reads your
personal events or writes to your main calendar. Refresh tokens stay in macOS
Keychain or Windows Credential Manager (private token JSON on other platforms);
calendar ID, status and the event ID/hash mapping are saved privately on your
computer. Access tokens stay in memory. See the [privacy policy](../site/privacy.html).
Blackboard Sync's use and transfer of information received from Google APIs
adhere to the Google API Services User Data Policy, including the Limited Use
requirements.

**Disconnect** revokes the token and removes local Calendar connection data.
If you keep the Google calendar, only its non-secret ID remains locally so a
later connection can reuse it or delete it. The confirmation has an optional **Also delete the Blackboard Deadlines calendar
from Google** checkbox. Otherwise the existing Google calendar remains and stops
updating. You can revoke access independently at
[Google Account → Third-party connections](https://myaccount.google.com/connections).
After revocation, the next Calendar attempt shows **Reconnect** in Home and
Settings. Blackboard downloads keep working. If deletion was requested after
access was revoked, reconnect first or delete the calendar in Google settings.
Disconnect before uninstalling; uninstalling the app does not revoke Google's
grant or remove its remote calendar.

Terminal commands (also used to connect/reconnect on Windows, whose native
Calendar connection controls are not yet implemented):

```sh
blackboard-sync calendar connect
blackboard-sync calendar status
blackboard-sync calendar sync
blackboard-sync calendar sync --reminders   # opt in to Google's default reminders
blackboard-sync calendar disconnect
blackboard-sync calendar disconnect --delete-calendar
```

`status` prints only connection state, last sync/error and whether reconnection is
needed. Tokens are never printed. `calendar sync` uses the cached Blackboard
source; run `blackboard-sync sync` first when testing from the terminal. The
terminal Blackboard sync command itself does not automatically contact Google.


## NotebookLM (Mac and Windows)

Blackboard Sync can add your course files to [NotebookLM](https://notebook.google.com) (now also
called Gemini Notebook), so you can ask questions about them. This is available on Mac and Windows only.

**Connect once.** On **Home**, press **Connect NotebookLM** on the NotebookLM card. A browser window
opens on Google's own sign-in page; sign in and it closes by itself. Your password goes only to
Google. You need Chrome, Edge, Brave or another Chromium browser installed, as for the Blackboard
sign-in. Once you are connected, the first run starts right away. If the sign-in does not finish, the
card says why (out of time, window closed, NotebookLM did not open) and you can try again.

**After that it runs by itself.** After every successful Blackboard sync, new files are added in the
background. **Sync NotebookLM** on the card does the same on demand, and **Open NotebookLM** opens your
notebooks in your browser. While files go up, the card counts them across your courses, up to three
of which are worked on at a time. Your downloads are never held up:
NotebookLM runs on its own after the sync, and a problem shows only on the card. Pause stops it too.
To turn the automatic step off, untick **Settings → NotebookLM → Add new files to NotebookLM after
each sync**; the button keeps working.

**What goes where.** Each course gets one notebook, named after its folder. A notebook with that name
is reused, and files already in it are kept and not added twice. Each source is named by its path
inside the course folder, such as `Week 3/slides.pdf`. NotebookLM sometimes keeps only the file name
(`slides.pdf`), so the app recognizes a file by what it recorded when adding it, then by its content,
then by its path, and then by its name. If a file's name is in the notebook but the app cannot tell
that it is the same file, the file is **held back**: it is not added, the card counts it, and
`blackboard-sync notebooklm sync` lists it in `held_files`.

- Added: the PDF, Word, PowerPoint, text, Markdown, CSV and EPUB files Blackboard Sync downloaded for
  your courses, up to 200 MB each, and the PDF notes of course pages. Hidden courses are left
  out, and so are announcements.
- Skipped and counted: other file types, images, larger files, and files you put in the folders
  yourself.

**What the app never does.** A sync only adds. It deletes and replaces nothing in NotebookLM; the one
exception is removing duplicates, below, which you confirm yourself. A source you
remove there stays removed: the app remembers the file and does not add it again. If a course has more files than the notebook's source limit (often 50), that
course is left as it is and marked **blocked**, because adding only some of them would leave a silent
gap. If a file changed on Blackboard after it was added, it is counted as **modified**; the old source
stays. If two notebooks have the same name, that course is skipped until you rename one.

**Duplicates.** **Settings → NotebookLM → Find duplicates** lists the sources that are in a notebook
more than once, with the date of each copy. It deletes nothing. Press **Remove** and confirm to take
out the extra copies. Only a newer copy that this app added, with the same content as an older copy
that is ready, can go. An older copy, a source you added yourself, and a file that changed on
Blackboard in between (both versions stay, and you decide in NotebookLM) are listed but never removed.

**If you used the `dersler-notebooklm` tool before.** Its `state.json` is read, never changed, and
what it uploaded counts as already there. The app looks in
`~/Documents/My Cave/Garage/dersler-notebooklm/state.json`; set `BBSYNC_NOTEBOOKLM_LEGACY_STATE` to
use another path.

**If the card asks you to sign in again,** Google ended the session. Press **Sign in**; nothing is lost
and the next run carries on from there. The app keeps the session fresh, but a changed password or a
security check at Google ends it.

**Disconnect.** **Settings → NotebookLM → Disconnect NotebookLM** deletes the stored Google session
and the sign-in browser's data from this computer. Your notebooks stay in NotebookLM. The record of which
files were added is kept, so reconnecting does not add anything twice. Uninstalling the app does the
same and removes that record as well.

**Please know before connecting.** Google has no public way for apps to add NotebookLM sources, so
this uses an unofficial connection, through the open-source
[notebooklm-py](https://github.com/teng-lin/notebooklm-py) library. Google may change it without
notice and it can stop working until the app is updated. It works with your Google account's session,
so use it knowing that Google could object to automated use. Your course files are sent to Google;
files your school does not allow you to share should stay out of it. The session is stored only on
this computer, in a file only your user account can read.

Terminal commands:

```sh
blackboard-sync notebooklm login
blackboard-sync notebooklm sync
blackboard-sync notebooklm status
blackboard-sync notebooklm duplicates [--json]
blackboard-sync notebooklm remove-duplicates [--yes] [--source ID] [--json]
blackboard-sync notebooklm disconnect
```

Each prints one JSON line per step. `status` shows only the connection and the last run's counts; the
session is never printed.


## Version 1.6.0

Official release packages include the Desktop OAuth client configuration; Google
Calendar Connect no longer needs terminal environment variables. Source checkouts
can use the gitignored `.bbsync/google-oauth-client.json` or the environment
overrides described in the setup guide.
