# blackboard-sync

Mirrors new Blackboard course content into local folders automatically.

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

Scheduling (an hourly background run with macOS notifications) is a separate
add-on; it calls `blackboard-sync sync --json` described below.

## Setup

Requirements: macOS, Python 3.10 or newer (`python3 --version`), and Google
Chrome or Brave in `/Applications`.

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

A Chrome window (Brave if Chrome is missing; force one with
`--browser chrome|brave`) opens on the Blackboard sign-in page, which for
blackboard.istun.edu.tr forwards to the university's Microsoft sign-in. Sign in
exactly as you normally do, including any two-factor step. As soon as Blackboard accepts you, the window closes by itself and the
terminal prints `Signed in as <your user name>`. You have 10 minutes
(`--timeout SECONDS` to change).

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

## Commands and options

```
blackboard-sync [--base-url URL] [--data-dir DIR] [-v] login [--browser auto|chrome|brave] [--timeout S]
blackboard-sync [...] check [--term NAME | --all-terms] [--course CODE ...]
blackboard-sync [...] sync  [--term NAME | --all-terms] [--course CODE ...]
                            [--dest DIR] [--json] [--dry-run] [--refetch-missing]
```

| Option | Meaning |
| --- | --- |
| `--dest DIR` | Base folder (default `~/Documents/Okul`, env `BBSYNC_DEST`). |
| `--term NAME` | Sync a specific term by its Blackboard name, e.g. `"2025-2026 Bahar"`. |
| `--all-terms` | Sync every term, including past ones and courses without a term. |
| `--course CODE` | Only this course (`CSE303`, or the course id); repeatable. |
| `--dry-run` | Show what would be fetched; write and download nothing. |
| `--refetch-missing` | Download again files you deleted locally (normally deletions are respected). |
| `--json` | Print the run summary as JSON (see below). |
| `--base-url URL` | Another Blackboard site (env `BBSYNC_BASE_URL`). |
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
| Session cookies | `~/Library/Application Support/blackboard-sync/session.json` |
| Sign-in browser profile | `~/Library/Application Support/blackboard-sync/browser-profile/` |
| Sync state | `~/Library/Application Support/blackboard-sync/state.json` |
| Last run summary | `~/Library/Application Support/blackboard-sync/last-run.json` |

The data folder is created with owner-only permissions (`700`) and the files in
it are `600`. None of it lives in this repository.

File and folder names are kept as on Blackboard. Only what macOS cannot store
safely is changed: `/` and `:` become `-` (`"Intro: Sorting"` becomes
`Intro - Sorting`), control characters and leading dots are removed, and very
long names are shortened to the 255-byte limit while keeping the extension.

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
while unknown routes answer `404`. The sign-in flow was also exercised up to
the Microsoft sign-in page with the installed Chrome. What a student session may read inside them
can only be confirmed by signing in, which is what the first-run steps above
do; anything a course does not allow is reported as a warning for that course
instead of stopping the run.

## Privacy

- Your password is typed only into Blackboard's own sign-in page in a real
  browser window; this tool never receives it.
- Only cookies for the Blackboard site are saved, in a file only your user
  account can read. Single-sign-on cookies stay inside the tool's private
  browser profile.
- Nothing is sent anywhere except to Blackboard itself.
- Session data, sync state and course material are never stored in this
  repository; `.gitignore` also blocks them as a safety net.
- To remove everything: delete
  `~/Library/Application Support/blackboard-sync/` (and the course folders if
  you want).

## Development

```sh
./scripts/setup.sh
.venv/bin/pytest
```

Tests run entirely against hand-written sample responses in
`tests/fixtures/` (no real accounts or data) and cover path building and the
mirrored tree, name sanitizing, incremental state, session-expiry detection
and note rendering.
