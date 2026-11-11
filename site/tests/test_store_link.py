"""Guard: the Windows download button stays on the Microsoft Store listing.

Static checks with the standard library only, so they run without a browser or server.
test_pages.py also checks the live href after script.js has run.
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from store_link import STORE_URL

SITE = Path(__file__).resolve().parent.parent


class WindowsButton(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.windows_version_labels = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('id') == 'download-windows':
            self.hrefs.append(attrs.get('href'))
        if attrs.get('data-version') == 'windows':
            self.windows_version_labels += 1


@pytest.mark.parametrize('page', ['index.html', 'tr/index.html'])
def test_windows_button_links_to_the_store(page):
    parser = WindowsButton()
    parser.feed((SITE / page).read_text(encoding='utf-8'))
    assert parser.hrefs == [STORE_URL], f'{page}: #download-windows must link to {STORE_URL}'
    # A data-version="windows" label invites script.js to fill it from a GitHub release again.
    assert parser.windows_version_labels == 0, f'{page}: Windows button has a release version label'


def test_script_does_not_rewrite_the_windows_button():
    script = (SITE / 'script.js').read_text(encoding='utf-8')
    for pattern in [r'download-windows', r'''id:\s*['"`]windows['"`]''',
                    r'''data-version=["']?windows''', r'Setup\.exe']:
        assert not re.search(pattern, script), f'script.js touches the Windows button ({pattern})'


def test_worker_does_not_rewrite_the_pages():
    worker = (SITE / 'worker' / 'index.js').read_text(encoding='utf-8')
    assert 'HTMLRewriter' not in worker
    assert 'download-windows' not in worker
    # The Worker sees only the short links and the video; pages are served as static assets.
    config = (SITE / 'wrangler.jsonc').read_text(encoding='utf-8')
    routes = json.loads(re.search(r'"run_worker_first"\s*:\s*(\[[^\]]*\])', config).group(1))
    assert set(routes) <= {'/mac', '/mac/', '/windows', '/windows/', '/assets/*.mp4'}, routes
