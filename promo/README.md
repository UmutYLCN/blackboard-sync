# Promo videos

Two 1080×1350 (4:5) films for the website and social media, in Turkish:

- `mac.html`: the Mac app, redrawn in its dark appearance (≈58 s).
- `windows.html`: the Windows app, showing **the app's own page** (`windows/webui`) with real
  states from `scripts/webui-preview.py` (≈69 s). It adds the tray icon and the theme switch.

Each film is a web page. `film.js` gives it `window.seek(t)`, and each scene sets its elements
from `t`, so the same film renders the same frames every time. `render.py` steps through the film
in Chromium at 30 fps and pipes the frames to ffmpeg (H.264, `yuv420p`, `+faststart`).

## Render

You need ffmpeg with libx264, Playwright's Chromium, and a woff2 of the film font. The films use
Inter (OFL), e.g. from `npm pack @fontsource-variable/inter`; pass the Latin and Latin Extended
files so Turkish letters use it too:

```sh
PYTHONPATH=src python promo/render.py promo/mac.html --out mac.mp4 \
  --font inter-latin-wght-normal.woff2 --font inter-latin-ext-wght-normal.woff2
PYTHONPATH=src python promo/render.py promo/windows.html --out windows.mp4 --font … --font …
```

To check single frames, use `--still SECONDS` (repeatable) with `--out-dir DIR`.

## Change a film

- The texts are in the HTML. The app texts in `mac.html` match the app's Turkish catalog
  (`src/blackboard_sync/locale_tr.py`); `windows.html` takes them from the app itself.
- The scene timings are in `SCENE_TIMES` and in each scene's `show(...)` calls.
- Icons are Material Symbols Rounded (Apache-2.0, `icons/LICENSE`). Add the SVG to `icons/` and
  `render.py` puts every icon a film references into it.
- The logo is `assets/icon/logo.png`.
