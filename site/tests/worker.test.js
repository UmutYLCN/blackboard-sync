import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import worker, { resetCache } from "../worker/index.js";

const MICROSOFT_STORE_DOWNLOADS = 568;

beforeEach(() => {
  resetCache();
  delete globalThis.caches;
});

function mockEnv(overrides = {}) {
  const dataPoints = [];
  return {
    dataPoints,
    DOWNLOADS: {
      writeDataPoint(point) {
        dataPoints.push(point);
      },
    },
    RELEASE_API: "https://api.github.com/repos/UmutYLCN/blackboard-sync/releases/latest",
    RELEASES_PAGE: "https://github.com/UmutYLCN/blackboard-sync/releases/latest",
    ASSETS: {
      fetch: async (req) => new Response("asset content", { status: 200 }),
    },
    ...overrides,
  };
}

function mockCtx() {
  const promises = [];
  return {
    promises,
    waitUntil(promise) {
      promises.push(promise);
    },
  };
}

const RELEASE_RESPONSE = {
  tag_name: "v9.8.7",
  assets: [
    {
      name: "Blackboard-Sync-9.8.7.dmg",
      browser_download_url: "https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/Blackboard-Sync-9.8.7.dmg",
    },
    {
      name: "Blackboard-Sync-9.8.7-Setup.exe",
      browser_download_url: "https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/Blackboard-Sync-9.8.7-Setup.exe",
    },
  ],
};

function mockFetch(handler) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

test("records download for /mac with platform, country and referrer host", async () => {
  const restoreFetch = mockFetch(async () => Response.json(RELEASE_RESPONSE));
  try {
    const env = mockEnv();
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/mac", {
      headers: {
        referer: "https://blackboardsyncapp.com/tr/?utm_source=test",
        cookie: "session=sensitive_token",
        "cf-connecting-ip": "203.0.113.195",
      },
    });
    req.cf = { country: "TR" };

    const res = await worker.fetch(req, env, ctx);
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 302);
    assert.strictEqual(
      res.headers.get("Location"),
      "https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/Blackboard-Sync-9.8.7.dmg"
    );
    assert.strictEqual(env.dataPoints.length, 1);
    assert.deepStrictEqual(env.dataPoints[0], {
      blobs: ["mac", "TR", "blackboardsyncapp.com"],
      doubles: [1],
    });
  } finally {
    restoreFetch();
  }
});

test("records download for /windows and strips trailing slash", async () => {
  const restoreFetch = mockFetch(async () => Response.json(RELEASE_RESPONSE));
  try {
    const env = mockEnv();
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/windows/", {
      headers: {
        referer: "https://github.com/search?q=blackboard-sync",
      },
    });
    req.cf = { country: "US" };

    const res = await worker.fetch(req, env, ctx);
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 302);
    assert.strictEqual(
      res.headers.get("Location"),
      "https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/Blackboard-Sync-9.8.7-Setup.exe"
    );
    assert.strictEqual(env.dataPoints.length, 1);
    assert.deepStrictEqual(env.dataPoints[0], {
      blobs: ["windows", "US", "github.com"],
      doubles: [1],
    });
  } finally {
    restoreFetch();
  }
});

test("handles missing referer and country safely", async () => {
  const restoreFetch = mockFetch(async () => Response.json(RELEASE_RESPONSE));
  try {
    const env = mockEnv();
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/mac");

    const res = await worker.fetch(req, env, ctx);
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 302);
    assert.strictEqual(env.dataPoints.length, 1);
    assert.deepStrictEqual(env.dataPoints[0], {
      blobs: ["mac", "", ""],
      doubles: [1],
    });
  } finally {
    restoreFetch();
  }
});

test("handles invalid referer URL gracefully", async () => {
  const restoreFetch = mockFetch(async () => Response.json(RELEASE_RESPONSE));
  try {
    const env = mockEnv();
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/mac", {
      headers: {
        referer: "not a valid url",
      },
    });

    const res = await worker.fetch(req, env, ctx);
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 302);
    assert.strictEqual(env.dataPoints.length, 1);
    assert.deepStrictEqual(env.dataPoints[0], {
      blobs: ["mac", "", ""],
      doubles: [1],
    });
  } finally {
    restoreFetch();
  }
});

test("analytics write failure does not block or fail redirect", async () => {
  const restoreFetch = mockFetch(async () => Response.json(RELEASE_RESPONSE));
  try {
    const env = {
      DOWNLOADS: {
        writeDataPoint() {
          throw new Error("Analytics Engine quota exceeded");
        },
      },
      RELEASE_API: "https://api.github.com/repos/UmutYLCN/blackboard-sync/releases/latest",
      RELEASES_PAGE: "https://github.com/UmutYLCN/blackboard-sync/releases/latest",
    };
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/mac");

    const res = await worker.fetch(req, env, ctx);
    // Even if the scheduled promise runs, it shouldn't reject.
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 302);
    assert.strictEqual(
      res.headers.get("Location"),
      "https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/Blackboard-Sync-9.8.7.dmg"
    );
  } finally {
    restoreFetch();
  }
});

test("records download even when GitHub API fails and falls back to release page", async () => {
  const restoreFetch = mockFetch(async () => new Response("Error", { status: 503 }));
  try {
    const env = mockEnv();
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/mac");
    req.cf = { country: "DE" };

    const res = await worker.fetch(req, env, ctx);
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 302);
    assert.strictEqual(res.headers.get("Location"), env.RELEASES_PAGE);
    assert.strictEqual(res.headers.get("Cache-Control"), "no-store");
    assert.strictEqual(env.dataPoints.length, 1);
    assert.deepStrictEqual(env.dataPoints[0], {
      blobs: ["mac", "DE", ""],
      doubles: [1],
    });
  } finally {
    restoreFetch();
  }
});

test("static asset requests and video do not record download points", async () => {
  const env = mockEnv();
  const ctx = mockCtx();

  // Root path
  const rootReq = new Request("https://blackboardsyncapp.com/");
  const rootRes = await worker.fetch(rootReq, env, ctx);
  assert.strictEqual(rootRes.status, 200);

  // Video path
  const videoReq = new Request("https://blackboardsyncapp.com/assets/promo-mac-tr.mp4");
  await worker.fetch(videoReq, env, ctx);

  // Other path
  const otherReq = new Request("https://blackboardsyncapp.com/privacy");
  await worker.fetch(otherReq, env, ctx);

  await Promise.all(ctx.promises);
  assert.strictEqual(env.dataPoints.length, 0);
});

test("/stats.json sums .dmg and .exe across releases, ignores SHA256SUMS.txt, and includes Microsoft Store baseline", async () => {
  const releasesPage1 = [
    {
      tag_name: "v1.7.1",
      draft: false,
      assets: [
        { name: "Blackboard-Sync-1.7.1.dmg", download_count: 42 },
        { name: "Blackboard-Sync-1.7.1-Setup.exe", download_count: 35 },
        { name: "SHA256SUMS.txt", download_count: 99 },
      ],
    },
    {
      tag_name: "v1.7.2-draft",
      draft: true,
      assets: [
        { name: "Blackboard-Sync-1.7.2.dmg", download_count: 500 },
      ],
    },
  ];
  const releasesPage2 = [
    {
      tag_name: "v1.6.0",
      draft: false,
      assets: [
        { name: "Blackboard-Sync-1.6.0.dmg", download_count: 58 },
        { name: "Blackboard-Sync-1.6.0-Setup.exe", download_count: 43 },
        { name: "SHA256SUMS.txt", download_count: 50 },
        { name: "source.zip", download_count: 12 },
      ],
    },
  ];

  const fetchedUrls = [];
  const restoreFetch = mockFetch(async (url) => {
    fetchedUrls.push(String(url));
    if (new URL(String(url)).searchParams.get("page") === "1") {
      return new Response(JSON.stringify(releasesPage1), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          Link: '<https://api.github.com/repos/UmutYLCN/blackboard-sync/releases?per_page=100&page=2>; rel="next"',
        },
      });
    }
    return Response.json(releasesPage2);
  });

  try {
    const env = mockEnv();
    const ctx = mockCtx();
    const req = new Request("https://blackboardsyncapp.com/stats.json");

    const res = await worker.fetch(req, env, ctx);
    await Promise.all(ctx.promises);

    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.headers.get("Cache-Control"), "public, max-age=3600");
    assert.strictEqual(fetchedUrls.length, 2);
    assert.strictEqual(env.dataPoints.length, 0);

    const body = await res.json();
    assert.strictEqual(body.mac, 100);
    assert.strictEqual(body.windows, 78 + MICROSOFT_STORE_DOWNLOADS);
    assert.strictEqual(body.total, 178 + MICROSOFT_STORE_DOWNLOADS);
    assert.strictEqual(typeof body.updated, "string");
    assert.ok(!Number.isNaN(Date.parse(body.updated)));
  } finally {
    restoreFetch();
  }
});

test("/stats.json caches for one hour with the Cache API and returns last cached value on upstream error", async () => {
  const store = new Map();
  globalThis.caches = {
    default: {
      async match(req) {
        const hit = store.get(req.url);
        return hit ? hit.clone() : undefined;
      },
      async put(req, res) {
        store.set(req.url, res.clone());
      },
    },
  };

  let calls = 0;
  let shouldFail = false;
  const restoreFetch = mockFetch(async () => {
    calls += 1;
    if (shouldFail) {
      return new Response("Rate limit exceeded", { status: 403 });
    }
    return Response.json([
      {
        tag_name: "v1.7.1",
        assets: [
          { name: "Blackboard-Sync-1.7.1.dmg", download_count: 110 },
          { name: "Blackboard-Sync-1.7.1-Setup.exe", download_count: 90 },
        ],
      },
    ]);
  });

  const originalNow = Date.now;
  let now = 1_700_000_000_000;
  Date.now = () => now;

  try {
    const env = mockEnv();
    const ctx = mockCtx();

    // First call populates Cache API and isolate cache.
    const res1 = await worker.fetch(new Request("https://blackboardsyncapp.com/stats.json"), env, ctx);
    await Promise.all(ctx.promises);
    const data1 = await res1.json();
    assert.strictEqual(res1.status, 200);
    assert.strictEqual(calls, 1);
    assert.strictEqual(data1.total, 200 + MICROSOFT_STORE_DOWNLOADS);

    // Second call within 1 hour hits Cache API without calling upstream fetch.
    const res2 = await worker.fetch(new Request("https://blackboardsyncapp.com/stats.json"), env, ctx);
    const data2 = await res2.json();
    assert.strictEqual(res2.status, 200);
    assert.strictEqual(calls, 1);
    assert.deepStrictEqual(data2, data1);

    // Simulate 1-hour cache expiration + upstream failure: returns last cached value.
    store.delete("https://blackboardsyncapp.com/stats.json");
    now += 3601 * 1000;
    shouldFail = true;

    const res3 = await worker.fetch(new Request("https://blackboardsyncapp.com/stats.json"), env, ctx);
    const data3 = await res3.json();
    assert.strictEqual(res3.status, 200);
    assert.strictEqual(res3.headers.get("Cache-Control"), "no-store");
    assert.strictEqual(calls, 2);
    assert.deepStrictEqual(data3, data1);
  } finally {
    Date.now = originalNow;
    restoreFetch();
  }
});

test("/stats.json returns 503 on cold upstream error without breaking other routes", async () => {
  const restoreFetch = mockFetch(async (url) => {
    if (String(url).includes("/releases/latest")) {
      return Response.json(RELEASE_RESPONSE);
    }
    return new Response("Upstream error", { status: 502 });
  });

  try {
    const env = mockEnv();
    const ctx = mockCtx();

    const statsRes = await worker.fetch(new Request("https://blackboardsyncapp.com/stats.json"), env, ctx);
    assert.strictEqual(statsRes.status, 503);
    assert.strictEqual(statsRes.headers.get("Cache-Control"), "no-store");

    const macRes = await worker.fetch(new Request("https://blackboardsyncapp.com/mac"), env, ctx);
    assert.strictEqual(macRes.status, 302);
    assert.strictEqual(
      macRes.headers.get("Location"),
      "https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/Blackboard-Sync-9.8.7.dmg"
    );

    const homeRes = await worker.fetch(new Request("https://blackboardsyncapp.com/"), env, ctx);
    assert.strictEqual(homeRes.status, 200);
  } finally {
    restoreFetch();
  }
});
