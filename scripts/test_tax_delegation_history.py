"""Offline checks of historical selection, credential hygiene, and real payloads."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.collect_tax_delegation_history import (
    NAMES, ROOT, article_sha256, assert_public_body, check_identity, public_xml,
    select_previous,
)
from scripts.static_storage import Storage

BUNDLE = ROOT / "output/tax-delegation-history-20260929"


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.current = dict(law_id="001565", name="소득세법", mst="280405", effective="20260701",
                            promulgated="20251223", promulgation_number="21221", status="현행")
        self.old = dict(law_id="001565", name="소득세법", mst="285523", effective="20260421",
                        promulgated="20260421", promulgation_number="21548", status="연혁")
        self.rows = [self.current, self.old]

    def test_prior_effective_may_have_newer_mst_and_promulgation(self):
        self.assertEqual(select_previous(self.rows, self.current, "20260929"), self.old)

    def test_future_public_and_future_search_rows_rejected(self):
        with self.assertRaises(ValueError):
            select_previous(self.rows, self.current, "20260101")
        with self.assertRaises(ValueError):
            select_previous(self.rows + [{**self.old, "effective": "20280101"}], self.current, "20260929")

    def test_missing_anchor_ambiguous_history_and_wrong_law_rejected(self):
        for rows in ([self.old], self.rows + [self.old], self.rows + [{**self.old, "law_id": "999"}]):
            with self.assertRaises(ValueError):
                select_previous(rows, self.current, "20260929")

    def test_remote_renaming_and_retroactivity_dont_change_selected_edition(self):
        remote = {**self.old, "name": "옛이름", "mst": "1", "effective": "19680101", "promulgated": "19680307"}
        self.assertEqual(select_previous(self.rows + [remote], self.current, "20260929"), self.old)

    def test_selected_rename_or_retroactivity_require_manual_review(self):
        for changed in ({"name": "다른 이름"}, {"promulgated": "20260501"}):
            with self.assertRaises(ValueError):
                select_previous([self.current, {**self.old, **changed}], self.current, "20260929")

    def test_history_body_metadata_must_match(self):
        for field in ("name", "law_id", "mst", "effective", "promulgated", "promulgation_number"):
            with self.assertRaises(ValueError):
                check_identity({**self.old, field: "mismatch"}, self.old)

    def test_current_public_body_must_match_completely(self):
        original = [{"jo": "1", "title": "목적", "text": "원문", "effective": "20260701"}]
        assert_public_body(original, copy.deepcopy(original))
        for field in ("jo", "title", "text", "effective"):
            changed = [{**original[0], field: "changed"}]
            with self.assertRaises(ValueError):
                assert_public_body(original, changed)

    def test_echoed_authentication_is_redacted_with_original_hash_only(self):
        raw = b'<link>?OC=secret%2Bvalue&amp;x=1</link><link>secret+value</link>'
        cleaned, provenance = public_xml(raw, "secret+value")
        self.assertNotIn(b"secret", cleaned)
        self.assertEqual(provenance["response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(provenance["credential_values_redacted"])


@unittest.skipUnless((BUNDLE / "manifest.json").is_file(), "real immutable bundle not collected")
class CollectedTests(unittest.TestCase):
    def test_sources_baselines_current_bodies_and_citation_absence(self):
        manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({row["name"] for row in manifest["laws"]}, set(NAMES))
        public = ROOT / manifest["public_site"]
        self.assertEqual(hashlib.sha256((public / "manifest.json").read_bytes()).hexdigest(), manifest["public_manifest_sha256"])
        storage = Storage(public)
        public_manifest = json.loads((public / "manifest.json").read_text(encoding="utf-8"))
        catalog = storage.read(next(d["catalog"] for d in public_manifest["domains"] if d["id"] == "tax"))
        for law in manifest["laws"]:
            with self.subTest(law=law["name"]):
                refs = [law["baseline"], law["current_snapshot"], law["current"]["xml"], law["previous"]["xml"], *law["history_pages"]]
                for ref in refs:
                    path = (BUNDLE / ref["path"]).resolve()
                    self.assertIn(BUNDLE.resolve(), path.parents)
                    raw = path.read_bytes()
                    self.assertEqual(len(raw), ref["bytes"])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), ref["sha256"])
                old = json.loads((BUNDLE / law["baseline"]["path"]).read_text(encoding="utf-8"))
                current = json.loads((BUNDLE / law["current_snapshot"]["path"]).read_text(encoding="utf-8"))
                self.assertLess(old["meta"]["effective"], current["meta"]["effective"])
                self.assertEqual(old["details"], {})
                self.assertEqual(old["evidence_availability"]["reverse_citations"], "not-collected")
                self.assertEqual(article_sha256(old["articles"]), law["previous"]["text_sha256"])
                self.assertEqual(article_sha256(current["articles"]), law["current"]["text_sha256"])
                entry = next(e for e in catalog["laws"] if e["id"] == law["id"])
                assert_public_body(current["articles"], storage.read(entry["file"])["articles"])


if __name__ == "__main__":
    unittest.main()
