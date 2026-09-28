"""Collect a scoped medical corpus; attach only verified official annex samples."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from core.fsc_collection import ymd
from scripts.collect_mofe_universes import run
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=('inventory','bodies','build'),required=True)
    p.add_argument('--date')
    a=p.parse_args();today=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    stamp=ymd(a.date or today)
    if stamp>today:raise ValueError('Future collection date')
    raise SystemExit(run('medical',a.stage,stamp))
