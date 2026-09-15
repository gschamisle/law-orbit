"""Synthetic scope cases plus repository snapshot evidence; no external API calls."""
from __future__ import annotations

import unittest

from core.citation_scope import classify, parse_target
from core.impact_explorer import analyze


class ScopeTests(unittest.TestCase):
    def test_target_validation(self):
        for invalid in ("16", "제0조", "제16조제2항xxx", "제16조부터 제18조까지", "제16조가목"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_target(invalid)
        self.assertEqual(parse_target("제16조 제2항 제1호").label, "제16조제2항제1호")
        self.assertEqual(parse_target("제3조의2제1호의2").ho, "1의2")
        self.assertEqual(parse_target("제3조의2제1호의2").label, "제3조의2제1호의2")

    def test_scope_cases(self):
        cases = [
            ("법 제16조제2항제1호", "exact"),
            ("「법인세법」 제16조", "covering"),
            ("법인세법 제16조제2항", "covering"),
            ("제16조제1항부터 제3항까지", "range"),
            ("제16조제1항 내지 제3항", "range"),
            ("제16조제1항~제3항", "range"),
            ("제16조제1항 및 제3항", "disjoint"),
            ("제16조제1항, 제2항 및 제3항", "covering"),
            ("제16조제2항제1호부터 제3호까지", "range"),
            ("제16조제2항제2호부터 제5호까지", "disjoint"),
            ("제16조제2항제2호 및 제4호", "disjoint"),
            ("제16조제2항 각 호", "covering"),
            ("제16조제1항제1호", "disjoint"),
            ("제16조제2항제2호", "disjoint"),
            ("제16조제2항의 제2호", "disjoint"),
            ("제16조제1호", "review"),
            ("제16조의2", "disjoint"),
            ("제160조", "disjoint"),
            ("제14조부터 제18조까지", "range"),
            ("제17조부터 제20조까지", "disjoint"),
            ("제16조제2항제1호를 제외한다", "review"),
            ("제16조제2항 각 호 외의 부분", "review"),
            ("제16조제2항제1호에 한정한다", "review"),
            ("같은 조 제2항", "review"),
            ("제2항", "review"),
            ("제16조제3항부터 제1항까지", "review"),
            ("제16조제1항부터", "review"),
            ("제16조제1항부터 제18조까지", "review"),
            ("제16조제2항제1호가목", "contained"),
        ]
        target = parse_target("제16조제2항제1호")
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(classify(text, target)[0], expected)

    def test_branch_intervals_and_mok(self):
        self.assertEqual(classify("제14조부터 제18조까지", parse_target("제16조의2"))[0], "range")
        self.assertEqual(classify("제16조제2항제1호의2", parse_target("제16조제2항제1호"))[0], "disjoint")
        self.assertEqual(classify("제16조제2항제1호가목", parse_target("제16조제2항제1호나목"))[0], "disjoint")

    def test_multiple_evidence_and_other_laws(self):
        edges = [dict(source_law="다른법", source_jo="9", target_law="법인세법", target_ref="제16조", cite_raw=raw)
                 for raw in ("제16조", "제16조제2항제1호", "제16조제1항", "제16조")]
        edges.append(dict(edges[0], target_law="소득세법"))
        result = analyze("법인세법", "제16조제2항제1호", {"edges": edges})
        self.assertEqual(len(result["rows"]), 3)
        self.assertEqual(result["counts"], {"exact": 1, "covering": 1, "disjoint": 1})

    def test_snapshot_evidence(self):
        result = analyze("법인세법", "제16조제2항제1호")
        rows = result["rows"]
        # Full context reveals exclusions that the old raw-only snapshot did not retain.
        self.assertTrue(any(r["source_law"] == "법인세법 시행규칙" and r["source_jo"] == "7"
                            and r["status"] == "review" and "포함되지 않는다" in r.get("context","") for r in rows))
        self.assertTrue(any(r["source_law"] == "법인세법 시행령" and r["source_jo"] == "14" and r["status"] == "exact" for r in rows))
        self.assertTrue(any(r["source_law"] == "법인세법 시행령" and r["source_jo"] == "12" and r["status"] == "disjoint" for r in rows))
        self.assertTrue(any(r["status"] == "range" for r in rows))
        self.assertTrue(all(r["raw"] and r["reason"] for r in rows))


if __name__ == "__main__":
    unittest.main()
