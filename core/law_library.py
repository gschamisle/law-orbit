"""Read-only helpers for browsing collected provision bodies."""
from __future__ import annotations
from urllib.parse import urlencode
from core.citation_scope import Provision
from core.galaxy_focus import _target


def article_label(article: dict) -> str:
    return Provision(str(article['jo'])).label + ' · ' + article.get('title', '')


def matching_articles(document: dict, query: str) -> list[dict]:
    tokens = [''.join(t.split()).casefold() for t in query.split()]
    return [a for a in document.get('articles', [])
            if all(t in ''.join((article_label(a) + ' ' + a.get('text', '')).split()).casefold()
                   for t in tokens)]


def provision_choices(article: dict) -> list[str]:
    """Only offer subprovisions actually present in the collected structure."""
    base = Provision(str(article['jo'])).label
    refs = [base]
    for block in article.get('blocks', []):
        try:
            target = _target(block['ref'], allow_hyphen=True)
        except (ValueError, KeyError):
            continue
        if target.jo == str(article['jo']) and target.label not in refs:
            refs.append(target.label)
    return refs


def official_url(document: dict) -> str:
    if document.get('source_url'):
        return document['source_url']
    if document.get('mst'):
        return 'https://www.law.go.kr/LSW/lsInfoP.do?' + urlencode(
            {'lsiSeq': document['mst'], 'efYd': document.get('effective', '')})
    return ''


def collected_text(document: dict) -> str:
    return '\n\n'.join([document['name'], '시행일: ' + document.get('effective', '확인 필요')]
                       + [a.get('text', '') for a in document.get('articles', [])])
