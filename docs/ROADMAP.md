# Roadmap

The agreed product direction for Blackboard Sync. Work follows the sequence below, one step at a time. Detailed bug notes stay in [TODO.md](TODO.md) and [PLANNED_WORK_INVESTIGATIONS.md](PLANNED_WORK_INVESTIGATIONS.md).

Status key: `Todo` · `In progress` · `Done` · `Blocked`

---

## Sequence

| Step | Work | Status |
|------|------|--------|
| 1 | Publish version 1.7.0 on the Microsoft Store | Todo |
| 2 | Mac work: school list, latest-term rule, past-terms removal, file-move fixes, no empty course folders, UI cleanup | Todo |
| 3 | Port the Mac work to Windows | Todo |
| 4 | Microsoft Store release of the ported version | Todo |
| 5 | Correct the website | Todo |

1. **Store publication of 1.7.0.** Version 1.7.0 is not yet officially published on the Microsoft Store. This comes before everything else. See the [Pre-Store checklist](#pre-store-checklist) and the [Store listings](#microsoft-store-listings) section. Packaging steps are in [MSIX.md](MSIX.md).
2. **Mac work.** All changes below are made on the Mac app first:
   - [School list with link fallback](#school-list-with-link-fallback)
   - [Simple latest-term rule](#simple-latest-term-rule) ✓ Done (desktop and iPad apps)
   - [Removal of the past-terms feature](#removal-of-the-past-terms-feature)
   - [File-move fixes](#file-move-fixes)
   - [No folders for courses without files](#no-folders-for-courses-without-files)
   - [UI cleanup](#ui-cleanup)
3. **Windows port.** The finished Mac work is ported to Windows.
4. **Microsoft Store release.** The ported Windows version is released on the Microsoft Store last. After this release, no new version is planned for a long time.
5. **Website correction.** The website is corrected only after all of the steps above are finished.

## Release 1.7.1

Version 1.7.1 gathers the Mac work that is ready, is tested by hand at the end against the first school (İSTÜN), and must not disturb existing users' term and course folders.

In 1.7.1:

- Everything merged since 1.7.0: the [file-move fixes](#file-move-fixes), [no folders for courses without files](#no-folders-for-courses-without-files) and the [removal of the past-terms feature](#removal-of-the-past-terms-feature).
- The [simple latest-term rule](#simple-latest-term-rule), on the desktop and iPad apps.
- Provider-independent silent sign-in with page stillness, fast-path checks (username/email, account picker, OTP) and session cookie fallback.
- The [UI cleanup](#ui-cleanup): the profile card and the calendar error card.
- The English and Turkish [Store listings](#microsoft-store-listings) with NotebookLM.
- School list growth: the known-schools list grew from 16 to about 143 schools, including 5 more Turkish schools, all checked on 2026-11-08.
- The version bump to 1.7.1 with release notes.
- The [Pre-Store checklist](#pre-store-checklist).

Waiting for 1.7.2:

- The Arabic PDF font ([Arabic text in PDF notes](#risks-of-other-schools-data)).
- The medium and low priority [risks of other schools' data](#risks-of-other-schools-data).

## Platform scope

- **iPad:** Gets bug fixes and parity fixes, so it behaves like the desktop apps; no NotebookLM and no other large features.
- **Windows and Mac:** NotebookLM is a major feature of these two versions only.

## No new big features

Apart from NotebookLM, no more big features are planned. From now on, only small fixes are made.

## School list with link fallback

- Schools that use Blackboard are identified and offered as a choice list.
- The link entry stays. A user whose school is not in the list can still sign in by entering the Blackboard address.

## Simple latest-term rule

Download the current term the way a student means "this term", and keep the school's own term names. The term-name merging that turns English season names such as `Fall` into Turkish `Güz` was added on 13 October 2026 (PR #98) as a side effect of the past-terms download work, to avoid an empty duplicate English folder at the first school (whose Blackboard returns one semester as a Turkish and an English term record).

1. Download the term that started most recently, plus every term that is running now: a year-long term beside a semester, a full term beside an 8-week block, sections that start on different days. Term records that share a start date (for example, a Turkish and an English copy of the same semester) count as one group. Ended terms and terms far in the future are not downloaded. Once the latest term has ended, the next one takes over a month before it starts.
2. A term with no dates counts from its newest course's creation date, but it never pushes out a dated term that is running. It is downloaded beside the running term when its courses were made for it: created once that term opened, and not named for another year or season (so a next-term shell or an old summer term that got a new course stays out). When no term has dates, the undated terms whose newest courses were created close together (within 45 days) are downloaded together.
3. Download every course in those terms, each course once.
4. Keep the school's own term names as written, with no renaming such as `Fall` to `Güz` and no Turkish-first naming. The Turkish/English merge stays only for the case where the same semester truly appears under two names; full official names (`2026-2027 Eğitim-Öğretim Yılı Güz Dönemi`) and Arabic, ordinal and Hijri names (`الفصل الدراسي الأول 1448`, `1448 First Semester`) are recognised too.
5. If no course is found, do not stay silent: tell the user the current term could not be determined and let them choose courses.

Safeguards:

- Courses with no term at all (`termId` empty) are included.
- Closed courses and enrolments, courses that open with a closed term, and Blackboard Organizations (clubs and communities listed among the courses) are skipped.
- A term whose dates ended before any of its courses was created has dates copied from an earlier year; it is dated by its courses instead.
- A term an older version archived stays frozen and can never be picked, so it cannot leave the student with no course at all.
- A term holding the merged (cross-listed) parent of a current course is downloaded too, since the files are there.
- When nothing can be dated, the term whose name gives the latest academic year and season is downloaded instead of every past term.
- `state.json` records the school; after a change of school, the other school's course folders are not reused. A state file from before this belongs to the school in use, so existing users keep their term and course folders and nothing is downloaded again or moved.

Before the first download at a new school whose term is not clear, the desktop apps ask first:

- When no state exists for the school and the term choice is ambiguous (undated terms, stale dates, terms that started on different days, or a term name with no year and season), a card lists the term(s) found and their courses, all ticked. The student can untick courses and presses Confirm; nothing is downloaded before that, and the choice is saved so it is asked once. Not now leaves nothing downloaded and the card comes back with the next sync.
- A clear first run downloads at once as before. A school with existing state (the first school, İSTÜN, with its files) never sees the card.
- Done on the desktop apps (Mac and Windows). The iPad app gets its own card in a later step.

Notes:

- The rule was checked against 28 synthetic school setups (`tests/test_term_scenarios.py`); at the first school it gives exactly the result it gave before.
- The real term and course data from the first school must be checked once to confirm which fields can be trusted. The real data check is part of the 1.7.1 test by hand at the first school.
- Done on the desktop apps (Mac and Windows share the code) and the iPad app, which runs the same 28 setups with the same results (an iPad course keeps the folder its files are already in).

## Removal of the past-terms feature

The past-terms feature has been removed from every app: the desktop controls, the terminal options and the iPad row are gone. Syncing the current term works as before. Terms an older version downloaded keep their files and stay as they are.

## File-move fixes

The known file-move problems already noted in [TODO.md](TODO.md) get fixed. The investigation notes are in [PLANNED_WORK_INVESTIGATIONS.md](PLANNED_WORK_INVESTIGATIONS.md).

## No folders for courses without files

- A course folder and its subfolders are created only when the first file (including a generated note PDF) is written for that course, so a course with no files leaves no empty folder; if files arrive later, the folder is created then.
- Existing empty folders are not touched or deleted.
- This touches the same code area as the [file-move fixes](#file-move-fixes) (folders are created up front in the sync, around `sync_course`), so plan the two together.

## UI cleanup

- The round profile avatar (initials) at the top right of the window no longer opens a dropdown card (`Signed in as <name>`, **Sign out**, **Settings**) on the Mac and Windows apps, because a Settings gear button already sits next to it. The avatar is now only a badge; **Sign out** is in **Settings → Account**.
- **Calendar connect cancel or timeout no longer leaves an error card.** When the user starts Google Calendar connect and then cancels or lets it time out, the Settings card shows a short-lived notice for a few seconds, nothing is stored, and the card returns to **Not connected** with the **Connect** button. A leftover error stored by an older version is ignored. Real errors while connected (failed calendar sync, access revoked by Google, needs reconnect) keep the error card.
- The visual design of the Settings page is improved.

Nothing else changes in the UI.

## Microsoft Store listings

- Store listings are created in both **English** and **Turkish**.
- Both listings include the **NotebookLM** feature.

## Pre-Store checklist

> **To be supplied by the product owner.** Items will be added here before the Store publication of 1.7.0.

- _(placeholder: checklist items pending)_

## Risks of other schools' data

Syncing other schools' data may break where the app's assumptions differ from how another school sets up Blackboard. Track these as the school list grows.

- **Undated terms and term titles.** Some schools leave terms without dates and only name them (such as `2026-2027` or `Fall 2026`), or name them differently from the expected format. The current-term choice in `sync.py` and its iPad twin can then pick the wrong term, sort courses under the wrong term, or drop active ones.
  Fixed on the desktop and iPad apps by the [Simple latest-term rule](#simple-latest-term-rule).
- **Courses without a term.** Courses with no term (`termId` null) are silently skipped, so the user sees zero courses and no error.
  Fixed on the desktop and iPad apps by the [Simple latest-term rule](#simple-latest-term-rule).
- **Arabic text in PDF notes.** Arabic text in generated PDF notes shows as replacement characters because the bundled fonts cover only Latin, Turkish and Greek and shaping tables were stripped. This matters for the Saudi universities in the school list.
- **Term-name aliases.** Term-name aliases rewrite English term names to Turkish (`Güz`, `Bahar`, `Yaz`) and miss other formats.
  Fixed on the desktop and iPad apps by the [Simple latest-term rule](#simple-latest-term-rule).
- **Unscoped desktop state files.** Desktop `state.json` and `courses.json` are not scoped by school or account, so switching schools can collide on Blackboard internal IDs; the iPad app already scopes them.
  Course folders recorded in `state.json` are no longer reused across schools ([Simple latest-term rule](#simple-latest-term-rule)); the rest of `state.json` and `courses.json` are still unscoped.
- **Course-code pattern.** The course-code pattern misses hyphenated codes like `CS-101` and can read a term prefix such as `FALL2026` as the course code.
- **Windows path-length limit.** On Windows, term and course folder names are not shortened to fit the 259-character path limit (only subfolders are), which matters in OneDrive folders.
- **English-only attachment check.** The check for items that do not support attachments looks for one English sentence, so a localized Blackboard server makes every such item fail and retry.
- **Classic (non-Ultra) Blackboard.** Embedded file links without `xid-` or `rid-` markers are ignored and web links hardcode `/ultra/`.

Lower-severity findings (sign-in methods, school directory gaps, iPad rate limits, language coverage) are kept in the private research notes and are not listed here.
