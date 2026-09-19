"""Official FSS bylaw discovery, with strict issuer and edition validation."""
from __future__ import annotations
import hashlib
from core.fsc_collection import CollectionError, field, xml_root, list_record, norm, ymd

# Names verified in the law.go.kr current administrative-rule list. This is an
# explicit collection scope, not a claim to cover all FSS internal regulations.
BYLAWS = (
 '보험업감독업무시행세칙', '은행업감독업무시행세칙', '금융투자업규정시행세칙',
 '보험사기방지업무 시행세칙', '증권의 발행 및 공시 등에 관한 규정 시행세칙',
 '금융기관 검사 및 제재에 관한 규정 시행세칙', '금융소비자보호에 관한 감독규정 시행세칙',
 '금융회사 지배구조 감독규정 시행세칙', '금융지주회사감독규정시행세칙',
 '퇴직연금감독규정시행세칙', '금융복합기업집단 감독규정 시행세칙',
 '여신전문금융업감독업무시행세칙', '상호금융업감독업무시행세칙', '상호저축은행업감독업무시행세칙',
 '대부업등 감독규정 시행세칙', '개인채무자보호법 감독업무 시행세칙', '신용정보업감독업무시행세칙',
 '전자금융감독규정시행세칙', '가상자산업 감독규정 시행세칙', '가상자산시장조사업무규정 시행세칙',
 '온라인투자연계금융업 감독규정 시행세칙', '혁신금융심사위원회 운영 등에 관한 규정 시행세칙',
 '금융거래지표 관리 감독규정 시행세칙', '금융회사등의해외진출에관한규정시행세칙',
 '외부감사 및 회계 등에 관한 규정 시행세칙', '자본시장조사 업무규정 시행세칙',
 '전기통신금융사기 피해 방지 및 신고포상금에 관한 규정 시행세칙', '한국주택금융공사감독규정시행세칙',
)

def discover_bylaws(request, *, as_of: str, display: int = 100) -> dict:
    as_of = ymd(as_of)
    wanted = {norm(n) for n in BYLAWS}
    received, expected, hashes, selected, seen = 0, None, [], [], set()
    for page in range(1, 101):
        raw = request('lawSearch.do', dict(target='admrul', query='시행세칙', nw=1, display=display, page=page, sort='lasc'))
        root = xml_root(raw)
        if root.tag != 'AdmRulSearch':
            raise CollectionError('unexpected-bylaw-envelope')
        try:
            count, actual_page = int(field(root,'totalCnt')), int(field(root,'page'))
        except ValueError:
            raise CollectionError('missing-bylaw-pagination') from None
        if count < 0 or actual_page != page or (expected is not None and count != expected):
            raise CollectionError('bylaw-pagination-changed')
        expected = count
        rows = root.findall('admrul')
        if len(rows) != min(display, max(0, count-received)):
            raise CollectionError('short-bylaw-page')
        received += len(rows)
        hashes.append(hashlib.sha256(raw).hexdigest())
        for row in rows:
            ident = field(row,'행정규칙ID')
            if not ident or ident in seen:
                raise CollectionError('duplicate-bylaw-inventory')
            seen.add(ident)
            if norm(field(row,'행정규칙명')) in wanted and field(row,'소관부처명') == '금융감독원':
                selected.append(list_record(row, 'admrul', as_of, fss=True))
        if received == expected:
            if {norm(r['name']) for r in selected} != wanted:
                raise CollectionError('requested-bylaw-missing-from-current-list')
            return dict(provider='admrul', scope='fss-sector-bylaws', as_of=as_of,
                        list_status='complete', expected=len(selected), received=len(selected), records=selected,
                        search_query='시행세칙', search_received=received, search_expected=expected,
                        pages=page, page_sha256=hashes, requested_names=list(BYLAWS))
    raise CollectionError('bylaw-page-limit')
