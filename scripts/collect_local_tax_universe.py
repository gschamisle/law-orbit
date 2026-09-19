"""Collect and build the independent local-tax corpus. Credentials stay local."""
from __future__ import annotations
import argparse
from datetime import date
from pathlib import Path
from core.fsc_credentials import law_api_key
from core.fsc_collection import CollectionError, LawTransport
from core.local_tax_collection import OUTPUT, collect_all, read


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--workers',type=int,choices=range(1,5),default=3)
    parser.add_argument('--collect-only',action='store_true')
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--as-of',default=date.today().strftime('%Y%m%d'))
    args=parser.parse_args()
    if args.collect_only and args.build_only: parser.error('choose one mode')
    if not args.build_only:
        key=law_api_key()
        if not key:
            raise SystemExit('법제처 인증 설정 없음: 프로젝트 .env의 LAW_API_KEY 또는 LAW_OC')
        try:
            report=collect_all(LawTransport(key,reuse_connections=True),args.output,as_of=args.as_of,workers=args.workers)
        except CollectionError as error:
            raise SystemExit('수집 중단 · 기존 공개 자료 유지 · '+str(error)) from None
        print(f"수집 완료 · 분석 가능 {report['indexed']} · 확인 필요 {len(report['failed'])}",flush=True)
    if not args.collect_only:
        from core.local_tax_graph import publish
        report=publish(args.output,args.as_of)
        print(f"지방세 은하 생성 완료 · 중앙 {report['central_documents']} · 자치법규 {report['indexed']} · 지역 {len(report['regions'])}",flush=True)


if __name__=='__main__': main()
