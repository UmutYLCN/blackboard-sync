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
| `screenshots/draft-*.png` | Draft screenshots, 1920x1080. **Do not upload:** they show the macOS app (see [Screenshots](#screenshots)) |
| `screenshots/render.sh` | Renders the screenshots from `screenshots/src/` |
| `screenshots/src/` | `template.html`, `shots.js` (titles, captions, what to capture), `draft-input/` (macOS captures), `windows/` (where the Windows captures go) |
| `trailer/make-trailer.sh` | Builds the 1920x1080 trailer and its thumbnail into `out/` |
| `trailer/draft-trailer-thumbnail.png` | The thumbnail it makes, for review |
| `images/hero-art.png` | 16:9 Super hero art, 1920x1080 (no text, no UI) |
| `images/store-logo-300.png` | 1:1 app tile icon, 300x300 |
| `images/make-images.sh` | Renders both images |
| `shot.sh` | Headless Chrome screenshot helper used by the scripts |
| `out/` | Generated videos and downloads; ignored by git |

The scripts run on macOS with Google Chrome (`CHROME=/path/to/chrome` to use another
Chrome) and, for the trailer, `ffmpeg`.

## Before you start

1. Download the package from CI (see [4. Packages](#4-packages)).
2. Do the manual test in `docs/MSIX.md` ("Manual Windows verification still required")
   with that exact `.msix`, signed with the test certificate as described there.
3. During the test, take the Windows screenshots listed in [Screenshots](#screenshots)
   and render the final images.

## Partner Center checklist

Microsoft's reference: [Create an app submission for your MSIX app](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/create-app-submission).
Items marked **Decide** are the maintainer's call; all are collected again under
[Open decisions](#open-decisions).

### 1. Pricing and availability

- [ ] **Markets:** **Decide.** All markets (the default) or Turkey only. The app works with
  any school's Blackboard Learn, but its interface is Turkish only.
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
- [ ] **Privacy policy URL:** `https://blackboard-sync.umutyalcin.workers.dev/gizlilik`.
  **Decide/fix first:** the page describes the Setup build only. For the Store package it is
  wrong in three places: the data folder is
  `%LOCALAPPDATA%\Packages\<family name>\LocalCache\Roaming\blackboard-sync`, not
  `%APPDATA%\blackboard-sync`; start at login is a Windows startup task, not an `HKCU\…\Run`
  value; and the package never contacts GitHub (no update checks, no "Uygulamayı kaldır…"
  button). Update the page (a site change, not part of this folder) before submitting. The
  page is Turkish only; an English listing may warrant an English version.
- [ ] **Website:** `https://blackboard-sync.umutyalcin.workers.dev`.
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
| Shares personal information with third parties | No | The session goes only to the school's own Blackboard (privacy page: "Verilerin hiçbir üçüncü tarafla paylaşılmaz") |
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
5. Partner Center reports the package's language (`tr-TR`), the restricted capability
   `runFullTrust` and the identity; they must match `packaging/msix/identity.toml`.

### 5. Store listings

- [ ] **Languages:** Turkish comes from the package. **Decide** whether to add English
  (**Add/remove languages > Manage additional languages**).
- [ ] **Text:** paste from `listing-tr.md` (and `listing-en.md`): description, short
  description, product features, keywords, copyright and trademark info, developed by.
  Leave "What's new in this version" empty for the first submission. The non-affiliation
  sentence is the second paragraph of the description and part of the copyright line.
- [ ] **Screenshots:** upload `01-genel-bakis.png` … `05-klasorler.png` in that order, with
  the captions from the listing file. Only the final (Windows) images; never `draft-*.png`.
  Images are uploaded separately for each language.
- [ ] **Store logos:** 1:1 app tile icon (300x300): `images/store-logo-300.png` (optional;
  without it the Store uses the package's logo). Poster and box art are for games; skip.
- [ ] **Trailer:** **Decide** (see [Trailer](#trailer)). If used: `out/trailer-1920x1080.mp4`,
  thumbnail `out/trailer-thumbnail.png`, title from the listing file.
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
  [date] This app downloads course files from a university's Blackboard Learn system. Signing in requires the student's own school account on the school's sign-in page, so we cannot provide a shared test account. Without an account testers can: open the app from Start (the "Başlangıç" first-run page appears; the UI is Turkish), enter any Blackboard address and choose a folder, open the "Genel" settings (automatic sync interval, start at sign-in, the note that updates come from the Microsoft Store), and close the window to see the app keep running in the notification area. A demo of a full sync: https://github.com/user-attachments/assets/d7e1e0a7-a25b-4412-824b-52ee71d25b03 . The app has no analytics and contacts only the Blackboard address the user enters.
  ```

- [ ] **Submission notification audience:** the account owner is notified by default; add
  others only if wanted.
- [ ] **Submit for certification** from the app overview page.

## Screenshots

Microsoft: desktop screenshots are PNG, 1366x768 or larger (up to 3840x2160), at most 50 MB,
up to 10 per language, with an optional caption of 200 characters each
([Screenshots, images and trailers](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images)).
They must show the Windows app as it is. The images here are 1920x1080 with one large
Turkish title at the top (Microsoft asks for key visuals and text in the top two-thirds).

The drafts use the only captures available, which are of the **macOS** app: the Windows app
is a different (Tk) window. Every draft carries an orange "TASLAK · Store'a yüklemeyin" label;
`draft-05-klasorler.png` is an empty placeholder.

![Draft 1](screenshots/draft-01-genel-bakis.png)

### Windows captures to take during the manual test

Use the Store package (signed with the test certificate), signed in with a real account,
after at least one sync. Set Windows display scaling to 150% or 200% (Settings > System >
Display) so the window is captured large; the app opens at 940x640 (logical) and the
template scales any capture to fit. Capture only the window, as PNG (Snipping Tool >
Window mode, or Alt+Print Screen and paste into Paint). Keep the window free of anything
that should not be public (the sidebar shows the account's name).

| File (`screenshots/src/windows/`) | Window and state |
| --- | --- |
| `01-genel-bakis.png` | Main window, **Genel bakış**, after a sync: the **Son indirilenler** list filled |
| `02-ayarlar.png` | Main window, **Genel**, scrolled to the top: **Hesap**, **Klasör** and **Genel** sections (automatic sync, start at sign-in) |
| `03-silinenler.png` | Main window, **Silinenler**, with a few deleted files listed (delete 2-4 downloaded files from the University folder first) |
| `04-eski-donemler.png` | Main window, **Genel**, scrolled to **Eski dönemler** with a term selected in the list |
| `05-klasorler.png` | File Explorer on `Belgeler\University`, with a term folder and a course folder open in the navigation pane |

Then render, from the repository root:

```sh
./store/microsoft/screenshots/render.sh
```

Each shot with a Windows capture is written as `screenshots/<id>.png` (no label) and its
draft is removed; shots still without one stay drafts. `--lang en` renders English titles
into `screenshots/en/`. Titles, captions and the list of shots are in
`screenshots/src/shots.js`. A screenshot of a toast notification after a sync would be a
good sixth image; add an entry to `shots.js` for it.

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

**Decide:** the promo video shows the macOS app (macOS window frames, Finder) and an end
card reading "macOS & Windows". Microsoft requires listing media to represent the product
accurately, so a trailer of the macOS app risks failing certification. Recommendation:
submit without a trailer, and add one later rebuilt from Windows captures (the promo's
`scene.html` with Windows images, then this script).

![Trailer thumbnail](trailer/draft-trailer-thumbnail.png)

## Other images

```sh
./store/microsoft/images/make-images.sh
```

- `images/hero-art.png` (1920x1080): the logo on the site's background, centred in the top
  two-thirds, no text and no app UI, as Microsoft asks for Super hero art.
- `images/store-logo-300.png` (300x300): `assets/icon/logo.png` scaled.

## Open decisions

1. **Notes for certification / test account:** how certification testers can sign in
   (school test account or explanation only). The biggest certification risk.
2. **Privacy policy page:** update it for the Store package (data path, startup task, no
   GitHub contact) before submitting; consider an English version.
3. **Trailer:** submit without one (recommended), or with the macOS-based trailer here.
4. **Markets:** all markets or Turkey only.
5. **English listing:** add it or not; if yes, Turkish-titled screenshots or `--lang en` ones.
6. **Category:** Education > Study aids is proposed; secondary category Productivity or none.
7. **Support contact:** GitHub Issues URL or an email address.
8. **OneDrive backup declaration:** keep the default (checked) or uncheck.
9. **Publishing hold:** publish on certification or hold until "Publish now".
10. **Screenshot style:** Microsoft's guidelines say "Don't add additional logos, icons, or
    marketing messages to your screenshots"; the images here carry a title (no logo). Keep
    the titles (common in the Store) or render the plain captures.
11. **Name spelling:** the copyright line and "Developed by" use "Umut Yalcin", as in
    `LICENSE`; change to "Umut Yalçın" if preferred.
