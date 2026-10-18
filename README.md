<p align="center"><img src="assets/banner.png" alt="Blackboard Sync" width="100%"></p>

Downloads your Blackboard course content to your computer automatically.

## Features

- **Automatic downloads:** Checks Blackboard every hour in the background, downloads new files by itself and sends you a notification.
- **Tidy folders:** Files are saved in a **University** folder with Blackboard's own term and course structure.
- **Calendar:** See the due dates of assignments, exams and other graded work day by day, with the course name.
- **Announcements:** Every synced announcement from your current-term courses in one place, newest first; open the saved notes from there.
- **Courses:** Untick a course you don't want and it is no longer synced. The folder is a copy of Blackboard; deleted or damaged files come back by themselves.
- **Past terms:** Download the files of an earlier term in one go.
- **Pause:** Stop syncing whenever you like and resume with one click.
- **One-click updates:** When a new version is out you get a notification; just press **Update**.
- **English or Turkish:** Pick the app's language in Settings (English / Türkçe).
- **Easy uninstall:** Remove the app and its data with one button in Settings.

## Installation

[Download the latest version](https://github.com/UmutYLCN/blackboard-sync/releases/latest):

- **macOS:** Open the `.dmg` and drag the app into the **Applications** folder.
- **Windows:** Run `Setup.exe`. If SmartScreen warns you, choose **More info → Run anyway**.

Or with a single command in the terminal:

```sh
# macOS
curl -fsSL https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.ps1 | iex
```

On first launch choose your school's address and the folder to save files in, then **Sign in**. See the [user guide](docs/USAGE.md) for details and terminal commands.

## Privacy

You type your password only into your school's own sign-in page; the app never sees it and never stores it. The sign-in session is kept only on your own computer and is never sent to any server.

🌐 **Website:** [blackboard-sync.umutyalcin.workers.dev](https://blackboard-sync.umutyalcin.workers.dev)

![Visitors](https://visitor-badge.laobi.icu/badge?page_id=UmutYLCN.blackboard-sync&left_text=visitors)

---

License: [MIT](LICENSE).

Blackboard Sync is an independent project; it is not affiliated with or endorsed by Anthology Inc.
