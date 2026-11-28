// Runs on the Gemini Notebook page. Picks up the app's loopback bridge (port and token handed over
// in the address fragment, which never leaves the browser), then carries out the app's requests
// with this page's Google session until the app says it is done. Every bridge request goes through
// the background page (background.js); Safari does not let a page reach 127.0.0.1.
"use strict";

(() => {
  const api = globalThis.browser || globalThis.chrome;
  const HASH = /(?:^#|&)bbsync=(\d{2,5})\.([A-Za-z0-9_-]{16,})/;
  const LOOPS = 4; // the app works on up to three courses at once, plus its status checks
  const CHUNK = 4 * 1024 * 1024; // bytes per file read from the app
  const ALIVE_MS = 10000; // the app takes a silent page for a closed tab after 90 s
  const say = (key, ...subs) => (api.i18n && api.i18n.getMessage(key, subs)) || key;
  // This copy of the page: after a reload the app knows the work it gave the old one is lost.
  const PAGE = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  let bridge = null;
  let banner = null;
  let finished = false;
  let working = 0;

  function show(text, failed = false) {
    const paint = () => {
      if (!banner) {
        banner = document.createElement("div");
        banner.setAttribute("role", "status");
        banner.style.cssText = "position:fixed;z-index:2147483647;left:50%;bottom:24px;transform:translateX(-50%);" +
          "max-width:min(560px,90vw);padding:10px 16px;border-radius:10px;font:13px -apple-system,system-ui,sans-serif;" +
          "box-shadow:0 4px 18px rgba(0,0,0,.25);color:#fff";
        document.documentElement.appendChild(banner);
      }
      banner.style.background = failed ? "#b3261e" : "#1f1f1f";
      banner.textContent = `Blackboard Sync: ${text}`;
    };
    if (document.documentElement) paint(); else document.addEventListener("DOMContentLoaded", paint, { once: true });
  }

  function takeBridgeFromAddress() {
    const match = location.hash.match(HASH);
    if (!match) return null;
    history.replaceState(null, "", location.pathname + location.search);
    return { port: Number(match[1]), token: match[2] };
  }

  async function call(path, { method = "GET", body = null, as = "json" } = {}) {
    const reply = await api.runtime.sendMessage({
      type: "bridge", url: `http://127.0.0.1:${bridge.port}${path}`, token: bridge.token, page: PAGE,
      method, body: body == null ? null : JSON.stringify(body), as,
    });
    if (!reply || reply.error) throw new Error(reply ? reply.error : "no reply from the background page");
    return as === "bytes" ? Uint8Array.from(atob(reply.base64), (c) => c.charCodeAt(0)) : reply.json;
  }

  async function note(event, detail) {
    try { await call("/log", { method: "POST", body: { event, detail } }); } catch (_) { /* best effort */ }
  }

  async function readFile(fileId, size, mime) {
    const parts = [];
    for (let offset = 0; offset < size; offset += CHUNK) {
      const length = Math.min(CHUNK, size - offset);
      const bytes = await call(`/file/${encodeURIComponent(fileId)}?offset=${offset}&length=${length}`, { as: "bytes" });
      if (bytes.length !== length) throw new BBSyncNotebook.NotebookError("transient", "the file changed while it was read");
      parts.push(bytes);
    }
    return new Blob(parts, { type: mime });
  }

  async function perform(request) {
    const N = BBSyncNotebook;
    const args = request.args || {};
    switch (request.op) {
      case "hello": return N.open();
      case "account_limits": return N.accountLimits();
      case "list_notebooks": return N.listNotebooks();
      case "create_notebook": return N.createNotebook(args.title);
      case "list_sources": return N.listSources(args.notebook_id);
      case "rename_source": return N.renameSource(args.notebook_id, args.source_id, args.title);
      case "add_file": {
        show(say("adding", args.filename));
        const mime = args.mime || "application/octet-stream";
        return N.addFile(args.notebook_id, await readFile(args.file_id, Number(args.size) || 0, mime), args.filename, mime);
      }
      default: throw new N.NotebookError("permanent", `unknown request ${request.op}`);
    }
  }

  async function finish(request) {
    if (finished) return;
    finished = true;
    await api.runtime.sendMessage({ type: "forget", token: bridge.token });
    show(say("done"));
    if (request.args && request.args.close) {
      setTimeout(() => api.runtime.sendMessage({ type: "close" }), 1500);
    }
  }

  async function serve() {
    while (!finished) {
      let request;
      try {
        request = await call("/next");
      } catch (error) {
        if (!finished) show(say("lost"), true);
        finished = true; // the app went away
        return;
      }
      if (!request || request.op === "idle") continue;
      if (request.op === "bye") { await finish(request); return; }
      let reply;
      working += 1;
      if (request.op !== "add_file") show(say("working"));
      try {
        reply = { id: request.id, ok: true, value: await perform(request) };
      } catch (error) {
        const kind = error.kind || "transient";
        reply = { id: request.id, ok: false, error: { kind, message: String(error.message || error) } };
        show(kind === "login" ? say("signIn") : reply.error.message, true);
      } finally {
        working -= 1;
      }
      try {
        await call("/result", { method: "POST", body: reply });
      } catch (_) {
        finished = true;
        return;
      }
    }
  }

  async function keepAlive() {
    while (!finished) {
      await new Promise((resolve) => setTimeout(resolve, ALIVE_MS));
      if (finished) return;
      try { await call("/alive", { method: "POST", body: { working } }); } catch (_) { /* /next will notice */ }
    }
  }

  async function start() {
    const fromAddress = takeBridgeFromAddress();
    if (fromAddress) {
      bridge = fromAddress;
      await api.runtime.sendMessage({ type: "remember", bridge });
    } else {
      const reply = await api.runtime.sendMessage({ type: "recall" });
      bridge = reply && reply.bridge;
    }
    if (!bridge) return;
    show(say("connected"));
    await note("page", `started on ${location.host}`);
    keepAlive();
    await Promise.all(Array.from({ length: LOOPS }, serve));
  }

  start().catch(() => {});
})();
