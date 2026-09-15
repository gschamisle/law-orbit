"""Offline regressions for the multi-domain law registry."""
import unittest

from core.law_domains import DEFAULT_DOMAIN, FSC_DOMAIN, get_domain, legacy_tax_scope
from core.law_universe import COURT_RULES, EXTERNAL, NEW_TAX


def norm(name: str) -> str:
    return ''.join(name.split()).replace('ㆍ', '').replace('·', '')


class LawDomainRegistryTests(unittest.TestCase):
    def test_default_domain_preserves_tax(self):
        self.assertEqual(DEFAULT_DOMAIN, 'tax')
        self.assertEqual(get_domain().key, 'tax')
        self.assertEqual(
            legacy_tax_scope(),
            {
                'new_tax': tuple(NEW_TAX),
                'external': tuple(EXTERNAL),
                'court_rules': tuple(COURT_RULES),
            },
        )

    def test_fsc_seeds_are_official_name_only(self):
        seeds = FSC_DOMAIN.principal_laws
        self.assertGreaterEqual(len(seeds), 20)
        self.assertEqual(len({norm(seed.name) for seed in seeds}), len(seeds))
        self.assertTrue(all(seed.status == 'verified-name-only' for seed in seeds))
        self.assertTrue(all(not seed.law_id and not seed.mst and not seed.effective for seed in seeds))
        self.assertTrue(all(seed.source_url.startswith('https://www.fsc.go.kr/po040101') for seed in seeds))

    def test_first_pass_hubs_are_explicit(self):
        priority_one = {seed.name for seed in FSC_DOMAIN.principal_laws if seed.priority == 1}
        self.assertEqual(
            priority_one,
            {
                '자본시장과 금융투자업에 관한 법률',
                '금융실명거래 및 비밀보장에 관한 법률',
                '금융소비자 보호에 관한 법률',
                '금융회사의 지배구조에 관한 법률',
                '신용정보의 이용 및 보호에 관한 법률',
            },
        )

    def test_nonstatutory_layers_require_official_evidence(self):
        layers = {layer.key: layer for layer in FSC_DOMAIN.collection_layers}
        self.assertEqual(layers['fsc-administrative-rules'].relationship_policy, 'official-evidence-only')
        self.assertEqual(layers['fss-rules'].relationship_policy, 'official-evidence-only')
        self.assertIn('do not', layers['fss-rules'].discovery_policy.lower())
        self.assertNotIn('append', layers['fsc-administrative-rules'].discovery_policy.lower())
        self.assertEqual(layers['fsc-administrative-rules'].coverage, 'not-collected')
        self.assertEqual(layers['fss-rules'].coverage, 'not-collected')


if __name__ == '__main__':
    unittest.main()
