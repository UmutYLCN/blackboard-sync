# Safari extension (Mac App Store build)

The Mac App Store build reaches Gemini Notebook through Safari: App Sandbox lets the app neither
drive a browser nor read Google's cookies. This Safari Web Extension runs on notebook.google.com,
makes the Gemini Notebook calls with the student's own Safari session, and takes its work from the
app over a loopback bridge. See `src/blackboard_sync/notebooklm/safari.py` for the app side.

- `Resources/`: the web extension (manifest V3, `_locales` in the app's six languages).
  `notebook-client.js` ports the notebooklm-py calls `notebooklm/gateway.py` uses; keep them in step.
- `SafariWebExtensionHandler.swift`: the required native handler, a stub.
- `scripts/build-safari-extension.sh APP` builds `Blackboard Sync Extension.appex` into the app's
  `Contents/PlugIns` (called by `scripts/build-mas.sh`); `scripts/sign-mas.sh` signs it with
  `packaging/entitlements/mas-safari-extension.plist`.

Its bundle id is the app's plus `.SafariExtension` (`safari.EXTENSION_SUFFIX`).

A local ad-hoc build only loads in Safari with Settings > Developer > **Allow unsigned
extensions** ticked; Safari clears that whenever it quits.
