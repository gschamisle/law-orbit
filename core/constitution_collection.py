"""Constitution has no managing ministry in DRF; verify its identity instead."""
import hashlib
from core.fsc_collection import CollectionError,field,norm,ymd,body_params,xml_root
from core.procurement_collection import collect_document,safe_xml
from core.constitution_profile import CONSTITUTION

def collect(request,item,as_of,*,authority_validator=None):
    if item['name']!=CONSTITUTION:
        if item['name']=='국회법' and item['document_id']=='001416' and item['managing_authority']=='국회':
            # DRF list uses the institution; its body uses the secretariat.
            authority_validator=lambda record,actual:actual=={'국회사무처'}
        return collect_document(request,item,as_of,authority_validator=authority_validator)
    if (item['provider']!='eflaw' or item['document_id']!='001444' or item['kind']!='헌법'
        or item['managing_authority'] or item['state']!='current-candidate' or item['effective']>ymd(as_of)):
        raise CollectionError('constitution-identity-mismatch')
    raw=safe_xml(request('lawService.do',body_params(item)));root=xml_root(raw)
    if (field(root,'.//법령ID')!='001444' or norm(field(root,'.//법령명_한글'))!=norm(CONSTITUTION)
        or ymd(field(root,'.//시행일자'))!=item['effective'] or field(root,'.//법종구분')!='헌법'
        or any((n.text or '').strip() for tag in ('.//소관부처명','.//소관부처') for n in root.findall(tag))):
        raise CollectionError('constitution-body-identity-or-edition-mismatch')
    from scripts.collect_law_universe import parse_body
    parsed=parse_body(root,dict(name=CONSTITUTION,law_id='001444',mst=item['version_id'],
                               effective=item['effective'],category='constitution',family=CONSTITUTION))
    if not parsed['articles']:raise CollectionError('constitution-body-empty')
    return {**parsed,**item,'body_sha256':hashlib.sha256(raw).hexdigest(),'fetched_at':as_of,
            'state':'current-body-verified','body_status':'indexed-statute-text',
            'authority_status':'no-ministry-in-official-metadata'}
