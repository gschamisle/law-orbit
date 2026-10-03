"""CSP for generated public/standalone HTML, without allowing arbitrary scripts."""

import base64
import hashlib
from html import escape
from html.parser import HTMLParser
import re


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not dict(attrs).get("src"):
            self.current = ""

    def handle_data(self, data):
        if self.current is not None:
            self.current += data

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append(self.current)
            self.current = None


def content_policy(html: str = "", *, counter: bool = False) -> str:
    """Hash exact inline scripts; browser HTML parsing normalizes CRLF to LF."""
    parser = _Scripts()
    parser.feed(html.replace("\r\n", "\n").replace("\r", "\n"))
    hashes = sorted({
        "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
        for s in parser.scripts
    })
    # Existing layout uses style attributes and dynamically assigned canvas styles.
    # Script execution stays hash/self-only; no unsafe-inline or unsafe-eval scripts.
    return "; ".join([
        "default-src 'none'",
        "script-src " + " ".join(["'self'", *hashes]),
        "script-src-attr 'none'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:" + (" https://hits.sh" if counter else ""),
        "font-src 'self' data:",
        "connect-src 'self'",
        "worker-src 'self'",
        "frame-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ])


def secure_html(html: str, *, counter: bool = False) -> str:
    """Insert policy immediately after charset, before executable content."""
    if "http-equiv=\"Content-Security-Policy\"" in html:
        raise ValueError("Document already has a content security policy")
    policy = escape(content_policy(html, counter=counter), quote=True)
    meta = f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
    result, count = re.subn(r"(<meta\s+charset=['\"]?utf-8['\"]?\s*/?>)",
                            lambda m: m[0] + meta, html, count=1, flags=re.I)
    if count != 1:
        raise ValueError("Expected an early UTF-8 charset declaration")
    return result
