import unittest
from copy import deepcopy
from core.public_institution_scope import labels_for,role,build_scope,validate_scope,PUBLIC,PRIVATE,bridge_matches

class ScopeLabelsTests(unittest.TestCase):
    def test_local_enterprise_title_is_not_national_enterprise_subset(self):
        s=f'「{PUBLIC}」 제4조 및 제6조에 따라 지정된 공공기관과 「지방공기업법」제49조의 지방공사 중 관계부처와 협의하여 평가가 필요하다고 정하는 기관'
        labels=labels_for(s,s,'제4조')
        self.assertIn('designated',labels);self.assertIn('additional',labels);self.assertNotIn('subset',labels)
    def test_partial_types(self):
        self.assertIn('subset',labels_for('제5조에 따른 공기업 및 준정부기관을 말한다.','','제5조'))
        self.assertNotIn('subset',labels_for('공기업, 준정부기관 및 기타 공공기관을 말한다.','','제5조'))
    def test_criteria_are_distinct_from_designation(self):
        self.assertIn('criteria',labels_for('각 호 어느 하나에 해당하는 기관(라목 제외)','','제4조제1항제1호부터 제5호까지'))
        self.assertIn('designated',labels_for('공공기관으로 지정받은 기관','','제4조제1항'))
    def test_transition_rule_preserves_exceptions(self):
        self.assertIn('exclusion',labels_for('지정 당시 적용되던 법령은 해당 회계연도에 따른다.','','제6조'))
    def test_no_similar_title_expansion(self):
        self.assertFalse(role('공공기관의 정보공개에 관한 법률 안내','eflaw'))
        self.assertFalse(role('2026년 공공기관 지정 고시','admrul'))

def fixture():
    from scripts.test_mofe_domains import fixture as base
    b=base();src=b['source'];law=src['laws'][0]
    law['articles']=[dict(jo=j,title='적용 대상' if j=='2' else '공공기관',text=f'제{j}조(공공기관) 기준',blocks=[]) for j in ('2','4','5','6')]
    law['articles'][0]['text']='제2조(적용 대상) 제4조부터 제6조까지 지정된 기관'
    other=deepcopy(law);other.update(name='공공기관의 정보공개에 관한 법률',uid='eflaw:9',managing_authority='행정안전부')
    other['articles']=[dict(jo='2',title='정의',text=f'제2조(정의) 「{PUBLIC}」 제2조에 따른 공공기관',blocks=[])]
    src['laws'].append(other);src['administrative_rules']=[]
    from core.mofe_collection import prepare_source
    from core.mofe_universe import build_graph
    src=prepare_source(src);return src,build_graph(src)

class BridgeScopeTests(unittest.TestCase):
    def edge(self,ref):return dict(target_law='전자정부법',target_ref=ref)
    def hop(self,ref):return dict(source_law='전자정부법',source_ref=ref)
    def test_same_article_different_definition_is_rejected(self):
        self.assertFalse(bridge_matches(self.edge('제2조제10호'),self.hop('제2조제3호나목')))
        self.assertFalse(bridge_matches(self.edge('제2조제6호'),self.hop('제2조제3호나목')))
    def test_same_definition_and_full_article_are_accepted(self):
        self.assertTrue(bridge_matches(self.edge('제2조제3호'),self.hop('제2조제3호나목')))
        self.assertTrue(bridge_matches(self.edge('제2조'),self.hop('제2조제3호나목')))
    def test_range_must_contain_definition_item(self):
        self.assertTrue(bridge_matches(self.edge('제2조제1호부터 제3호까지'),self.hop('제2조제3호나목')))
        self.assertFalse(bridge_matches(self.edge('제2조제4호부터 제6호까지'),self.hop('제2조제3호나목')))
    def test_unknown_source_item_does_not_become_certain_path(self):
        self.assertFalse(bridge_matches(self.edge('제2조제3호'),self.hop('제2조')))
        self.assertFalse(bridge_matches(self.edge('제2조제3호 단서'),self.hop('제2조제3호나목')))

class ScopeEvidenceTests(unittest.TestCase):
    def test_two_step_paths_have_both_provenances(self):
        src,g=fixture();rows=g['public_scope']['records']
        indirect=[r for r in rows if r['kind']=='indirect']
        self.assertEqual({r['target_jo'] for r in indirect},{'4','5','6'})
        self.assertTrue(all(len(r['evidence_ids'])==2 for r in indirect))
        self.assertFalse(any('scope' in e for e in g['edges']))
    def test_path_cannot_borrow_an_unrelated_witness(self):
        src,g=fixture();v=deepcopy(g['public_scope']);v['records'][0]['path'][0]['target_ref']='제5조'
        with self.assertRaises(ValueError):validate_scope(v,src,g)
    def test_anchor_articles_keep_scope_sector(self):
        src,g=fixture();d=next(d for d in src['laws'] if d['name']==PUBLIC)
        self.assertTrue(all('scope' in a['sectors'] for a in d['articles']))
    def test_fake_excerpt_is_rejected(self):
        src,g=fixture();v=deepcopy(g['public_scope']);v['records'][0]['raw']='가짜'
        with self.assertRaises(ValueError):validate_scope(v,src,g)
    def test_missing_path_evidence_is_rejected(self):
        src,g=fixture();v=deepcopy(g['public_scope']);v['records'][0]['evidence_ids']=['unknown']
        with self.assertRaises(ValueError):validate_scope(v,src,g)

if __name__=='__main__':unittest.main()
