"""Add export finance and KIC to an immutable public snapshot.

All existing source texts and dates survive. Forex evidence is regenerated with
the corrected quoted-owner parser; other domain catalogs remain byte-identical.
The collected current edition is mandatory; scheduled bodies never enter a map.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.domain_navigation import ordered_domains
from core.export_finance_profile import PROFILE
from core.forex_collection import KIC_LAWS, index_forex_rule, tag_document, SECTORS
from core.forex_universe import build_graph as forex_graph
from core.mofe_universe import load_bundle
from core.forex_finance_links import EXTERNAL_FINANCE_PAIRS
from scripts.build_static_galaxies import Writer, shell, export_documents, overview, workbench
from scripts.build_forex_finance_site import attach_bridge_pairs
from scripts.build_edition_refresh_site import source_document
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.edition_refresh_bridges import rebuild_bridges
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def restore_forex(storage, catalog, kic_source):
    from urllib.parse import urlsplit
    from core.forex_bok import TITLES as BOK_TITLES
    docs=[]
    for entry in catalog['laws']:
        packed=storage.read(entry['file'])
        doc=source_document(entry, packed, 'forex', {})
        # Public display labels are not evidence of legal abbreviations. The
        # verified body declarations below supply aliases used by the parser.
        doc.update(uid=entry['id'], display_name=entry['label'],
                   short_name=entry['name'], citation_names=[entry['name']])
        # The general edition restorer infers only MOLEG providers. Keep the
        # separate BOK provenance and its administrative-number parser path.
        hostname=urlsplit(entry['url']).hostname
        if entry['name'] in BOK_TITLES or hostname in ('www.bok.or.kr','bok.or.kr'):
            if (entry['name'] not in BOK_TITLES or hostname not in ('www.bok.or.kr','bok.or.kr')
                    or entry.get('authority')!='한국은행'):
                raise ValueError('Published BOK source identity mismatch')
            doc['provider']='bok'
        # Existing forex statutes and rules keep their original parser policy;
        # mofe-explicit is an opt-in and must not be introduced during copying.
        for key in ('source_notes','pdf_url','unparsed_provisions'):
            if key in entry: doc[key]=deepcopy(entry[key])
        # Recover document aliases without changing a single article or offset.
        body='\n'.join(a['text'] for a in doc['articles'])
        aliases=index_forex_rule({**doc,'raw_body_blocks':[body]})
        doc.update(aliases=aliases.get('aliases',{}), alias_evidence=aliases.get('alias_evidence',[]), raw_body_blocks=[body])
        tag_document(doc, retain_existing=True)
        docs.append(doc)
    additions=deepcopy(kic_source['laws'])
    if len(additions)!=len(KIC_LAWS) or {d['name'] for d in additions}!=set(KIC_LAWS):
        raise ValueError('Expected both verified KIC documents')
    for doc in additions:
        if doc.get('state')!='current-body-verified' or doc['effective']>kic_source['built_at']:
            raise ValueError('KIC current body is not verified')
        doc.update(category='forex',display_name=doc['name'])
        tag_document(doc)
    docs+=additions
    return dict(domain='forex', built_at=kic_source['built_at'],
                inventory={'scope':'published-forex-bodies-plus-verified-KIC'},
                laws=[d for d in docs if d['provider']=='eflaw'],
                administrative_rules=[d for d in docs if d['provider']!='eflaw'])


def build(base, bundle_path, kic_path, destination):
    base,destination=Path(base).resolve(),Path(destination).resolve()
    stage=destination.with_name(destination.name+'-unpacked')
    if any(p.exists() for p in (destination,stage)) or destination.is_relative_to(base):
        raise ValueError('Choose independent new output folders')
    original_bytes=(base/'manifest.json').read_bytes()
    original=json.loads(original_bytes);manifest=deepcopy(original)
    if any(d['id']=='export_finance' for d in original['domains']):
        raise ValueError('Export finance already exists in this baseline')
    print('Validating immutable public baseline',flush=True)
    validate(base)
    bundle=load_bundle('export_finance',bundle_path)
    kic=json.loads(Path(kic_path).read_text(encoding='utf-8'))
    stage.mkdir(parents=True);shell(stage);writer=Writer(stage)
    manifest.pop('data_packs',None)
    storage=Storage(base,original)
    domain=next(d for d in manifest['domains'] if d['id']=='forex')
    old=storage.read(domain['catalog'])
    print('Rebuilding forex citations and adding KIC bodies',flush=True)
    source=restore_forex(storage,old,kic);graph=forex_graph(source)
    entries,ids=export_documents(writer,'forex','',source['laws']+source['administrative_rules'],graph)
    old_by={e['name']:e for e in old['laws']}
    for entry in entries:
        if entry['name'] not in old_by: continue
        previous=old_by[entry['name']];before=storage.read(previous['file'])
        after=Storage(stage,{}).read(entry['file'])
        for fields in (('jo','title','text','effective'),):
            if [tuple(a.get(k) for k in fields) for a in before['articles']] != [tuple(a.get(k) for k in fields) for a in after['articles']]:
                raise ValueError('Existing forex source text changed')
        if previous['id']!=entry['id'] or previous['effective']!=entry['effective'] or previous['url']!=entry['url']:
            raise ValueError('Existing forex edition changed')
        # Keep source notes and attachment inventories exactly as published.
        entry.update({k:v for k,v in previous.items() if k not in entry and k not in ('file','parts')})
        if 'annexes' in before: after['annexes']=deepcopy(before['annexes'])
        after['meta']={k:deepcopy(v) for k,v in entry.items() if k!='file'}
        entry['file']=writer.data(after)
    catalog={**old,'laws':entries,'overview':writer.data(overview(graph,'forex',ids,entries)),
             'coverage':graph['coverage_note'],'built_at':source['built_at'],'sectors':SECTORS}
    catalog['coverage']+=' 기존 외환 자료의 판본은 그대로 보존하고 KIC 법·시행령을 추가했습니다.'
    domain.update(laws=len(entries),catalog=writer.data(catalog),built_at=source['built_at'])
    write_json(stage/'manifest.json',manifest)
    materialize_reachable(base,stage,manifest)
    print('Refreshing existing forex bridges',flush=True)
    bridge_refresh=rebuild_bridges(base,stage,manifest,{'forex'},writer)
    # Only after refreshing existing pairs may the new domain enter the manifest.
    src,g=bundle['source'],bundle['graph']
    entries,ids=export_documents(writer,'export_finance','',src['laws']+src['administrative_rules'],g)
    catalog=dict(laws=entries,overview=writer.data(overview(g,'export_finance',ids,entries)),
        coverage=g['coverage_note'],built_at=g['built_at'],sectors=PROFILE['sectors'],
        workbench=workbench(bundle,ids),default_laws=PROFILE.get('default_laws',{}),default_refs=PROFILE.get('default_refs',{}))
    manifest['domains'].append(dict(id='export_finance',title=PROFILE['title'],laws=len(entries),
                                   catalog=writer.data(catalog),built_at=g['built_at']))
    manifest['domains']=ordered_domains(manifest['domains'])
    materialize_reachable(base,stage,manifest)
    print('Linking export finance to existing fields',flush=True)
    extra_pairs=attach_bridge_pairs(stage,manifest,EXTERNAL_FINANCE_PAIRS,writer)
    manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    write_json(stage/'manifest.json',manifest)
    reachable=materialize_reachable(base,stage,manifest)
    for p in (stage/'data').glob('*.json.gz'):
        if p.relative_to(stage).as_posix() not in reachable:
            if p.resolve().parent!=(stage/'data').resolve(): raise ValueError('Unsafe provisional path')
            p.unlink()
    print('Packing and validating the complete preview',flush=True)
    # Unpacked logical members intentionally exceed the hosting file budget.
    # The packer verifies every hash; hosting and semantic gates run on the
    # final packed tree, which is the only deliverable.
    result=convert(stage,destination,validate_site=False)
    result.update(validate(destination))
    current={d['id']:d for d in manifest['domains']}
    if any(current[d['id']]!=d for d in original['domains'] if d['id']!='forex'):
        raise ValueError('Unrelated domain catalog changed')
    if (base/'manifest.json').read_bytes()!=original_bytes: raise ValueError('Input mutated')
    result.update(version=manifest['version'],existing_forex_bodies_preserved=len(old['laws']),
                  unchanged_domain_catalogs=len(original['domains'])-1,
                  bridge_refresh=bridge_refresh,external_pairs=extra_pairs)
    write_json(destination.with_name(destination.name+'-report.json'),result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('base','bundle','kic','destination'): parser.add_argument('--'+arg,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.base,args.bundle,args.kic,args.destination),ensure_ascii=False,indent=2))
