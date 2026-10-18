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
  attention with the newest announcements, and the upcoming due dates.
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

The list fills after the first sync. Past terms are not in this list; download them separately from
**Past terms** on the **Settings** page.

## Announcements

The **Announcements** section of the main window lists every announcement synced from your
current-term courses, newest first. Each card shows the course name, title, date and a short preview.
Choose a card to open the saved note; if the note is not on the computer, the course's announcements
page on Blackboard opens.

The list comes from the local sync data; switching to this section sends no new request to
Blackboard. If you updated from an earlier version, announcements are listed after the next sync.
Announcements of past-term archives do not show in this list.

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

## Downloading a past term

In **Past terms** on the **Settings** page of the main window, choose a term from the list and press
**Download past term**. The list loads when the **Settings** page opens while you are signed in; the
current term is not in it. Files are downloaded into term/course folders in your current download
folder: each term's folder is created next to the current term's folder (for example `2026-2027 Güz`
next to `2025-2026 Bahar`). Even if Blackboard shows the same term under both a Turkish and an English
name (`2025-2026 Bahar` / `2025-2026 Spring`), it is one term and one folder; a course listed twice is
downloaded once. A past term is downloaded once and not updated automatically; downloading it again only
fills in missing files. If a course's content cannot be read (for example access is closed), you are told,
and trying again fills in what is missing. The normal sync keeps following the current term.

From the terminal: `blackboard-sync sync --term "2025-2026 Bahar"` (the Turkish or English term name
works) or `blackboard-sync sync --term-id <id>`. List the available terms and their ids with
`blackboard-sync past-terms`.

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
