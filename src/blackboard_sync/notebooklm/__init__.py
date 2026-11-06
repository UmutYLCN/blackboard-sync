"""Adding the synced course files to NotebookLM: one notebook per course, one source per file.

Google offers no consumer API for NotebookLM, so this goes through the unofficial
``notebooklm-py`` library, which may stop working whenever Google changes NotebookLM. A run only
adds. Only ``duplicates.remove``, which the student confirms, ever deletes anything in NotebookLM.

The package is free of GUI code so the other platforms can reuse it, and of the library too,
except ``gateway``: the one module that talks to Google, loaded only when a run starts.

- ``store``: where it all lives, what was added so far and how the last run went.
- ``planner``: which files of which course to add, without any network.
- ``runner``: one run, from the plan to the uploads, with its limits and retries.
- ``duplicates``: listing sources that are there twice, and removing confirmed extra copies.
- ``signin``: the one-time Google sign-in in the student's own browser.
- ``gateway``: the library, behind a small surface a browser-driven fallback could replace.

The apps run it as the ``blackboard-sync notebooklm`` child process, beside the Blackboard
sync and never in its way. The rules come from the ``dersler-notebooklm`` command line tool.
"""
