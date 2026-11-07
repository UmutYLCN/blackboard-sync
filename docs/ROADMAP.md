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
   - [Simple latest-term rule](#simple-latest-term-rule)
   - [Removal of the past-terms feature](#removal-of-the-past-terms-feature)
   - [File-move fixes](#file-move-fixes)
   - [No folders for courses without files](#no-folders-for-courses-without-files)
   - [UI cleanup](#ui-cleanup)
3. **Windows port.** The finished Mac work is ported to Windows.
4. **Microsoft Store release.** The ported Windows version is released on the Microsoft Store last. After this release, no new version is planned for a long time.
5. **Website correction.** The website is corrected only after all of the steps above are finished.

## Platform scope

- **iPad:** No NotebookLM and no extra development.
- **Windows and Mac:** NotebookLM is a major feature of these two versions only.

## No new big features

Apart from NotebookLM, no more big features are planned. From now on, only small fixes are made.

## School list with link fallback

- Schools that use Blackboard are identified and offered as a choice list.
- The link entry stays. A user whose school is not in the list can still sign in by entering the Blackboard address.

## Simple latest-term rule

Download the latest term the way the top group appears on Blackboard, and keep the school's own term names. The term-name merging that turns English season names such as `Fall` into Turkish `Güz` was added on 13 October 2026 (PR #98) as a side effect of the past-terms download work, to avoid an empty duplicate English folder at the first school (whose Blackboard returns one semester as a Turkish and an English term record).

1. Pick the term that started most recently. Term records that share that start date (for example, a Turkish and an English copy of the same semester) count as one group. When a term has no start date, use the newest course creation date instead.
2. Download every course in that group, each course once.
3. Keep the school's own term names as written, with no renaming such as `Fall` to `Güz` and no Turkish-first naming. The Turkish/English merge stays only for the case where the same semester truly appears under two names.
4. If no course is found, do not stay silent: tell the user the current term could not be determined and let them choose courses.

Notes:

- Courses with no term at all (`termId` empty) are included.
- A student in both a year-long and a semester term gets both, because all terms sharing the latest start date are one group.
- The real term and course data from the first school must be checked once to confirm which fields can be trusted before coding.

## Removal of the past-terms feature

The past-terms feature has been removed from every app: the desktop controls, the terminal options and the iPad row are gone. Syncing the current term works as before. Terms an older version downloaded keep their files and stay as they are.

## File-move fixes

The known file-move problems already noted in [TODO.md](TODO.md) get fixed. The investigation notes are in [PLANNED_WORK_INVESTIGATIONS.md](PLANNED_WORK_INVESTIGATIONS.md).

## No folders for courses without files

- A course folder and its subfolders are created only when the first file (including a generated note PDF) is written for that course, so a course with no files leaves no empty folder; if files arrive later, the folder is created then.
- Existing empty folders are not touched or deleted.
- This touches the same code area as the [file-move fixes](#file-move-fixes) (folders are created up front in the sync, around `sync_course`), so plan the two together.

## UI cleanup

- On the Mac app, clicking the round profile avatar (initials) at the top right of the window opens a small dropdown card showing `Signed in as <name>`, **Sign out** and **Settings**. That card is removed, because a Settings gear button already sits next to the avatar.
- **Calendar connect cancel or timeout no longer leaves an error card.** When the user starts Google Calendar connect and then cancels or lets it time out, the Settings card currently keeps showing `Google Calendar error - authorization timed out` permanently (the error is stored as `last_error` and survives restarts). Planned: show a short-lived notice instead, do not store the error, and return the card to **Not connected** with the **Connect** button; real errors while connected (failed calendar sync, access revoked by Google) keep the error card.
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
  Planned fix: see [Simple latest-term rule](#simple-latest-term-rule).
- **Courses without a term.** Courses with no term (`termId` null) are silently skipped, so the user sees zero courses and no error.
  Planned fix: see [Simple latest-term rule](#simple-latest-term-rule).
- **Arabic text in PDF notes.** Arabic text in generated PDF notes shows as replacement characters because the bundled fonts cover only Latin, Turkish and Greek and shaping tables were stripped. This matters for the Saudi universities in the school list.
- **Term-name aliases.** Term-name aliases rewrite English term names to Turkish (`Güz`, `Bahar`, `Yaz`) and miss other formats.
  Planned fix: see [Simple latest-term rule](#simple-latest-term-rule).
- **Unscoped desktop state files.** Desktop `state.json` and `courses.json` are not scoped by school or account, so switching schools can collide on Blackboard internal IDs; the iPad app already scopes them.
- **Course-code pattern.** The course-code pattern misses hyphenated codes like `CS-101` and can read a term prefix such as `FALL2026` as the course code.
- **Windows path-length limit.** On Windows, term and course folder names are not shortened to fit the 259-character path limit (only subfolders are), which matters in OneDrive folders.
- **English-only attachment check.** The check for items that do not support attachments looks for one English sentence, so a localized Blackboard server makes every such item fail and retry.
- **Classic (non-Ultra) Blackboard.** Embedded file links without `xid-` or `rid-` markers are ignored and web links hardcode `/ultra/`.

Lower-severity findings (sign-in methods, school directory gaps, iPad rate limits, language coverage) are kept in the private research notes and are not listed here.
