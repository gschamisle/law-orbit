"""Reviewed annual announcement changes, not a live institution designation register."""
import hashlib,json
from pathlib import Path
from core.fsc_collection import norm

SOURCE=Path(__file__).resolve().parents[1]/'data/public-institutions/designation-changes.json'

def validate(register):
    sources={s['id']:s for s in register['sources']}
    if len(sources)!=len(register['sources']):raise ValueError('duplicate-designation-source')
    ids=set()
    for event in register['events']:
        s=sources[event['source_id']]
        if event['id'] in ids:raise ValueError('duplicate-designation-event')
        ids.add(event['id'])
        if event['effective'] is not None:raise ValueError('announcement-is-not-effective-date')
        if s['page_text'][event['start']:event['end']]!=event['raw'] or norm(event['name']) not in norm(event['raw']):raise ValueError('designation-excerpt-mismatch')
        if event['after'] not in ('공기업','준정부기관','기타공공기관'):raise ValueError('designation-type-unknown')
        if event['kind']=='new' and event['before'] is not None:raise ValueError('new-designation-previous-type-guessed')
        if event['kind']=='changed' and event['before'] not in ('공기업','준정부기관','기타공공기관'):raise ValueError('designation-previous-type-missing')
        if event['year']!=s['year']:raise ValueError('designation-year-mismatch')
    for s in sources.values():
        if hashlib.sha256(s['page_text'].encode()).hexdigest()!=s['text_sha256']:raise ValueError('designation-source-mismatch')
        events=[e for e in register['events'] if e['source_id']==s['id']]
        if sum(e['kind']=='new' for e in events)!=s['new_count'] or sum(e['kind']=='changed' for e in events)!=s['changed_count']:raise ValueError('designation-count-mismatch')
    return register

def load(path=SOURCE):return validate(json.loads(Path(path).read_text(encoding='utf-8')))

def review_candidates(scope, event):
    """All anchor groups remain inspectable; type changes prioritize subset wording."""
    rows=[r for r in scope['records'] if r['kind']=='scope']
    return sorted(rows,key=lambda r:('subset' not in r['labels'] if event['kind']=='changed' else r['target_jo'] not in ('4','6'),r['source_law'],r['source_jo']))
