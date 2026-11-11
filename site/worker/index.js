// Short download links: /mac and /windows redirect to the latest release asset.
// /stats.json aggregates release download counts across all releases.
// The promo video gets byte ranges. Every other path is served by the static
// assets binding (see wrangler.jsonc).

const CACHE_SECONDS = 300;
const STATS_CACHE_SECONDS = 3600;
const STALE_STATS_CACHE_SECONDS = 604800;
const DEFAULT_RELEASES_API = "https://api.github.com/repos/UmutYLCN/blackboard-sync/releases";
const PER_PAGE = 100;
const MAX_PAGES = 20;

// Microsoft Store downloads not counted by GitHub releases (as of 2026-11-11).
const MICROSOFT_STORE_DOWNLOADS = 568;

// Asset name matchers per platform, most specific first.
const PLATFORMS = {
  mac: [/\.dmg$/i],
  windows: [/-Setup\.exe$/i, /\.exe$/i, /\.msi$/i],
};

// Resolved release and download stats, kept per isolate so most requests skip the GitHub API.
let cached = { assets: null, expires: 0 };
let cachedStats = { data: null, expires: 0 };

export function resetCache() {
  cached = { assets: null, expires: 0 };
  cachedStats = { data: null, expires: 0 };
}

// Find the first release asset matching the platform's patterns.
function pickAsset(assets, patterns) {
  for (const pattern of patterns) {
    const asset = assets.find((a) => pattern.test(a.name));
    if (asset) return asset;
  }
  return null;
}

async function latestAssets(env) {
  if (cached.assets && Date.now() < cached.expires) return cached.assets;

  // The edge cache also keeps the API response for a few minutes.
  const res = await fetch(env.RELEASE_API, {
    headers: {
      "User-Agent": "blackboard-sync-site",
      Accept: "application/vnd.github+json",
    },
    cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true },
  });
  if (!res.ok) throw new Error(`GitHub API responded ${res.status}`);

  const release = await res.json();
  if (!Array.isArray(release.assets)) throw new Error("Release has no assets");

  cached = { assets: release.assets, expires: Date.now() + CACHE_SECONDS * 1000 };
  return cached.assets;
}

function jsonResponse(body, status, cacheControl) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": cacheControl,
    },
  });
}

function nextPageUrl(res, baseApi, page, count) {
  const link = res.headers && typeof res.headers.get === "function" ? res.headers.get("Link") : null;
  if (link) {
    const match = /<([^>]+)>;\s*rel="next"/.exec(link);
    return match ? match[1] : null;
  }
  if (count === PER_PAGE) {
    const next = new URL(baseApi);
    next.searchParams.set("per_page", String(PER_PAGE));
    next.searchParams.set("page", String(page + 1));
    return next.toString();
  }
  return null;
}

async function fetchReleaseStats(env) {
  const baseApi = (env && env.RELEASES_API) || DEFAULT_RELEASES_API;
  const first = new URL(baseApi);
  first.searchParams.set("per_page", String(PER_PAGE));
  first.searchParams.set("page", "1");

  let nextUrl = first.toString();
  const seen = new Set();
  let mac = 0;
  let windows = 0;

  for (let page = 1; page <= MAX_PAGES && nextUrl && !seen.has(nextUrl); page++) {
    seen.add(nextUrl);
    const res = await fetch(nextUrl, {
      headers: {
        "User-Agent": "blackboard-sync-site",
        Accept: "application/vnd.github+json",
      },
      cf: { cacheTtl: STATS_CACHE_SECONDS, cacheEverything: true },
    });
    if (!res.ok) throw new Error(`GitHub releases API responded ${res.status}`);

    const releases = await res.json();
    if (!Array.isArray(releases)) throw new Error("Releases payload is not an array");

    for (const release of releases) {
      if (!release || release.draft || !Array.isArray(release.assets)) continue;
      for (const asset of release.assets) {
        if (!asset || typeof asset.name !== "string" || typeof asset.download_count !== "number") continue;
        if (!Number.isFinite(asset.download_count) || asset.download_count < 0) continue;
        if (/\.dmg$/i.test(asset.name)) {
          mac += asset.download_count;
        } else if (/\.exe$/i.test(asset.name)) {
          windows += asset.download_count;
        }
      }
    }

    nextUrl = nextPageUrl(res, baseApi, page, releases.length);
  }

  const storeDownloads =
    env && typeof env.MICROSOFT_STORE_DOWNLOADS === "number"
      ? env.MICROSOFT_STORE_DOWNLOADS
      : MICROSOFT_STORE_DOWNLOADS;
  windows += storeDownloads;

  return {
    total: mac + windows,
    mac,
    windows,
    updated: new Date().toISOString(),
  };
}

async function statsJson(request, env, ctx) {
  const cache = globalThis.caches && globalThis.caches.default;
  const cacheKey = new Request(new URL("/stats.json", request.url).toString(), { method: "GET" });
  const staleKey = new Request(new URL("/stats.json?stale=1", request.url).toString(), { method: "GET" });

  if (cache && typeof cache.match === "function") {
    try {
      const hit = await cache.match(cacheKey);
      if (hit) {
        try {
          cachedStats.data = await hit.clone().json();
        } catch {
          // Ignore body parse errors on cache hit.
        }
        return hit;
      }
    } catch (err) {
      console.error("Failed to read stats from Cache API:", err);
    }
  }

  if (cachedStats.data && Date.now() < cachedStats.expires) {
    return jsonResponse(cachedStats.data, 200, `public, max-age=${STATS_CACHE_SECONDS}`);
  }

  try {
    const stats = await fetchReleaseStats(env);
    cachedStats = { data: stats, expires: Date.now() + STATS_CACHE_SECONDS * 1000 };
    const res = jsonResponse(stats, 200, `public, max-age=${STATS_CACHE_SECONDS}`);

    if (cache && typeof cache.put === "function") {
      const writeCache = async () => {
        try {
          await cache.put(cacheKey, res.clone());
          await cache.put(staleKey, jsonResponse(stats, 200, `public, max-age=${STALE_STATS_CACHE_SECONDS}`));
        } catch (err) {
          console.error("Failed to write stats to Cache API:", err);
        }
      };
      if (ctx && typeof ctx.waitUntil === "function") {
        try {
          ctx.waitUntil(writeCache());
        } catch (err) {
          console.error("Failed to schedule stats cache write:", err);
        }
      } else {
        await writeCache();
      }
    }

    return res;
  } catch (err) {
    console.error(err);
    if (cachedStats.data) {
      return jsonResponse(cachedStats.data, 200, "no-store");
    }
    if (cache && typeof cache.match === "function") {
      try {
        const stale = await cache.match(staleKey);
        if (stale) {
          const data = await stale.json();
          cachedStats.data = data;
          return jsonResponse(data, 200, "no-store");
        }
      } catch (cacheErr) {
        console.error("Failed to read stale stats from Cache API:", cacheErr);
      }
    }
    return jsonResponse({ error: "Download stats unavailable" }, 503, "no-store");
  }
}

// Safari plays a video only when the server answers byte ranges (206); the assets
// binding sends the whole file, so the Worker cuts the range out of it.
async function videoRange(request, env) {
  const res = await env.ASSETS.fetch(request);
  const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get("Range") || "");
  if (res.status !== 200) return res;
  const headers = new Headers(res.headers);
  headers.set("Accept-Ranges", "bytes");
  if (!range || (range[1] === "" && range[2] === "")) return new Response(res.body, { status: 200, headers });

  const body = await res.arrayBuffer();
  const size = body.byteLength;
  let start = Number(range[1]);
  let end = range[2] === "" ? size - 1 : Math.min(Number(range[2]), size - 1);
  if (range[1] === "") [start, end] = [Math.max(0, size - Number(range[2])), size - 1]; // the last N bytes
  if (start > end || start >= size) {
    return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
  }
  headers.set("Content-Range", `bytes ${start}-${end}/${size}`);
  headers.set("Content-Length", String(end - start + 1));
  return new Response(request.method === "HEAD" ? null : body.slice(start, end + 1), { status: 206, headers });
}

function redirect(location, cacheControl) {
  return new Response(null, {
    status: 302,
    headers: { Location: location, "Cache-Control": cacheControl },
  });
}

function recordDownload(request, env, ctx, platform) {
  const dataset = env.DOWNLOADS || env.downloads;
  if (!dataset || typeof dataset.writeDataPoint !== "function") return;

  const country = (request.cf && request.cf.country) || "";
  let host = "";
  const referer = request.headers.get("referer");
  if (referer) {
    try {
      host = new URL(referer).hostname;
    } catch {
      // Invalid referer URL: leave host empty.
    }
  }

  const write = () => {
    try {
      dataset.writeDataPoint({
        blobs: [platform, country, host],
        doubles: [1],
      });
    } catch (err) {
      console.error("Failed to write download data point:", err);
    }
  };

  if (ctx && typeof ctx.waitUntil === "function") {
    try {
      ctx.waitUntil(Promise.resolve().then(write));
    } catch (err) {
      console.error("Failed to schedule download data point:", err);
    }
  } else {
    write();
  }
}

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    if (pathname.endsWith(".mp4")) return videoRange(request, env);
    if (pathname === "/stats.json") return statsJson(request, env, ctx);
    const platform = pathname.replace(/^\/|\/$/g, "");
    const patterns = PLATFORMS[platform];

    // Only /mac, /windows, /stats.json and the video are routed here; anything else is a static asset.
    if (!patterns) return env.ASSETS.fetch(request);

    recordDownload(request, env, ctx, platform);

    try {
      const asset = pickAsset(await latestAssets(env), patterns);
      if (!asset) throw new Error(`No ${platform} asset in the latest release`);
      return redirect(asset.browser_download_url, `public, max-age=${CACHE_SECONDS}`);
    } catch (err) {
      console.error(err);
      // Fall back to the release page and do not let the fallback stick.
      return redirect(env.RELEASES_PAGE, "no-store");
    }
  },
};
