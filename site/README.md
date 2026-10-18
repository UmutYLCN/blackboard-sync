# Blackboard Sync promotional site

English and Turkish promotional pages with local assets, plain HTML/CSS/JavaScript, and no build or dependencies.

Preview from the repository root:

```sh
python3 -m http.server 8000 --directory site
```

Open http://localhost:8000. The two download links start at GitHub's latest release page, then resolve to the latest `.dmg` and `-Setup.exe` assets when the public GitHub API responds. API errors, missing assets, and disabled JavaScript preserve the release-page fallback. No analytics or trackers are included.

Short download links `/mac` and `/windows` are handled by a small Worker (`worker/index.js`). It reads the latest release from the GitHub API, caches it for five minutes, and answers with a 302 to the `.dmg` or `-Setup.exe` asset (falling back to `.exe`, then `.msi`). API errors or a missing asset redirect to the latest release page. The Worker also answers byte ranges for the promo MP4. Every other path is served as a static asset without running the Worker. To try the links locally:

```sh
cd site
npx wrangler@4.149.0 dev --persist-to ../.wrangler/state
```

Keeping local state outside `site/` stops the dev server from reloading on its own writes.

Browser checks run in the Website GitHub Actions workflow against Wrangler's
real asset server, including EN/TR navigation without JavaScript, narrow screens,
download API failures and the legacy privacy redirects. With the server above
running and pytest/Playwright plus Chromium installed, run
`python -m pytest -q site/tests` from the repository root. Screenshots are attached
to the workflow run; tests and test caches are excluded from published assets.

English stays at `/` and `/privacy`. Turkish is served at `/tr/` and `/tr/privacy`
from `tr/index.html` and `tr/privacy.html`. The EN/TR links in the header switch to
the corresponding page, and internal links keep the current language. These are
complete HTML pages with translated metadata and alternate-language links; they
work without JavaScript or browser storage. Both languages use the same CSS,
download-link script, video and images. The header scrolls with the page.

`_redirects` sends the old Turkish address `/gizlilik` (and `/gizlilik.html`) to
`/tr/privacy` with a 301. Extensionless paths and redirects are handled by
Cloudflare's asset server, so check them with `wrangler dev` rather than
`python3 -m http.server`.

The production site is served at <https://blackboardsyncapp.com/>. The root domain is
attached to the existing Cloudflare Worker as a custom domain; `/privacy` serves
`privacy.html`, and `/mac` and `/windows` remain the short download routes.

Cloudflare Workers Builds settings:

- Root directory: `/site`
- Build command: leave empty
- Deploy command: `npx wrangler deploy` (reads `wrangler.jsonc`)

`.assetsignore` keeps the Worker code, Wrangler config and this README out of the published assets.

`_headers` applies security headers and a one-day asset cache; HTML/CSS/JS revalidate because their filenames are not versioned. The one-minute MP4 (`assets/promo-mac-tr.mp4`, made with `promo/mac.html`; see `promo/README.md`) is served with the other assets (Workers allow 25 MiB per asset). It has no sound. The Worker answers byte ranges for it, which Safari needs to play video; the assets binding alone sends the whole file. A changed video or poster gets a new file name, because assets are cached for a day. Native video controls allow pausing; reduced-motion preferences disable automatic playback when JavaScript is enabled.

The social card references the existing public repository banner by absolute URL. The page declares `https://blackboardsyncapp.com/` as its canonical URL. Page assets, the video included, are local. Header and footer logos use 128 px PNGs with 256 px retina variants; the favicon is a separate 32 px PNG. Review screenshots are linked from an earlier commit in the pull request and are not included in the deployed folder.
