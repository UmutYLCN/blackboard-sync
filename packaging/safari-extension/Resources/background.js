// The extension's background page. Remembers the app's bridge across a Google sign-in detour and
// relays the page's requests to the app's loopback bridge: Safari does not let the page itself
// reach 127.0.0.1. Never talks to Google and never reads a cookie.
"use strict";

const api = globalThis.browser || globalThis.chrome;
const LIFETIME_MS = 30 * 60 * 1000; // a bridge is good for one run or one setup, no longer

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

async function relay(message) {
  const url = new URL(message.url);
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1") return { error: "refused" };
  const init = {
    method: message.method || "GET",
    headers: { "X-BBSync-Token": message.token, ...(message.body != null ? { "Content-Type": "application/json" } : {}) },
    body: message.body != null ? message.body : undefined,
    cache: "no-store",
    credentials: "omit",
  };
  const response = await fetch(url.href, init);
  if (!response.ok) return { error: `bridge HTTP ${response.status}`, status: response.status };
  if (message.as === "bytes") return { base64: toBase64(await response.arrayBuffer()) };
  return { json: await response.json() };
}

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handle = async () => {
    switch (message && message.type) {
      case "remember":
        await api.storage.local.set({ bridge: { ...message.bridge, at: Date.now() } });
        return { ok: true };
      case "recall": {
        const { bridge } = await api.storage.local.get("bridge");
        return { bridge: bridge && Date.now() - bridge.at < LIFETIME_MS ? bridge : null };
      }
      case "forget":
        await api.storage.local.remove("bridge");
        return { ok: true };
      case "bridge":
        return relay(message);
      case "close":
        if (sender && sender.tab && sender.tab.id != null) await api.tabs.remove(sender.tab.id);
        return { ok: true };
      default:
        return { error: "unknown message" };
    }
  };
  handle().then(sendResponse, (error) => sendResponse({ error: String(error) }));
  return true;
});

// The toolbar button is where Safari asks for access to the notebook site. Once it is granted,
// reload the notebook tab so the content script starts on it.
if (api.action && api.action.onClicked) {
  api.action.onClicked.addListener((tab) => {
    if (tab && tab.id != null && /^https:\/\/(notebook|notebooklm)\.google\.com\//.test(tab.url || "")) {
      api.tabs.reload(tab.id);
    }
  });
}
