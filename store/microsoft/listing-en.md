# Store listing: English (en-US)

An additional listing. The package declares only `tr-TR`, so add English under
**Add/remove languages > Manage additional languages** (Microsoft allows listings in
languages the package does not support). The app's interface is Turkish only, and the
description says so. Limits as in `listing-tr.md`; the character counts below were measured.

## Product name

`blackboard-sync`. For a language without a package, Partner Center asks you to pick one
of the reserved names; pick this one.

## Short description

Limit 1,000; only the first 270 are shown in some views. 163 characters.

```text
Downloads the course files, announcements and notes from your school's Blackboard to your PC in the background, organised by term and course. Free and open source.
```

## Description

Limit 10,000, plain text, no URLs. 2,441 characters.

```text
Downloads your Blackboard course content to your computer automatically, so you no longer have to open the site and download files one by one.

blackboard-sync is an independent project, not affiliated with Anthology Inc. or Blackboard. “Blackboard” is a trademark of its owner, not of this app.

HOW IT WORKS
1. Enter your school's Blackboard address and choose the folder for your files.
2. Sign in on your school's own sign-in page. The first sync starts right after.
3. Your files stay up to date: by default the app checks Blackboard every hour.

WHAT IT DOWNLOADS
• The files in your courses and the attachments in assignment instructions.
• Announcements, links and pages, as readable Markdown notes.
• Files and notes that change on Blackboard are updated too, and a Windows notification tells you when something new arrives.

ORGANISED FOLDERS
Files are saved in a University folder inside the folder you choose, by term and course as on Blackboard. The default is Documents\University. If you change the folder later, you can move the downloaded files, download them again, or only get new files.

OVERVIEW
The main window lists your latest downloads; open any of them with a click. "Sync now" checks right away and "Open folder" takes you to the University folder. Closing the window keeps the app running from its icon next to the clock.

DELETED FILES
Pick files you downloaded and later removed from the folder, and download them again. Files you dismiss are not suggested again.

PAST TERMS
Past-term desktop downloads are being redesigned. The section currently shows Coming soon; existing downloaded files are kept.

SETTINGS
• Automatic sync: every 30 minutes, every hour, every 3 hours, or manual only.
• Start when the computer starts: the app starts in the background without opening its window. You can also turn this off in Task Manager under Startup apps.
• Updates are installed through the Microsoft Store.

PRIVACY
• You type your password only on your school's own sign-in page; the app never sees or stores it.
• Your sign-in session, settings and download records stay on your computer.
• The app connects to Blackboard and its sign-in/file redirects, plus Google only if you enable optional Calendar sync.
• No analytics, ads or usage tracking, and no account to create.

REQUIREMENTS
• A Blackboard Learn account at your school.
• The app's interface is in Turkish.

Free and open source (MIT License).
```

## What's new in this version

Limit 1,500. Leave it empty for the first submission (Microsoft's guidance); for later
updates, for example:

```text
First Microsoft Store release. Updates now come through the Microsoft Store, and you can remove the app from Windows Settings > Apps.
```

## Product features

Up to 20, 200 characters each, no bullets.

```text
Downloads new course files in the background
Also downloads attachments in assignment instructions
Saves announcements, links and pages as Markdown notes
A tidy University folder, by term and course
A Windows notification when new files arrive
Automatic sync every 30 minutes, every hour, every 3 hours, or manual only
Deleted: pick files you removed and download them again
Past-term downloads: coming soon
Can start in the background when the computer starts
Never sees your password; your session stays on your computer
No analytics, ads or usage tracking
Free and open source
```

## Screenshot captions

200 characters each, one per screenshot, in this order. The same text lives in
`screenshots/src/shots.js`. Use the same Turkish-titled images for both listings.

| Image | Caption |
| --- | --- |
| `01-tek-tek.png` | Still downloading Blackboard files one by one? Blackboard Sync automatically downloads your course files to your computer in the background. |
| `02-genel-bakis.png` | Home: new course files download in the background. Recent downloads, announcements and upcoming due dates at a glance. |
| `03-teslim-tarihleri.png` | Calendar: upcoming due dates, day by day. A notification comes 24 hours and 1 hour before each one is due. |
| `04-google-takvim.png` | Connect Google Calendar in Settings: due dates stay up to date in a separate Blackboard Deadlines calendar. Your other calendars stay private. |
| `05-duyurular.png` | Announcements: every course’s Blackboard announcements in one list, newest first. Open any of them in one click. |
| `06-dersler.png` | Courses: see this term’s courses and untick the ones you don’t want. Unticked courses are not synced; downloaded files are not deleted. |
| `07-koyu-tema.png` | Dark theme: the app follows your Windows theme, or stays light or dark from Settings. |
| `08-baslangic.png` | Getting started: enter your school's Blackboard address, choose a save folder and whether to start with your computer, then sign in. |
| `09-tepsi-menusu.png` | The app keeps working from the system tray after you close its window. Check the last sync, sync again, or access your courses and recent downloads. |

## Trailer title

```text
blackboard-sync: your Blackboard course files, on your PC automatically
```

## Search terms (Keywords)

Up to 7 terms, 40 characters each, at most 21 unique words in all. 7 terms, 8 unique words.

```text
Blackboard
Blackboard Learn
course files
university
download
sync
student
```

## Copyright and trademark info

Limit 200. 184 characters.

```text
© 2026 Umut Yalçın. MIT License. blackboard-sync is an independent project, not affiliated with Anthology Inc. or Blackboard. “Blackboard” is a trademark of its owner, not of this app.
```

## Additional license terms

Leave empty (see `listing-tr.md`).

## Developed by

```text
Umut Yalçın
```

## Optional Google Calendar privacy

CLI connection enables automatic deadline updates to a dedicated Blackboard Deadlines calendar. Google receives event titles, course names, due times and Blackboard links. Tokens are stored in Windows Credential Manager; mapping and status stay in the private app data folder. Run `calendar disconnect` to revoke access and clear local Calendar data, optionally with `--delete-calendar` (keeping the calendar retains only its non-secret ID for reconnection), or revoke at https://myaccount.google.com/connections. Windows connection controls are not yet available in the GUI. Google API use follows the Google API Services User Data Policy, including Limited Use.
