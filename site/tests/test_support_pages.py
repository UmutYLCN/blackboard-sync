"""Guard: /support and /tr/support exist and every page links to them from the footer.

Static checks with the standard library only, so they run without a browser or server.
"""
from html.parser import HTMLParser
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent
ISSUES = 'https://github.com/UmutYLCN/blackboard-sync/issues'
PAGES = {'en': ('support.html', '/support', '/privacy'), 'tr': ('tr/support.html', '/tr/support', '/tr/privacy')}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.footer = False
        self.footer_hrefs = []
        self.hrefs = []
        self.lang = None
        self.has_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.lang = attrs.get('lang')
        if tag == 'footer':
            self.footer = True
        if tag == 'h1':
            self.has_h1 = True
        if tag == 'a' and attrs.get('href'):
            self.hrefs.append(attrs['href'])
            if self.footer:
                self.footer_hrefs.append(attrs['href'])

    def handle_endtag(self, tag):
        if tag == 'footer':
            self.footer = False


def parse(page):
    parser = Links()
    parser.feed((SITE / page).read_text(encoding='utf-8'))
    return parser


@pytest.mark.parametrize('lang', PAGES)
def test_support_page_exists_and_links_out(lang):
    page, own, privacy = PAGES[lang]
    parser = parse(page)
    assert parser.lang == lang and parser.has_h1
    for href in (privacy, ISSUES, '/support', '/tr/support'):
        assert href in parser.hrefs, f'{page} must link to {href}'
    text = (SITE / page).read_text(encoding='utf-8')
    assert '@' not in text.replace('@media', ''), f'{page} must not show an email address'
    assert '<script' not in text and 'style=' not in text, f'{page} must stay CSP-safe'


@pytest.mark.parametrize('page,support', [('index.html', '/support'), ('privacy.html', '/support'),
                                          ('support.html', '/support'),
                                          ('tr/index.html', '/tr/support'), ('tr/privacy.html', '/tr/support'),
                                          ('tr/support.html', '/tr/support')])
def test_footer_links_to_support(page, support):
    assert support in parse(page).footer_hrefs, f'{page}: footer must link to {support}'
