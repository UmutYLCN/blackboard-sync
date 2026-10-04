# Development guide

Developer setup, CLI reference, architecture, and troubleshooting for Blackboard Sync.
For installation, see the [README](../README.md). Commands below run from the repository root.

`blackboard-sync` signs in to Blackboard Learn Ultra
(default: <https://blackboard.istun.edu.tr>) using your own browser session,
finds your courses for the current term, and copies everything in them to
`~/Documents/Okul/` with the same folder structure you see on the site:

```
~/Documents/Okul/
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

Requirements: macOS, Python 3.10 or newer (`python3 --version`), and Google
Chrome, Brave, or Microsoft Edge in `/Applications` or `~/Applications`. On Windows, see
[Windows](#windows).

```sh
./scripts/setup.sh
```

This creates a project-local virtual environment in `.venv/` and installs the
pinned dependencies from `requirements.lock`. Nothing is installed globally and
no browser is downloaded — sign-in uses the Chrome or Brave you already have.
After setup the command is `.venv/bin/blackboard-sync` (or activate the
environment with `source .venv/bin/activate` and type `blackboard-sync`).

## First run

### 1. Sign in

```sh
.venv/bin/blackboard-sync login
```

A separate Chrome window (Brave if Chrome is missing, then Microsoft Edge;
force one with `--browser chrome|brave|edge`) opens in front, on the Blackboard sign-in page, which
for blackboard.istun.edu.tr forwards to the university's Microsoft sign-in.
It is started like any app you open from the Dock, with its own private profile,
so your everyday browser and its tabs are not touched. Sign in exactly as you
normally do, including any two-factor step. As soon as Blackboard accepts you,
that window closes by itself and the terminal prints
`Signed in as <your user name>`. You have 10 minutes (`--timeout SECONDS` to
change).

The tool never asks for, sees, or stores your password. It only keeps the
session cookies Blackboard gives your browser after you sign in.

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
Synced 8 course(s) for 2026-2027 Güz into /Users/you/Documents/Okul
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

The first time the app starts, a small **Blackboard Sync kurulumu** window
asks for:

- **Okulunuzun Blackboard adresi** — prefilled with
  `https://blackboard.istun.edu.tr`; students of another university type their
  school's Blackboard address instead (it must be `https://`; a pasted course
  link is reduced to the site address).
- **Dosyaların kaydedileceği klasör** — prefilled with `~/Documents/Okul`;
  **Seç…** opens a folder picker.
- **Bilgisayar açılınca başlat** — ticked by default (see below).
- **Güncellemeleri otomatik denetle** — ticked by default (see
  [Updates](#updates)).

**Giriş yap** saves and opens the Blackboard sign-in window; **Kaydet** only
saves. Nothing is synced on a schedule until the window has been saved once.
Choose **Ayarlar…** in the menu to change the settings later:

- A different school address requires signing in again; the sign-in window
  opens as soon as you save.
- A different folder applies to future syncs only. Files already downloaded
  stay where they are; nothing is moved or deleted.

The choices are stored in `settings.json` in the data folder (see
[Where things go](#where-things-go)). The `blackboard-sync` command reads the
same file, so after the window is saved the terminal syncs the same school
into the same folder without any flags; `BBSYNC_*` variables and command-line
options still override it for the terminal.

### Updates

Once a day the app asks GitHub whether a newer release exists (only while
**Güncellemeleri otomatik denetle** is ticked) and posts one notification per
new version, "Blackboard Sync 1.1.0 hazır — Güncelle". The version row at the
bottom of the menu then reads **Güncelleme var: 1.1.0 — Güncelle**; otherwise
**Sürüm … · Güncellemeleri denetle** checks right away and answers with a
notification.

**Güncelle** downloads `Blackboard-Sync-<version>.dmg` into Downloads, checks
it against the release's `SHA256SUMS.txt`, opens it and explains the last
step: quit Blackboard Sync and drag the new app over the old one in
Applications. The app is not signed with a paid Apple certificate, so it does
not replace itself silently. Run from a checkout, **Güncelle** opens the
release page instead.

Checking needs the GitHub repository to be public: without signing in, GitHub
does not show a private repository's releases, and the app then simply finds
no update. No account data is sent; the request is an anonymous call to
`api.github.com`.

### Start at login

Tick **Bilgisayar açılınca başlat** in the menu (or run
`.venv/bin/blackboard-sync-menubar --enable-autostart`). This writes a per-user
LaunchAgent, `~/Library/LaunchAgents/io.github.umutylcn.blackboard-sync.menubar.plist`,
that starts the app every time you log in; macOS may show a "Background item
added" notice for Python. Untick it (or `--disable-autostart`) to remove the
file. No administrator rights are needed and nothing is installed outside your
user account.

### What the menu shows

| Item | What it does |
| --- | --- |
| `Son senkron: 14:00 · 3 yeni dosya` | Result of the last run (greyed out, information only), followed by when the next one is due. Shows `oturum sona erdi` when you need to sign in again, or `hata` plus the error. |
| **Şimdi senkronize et** | Sync right away instead of waiting for the next hourly run. Greyed out while a sync or sign-in is running. |
| **Silinenleri tekrar indir** | Runs one sync that also downloads again the files you deleted locally (the same as `blackboard-sync sync --refetch-missing`), for example after deleting the whole `Okul` folder by mistake. Files you only edited are not touched, and the notification still has one line per course. The hourly runs and **Şimdi senkronize et** keep respecting deletions. |
| **Giriş yap** | Opens the Blackboard sign-in window (same as `blackboard-sync login`). As soon as you are in, a sync starts. |
| **Okul klasörünü aç** | Opens the folder chosen in **Ayarlar…** (`~/Documents/Okul` by default) in Finder. |
| **Son indirilenler** | The last 10 files, notes and announcements that came in. Click one to open it (or its folder, if you moved the file). |
| **Ayarlar…** | Reopens the [settings window](#settings): school address, folder, start at login, update checks. |
| **Bilgisayar açılınca başlat** | Start the app at login (see above). A check mark means it is on. |
| **Sürüm … · Güncellemeleri denetle** | Check for a new version now. Reads **Güncelleme var: X — Güncelle** when one is available; click it to download and install it (see [Updates](#updates)). |
| **Çıkış** | Quit the app. |

The icon tells you the state at a glance:

| Icon | Meaning |
| --- | --- |
| graduation cap | Everything fine. |
| circling arrows | A sync is running. |
| **red** person with an exclamation mark | Your Blackboard session expired: choose **Giriş yap**. |
| **orange** warning triangle | The last sync failed (e.g. no internet); it retries in 10 minutes. |

### When it syncs and notifies

- About 30 seconds after the app starts, then every hour. After the Mac
  wakes up, an overdue sync runs within half a minute.
- Never two at once: the app runs one sync (normal or **Silinenleri tekrar
  indir**) or sign-in at a time, and if a
  `blackboard-sync sync` from the terminal is already running (the lock file),
  it waits and tries again in 10 minutes.
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
blackboard-sync [--base-url URL] [--data-dir DIR] [-v] login [--browser auto|chrome|edge|brave] [--timeout S]
blackboard-sync [...] check [--term NAME | --all-terms] [--course CODE ...]
blackboard-sync [...] sync  [--term NAME | --all-terms] [--course CODE ...]
                            [--dest DIR] [--json] [--dry-run] [--refetch-missing]
```

| Option | Meaning |
| --- | --- |
| `--dest DIR` | Base folder (default: the folder saved in the menu bar app's settings, else `~/Documents/Okul`; env `BBSYNC_DEST`). |
| `--term NAME` | Sync a specific term by its Blackboard name, e.g. `"2025-2026 Bahar"`. |
| `--all-terms` | Sync every term, including past ones and courses without a term. |
| `--course CODE` | Only this course (`CSE303`, or the course id); repeatable. |
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
| Course material | `~/Documents/Okul/<term>/<course code> <course name>/...` |
| Settings (school address, folder) | `~/Library/Application Support/blackboard-sync/settings.json` |
| Session cookies | `~/Library/Application Support/blackboard-sync/session.json` |
| Sign-in browser profile | `~/Library/Application Support/blackboard-sync/browser-profile/` |
| Sync state | `~/Library/Application Support/blackboard-sync/state.json` |
| Last run summary | `~/Library/Application Support/blackboard-sync/last-run.json` |
| Menu bar app state and log | `~/Library/Application Support/blackboard-sync/menubar.json`, `menubar.log` |
| Start-at-login item | `~/Library/LaunchAgents/io.github.umutylcn.blackboard-sync.menubar.plist` |

The data folder is created with owner-only permissions (`700`) and the files in
it are `600`. None of it lives in this repository. (Windows paths are listed
under [Windows](#windows).)

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
  "dest": "/Users/you/Documents/Okul",
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

Paths in the summary are relative to `dest`. `changed_courses[].summary` is a
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
| Files embedded in a page | `/bbcswebdav/xid-...` links inside the item body |
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

- Your password is typed only into Blackboard's own sign-in page in a real
  browser window; this tool never receives it.
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

Requirements: Python 3.10 or newer from python.org, and Google Chrome or
Microsoft Edge (every Windows has Edge; Brave works too). `login` picks Chrome
if it is installed, otherwise Edge (`--browser chrome|edge|brave` to choose),
and opens it as a separate window with its own private profile, exactly like on
a Mac.

| What | Where on Windows |
| --- | --- |
| Course material | `Documents\Okul\<term>\<course code> <course name>\...` (your Documents folder, also when it is in OneDrive) |
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
  paths are enabled. File names are shortened (keeping the extension) so files
  fit under that limit; folder names are not, so a very deep folder structure
  can still be too long. If a sync stops with a path error, choose a shorter
  destination with `--dest` (for example `C:\Okul`) or enable Windows long
  paths.

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
Python and all dependencies. It is ad-hoc signed, not notarized, so on first
launch macOS says the developer cannot be verified: right-click the app →
**Open** once. Sync and sign-in runs re-invoke the app's own executable with
the CLI subcommand (`packaging/app_entry.py`).

The version lives in `src/blackboard_sync/__init__.py` (`pyproject.toml` reads
it). To release, bump it, merge, then push a matching tag:

```sh
# Replace <version> with the value of __version__.
git tag "v<version>"
git push origin "v<version>"
```

The `Release` workflow builds the `.dmg` on a macOS runner and attaches it,
with a `SHA256SUMS.txt` the app's updater verifies it against, to a GitHub
Release. The `CI` workflow runs the tests on macOS and Windows for pull requests and pushes to `main`.

The release asset contract is `Blackboard-Sync-<version>.dmg` for macOS and
`Blackboard-Sync-<version>-Setup.exe` for Windows. Both must be listed in the
release's `SHA256SUMS.txt`; the updater rejects missing or mismatched checksums.
The first public release, `v1.0.0`, must ship both installers together. Check
`.github/workflows/release.yml` for the build jobs before publishing. The
Windows updater launches the installer with
`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`; the installer must restart the app.

## License

MIT, see [LICENSE](../LICENSE).

### Windows tray app (from source)

The Windows 10/11 tray app uses the same menu, hourly sync schedule, settings,
CLI jobs and locks as the macOS app. Install Python 3.12 from python.org with
**pip** and **Tcl/Tk** enabled, and install Chrome or Edge for sign-in. Download
or clone this repository, open PowerShell in its folder, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m blackboard_sync.windows
```

The first launch opens settings: enter your school's Blackboard URL, choose a
folder (default: `Documents\Okul`), and select **Giriş yap**. Complete sign-in in
the browser. Right-click the tray icon next to the clock (possibly inside the
hidden-icons arrow) for the shared menu. Later, launch without a console with:

```powershell
.\.venv\Scripts\pythonw.exe -m blackboard_sync.windows
```

**Bilgisayar açılınca başlat** toggles only the current user's
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\BlackboardSync` value.
Keep this checkout and its virtual environment in place while it is enabled;
disable the option before moving or deleting them. No administrator rights are
needed. Settings and logs (`windows-tray.log`) live under
`%APPDATA%\blackboard-sync` unless `BBSYNC_DATA_DIR` overrides it.

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
