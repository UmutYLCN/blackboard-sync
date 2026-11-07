# Roadmap

The agreed product direction for Blackboard Sync. Work follows the sequence below, one step at a time. Detailed bug notes stay in [TODO.md](TODO.md) and [PLANNED_WORK_INVESTIGATIONS.md](PLANNED_WORK_INVESTIGATIONS.md).

Status key: `Todo` · `In progress` · `Done` · `Blocked`

---

## Sequence

| Step | Work | Status |
|------|------|--------|
| 1 | Publish version 1.7.0 on the Microsoft Store | Todo |
| 2 | Mac work: school list, past-terms removal, file-move fixes | Todo |
| 3 | Port the Mac work to Windows | Todo |
| 4 | Microsoft Store release of the ported version | Todo |
| 5 | Correct the website | Todo |

1. **Store publication of 1.7.0.** Version 1.7.0 is not yet officially published on the Microsoft Store. This comes before everything else. See the [Pre-Store checklist](#pre-store-checklist) and the [Store listings](#microsoft-store-listings) section. Packaging steps are in [MSIX.md](MSIX.md).
2. **Mac work.** All changes below are made on the Mac app first:
   - [School list with link fallback](#school-list-with-link-fallback)
   - [Removal of the past-terms feature](#removal-of-the-past-terms-feature)
   - [File-move fixes](#file-move-fixes)
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

## Removal of the past-terms feature

The past-terms feature is removed from every app. Its desktop controls already show **Coming soon** ([USAGE.md](USAGE.md#downloading-a-past-term)); this step removes the feature itself.

## File-move fixes

The known file-move problems already noted in [TODO.md](TODO.md) get fixed. The investigation notes are in [PLANNED_WORK_INVESTIGATIONS.md](PLANNED_WORK_INVESTIGATIONS.md).

## Microsoft Store listings

- Store listings are created in both **English** and **Turkish**.
- Both listings include the **NotebookLM** feature.

## Pre-Store checklist

> **To be supplied by the product owner.** Items will be added here before the Store publication of 1.7.0.

- _(placeholder: checklist items pending)_

## Risks of other schools' data

Syncing other schools' data may break where the app's assumptions differ from how another school sets up Blackboard. Track these as the school list grows.

- **Term titles.** Courses are fetched under a term title such as `2026-2027`. Another school may name its terms differently, so courses may not be found or may be sorted under the wrong term.
