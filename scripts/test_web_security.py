"""Offline checks for the generated CSP and untrusted map payload boundary."""

import base64
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import tempfile
import unittest

from core.web_security import content_policy, secure_html
from core.law_galaxy import render_page
from scripts.build_static_galaxies import shell

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.policies = []
        self.scripts = []
        self.current = None
        self.feed(html.replace('\r\n', '\n').replace('\r', '\n'))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy':
            self.policies.append(attrs['content'])
        if tag == 'script' and not attrs.get('src'):
            self.current = ''

    def handle_data(self, data):
        if self.current is not None:
            self.current += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.scripts.append(self.current)
            self.current = None


class WebSecurityTests(unittest.TestCase):
    def check_scripts(self, html):
        page = Page(html)
        self.assertEqual(len(page.policies), 1)
        policy = page.policies[0]
        directives = dict(p.strip().split(' ', 1) for p in policy.split(';'))
        self.assertNotIn('unsafe-inline', directives['script-src'])
        self.assertNotIn('unsafe-eval', policy)
        self.assertEqual(directives['object-src'], "'none'")
        self.assertEqual(directives['script-src-attr'], "'none'")
        for script in page.scripts:
            digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
            self.assertIn("'sha256-" + digest + "'", directives['script-src'])
        return page

    def test_hash_matches_browser_newline_normalization(self):
        html = '<meta charset="utf-8"><script>\r\nconst x="한글 & 값";\r\n</script>'
        self.check_scripts(secure_html(html))
        self.assertEqual(content_policy(html), content_policy(html.replace('\r\n', '\n')))

    def test_changed_script_is_not_authorized_by_old_hash(self):
        html = secure_html('<meta charset="utf-8"><script>const x=1;</script>')
        changed = html.replace('const x=1;', 'const x=2;')
        digest = base64.b64encode(hashlib.sha256(b'const x=2;').digest()).decode()
        self.assertNotIn("'sha256-" + digest + "'", Page(changed).policies[0])

    def test_counter_is_image_only_and_main_has_no_inline_code(self):
        html = (ROOT/'web/index.html').read_text(encoding='utf-8')
        page = self.check_scripts(html)
        self.assertEqual(page.scripts, [])
        self.assertIn('img-src \'self\' data: https://hits.sh', page.policies[0])
        self.assertNotRegex(page.policies[0], r'script-src[^;]*hits')
        self.assertLess(html.index('Content-Security-Policy'), html.index('<link'))

    def test_standalone_payload_cannot_close_script(self):
        attack = '</script><img src=x onerror="alert(1)"><script>'
        page = self.check_scripts(render_page(dict(nodes=[], links=[], galaxy_title=attack)))
        self.assertEqual(len(page.scripts), 2)
        self.assertTrue(any('\\u003c/script\\u003e' in s for s in page.scripts))
        self.assertFalse(any('<img src=x' in s for s in page.scripts))

    def test_public_renderer_hashes_and_message_boundary_survive_formatting(self):
        with tempfile.TemporaryDirectory() as folder:
            shell(Path(folder))
            html = (Path(folder)/'renderer.html').read_text(encoding='utf-8')
            page = self.check_scripts(html)
            self.assertEqual(len(page.scripts), 2)
            self.assertNotIn('__DATA__', html)
            self.assertNotIn('__GESTURES__', html)
            self.assertNotIn('PUBLIC_MAP_', html)
            self.assertIn('event.source!==parent||event.origin!==location.origin', html)
            self.assertIn("type:'galaxy-select'", html)
            self.check_scripts((Path(folder)/'introduction.html').read_text(encoding='utf-8'))

    def test_missing_charset_fails_closed(self):
        with self.assertRaises(ValueError):
            secure_html('<script>1</script>')


if __name__ == '__main__':
    unittest.main()
