# Planned Work: Investigations

Working notes for the items in [TODO.md](TODO.md). Each item is investigated here first (reproduction, evidence, likely cause, scope). No code changes happen in this document; a confirmed fix becomes a separate implementation task.

Status key: `Todo` · `In progress` · `Done` · `Blocked`

---

## 1. Destination change can leave downloaded files behind

**Status:** In progress (code review done, reproduction pending)
**Source:** [TODO.md](TODO.md), first item
**Reported behavior:** After changing the save folder in Settings and choosing **Move**, the folder structure appears in the new location, but some nested files (PDFs, PowerPoint presentations) do not arrive. Not yet reproduced.

### Todo

- [ ] Reproduce with nested course folders and several file types (PDF, PPTX, PDF notes with hidden `.md` copies) on macOS.
- [ ] Reproduce on Windows with a long destination path, so folder names are shortened.
- [ ] Diff the old and new trees before and after the move, and save the `relocate` log warnings.
- [ ] Check hypothesis H1 (below): list files on disk under the old `University` folder that are missing from `state.json`.
- [ ] Check hypothesis H2 (below): delete one recorded file before the move and see what the move reports.
- [ ] Choose a fix from the proposals below and open an implementation task with regression tests.

### What the code does (evidence)

All paths are relative to the repository root.

- **Only recorded files are moved.** `move_files()` builds its list from `synced_files(state, old)`, which returns the paths in `state.outputs` that exist on disk ([src/blackboard_sync/relocate.py:84-87](../src/blackboard_sync/relocate.py), [relocate.py:192](../src/blackboard_sync/relocate.py)). A file on disk with no entry in `state.json` is never considered: it is not moved and not added to `kept`.
- **Unrecorded files block cleanup silently.** `_move_empty_folders()` removes an old folder only when it is empty ([relocate.py:347-379](../src/blackboard_sync/relocate.py)). A folder holding an unrecorded file stays, so the old tree keeps that file. Nothing reports it.
- **The reported count hides the gap.** `MoveResult.moved` counts recorded, visible files. The app shows "N files moved" and warns only about `kept` entries (conflict or failed). A file that was never recorded produces no warning at all.
- **Documented behavior assumes every file is recorded.** [docs/DEVELOPMENT.md:319-330](DEVELOPMENT.md) says Move "moves every downloaded file". The code only moves recorded files, so the documentation is correct only while `state.json` matches the disk.
- **Move job path.** The UI calls `relocate.move_destination()` under the run lock ([relocate.py:152-178](../src/blackboard_sync/relocate.py)) through `run_move_guarded()` ([src/blackboard_sync/menubar/jobs.py:424-430](../src/blackboard_sync/menubar/jobs.py)).
- **Existing test coverage.** [tests/test_dest_change.py](../tests/test_dest_change.py) covers conflicts, locked files, cross-drive copies, hard links, symlinks, retries and shortened Windows names. It does **not** cover a file that exists on disk but not in `state.json`, or a move with a missing or reset `state.json`. That is the gap this investigation should close.

### Hypotheses (ranked, none reproduced yet)

| # | Hypothesis | Why it fits the report | How to check |
|---|------------|------------------------|--------------|
| H1 | A downloaded file exists on disk but has no entry in `state.json`. It is never moved and never reported. | Matches "the folders arrived, some PDFs and PPTs did not". The old folder keeps those files. | After a sync, compare `files on disk under University` with `state.outputs` paths. Any extra file confirms H1. |
| H2 | A recorded file is already missing from the old folder when Move runs. `synced_files` skips it silently. | The file is not lost (the next sync downloads it again in the new folder), but the move reports nothing about it. | Delete one recorded file, run Move, and read the count and log. |
| H3 | On Windows, the new path budget shortens a name differently from the old one, and the recorded path and disk path disagree. | Explains files missing only on Windows with long destination paths. | Use the long-path fixture from `test_windows_long_paths.py` with a real-length OneDrive path. |
| H4 | A file is open in another program (PowerPoint, Preview, a PDF viewer). | Would be reported as `FAILED`, so it is a weak fit for a silent loss. Keep it as a control case. | Open a PPTX during the move and confirm the warning appears. |

Both H1 and H2 come from one design choice: the state file is the only source of truth for which files are "ours". Anything outside it is either ignored or treated as the student's own.

### Reproduction plan

1. Sync a test course into the old folder. Save a copy of `state.json` and the file tree.
2. Simulate H1: add a file under a course folder that is not in `state.json`, such as a PDF copied from another place. Also keep one recorded file.
3. Simulate H2: delete one recorded file from the old folder.
4. Run Move to a new folder and save the new tree, the result counts and the log.
5. Repeat on Windows with a long destination path.

Expected outcome: the tree diff shows which class of file was left behind, and the log says why.

### Proposed solutions (for discussion)

**S1. Report files left behind, do not guess (recommended first step).**
After the move, walk the old term and course folders and list every file that was not moved and is not a system leftover (`.DS_Store`, `Thumbs.db`, `desktop.ini`). Put them in `MoveResult.kept` with a new reason such as `UNRECORDED`, and show them in the notification and in the log. The student then sees exactly what was left and where it is. Nothing is moved on a guess, so the risk is low.

**S2. Move unrecorded files that clearly belong to a managed course folder.**
Only if S1 confirms H1 in practice. Move a file found inside a recorded course folder when its name also matches a recorded file, or when it sits in the same folder as recorded files. This needs a precise rule, because the student's own files must never move. It is riskier, so decide it after S1.

**S3. Refuse a silent move when the record is missing.**
If `state.json` is missing, reset or set aside, do not report "0 files moved" as success. Say that no sync record exists and suggest running a sync first, or fall back to **Download again**. This closes H2's silent path.

**S4. Verify the whole move at the end.**
After a successful move, compare the set of files in the new folder with the set recorded before the move (name and SHA-256 from the state). Report any mismatch. This costs time on large folders, so consider running it only when the move reported no kept files.

**S5. Regression tests (required with any fix).**
- A file on disk that is not in `state.json` is reported and not silently ignored.
- A recorded file deleted before the move is reported, and the next sync downloads it again.
- A missing `state.json` gives a clear message instead of "0 moved".
- Windows shortened names still line up with the recorded paths after the move.

### Recommendation

Confirm H1 first, because the reproduction is cheap and it decides the whole direction. If H1 is confirmed, implement **S1** and **S3** first: they make the failure visible without any risky automatic moves. Decide **S2** after that, based on how often unrecorded files show up in real folders.

### Out of scope

- No changes to the sync engine or to what counts as a downloaded file.
- No changes to the student's own files; they stay untouched in every option.

---

## 2. Four large files are hard to maintain

**Status:** Investigation done (read-only). Proposals below; no code changed.
**Source:** Project owner request. Not yet listed in [TODO.md](TODO.md).
**Reported problem:** The four largest files are hard to maintain.

### Todo

- [ ] Owner decides the goal: faster feature work, or fewer bugs. This sets the order below.
- [ ] Approve step R1 (dialogs), then start it as a separate branch with a pure move and no behavior change.
- [ ] Before each split, measure coverage of the code being moved so tests are known to cover it.
- [ ] Decide whether the shared `menubar/` core should be renamed (step R5).

### Measurements

Line counts are from `wc -l`. Class sizes are the line span from the `class` line to the next top-level definition.

| File | Lines | Main class (span, methods) | Longest functions (lines) |
|------|-------|----------------------------|---------------------------|
| [src/blackboard_sync/menubar/main_window.py](../src/blackboard_sync/menubar/main_window.py) | 2337 | `MainWindow` (about 1,580 lines, 75 methods); `_Target` (46 action methods); 8 dialog functions | `_build_start` 93, `__init__` 91, `update_status` 78 |
| [src/blackboard_sync/menubar/model.py](../src/blackboard_sync/menubar/model.py) | 1357 | `AppModel` (about 680 lines, 66 methods) | `__init__` 73, `_finish_sync` 66, `apply_settings` 61 |
| [src/blackboard_sync/sync.py](../src/blackboard_sync/sync.py) | 1411 | `Syncer` (about 955 lines, 44 methods) | `process_item` 152, `run_sync` 116, `discover` 109, `sync_announcements` 92 |
| [src/blackboard_sync/windows/main_window.py](../src/blackboard_sync/windows/main_window.py) | 1361 | `MainWindow` (about 1,126 lines, 67 methods) | `update_status` 101, `__init__` 87, `_build_overview` 61 |

### What is in each file

- **`sync.py` (`Syncer`) mixes five jobs:**
  - Folder naming and term placement, lines 382 to 627: `discover`, `assign_term_folders`, `folder_path`, `move_folder`, `migrate_item_outputs`.
  - Item processing, lines 716 to 867: `process_item` with attachments and embedded files.
  - Announcements, lines 931 to 1022.
  - Writing and placing files on disk, lines 1023 to 1290: `fetch_or_link`, `write_output`, `place`, `free_path`.
  - State bookkeeping: `self.state` is used 44 times across these parts.
- **`menubar/model.py` (`AppModel`) mixes four jobs:** scheduling and retries, a job queue (`pending_job`, `begin`), one `finish_*` handler per job type, and saved state (`saved_state`, `restore_pending`). It also builds notification text.
- **`menubar/main_window.py` (`MainWindow`) mixes layout and content for every screen:** sidebar, Home, Activity, Announcements, Settings, Calendar, Courses, the NotebookLM card, animation, and the file dialogs at the bottom of the file. `_Target` holds 46 action methods that call into the window.
- **`windows/main_window.py` (`MainWindow`) repeats the same screen list in tkinter.** The two windows are parallel implementations of the same screens.

### Findings

1. **Two UI packages depend on a package named `menubar`.** The Windows app imports from `blackboard_sync.menubar` in about 14 places: `model`, `jobs`, `settings_form`, `main_window_model`, and `sync_scene`. The shared logic therefore lives under a name that suggests macOS menu bar only. A Windows change looks like a menu bar change.
2. **The project already has a pattern for splitting.** `menubar/main_window_model.py` (744 lines), `settings_form.py` (527), `jobs.py` (663), `presentation.py`, and `sync_scene.py` already hold logic outside the window classes. The large files are the parts not yet split.
3. **Tests give a safety net, with gaps.** CI runs `pytest` on macOS and Windows ([.github/workflows/ci.yml](../.github/workflows/ci.yml)). The sync and model code has good coverage: `tests/test_sync.py` has 40 tests, `tests/test_menubar_model.py` 34, `tests/test_main_window_model.py` 50. Layout code in the window classes is tested less.
4. **Tests patch module-level names.** Tests such as `tests/test_dest_change.py` patch `blackboard_sync.sync` and `blackboard_sync.relocate` attributes (for example `is_windows`). Moving code to a new module breaks those patches unless the tests are updated in the same change. This is the main hidden cost of splitting `sync.py`.
5. **Other modules import from `sync.py`.** `cli.py`, `relocate.py`, `notebooklm/runner.py`, `session_refresh.py`, `uninstall.py` and `update_macos.py` import helpers such as `run_lock` and `sha256_file` from `blackboard_sync.sync`. A split must keep these import paths working.

### Proposals (lowest risk first)

**R1. Move the file dialogs into their own module (no logic change).**
Move the `ask_*` and `show_*` functions from both `main_window.py` files into `dialogs_macos.py` and `dialogs_windows.py`, or one `dialogs/` package per platform. Each file has about 120 lines of dialog code, with no state and no layout. It is a good first change to confirm the process.

**R2. Split `sync.py` into a package, keeping `Syncer` as the coordinator.**
Create `blackboard_sync/sync/` with `__init__.py` re-exporting every name other modules import today (`run_lock`, `sha256_file`, `markdown_key`, `run_sync`, `Syncer`, and so on). Then move the five jobs from the list above into `naming.py`, `items.py`, `announcements.py` and `files.py`. Patch the tests to target the module that uses each name. Keep the file moves separate from any behavior change.

**R3. Split `AppModel` by job.**
Move the `finish_*` handlers and their helper notification functions into a `finish.py` module, and the scheduling functions into `schedule.py`. `AppModel` keeps its public methods as thin delegates, so both platforms and the 34 tests in `tests/test_menubar_model.py` keep working unchanged.

**R4. Split the window classes by screen.**
Create one module per screen (Home, Activity, Announcements, Settings, Calendar, Courses) with a builder function that receives the window. Keep the sidebar, top bar and shared helpers in a common module. Start with the Settings screen in one platform and copy the pattern to the other only after the first is reviewed. Move the 46 `_Target` action methods next to the screen they belong to.

**R5. Rename the shared core from `menubar/` (last).**
Move `model.py`, `jobs.py`, `settings_form.py`, `main_window_model.py` and `sync_scene.py` into a neutral package such as `core_ui/`, and keep `menubar/` for the macOS-only files. This touches imports in about 20 files, so do it as one small PR with no other changes. It is not visible to users.

### Recommendation

Do R1 first: it is small, has no logic, and proves the process. Then R2 for `sync.py`, because it is the biggest backend file and has the best test coverage. R3 and R4 come next, and R5 last, once the code has moved and the names are clear.

### Out of scope

- No changes to what the app does, to the file formats, or to the Blackboard API calls.
- No rewrite of the two UI toolkits (AppKit and tkinter).

---

## 3. Find the Blackboard address automatically, for universities worldwide

**Status:** First step built on branch `feat/school-picker` (approach A with the 16 verified schools below; see "Known schools" in [DEVELOPMENT.md](DEVELOPMENT.md)). The worldwide list, approaches B and D, and an Arabic interface are still open.
**Source:** Project owner request. Most downloads come from Saudi Arabia, so Saudi universities come first.
**Goal:** The student should not have to know or type the Blackboard address. The app finds it for any university.

### Todo

- [ ] Owner picks the approach (A is recommended below).
- [ ] Turn the owner's list (84 institutions, names only) into hostnames, and verify each one with the check described below.
- [ ] Get the three Saudi hosts that did not answer (PNU, KAU, IAU) from a network inside Saudi Arabia, or from students there.
- [ ] Decide where the school list lives and how it updates.
- [ ] Test a real sign-in and one sync with a Saudi account (term names, single sign-on).
- [ ] Decide on an Arabic interface (see risks).

### How the app handles the address today

- The address is one text field. The default is `https://blackboard.istun.edu.tr` ([src/blackboard_sync/config.py:17](../src/blackboard_sync/config.py)).
- `normalize_base_url()` reduces whatever the student types to `https://host` ([src/blackboard_sync/settings.py:113-140](../src/blackboard_sync/settings.py)). The student must already know the address.
- Everything else takes the address as a parameter: the API client, the sign-in windows, the saved session and the sync. So a school picker only changes the Settings and start screens. The sync engine does not need to change for it, though term naming needs a check (see risks).

### Research findings

**1. A Blackboard host can be recognised with one request, without signing in.**
`GET /learn/api/public/v1/system/version` on a Blackboard Learn host returns a small JSON answer such as `{"learn":{"major":4001,...}}`. I tested it on 19 hosts: 16 answered with this JSON and 3 did not answer at all. It answered on the default Turkish host too, so it works outside Saudi Arabia. This gives a cheap, credential-free check for every candidate address and also for what a student types.

**2. Official university pages rarely state the address.**
I read six Saudi pages. Only two stated or redirected to a Blackboard host (SEU, KFUPM). One gave an SSO path instead of a host (UQU). One returned 404 (PNU), one 403 (KSU) and one named no host (PSAU). Collecting addresses by reading pages is slow and often fails, so it cannot be the main method.

**3. Saudi universities mostly use `lms.<university domain>`.**
Testing that pattern against each university's own `edu.sa` domain worked for 12 of 15 guesses. Hosts that answered with the Blackboard JSON:

| University | Host | Where the adoption is documented |
|------------|------|----------------------------------|
| King Saud University | `lms.ksu.edu.sa` | KSU CELT page names this address |
| Saudi Electronic University | `lms.seu.edu.sa` | SEU IT page links to it |
| KFUPM | `blackboard.kfupm.edu.sa` | KFUPM e-services page redirects to it |
| Imam Mohammad Ibn Saud Islamic University | `lms.imamu.edu.sa` | University Blackboard policy documents |
| Umm Al-Qura University | `lms.uqu.edu.sa` | Blackboard replaced D2L in 2020; its page links to an SSO path |
| King Abdulaziz University | `lms.kau.edu.sa` | KAU page on the move to Blackboard Ultra |
| Qassim University | `lms.qu.edu.sa` | Qassim news pages (Blackboard since 2016) |
| King Khalid University | `lms.kku.edu.sa` | KKU e-services lists Blackboard |
| Taif University | `lms.tu.edu.sa` | Anthology case study |
| Northern Border University | `lms.nbu.edu.sa` | NBU service catalog lists Blackboard |
| Prince Sattam bin Abdulaziz University | `lms.psau.edu.sa` | University page on adopting Blackboard Ultra (2026) |
| King Faisal University | `lms.kfu.edu.sa` | KFU college page on its learning management system |
| Taibah University | `lms.taibahu.edu.sa` | Host answers; I found no page naming Blackboard |
| University of Jeddah | `lms.ju.edu.sa` | Login guide is hosted on `ju.edu.sa` |
| Jazan University | `lms.jazanu.edu.sa` | Older training deck; confirm it is the current host |

Two cautions on this table:

- Answering proves a Blackboard instance exists at that host. The link to the university comes from the host being under the university's own domain, so each row should still be confirmed before it ships.
- A search summary labelled `lms.ju.edu.sa` as Jazan University's address. The guide it came from sits on `ju.edu.sa`, which is the University of Jeddah's domain, so I filed it under Jeddah. Please check both.

**Did not answer:** `lms.pnu.edu.sa` (Princess Nourah University), `lms.iau.edu.sa` (Imam Abdulrahman Bin Faisal University) and `elearning.kau.edu.sa`. Both PNU and IAU are documented Blackboard users. Their server may use another name, or it may only answer inside Saudi Arabia. This is not evidence that they do not use Blackboard.

**Documented as Blackboard users, host not tested:** Batterjee Medical College. Other Saudi names may exist; the list is not complete.

**4. The owner's list has names only.**
The pasted list holds 84 institutions in Europe, North America, South America, Mexico, Asia, Australia, New Zealand and Africa. It gives no hostnames, and it contains only one Saudi university (Princess Nourah). Other regions use different naming, so the Saudi `lms.` pattern cannot be assumed there.

**5. Blackboard's own mobile app uses a central registry.**
Each school registers a search name in a Mobile Web Services building block, and the app looks schools up there ([Blackboard documentation](https://help.blackboard.com/Learn/Administrator/Hosting/Release_Notes/Release_Notes_for_Building_Blocks/Release_Notes_for_Mobile_Web_Services/Configure_and_Register_Blackboard_Mobile_Web_Services)). The documentation does not describe a public interface for it, and a school must opt in. I did not look for it further.

### Proposals

**A. A built-in list of verified schools, with search (recommended).**
Ship a data file with the school name (English, Arabic, Turkish), country, domain, address and the date it was last verified. Settings and the start screen get a search box. The student picks a school and the address is filled in. Keep the current free-text field for schools not on the list.
- A script in `scripts/` builds the list: for each school it probes candidate hosts with the version check above, and the owner reviews the result before it is committed.
- A scheduled CI job re-checks the list and reports hosts that stop answering.
- The list works offline and sends nothing to a server while the student searches.
- Cost: someone has to maintain it.

**B. Find the address from a domain the student types (fallback).**
The student types the university's web domain or a short name (for example `ksu.edu.sa`). The app tries a short list of host names (`lms.`, `blackboard.`, `bb.`, `learn.`, `elearning.`) on that domain, checks each with the version call, and offers the one that answers. It covers schools missing from the list. Only host names are contacted, and only the school's own servers.

**C. Use Blackboard's mobile-app registry. Not recommended.**
It has no public documentation, schools opt in, and it can change without notice.

**D. A "my school is missing" path that grows the list.**
After a successful sign-in with an address that is not in the list, the app offers to open a prefilled report with the host only. It sends nothing on its own, so the project's no-analytics promise holds. The reports feed approach A.

**E. Bulk discovery for the worldwide list.**
Offline, at list build time: find candidate hostnames from public certificate transparency logs for each university domain, then probe them with the version check. A person reviews the result. This is how the first worldwide list can reach many schools quickly.

### Recommendation

Start with **A**, built from the Saudi table above plus the owner's list, and verify every row before it ships. Add **B** next, because it removes the dependence on the list. Add **D** so the list grows by itself. Use **E** only for the bulk first pass.

### Risks and open points

- **Arabic interface.** The app offers English and Turkish only. Many Saudi students may need Arabic text and right-to-left layout in the school search and in Settings. This is a separate, larger task.
- **Term names.** [src/blackboard_sync/sync.py](../src/blackboard_sync/sync.py) has Turkish season rules for folder names (`TURKISH_SEASONS`, `ACADEMIC_TERM`). Saudi terms may use Arabic names or Hijri years, which can change folder names and which term counts as current. Test with a real account before announcing Saudi support.
- **Single sign-on.** Saudi universities may use their own identity provider. The sign-in window handles school single sign-on, but a real Saudi account has not been tried.
- **Hosts change.** Jazan has two possible hosts and KAU lists another one. Keep the verification date in the data and re-check it on a schedule.
- **Privacy text.** The version check contacts the school's own server from the student's computer, with no sign-in. If A or B ships, the privacy page should say so.
- **No guessed addresses.** Only addresses that answered the check and were confirmed by a person go into the list.

### Out of scope

- No sign-in or sync changes for non-Blackboard systems (Moodle, Canvas and others).
- No scraping of university web pages by the app itself.
