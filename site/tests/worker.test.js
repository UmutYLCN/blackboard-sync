import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import worker, { resetCache } from "../worker/index.js";

beforeEach(() => {
  resetCache();
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
