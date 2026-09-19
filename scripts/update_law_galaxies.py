"""Refresh both independent galaxies; never touch bill-review or original checkout data."""
import argparse
import json
from core.fsc_collection import CollectionError
from core.galaxy_updates import run

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('auto','daily','full'),default='auto')
    parser.add_argument('--check-only',action='store_true',help='compare official inventories without replacing active data')
    args=parser.parse_args()
    try:
        result=run(mode=args.mode,check_only=args.check_only)
    except (CollectionError,OSError,ValueError,KeyError,TypeError):
        result={'status':'failed','message':'로컬 설정 또는 갱신 상태를 확인해 주세요. 기존 자료는 유지됩니다.'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['status']=='failed' else 0

if __name__=='__main__': raise SystemExit(main())
