# Development guide

Developer setup, CLI reference, architecture, and troubleshooting for Blackboard Sync.
For installation, see the [README](../README.md). Commands below run from the repository root.

`blackboard-sync` signs in to Blackboard Learn Ultra
(default: <https://blackboard.istun.edu.tr>) using your own browser session,
finds your courses for the current term, and copies everything in them to
`~/Documents/University/` with the same folder structure you see on the site:

```
~/Documents/University/
  2026-2027 Güz/
    CSE303 Algorithm Analysis/
      Syllabus/
        CSE303_Algorithm_Analysis_for_Computer_Engineering_Syllabus_v1.pdf
      Lecture Notes/
        Week 1/
          Intro - Asymptotic Notation.md
          week1-slides.pdf
        Week 2/
      Course Website - Visualizations.md
      Duyurular/
        2026-09-20 Welcome to CSE303.md
    MTH201 Linear Algebra/
    ...
```

- **Files** (PDFs, slides, documents, files embedded in pages) are downloaded
  with their original names.
- **Everything that is not a file** — web links, text pages, assignments and
  tests, discussions, external tools and **announcements** — becomes a small
  Markdown note (`.md`) in the matching folder, with its text and a link back
  to Blackboard.
- Runs are **incremental**: only new or changed items are fetched. Nothing
  local is ever deleted.
- New term? It switches automatically; no course URLs to configure.

Day to day you do not need the terminal at all: the [menu bar app](#menu-bar-app)
syncs every hour in the background and shows a macOS notification such as
`CSE303: 2 yeni dosya` when something new arrives.

## Setup

Requirements: macOS 11 or newer and Python 3.10 or newer (`python3 --version`).
Google Chrome, Edge, Brave, Vivaldi, Opera, Opera GX, Chromium, or Arc (any
Chromium-based browser) in `/Applications` or `~/Applications` is used for
sign-in when present; without one, sign-in happens in the app's own window. On
Windows, see [Windows](#windows).

```sh
./scripts/setup.sh
```

This creates a project-local virtual environment in `.venv/` and installs the
pinned dependencies from `requirements.lock`. Nothing is installed globally and
no browser is downloaded — sign-in uses the Chromium-based browser you already have,
or the system's web view.
After setup the command is `.venv/bin/blackboard-sync` (or activate the
environment with `source .venv/bin/activate` and type `blackboard-sync`).

## First run

### 1. Sign in

```sh
.venv/bin/blackboard-sync login
```

A separate browser window (Chrome, else Edge, Brave, Vivaldi, Opera, Opera GX,
Chromium, and Arc last; force one with
`--browser chrome|edge|brave|vivaldi|opera|operagx|chromium|arc`) opens in front, on the Blackboard sign-in page, which
for blackboard.istun.edu.tr forwards to the university's Microsoft sign-in.
It is started like any app you open from the Dock, with its own private profile,
so your everyday browser and its tabs are not touched. Sign in exactly as you
normally do, including any two-factor step. As soon as Blackboard accepts you,
that window closes by itself and the terminal prints
`Signed in as <your user name>`. You have 10 minutes (`--timeout SECONDS` to
change).

Without any of those browsers, `login` signs you in in its own small window
instead (also forced with `--browser inapp`): the operating system's web view
(WKWebView on macOS, Microsoft Edge WebView2 on Windows) opens the same
Blackboard address, you sign in the same way, and the window closes by itself.
With `auto`, a browser that fails to start or cannot be reached before the
sign-in page is up also falls back to that window. The terminal says which one
opened (`Opening Google Chrome ...` or `Opening the sign-in window ...`), and
the menu bar / tray status line while waiting names it too. Both methods save
the same `session.json`, so `sync`, cookie refresh and expiry work the same.
Some identity providers refuse embedded web views; if the window shows such an
error, install a Chromium-based browser and sign in again.

The tool never asks for, sees, or stores your password. It only keeps the
session cookies Blackboard gives your browser after you sign in.

Browser discovery (`blackboard_sync.login`): `discover_browser()` returns the
installed browser's path or `None`; `find_browser()` raises
`NoSupportedBrowserError` (a `BlackboardSyncError`; `.requested` is the
`--browser` name, or `None` for `auto`) so a caller can fall back to another
sign-in method. Every listed browser is Chromium and takes `--user-data-dir`
and `--remote-debugging-port`. macOS bundle names: `Google Chrome.app`,
`Microsoft Edge.app`, `Brave Browser.app`, `Vivaldi.app`, `Opera.app`,
`Opera GX.app`, `Chromium.app`, `Arc.app`; on Windows `opera.exe` and
`chrome.exe` are shared by Opera/Opera GX and Chrome/Chromium, so those are told
apart by install folder. Arc is tried last on macOS and is not offered on
Windows (Store app, no stable path). Only Chrome, Edge and Brave have been run
end to end; the others are the same Chromium flags but untested here, and Arc
may reuse a running instance instead of honouring the private profile.

In-app window (`blackboard_sync.inapp`, GUI-free; `inapp_macos`,
`inapp_windows`): `login.choose_browser()` returns the browser to use or `None`
for the window, `login.login_method_label()` the name shown in the UI (or
`inapp`). The window polls its web view's cookie store, which includes HttpOnly
cookies (`WKHTTPCookieStore` on macOS, WebView2's cookie manager through
pywebview's `get_cookies()` on Windows), keeps only Blackboard-host cookies,
and stops once `/learn/api/public/v1/users/me` accepts them. macOS keeps the
window's web data in WebKit's store for the app (`~/Library/WebKit/`), Windows
in `inapp-profile\` in the data folder; both keep the identity provider's "stay
signed in", like the browser profile. macOS does not let a process started in
the background take the keyboard from the active app, so the window opens on
top of other windows but you may need to click into it once before typing.

### 2. Check what will be synced

```sh
.venv/bin/blackboard-sync check
```

Prints the signed-in user, the term it considers current, and the folder each
course will go to. Use this to confirm everything looks right.

### 3. Sync

```sh
.venv/bin/blackboard-sync sync --dry-run   # optional: list what would be downloaded
.venv/bin/blackboard-sync sync
```

The first sync downloads everything; later runs only fetch what is new. At the
end it prints a summary per course, for example:

```
Synced 8 course(s) for 2026-2027 Güz into /Users/you/Documents/University
  CSE303: 2 new files, 1 new announcement
      + 2026-2027 Güz/CSE303 Algorithm Analysis/Lecture Notes/Week 2/week2.pdf
      ...
  MTH201: no changes
1 course(s) had changes.
```

Run `sync` a second time right away: it should report `Nothing new.` and
download nothing.

If something looks off, `-v` (`blackboard-sync -v sync`) logs every request
(URLs only, never cookies).

## Menu bar app

A small icon next to the clock that runs the sync for you every hour, so you
never have to type commands after the first setup.

### Start it

```sh
./scripts/menubar.sh
```

The app starts in the background and the command returns right away; you can
close the terminal. (`.venv/bin/blackboard-sync-menubar` runs it in the
foreground instead, with its log in the terminal.) Only one copy runs at a
time; starting it again does nothing.

To start it **without a terminal**, build the standalone app (see
[Building the app](#building-the-app-and-releases)) and open
`dist/Blackboard Sync.app`. It bundles its own Python and needs no checkout or
`.venv`. Notifications appear under the name "Blackboard Sync".

### Settings

The first time the app starts, the settings window opens as **Blackboard Sync
kurulumu**; later **Ayarlar…** in the menu opens the same window. On macOS
and Windows it has **Genel** and **Silinenler** tabs. **Genel** has five sections:

- **Hesap** — **Okulunuzun Blackboard adresi**, prefilled with
  `https://blackboard.istun.edu.tr`; students of another university type their
  school's Blackboard address instead (it must be `https://`; a pasted course
  link is reduced to the site address). Below it, who is signed in and
  **Giriş yap** (saves the window and opens the Blackboard sign-in window) or
  **Hesaptan çıkış yap** (asks first; removes the session and all login browser data, so the next sign-in asks for the school credentials again; downloaded files, settings and sync state are kept).
- **Klasör** — **Dosyaların kaydedileceği klasör**, prefilled with
  `~/Documents/University`; **Seç…** opens a folder picker. The files go into
  the **University** folder inside the chosen one (created when needed), or
  into the chosen folder itself when it is already named University (any case);
  the note under the field says so. Files an older version put directly into the
  chosen folder are moved into University once, at the next app start or sync
  (`relocate.migrate_to_root`); a file that cannot be moved stays and is reported.
- **Eski dönemler** — a list of past terms (newest first, never the current
  one) and **Eski dönemi indir**, which downloads the chosen term once into
  the same folder; it is not updated afterwards. The list is looked up in the
  background each time the window opens while you are signed in; until then it
  says it is loading, and **İndirilebilecek eski dönem yok.** when there is none.
- **Genel** — **Bilgisayar açılınca başlat**, ticked by default (see
  [Start at login](#start-at-login)), and **Otomatik senkron**: every 30
  minutes, **every hour** (default), every 3 hours or **Yalnızca elle** (no
  automatic sync; the menu says "otomatik senkron kapalı" and no notifications
  arrive until you choose **Şimdi senkronize et**). There is deliberately no
  shorter choice: an idle sync is a few hundred requests to the school.
- **Güncellemeler** — **Güncellemeleri otomatik denetle**, ticked by default,
  **Şimdi denetle** and the version number (see [Updates](#updates)), then
  **Uygulamayı kaldır…**, which asks first and removes the app and its data
  (downloaded course files are kept unless you tick the box).

**Silinenler** lists downloaded files whose recorded path is missing under the
saved destination, grouped by term and course, with their name and folder.
Check the files to recover, then **Seçilenleri indir**; **Tümünü seç** checks
all listed files. **Listeden kaldır** permanently dismisses checked entries
from the list and future refetches. Unchecked deletions stay respected during
normal syncs. An empty list says **Silinmiş dosya yok.** These actions use the
saved destination; save a folder change on **Genel** first.

The CLI still accepts `sync --refetch-missing` for all missing, undismissed
outputs. To recover selected outputs only (including past terms), add
`--refetch-selection selection.json`, where the file is a JSON array of keys
from `state.json`'s `outputs`. Selection jobs only restore those outputs and
leave unrelated new or changed content for normal sync.

**Kaydet** saves the fields and check boxes; **Giriş yap**, **Hesaptan çıkış
yap**, **Eski dönemi indir**, **Seçilenleri indir**, **Listeden kaldır**, **Şimdi denetle** and
**Uygulamayı kaldır…** act right away. The buttons that need the app's single job
slot (sign in, sign out, download a past term, bring back deleted files,
uninstall) are greyed out while a sync or sign-in runs. Nothing is synced
on a schedule until the window has been saved once. When you save later:

- A different school address requires signing in again; the sign-in window
  opens as soon as you save.
- A different folder, when the old one holds downloaded files, asks what to do
  with them:
  - **Taşı** (the default) moves every downloaded file to the same place in
    the new folder without downloading it again. A file that cannot be moved
    (a different file of that name is already there, or it is open in another
    program) stays in the old folder and is reported; nothing is overwritten.
    Your own files in the old folder are left alone, and the old folders are
    removed only once every downloaded file moved and they are empty.
  - **Yeniden indir** downloads undismissed files again into the new folder;
    the old folder is left untouched.
  - **Sadece yeni dosyalar** leaves the old files where they are; only content
    that appears from now on lands in the new folder.

  **Vazgeç** (or closing the question) keeps the old folder and saves nothing.
  While a sync runs the folder cannot be changed; wait for it to finish.

The choices are stored in `settings.json` in the data folder (see
[Where things go](#where-things-go)). The `blackboard-sync` command reads the
same file, so after the window is saved the terminal syncs the same school
into the same folder without any flags; `BBSYNC_*` variables and command-line
options still override it for the terminal.

### Updates

Once a day the app asks GitHub whether a newer release exists (only while
**Güncellemeleri otomatik denetle** is ticked) and posts one notification per
new version, "Blackboard Sync 1.1.0 hazır — Güncelle". The menu then shows
**Güncelleme var: 1.1.0 — Güncelle** above **Ayarlar…** (the row is absent
while there is no update). **Şimdi denetle** in the settings window checks
right away and answers with a notification; with an update waiting it reads
**1.1.0 sürümüne güncelle** instead.

On macOS **Güncelle** updates the app in place (`update_macos.py`). It
downloads `Blackboard-Sync-<version>.dmg` into a temporary folder, checks it
against the release's `SHA256SUMS.txt`, attaches it hidden and read-only, and
checks the app on it the way `install.sh` does: this release's bundle
identifier and version, a valid Developer ID signature of the running app's
team, and Gatekeeper's notarization verdict. Any failure keeps the current
app and says why in a notification. The verified app is copied with `ditto`
to a hidden sibling of the running one, the image is detached, and the app
quits; a detached shell helper waits for it to exit, swaps the new app in
(the old one is restored if a step fails) and opens it again, which then
posts "Blackboard Sync X sürümüne güncellendi". No update starts while a
sync or folder move runs (the run lock is held throughout).

Where the app cannot replace itself (it runs from the mounted image or a
translocated path, its folder is not writable, or it is an unsigned build)
**Güncelle** downloads the `.dmg` into Downloads, opens it and explains the
last step: quit Blackboard Sync and drag the new app over the old one in
Applications. Run from a checkout, **Güncelle** opens the release page
instead.

Checking needs the GitHub repository to be public: without signing in, GitHub
does not show a private repository's releases, and the app then simply finds
no update. No account data is sent; the request is an anonymous call to
`api.github.com`.

### Start at login

Tick **Bilgisayar açılınca başlat** in the settings window (or run
`.venv/bin/blackboard-sync-menubar --enable-autostart`). This writes a per-user
LaunchAgent, `~/Library/LaunchAgents/io.github.umutylcn.blackboard-sync.menubar.plist`,
that starts the app every time you log in; macOS may show a "Background item
added" notice for Python. Untick it (or `--disable-autostart`) to remove the
file; the change takes effect when you press **Kaydet**. No administrator rights are needed and nothing is installed outside your
user account.

### What the menu shows

| Item | What it does |
| --- | --- |
| `✓ UMUT YALÇIN · 14:05 senkronize edildi` | Who is signed in and when the last sync ran (greyed out, information only). When the session expired, a red **⚠ Oturum sona erdi — Giriş yap** row takes its place; when nobody is signed in, **Giriş yap**. Either opens the Blackboard sign-in window (same as `blackboard-sync login`); as soon as you are in, a sync starts. |
| `14 yeni dosya, 2 yeni not · sonraki: 14:19` | What the last sync brought (or the error) and when the next one is due. While a sync or sign-in runs it says so instead. |
| **Şimdi senkronize et** | Sync right away instead of waiting for the next hourly run. Greyed out while a sync or sign-in is running. |
| **Dersler** | The courses of the term; click one to open its folder. |
| **Son indirilenler** | The last 10 files, notes and announcements that came in. Click one to open it (or its folder, if you moved the file). |
| **University klasörünü aç** | Opens the University folder inside the folder chosen in **Ayarlar…** in Finder; the item carries that folder's name. |
| **Güncelleme var: X — Güncelle** | Only when a new version is available: download and install it (see [Updates](#updates)). |
| **Ayarlar…** | Opens the [settings window](#settings): account, folder, start at login, updates. |
| **Çık** | Quit the app. |

The icon tells you the state at a glance:

| Icon | Meaning |
| --- | --- |
| graduation cap | Everything fine. |
| circling arrows | A sync is running. |
| **red** person with an exclamation mark | Your Blackboard session expired: choose **Giriş yap**. |
| **orange** warning triangle | The last sync failed (e.g. no internet); it retries in 10 minutes. |

### When it syncs and notifies

- About 30 seconds after the app starts, then at the chosen **Otomatik
  senkron** interval (every hour by default). After the Mac wakes up, an
  overdue sync runs within half a minute. Changing the interval moves the next
  run; one that would already be overdue starts 30 seconds later.
- Never two at once: the app runs one sync (normal or **Silinenleri tekrar
  indir**) or sign-in at a time, and if a
  `blackboard-sync sync` from the terminal is already running (the lock file),
  it waits and tries again in 10 minutes (or after the interval, if that is
  shorter; never in manual mode).
- After a run with something new, **one** notification lists each changed
  course on its own line, for example `CSE303: 2 yeni dosya, 1 yeni duyuru`.
  Clicking it opens that course's folder (when several courses changed, the
  term folder that contains them). No notification when nothing is new.
- When the session expires you get **one** notification asking you to sign in
  (clicking it opens the sign-in window). It is not repeated every hour; the
  red icon stays until a sync succeeds again.

Under the hood every run is exactly
`blackboard-sync --base-url <school> sync --json --dest <folder>` with the
values from the settings window (see
[the single-run contract](#for-the-scheduler-single-run-contract)), so the app
downloads the same files into the same folders as the command does.

## Commands and options

```
blackboard-sync [--base-url URL] [--data-dir DIR] [-v] login [--browser auto|chrome|edge|brave|vivaldi|opera|operagx|chromium|arc|inapp] [--timeout S]
blackboard-sync [...] check [--term NAME | --all-terms] [--course CODE ...]
blackboard-sync [...] sync  [--term NAME | --all-terms] [--course CODE ...]
                            [--dest DIR] [--json] [--dry-run] [--refetch-missing]
```

| Option | Meaning |
| --- | --- |
| `--dest DIR` | Base folder (default: the folder saved in the menu bar app's settings, else `~/Documents/University`; env `BBSYNC_DEST`). Files go into its `University` subfolder unless the folder is already named University. |
| `--term NAME` | Sync a specific term by its Blackboard name, e.g. `"2025-2026 Bahar"`. |
| `--all-terms` | Sync every term, including past ones and courses without a term. |
| `--course CODE` | Only this course (`CSE303`, or the course id); repeatable. Case and Turkish dots do not matter: `bil101` finds `BİL101`. |
| `--dry-run` | Show what would be fetched; write and download nothing. |
| `--refetch-missing` | Download again files you deleted locally (normally deletions are respected). |
| `--json` | Print the run summary as JSON (see below). |
| `--base-url URL` | Another Blackboard site (default: the saved school address, else İSTÜN; env `BBSYNC_BASE_URL`). |
| `--data-dir DIR` | Where the session and state live (env `BBSYNC_DATA_DIR`). |

The announcements folder is called `Duyurular` like on the site; set
`BBSYNC_ANNOUNCEMENTS_FOLDER` to rename it.

**Which term is "current"?** The term whose dates include today (counting from
a month before it starts, since courses open early). Between terms it is the
most recently started term. Courses the instructor has not opened yet
(shown as private) are skipped until they open.

## Where things go

| What | Where |
| --- | --- |
| Course material | `~/Documents/University/<term>/<course code> <course name>/...` (another chosen folder: `<folder>/University/<term>/...`) |
| Settings (school address, folder) | `~/Library/Application Support/blackboard-sync/settings.json` |
| Session cookies | `~/Library/Application Support/blackboard-sync/session.json` |
| Sign-in browser profile | `~/Library/Application Support/blackboard-sync/browser-profile/` |
| In-app sign-in window's web data | `~/Library/WebKit/` (the app's or Python's folder) |
| Sync state | `~/Library/Application Support/blackboard-sync/state.json` |
| Last run summary | `~/Library/Application Support/blackboard-sync/last-run.json` |
| Menu bar app state and log | `~/Library/Application Support/blackboard-sync/menubar.json`, `menubar.log` |
| Start-at-login item | `~/Library/LaunchAgents/io.github.umutylcn.blackboard-sync.menubar.plist` |

The data folder is created with owner-only permissions (`700`) and the files in
it are `600`. None of it lives in this repository. (Windows paths are listed
under [Windows](#windows).)

Course codes may contain Turkish letters (`İNG101`, `TÜR101`). Versions
before this support named such folders after the full course id
(`İNG101-1 İNG101 İngilizce I`); the first sync after updating renames them to
`İNG101 İngilizce I` without downloading anything again. If that name is
already taken or the folder cannot be moved (for example a file in it is open
on Windows), the old folder is kept and used, a warning says why, and the next
sync tries again.

File and folder names are kept as on Blackboard. Only what macOS cannot store
safely is changed: `/` and `:` become `-` (`"Intro: Sorting"` becomes
`Intro - Sorting`), control characters and leading dots are removed, and very
long names are shortened to the 255-byte limit while keeping the extension.
On Windows a few more rules apply there only (see
[Windows](#windows)); names on a Mac are not affected.

## How the incremental state works

`state.json` records, keyed by Blackboard's own ids:

- every content item and announcement, with the `modified` timestamp seen last
  time — an unchanged item is skipped without any download;
- every local file written (attachment, embedded file or note), with its path
  and SHA-256.

When an item changes on Blackboard, its files are fetched again and compared:

- **same bytes** — nothing happens and nothing is reported;
- **new bytes, your local copy untouched** — the copy is replaced and reported
  as an updated file;
- **new bytes, but you edited the local copy** (e.g. highlighted the PDF) —
  your copy is kept and the new version is saved next to it as `name (2).pdf`.

Two items with the same name in one folder get `name (2)`, `name (3)`, …
An identical file already sitting at the target path is adopted, not
duplicated. Files that disappear from Blackboard, or that Blackboard renames or
moves, stay where they are locally — the tool never deletes or moves your
files. If you delete a downloaded file it is not downloaded again unless you
pass `--refetch-missing`.

To start over completely, delete `state.json`: the next run re-checks
everything, adopts files that are already present and identical, and fetches
the rest.

## Session expiry

Blackboard sessions expire after a while. When that happens `sync` and `check`
stop with:

```
Your Blackboard session has expired. Run `blackboard-sync login` to sign in to Blackboard.
```

and exit with status **3**. `login` reuses its own browser profile, so signing
in again is often just a click. Cookies that Blackboard refreshes during a run
are saved back, which keeps a regularly used session alive longer.
In the menu bar app the icon turns red and one notification asks you to sign
in; choose **Giriş yap** there instead of typing `login`.

## For the scheduler: single-run contract

`blackboard-sync sync --json` performs one complete pass and prints a JSON
summary; the same summary is written to `last-run.json` (dry runs excepted).

| Exit status | `status` | Meaning |
| --- | --- | --- |
| 0 | `ok` | Sync finished (check `warnings` for courses or folders that could not be read). |
| 3 | `login_required` | Session missing or expired — ask the student to run `login`. |
| 4 | `locked` | Another sync is still running; this run did nothing. |
| 1 | `error` | Network or unexpected Blackboard error; details in `message`. |

```json
{
  "status": "ok",
  "message": "",
  "started_at": "2026-10-03T12:00:00+00:00",
  "finished_at": "2026-10-03T12:00:09+00:00",
  "dry_run": false,
  "dest": "/Users/you/Documents/University",
  "terms": ["2026-2027 Güz"],
  "courses": [
    {
      "code": "CSE303", "name": "Algorithm Analysis",
      "folder": "2026-2027 Güz/CSE303 Algorithm Analysis",
      "new_files": ["2026-2027 Güz/CSE303 Algorithm Analysis/Lecture Notes/Week 2/week2.pdf"],
      "updated_files": [], "new_notes": [], "updated_notes": [],
      "new_announcements": [], "updated_announcements": [], "warnings": []
    }
  ],
  "warnings": [],
  "totals": {"new_files": 1, "updated_files": 0, "new_notes": 0, "updated_notes": 0,
             "new_announcements": 0, "updated_announcements": 0},
  "changed_courses": [
    {"code": "CSE303", "name": "Algorithm Analysis", "summary": "CSE303: 1 new file", "changes": 1}
  ]
}
```

`dest` is the University folder the files are in, and paths in the summary are
relative to it. When the run first moved an older version's files into it,
`moved_into_root` counts them and `left_outside_root` lists the ones that could
not be moved. `changed_courses[].summary` is a
ready-made one-line notification text. Concurrent runs are prevented with a
lock file.

## How it talks to Blackboard

Blackboard Learn Ultra's web pages are built on its REST API under
`/learn/api`, and that API accepts the browser session of a signed-in student.
The tool therefore makes plain read-only `GET` requests with your session
cookies — no page scraping and no application key:

| Purpose | Endpoint |
| --- | --- |
| Who is signed in (also the session check) | `/learn/api/public/v1/users/me` |
| Your courses | `/learn/api/public/v1/users/{userId}/courses?expand=course` |
| Term name and dates | `/learn/api/public/v1/terms/{termId}` |
| Course content tree | `/learn/api/public/v1/courses/{courseId}/contents` and `.../contents/{id}/children` |
| Files of an item | `.../contents/{id}/attachments` and `.../attachments/{id}/download` |
| Files embedded in a page | `data-bbfile` links (`/bbcswebdav/...xid-...`) inside the item body; Ultra documents keep them in a hidden `ultraDocumentBody` child, saved in the parent folder |
| Announcements | `/learn/api/public/v1/courses/{courseId}/announcements` (falls back to `/learn/api/v1/...`) |

All of these routes were confirmed to exist on blackboard.istun.edu.tr (Learn
4001): without a session they answer `401 API request is not authenticated`,
while unknown routes answer `404`. The original sign-in flow was also exercised up
to the Microsoft sign-in page with the installed Chrome. What a student session may read inside them
can only be confirmed by signing in, which is what the first-run steps above
do; anything a course does not allow is reported as a warning for that course
instead of stopping the run.

## Troubleshooting

**The sign-in window opened but I cannot type into it (keys go to the
terminal).** Versions before this fix started the browser program directly from
the command. When that command runs inside a terminal multiplexer or session
manager (tmux, herdr, ...), the shell lives in a background macOS session, and a
browser started from there can show its window without ever becoming the active
app that receives the keyboard. `login` now asks macOS itself to open the
browser (the same way the Dock does), so the window comes to the front and takes
the keyboard. Update and run `blackboard-sync login` again. If it still happens,
click once inside the sign-in window; if typing still goes to the terminal,
run `login` from a plain iTerm or Terminal tab (outside tmux/herdr) and report it.

**"The browser did not start."** A sign-in window from an earlier attempt is
probably still open with the same private profile. Quit that window (it is the
one without your usual tabs) and run `login` again.

**"The sign-in window needs the Microsoft Edge WebView2 Runtime" (Windows).**
WebView2 comes with Windows 10 and 11, but it can be missing on stripped-down
or very old installations. Install the Evergreen runtime from
<https://go.microsoft.com/fwlink/p/?LinkId=2124703>, or install Chrome or Edge,
then sign in again.

**The sign-in window says the browser or app is not allowed.** Some schools'
identity providers block embedded web views. Install a Chromium-based browser
(Chrome, Edge, Brave, Opera, Vivaldi, ...) and sign in again; it is used
automatically.

**`login` keeps waiting after I signed in.** It finishes once Blackboard's own
pages load for you. If you ended on an error page, open
<https://blackboard.istun.edu.tr> in that window and finish signing in there.

**The menu bar icon does not appear.** Check
`~/Library/Application Support/blackboard-sync/menubar.log` for an error. If it
says the app is already running, an earlier copy is still alive: find it with
`pgrep -fl blackboard_sync.menubar` and quit it (or `kill` the number shown).
On a crowded menu bar (especially with a notch), macOS hides icons that do not
fit; quit a few other menu bar apps to check.

**No notifications.** Allow notifications for "Python" in System Settings →
Notifications. If your Python cannot use the notification center at all (some
non-framework builds such as pyenv's), the app falls back to plain
notifications that do not open a folder when clicked; the Python from
python.org or Homebrew works.

**The icon stays red after signing in from the terminal.** It turns back to
normal after the next successful sync; choose **Şimdi senkronize et** to do it
right away.

**"Start at login" does nothing after moving the repository.** The login item
points at this checkout's `.venv` (or at the app, if you moved the app). Untick
and tick **Bilgisayar açılınca başlat** again.

## Privacy

- Your password is typed only into Blackboard's own sign-in page, in a real
  browser window or the system web view of the in-app window; this tool never
  receives it.
- While `login` waits for you, the sign-in browser listens on a random local
  DevTools port (127.0.0.1 only) so the tool can read the Blackboard cookies
  once you are in; the port closes with that window.
- Only cookies for the Blackboard site are saved, in a file only your user
  account can read. Single-sign-on cookies stay inside the tool's private
  browser profile.
- Nothing is sent anywhere except to Blackboard itself, and, for the menu
  bar app's update check, an anonymous request to GitHub for this project's
  latest release (switch it off with **Güncellemeleri otomatik denetle**).
- Session data, sync state and course material are never stored in this
  repository; `.gitignore` also blocks them as a safety net.
- To remove everything: delete
  `~/Library/Application Support/blackboard-sync/` (and the course folders if
  you want).

## Windows

The command-line tool also runs on Windows 10 and 11. For the tray app, follow
[the source instructions below](#windows-tray-app-from-source).
For packaged installation, see the [README](../README.md). To use only the command-line tool:

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
.venv\Scripts\python -m pip install --no-deps -e .
.venv\Scripts\blackboard-sync login
.venv\Scripts\blackboard-sync sync
```

Requirements: Python 3.10 or newer from python.org. `login` picks Chrome if it
is installed, otherwise Edge, Brave, Vivaldi, Opera, Opera GX or Chromium
(`--browser chrome|edge|brave|vivaldi|opera|operagx|chromium` to choose), and
opens it as a separate window with its own private profile, exactly like on a
Mac. Without any of them (or with `--browser inapp`) it signs in in its own
WebView2 window (pywebview, through pythonnet); see
[Troubleshooting](#troubleshooting) if the WebView2 Runtime is missing.

| What | Where on Windows |
| --- | --- |
| Course material | `Documents\University\<term>\<course code> <course name>\...` (your Documents folder, also when it is in OneDrive; another chosen folder: `<folder>\University\<term>\...`) |
| Session, sign-in profile, state, last run | `%APPDATA%\blackboard-sync\` |

Differences from macOS:

- **Permissions.** Windows has no `600`/`700` modes. When the data folder is
  created, its inherited permissions are replaced with full control for your
  user account (and the Windows system account), and everything inside,
  including `session.json`, inherits that. Administrators can still take
  ownership of any file, as on every Windows. If setting the permissions fails,
  the folder keeps Windows' defaults, which under `%APPDATA%` already keep other
  standard users out.
- **Names.** Characters Windows does not allow are changed: `\` and `|` become
  `-`, `"` becomes `'`, `<` `>` become `(` `)`, and `?` `*` are dropped.
  Reserved device names get a `_` (`CON` becomes `CON_`, `nul.txt` becomes
  `nul_.txt`). Names are kept to 120 characters.
- **Path length.** Windows limits a full path to 260 characters unless long
  paths are enabled, and Explorer, Office and Acrobat often cannot open longer
  ones even then. So paths are kept under that limit whether or not long paths
  are enabled: a long folder name below the course folder may use at most half
  of the room still left (never less than 16 characters), keeping its start
  and end around a `…` (`Week 05 - Normalizati…Part 2`), and file names are
  shortened (keeping the extension) to fit what remains. Folders that an older
  version created with the full name are renamed on the next sync, the same way
  as course folders with Turkish codes: nothing is downloaded again, and if the
  folder cannot be moved it is kept and used, with a warning. With a very long
  destination folder and many nested folders a path can still be too long;
  that item is skipped with a warning, and a shorter destination with `--dest`
  (for example `C:\University`) fixes it.

## Development

```sh
./scripts/setup.sh
.venv/bin/pytest
```

Tests run entirely against hand-written sample responses in
`tests/fixtures/` (no real accounts or data) and cover path building and the
mirrored tree, name sanitizing, incremental state, session-expiry detection
and note rendering. The menu bar app's decisions (scheduling, session-expiry
handling, notification and menu text, the login item) live in plain modules
under `src/blackboard_sync/menubar/` and are tested without a GUI session;
only `menubar/app.py` touches AppKit.

## Building the app and releases

```sh
./scripts/setup.sh
./scripts/build-app.sh   # dist/Blackboard Sync.app and dist/Blackboard-Sync-<version>.dmg
```

The app is built with PyInstaller (installed into `.venv` only) and bundles
Python and all dependencies. A local build is ad-hoc signed, not notarized, so on first
launch macOS says the developer cannot be verified: right-click the app →
**Open** once. Release builds are signed with the maintainer's Developer ID and
notarized by the `Release` workflow once the signing secrets are set; see
[SIGNING.md](SIGNING.md). Sync and sign-in runs re-invoke the app's own executable with
the CLI subcommand (`packaging/app_entry.py`).

The version lives in `src/blackboard_sync/__init__.py` (`pyproject.toml` reads
it). To release, bump it, merge, then push a matching tag:

```sh
# Replace <version> with the value of __version__.
git tag "v<version>"
git push origin "v<version>"
```

The `Release` workflow builds the `.dmg` on a macOS runner and the Windows
installer on a Windows runner, then publishes one GitHub Release holding both
plus a `SHA256SUMS.txt` covering both, which the app's updater verifies them
against. Rerunning it for the same tag replaces the release's assets. Running
the workflow by hand (Actions > Release > Run workflow) builds and smoke-tests
both files as workflow artifacts and publishes nothing. A tag with a `-`
(`v1.3.0-rc1`) is published as a pre-release, which `install.sh` and the
updater ignore.

### Windows installer

On Windows with Python 3.12 and [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`iscc`) on `PATH`:

```powershell
./scripts/build-windows.ps1   # dist\Blackboard-Sync-<version>-Setup.exe
```

PyInstaller freezes the tray app (`packaging/blackboard_sync_windows.spec`) into
two programs sharing one folder: the windowed `Blackboard Sync.exe`, and
`blackboard-sync-cli.exe`, a console twin the app runs for sync and sign-in
jobs (a windowed exe may lose its standard streams, and the job's report is read
from them). `packaging/installer.iss` installs per user into
`%LOCALAPPDATA%\Programs\Blackboard Sync` (no administrator rights), adds a
Start Menu shortcut and starts the app. It closes a running copy before an
upgrade and starts it again afterwards, also with `/VERYSILENT`, which is how
the updater runs it. The uninstaller removes the app and its start-at-login
entry, never the downloaded files or `%APPDATA%` data. The installer is
unsigned: Windows SmartScreen shows "Ek bilgi > Yine de çalıştır" once.
`scripts/smoke-test-windows.ps1` (run by the workflow) installs, checks the
installed app and `--version`, checks the GUI (within 45 s `windows-tray.log`
exists, the app runs and its first-run window "Blackboard Sync kurulumu" is
visible; closed and started again, the running copy shows it), upgrades, and
uninstalls. On a failure it prints `scripts/windows-gui-snapshot.ps1`: the
app's windows, its data folder and the logs (the periodic thread stacks are in
`windows-tray-faults.log`).

The `CI` workflow runs the tests on macOS and Windows for pull requests and pushes to `main`.

The release asset contract is `Blackboard-Sync-<version>.dmg` for macOS and
`Blackboard-Sync-<version>-Setup.exe` for Windows. Both must be listed in the
release's `SHA256SUMS.txt`; the updater rejects missing or mismatched checksums.
The first public release, `v1.0.0`, must ship both installers together. Check
`.github/workflows/release.yml` for the build jobs before publishing. The
Windows updater launches the installer with
`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`; the installer must restart the app
(with `--background`, so an update does not open the settings window).

### One-line installers

`install.sh` (macOS) and `install.ps1` (Windows) download the latest release,
verify its SHA-256 checksum and install it. A macOS release signed with the
Developer ID must also pass `install.sh`'s signature, team and notarization
checks or nothing is installed. For an unsigned release only the installed
app's quarantine attribute is removed, which makes the first-open right click →
**Aç** step unnecessary. No Python is needed: sign-in uses an
installed Chromium-based browser (Chrome, Edge, Brave, Opera, Vivaldi) or, if
there is none, the app's own window.

## License

MIT, see [LICENSE](../LICENSE).

### Windows tray app (from source)

The Windows 10/11 tray app uses the same menu, hourly sync schedule, settings,
CLI jobs and locks as the macOS app. Install Python 3.12 from python.org with
**pip** and **Tcl/Tk** enabled (sign-in uses an installed Chromium-based browser,
else the app's WebView2 window). Download
or clone this repository, open PowerShell in its folder, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m blackboard_sync.windows
```

The first launch opens settings: enter your school's Blackboard URL, choose a
folder (default: `Documents\University`), and select **Giriş yap**. Complete sign-in in
the window that opens. Right-click the tray icon next to the clock (possibly inside the
hidden-icons arrow) for the shared menu. Later, launch without a console with:

```powershell
.\.venv\Scripts\pythonw.exe -m blackboard_sync.windows
```

**Bilgisayar açılınca başlat** toggles only the current user's
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\BlackboardSync` value,
which starts the app with `--background` (tray only). Any other start (the
installer's last page, the Start Menu) opens the settings window in front; when
the app is already running, the new start asks the running copy to do that and
exits. After the first settings window closes, a one-time tray notification
says the app keeps running from the icon next to the clock (maybe under the
**^** hidden-icons arrow).
Keep this checkout and its virtual environment in place while it is enabled;
disable the option before moving or deleting them. No administrator rights are
needed. Settings and logs (`windows-tray.log`) live under
`%APPDATA%\blackboard-sync` unless `BBSYNC_DATA_DIR` overrides it. The log is
opened before anything else is imported (`windows/startup.py`; it rotates at
1 MB, keeping three older files), together with `faulthandler`, which writes
to `windows-tray-faults.log`; an unhandled error shows a message box naming the log. To see
where a running app waits, start it with `BBSYNC_STACK_DUMP=<seconds>`: every
thread's stack is then written to `windows-tray-faults.log` at that interval.

Toasts show one Turkish summary line per changed course. Clicking opens the
course folder, or the common parent folder when several courses changed, via a
`file:` URI. Windows notification policies can suppress toasts or protocol
activation; the tray's folder menu remains available. Expiry notifications ask
you to sign in from the menu. Toast delivery uses Windows PowerShell and WinRT;
no browser extension is required. Native Windows menus do not expose colored
text through pystray, so expiry uses the shared warning label and a red icon.
Idle is green, syncing blue, and errors orange. Settings saves and exit wait
until a running sync/sign-in finishes. For packaged installation, see the [README](../README.md).

The Windows tray also uses the shared daily update checker. Settings include
**Güncellemeleri otomatik denetle**; the version row checks manually even when
that setting is off. Source checkouts open the release page for updates.
Packaged builds download and verify the Windows installer on a worker thread,
then exit after launching it. Installation waits until sync/sign-in is idle and
blocks new jobs while downloading. Update-toast clicks use the current user's
`HKCU\Software\Classes\blackboard-sync` URI registration to forward a fixed
update action to the running tray; no URI-supplied command is executed.
