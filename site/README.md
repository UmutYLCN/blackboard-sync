# Blackboard Sync promotional site

A single Turkish page with local assets, plain HTML/CSS/JavaScript, and no build or dependencies.

Preview from the repository root:

```sh
python3 -m http.server 8000 --directory site
```

Open http://localhost:8000. The two download links start at GitHub's latest release page, then resolve to the latest `.dmg` and `-Setup.exe` assets when the public GitHub API responds. API errors, missing assets, and disabled JavaScript preserve the release-page fallback. No analytics or trackers are included.

Cloudflare Pages settings:

- Root directory: `site`
- Framework preset: None
- Build command: leave empty
- Build output directory: `.`

`_headers` applies security headers and a one-day asset cache; HTML/CSS/JS revalidate because their filenames are not versioned. The original 45-second MP4 is copied without re-encoding. Native video controls allow pausing and sound; reduced-motion preferences disable automatic playback when JavaScript is enabled.

The social card references the existing public repository banner by absolute URL, so sharing works before a custom site domain is chosen. Visible page assets are local. Header and footer logos use 128 px PNGs with 256 px retina variants; the favicon is a separate 32 px PNG. Review screenshots are linked from an earlier commit in the pull request and are not included in the deployed folder.
