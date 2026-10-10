# Blackboard Sync promotional site

A single Turkish page with local assets, plain HTML/CSS/JavaScript, and no build or dependencies.

Preview from the repository root:

```sh
python3 -m http.server 8000 --directory site
```

Open http://localhost:8000. The two download links start at GitHub's latest release page, then resolve to the latest `.dmg` and `-Setup.exe` assets when the public GitHub API responds. API errors, missing assets, and disabled JavaScript preserve the release-page fallback. No analytics or trackers are included.

Short download links `/mac` and `/windows` are handled by a small Worker (`worker/index.js`). It reads the latest release from the GitHub API, caches it for five minutes, and answers with a 302 to the `.dmg` or `-Setup.exe` asset (falling back to `.exe`, then `.msi`). API errors or a missing asset redirect to the latest release page. Every other path is served as a static asset without running the Worker. To try the links locally:

```sh
cd site
npx wrangler@4.149.0 dev --persist-to ../.wrangler/state
```

Keeping local state outside `site/` stops the dev server from reloading on its own writes.

Cloudflare Workers Builds settings:

- Root directory: `/site`
- Build command: leave empty
- Deploy command: `npx wrangler deploy` (reads `wrangler.jsonc`)

`.assetsignore` keeps the Worker code, Wrangler config and this README out of the published assets.

`_headers` applies security headers and a one-day asset cache; HTML/CSS/JS revalidate because their filenames are not versioned. The 45-second MP4 is hosted as a GitHub user attachment and loaded by the page. Native video controls allow pausing and sound; reduced-motion preferences disable automatic playback when JavaScript is enabled.

The social card references the existing public repository banner by absolute URL, so sharing works before a custom site domain is chosen. Page assets are local except for the hosted video. Header and footer logos use 128 px PNGs with 256 px retina variants; the favicon is a separate 32 px PNG. Review screenshots are linked from an earlier commit in the pull request and are not included in the deployed folder.
