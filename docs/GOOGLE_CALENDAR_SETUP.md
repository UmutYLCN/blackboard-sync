# Google Calendar setup

Official release packages include the Desktop OAuth client metadata and require
no Client Secret entry by end users. Google Calendar is optional. A public Desktop OAuth client ID is configured in
`gcal.CLIENT_ID`; `BBSYNC_GOOGLE_CLIENT_ID` overrides it for development. No Google SDK is needed.
The environment override works with both the CLI and the macOS app launched from
that terminal. Never put downloaded OAuth credentials or refresh tokens in Git.

## Create your development client

1. Open [Google Cloud Console](https://console.cloud.google.com/), use the project
   selector → **New project**, name it (for example **Blackboard Sync Dev**),
   create it and select it.
2. Open **APIs & Services → Library**, search **Google Calendar API**, open it
   and click **Enable**.
3. Open **Google Auth Platform → Branding** (or the OAuth consent screen entry
   under APIs & Services). Click **Get started** if prompted. Enter the app name,
   your user support email and developer contact email. Choose **External** for
   personal Gmail accounts or users outside your Workspace organization; finish
   the initial setup. Do not select Internal for a publicly distributed app.
4. Under **Branding**, set the app homepage and privacy policy URLs to your
   published project pages. For production, use domains you own and can verify.
5. Open **Audience**. Keep the development project in **Testing**. Under
   **Test users → Add users**, add the exact Google account email(s) you will
   authorize with and save. Workspace administrators may still block consent.
6. Open **Data Access → Add or remove scopes**. Add only
   `https://www.googleapis.com/auth/calendar.app.created`; if needed paste the
   full URI under manually adding scopes, update and save. Do not add broad
   Calendar, CalendarList, profile or email scopes.
7. Open **Clients → Create client**, choose **Desktop app**, name it, create it
   and copy its **Client ID**. Do not create a Web application client. Desktop
   clients use `http://127.0.0.1:<random-port>/`; there is no fixed port to register.
   Keep any downloaded client JSON outside the repository.
8. In a terminal in this checkout:

   ```sh
   export BBSYNC_GOOGLE_CLIENT_ID='YOUR_ID.apps.googleusercontent.com'
   .venv/bin/blackboard-sync calendar connect
   .venv/bin/blackboard-sync calendar status
   .venv/bin/blackboard-sync sync
   .venv/bin/blackboard-sync calendar sync
   ```

   Consent opens in your system browser; select a test account and grant the
   requested access. Return to the terminal within four minutes. The redirect
   listener binds only to IPv4 loopback and checks a random state and PKCE S256.
   If your Desktop client requires a client secret at the token endpoint, also
   set `BBSYNC_GOOGLE_CLIENT_SECRET` to the downloaded value in this terminal.
   It is optional public-client metadata, never a substitute for PKCE. Do not
   paste it into source code, issues, logs or shell scripts in the repository.
   `calendar sync --reminders` opts into the dedicated calendar's default Google
   reminders; by default Google reminders are disabled.

   To test the macOS GUI with the same environment, launch it directly:

   ```sh
   .venv/bin/blackboard-sync-menubar
   ```

   Quit an existing app instance first. Finder-launched apps do not inherit
   terminal exports. For production, set the public `gcal.CLIENT_ID` in the
   distribution build after registering the real Desktop client; never embed
   refresh tokens. If that client requires additional metadata, supply it through
   the distribution's configuration rather than committing credentials.

## Publishing

Use separate development and production Cloud projects. Before distributing the
Calendar integration, configure accurate Branding (app identity, support contact,
homepage, privacy policy and authorized domains), and verify domain ownership as
requested. In **Audience**, publish the production app to **In production**.
Complete the branding and scope verification required by the **Verification
Center**; publishing alone does not mean the app is verified. If Google marks a
requested scope sensitive/restricted, submit its justification and the requested
demo/verification material before public rollout. Request only the scope the code
actually uses. Review quotas and Google API Services User Data Policy, including
Limited Use; the privacy page contains the required disclosure.

In External/Testing, Calendar authorization and offline refresh tokens expire
after **seven days**. Reconnect when prompted. Production removes that testing
lifetime restriction, but tokens can still be revoked or expire for other reasons;
users with already expired grants must reconnect. Do not promise perpetual access.

## Local data and disconnect

The refresh token is in macOS Keychain (`blackboard-sync.google-calendar`) or
Windows Credential Manager. Each data directory has its own vault account.
Other platforms use owner-only `google-token.json`. Access tokens remain in memory.
`google-calendar.json` contains the dedicated calendar ID and connection status;
`google-calendar-events.json` maps Blackboard keys to Google event IDs and hashes.
`google-calendar-target.json` retains only the dedicated calendar ID when
Disconnect keeps the Google calendar. Reconnecting reuses it, and Disconnect with
Delete can remove it before another sync. It contains no token or event mapping;
deleting the remote calendar also clears this handle. No tokens are printed by
`calendar status`.

```sh
blackboard-sync calendar disconnect
# Opt in to removing the entire app-created calendar, before revoking access:
blackboard-sync calendar disconnect --delete-calendar
```

Without the flag, existing Google events stay in Google and stop updating. Only
the non-secret dedicated-calendar ID remains locally for reconnection. Older builds
that already forgot the ID cannot discover it with the narrow app-created scope;
remove that orphaned Blackboard Deadlines calendar once in Google Calendar
Settings → select that calendar → Remove calendar → Delete. The new code reports
an explicit error if deletion is requested without any saved calendar ID. Revoking
access does not delete them. You can also remove access on
[Google Account → Third-party connections](https://myaccount.google.com/connections).
If access is already revoked, Google cannot authorize calendar deletion: reconnect
first, or delete Blackboard Deadlines manually in Google Calendar settings. A
network failure during disconnect is reported; retry to finish revocation. Remove
access before uninstalling (especially the Microsoft Store package); uninstalling
local files alone does not revoke Google's grant or delete the Google calendar.

## Manual Mac acceptance checklist

- [ ] Start the source app with your client ID exported. Open Settings → Google
      Calendar and Connect. The UI stays responsive; cancel once, then connect
      again. Save/Cancel of other settings does not undo the connection.
- [ ] Complete a Blackboard sync. A new deadline appears in **Blackboard
      Deadlines**, titled `[COURSE] Title`, lasting 30 minutes and ending at its
      due time, with its Blackboard link and no Google reminder. Your main
      calendar has no app event.
- [ ] Change the deadline in Blackboard; sync again. The same Google event gets
      the new end time. A further unchanged sync creates no duplicate.
- [ ] Remove a deadline in Blackboard; sync again. Its Google event disappears.
      Hide a course and sync; its events disappear too. Passing the due time
      alone does not delete an event.
- [ ] Pause the app: no automatic Calendar updates. Resume, let Blackboard sync
      finish, and verify Calendar updates afterward. Test manual and scheduled
      Blackboard runs as well.
- [ ] Delete the dedicated calendar in Google; sync again. A new dedicated
      calendar is created and eligible deadlines repopulate it.
- [ ] Disconnect with the deletion checkbox off: connection clears, calendar
      stays. Reconnect without syncing; disconnect with the checkbox on: dedicated calendar is
      deleted. Confirm Cancel of the dialog has no effect.
- [ ] Connect again. Remove access at Google Account → Third-party connections.
      Run Sync calendar now (or wait for the next successful Blackboard sync).
      Home shows **Google Calendar needs to be reconnected**. Its Reconnect
      action opens Settings at Google Calendar. Blackboard sync still succeeds.
- [ ] Test the same flows with Turkish selected; check row text fits the window.

Windows already shares automatic post-sync updates, pause/cancellation, credential
storage and Home attention. Native Windows connection/status/sync/disconnect
controls, the delete-calendar confirmation and scrolling directly to a Calendar
settings section remain out of scope; connect/reconnect/disconnect using the CLI.

References checked 2026-10-18:
[scope definitions](https://developers.google.com/workspace/calendar/api/auth),
[Desktop OAuth and PKCE](https://developers.google.com/identity/protocols/oauth2/native-app),
[Audience and test users](https://support.google.com/cloud/answer/15549945),
[verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification).


## Release packaging and client metadata

For local source runs/builds, store the downloaded Desktop JSON under
`.bbsync/google-oauth-client.json` (gitignored), or set
`BBSYNC_GOOGLE_OAUTH_CLIENT_FILE` to its path. This file uses Google's
`{"installed": {"client_id": "…", "client_secret": "…"}}` format. Never add it to
Git. Explicit `BBSYNC_GOOGLE_CLIENT_ID` / `BBSYNC_GOOGLE_CLIENT_SECRET` values
override the file when testing a different client.

The release workflow consumes the repository Actions secret
`GOOGLE_CALENDAR_OAUTH_CLIENT_JSON`. Set it from a local file through stdin, never
as a command-line value. `packaging/google_oauth_bundle.py` validates the Desktop
configuration and emits only its client ID and client secret as a private build
input for PyInstaller. Both macOS and Windows bundles include that metadata as
`assets/google-oauth-client.json`. User tokens are never bundled. Release builds
fail if metadata is missing; ordinary development builds may omit it.

A Desktop OAuth client is a public client: someone who downloads the installer can
extract its client metadata. Bundling is a convenience, not protection of a
server-side credential. PKCE, state verification and user consent remain mandatory;
users' refresh tokens still belong in their OS credential stores.
