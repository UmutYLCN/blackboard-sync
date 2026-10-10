// Keep the release-page links usable when JavaScript or the GitHub API is unavailable.
(async () => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch('https://api.github.com/repos/UmutYLCN/blackboard-sync/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' },
      signal: controller.signal,
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
    });
    if (!response.ok) return;
    const release = await response.json();
    if (!Array.isArray(release.assets) || typeof release.tag_name !== 'string') return;
    const platforms = [
      { id: 'macos', suffix: '.dmg', extension: '.dmg' },
      { id: 'windows', suffix: '-Setup.exe', extension: '.exe' },
    ];
    for (const platform of platforms) {
      const asset = release.assets.find(item => typeof item.name === 'string' && item.name.endsWith(platform.suffix));
      if (!asset || typeof asset.browser_download_url !== 'string') continue;
      const url = new URL(asset.browser_download_url);
      if (url.origin !== 'https://github.com' || !url.pathname.startsWith('/UmutYLCN/blackboard-sync/releases/download/')) continue;
      document.getElementById(`download-${platform.id}`).href = url.href;
      document.querySelector(`[data-version="${platform.id}"]`).textContent = `${platform.extension} · ${release.tag_name}`;
    }
  } catch {
    // The static links already lead to the latest release, including during rate limits.
  } finally {
    clearTimeout(timeout);
  }
})();

const video = document.getElementById('promo-video');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
function applyMotionPreference() {
  video.autoplay = !reducedMotion.matches;
  if (reducedMotion.matches) {
    video.pause();
  } else {
    video.play().catch(() => {}); // Native controls remain available if autoplay is blocked.
  }
}
applyMotionPreference();
reducedMotion.addEventListener('change', applyMotionPreference);
