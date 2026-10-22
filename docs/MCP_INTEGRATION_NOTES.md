# Blackboard Sync MCP integration notes

**Status:** This is a future-feature research note. It describes options and recommendations; it is not an implemented feature or release approval. Research retrieved 22 October 2026.

This note evaluates exposing Blackboard Sync’s locally cached course content to an AI client through MCP, with an optional embedded terminal for an official AI CLI. The recommendations are planning guidance only.

## Recommendation and limits

**A local, read-only MCP server is feasible and is the right reusable foundation.** The AI client owns inference, its subscription, authentication, and chat history; Blackboard Sync supplies only approved, already synced content. No provider API key needs to enter Blackboard Sync.

Start with stdio, a small fixed tool set, explicit course consent, and a launch command in the installed application. Support existing GUI clients as the dependable baseline. **Prototype a polished embedded real terminal early**, as requested: it could keep students inside Blackboard Sync while an unmodified official CLI remains the AI client. It is a presentation and process-hosting project on top of MCP, not a replacement for MCP.

Do not promise universal “connect your AI account” support:

- Current **ChatGPT desktop/Codex-host documentation supports direct local stdio MCP**. ChatGPT **web custom MCP connections** use public HTTPS or Secure MCP Tunnel; these are separate surfaces with different permissions.
- Claude Desktop supports local servers and one-click **.mcpb** desktop extensions. A desktop extension and a local-server plugin are not interchangeable: current Anthropic guidance says a plugin referencing a local server runs in Cowork/Code rather than ordinary chat. Test the intended extension/chat surface.
- Gemini CLI supports local MCP and a native **ACP mode**. Gemini’s consumer web/mobile apps now have custom MCP connections, but the retrieved help restricts them to **US adults, personal accounts, English, and Keep Activity enabled**. They do not document a local process launcher.
- No local transport guarantees local inference. Content returned to Claude, ChatGPT, or Gemini can go to that provider. An entirely local model/client is a separate configuration.
- Hosting an official CLI does **not** automatically grant permission to sell or distribute a subscription-backed third-party AI product. Anthropic’s public guidance is particularly restrictive and internally qualified; OpenAI’s app-server authentication guidance distinguishes local/open-source apps from commercial/hosted services. See section 7.

Estimated future effort: **6–10 engineer-days** for a useful stdio release on macOS/Windows Setup, then **1–2 days for a disposable two-platform terminal-feel prototype** and roughly **10–18 additional days** to make one embedded CLI polished and supportable. Store-launch integration, further clients, vendor clarification, review queues, and accessibility findings can extend this. Estimates are planning judgments, not measurements.

No product decision is required to use this note as future planning input. Recommendations and future verification conditions below do not authorize building.

## 1. Prior research reused, and repository integration map

Earlier API-key research found that user-supplied provider API keys are the simplest route for an in-app AI feature: the user controls the key and provider account, while the application would need to secure the key and explain provider data handling and usage costs. The provider may receive prompts and course content, usage can incur separate charges, and an API key does not grant rights to redistribute subscription-backed services. Those findings remain relevant to any future in-app route; an MCP exporter avoids collecting a provider key but does not prevent the client from sending shared content to its provider. The established privacy promise, consent principles, school-policy cautions, Calendar separation, and distribution/store facts also apply. Essential facts:

1. Saved Blackboard sign-in material is promised to stay local and go only to the school. Optional Calendar already has separate data-sharing and permission disclosures.
2. AI must be optional; consent to connect a client is distinct from permission to disclose every course.
3. Do not expose grades, identifiable classmates, Google Calendar data, credentials, logs, signed download URLs, or whole private databases.
4. The current Mac release is a DMG; Windows has Setup and MSIX/Store builds. The Store checklist currently leaves generative AI unchecked.
5. Permission to download course material does not establish permission to send it to a model. School/course assessment rules remain controlling.

### Prior API-key research conclusions

User-supplied API keys are the simplest in-app integration route, but they require secure key handling, clear provider privacy disclosures, and explicit notice that model usage may cost extra. Provider terms govern use and redistribution. MCP keeps provider authentication in the chosen AI client; it does not change the privacy or academic-integrity implications of sending course content to a model.

The only store-policy recheck here was the narrower question of whether an MCP exporter, as opposed to an in-app generator, triggers the live-generative-AI declaration.

Local references below use this repository snapshot and line numbers, not a student’s runtime files:

| Existing seam | Evidence | Implementation consequence |
| --- | --- | --- |
| Python CLI and runtime | `pyproject.toml:11`, `:39`; `src/blackboard_sync/cli.py:49`, `:282`; `runtime.py:18` | Python >=3.10 today; add an explicit offline `mcp` branch. Frozen apps re-invoke their executable, not a system Python. |
| Frozen dispatch | `packaging/app_entry.py:20`, `:53` | Add `mcp` to dispatch; otherwise a bare subcommand launches the GUI. Dispatch before GUI initialization or stdout logging. |
| Windows stdio executable | `packaging/blackboard_sync_windows.spec:47`; `windows/app.py:77` | Use the existing console twin `blackboard-sync-cli.exe`. The GUI executable can lose standard streams. |
| Mac bundle | `packaging/blackboard_sync.spec:14`, `:51`, `:53` | Existing executable is inside `Blackboard Sync.app/Contents/MacOS/Blackboard Sync`. Verify pipe inheritance and frozen imports. |
| Private data discovery | `system.py:35`; `config.py:39` | macOS Application Support; Windows Setup Roaming AppData; Store has an explicit package-specific location. |
| Destination root | `system.py:63`, `:80`; `config.py:63` | Respect saved destination and the University-root migration rules. Never infer the content root from current working directory. |
| Disabled courses | `courses.py:52`, `:81` | Unticked courses remain on disk. Their files must still be unavailable through MCP. The current loader fails open on malformed input; MCP authorization must not inherit that behavior. |
| Current membership and archives | `state.py:106`; `sync.py:1346`, `:1355`, `:1377` | Intersect current membership, course catalog, enabled status, and separate MCP consent. Past terms are not implicitly authorized. |
| Announcement cache | `announcements.py:47`, `:84` | Cache has a preview and an output key. Full text comes from the recorded note’s Markdown twin, not the preview. |
| Exact Markdown keys | `sync.py:220`, `:861`, `:942`, `:1116`; `paths.py:150` | Content notes use `note-md:...`; announcement notes use `announcement-note-md:...`. Resolve recorded keys; do not guess filenames from titles. |
| Deadline cache | `deadlines.py:38`, `:49`, `:174`; `sync.py:672` | Use cached grading due dates, explicit timezone, and unavailable/stale status. Do not ask a model to infer dates from text. |
| State loading and ownership | `state.py:130`, `:245`, `:278` | Default load can rename corrupt files. MCP needs a strictly read-only, validated snapshot and an output-to-course ownership map. |
| Existing settings | `settings.py:54`, `:90` | Corrupt settings currently collapse to defaults. MCP must report configuration unavailable rather than silently choose a new root or permission scope. |
| Installation/update paths | `packaging/installer.iss:22`, `:70`; `packaging/msix/AppxManifest.xml.in:33` | Setup path is stable and per-user. Its updater kills both executables. MSIX has no execution alias today; a stable Store launcher is future work. |
| Python in release builds | `.github/workflows/release.yml:27`, `:224` | Builds use Python 3.12, despite source support beginning at 3.10. SDK runtime compatibility must be explicit. |

These are integration constraints, not reproduced existing defects. Existing sync behavior should not be changed merely to add MCP; introduce strict export-only adapters where necessary.

## 2. MCP fundamentals that matter here

MCP standardizes how an AI host discovers and calls tools and reads resources over JSON-RPC. Blackboard Sync would be the **server**; the student’s AI application is the **host**, containing an MCP **client**. MCP is not a model, a subscription-sharing mechanism, or a guarantee of safe agent behavior. Tools suit questions/search; resources suit explicitly selected context. A custom chat UI or MCP Apps interface is optional. [Specification][S01] [Tools][S08] [Resources][S09]

### Version: current docs differ materially from 2025 examples

On retrieval, `/specification/latest` redirected to **2026-07-28**. Its predecessor is 2025-11-25. The new revision uses self-contained requests with version/capabilities in `_meta` and `server/discover`; it removes the connection-scoped initialize handshake and HTTP session header for modern peers. Ordinary results carry `resultType`. Cacheable resource/list results add freshness and privacy fields. Older clients still use initialize negotiation. [Current specification][S01] [Key changes][S02]

**Recommendation:** implement through a pinned SDK with tested legacy and modern support. Do not copy a tiny 2024/2025 initialize-only tutorial and call it the latest protocol. Keep transport/version handling outside the domain layer. Python SDK documentation describes bridging both eras, including legacy HTTP sessions; verify stdio negotiation with the exact selected SDK/clients. Do not hardcode one revision into every business handler. [SDK protocol versions][S11] [Legacy clients][S12]

### Transport choices

| Transport/topology | Who starts it | Authentication/boundary | Fit here |
| --- | --- | --- | --- |
| **stdio local subprocess** | AI client launches an executable and communicates through its pipes | No web listener or HTTP OAuth flow. OS account/process access plus the app’s export consent are the primary boundary. No provider credentials needed. | **First milestone.** Simple lifecycle; independent reader process per client. |
| **Streamable HTTP on loopback** | App runs an HTTP service; local clients connect | Bind to 127.0.0.1, validate Origin/Host, authenticate every request with a separate local connection credential or compatible OAuth. Loopback alone is insufficient. | Later, only for clients that benefit from a shared endpoint. |
| **Remote Streamable HTTP** | Hosted service or a bridge forwards requests to the local reader | HTTPS, per-user authorization, token audience/scope checks, isolation, revocation, monitoring and availability | A materially different deployment. Needed for ordinary cloud clients unless an approved private tunnel is used. |

Local HTTP and remote HTTP are deployment locations of the same transport, not two protocol names. HTTP can return JSON or SSE streams. The deprecated **HTTP+SSE transport** is different from SSE used within Streamable HTTP; do not introduce a legacy SSE endpoint for convenience. [Transport bindings][S03] [stdio][S04] [Streamable HTTP][S05]

For stdio, stdout must contain protocol messages only, encoded as UTF-8 and newline framed. Safe diagnostic codes go to stderr; no banners, progress text, raw paths, course bodies, tokens, or verbose network logs. Exit promptly on stdin EOF and client termination; never start the menu bar/tray application as a side effect.

MCP HTTP authorization is optional at protocol level, but a private course-content service should require it. The standard uses OAuth 2.1-oriented flows, protected-resource and authorization-server discovery, resource indicators, PKCE and issuer/audience validation. Current docs prefer Client ID Metadata Documents, while keeping Dynamic Client Registration for compatibility. A local shared-secret bearer token may suit a controlled local client; it is not a substitute for interoperable remote OAuth. An MCP token authorizes content access; it is entirely distinct from an AI subscription token or Blackboard session. [Authorization][S06]

### Official Python SDK versus hand-written server

**Use the official `mcp` SDK provisionally, after a frozen-build size spike.** It is Tier 1. Current v2 documentation uses `MCPServer`; older examples using `FastMCP` describe another API generation. The separate third-party FastMCP distribution should not be confused with the SDK’s historic helper. Install plain `mcp` in runtime; keep CLI extras/Inspector in development. [SDK directory][S10] [Python SDK][S13]

Public registry inspection on 2026-10-22 found:

- Latest PyPI release **mcp 2.3.0**; wheel **368,664 bytes compressed**, **1,210,630 bytes unpacked**, before dependencies.
- Its metadata and release-tag pyproject say **Python >=3.10**. The latest docs/main branch say **Python >=3.11**. This discrepancy is real; pin and test the release, and do not silently raise this app’s source requirement.
- Base dependencies include AnyIO, httpx2, jsonschema, mcp-types, OpenTelemetry API, Pydantic, PyJWT with crypto, multipart, SSE-Starlette, Starlette, typing helpers, Uvicorn, and Windows pywin32. Crypto/native Pydantic and HTTP dependencies can dominate the bundle. The app currently has requests and pywin32 but not this whole stack.
- The SDK’s own small wheel is **not the application size delta**. Budget roughly **10–40 MiB of added installed libraries per architecture** until measured; this is an estimate, not a resolved dependency tree or frozen build. Installer compression, already present libraries, PyInstaller hooks, and platform wheels change the result. [Release metadata][S14] [Release pyproject][S15]

| Option | Size/dependency tradeoff | Maintenance tradeoff |
| --- | --- | --- |
| Official SDK high-level server | More dependencies; small handlers and schemas; frozen import/native wheel validation required | Version compatibility, framing, validation, cancellation and HTTP support come from maintained code. Preferred. |
| Official SDK low-level server | Same declared package requirements; can make protocol surface explicit | Useful if high-level behavior is unsuitable. It does not automatically eliminate installed dependencies. |
| Hand-written stdio only | Potentially no additional runtime packages; perhaps tens of KiB of code, unmeasured | Must own discovery/legacy initialize, validation, errors, notifications, pagination, framing, UTF-8, cancellation, malformed/oversized inputs and future revisions. |
| Hand-written HTTP/OAuth | Dependency savings become doubtful | Much larger security and compatibility responsibility. Not recommended. |

Lazy imports improve startup but do not remove wheel requirements or prove reduced frozen size. Do not strip dependencies speculatively. Compare signed macOS and Windows artifacts, launch latency, peak memory, and dependency licenses before choosing. A zero-dependency server is a fallback only if the measured SDK impact is unacceptable and the team accepts ongoing protocol maintenance.

## 3. Client support and student onboarding, as documented today

**Compatibility below is documentary, not hands-on certification.** Version, plan, country, workspace policy, tool approvals and context limits all matter. A server cannot unlock a host’s unavailable plan feature. The student signs in to the AI client, never to an AI login form owned by Blackboard Sync.

| Client/surface | Local-only server? | Student setup and platforms | Subscription and limits |
| --- | --- | --- | --- |
| **Claude Desktop desktop extension/manual server** | **Yes, local stdio.** Do not use its remote connector URL form for localhost. | Install Claude Desktop, sign in, install Blackboard Sync, enable course access, then open a supplied .mcpb or paste generated config. Current Desktop supports macOS 13+, Windows 10+, Linux beta; Blackboard Sync delivery remains Mac/Windows. | Free chat exists; retrieved local-extension docs do not explicitly state a paid-plan gate. Validate Free tool access before promising it. Cowork requires a paid plan; organization policy can block extensions. |
| **Claude Code** | **Yes**, stdio or local HTTP; remote HTTP also supported. | Install official CLI, authenticate in it, copy a `claude mcp add --scope user` command; check `/mcp`. macOS, Windows native/WSL, Linux. A Desktop extension/import is another path. | Pro/Max and eligible organization plans, or separately billed developer access. Model usage is the client’s; MCP adds context and calls. |
| **ChatGPT desktop with local Codex host** | **Yes**, current docs explicitly support stdio and Streamable HTTP. | Desktop Settings → MCP servers → Add server → STDIO → command/args → Save → Restart. macOS, Windows, Linux are documented; verify the chosen distributed app/version. | Local Codex plan access applies. Current pricing lists Free/Go limited desktop access subject to rollout; paid plans have greater usage. No promise that every Free account has this capability. |
| **Codex CLI / IDE extension** | **Yes**, same local-host MCP configuration. | Install/sign in to official client; add with `codex mcp add` or app Settings. Mac/Windows/Linux host; remote/WSL executor must reach the actual data location. | Eligible ChatGPT usage or API billing configured in the official client. Desktop config does not imply cloud config. |
| **ChatGPT web custom MCP/plugin** | **No direct local process or localhost URL.** Public HTTPS or official Secure MCP Tunnel is required. | Browser → Plugins → plus → Add custom MCP server → HTTPS URL or Tunnel → auth/risk review → install → invoke with @. A laptop reader needs an ongoing bridge. | Full custom MCP documented for Business/Enterprise/Edu; Pro supports read/fetch. Do not advertise Plus/Free based on old snippets. Workspace creation/publishing permissions differ; mobile custom connection is not supported in the help article. |
| **Gemini CLI** | **Yes**, stdio, local HTTP and remote transports. | Install official CLI/runtime, sign in with Google, paste user-scope MCP entry or command, approve trust, inspect `/mcp`. Recommended OS currently macOS 15+, Windows 11 24H2+, Ubuntu 20.04+; Node >=20. | Google-account individual free quota is documented; AI Pro/Ultra and organization/API routes differ. No Gemini subscription is inherently required for the individual free route. Eligibility and regional terms still apply. |
| **Gemini consumer web/mobile apps** | **No documented local process or loopback connector.** Treat as remotely reachable MCP only; that reachability conclusion is an architectural inference. | Add server URL in web Settings → Connected Apps → Custom apps; complete account linking; use @. Connected app can then be used in web/mobile, but connection is created on web. | Retrieved help: 18+, US, personal Google Account, English, Keep Activity on; school/work accounts excluded. No paid-plan requirement is listed on that page; absence is not a universal entitlement guarantee. Not a solution to promise to Turkey-based students today. |
| **Gemini Code Assist agent mode** | **Yes**, documented local/remote MCP, notably through Gemini CLI on VS Code. | Install supported IDE/extension and sign in, then configure the Gemini CLI user settings file and enter agent mode. VS Code and IntelliJ have different capabilities/configuration. | Individual/organization Code Assist access and quota apply; preview limitations. It is a developer UI, not Gemini’s consumer chat. |
| **Gemini Enterprise** | Treat as a **remote endpoint** integration, not a laptop process launcher. | School/organization administrator configures a custom MCP connection/workflow in its cloud product. | Enterprise product access, administrator and network setup. Not the self-service first milestone. |
| **Cursor desktop** | **Yes**, stdio and local/remote HTTP. | Install Cursor, sign in, Customize → MCP or paste a personal mcp.json entry; later an Add-to-Cursor link. Mac/Windows/Linux downloads. | Free limited Agent usage and paid options exist. Exact model access/billing differs by current versus legacy plan; do not promise a particular subscription includes Claude/Gemini calls. |
| **VS Code with GitHub Copilot/local agent harness** | **Yes**, command stdio and HTTP. | Install VS Code/Copilot, sign in, MCP: Add Server → Command → choose personal destination → trust → enable tools in chat. Mac/Windows/Linux. Config depends on selected harness. | Copilot Free/paid or eligible student access is separate from MCP. Current setup offers free access; quotas and administrator policy apply. |
| **Cline IDE extension/CLI** | **Yes**, local stdio; remote supported. | Install Cline in editor, choose its provider, MCP Servers → Configure → add mcpServers entry. IDE host platforms apply; native Desktop is documented Mac/Windows beta but needs separate MCP validation. | Provider PAYG, ClinePass, or own provider/local access. No universal “your ChatGPT subscription works” claim. Keys, if used, stay in Cline. |
| **LM Studio/Bionic** | **Yes**, local and remote MCP. | Install, obtain a suitable tool-capable model, Program → Install → Edit mcp.json; Add-to-LM-Studio links also exist. Apple Silicon macOS 14+, supported Windows/Linux hardware. | Free local models are available; optional cloud inference is paid. Local model weights, RAM and tool-call quality are the student’s constraints; app name alone does not guarantee offline operation. |

Sources: [Claude install][S16], [local extension setup][S17], [connector distinctions][S18], [Claude Code MCP][S19], [Claude setup][S20], [local OpenAI MCP][S21], [desktop availability][S22], [Codex pricing][S23], [ChatGPT web help][S24], [web connection guide][S25], [Gemini MCP][S27], [installation][S28], [authentication][S29], [quotas][S30], [Gemini custom apps][S31], [Code Assist][S32], [Enterprise][S33], [Cursor][S34], [pricing][S35], [downloads][S36], [VS Code setup][S37], [MCP setup][S38], [Cline][S40], [installation][S41], [LM Studio][S42], [requirements][S43], [pricing][S44].

**Plain incompatibility statement:** Claude web/mobile, ordinary ChatGPT web custom connections, Gemini consumer web/mobile, and organization-hosted cloud agent containers cannot simply run this laptop’s stdio command. Remote access, a supported local-executor feature, or a bridge changes that boundary. Current ChatGPT desktop’s local Codex host is explicitly an exception; “ChatGPT never supports local MCP” is now false.

### ChatGPT private tunnel: useful but not the keyless shortcut

OpenAI’s Secure MCP Tunnel runs `tunnel-client` near the private MCP reader and connects outbound over HTTPS. It supports a local stdio or HTTP target and avoids public inbound ports. Setup needs a Platform tunnel ID, a **runtime API key**, organization permissions and the correct ChatGPT workspace association. It is for private connections/testing, not public plugin distribution. [Secure MCP Tunnel][S26]

Thus the reader can stay private, but the workflow is not “no credentials anywhere”: the external tunnel process owns an additional credential. Do not put that key in Blackboard Sync, silently install a tunnel, or advertise this as ordinary student one-click access. Public distribution needs a different supported endpoint arrangement. Sleeping/offline laptops cannot answer live calls.

## 4. Proposed read-only tool and resource contract

All names, argument examples, limits and file names in this section are **proposals**.

### Authorization before content

Create an explicit local MCP consent record, separate from sync settings. Default off, with a positively selected set of courses; newly discovered courses do not automatically gain AI access.

For every request compute:

~~~text
allowed = recorded_current_course_ids
          ∩ validated_current_course_catalog_ids
          ∩ sync_enabled_course_ids
          ∩ explicitly_MCP_allowed_course_ids
~~~

Validate settings/disabled/consent/state shapes and versions. A missing or corrupt consent record means no access. A malformed disabled-course file means authorization unavailable, not “all enabled.” Missing legacy current membership must not broaden to every output. Return “Open Blackboard Sync and sync/review access” without repairing files or contacting Blackboard.

Recheck permissions on each call and before returning a long read; invalidate caches/cursors when selection/root/state changes. Revocation stops future disclosures, including in already running subprocesses. It cannot retract text already in an AI conversation. Past terms need a later, distinct opt-in and catalog design; do not offer `include_all_terms=true` as an authorization bypass.

### Initial tools

| Tool | Proposed arguments | Result and important restriction |
| --- | --- | --- |
| `list_courses` | `cursor?, limit?` | Authorized current courses only: opaque course ID, code, title, term, snapshot freshness. No disabled-course names leaked in counts. |
| `list_announcements` | `course_id?, since?, cursor?, limit?` | ID, title, original timestamp, bounded preview, note ID, completeness. Filtering never expands authorization. |
| `get_note` | `note_id, cursor?` | Full approved Markdown text in bounded chunks, course/source metadata and stable citation URI. Follow recorded Markdown output key. |
| `list_deadlines` | `course_id?, from?, to?, cursor?, limit?` | Exact cached due instant with timezone, title, course and source ID; unavailable/stale flags; submissions not checked. No inferred deadlines or Calendar token/data access. |
| `search_synced_text` | `query, course_id?, cursor?, limit?` | Bounded literal/lexical search over authorized note/text sources; snippets, line ranges and IDs. No arbitrary regex/shell, embeddings API, URLs or recursive home scan. |
| `list_synced_files` | `course_id, cursor?, limit?` | Manifest-backed file IDs, safe display name, type, recorded size, availability and extraction support. No absolute machine paths. |
| `read_synced_file` | `file_id, cursor?` | First milestone: recorded UTF-8 text/Markdown only. Unsupported PDF/binary returns metadata and a clear limitation. Later: bounded extracted text with page citations, not opaque base64 megabytes. |

Tool descriptions must distinguish “read cached content” from “sync/check school.” No login, sync, shell, arbitrary HTTP, write-file, delete, submit-assignment, gradebook, email or Calendar tools. Model inference belongs solely to the client; do not request sampling to hide inference inside the server.

Use fixed author-written schemas/descriptions and read-only annotations such as `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true` and `openWorldHint=false` for offline reads. These are hints, not authorization or a claim that reading sensitive data is harmless. Course content must never become tool names or instructions. [Tools][S08]

Resources can expose the same guarded operations under a private namespace, for example `bbsync://courses`, `bbsync://notes/n_opaque` and `bbsync://files/f_opaque`. They are identifiers, not general filesystem URLs. Tool calls must work even if a client has weak resource support. Use private cache scope and short TTL for content, zero/disabled caching where consent changes need immediate effect; resource reads require the same guards as tools. [Resources][S09]

A later ChatGPT company-knowledge adapter may provide conventional `search`/`fetch` wrappers with its expected citation schema. Do not force that shape into every client: current ChatGPT custom-server help explicitly says those names are not universally required.

### Ownership, reads and output budgets

Build course ownership through validated `state.items` → output-key references and catalog folder mappings. Do not assume every attachment/embedded-file key encodes its owning course uniformly. Reject ambiguous/cross-course ownership. Only manifest-recorded regular files within the approved course root qualify.

Deny absolute paths, traversal, drive-relative Windows paths, UNC/device paths, alternate streams, case/Unicode tricks, symlink/reparse/junction escapes, FIFOs and devices. Resolve and verify containment at open time; avoid check-then-open races. A file ID is not sufficient authorization. Block private data directories even if destination settings overlap them. Do not follow shortcuts, archives, links or URLs.

Hidden files are normally excluded; the explicit exception is the exact recorded app-generated Markdown twin. Do not grant access to arbitrary dotfiles. Treat locally edited course files as untrusted material. Identify missing/cloud-only files without triggering automatic iCloud/OneDrive hydration where possible.

Never serialize state/settings wholesale. Exclude sessions, SSO/browser profiles, Blackboard cookies, passwords, MFA codes, provider keys/tokens, Calendar credentials/data, OS vaults, logs, crash dumps, environment/config dumps, account identifiers and signed/authenticated download URLs. Projected source links should be credential-free Blackboard navigation links or opaque URIs. Redact authentication query parameters from note links; do not fetch them. Pattern redaction is not a guarantee that a document contains no personal data.

Proposed starting budgets:

| Boundary | Initial value |
| --- | --- |
| Inbound JSON-RPC message | 1 MiB maximum; reject before unbounded allocation |
| Request query | 256 characters; fixed bounded parameters |
| List pages | Default 20, maximum 50 items |
| Search | Default 10, maximum 20 hits; <=500 characters per snippet |
| Note/file text chunk | <=16 KiB UTF-8; preserve complete code points and line/page metadata |
| Entire serialized tool result | <=64 KiB, including metadata and duplicate text representations |
| Text file eligible for initial scan | <=2 MiB; bounded total scan/work time |
| Work timeout | Approximately 5 seconds for cached queries; cancellation and bounded concurrency |
| Client lifetime disclosure budget | Consider a configurable 2 MiB session ceiling, with reset through the app |

These are server ceilings, not claims about host token/context limits. Count the actual encoded result, not just a string’s character count. Include `truncated`, continuation cursor, snapshot ID, source ID, line/page location and precise coverage; never silently omit content. Expired/snapshot-mismatched cursors require restarting the query. A malicious agent can enumerate chunks: per-call limits alone do not limit total disclosure.

Read state as a bounded validated snapshot; never take a writer lock that creates files, invoke migration, rename corrupt state, or call save/checkpoint. The existing `State.load(..., backup=False)` avoids renaming but can still normalize in-memory records and hide corruption; an export-specific strict reader gives clearer errors. Surface cached/last-known freshness, not “up to date” unless it can be established from permitted metadata. Do not read full last-run logs to obtain a timestamp.

## 5. Packaging, launch commands and setup examples

### Finding the right data and content folders

Reuse `default_data_dir` and Config’s documented precedence for trusted launch configuration:

- macOS: the macOS Application Support data directory.
- Windows Setup: the Windows Setup roaming AppData directory.
- Windows Store/MSIX: `%LOCALAPPDATA%\Packages\<package-family>\LocalCache\Roaming\blackboard-sync`, deliberately isolated from Setup data.
- The content root comes from saved destination and `sync_root`. Windows Documents can be redirected into OneDrive; custom destinations are legitimate.

Generate an explicit absolute `--data-dir` argument from the running app’s actual profile, particularly for Store or multiple installations. Treat it as a trusted startup argument, never a tool argument. Avoid blindly inheriting `BBSYNC_DEST`/`BBSYNC_DATA_DIR` overrides from another host: show and validate the effective profile. A copied standalone Store helper can lose package identity and choose Setup’s data; “same Windows user” is not enough.

**Store uncertainty:** the manifest has no app execution alias today. A future stable alias/registered launcher must preserve stdio, find the current package version, and select the correct consent/data profile. Do not tell students to copy a versioned WindowsApps path or take ownership of that directory. Ship Store onboarding only after a packaged update/reinstall test establishes this.

### Installed-app entry point

Proposed source command:

~~~text
blackboard-sync --data-dir "/absolute/private/profile" mcp --transport stdio
~~~

Keep this process separate from the normal sync writer. It can serve cached content while the GUI is closed, but the saved MCP switch/allowlist still controls access. Lazy-import MCP only for that subcommand, and do not call `open_client`, load a saved session, refresh cookies or start Playwright. Reuse the current CLI parser where useful, but dispatch the read-only path before auth/network-heavy imports.

The Mac client should launch the app executable directly; `open -a` is not a stdio bridge. Windows clients should launch the console twin directly with argv arrays, not a shell string. Verify stdout/Unicode behavior in both frozen artifacts.

### Settings flow

Proposed Settings → “Connect your AI”:

1. Explain what is shared and that the chosen AI may send it to its provider; normal sync works independently.
2. Select authorized current courses. Show the exact profile and a safe example of exposed notes.
3. Select client: Claude Desktop, ChatGPT desktop/Codex, Gemini CLI, other. Show supported-platform/plan caveats.
4. Offer “Open extension,” “Copy setup,” or an explicit “Configure this client” action. A configuration helper merges only this server entry, preserves other entries, validates syntax, and provides an undo path. Never silently replace a client’s file.
5. Test local server discovery with synthetic/no-content status. Reading a real course for a client test requires the already chosen scope.
6. Show “Enabled for 3 courses,” last successful local connection, “Review shared content,” and “Disable access.” Do not call the external AI “connected” merely because the server starts.

A setup button can run the documented client configuration command after the user chooses it; this is a deliberate local settings change. It must not install unrelated clients/runtimes or modify their global tool permissions.

### Configuration snippets

**Proposed commands: they do not work in today’s app because the mcp subcommand does not exist.** Replace example paths with detected absolute paths. Preserve other server entries. No sample requires an AI key.

Claude Desktop Mac, in the existing Desktop config:

~~~json
{
  "mcpServers": {
    "blackboard-sync": {
      "command": "<BLACKBOARD_SYNC_EXECUTABLE>",
      "args": [
        "--data-dir", "<APP_DATA_DIR>",
        "mcp", "--transport", "stdio"
      ]
    }
  }
}
~~~

Desktop config locations: the platform-specific Claude Desktop configuration file. Restart Claude after manual setup. For Windows Setup replace the server entry with:

~~~json
{
  "command": "<BLACKBOARD_SYNC_EXECUTABLE>",
  "args": [
    "--data-dir", "<APP_DATA_DIR>",
    "mcp", "--transport", "stdio"
  ]
}
~~~

Use fully expanded paths; do not assume every JSON client expands shell variables or `~`. [Manual local-server configuration][S45]

Claude Code Mac:

~~~sh
claude mcp add --transport stdio --scope user blackboard-sync -- \
  "<BLACKBOARD_SYNC_EXECUTABLE>" \
  --data-dir "<APP_DATA_DIR>" \
  mcp --transport stdio
~~~

ChatGPT desktop: use Settings’ STDIO fields above. Codex CLI equivalent:

~~~sh
codex mcp add blackboard-sync -- \
  "<BLACKBOARD_SYNC_EXECUTABLE>" \
  --data-dir "<APP_DATA_DIR>" \
  mcp --transport stdio
~~~

Or merge into the local host’s the Codex user configuration file:

~~~toml
[mcp_servers.blackboard-sync]
command = "<BLACKBOARD_SYNC_EXECUTABLE>"
args = ["--data-dir", "<APP_DATA_DIR>", "mcp", "--transport", "stdio"]
~~~

Gemini CLI: merge the same `mcpServers` JSON shape as Claude’s example into the Gemini CLI user settings file, then verify `/mcp`. A user-scope `gemini mcp add` helper is possible; use the installed CLI’s documented flag parsing rather than assuming Claude’s syntax. An optional Gemini extension can package the server definition later; installing an extension from a repository is not necessary for milestone one. [Gemini MCP][S27] [Extensions][S46]

Cursor: use the same `mcpServers` object, add `"type": "stdio"` where its schema requires it, and place it in the personal config selected by Customize → MCP. LM Studio uses Cursor-style notation through its editor. Cline adds `"disabled": false, "autoApprove": []` to the local entry. Keep auto-approval off initially.

VS Code’s native format differs:

~~~json
{
  "servers": {
    "blackboard-sync": {
      "type": "stdio",
      "command": "<BLACKBOARD_SYNC_EXECUTABLE>",
      "args": [
        "--data-dir", "<APP_DATA_DIR>",
        "mcp", "--transport", "stdio"
      ]
    }
  }
}
~~~

Use MCP: Add Server for the correct personal/harness destination. Current Copilot portable configs use `mcpServers`, whereas native VS Code profile/workspace configs use `servers`. Do not commit a student’s machine path to a shared repository. [Configuration reference][S39]

**ChatGPT web and Gemini consumer app have no equivalent local JSON snippet.** Their future form would contain an authenticated remotely reachable `https://<host>/mcp` URL, or ChatGPT’s explicit tunnel selector. Do not supply `http://localhost` and imply it works from the provider’s cloud.

### Claude Desktop one-click extension

Use **.mcpb**, the current name replacing .dxt; older .dxt bundles still work. Bundle a manifest with identity, version, compatibility, privacy URL and server configuration. Desktop can install by opening the package or Settings → Extensions → Advanced → Install Extension; directory review is a separate publication step. Directory extensions can auto-update; private bundles need manual updates. [Anthropic overview][S47] [Install/update behavior][S17]

For this app, prefer a tiny launcher adapter using Claude’s supplied Node runtime, or a small signed binary launcher, that locates the installed Blackboard Sync and forwards stdio. Its input is a non-secret installation/profile selection. Avoid bundling another Python interpreter or a full copy of the application. The MCPB manifest supports Node, Python, binary and platform metadata, but the installed-app adapter design and directory acceptance still need testing; it is not a pre-existing packaged integration. [Manifest specification][S48]

If the app is absent, display a download instruction and stop. Never download an unsigned executable automatically. Keep the adapter and server’s minimum versions compatible. A self-contained Python MCPB is possible but duplicates runtime/libraries and complicates update ownership.

### Updates and Inspector

Use stable installation locations; resolve Store versions through a supported launcher. New server code takes effect on the next process launch. On Windows Setup updates the current installer stops both GUI and CLI; surface a reconnect/restart state. Preserve consent across compatible updates, and require renewed consent for expanded permissions. Keep tool names and required arguments stable; ChatGPT web workspace approvals can retain a frozen tool snapshot until refreshed.

For development, use the current **MCP Inspector** on synthetic fixtures. Its current docs require Node >=22.19.0, newer than Gemini CLI’s minimum. Do not bundle Inspector or Node just to serve this Python MCP endpoint. [Inspector][S49]

~~~sh
npx @modelcontextprotocol/inspector \
  "<BLACKBOARD_SYNC_EXECUTABLE>" \
  --data-dir "/absolute/synthetic-fixture-profile" mcp --transport stdio
~~~

Pin the Inspector version in actual development/CI after verification. Test tools/resources, schemas, malformed inputs, refusal paths, both protocol eras, cancellation and real frozen executable pipes. A localhost HTTP test later uses the authenticated Streamable HTTP selector. Keep Inspector’s own auth/proxy protection enabled; it is a developer tool with local execution authority.


## 6. Dedicated design brief: a real embedded terminal that feels welcoming

### What this route actually hosts

The process chain would be:

~~~text
Blackboard Sync window
  └─ local terminal renderer + narrow native bridge
       └─ OS PTY / Windows ConPTY
            └─ user's installed official Gemini CLI / Claude Code / Codex
                 ├─ provider login, token refresh, inference, approvals and history
                 └─ MCP client → Blackboard Sync read-only stdio reader
~~~

**Yes, this can avoid making a student operate a separate terminal window.** The terminal pane is a real terminal, with a controlling PTY, dimensions and input/output streams, running the official interactive client. A plain text widget connected to subprocess pipes does not reproduce a full-screen CLI reliably.

The application owns the outer presentation, process lifecycle and approved course exporter. The CLI continues to own model access and its own credentials. It remains recognizable as “Gemini CLI in Blackboard Sync,” not a claim that Blackboard Sync is an official Gemini/Claude/ChatGPT client. This route needs no direct inference API in the app.

**Recommended position:** keep “open your own GUI client” as the supported fallback and make the embedded terminal the first UX experiment after the MCP boundary exists. The requested integrated experience is technically plausible. Its success depends on whether a real CLI can feel good without hiding essential controls, and whether each vendor permits this distributed use.

### Hosting architecture on macOS and Windows

| Layer | macOS | Windows |
| --- | --- | --- |
| Terminal process host | Unix PTY via a small dedicated helper using openpty and a safe spawn strategy | Native Windows ConPTY, directly or through a maintained binding such as pywinpty |
| Rendering | WKWebView with locally bundled xterm.js; app already has PyObjC/WebKit dependencies, but the existing Mac main UI is native | Dedicated pane/window in the existing WebView2/pywebview UI, with locally bundled xterm.js |
| Native bridge | A small explicit message handler: input bytes, resize, readiness, lifecycle, safe links | Existing bridge extended narrowly for the terminal channel; no general eval or arbitrary process endpoint |
| Main-thread work | Native view/layout and batched render updates only | WebView UI and event dispatch only |
| Worker work | PTY read/write queues, subprocess management and bounded buffering | Separate I/O servicing and process management; never block UI on pipe reads |
| Shutdown | Graceful CLI interruption/exit, then bounded cleanup of the owned process group | Close input/graceful exit where supported, then owned-process-tree cleanup; avoid affecting external sessions |
| Store concerns | Hardened runtime/signing and TCC file access must be tested | MSIX subprocess/runtime policy and package identity/path must be tested with the installed CLI |

Python’s PTY module is Unix-only and explicitly warns against mixing macOS fork usage with higher-level system APIs. Do not call a naive `pty.fork()` loop inside the AppKit/PyObjC GUI. Isolate terminal setup in a purpose-built helper or use a tested safe PTY/spawn library. [Python PTY][S50]

ConPTY is Windows’ supported pseudoconsole mechanism. The host creates communication channels and the pseudoconsole before the client process, supplies dimensions, services the streams, and resizes it as the pane changes. Microsoft warns about deadlocks when synchronous channels are not serviced correctly. Older Windows behavior and pywinpty compatibility require real tests, not POSIX emulation assumptions. [Microsoft ConPTY][S51]

Prefer **native Windows CLIs first**, not a silent WSL installation. WSL has different paths, homes, installed clients and credential stores. A Windows app’s MCP executable and data paths may not be directly usable from a Linux-side MCP configuration. Support WSL later with an explicit, tested bridge.

Use the same local xterm.js assets on both platforms to reduce UI divergence. This does not require Electron, Chromium, a Node renderer process, or a Node server. The JavaScript runs inside WKWebView/WebView2; Python/native code owns the PTY. Gemini CLI itself still requires its documented runtime. A fit addon computes rows/columns; the bridge propagates resize and handles high-DPI changes.

**Native alternatives:** a native terminal component can improve OS accessibility or avoid a browser bridge, but it adds platform-specific dependencies and terminal-emulation maintenance. A basic AppKit text view/Tk text widget is not an adequate replacement for cursor movement, alternate screens, Unicode widths and bracketed paste. A separate external Terminal/Windows Terminal window is the smallest fallback, but it does not satisfy the desired integrated experience.

### Dependency and size impact

Keep AI clients user-installed for the first version. Do not bundle three CLIs and their runtimes merely to save onboarding steps.

Registry metadata retrieved for this research provides useful scale, not frozen app deltas:

| Component | Measured metadata, 2026-10-22 | Interpretation |
| --- | --- | --- |
| `@xterm/xterm 6.0.0` | npm package unpacked size **5,921,599 bytes** | Includes more than production JS/CSS. Bundle only licensed runtime assets/addons; expect a low-single-digit MiB contribution, to be measured. |
| `pywinpty 3.1.0`, CPython 3.12 Windows x64 | Wheel **2,105,451 bytes compressed** | Native binding option for Windows. Installed/native DLL and frozen size differ. Direct ConPTY reduces wrapper dependencies but increases native code responsibility. |
| `agent-client-protocol 0.12.1` | Wheel **85,929 bytes compressed**; Pydantic dependency | ACP library itself is small; it is not needed for the PTY route. |
| `@google/gemini-cli 0.65.0` | npm package unpacked size **98,737,043 bytes** | Already far larger than a renderer; Node/platform/runtime/installation totals are separate. |
| `claude-agent-sdk 0.2.172` | Mac arm wheel **115,999,146 bytes**, Mac x64 **121,683,387**, Windows x64 **129,519,248**, compressed | Bundled agent runtime makes this quite different from the small MCP SDK. It is not needed to host the user’s CLI. |
| `@openai/codex-sdk 0.163.0` | Package **80,303 bytes unpacked**, depends on `@openai/codex 0.163.0` | The wrapper’s small size excludes the actual CLI/native payload and Node runtime. |

Sources are versioned/public package metadata [S52–S57]. No terminal bundle, CLI payload, or app build was installed to measure total disk use. Do not add compressed wheel bytes to unpacked npm sizes and call it an installer total.

The Mac app already depends on WebKit; Windows already uses WebView2. The extra renderer/PTY binding can therefore plausibly stay modest. A future build spike must compare DMG/Setup/MSIX size, native signing, launch memory and cold start. Bringing bundled official clients raises update, license, redistribution and security-response responsibilities; it is deliberately deferred.

### A polished chat-like design without corrupting terminal semantics

Use an “Ask about your courses” destination in the app, not a generic developer console. Suggested layout:

~~~text
[Gemini CLI ▾]   Using your Google account      [Open externally]
3 courses shared · Current term · Cached at 13:40     [Manage]

What would you like to review?
[Summarize this week's announcements]
[What deadlines are coming up?]
[Help me review lecture notes]

┌ terminal pane, themed and framed as the conversation ┐
│ official client output, input and approval UI        │
└─────────────────────────────────────────────────────┘
[Copy selection] [Find]                  [Stop] [New session]
~~~

This is a design brief, not a rendered/implemented screen.

- **Header:** name and icon of the actual client, selected model when reliably known, and account status without exposing an email by default. Include “Your AI client runs locally; its provider may receive shared course text.” Distinguish client installation, login, MCP readiness and inference connectivity.
- **Course status:** an app-owned chip saying “3 courses shared” opens the actual allowlist. Show enabled current term and cache freshness from the exporter. “Connected to course data” requires a successful MCP handshake/tool discovery or observed reader session, not detecting that a CLI binary exists. Avoid claiming the CLI has no other tools.
- **Theming:** map the terminal ANSI palette, background, foreground, selection and cursor to app light/dark settings. Configure the official CLI’s supported theme separately where needed. Dark terminal output embedded in a light app should be an intentional option, not an accidental mismatch. Contrast must survive CLI hard-coded colors.
- **Chrome:** hide shell tabs, path breadcrumbs, command shell prompts and developer-only controls around the terminal. Start the official executable directly, not an interactive shell. Preserve the CLI’s own model/permission/status lines and prompts. Cropping out its warnings or replacing its approval controls would be misleading.
- **Typography:** readable monospace, comfortable line height, zoom, high-DPI fit and generous padding. Test Turkish dotted/dotless letters, emoji, double-width characters, wrapped Markdown tables and long source titles. A proportional-font transcript would require a structured protocol rather than a terminal.
- **Starter prompts:** buttons insert an editable question into the official prompt. They should not execute on selection. Do not inject keystrokes while the CLI is displaying login, a permission dialog, slash-command picker or other full-screen mode. The first prototype may place prompt text on the clipboard with a clear “Paste into client” action instead of pretending it knows the CLI’s input state.
- **Input:** retain terminal keyboard behavior, IME composition, paste and history. A second app-owned chat composer is risky without a reliable “ready for prompt” signal. If later added, use bracketed paste, explicit Send, a tested state machine and a visible fallback to direct terminal input; never synthesize hidden Enter or click “approve.”
- **Selection and copy:** Cmd+C copies a selection on Mac; otherwise Ctrl+C retains its documented interrupt meaning. Windows offers Ctrl+Shift+C/context-menu copy without breaking interrupt. Make multiline copy predictable and strip presentation escape codes, not content. Do not automatically copy output, prompts, device codes or clipboard contents.
- **Scroll:** preserve the student’s position when reading earlier output; show “New output” and “Jump to latest.” Full-screen alternate-buffer CLIs may not preserve a transcript in terminal scrollback. Test this early; do not promise a complete export based on screen scraping.
- **Stop/new session:** Stop sends the appropriate official interrupt, visibly waits, and offers force-stop only for the owned session if needed. New session confirms whether the current turn will end. Closing the pane should not leave invisible model jobs running; use an explicit keep-running state if eventually supported.
- **Source links:** prefer an app-owned Sources panel populated from MCP responses/opaque source mappings. Clicking a source resolves and revalidates its file ID, then opens only that approved file. Do not depend on a CLI displaying custom resource URIs as hyperlinks.
- **Terminal links:** xterm supports OSC 8 and optional URL detection. Treat every target as untrusted; allow http/https externally after validation, never execute `javascript:`, shell, custom process URLs or arbitrary `file:` paths. App-generated source links are the only local-file opener. Do not turn model-printed paths into unrestricted native bridge calls. [Link handling][S58]

The presentation can be warm and approachable while remaining a terminal. It cannot reliably turn every CLI redraw into clean assistant/user bubbles. If that visual constraint proves decisive in user testing, switch to section 7’s structured interfaces rather than layering more terminal-output parsing.

### First-run onboarding: no secret collection

1. **Choose client.** Briefly compare availability, expected plan, platform requirements, inference recipient and independent installation. Let users keep their existing provider. Do not imply paid Claude Code is the only option.
2. **Detect installation safely.** Search documented standard executable locations and PATH; allow the user to select an official executable. Frozen GUI apps often have a restricted PATH, so a failed PATH lookup is not proof of absence. Resolve the chosen executable, show its publisher/location, and run only `--version` under a timeout. Never recursively search private homes or credential directories.
3. **Not installed.** Show “Install Gemini CLI/Claude Code/Codex,” official instructions and “Check again.” A future installer helper can offer a reviewed, explicit installation flow, but do not silently pipe a remote script into a shell, request admin rights, install WSL, or choose billing for the student. Show Node requirements for Gemini; native Claude/Codex distributions can avoid an extra Node dependency where their official installers support that.
4. **Check sign-in through the client.** Claude documents `claude auth status` with JSON and exit status; Codex documents `codex login status`. Parse only documented non-secret status fields and discard output after use; never display raw diagnostics or a partial API key. If a version’s status output can include secrets, do not capture it—use a safer documented account-status surface or user-visible official login. [Claude CLI reference][S59] [Codex authentication][S60]
5. **Gemini status uncertainty.** The retrieved docs establish browser sign-in and cached-auth reuse but not a universal non-inference “auth status” command. Do not invent one, peek into its OAuth cache, or send a course question to test login. Show “Open Gemini to finish setup,” let its own initial UI/browser flow determine readiness, and offer a user-confirmed tiny no-course test only if necessary. [Gemini authentication][S29]
6. **Sign in externally first.** Launch the official client/login flow in its external window and the system browser, then return to Blackboard Sync. Browser callback, token persistence and refresh remain wholly owned by that client. Do not embed provider login websites, intercept OAuth redirects, read the vault, proxy model requests, or copy tokens into app config.
7. **Grant course access.** Select current enabled courses and preview what MCP can return. Explain that existing client tools/history may have their own permissions beyond this connection.
8. **One-click MCP setup.** Show the exact server name, app/profile and permission summary. Run the official configuration command or merge the documented user entry atomically. Preserve other entries and provide undo. For an app-hosted session, prefer a documented scoped server config where available, but do not relocate/copy the client’s auth home to invent isolation.
9. **Verify data connection without inference.** Verify local server discovery on synthetic status and that the CLI lists the configured server. Launch the official client in the terminal, retain its approvals, and offer an editable starter prompt. A benign real course read occurs only after the student has enabled the scope.
10. **Return use.** If login expires, stop safely and show “Sign in again in Gemini/Claude/Codex.” No automatic API-key fallback, account switch or credit purchase.

The truthful promise is **“Blackboard Sync never intentionally reads, stores, refreshes or forwards your AI credentials; your official client manages them.”** A same-user desktop process is not an OS-enforced credential isolation boundary. A terminal host necessarily handles displayed input/output; if a user pastes a key or a CLI prints a secret, those bytes traverse the host. External sign-in, no raw session logging, no key-entry UI and verified status schemas are therefore part of the design. An absolute claim that the host could never observe any token byte would be false.

### Permission and injection boundaries of the embedded CLI

Read-only MCP does not make a general coding agent read-only. Official CLIs can carry shell, filesystem, web, plugin and project-instruction capabilities. An announcement could ask them to read the saved session through another tool.

- Start in a neutral app-owned workspace, not the private data folder or an entire course root. Do not give automatic folder-wide access just to establish MCP.
- Use each client’s documented tool restrictions/sandbox/approval settings to make the course server the intended content channel. Keep shell, arbitrary file reads, web tools and extra plugins disabled or denied where a restricted study mode is promised.
- Do not bypass permission dialogs, auto-approve everything, or set dangerous flags for a prettier demo. A read-only filesystem sandbox can still permit reading secrets; it is not automatically a confidential-data sandbox.
- Do not silently erase the student’s existing global client configuration. Prefer documented per-launch scope and explain when global tools remain active.
- Confirm handling of project instruction files, hooks and persistent memory. Merely launching in the course directory can import attacker-controlled instructions.
- If a provider’s interactive client cannot be confined sufficiently, label the pane as that general-purpose client and keep it an advanced option; do not advertise an enforced safe study agent.

The app’s view should show both the exporter’s narrow course scope and the fact that client permissions are separate.

### Accessibility and webview security

Enable xterm’s screen-reader mode and test **VoiceOver on macOS and NVDA on Windows**; the option exposes supporting DOM elements, but the CLI’s full-screen redraw behavior can still be difficult. Provide accessible native/DOM labels for header/status/actions, predictable Tab navigation and a way to leave terminal focus. Respect zoom, high contrast, reduced motion, cursor-blink preferences and language. Do not announce every streamed token or spinner redraw. [xterm options][S61]

Support keyboard-only setup, approval, source opening, copying, stopping and reconnecting. Do not rely on color alone. Test IME and composed input, text selection while output arrives, resize during a permission dialog, and user font scaling. If terminal accessibility fails, retain external-client access and consider a structured transcript interface. A hidden inaccessible text clone of screen-scraped output is not a sufficient fix.

Bundle renderer scripts/fonts locally, use a restrictive CSP, and keep the terminal in its own trusted view/context. No remote images, ads, live documentation scripts or unsanitized Markdown share the terminal’s scripting context. The bridge only accepts bounded input/resize/source operations for the owned process. Never expose “run command” to arbitrary web content. Disable unsolicited clipboard/window-control escape behavior. [xterm security guidance][S62]

### Fast prototype and acceptance criteria

**Prototype first, before designing a multi-provider chat architecture:**

- 0.5–1 day: local xterm pane in both actual GUI stacks; run a harmless local echo/test process in a real PTY/ConPTY; verify input, resize, UTF-8, selection and shutdown.
- A further 0.5–1 day: launch one already installed, externally authenticated official CLI; use synthetic course MCP fixtures and a tiny user-authorized test. No token inspection or redistributed client.
- Show light and dark themes, narrow/wide windows, starter prompt insertion, a real tool approval and a clickable approved source.
- Evaluate whether the terminal feels comfortable for a nontechnical student, including keyboard/screen-reader access. Record startup latency, flicker, input-state ambiguity, scrollback and cancellation behavior.

Success means no external terminal is needed for normal questions after setup; the student can identify the actual client, shared courses and recipient; source links and copy work; permissions remain visible; no extra secret or unsafe tool permission is required. Failure means repeated broken layouts, hidden approvals, unusable accessibility, unreliable prompt injection into the input field, uncontrollable built-in tools, or vendor restrictions. A failed feel prototype should change the UX route, not weaken security.

Planning estimate after that prototype: **10–18 engineer-days for one polished official CLI on both OSes**, including onboarding, terminal bridge lifecycle, access controls, themes, accessibility, safe links, packaged builds and documentation. Supporting all three at comparable quality can add **5–10 days** plus vendor-specific review time. This is additional to the MCP foundation; shared UI/security work overlaps.

## 7. Other embedding routes, SDKs and vendor permission

### Short comparison against the real terminal

| Route | Installation/sign-in and credentials | UX/engineering | Ranking for this request |
| --- | --- | --- | --- |
| **Student opens their own GUI client + MCP** | Install/sign in there; Blackboard Sync never hosts AI auth or output | Lowest maintenance; familiar official UI; client-specific onboarding | **Production baseline and fallback.** Already avoids terminals for desktop-client users. |
| **Real embedded PTY official CLI** | User installs and signs in to CLI first; app hosts terminal bytes, not tokens/auth files | Strong integrated experience if prototype succeeds; inherits CLI UI/approvals | **First integrated UX experiment**, as the first integrated UX experiment. |
| **Official CLI headless subprocess + own chat UI** | Same official installation/cached sign-in; read structured events only | More control of transcript; own session, cancellation, approval and error UX | Good for bounded jobs; interactive chat needs richer protocol. Approx. **8–14 days** for one-provider bounded UI, **12–20** for a robust chat. |
| **ACP-hosted agent** | Official Gemini CLI can remain agent; Claude/Codex generally need adapters | Structured sessions/events/permissions; less terminal parsing, more protocol/state work | Strong later alternative if terminal presentation/accessibility is insufficient. Approx. **12–20 days** for first provider, **5–10** more for adapters. |
| **Official SDK/App Server** | Agent runtime owns auth only in supported managed mode; direct API SDKs need keys | Provider-native control but packaging/terms differ; not a universal embeddable chat widget | Prefer an official protocol when own-chat UI is truly needed; avoid duplicating large runtimes initially. |

Effort estimates include two-platform UI/security work, overlap, and exclude the common MCP server. These are not promises that subscription-based distribution is authorized.

### Headless CLI specifics

- **Claude Code:** official `claude -p` supports JSON and newline-delimited `stream-json` output, partial streaming, resumption and permission mechanisms. It is not a terminal UI under pipes. Build against documented events, not ANSI scraping; review permission denials and end-of-turn errors. [Programmatic Claude][S63]
- **Gemini CLI:** official headless mode is entered by a prompt flag or non-TTY input and offers JSON/JSONL events. Its auth guide explicitly says headless can reuse existing cached authentication; a fresh headless environment otherwise needs an appropriate configured method. Never read/copy that cache into Blackboard Sync. [Headless reference][S64] [Authentication][S29]
- **Codex:** `codex exec --json` produces event JSONL and reuses saved CLI auth. It defaults to a read-only sandbox; that is not an assurance of secret-file confidentiality. Session persistence, resumes and ephemeral mode need an explicit choice. Use app-server for bidirectional approvals/custom clients rather than trying to reconstruct them from final output. [Non-interactive mode][S65]

Headless adapters should send prompts via supported stdin/protocol fields rather than putting private course text in process argv. Preserve cancellation and errors; a killed process does not guarantee usage is unbilled. Never use unattended “approve all” to avoid building an approval UI. Own-chat mode also makes Blackboard Sync receive/display generated content, changing its privacy/store posture.

### ACP: different direction from MCP

**MCP connects the agent to course tools; ACP connects Blackboard Sync’s UI to the agent.** They can be used together. ACP defines sessions, prompts, streamed updates, permissions, cancellation and optional editor filesystem/terminal services. Current ACP docs label v1 latest and v2 draft. The Python library provides schema models and JSON-RPC plumbing, so Python need not bundle a Node-based ACP host. [ACP introduction][S66] [Python SDK][S67]

Gemini CLI officially documents `gemini --acp` for programmatic IDE/developer integrations. Earlier examples using an experimental flag should not be copied blindly. The docs’ informal handshake description and precise ACP versioned schemas should be reconciled during implementation. [Gemini ACP][S68]

The ACP agent list identifies Claude Agent via a **Zed/ACP SDK adapter** and Codex via an **ACP adapter**; these are not native provider ACP implementations. The Codex adapter can depend on a bundled compatible Codex package, adding another update/version boundary. Inspect its auth mode and code before promising tokens stay outside every third-party component. [Agent catalog][S69] [Claude adapter][S70] [Codex adapter][S71]

ACP can let the agent own login through its advertised authentication method; terminal login requires the host to advertise support. Choose agent-owned sign-in and reject any host-managed-token option. A protocol does not guarantee an adapter never reads credentials, nor does declining editor filesystem capabilities remove the agent’s own built-in tools. [ACP authentication][S72]

### Official embeddable offerings

**No retrieved documentation offers a universal drop-in official consumer chat widget** that embeds the Claude/ChatGPT/Gemini website and automatically spends the student’s subscription. Do not iframe or automate those websites.

- **OpenAI:** Codex **App Server** is expressly designed for custom clients, with streamed turns, approvals, history and managed authentication over a subprocess protocol. Managed ChatGPT mode lets Codex own OAuth persistence/refresh. **Do not use external `chatgptAuthTokens` mode:** that explicitly requires the host to supply/refresh tokens. For this Python app, speaking app-server directly avoids the TypeScript SDK’s Node wrapper. [App Server][S73]
- **OpenAI SDK:** the official Codex SDK is a TypeScript library requiring Node and a Codex dependency. It controls local agents; App Server is the more appropriate rich-client interface. The removed `codex mcp-server` command is not an embedding strategy. [Codex SDK][S74]
- **Anthropic:** the Claude Agent SDK officially supports Python/TypeScript and runs the Claude Code agent binary. It is a real embedding library, not the consumer Desktop UI. Its standard public-app authentication guidance requires API keys unless approved otherwise; that conflicts with this project’s no-key objective until clarified. Its large platform wheels are quantified above. [Agent SDK][S75] [Python reference][S76]
- **Google:** the official CLI’s ACP/headless interfaces are the clearest documented way to keep the CLI as client. A public Gemini Code Assist subscription-delegating Python SDK for this consumer app was not established. Google model SDKs are direct inference APIs, not an embeddable authenticated Gemini consumer client.

### Provider terms: launching an executable is not credential delegation

| Provider | Positive evidence | Limit / interpretation for Blackboard Sync |
| --- | --- | --- |
| **Google** | Official Gemini CLI offers headless and ACP programmatic integration; software is Apache 2.0. | Its terms page expressly prohibits third-party software directly accessing the services powering Gemini CLI with CLI OAuth. Running the unmodified official CLI via documented modes is materially different from extracting its token and recreating requests. This is the defensible technical route, but the retrieved docs are framed around coding/developer integrations, not a blanket approval for every public study app. Recheck service eligibility/use and branding before distribution. [Terms][S77] |
| **Anthropic** | Official headless interface and Agent SDK exist; current help says SDK, claude -p and third-party usage can still draw subscription limits. | SDK docs say unapproved third-party developers may not offer claude.ai login/rate limits in their products; account guidance directs products for others to API keys and prohibits identity spoofing/routing around limits. A terminal wrapper is not an established exemption. Keep external Claude MCP support; seek explicit permission before marketing an embedded subscription-funded Claude experience. [SDK guidance][S75] [Plan help][S78] [Account policy][S79] [Consumer Terms][S80] |
| **OpenAI** | Official app-server/SDK explicitly enable custom integrations and a managed-auth mode. | App-server auth guidance allows existing local/open-source applications to continue but says commercial/hosted use was never permitted; it recommends Sign in with ChatGPT. That recommended direct-token route would put auth in the host and is outside this task’s strict boundary. Confirm applicability to a **new** public MIT/local app before promising managed subscription use. Do not infer permission for paid/hosted redistribution. [App Server auth][S73] |

These are documented allowances and limitations with marked interpretation, not legal clearance. Software licenses do not override service/account terms. User-installed binaries avoid redistribution work but do not settle vendor permission for the hosted experience. Do not rename client identity/user-agent, copy another client’s credentials, share accounts, or proxy other students through one login.

## 8. Security, privacy, academic integrity and Store treatment

### Prompt injection and cross-tool exfiltration

Course files/announcements are untrusted data, even when downloaded from a real school. They may include “ignore previous instructions,” credential requests, malicious URLs, embedded HTML, or instructions aimed at other connected tools.

The MCP server should return source text clearly labeled as data with fixed provenance, never interpret it as configuration, never execute it, and never follow its URLs. Keep schemas fixed; validate input, response size and output rendering. Do not allow dynamic tools from course titles. Client annotations and a system instruction to ignore injected commands help but are insufficient. [MCP security guidance][S07]

The crucial residual risk is **other host tools**. A malicious course could induce a client with shell/email/filesystem access to steal data outside this exporter. The exporter can enforce its own scope but cannot police the rest of a general-purpose host. Explain this in setup and test restricted host modes. For embedded clients, do not claim a safe study-only boundary unless tool/sandbox controls actually enforce it.

### Any future local HTTP endpoint

Require all of the following as part of the implementation, rather than relying on “localhost” branding:

- Bind loopback only; no LAN/public listener or automatic firewall exception. IPv6 loopback is optional only if deliberately implemented/tested.
- Authenticate every request; use a random separate local connection credential or a compatible authorization flow. Never reuse a Blackboard cookie or AI key. Store connection secrets privately and keep them out of URLs, logs, transcripts and argv.
- Validate Origin and Host, reject invalid browser origins/DNS rebinding, use restrictive CORS, and protect state-changing pairing/settings separately from the read-only API.
- Check content type/method, body limits, request timeouts, concurrency, protocol/header consistency, token audience and scope. A legacy session ID is not authentication.
- Rotate/revoke connection authorization on disable and profile changes; test an already-connected client after revocation.
- If a remote bridge is later added, add per-user identity, tenant isolation, HTTPS and egress controls. Never blindly pass an upstream token through to Blackboard.

The protocol’s HTTP security requirements explicitly call out Origin checks, loopback binding and authentication. [Streamable HTTP][S05] [Authorization][S06]

For stdio, retain normal OS user permissions and signed app distribution. No connection credential is intrinsically needed. Another process running as the same user is outside the protection offered by the app’s logical file allowlist; a separate sandboxed exporter process could strengthen that boundary later.

### Required public copy

Before release, update English and Turkish Settings/help, website/privacy, README and Store listing. Reuse the earlier research’s disclosure locations and Calendar restrictions; replace key-based phrasing with MCP-specific facts.

Suggested exporter copy:

> Optional AI connections are off by default. When enabled, your chosen AI client can read the currently enabled courses you explicitly share, including their synced notes, announcements and cached deadlines. The connection runs locally, but the AI client may send this content to its provider under that client’s account and privacy settings. Blackboard Sync does not receive or store your AI credentials and does not send your Blackboard sign-in session to the AI client. Disable access here to stop future reads. Previously shared text may remain in the AI client’s history.

Add the actual supported file types, limits, course/term exclusions, and how to inspect/remove the connection. Do not promise that every tool call asks for confirmation: hosts may auto-approve reads. Do not claim no training, zero retention or no network simply because MCP is local; the chosen client/account terms control provider processing.

For embedded-terminal mode add: the official CLI runs as a subprocess, its own terms/permissions/history apply, the app renders its displayed input/output, sign-in stays with the CLI/system browser, local terminal logging is off, and diagnostics are user-reviewed. If transcript export is offered, it is explicit and may contain private course material. No automatic transcript or terminal screenshot attachment to support reports.

### Microsoft Store generative-AI declaration

Earlier API-key research identified policy 11.16 as relevant to a product that displays generated content. Rechecking the current policy gives a narrower distinction:

- **Exporter only:** if Blackboard Sync only exposes existing synced material through MCP, never calls a model and never displays generated responses, it does not obviously “contain dynamic content created by generative AI models.” The policy does not expressly classify this MCP-only edge case. **Inference:** a generative-AI declaration is not automatically triggered merely by supporting MCP. Update privacy/data-sharing metadata and explain the exact exporter behavior in review notes; verify Partner Center wording/certification before launch.
- **Embedded official CLI or own chat UI:** the product visibly contains live AI-generated responses, even though the child process calls the model. **Recommendation:** treat 11.16 as applicable—disclose live AI in metadata and submission, comply with content rules, and provide a developer reporting path. “We do not make the HTTP request ourselves” is not a sound exemption.
- A terminal renderer alone with no AI feature is a different product, but this proposed integrated study-client mode is expressly an AI feature. Branding and copy should match that behavior.

This is an evidence-based policy interpretation, not a Microsoft ruling. The reviewed current policy’s trigger is generated **content in the product**, not who stores the key. Existing `store/microsoft/README.md:87` must be reconsidered for any embedded release. [Microsoft Store Policies, 11.16 and accurate representation][S81]

### Academic integrity

Default examples should support understanding, source-grounded summaries, retrieval and practice. Keep deadlines deterministic and clearly cached. Ask students to check course/assessment rules and disclose AI assistance when required. Never present the connection as permission to upload licensed course packs or classmates’ information, and do not add exam/assignment submission automation.

The earlier research’s institutional example remains illustrative: Oxford requires assessment-specific permission and declarations; it is not evidence of the target school’s rules. No target-school policy was provided or researched. [Official institutional example][S82]

## 9. Phased implementation plan, tests and risks

### Milestones and rough effort

| Phase | Deliverable and exit condition | Estimate |
| --- | --- | --- |
| **0 — verification spike** | Pin SDK/version; validate modern+legacy stdio, metadata discrepancy, Mac/Windows frozen launch, bundle delta and MSIX path strategy with synthetic data. Recheck intended client plan/surface. | **1–2 days** |
| **1 — minimum useful exporter** | Opt-in course allowlist, current-term-only strict snapshots; list courses/announcements/deadlines, full Markdown note read, bounded text search; stdio subcommand, copyable setup and privacy copy. First certify one GUI host on Mac and Windows Setup. | **5–8 days after phase 0**, approximately **6–10 total** |
| **1a — embedded terminal feel** | Real PTY/ConPTY in actual app UIs with synthetic data, one existing signed-in CLI, theme/approval/copy/source/resize demonstration. No distribution or automatic installation. | **1–2 days**, can precede full exporter polish |
| **2 — student onboarding and Store** | MCPB adapter, client merge/undo, Store stable launcher/profile isolation, frozen update/reconnect tests, additional client certificates. | **3–6 days**, plus store/directory queues |
| **3 — polished terminal mode** | One provider’s approved integration, stepwise installation/login, narrow terminal bridge, source links, errors, accessibility, two-platform packaged smoke tests. | **10–18 days beyond shared MCP**, prototype findings may change scope |
| **4 — richer retrieval** | list/read text files, local PDF extraction/page citations, incremental search index, bounded parsing and stale-content behavior. No remote embeddings required. | **5–10 days**; OCR a separate project |
| **5 — optional structured chat** | If terminal feel is insufficient: official ACP/App Server or carefully scoped headless UI, with agent-owned credentials and explicit approvals. | **12–20 days first provider**, overlapping UI work reduces totals |
| **6 — remote clients** | Only if justified: authenticated bridge/tunnel onboarding, tenant/security/availability design, deletion/retention and review. | **2–4+ weeks** for a supported service; significant ongoing operations |

These scopes overlap; do not mechanically sum every column. A one-client prototype can take hours, but secure two-platform onboarding and updates are the substantial work. No feature work is started by this report.

Minimum first release should not advertise arbitrary PDFs, every AI app, a universal subscription, mobile access or a polished integrated agent. Its acceptance example: a student selects two current courses, connects a supported GUI client, asks for recent announcements/upcoming deadlines, and receives bounded source-linked cached results; unticked/unshared/past course reads fail.

### Meaningful implementation test plan

1. **Authorization:** disabled course still on disk, newly discovered course, revoked consent mid-read, current→past transition, unknown/ambiguous IDs, bad/missing settings/consent/course-selection/state, legacy snapshots and mismatched roots. Verify no fail-open/default-path fallback.
2. **No secret exposure:** synthetic canary credentials in private profile, logs, fake browser cache and out-of-scope courses; assert no output, error, stderr or index contains canaries. Test a permitted note containing an authenticated URL separately.
3. **Filesystem:** traversal/URL encoding, Windows drive/UNC/ADS/reparse points, symlinks/hardlink considerations, nonregular files, destination/private-data overlap, races, renamed files, Unicode/case collisions, partial downloads and cloud placeholders.
4. **Read-only behavior:** snapshot all fixture bytes/paths before and after every operation, including malformed input and corruption. Assert no migration, rename, repair, sync, Blackboard request or Calendar access. Network-blocked server must still answer cached queries.
5. **Data correctness:** announcement preview versus full Markdown, key ownership, local edits, date/timezone/DST boundaries, unavailable/stale deadlines, missing attachments and source-line/page coverage. Do not mark submitted work incomplete/complete.
6. **Protocol:** current/legacy discovery, stdout purity, newline/UTF-8 framing, schema validation, pagination/cursor invalidation, output byte ceilings, empty results, malformed/oversized JSON, cancellation/EOF, parallel clients and fixed tool ordering.
7. **Packaged launch:** clean Mac and Windows machines without Python/Node for the exporter; app paths with spaces, custom install/destination, restricted PATH, Documents permission, Setup/MSIX coexistence, update while connected, uninstall and stale config. Test each distribution independently.
8. **Client smoke:** record exact app/CLI versions, account plan, country and workspace policy. Prove discover→list→read→search→revoke, not just config creation. Confirm read-only annotations/approval behavior and citation display.
9. **HTTP later:** wrong/missing token, invalid Origin/Host, DNS rebinding/browser requests, CORS, CSRF on pairing, token audience, rotation, expired sessions, public-interface refusal and disconnect behavior.
10. **Terminal:** PTY/ConPTY resize/backpressure, process-tree cleanup, startup/login-expiry/credit exhaustion, Ctrl+C/copy, bracketed paste/IME, malformed escape sequences, malicious OSC links/clipboard, accessibility, app theme changes, focus and scrollback.
11. **Embedded agent:** adversarial announcement asks for private files/shell/network; actual host tool restrictions prevent it. Test hostile local instruction files/hooks and other installed MCP servers. The terminal styling must not conceal approvals.
12. **Structured UI later:** unknown events, partial JSON frames, duplicate/out-of-order chunks, resumed turns, permission requests, cancellation, safe Markdown, untrusted URLs and transcript deletion. Verify no code path asks the app for provider tokens.

Use entirely synthetic fixtures and mocked client transport for routine tests. A final small real client call requires a user-owned appropriately permitted account and explicit course scope; record it as a launch certification step, not something done by this research.

### Open questions to settle when building

These are future engineering/vendor verification items, not a request for a product decision during this research:

- Which exact first GUI/CLI versions and student OS/account combinations pass hands-on certification? Is Free-plan local MCP actually available where intended?
- Does the SDK’s measured bundle delta fit the size budget, and which pinned release/runtime baseline is supported?
- How will a Store execution alias/launcher preserve stdio and the explicit package profile across upgrades?
- Can the official interactive CLI be restricted to an acceptable study scope without global configuration damage? Can the terminal retain a usable transcript and approvals at the intended window size?
- Do VoiceOver/NVDA and keyboard/IME behavior meet the app’s accessibility bar?
- Does each provider permit a new publicly distributed local educational wrapper using managed subscription auth? In particular, resolve Anthropic’s conflicting narrow/broad guidance and OpenAI’s existing-app language.
- Is the chosen school’s course material/assessment policy compatible with external AI disclosure? What about students under 18 and account/region restrictions?
- Does Microsoft classify the exporter-only mode as live AI, and what exact reviewer/reporting requirements apply to the embedded mode?
- Are PDF/OCR, archived terms or cloud/mobile access valuable enough to justify their extra security, dependency and operational scope?

### Risks and conditions that could make the idea unworkable

| Risk | What would change the plan |
| --- | --- |
| Vendor disallows embedded subscription-funded use | Keep plain official-client MCP integration; do not work around policy with token reuse. |
| Required student client cannot reach a laptop server | Use supported desktop client or separately designed bridge; a local-only exporter cannot deliver universal mobile/web support. |
| CLI tool access cannot be constrained | Terminal mode remains advanced/general-purpose or is deferred; do not weaken the credential boundary. |
| Poor terminal usability/accessibility | Use ACP/App Server structured UI or stay with official GUI client. |
| Store launcher or update behavior breaks stdio | Defer Store integration until a supported stable launcher is proven; do not copy protected package executables. |
| School forbids sending material to external AI | No cloud-client connection for that material; a truly local client/model may be an alternative only if policy permits. |
| SDK/CLI bundles too large or fragile | Keep clients external; benchmark a lean exporter; avoid bundling agent SDKs/runtimes. |
| Stale or unextractable synced content | Report coverage/freshness precisely. MCP does not make scanned PDFs searchable or guarantee live deadlines. |
| Prompt injection uses other agent tools | Strong host restrictions and informed setup; the exporter alone cannot solve it. |
| Public remote service cost/privacy exceeds scope | Preserve local stdio product; remote support is optional and not required for the core idea. |

## 10. Evidence and retrieval limitations

The research uses public vendor documentation and package metadata retrieved on 22 October 2026, plus a read-only review of repository source and packaging. No signed-in account, live Blackboard material, terminal client run, frozen app, Store submission or vendor clarification was tested. Client support, permission and effort figures retain those limits.

Cached snippets were materially stale on MCP version, Gemini custom apps, ChatGPT local support and plan setup; fetched current official pages take priority, though current pages can still reflect rollout and account differences. Some guessed documentation paths were inaccessible; matching vendor pages were located through official links. The unparameterized Gemini custom-app help URL was inaccessible, but the English-locale URL in the source register fetched successfully.

The published mcp 2.3.0 metadata and release pyproject specify Python 3.10 or newer, while the latest SDK documentation/main branch specifies Python 3.11 or newer. Both findings are recorded pending implementation-time verification. Package component sizes are not measured frozen application deltas.

This note identifies future work and does not report a reproduced application defect. Versionless sources, vendor terms, platform behavior, account availability and Store interpretation should be rechecked when implementation begins.

### Source register

**All sources below were retrieved on 2026-10-22.** Reference links resolve to exact official documentation URLs or maintainer-published package/repository metadata; no third-party tutorial is used as technical evidence. Versionless pages must be rechecked when implementation starts. Related sources are grouped to keep this register navigable.

| ID | Official source | Retrieval date |
| --- | --- | --- |
| S01 | [MCP specification, current revision](https://modelcontextprotocol.io/specification/2026-07-28) | 2026-10-22 |
| S02 | [MCP key changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog) | 2026-10-22 |
| S03 | [MCP transport overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) | 2026-10-22 |
| S04 | [stdio binding](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) | 2026-10-22 |
| S05 | [Streamable HTTP binding](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) | 2026-10-22 |
| S06 | [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) | 2026-10-22 |
| S07 | [MCP security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) | 2026-10-22 |
| S08 | [MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | 2026-10-22 |
| S09 | [MCP resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources) | 2026-10-22 |
| S10 | [Official MCP SDK directory](https://modelcontextprotocol.io/docs/2026-07-28/sdk) | 2026-10-22 |
| S11 | [Python SDK protocol versions](https://py.sdk.modelcontextprotocol.io/protocol-versions/) | 2026-10-22 |
| S12 | [Python SDK legacy-client support](https://py.sdk.modelcontextprotocol.io/run/legacy-clients/) | 2026-10-22 |
| S13 | [Python SDK current documentation](https://py.sdk.modelcontextprotocol.io/) | 2026-10-22 |
| S14 | [mcp 2.3.0 registry metadata](https://pypi.org/pypi/mcp/2.3.0/json) | 2026-10-22 |
| S15 | [mcp 2.3.0 release pyproject](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v2.3.0/pyproject.toml) | 2026-10-22 |
| S16 | [Install Claude Desktop](https://support.claude.com/en/articles/10065433-install-claude-desktop) | 2026-10-22 |
| S17 | [Claude local extension installation and updates](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop?q=claude+desktop) | 2026-10-22 |
| S18 | [Claude desktop versus web connectors](https://support.claude.com/en/articles/11725091-when-to-use-desktop-and-web-connectors) | 2026-10-22 |
| S19 | [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp) | 2026-10-22 |
| S20 | [Claude Code platform setup](https://code.claude.com/docs/en/setup) | 2026-10-22 |
| S21 | [ChatGPT desktop/Codex local MCP](https://learn.chatgpt.com/docs/extend/mcp) | 2026-10-22 |
| S22 | [ChatGPT desktop app](https://learn.chatgpt.com/docs/app) | 2026-10-22 |
| S23 | [Local Codex pricing and access](https://learn.chatgpt.com/docs/pricing) | 2026-10-22 |
| S24 | [ChatGPT custom MCP help and plan distinctions](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt) | 2026-10-22 |
| S25 | [ChatGPT connection and test workflow](https://developers.openai.com/plugins/deploy/connect-chatgpt) | 2026-10-22 |
| S26 | [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) | 2026-10-22 |
| S27 | [Gemini CLI MCP servers](https://geminicli.com/docs/tools/mcp-server/) | 2026-10-22 |
| S28 | [Gemini CLI installation](https://geminicli.com/docs/get-started/installation/) | 2026-10-22 |
| S29 | [Gemini CLI authentication](https://geminicli.com/docs/get-started/authentication/) | 2026-10-22 |
| S30 | [Gemini CLI quotas and pricing](https://geminicli.com/docs/resources/quota-and-pricing/) | 2026-10-22 |
| S31 | [Gemini consumer custom apps, successfully fetched English locale](https://support.google.com/gemini/answer/17209137?hl=en-TT) | 2026-10-22 |
| S32 | [Gemini Code Assist agent/MCP setup](https://docs.cloud.google.com/gemini/docs/codeassist/use-agentic-chat-pair-programmer) | 2026-10-22 |
| S33 | [Gemini Enterprise MCP workflows](https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/connect-mcp-servers) | 2026-10-22 |
| S34 | [Cursor MCP](https://prod.cursor.com/docs/mcp) | 2026-10-22 |
| S35 | [Cursor current pricing](https://cursor.com/pricing) | 2026-10-22 |
| S36 | [Cursor downloads/platforms](https://cursor.com/download) | 2026-10-22 |
| S37 | [VS Code Copilot setup](https://code.visualstudio.com/docs/setup/copilot) | 2026-10-22 |
| S38 | [VS Code add MCP server](https://code.visualstudio.com/docs/agent-customization/mcp-servers) | 2026-10-22 |
| S39 | [VS Code MCP configuration formats](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) | 2026-10-22 |
| S40 | [Cline MCP configuration](https://docs.cline.bot/mcp/mcp-overview) | 2026-10-22 |
| S41 | [Cline installation/provider options](https://docs.cline.bot/getting-started/installing-cline) | 2026-10-22 |
| S42 | [LM Studio MCP host](https://lmstudio.ai/docs/app/mcp) | 2026-10-22 |
| S43 | [LM Studio system requirements](https://lmstudio.ai/docs/app/system-requirements) | 2026-10-22 |
| S44 | [LM Studio/Bionic pricing](https://lmstudio.ai/pricing) | 2026-10-22 |
| S45 | [MCP local-server configuration tutorial](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers) | 2026-10-22 |
| S46 | [Gemini CLI extensions](https://geminicli.com/docs/extensions/) | 2026-10-22 |
| S47 | [Anthropic desktop-extension/MCPB overview](https://www.anthropic.com/research/desktop-extensions) | 2026-10-22 |
| S48 | [MCPB maintainer manifest specification](https://raw.githubusercontent.com/modelcontextprotocol/mcpb/main/MANIFEST.md) | 2026-10-22 |
| S49 | [MCP Inspector](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector) | 2026-10-22 |
| S50 | [Python PTY utilities and macOS caveat](https://docs.python.org/3/library/pty.html) | 2026-10-22 |
| S51 | [Microsoft pseudoconsole session](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session) | 2026-10-22 |
| S52 | [xterm npm metadata](https://registry.npmjs.org/@xterm/xterm/latest) | 2026-10-22 |
| S53 | [pywinpty registry metadata](https://pypi.org/pypi/pywinpty/json) | 2026-10-22 |
| S54 | [ACP Python registry metadata](https://pypi.org/pypi/agent-client-protocol/json) | 2026-10-22 |
| S55 | [Gemini CLI npm metadata](https://registry.npmjs.org/@google/gemini-cli/latest) | 2026-10-22 |
| S56 | [Claude Agent SDK registry metadata](https://pypi.org/pypi/claude-agent-sdk/json) | 2026-10-22 |
| S57 | [Codex SDK npm metadata](https://registry.npmjs.org/@openai/codex-sdk/latest) | 2026-10-22 |
| S58 | [xterm link handling](https://xtermjs.org/docs/guides/link-handling/) | 2026-10-22 |
| S59 | [Claude CLI/auth status reference](https://code.claude.com/docs/en/cli-reference) | 2026-10-22 |
| S60 | [Codex authentication/status](https://learn.chatgpt.com/docs/auth) | 2026-10-22 |
| S61 | [xterm terminal options/accessibility](https://xtermjs.org/docs/api/terminal/interfaces/iterminaloptions/) | 2026-10-22 |
| S62 | [xterm security guidance](https://xtermjs.org/docs/guides/security/) | 2026-10-22 |
| S63 | [Claude programmatic/headless interface](https://code.claude.com/docs/en/headless) | 2026-10-22 |
| S64 | [Gemini headless JSON/events](https://geminicli.com/docs/cli/headless/) | 2026-10-22 |
| S65 | [Codex non-interactive interface](https://learn.chatgpt.com/docs/non-interactive-mode) | 2026-10-22 |
| S66 | [ACP introduction and version navigation](https://agentclientprotocol.com/get-started/introduction) | 2026-10-22 |
| S67 | [ACP Python library](https://agentclientprotocol.com/libraries/python) | 2026-10-22 |
| S68 | [Gemini native ACP mode](https://geminicli.com/docs/cli/acp-mode/) | 2026-10-22 |
| S69 | [ACP agent catalog](https://agentclientprotocol.com/get-started/agents) | 2026-10-22 |
| S70 | [Claude Agent ACP adapter maintained by ACP project](https://github.com/agentclientprotocol/claude-agent-acp) | 2026-10-22 |
| S71 | [Codex ACP adapter maintained by ACP project](https://github.com/agentclientprotocol/codex-acp) | 2026-10-22 |
| S72 | [ACP authentication ownership](https://agentclientprotocol.com/protocol/v1/authentication) | 2026-10-22 |
| S73 | [Codex App Server, managed/external auth and use limitations](https://learn.chatgpt.com/docs/app-server) | 2026-10-22 |
| S74 | [Official Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) | 2026-10-22 |
| S75 | [Claude Agent SDK and public-product authentication guidance](https://code.claude.com/docs/en/agent-sdk/overview) | 2026-10-22 |
| S76 | [Claude Agent SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python) | 2026-10-22 |
| S77 | [Gemini CLI license and service terms](https://geminicli.com/docs/resources/tos-privacy/) | 2026-10-22 |
| S78 | [Claude SDK/subscription help, October 7 update](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) | 2026-10-22 |
| S79 | [Claude account/subscription third-party policy](https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account) | 2026-10-22 |
| S80 | [Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms) | 2026-10-22 |
| S81 | [Microsoft Store Policies version 7.20](https://learn.microsoft.com/en-us/windows/apps/publish/store-policies) | 2026-10-22 |
| S82 | [Oxford student AI guidance, illustrative only](https://www.ox.ac.uk/students/life/it/genai-tools/guidance-on-safe-and-responsible-use-of-genai) | 2026-10-22 |

[S01]: https://modelcontextprotocol.io/specification/2026-07-28 "MCP specification, current revision; retrieved 2026-10-22"
[S02]: https://modelcontextprotocol.io/specification/2026-07-28/changelog "MCP key changes; retrieved 2026-10-22"
[S03]: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports "MCP transport overview; retrieved 2026-10-22"
[S04]: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio "stdio binding; retrieved 2026-10-22"
[S05]: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http "Streamable HTTP binding; retrieved 2026-10-22"
[S06]: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization "MCP authorization; retrieved 2026-10-22"
[S07]: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices "MCP security best practices; retrieved 2026-10-22"
[S08]: https://modelcontextprotocol.io/specification/2026-07-28/server/tools "MCP tools; retrieved 2026-10-22"
[S09]: https://modelcontextprotocol.io/specification/2026-07-28/server/resources "MCP resources; retrieved 2026-10-22"
[S10]: https://modelcontextprotocol.io/docs/2026-07-28/sdk "Official MCP SDK directory; retrieved 2026-10-22"
[S11]: https://py.sdk.modelcontextprotocol.io/protocol-versions/ "Python SDK protocol versions; retrieved 2026-10-22"
[S12]: https://py.sdk.modelcontextprotocol.io/run/legacy-clients/ "Python SDK legacy-client support; retrieved 2026-10-22"
[S13]: https://py.sdk.modelcontextprotocol.io/ "Python SDK current documentation; retrieved 2026-10-22"
[S14]: https://pypi.org/pypi/mcp/2.3.0/json "mcp 2.3.0 registry metadata; retrieved 2026-10-22"
[S15]: https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v2.3.0/pyproject.toml "mcp 2.3.0 release pyproject; retrieved 2026-10-22"
[S16]: https://support.claude.com/en/articles/10065433-install-claude-desktop "Install Claude Desktop; retrieved 2026-10-22"
[S17]: https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop?q=claude+desktop "Claude local extension installation and updates; retrieved 2026-10-22"
[S18]: https://support.claude.com/en/articles/11725091-when-to-use-desktop-and-web-connectors "Claude desktop versus web connectors; retrieved 2026-10-22"
[S19]: https://code.claude.com/docs/en/mcp "Claude Code MCP configuration; retrieved 2026-10-22"
[S20]: https://code.claude.com/docs/en/setup "Claude Code platform setup; retrieved 2026-10-22"
[S21]: https://learn.chatgpt.com/docs/extend/mcp "ChatGPT desktop/Codex local MCP; retrieved 2026-10-22"
[S22]: https://learn.chatgpt.com/docs/app "ChatGPT desktop app; retrieved 2026-10-22"
[S23]: https://learn.chatgpt.com/docs/pricing "Local Codex pricing and access; retrieved 2026-10-22"
[S24]: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt "ChatGPT custom MCP help and plan distinctions; retrieved 2026-10-22"
[S25]: https://developers.openai.com/plugins/deploy/connect-chatgpt "ChatGPT connection and test workflow; retrieved 2026-10-22"
[S26]: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels "OpenAI Secure MCP Tunnel; retrieved 2026-10-22"
[S27]: https://geminicli.com/docs/tools/mcp-server/ "Gemini CLI MCP servers; retrieved 2026-10-22"
[S28]: https://geminicli.com/docs/get-started/installation/ "Gemini CLI installation; retrieved 2026-10-22"
[S29]: https://geminicli.com/docs/get-started/authentication/ "Gemini CLI authentication; retrieved 2026-10-22"
[S30]: https://geminicli.com/docs/resources/quota-and-pricing/ "Gemini CLI quotas and pricing; retrieved 2026-10-22"
[S31]: https://support.google.com/gemini/answer/17209137?hl=en-TT "Gemini consumer custom apps, successfully fetched English locale; retrieved 2026-10-22"
[S32]: https://docs.cloud.google.com/gemini/docs/codeassist/use-agentic-chat-pair-programmer "Gemini Code Assist agent/MCP setup; retrieved 2026-10-22"
[S33]: https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/connect-mcp-servers "Gemini Enterprise MCP workflows; retrieved 2026-10-22"
[S34]: https://prod.cursor.com/docs/mcp "Cursor MCP; retrieved 2026-10-22"
[S35]: https://cursor.com/pricing "Cursor current pricing; retrieved 2026-10-22"
[S36]: https://cursor.com/download "Cursor downloads/platforms; retrieved 2026-10-22"
[S37]: https://code.visualstudio.com/docs/setup/copilot "VS Code Copilot setup; retrieved 2026-10-22"
[S38]: https://code.visualstudio.com/docs/agent-customization/mcp-servers "VS Code add MCP server; retrieved 2026-10-22"
[S39]: https://code.visualstudio.com/docs/agents/reference/mcp-configuration "VS Code MCP configuration formats; retrieved 2026-10-22"
[S40]: https://docs.cline.bot/mcp/mcp-overview "Cline MCP configuration; retrieved 2026-10-22"
[S41]: https://docs.cline.bot/getting-started/installing-cline "Cline installation/provider options; retrieved 2026-10-22"
[S42]: https://lmstudio.ai/docs/app/mcp "LM Studio MCP host; retrieved 2026-10-22"
[S43]: https://lmstudio.ai/docs/app/system-requirements "LM Studio system requirements; retrieved 2026-10-22"
[S44]: https://lmstudio.ai/pricing "LM Studio/Bionic pricing; retrieved 2026-10-22"
[S45]: https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers "MCP local-server configuration tutorial; retrieved 2026-10-22"
[S46]: https://geminicli.com/docs/extensions/ "Gemini CLI extensions; retrieved 2026-10-22"
[S47]: https://www.anthropic.com/research/desktop-extensions "Anthropic desktop-extension/MCPB overview; retrieved 2026-10-22"
[S48]: https://raw.githubusercontent.com/modelcontextprotocol/mcpb/main/MANIFEST.md "MCPB maintainer manifest specification; retrieved 2026-10-22"
[S49]: https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector "MCP Inspector; retrieved 2026-10-22"
[S50]: https://docs.python.org/3/library/pty.html "Python PTY utilities and macOS caveat; retrieved 2026-10-22"
[S51]: https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session "Microsoft pseudoconsole session; retrieved 2026-10-22"
[S52]: https://registry.npmjs.org/@xterm/xterm/latest "xterm npm metadata; retrieved 2026-10-22"
[S53]: https://pypi.org/pypi/pywinpty/json "pywinpty registry metadata; retrieved 2026-10-22"
[S54]: https://pypi.org/pypi/agent-client-protocol/json "ACP Python registry metadata; retrieved 2026-10-22"
[S55]: https://registry.npmjs.org/@google/gemini-cli/latest "Gemini CLI npm metadata; retrieved 2026-10-22"
[S56]: https://pypi.org/pypi/claude-agent-sdk/json "Claude Agent SDK registry metadata; retrieved 2026-10-22"
[S57]: https://registry.npmjs.org/@openai/codex-sdk/latest "Codex SDK npm metadata; retrieved 2026-10-22"
[S58]: https://xtermjs.org/docs/guides/link-handling/ "xterm link handling; retrieved 2026-10-22"
[S59]: https://code.claude.com/docs/en/cli-reference "Claude CLI/auth status reference; retrieved 2026-10-22"
[S60]: https://learn.chatgpt.com/docs/auth "Codex authentication/status; retrieved 2026-10-22"
[S61]: https://xtermjs.org/docs/api/terminal/interfaces/iterminaloptions/ "xterm terminal options/accessibility; retrieved 2026-10-22"
[S62]: https://xtermjs.org/docs/guides/security/ "xterm security guidance; retrieved 2026-10-22"
[S63]: https://code.claude.com/docs/en/headless "Claude programmatic/headless interface; retrieved 2026-10-22"
[S64]: https://geminicli.com/docs/cli/headless/ "Gemini headless JSON/events; retrieved 2026-10-22"
[S65]: https://learn.chatgpt.com/docs/non-interactive-mode "Codex non-interactive interface; retrieved 2026-10-22"
[S66]: https://agentclientprotocol.com/get-started/introduction "ACP introduction and version navigation; retrieved 2026-10-22"
[S67]: https://agentclientprotocol.com/libraries/python "ACP Python library; retrieved 2026-10-22"
[S68]: https://geminicli.com/docs/cli/acp-mode/ "Gemini native ACP mode; retrieved 2026-10-22"
[S69]: https://agentclientprotocol.com/get-started/agents "ACP agent catalog; retrieved 2026-10-22"
[S70]: https://github.com/agentclientprotocol/claude-agent-acp "Claude Agent ACP adapter maintained by ACP project; retrieved 2026-10-22"
[S71]: https://github.com/agentclientprotocol/codex-acp "Codex ACP adapter maintained by ACP project; retrieved 2026-10-22"
[S72]: https://agentclientprotocol.com/protocol/v1/authentication "ACP authentication ownership; retrieved 2026-10-22"
[S73]: https://learn.chatgpt.com/docs/app-server "Codex App Server, managed/external auth and use limitations; retrieved 2026-10-22"
[S74]: https://learn.chatgpt.com/docs/codex-sdk "Official Codex SDK; retrieved 2026-10-22"
[S75]: https://code.claude.com/docs/en/agent-sdk/overview "Claude Agent SDK and public-product authentication guidance; retrieved 2026-10-22"
[S76]: https://code.claude.com/docs/en/agent-sdk/python "Claude Agent SDK Python reference; retrieved 2026-10-22"
[S77]: https://geminicli.com/docs/resources/tos-privacy/ "Gemini CLI license and service terms; retrieved 2026-10-22"
[S78]: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan "Claude SDK/subscription help, October 7 update; retrieved 2026-10-22"
[S79]: https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account "Claude account/subscription third-party policy; retrieved 2026-10-22"
[S80]: https://www.anthropic.com/legal/consumer-terms "Anthropic Consumer Terms; retrieved 2026-10-22"
[S81]: https://learn.microsoft.com/en-us/windows/apps/publish/store-policies "Microsoft Store Policies version 7.20; retrieved 2026-10-22"
[S82]: https://www.ox.ac.uk/students/life/it/genai-tools/guidance-on-safe-and-responsible-use-of-genai "Oxford student AI guidance, illustrative only; retrieved 2026-10-22"
