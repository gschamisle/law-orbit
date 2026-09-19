"""Bounded tax-law universe, separate from the uploaded-bill review corpus."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / 'data/law-galaxy-graph.json'
SOURCES = ROOT / 'data/law-galaxy-sources.json'
LEGACY = ROOT / 'data/law-citation-graph.json'
LIVE_BUNDLE = ROOT / 'output/tax-universe/bundle.json'
NEW_TAX = ['증권거래세법', '개별소비세법', '교육세법', '주세법', '교통ㆍ에너지ㆍ환경세법', '인지세법']
EXTERNAL = [
    '상법', '자본시장과 금융투자업에 관한 법률', '중소기업기본법', '독점규제 및 공정거래에 관한 법률',
    '민법', '채무자 회생 및 파산에 관한 법률', '민사집행법', '주식회사 등의 외부감사에 관한 법률', '신탁법',
    '벤처투자 촉진에 관한 법률', '벤처기업육성에 관한 특별법', '중소기업창업 지원법',
    '민간임대주택에 관한 특별법', '주택법', '도시 및 주거환경정비법', '공공주택 특별법',
    '빈집 및 소규모주택 정비에 관한 특례법', '은행법', '보험업법', '여신전문금융업법', '근로자퇴직급여 보장법',
]
COURT_RULES = ['민사집행규칙', '채무자 회생 및 파산에 관한 규칙']


def norm(name):
    return ''.join(str(name).split()).replace('ㆍ', '').replace('·', '')


def graph_path():
    if LIVE_BUNDLE.is_file():
        return LIVE_BUNDLE
    return GRAPH if GRAPH.exists() else LEGACY


def load_graph():
    return json.loads(graph_path().read_text(encoding='utf-8'))
