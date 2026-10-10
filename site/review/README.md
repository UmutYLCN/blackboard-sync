# Browser verification

Verified in installed Google Chrome, headless mode, on 2026-10-10. Chrome DevTools Protocol was used directly after the prescribed chrome-devtools-axi integration failed to supply the backend's required pageId; firstmate approved this fallback.

- Desktop viewport: 1440 × 1000; full-page screenshot in `desktop.png`.
- Mobile viewport: 390 × 844; full-page screenshot in `mobile.png`.
- Additional 360 × 800 mobile check: document width equals viewport width, with no horizontal overflow.
- Live GitHub API resolved macOS to `https://github.com/UmutYLCN/blackboard-sync/releases/download/v1.4.4/Blackboard-Sync-1.4.4.dmg` and Windows to `https://github.com/UmutYLCN/blackboard-sync/releases/download/v1.4.4/Blackboard-Sync-1.4.4-Setup.exe`; both show v1.4.4.
- Local H.264 video loaded at its original 1080 × 1350 resolution and played muted. Screenshots pause it at two seconds for a consistent capture.
- Emulated reduced motion disabled autoplay and paused playback.
- Disabled JavaScript, simulated HTTP 403, and a simulated fetch network failure all retained both latest-release fallback links.
- JavaScript syntax checked with `node --check site/script.js`; staged changes checked with `git diff --cached --check`.

Cloudflare-specific response headers are declared in `_headers`; Python's local server does not apply them. Deployment is outside this change's scope.
