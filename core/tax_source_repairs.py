"""Apply reviewed, same-edition source corrections with exact hash gates."""
from copy import deepcopy
import hashlib


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def apply_repairs(source, plan):
    if plan.get('schema') != 1:
        raise ValueError('Unknown source repair plan')
    result=deepcopy(source)
    laws={law['name']:law for law in result['laws']}
    changed=[]
    def article_for(edit):
        law=laws[edit['law']]
        if str(law.get('mst'))!=edit['mst'] or law['effective']!=edit['effective']:
            raise ValueError('Source repair edition mismatch')
        article=next(a for a in law['articles'] if a['jo']==edit['jo'])
        if article.get('effective',law['effective'])!=edit['effective']:
            raise ValueError('Source repair article edition mismatch')
        return law,article
    visited=set()
    for edit in plan.get('body_edits',[]):
        identity=edit['law'],edit['jo']
        if identity in visited:raise ValueError('Multiple body edits require a new reviewed plan')
        visited.add(identity)
        law,article=article_for(edit)
        before=article['text'];start,end=edit['start'],edit['end']
        if digest(before)!=edit['before_sha256'] or not(0<=start<end<=len(before)) or before[start:end]!=edit['before']:
            raise ValueError('Source repair original text mismatch')
        after=before[:start]+edit['after']+before[end:]
        if digest(after)!=edit['after_sha256']:
            raise ValueError('Source repair verified text mismatch')
        blocks=article.get('blocks',[])
        owner=[b for b in blocks if b['start']<=start and end<=b['end']]
        if len(owner)!=1:raise ValueError('Source repair crosses text blocks')
        delta=len(edit['after'])-(end-start)
        for block in blocks:
            if block is owner[0]:
                block['end']+=delta
            elif block['start']>=end:
                block['start']+=delta;block['end']+=delta
            elif block['end']>start:
                raise ValueError('Unexpected overlapping source blocks')
            block['text']=after[block['start']:block['end']]
        article['text']=after
        changed.append(dict(kind='same-edition-body-correction',law=law['name'],jo=article['jo'],before_sha256=edit['before_sha256'],after_sha256=edit['after_sha256'],official_url=edit['official_url']))
    for edit in plan.get('reference_note_updates',[]):
        law,article=article_for(edit)
        if article.get('reference_notes'):raise ValueError('Existing source remarks must not be overwritten')
        notes=edit['reference_notes']
        if not isinstance(notes,list) or not notes or not all(isinstance(n,str) and n.strip() for n in notes):
            raise ValueError('Invalid source remarks')
        article['reference_notes']=deepcopy(notes)
        changed.append(dict(kind='official-reference-note-restored',law=law['name'],jo=article['jo'],official_url=edit['official_url']))
    return result,changed
