# Planned Work

Items in this list must be investigated before implementation. An investigation should record the reproduction, evidence, likely cause, and scope before a separate implementation task begins.

## Destination change can leave downloaded files behind

- **Status:** Investigation needed
- **Reported behavior:** In Settings, after changing the save location and choosing **Taşı**, the folder structure appears at the new location, but nested downloaded files such as PDFs and PowerPoint presentations do not all arrive. This is a user report and has not yet been reproduced in this task.
- **Expected behavior:** Move every Blackboard Sync managed file into the matching relative path under the new `University` folder. Once relocation succeeds, no moved files should remain under the old `University` location, and its now-empty folders should be removed. Preserve user-owned files, avoid overwriting destination files, and report files that cannot be moved; do not remove an old file before its move is verified.
- **Investigate first:** Reproduce the same settings flow with nested course folders and several file types; compare the old and new trees; capture any warnings; and trace where files are skipped or left behind. Check conflicts, open files, permissions, path handling, and differences between macOS and Windows. Compare findings with the documented **Taşı** behavior in `DEVELOPMENT.md`.
- **Implementation follow-up:** After reviewing the investigation, open a separate task for the confirmed fix and regression coverage. Verify that successful moves preserve relative paths and file contents, that a repeated move does not duplicate or lose files, and that the old `University` tree is removed only after all managed files have moved successfully. On partial failure, keep unresolved files safe and report them.
