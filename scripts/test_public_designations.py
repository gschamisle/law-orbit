import unittest
from copy import deepcopy
from core.public_designations import load,validate

class DesignationTests(unittest.TestCase):
    def test_counts_and_dates(self):
        v=load();self.assertEqual(len(v['events']),20)
        self.assertEqual(sum(e['year']==2026 for e in v['events']),13)
        self.assertTrue(all(e['effective'] is None for e in v['events']))
        self.assertTrue(all(not s['full_register'] for s in v['sources']))
    def test_actual_type_changes(self):
        v=load();by_name={e['name']:e for e in v['events']}
        self.assertEqual((by_name['한국방송광고진흥공사']['before'],by_name['한국방송광고진흥공사']['after']),('공기업','기타공공기관'))
        self.assertEqual(by_name['한국법무보호복지공단']['after'],'준정부기관')
    def test_announcement_date_cannot_be_used_as_effective_date(self):
        v=deepcopy(load());v['events'][0]['effective']='20250121'
        with self.assertRaises(ValueError):validate(v)
    def test_fake_institution_or_missing_row_fails(self):
        v=deepcopy(load());v['events'][0]['name']='존재하지않는기관'
        with self.assertRaises(ValueError):validate(v)
        v=deepcopy(load());v['events'].pop()
        with self.assertRaises(ValueError):validate(v)

if __name__=='__main__':unittest.main()
