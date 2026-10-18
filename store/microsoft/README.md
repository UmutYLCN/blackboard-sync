# Microsoft Store submission

Everything for the first Microsoft Store submission of the Windows app: a checklist that
follows Partner Center's submission sections, the listing text, Store images and the
trailer. The maintainer tests the package on a real Windows PC and submits it in Partner
Center; nothing here submits anything.

**Deadline:** send the submission before early January 2027, or the reservation of the
name `blackboard-sync` lapses.

The package identity is already in the repository (`packaging/msix/identity.toml`,
`docs/MSIX.md`): `UmutYLCN.blackboard-sync`, publisher display name `UmutYLCN`, reserved
Store name `blackboard-sync` ("Blackboard Sync" is taken by another app). The Start menu
still shows **Blackboard Sync**.

## Contents

| Path | What it is |
| --- | --- |
| `listing-tr.md` | Turkish Store listing (primary market), ready to paste |
| `listing-en.md` | English Store listing (additional language), ready to paste |
| `screenshots/01-tek-tek.png` … `09-tepsi-menusu.png` | Final 1920x1080 images: problem card, then eight Windows screenshots, in upload order (see [Screenshots](#screenshots)) |
| `screenshots/capture.py` | Captures the Windows app's own page (light and dark) and the tray menu into `screenshots/src/windows/` |
| `screenshots/render.sh` | Renders the screenshots from `screenshots/src/` |
| `screenshots/src/` | `template.html`, `shots.js` (titles, captions, what to capture), `windows/` (the eight Windows captures as PNG, from `capture.py`) |
| `trailer/make-trailer.sh` | Builds the 1920x1080 trailer and its thumbnail into `out/` |
| `trailer/draft-trailer-thumbnail.png` | The thumbnail it makes, for review |
| `images/hero-art.png` | 16:9 Super hero art, 1920x1080 (no text, no UI) |
| `images/poster-art.png` | Poster art, 1440x2160 (logo and app name) |
| `images/box-art.png` | 1:1 box art, 2160x2160 (logo and app name) |
| `images/store-logo-{300,150,71}.png` | 1:1 app tile icons, 300x300, 150x150 and 71x71 |
| `images/make-images.sh` | Renders the artwork and scales the tile icons |
| `shot.sh` | Headless Chrome screenshot helper used by the scripts |
| `out/` | Generated videos and downloads; ignored by git |

The scripts run on macOS with Google Chrome (`CHROME=/path/to/chrome` to use another
Chrome), Node.js for the screenshot manifest, and `ffmpeg` for the trailer.

## Before you start

1. Download the package from CI (see [4. Packages](#4-packages)).
2. Do the manual test in `docs/MSIX.md` ("Manual Windows verification still required")
   with that exact `.msix`, signed with the test certificate as described there.
3. Use the nine final Store images in [Screenshots](#screenshots). Capture additional
   screens during future manual tests to improve the listing.

## Partner Center checklist

Microsoft's reference: [Create an app submission for your MSIX app](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/create-app-submission).
Items marked **Decide** are the maintainer's call; all are collected again under
[Open decisions](#open-decisions).

### 1. Pricing and availability

- [ ] **Markets:** **Decide.** All markets (the default) or Turkey only. The app works with
  any school's Blackboard Learn; its interface is English by default, with Turkish in Settings.
- [ ] **Audience:** Public audience.
- [ ] **Discoverability:** Make this product available and discoverable in the Microsoft Store.
- [ ] **Schedule:** Release as soon as possible; Stop acquisition never. (Use
  [6. Submission options](#6-submission-options) to hold the release instead.)
- [ ] **Base price:** Free. No free trial, no sale pricing.
- [ ] **Organizational licensing:** leave the defaults.

### 2. Properties

- [ ] **Category:** Education, subcategory **Study aids**. **Decide** on an optional
  secondary category: Productivity ("apps which help user to complete a particular task
  more efficiently") is the closest; Utilities + tools also fits.
- [ ] **Privacy:** "Does this product access, collect or transmit personal information?"
  **Yes.** The app stores the Blackboard session cookies, user ID, user name and display
  name on the PC and sends the cookies to the school's Blackboard server.
- [ ] **Privacy policy URL:** `https://blackboardsyncapp.com/privacy`.
  The page is in English and says which statements apply to the macOS, Windows Setup and
  Microsoft Store builds. Its "Microsoft Store build" section covers the package's data
  folder (`%LOCALAPPDATA%\Packages\<family name>\LocalCache\Roaming\blackboard-sync`),
  the startup task (instead of the `HKCU\…\Run` value), no GitHub contact or self-update,
  removal through Windows Settings > Apps, and separate data from the Setup build. The old
  `/gizlilik` address redirects to it.
- [ ] **Website:** `https://blackboardsyncapp.com/`.
- [ ] **Support contact info:** **Decide.** `https://github.com/UmutYLCN/blackboard-sync/issues`
  (what the privacy page names) or an email address. Required only for Xbox.
- [ ] **Contact details:** required only for company accounts.
- [ ] **Display mode:** leave all unchecked.
- [ ] **Product declarations:**
  - "Allows users to make purchases, but does not use the Microsoft Store commerce system": unchecked (no purchases).
  - "Tested to meet accessibility guidelines": unchecked (not tested to that standard).
  - "Can install to alternate drives or removable storage": leave checked (default).
  - "Windows can include this product's data in automatic backups to OneDrive": default
    checked. **Decide:** the app data holds the Blackboard session; unchecking keeps it out
    of backups.
  - Pen and ink, generative AI: unchecked.
- [ ] **System requirements:** leave empty. The package already requires Windows 10
  version 1809 (10.0.17763) or later, x64.

### 3. Age ratings

The IARC questionnaire ([Microsoft's page](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/age-ratings)).
The exact questions depend on the category picked first and can change; the answers
below follow what the app does. Check each question's info icon when its wording differs.

| Question | Answer | Why |
| --- | --- | --- |
| Category of the app | Not a game; the type for educational/reference or utility/productivity apps | It downloads course files |
| Violence, fear, blood | No | The app has no such content of its own |
| Sexual content or nudity | No | Same |
| Crude language, profanity, discrimination | No | Same |
| Drugs, alcohol, tobacco | No | Same |
| Gambling, simulated gambling | No | Same |
| Users can interact or exchange content with other users (chat, posting, sharing) | No | It only downloads from the student's own courses; nothing is posted |
| Shares the user's location | No | It reads no location |
| Shares personal information with third parties | Yes, optional | If Calendar is enabled, deadline titles, course names, due times and Blackboard links are sent to Google at the user’s request; disclose optional sharing in the submission. Blackboard cookies go only to the school. |
| Digital purchases | No | Free, no in-app purchases |
| Unrestricted internet access (for example a web browser) | No | The sign-in window opens the school's sign-in page; the app is not a browser. Confirm against the question's info text |

The course material comes from the student's school, not from the app. Expect the lowest
rating in most regions; IARC decides.

### 4. Packages

The Store signs the package, so upload the **unsigned** `.msix` from CI, not the test-signed
copy.

1. Pick the `main` commit you tested. The `msix` job of the **CI** workflow builds it on
   every push to `main` and keeps it as the workflow artifact `msix`
   (`Blackboard-Sync-<version>-x64.msix`). Artifacts expire (GitHub's default is 90 days),
   so download it soon after the push.
2. Download it:

   ```sh
   gh run list --workflow ci.yml --branch main --status success --limit 5
   gh run download <run-id> --name msix --dir store/microsoft/out/msix
   ```

   Or: GitHub > Actions > CI > the run for that commit > Artifacts > `msix`.
3. Partner Center > Packages: upload `Blackboard-Sync-<version>-x64.msix`. The version is
   the app version with a fourth part of 0 (`1.5.1` → `1.5.1.0`). Each later submission
   needs a higher version.
4. **Device family availability:** Windows 10/11 Desktop only (the manifest's
   `Windows.Desktop`); leave the others off.
5. Partner Center reports the package's languages (`en-US`, the default, and `tr-TR`), the restricted capability
   `runFullTrust` and the identity; they must match `packaging/msix/identity.toml`.

### 5. Store listings

- [ ] **Languages:** English and Turkish both come from the package, so both listings are
  needed (`listing-en.md` and `listing-tr.md`).
- [ ] **Text:** paste from `listing-tr.md` (and `listing-en.md`): description, short
  description, product features, keywords, copyright and trademark info, developed by.
  Leave "What's new in this version" empty for the first submission. The non-affiliation
  sentence is the second paragraph of the description and part of the copyright line.
- [ ] **Screenshots:** upload `01-tek-tek.png` to `09-tepsi-menusu.png` in order, with the
  captions from the listing file. The problem card comes first, followed by the eight Windows
  captures. Use the Turkish-titled images for both listings (`render.sh --lang en` makes
  English ones in `screenshots/en/` if wanted).
- [ ] **Store logos:** poster art (1440x2160): `images/poster-art.png`; 1:1 box art
  (2160x2160): `images/box-art.png`; 1:1 app tile icons: `images/store-logo-300.png`
  (300x300), `images/store-logo-150.png` (150x150), `images/store-logo-71.png` (71x71).
- [ ] **Trailer:** skip it for the first submission (decided; see [Trailer](#trailer)). The
  promo video shows the macOS app; a trailer built from Windows captures can be added in a
  later submission (`out/trailer-1920x1080.mp4`, thumbnail `out/trailer-thumbnail.png`, title
  from the listing file).
- [ ] **16:9 Super hero art:** `images/hero-art.png`. Optional, but Microsoft shows trailers
  at the top of the listing only when this image is there.
- [ ] **Supplemental fields:** short title, sort title, voice title and additional system
  requirements: leave empty.
- [ ] **Additional license terms:** leave empty (MIT; see the listing files).

### 6. Submission options

- [ ] **Publishing hold:** **Decide.** The default publishes as soon as certification
  passes. "Don't publish this submission until I select Publish now" lets you check the
  live listing text first.
- [ ] **Restricted capabilities (`runFullTrust`):** required. Suggested text:

  ```text
  Blackboard Sync is a desktop app packaged with the Desktop Bridge (Windows.FullTrustApplication; a PyInstaller-built Win32 executable). runFullTrust is required for it to run as a full-trust desktop process: it shows a notification-area (tray) icon and keeps syncing after its window is closed, downloads course files into a folder the user chooses (default Documents\University), starts the user's installed Chromium-based browser (Edge, Chrome and others) with a separate profile for sign-in, or shows a WebView2 sign-in window, and sends toast notifications. It declares no other restricted capabilities.
  ```

- [ ] **Notes for certification:** **Decide** how testers sign in. The app needs a school
  Blackboard Learn account, and Microsoft asks for test account credentials when an app
  requires sign-in ("If we can't fully test your submission, it may fail certification").
  Options: a test account from a school (if one can be arranged), or no account with an
  explanation and a link to the demo video. Suggested text for the second case (date it):

  ```text
  [date] This app downloads course files from a university's Blackboard Learn system. Signing in requires the student's own school account on the school's sign-in page, so we cannot provide a shared test account. Without an account testers can: open the app from Start (the "Get started" first-run page appears; the UI is English, with Turkish under Settings > Language), enter any Blackboard address and choose a folder, open Settings (the gear; automatic sync interval, language, start at sign-in, the note that updates come from the Microsoft Store), and close the window to see the app keep running in the notification area. A demo of a full sync: https://github.com/user-attachments/assets/d7e1e0a7-a25b-4412-824b-52ee71d25b03 . The app has no analytics. It contacts the Blackboard address the user enters and its redirects; optional Calendar sync also contacts Google. Calendar connection is currently CLI-only on Windows.
  ```

- [ ] **Submission notification audience:** the account owner is notified by default; add
  others only if wanted.
- [ ] **Submit for certification** from the app overview page.

## Screenshots

Microsoft: desktop screenshots are PNG, 1366x768 or larger (up to 3840x2160), at most 50 MB,
up to 10 per language, with an optional caption of 200 characters each
([Screenshots, images and trailers](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images)).
All nine images are 1920x1080 with Turkish titles; the opening card introduces the problem,
followed by eight titled screenshots of the Windows app (1.6.2).

The app captures come from `screenshots/capture.py`: the app's own WebView2 page
(`src/blackboard_sync/windows/webui`) with the states of `scripts/webui-preview.py` (the same
invented student, courses and files as the promo films), in a Windows 11 window frame, at 2x.
They are rendered as the Store package shows them, without update rows or offers (the Store
updates the app). The tray image draws the notification-area menu with the app's Turkish menu
texts (`menubar/model.py`, `Model.menu`) above a taskbar corner with the tray icon (the logo).

| Final image / upload order | Content |
| --- | --- |
| [01-tek-tek.png](screenshots/01-tek-tek.png) | “Still downloading files from Blackboard one by one?” / “You no longer have to.” — text-only problem card |
| [02-genel-bakis.png](screenshots/02-genel-bakis.png) | Ana sayfa after a sync: greeting, Güncel, recent files, announcements and upcoming due dates |
| [03-teslim-tarihleri.png](screenshots/03-teslim-tarihleri.png) | Takvim page: upcoming due dates grouped by day |
| [04-google-takvim.png](screenshots/04-google-takvim.png) | Ayarlar: Görünüm (theme) and Google Takvim connected |
| [05-duyurular.png](screenshots/05-duyurular.png) | Duyurular page with three announcements |
| [06-dersler.png](screenshots/06-dersler.png) | Dersler page: five courses, one turned off |
| [07-koyu-tema.png](screenshots/07-koyu-tema.png) | Ana sayfa in the dark theme |
| [08-baslangic.png](screenshots/08-baslangic.png) | Başlangıç first-run page: school address, save folder, start with computer and Giriş yap |
| [09-tepsi-menusu.png](screenshots/09-tepsi-menusu.png) | Notification-area menu above the taskbar, with the tray icon |

![Home](screenshots/02-genel-bakis.png)

### Promo card selection

The source is the maintainer's local `~/Desktop/blackboard-sync-video/scene.html` and its
rendered preview frames. Its reusable text beats (Turkish in the video; English here) are:

- **Problem:** “Still downloading files from Blackboard one by one?” (`s1cap`).
- **Reveal:** “You no longer have to.” (`s2a`).
- **Setup:** “Choose your school, sign in. That's it.” (`s3cap`).
- **Background downloads:** “Checks every hour, downloads new files automatically and lets you know.” (`s4sub`).
- **Organisation:** “Everything on your computer, folder by folder.” (`s5cap`).
- **Other features:** assignment attachments, deleted-file recovery and past-term downloads.
- **Closing value statement:** “Your course files, on your computer automatically.” (`s7tag`).

The problem and reveal are combined into **one opening card**, so the listing introduces
why the app exists and then immediately shows the Windows app. The remaining statements
repeat the app screenshots or need captures that can be added later.

The card reuses the source wording, bold white type, cyan-to-blue emphasis, navy radial
background and cyan glow. Its HTML is laid out afresh for 16:9 in `template.html`; no 4:5
frame is cropped or embedded. It includes no macOS UI, platform badge, logo or LinkedIn
call to action. The Desktop video sources are read-only references and were not modified;
rendering the Store set needs only repository files.

### Sources and rendering

Capture the app, then render the final images, from the repository root:

```sh
PYTHONPATH=src python store/microsoft/screenshots/capture.py   # src/windows/*.png
./store/microsoft/screenshots/render.sh                        # screenshots/*.png
```

`capture.py` needs Playwright's Chromium. Linux has no Segoe UI, so pass a font there
(`--font inter-latin-wght-normal.woff2 --font inter-latin-ext-wght-normal.woff2`, as for the
promo films); `--only ID` recaptures one image. `render.sh` uses headless Google Chrome as on macOS;
on Linux its `--window-size` screenshot can come out short, so check the bottom edge of the images. The template fits each capture within its
image area; the tray image is centred below the title (`compact` in `shots.js`).

The nine final 1920x1080 PNGs are written directly to `screenshots/`. Upload them in the
table's order, with the captions in `listing-tr.md` or `listing-en.md` (also stored in
`screenshots/src/shots.js`). `kind: "card"` in `shots.js` renders the opening card without a
capture; other entries take `src/windows/<id>.png`.

### To add later

- **Deleted files** and **past terms** views.
- **Folders**: File Explorer showing the University term/course folder structure.
- A capture from a real Windows PC to compare with the rendered window before the submission.

## Trailer

Microsoft's requirements against what the script produces:

| Requirement | Trailer here |
| --- | --- |
| MP4 or MOV, at most 2 GB, 60 s or less recommended | MP4, about 34 MB, 56.65 s |
| Video 1920x1080 | 1920x1080, 30 fps (the source's rate) |
| H.264 High profile, progressive, 2 B-frames, closed GOP of half the frame rate, 4:2:0 | H.264 High, `-bf 2`, `-g 15 -flags +cgop`, yuv420p, capped at 50 Mbps |
| AAC-LC stereo, 48 kHz, 384 kbps | AAC-LC stereo 48 kHz, encoded with `-b:a 384k` (the source is mono 44.1 kHz, so both channels carry it and the encoder uses less) |
| moov atom at the front | `-movflags +faststart` |
| Thumbnail PNG 1920x1080 | `out/trailer-thumbnail.png`, a still at 21 s |
| Title, 255 characters at most | In the listing files |
| No age rating in the trailer | None |

The promo video is 1080x1350 (portrait), which Microsoft does not accept. The script places
it at 800x1000 in a frame on a 1920x1080 page in the site's style (`trailer/src/background.html`:
logo, name and tagline on the left, four features on the right). It cuts the video at
54.15 s, where the LinkedIn line "Link yorumlarda 👇" appears, and holds the last clean
frame for 2.5 s with a fade-out.

```sh
./store/microsoft/trailer/make-trailer.sh          # downloads the promo video into out/
./store/microsoft/trailer/make-trailer.sh promo.mp4 # or uses a local copy
```

**Decided:** the first submission goes without a trailer. The promo video shows the macOS
app (macOS window frames, Finder) and an end card reading "macOS & Windows", and Microsoft
requires listing media to represent the product accurately, so a trailer of the macOS app
risks failing certification. A trailer can be added later, rebuilt from Windows captures
(the promo's `scene.html` with Windows images, then this script).

![Trailer thumbnail](trailer/draft-trailer-thumbnail.png)

## Other images

```sh
./store/microsoft/images/make-images.sh
```

- `images/hero-art.png` (1920x1080): the logo on the site's background, centred in the top
  two-thirds, no text and no app UI, as Microsoft asks for Super hero art.
- `images/poster-art.png` (1440x2160) and `images/box-art.png` (2160x2160): the logo
  and `blackboard-sync` name on the hero art's background style, no app UI.
- `images/store-logo-300.png` (300x300), `images/store-logo-150.png` (150x150) and
  `images/store-logo-71.png` (71x71): `assets/icon/logo.png` scaled.

## Open decisions

1. **Notes for certification / test account:** how certification testers can sign in
   (school test account or explanation only). The biggest certification risk.
2. **Markets:** all markets or Turkey only.
3. **Screenshots:** take new English captures for the English listing (`render.sh --lang en`) and
   Turkish ones for the Turkish listing; the current ones show the earlier Turkish-only interface.
4. **Category:** Education > Study aids is proposed; secondary category Productivity or none.
5. **Support contact:** GitHub Issues URL or an email address.
6. **OneDrive backup declaration:** keep the default (checked) or uncheck.
7. **Publishing hold:** publish on certification or hold until "Publish now".

## Settled decisions

- **Screenshots:** open with the promo problem/reveal card, then show eight captures of the
  Windows app (1.6.2, WebView2 window): seven in light mode, one in dark mode, plus the tray
  menu. Keep Turkish titles for both listings.

- **Privacy policy page:** the page is now English, lives at `/privacy` (the old `/gizlilik`
  redirects there) and covers the Store package (data folder, startup task, no GitHub
  contact, removal through Windows Settings).
- **Trailer:** the first submission goes without one; a Windows-based trailer can come later.
- **Name spelling:** the copyright line and "Developed by" use "Umut Yalçın".
