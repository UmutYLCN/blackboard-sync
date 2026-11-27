"""Guard: site/min-version.json is valid schema-1 JSON served uncached as a static asset.

Static checks with the standard library only, so they run without a browser or server.
"""
import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
ALLOWED_MINIMUM_KEYS = {'macos', 'windows', 'mas'}
ALLOWED_TOP_KEYS = {'schema', 'minimum', 'dmg_retired', 'mas_url'}


def test_min_version_json_has_valid_schema_and_versions():
    data = json.loads((SITE / 'min-version.json').read_text(encoding='utf-8'))
    assert set(data) <= ALLOWED_TOP_KEYS
    assert type(data.get('schema')) is int and data['schema'] == 1
    minimum = data.get('minimum')
    assert isinstance(minimum, dict)
    assert {'macos', 'windows'} <= set(minimum) <= ALLOWED_MINIMUM_KEYS
    for key, version in minimum.items():
        assert isinstance(version, str) and VERSION_RE.match(version), f'{key}: invalid version {version!r}'
    assert type(data.get('dmg_retired')) is bool
    mas_url = data.get('mas_url')
    assert isinstance(mas_url, str) and mas_url.startswith('https://apps.apple.com/')
    assert not any(ch.isspace() for ch in mas_url)


def test_min_version_json_is_published_uncached_without_cors():
    ignored = {
        line.strip()
        for line in (SITE / '.assetsignore').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.strip().startswith('#')
    }
    assert 'min-version.json' not in ignored

    headers = (SITE / '_headers').read_text(encoding='utf-8')
    match = re.search(r'^/min-version\.json\n((?:  .+\n?)+)', headers, re.M)
    assert match is not None, 'missing /min-version.json section in site/_headers'
    block = match.group(1)
    assert 'Cache-Control: no-cache, max-age=0' in block
    assert 'Access-Control-Allow-Origin' not in headers
