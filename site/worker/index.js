// Short download links: /mac and /windows redirect to the latest release asset.
// The promo video gets byte ranges. Every other path is served by the static
// assets binding (see wrangler.jsonc).

const CACHE_SECONDS = 300;

// Asset name matchers per platform, most specific first.
const PLATFORMS = {
  mac: [/\.dmg$/i],
  windows: [/-Setup\.exe$/i, /\.exe$/i, /\.msi$/i],
};

// Resolved release, kept per isolate so most requests skip the GitHub API.
let cached = { assets: null, expires: 0 };

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

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname.endsWith(".mp4")) return videoRange(request, env);
    const platform = pathname.replace(/^\/|\/$/g, "");
    const patterns = PLATFORMS[platform];

    // Only /mac, /windows and the video are routed here; anything else is a static asset.
    if (!patterns) return env.ASSETS.fetch(request);

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
