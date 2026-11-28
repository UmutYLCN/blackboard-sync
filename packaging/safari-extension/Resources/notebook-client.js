// Gemini Notebook (NotebookLM) web calls, made from the notebook page itself so Safari sends the
// student's own Google session. Mirrors the few notebooklm-py calls the app's gateway.py uses:
// the batchexecute RPC ids and payloads below are that library's (0.8.5), so a change Google makes
// there shows up in both. Nothing here reads or keeps a cookie.
"use strict";

const BBSyncNotebook = (() => {
  const TEMPLATE = () => [2, null, null, [1, null, null, null, null, null, null, null, null, null, [1]]];
  const RPC = {
    LIST_NOTEBOOKS: "wXbhsf",
    CREATE_NOTEBOOK: "CCqFvf",
    GET_NOTEBOOK: "rLM1Ne",
    ADD_SOURCE_FILE: "o4cbdc",
    UPDATE_SOURCE: "b7Wfje",
    GET_USER_SETTINGS: "ZwVcOc",
  };
  const STATUS = { 1: "processing", 2: "ready", 3: "error" };
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  class NotebookError extends Error {
    constructor(kind, message) {
      super(message);
      this.kind = kind; // login | rate | transient | permanent
    }
  }

  let session = null;
  let opening = null; // the loops share one look at the page for its tokens
  let reqid = 100000 + Math.floor(Math.random() * 9000);

  function authuser() {
    const fromUrl = new URLSearchParams(location.search).get("authuser");
    return fromUrl || "0";
  }

  function pick(html, key) {
    const match = html.match(new RegExp(`"${key}":"((?:[^"\\\\]|\\\\.)*)"`));
    return match ? JSON.parse(`"${match[1]}"`) : null;
  }

  async function readTokens() {
    let response;
    try {
      response = await fetch(`${location.origin}/?authuser=${encodeURIComponent(authuser())}`,
        { credentials: "include", redirect: "follow" });
    } catch (error) {
      throw new NotebookError("transient", `home page: ${error}`);
    }
    const html = await response.text();
    const at = pick(html, "SNlM0e");
    const sid = pick(html, "FdrFJe");
    if (!at || !sid || /accounts\.google\.com/.test(response.url)) {
      throw new NotebookError("login", "not signed in to Google in this browser");
    }
    session = { at, sid };
    return { origin: location.origin };
  }

  function open() {
    if (!opening) opening = readTokens().finally(() => { opening = null; });
    return opening;
  }

  function classifyHttp(status, text) {
    if (status === 401 || status === 403) return new NotebookError("login", `HTTP ${status}`);
    if (status === 429) return new NotebookError("rate", `HTTP ${status}`);
    if (status >= 500) return new NotebookError("transient", `HTTP ${status}`);
    return new NotebookError("permanent", `HTTP ${status}: ${text.slice(0, 200)}`);
  }

  function decode(text, rpcId) {
    const body = text.replace(/^\)\]\}'\r?\n/, "");
    for (const line of body.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("[")) continue;
      let chunk;
      try { chunk = JSON.parse(trimmed); } catch (_) { continue; }
      for (const item of chunk) {
        if (!Array.isArray(item)) continue;
        if (item[0] === "er") throw new NotebookError("permanent", `rpc ${rpcId} error ${JSON.stringify(item).slice(0, 200)}`);
        if (item[0] !== "wrb.fr" || item[1] !== rpcId) continue;
        if (item[2] == null) {
          const code = Array.isArray(item[5]) ? item[5][0] : null;
          if (code === 16 || code === 7) throw new NotebookError("login", `rpc ${rpcId} status ${code}`);
          if (code === 8) throw new NotebookError("rate", `rpc ${rpcId} status ${code}`);
          if (code === 14 || code === 4) throw new NotebookError("transient", `rpc ${rpcId} status ${code}`);
          if (code != null) throw new NotebookError("permanent", `rpc ${rpcId} status ${code}`);
          return null;
        }
        return JSON.parse(item[2]);
      }
    }
    throw new NotebookError("transient", `rpc ${rpcId}: no result in response`);
  }

  async function rpc(rpcId, params, sourcePath = "/") {
    if (!session) await open();
    reqid += 100000;
    const query = new URLSearchParams({
      rpcids: rpcId, "source-path": sourcePath, "f.sid": session.sid, hl: "en",
      _reqid: String(reqid), rt: "c", authuser: authuser(),
    });
    const fReq = JSON.stringify([[[rpcId, JSON.stringify(params), null, "generic"]]]);
    let response;
    try {
      response = await fetch(`${location.origin}/_/LabsTailwindUi/data/batchexecute?${query}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "X-Same-Domain": "1" },
        body: `f.req=${encodeURIComponent(fReq)}&at=${encodeURIComponent(session.at)}&`,
      });
    } catch (error) {
      throw new NotebookError("transient", `rpc ${rpcId}: ${error}`);
    }
    const text = await response.text();
    if (!response.ok) {
      if (response.status === 400 || response.status === 401) session = null; // read the tokens again next time
      throw classifyHttp(response.status, text);
    }
    return decode(text, rpcId);
  }

  async function accountLimits() {
    const result = await rpc(RPC.GET_USER_SETTINGS, [null, [1, null, null, null, null, null, null, null, null, null, [1]]]);
    const limits = Array.isArray(result) && Array.isArray(result[0]) && Array.isArray(result[0][1]) ? result[0][1] : [];
    const positive = (value) => (Number.isInteger(value) && value > 0 ? value : null);
    return { notebook_limit: positive(limits[1]), source_limit: positive(limits[2]) };
  }

  async function renameSource(notebookId, sourceId, title) {
    await rpc(RPC.UPDATE_SOURCE, [null, [sourceId], [[[title]]]], `/notebook/${notebookId}`);
    return true;
  }

  async function listNotebooks() {
    const result = await rpc(RPC.LIST_NOTEBOOKS, [null, 1, null, [2]]);
    const rows = Array.isArray(result) && Array.isArray(result[0]) ? result[0] : [];
    return rows.filter(Array.isArray).map((row) => ({
      id: typeof row[2] === "string" ? row[2] : "",
      title: (typeof row[0] === "string" ? row[0] : "").replace("thought\n", "").trim(),
    })).filter((notebook) => notebook.id);
  }

  async function createNotebook(title) {
    const row = await rpc(RPC.CREATE_NOTEBOOK, [title, null, null, TEMPLATE()]);
    const id = Array.isArray(row) && typeof row[2] === "string" ? row[2] : null;
    if (!id) throw new NotebookError("permanent", "create notebook: no id in response");
    return { id, title: (typeof row[0] === "string" && row[0]) || title };
  }

  async function listSources(notebookId) {
    const result = await rpc(RPC.GET_NOTEBOOK, [notebookId, null, TEMPLATE(), null, 0], `/notebook/${notebookId}`);
    const info = Array.isArray(result) ? result[0] : null;
    const rows = Array.isArray(info) && Array.isArray(info[1]) ? info[1] : [];
    const sources = [];
    const seen = new Set();
    for (const row of rows) {
      if (!Array.isArray(row)) continue;
      const id = Array.isArray(row[0]) ? row[0][0] : row[0];
      if (typeof id !== "string" || seen.has(id)) continue;
      seen.add(id);
      const code = Array.isArray(row[3]) ? row[3][1] : null;
      sources.push({ id, title: typeof row[1] === "string" ? row[1] : "", status: STATUS[code] || "unknown" });
    }
    return sources;
  }

  function findSourceId(node, depth = 0) {
    if (depth > 6) return null;
    if (typeof node === "string") return UUID.test(node) ? node : null;
    if (!Array.isArray(node)) return null;
    for (const child of node) {
      const found = findSourceId(child, depth + 1);
      if (found) return found;
    }
    return null;
  }

  async function addFile(notebookId, blob, filename, mime) {
    const registered = await rpc(RPC.ADD_SOURCE_FILE, [[[filename]], notebookId, TEMPLATE()], `/notebook/${notebookId}`);
    const sourceId = findSourceId(registered);
    if (!sourceId) throw new NotebookError("permanent", `register ${filename}: no source id`);
    const user = authuser();
    let start;
    try {
      start = await fetch(`${location.origin}/upload/_/?authuser=${encodeURIComponent(user)}`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "x-goog-authuser": user,
          "x-goog-upload-command": "start",
          "x-goog-upload-header-content-length": String(blob.size),
          "x-goog-upload-header-content-type": mime,
          "x-goog-upload-protocol": "resumable",
        },
        body: JSON.stringify({ PROJECT_ID: notebookId, SOURCE_NAME: filename, SOURCE_ID: sourceId }),
      });
    } catch (error) {
      throw new NotebookError("transient", `upload start: ${error}`);
    }
    if (!start.ok) throw classifyHttp(start.status, await start.text());
    const uploadUrl = start.headers.get("x-goog-upload-url");
    if (!uploadUrl || new URL(uploadUrl).origin !== location.origin) {
      throw new NotebookError("permanent", "upload start: no upload address");
    }
    let finish;
    try {
      finish = await fetch(uploadUrl, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
          "x-goog-authuser": user,
          "x-goog-upload-command": "upload, finalize",
          "x-goog-upload-offset": "0",
        },
        body: blob,
      });
    } catch (error) {
      throw new NotebookError("transient", `upload: ${error}`);
    }
    if (!finish.ok) throw classifyHttp(finish.status, await finish.text());
    return sourceId;
  }

  return { NotebookError, open, accountLimits, listNotebooks, createNotebook, listSources, addFile, renameSource };
})();
