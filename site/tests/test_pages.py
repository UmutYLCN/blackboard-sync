"""Browser checks against the real Wrangler asset server; no application imports."""
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from store_link import STORE_URL

BASE = os.environ.get('SITE_BASE_URL', 'http://127.0.0.1:8792').rstrip('/')
RELEASE_PAGE = 'https://github.com/UmutYLCN/blackboard-sync/releases/latest'
DOWNLOAD = 'https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/'
API = 'https://api.github.com/repos/UmutYLCN/blackboard-sync/releases/latest'
RELEASE = {'tag_name': 'v9.8.7', 'assets': [
    {'name': 'Blackboard-Sync-9.8.7.dmg', 'browser_download_url': DOWNLOAD + 'Blackboard-Sync-9.8.7.dmg'},
    {'name': 'Blackboard-Sync-9.8.7-Setup.exe', 'browser_download_url': DOWNLOAD + 'Blackboard-Sync-9.8.7-Setup.exe'},
]}
STATS = {'total': 746, 'mac': 100, 'windows': 646, 'updated': '2026-11-11T00:00:00Z'}


@pytest.fixture(scope='session')
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


def context_for(browser, *, width=1440, javascript=True, release_ok=True, stats_ok=True, stats=STATS):
    context = browser.new_context(viewport={'width': width, 'height': 900},
                                  reduced_motion='reduce', java_script_enabled=javascript)
    context.route(API, lambda route: route.fulfill(status=200 if release_ok else 503,
                                                   json=RELEASE if release_ok else {}))
    context.route('**/stats.json', lambda route: route.fulfill(
        status=200 if stats_ok else 503,
        json=stats if stats_ok else {'error': 'unavailable'},
    ))
    # Layout tests do not need the MP4.
    context.route('**/*.mp4', lambda route: route.abort())
    return context


def capture(page, name):
    directory = os.environ.get('SITE_SCREENSHOT_DIR')
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path / f'{name}.png'), full_page=page.viewport_size['width'] >= 700)


@pytest.mark.parametrize('locale,path,heading', [
    ('en', '/', 'Your course files.'),
    ('tr', '/tr/', 'Ders dosyaların.'),
])
@pytest.mark.parametrize('width', [1440, 375, 320])
def test_home_layout_downloads_and_scrolling(browser, locale, path, heading, width):
    with context_for(browser, width=width) as context:
        page = context.new_page()
        errors, missing = [], []
        page.on('pageerror', lambda error: errors.append(error))
        page.on('response', lambda response: missing.append(response.url)
                if response.url.startswith(BASE) and response.status >= 400 else None)
        assert page.goto(BASE + path).status == 200
        expect(page.locator('html')).to_have_attribute('lang', locale)
        expect(page.locator('h1')).to_contain_text(heading)
        expect(page.locator('.language-switch a[aria-current="page"]')).to_have_text(locale.upper())
        expect(page.locator('.nav-github')).to_be_visible()
        expect(page.locator('.hero a[href="https://github.com/UmutYLCN/blackboard-sync"]')).to_have_count(0)
        expect(page.locator('#download-macos')).to_have_attribute('href', DOWNLOAD + 'Blackboard-Sync-9.8.7.dmg')
        expect(page.locator('[data-version="macos"]')).to_contain_text('v9.8.7')
        # The Windows button is the Microsoft Store listing; script.js must leave it alone.
        expect(page.locator('#download-windows')).to_have_attribute('href', STORE_URL)
        expected_stats = '700+ downloads' if locale == 'en' else '700+ indirme'
        expect(page.locator('#download-stats')).to_be_visible()
        expect(page.locator('#download-stats')).to_have_text(expected_stats)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow at {width}px'
        capture(page, f'{locale}-home-{width}')
        page.evaluate('window.scrollTo({top: 1000, behavior: "instant"})')
        page.wait_for_function('document.querySelector(".site-header").getBoundingClientRect().bottom < 0')
        assert not errors
        assert not missing


@pytest.mark.parametrize('javascript', [True, False])
def test_language_navigation_keeps_the_corresponding_page(browser, javascript):
    with context_for(browser, javascript=javascript) as context:
        page = context.new_page()
        page.goto(BASE + '/')
        page.get_by_role('link', name='Türkçe', exact=True).click()
        expect(page).to_have_url(BASE + '/tr/')
        expect(page.locator('html')).to_have_attribute('lang', 'tr')
        page.locator('.site-footer').get_by_role('link', name='Gizlilik', exact=True).click()
        expect(page).to_have_url(BASE + '/tr/privacy')
        expect(page.locator('h1')).to_have_text('Gizlilik Politikası')
        page.get_by_role('link', name='English', exact=True).click()
        expect(page).to_have_url(BASE + '/privacy')
        expect(page.locator('h1')).to_have_text('Privacy Policy')
        page.locator('.site-header .brand').click()
        expect(page).to_have_url(BASE + '/')


@pytest.mark.parametrize('locale,path,label', [('en', '/', 'Latest version'), ('tr', '/tr/', 'Son sürüm')])
def test_release_api_failure_preserves_localized_download_fallback(browser, locale, path, label):
    with context_for(browser, release_ok=False) as context:
        page = context.new_page()
        page.goto(BASE + path)
        expect(page.locator('#download-macos')).to_have_attribute('href', RELEASE_PAGE)
        expect(page.locator('[data-version="macos"]')).to_contain_text(label)
        expect(page.locator('#download-windows')).to_have_attribute('href', STORE_URL)


@pytest.mark.parametrize('locale,path,expected', [
    ('en', '/', '1,500+ downloads'),
    ('tr', '/tr/', '1.500+ indirme'),
])
def test_download_counter_rounds_down_and_formats_for_language(browser, locale, path, expected):
    stats = {'total': 1589, 'mac': 621, 'windows': 968, 'updated': '2026-11-11T00:00:00Z'}
    with context_for(browser, stats=stats) as context:
        page = context.new_page()
        page.goto(BASE + path)
        counter = page.locator('#download-stats')
        expect(counter).to_be_visible()
        expect(counter).to_have_text(expected)
        expect(counter).to_have_attribute('data-total', '1589')
        expect(counter).to_have_attribute('data-mac', '621')
        expect(counter).to_have_attribute('data-windows', '968')


@pytest.mark.parametrize('locale,path', [('en', '/'), ('tr', '/tr/')])
@pytest.mark.parametrize('kwargs', [
    {'stats_ok': False},
    {'stats': {'total': 99, 'mac': 40, 'windows': 59, 'updated': '2026-11-11T00:00:00Z'}},
    {'javascript': False},
])
def test_download_counter_stays_hidden_when_unavailable_below_minimum_or_no_js(browser, locale, path, kwargs):
    with context_for(browser, **kwargs) as context:
        page = context.new_page()
        page.goto(BASE + path)
        expect(page.locator('#download-stats')).to_be_hidden()
        expect(page.locator('.hero-note')).to_be_visible()


def test_stats_json_route_returns_cached_release_totals(browser):
    with browser.new_context() as context:
        response = context.request.get(BASE + '/stats.json')
        assert response.status == 200
        assert 'application/json' in response.headers.get('content-type', '')
        assert 'max-age=3600' in response.headers.get('cache-control', '')
        payload = response.json()
        assert payload['mac'] >= 0
        assert payload['windows'] >= 568
        assert payload['total'] == payload['mac'] + payload['windows']
        assert isinstance(payload['updated'], str) and payload['updated']


@pytest.mark.parametrize('locale,path', [('en', '/privacy'), ('tr', '/tr/privacy')])
def test_privacy_mobile_layout_and_metadata(browser, locale, path):
    with context_for(browser, width=320) as context:
        page = context.new_page()
        assert page.goto(BASE + path).status == 200
        expect(page.locator('html')).to_have_attribute('lang', locale)
        expect(page.locator('link[rel="canonical"]')).to_have_attribute(
            'href', 'https://blackboardsyncapp.com' + path)
        expect(page.locator('link[rel="alternate"][hreflang="tr"]')).to_have_attribute(
            'href', 'https://blackboardsyncapp.com/tr/privacy')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        capture(page, f'{locale}-privacy-320')


@pytest.mark.parametrize('path', ['/gizlilik', '/gizlilik.html', '/gizlilik/'])
def test_old_turkish_privacy_links_redirect_to_turkish(browser, path):
    with browser.new_context() as context:
        response = context.request.get(BASE + path, max_redirects=0)
        assert response.status == 301
        assert response.headers['location'].endswith('/tr/privacy')


@pytest.mark.parametrize('path,suffix', [
    ('/mac', '.dmg'),
    ('/mac/', '.dmg'),
    ('/windows', '-Setup.exe'),
    ('/windows/', '-Setup.exe'),
])
def test_short_download_links_redirect_to_release_asset(browser, path, suffix):
    with browser.new_context() as context:
        response = context.request.get(BASE + path, max_redirects=0)
        assert response.status == 302
        location = response.headers['location']
        assert location.startswith('https://github.com/UmutYLCN/blackboard-sync/releases/download/')
        assert location.endswith(suffix)
        assert 'public' in response.headers.get('cache-control', '')


def test_promo_video_answers_byte_ranges(browser):
    """Safari plays the video only from 206 responses."""
    with browser.new_context() as context:
        whole = context.request.get(BASE + '/assets/promo-mac-tr.mp4')
        assert whole.status == 200
        assert whole.headers['accept-ranges'] == 'bytes'
        size = len(whole.body())
        first = context.request.get(BASE + '/assets/promo-mac-tr.mp4', headers={'Range': 'bytes=0-1'})
        assert first.status == 206
        assert first.headers['content-range'] == f'bytes 0-1/{size}'
        assert first.body() == whole.body()[:2]
        last = context.request.get(BASE + '/assets/promo-mac-tr.mp4', headers={'Range': 'bytes=-100'})
        assert last.status == 206
        assert last.body() == whole.body()[-100:]
        past = context.request.get(BASE + '/assets/promo-mac-tr.mp4', headers={'Range': f'bytes={size}-'})
        assert past.status == 416
