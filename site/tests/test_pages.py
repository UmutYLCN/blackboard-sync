"""Browser checks against the real Wrangler asset server; no application imports."""
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('SITE_BASE_URL', 'http://127.0.0.1:8792').rstrip('/')
RELEASE_PAGE = 'https://github.com/UmutYLCN/blackboard-sync/releases/latest'
DOWNLOAD = 'https://github.com/UmutYLCN/blackboard-sync/releases/download/v9.8.7/'
API = 'https://api.github.com/repos/UmutYLCN/blackboard-sync/releases/latest'
RELEASE = {'tag_name': 'v9.8.7', 'assets': [
    {'name': 'Blackboard-Sync-9.8.7.dmg', 'browser_download_url': DOWNLOAD + 'Blackboard-Sync-9.8.7.dmg'},
    {'name': 'Blackboard-Sync-9.8.7-Setup.exe', 'browser_download_url': DOWNLOAD + 'Blackboard-Sync-9.8.7-Setup.exe'},
]}


@pytest.fixture(scope='session')
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


def context_for(browser, *, width=1440, javascript=True, release_ok=True):
    context = browser.new_context(viewport={'width': width, 'height': 900},
                                  reduced_motion='reduce', java_script_enabled=javascript)
    context.route(API, lambda route: route.fulfill(status=200 if release_ok else 503,
                                                   json=RELEASE if release_ok else {}))
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
        for platform, filename in [('macos', 'Blackboard-Sync-9.8.7.dmg'),
                                   ('windows', 'Blackboard-Sync-9.8.7-Setup.exe')]:
            expect(page.locator(f'#download-{platform}')).to_have_attribute('href', DOWNLOAD + filename)
            expect(page.locator(f'[data-version="{platform}"]')).to_contain_text('v9.8.7')
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
        for platform in ('macos', 'windows'):
            expect(page.locator(f'#download-{platform}')).to_have_attribute('href', RELEASE_PAGE)
            expect(page.locator(f'[data-version="{platform}"]')).to_contain_text(label)


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
