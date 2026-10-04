"""Regression cases from the source-first blind tax audit; no collection needed."""
from copy import deepcopy
import unittest

from core.tax_citation_context import tax_annex_references, tax_article_overrides, tax_law_level_references

# Exact stored official-source article reviewed before viewing the app result.
# Its full-body hash is the narrow allow-list guard, not a generic table fixture.
REVIEWED_TABLE_BODY = '제49조(재해손실에 대한 세액공제)\n①법 제58조에 따라 법인세에서 공제할 세액의 계산은 다음 계산식에 따른다.  \n\n┌────────────────────────────────────────────────┐\n│                                                                                                │\n│                                                                                                │\n│  (   법 제55조에   +   법 제75조의3과        -   다른 법률에 따른  )   ×  재해로 인하여       │\n│      따른              「국세기본법」 제47       공제 및 감면세액          상실된 자산의 가액  │\n│      산출세액          조의2부터                                         ───────────│\n│                        제47조의5까지에 따                                  상실전 자산총액     │\n│                        른 가산세액                                                             │\n│                                                                                                │\n│                                                                                                │\n└────────────────────────────────────────────────┘\n②법인이 재해로 인하여 수탁받은 자산을 상실하고 그 자산가액의 상당액을 보상하여 주는 경우에는 이를 재해로 인하여 상실된 자산의 가액 및 상실전의 자산총액에 포함하되, 예금ㆍ받을어음ㆍ외상매출금 등은 당해채권추심에 관한 증서가 멸실된 경우에도 이를 상실된 자산의 가액에 포함하지 아니한다. 이 경우 그 재해자산이 보험에 가입되어 있어 보험금을 수령하는 때에도 그 재해로 인하여 상실된 자산의 가액을 계산함에 있어서 동 보험금을 차감하지 아니한다.\n③법인이 동일한 사업연도중에 2회이상 재해를 입은 경우 재해상실비율의 계산은 다음 산식에 의한다. 이 경우 자산은 영 제95조1항 각호의 자산에 한한다.\n\n┌──────────────────────────────────────────────┐\n│                                                                                            │\n│                                                                                            │\n│  재해상실비율  =   재해로 인하여 상실된 자산가액의 합계액                                  │\n│                  ─────────────────────────────────────│\n│                    최초 재해발생전 자산총액    +   최종 재해발생전까지의 증가된 자산총액   │\n│                                                                                            │\n│                                                                                            │\n└──────────────────────────────────────────────┘'


def inputs(text, name="국세기본법 시행규칙", jo="12", effective="20260320"):
    return (dict(name=name, effective=effective),
            dict(jo=jo, effective=effective, text=text))


class TaxAnnexContextTests(unittest.TestCase):
    def extract(self, text, **kwargs):
        law, article = inputs(text, **kwargs)
        issues = []
        rows = tax_annex_references(law, article, issues=issues)
        for row in rows:
            self.assertEqual(text[row["start"]:row["end"]], row["raw"])
        return rows, issues

    def test_audited_named_forms_keep_owner_through_parenthesis_and_enumeration(self):
        text = "「개별소비세법 시행규칙」 별지 제6호서식(부표를 포함한다), 별지 제7호서식, 별지 제7호의2서식 또는 별지 제7호의3서식"
        rows, issues = self.extract(text)
        self.assertFalse(issues)
        self.assertEqual([(r["target_name"], r["target_ref"]) for r in rows], [
            ("개별소비세법 시행규칙", ref) for ref in
            ("별지 제6호서식", "별지 제7호서식", "별지 제7호의2서식", "별지 제7호의3서식")])
        self.assertEqual([r["raw"] for r in rows],
            ["별지 제6호서식", "별지 제7호서식", "별지 제7호의2서식", "별지 제7호의3서식"])

    def test_branch_position_variants_and_subforms_are_distinct(self):
        text = "별지 제54호의2서식, 별지 제54의2호서식 및 별지 제16호서식(1) 또는 별지 제16호서식(2)"
        rows, issues = self.extract(text)
        self.assertFalse(issues)
        self.assertEqual([r["target_ref"] for r in rows],
            ["별지 제54호의2서식", "별지 제54호의2서식", "별지 제16호서식(1)", "별지 제16호서식(2)"])

    def test_all_branches_have_one_canonical_label(self):
        for raw in ("별지 제33호의2서식", "별지 제33의2호서식", "별지 제33 호 의 2 서식"):
            rows, issues = self.extract(raw)
            self.assertFalse(issues)
            self.assertEqual(rows[0]["target_ref"], "별지 제33호의2서식")

    def test_source_subform_suffix_not_dropped(self):
        rows, _ = self.extract("별지 제16호서식 (1), 별지 제16호서식（2）")
        self.assertEqual([r["target_ref"] for r in rows], ["별지 제16호서식(1)", "별지 제16호서식(2)"])

    def test_no_owner_inheritance_across_sentence_paragraph_or_clause(self):
        for gap in (". ", "。 ", "; ", "\n", " ② "):
            with self.subTest(gap=gap):
                rows, _ = self.extract("「개별소비세법 시행규칙」 별지 제6호서식" + gap + "별지 제7호서식")
                self.assertEqual([r["target_name"] for r in rows],
                    ["개별소비세법 시행규칙", "국세기본법 시행규칙"])

    def test_new_named_owner_replaces_previous_list_owner(self):
        rows, issues = self.extract("「소득세법 시행규칙」 별지 제1호서식 및 「법인세법 시행규칙」 별지 제2호서식, 별지 제3호서식")
        self.assertFalse(issues)
        self.assertEqual([r["target_name"] for r in rows],
            ["소득세법 시행규칙", "법인세법 시행규칙", "법인세법 시행규칙"])

    def test_different_annex_kind_is_not_an_external_list_continuation(self):
        rows, issues = self.extract("「소득세법 시행규칙」 별지 제1호서식 및 별표 2")
        self.assertEqual([r["target_name"] for r in rows], ["소득세법 시행규칙"])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["raw"], "별표 2")

    def test_arbitrary_parenthesis_does_not_carry_external_owner(self):
        for gap in ("(다른 법률에 따른 경우), ", "에 따른 서류를 첨부하고, "):
            rows, issues = self.extract("「소득세법 시행규칙」 별지 제1호서식" + gap + "별지 제2호서식")
            self.assertEqual([r["target_name"] for r in rows], ["소득세법 시행규칙"])
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["raw"], "별지 제2호서식")

    def test_deictic_family_and_explicit_same_owner_are_bounded(self):
        for prefix, wanted in (("법", "국세기본법"), ("영", "국세기본법 시행령"),
                                ("이 규칙", "국세기본법 시행규칙")):
            rows, _ = self.extract(prefix + " 별지 제1호서식")
            self.assertEqual(rows[0]["target_name"], wanted)
        rows, _ = self.extract("「소득세법」에 따른 같은 법 별표 1")
        self.assertEqual(rows[0]["target_name"], "소득세법")
        rows, issues = self.extract("「소득세법」에 따른다. 같은 법 별표 1")
        self.assertFalse(rows)
        self.assertTrue(issues)

    def test_unknown_owner_or_competing_anchor_is_not_own_document(self):
        for raw in ("해당 규칙 별지 제1호서식", "알수없는법 별표 1",
                    "「소득세법」 및 「법인세법」에 따른 같은 법 별표 1",
                    "「소득세법」 제3조 및 별표 1"):
            rows, issues = self.extract(raw)
            self.assertFalse(rows)
            self.assertTrue(issues)

    def test_unsupported_suffix_range_or_quotation_never_becomes_partial_number(self):
        for raw in ("별표 1-2", "별지 제1의2호의3서식", "별표 1부터 별표 4까지",
                    '"별지 제1호서식"이라 한다', "「별표 1」"):
            rows, issues = self.extract(raw)
            self.assertFalse(rows)
            self.assertTrue(issues)

    def test_no_mutation_of_input_documents(self):
        law, article = inputs("「소득세법 시행규칙」 별지 제33호의2서식")
        before = deepcopy((law, article))
        tax_annex_references(law, article)
        self.assertEqual((law, article), before)


class TaxArticleContextTests(unittest.TestCase):
    def test_source_article_range_keeps_original_and_resolved_scope(self):
        law, article = inputs("제81조(안분)\n이하 이 조부터 제83조까지의 규정에서 같다",
                              name="부가가치세법 시행령", jo="81")
        rows = tax_article_overrides(law, article)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["raw"], "이 조부터 제83조까지")
        self.assertEqual(row["resolved_raw"], "제81조부터 제83조까지")
        self.assertEqual(row["target_name"], "부가가치세법 시행령")
        self.assertEqual(article["text"][row["start"]:row["end"]], row["raw"])
        self.assertEqual(row["skip_spans"], [(row["start"], row["end"])])

    def test_article_branch_range_and_unsafe_shapes(self):
        law, article = inputs("이 조부터 제83조의2까지", jo="81의2")
        self.assertEqual(tax_article_overrides(law, article)[0]["resolved_raw"],
                         "제81조의2부터 제83조의2까지")
        for text, jo in (("이 조부터 제80조까지", "81"),
                         ('"이 조부터 제83조까지"로 고친다', "81"),
                         ("이 조부터 제83조까지", "별표"),
                         ("그 조부터 제83조까지", "81")):
            self.assertFalse(tax_article_overrides(*inputs(text, jo=jo)))

    def test_reviewed_table_positive_has_exact_source_and_full_skip_span(self):
        law, article = inputs(REVIEWED_TABLE_BODY, name="법인세법 시행규칙", jo="49", effective="20260701")
        before = deepcopy((law, article))
        rows = tax_article_overrides(law, article)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["start"], row["end"]), (414, 578))
        self.assertEqual(row["raw"], REVIEWED_TABLE_BODY[414:578])
        self.assertEqual(row["resolved_raw"], "제47조의2부터 제47조의5까지")
        self.assertEqual(row["target_name"], "국세기본법")
        self.assertEqual(row["skip_spans"], [(414, 578)])
        # Both legacy errors (bare law-name and self article47의5) lie here.
        self.assertTrue(414 <= 414 < 421 <= 578)
        self.assertTrue(414 <= 570 < 576 <= 578)
        self.assertEqual((law, article), before)

    def test_table_override_rejects_changed_body_even_outside_citation(self):
        for text in (REVIEWED_TABLE_BODY + " ", REVIEWED_TABLE_BODY.replace("재해", "재난", 1),
                     REVIEWED_TABLE_BODY.replace("공제 및 감면세액", "공제 및 감면 세액", 1)):
            law, article = inputs(text, name="법인세법 시행규칙", jo="49", effective="20260701")
            self.assertFalse(tax_article_overrides(law, article))

    def test_table_override_rejects_wrong_law_article_or_edition(self):
        for kwargs in (dict(name="다른법 시행규칙", jo="49", effective="20260701"),
                       dict(name="법인세법 시행규칙", jo="50", effective="20260701"),
                       dict(name="법인세법 시행규칙", jo="49", effective="20270101")):
            self.assertFalse(tax_article_overrides(*inputs(REVIEWED_TABLE_BODY, **kwargs)))


class TaxLawLevelContextTests(unittest.TestCase):
    def extract(self, text, name="법인세법 시행령", **fields):
        law, article = inputs(text, name=name, jo="97")
        law.update(fields)
        rows = tax_law_level_references(law, article)
        for row in rows:
            self.assertEqual(text[row["start"]:row["end"]], row["raw"])
            self.assertEqual((row["kind"], row["target_ref"]), ("law", "법령·정의 참조"))
        return rows

    def test_two_source_first_audited_constructions(self):
        samples = [
            ("법인세법 시행령",
             "⑧법 제60조제5항을 적용함에 있어서 합병 또는 분할로 인하여 소멸하는 법인의 최종사업연도의 과세표준과 세액을 신고함에 있어서는 같은 조 제2항제1호의 서류중 이익잉여금처분계산서(또는 결손금처리계산서)를 제출하지 아니한 경우에도 법에 의한 신고를 한 것으로 본다.",
             "법에 의한 신고", "법인세법"),
            ("소득세법 시행규칙",
             "라. 법 또는 다른 법률의 규정에 의하여 충당금ㆍ준비금 등을 필요경비 또는 총수입금액에 산입한 경우에는 그 명세서",
             "법 또는 다른 법률", "소득세법"),
        ]
        for name, text, quote, owner in samples:
            with self.subTest(name=name):
                rows = self.extract(text, name)
                self.assertEqual([(r["target_name"], r["raw"]) for r in rows], [(owner, quote)])
                self.assertEqual(rows[0]["relation"], "law_reference")
                self.assertTrue(rows[0]["context_review"])

    def test_whitespace_and_repeated_occurrences_preserve_source_positions(self):
        text = "법에\t의한 신고를 한다. 법에 의한 신고를 한다. 법 또는 다른 법률의 규정"
        rows = self.extract(text)
        self.assertEqual([r["raw"] for r in rows], ["법에\t의한 신고", "법에 의한 신고", "법 또는 다른 법률"])
        self.assertEqual(len({r["start"] for r in rows}), 3)
        self.assertEqual({r["target_name"] for r in rows}, {"법인세법"})

    def test_only_statutory_decree_or_enforcement_rule_has_parent(self):
        for name in ("법인세법", "국세청 고시", "특별 운영규칙", "기관운영 시행규칙"):
            with self.subTest(name=name):
                self.assertFalse(self.extract("법에 의한 신고를 한다.", name))
        self.assertEqual(self.extract("법에 의한 신고를 한다.", "조세범 처벌절차법 시행령")[0]["target_name"],
                         "조세범 처벌절차법")

    def test_standalone_boundaries_do_not_match_names_modifiers_or_compound_words(self):
        for text in ("국세기본법에 의한 신고", "방법에 의한 신고", "A법에 의한 신고",
                     "같은 법에 의한 신고", "다른 법에 의한 신고", "해당 법 또는 다른 법률",
                     "이 법에 의한 신고", "그 법 또는 다른 법률", "법에 의한 신고서",
                     "법에 의한 신고가액", "법에 의한 신고의무", "법 또는 다른 법률안"):
            with self.subTest(text=text):
                self.assertFalse(self.extract(text))

    def test_quoted_or_unclosed_examples_are_not_law_references(self):
        phrase = "법에 의한 신고"
        for opening, closing in (("「", "」"), ("『", "』"), ("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")):
            with self.subTest(opening=opening):
                self.assertFalse(self.extract(opening + phrase + closing))
                self.assertFalse(self.extract(opening + phrase))
        self.assertFalse(self.extract('명칭은 「법 또는 다른 법률」이다.'))

    def test_shadowing_alias_definition_or_metadata_disables_family_fallback(self):
        for declaration in ('「다른법」(이하 "법"이라 한다). ',
                            '다른법(이하 "법"이라 한다). ',
                            '이 조에서 "법"이란 다른 법률을 말한다. '):
            self.assertFalse(self.extract(declaration + "법에 의한 신고를 한다."))
        self.assertFalse(self.extract("법에 의한 신고를 한다.", aliases={"법": "다른법"}))
        self.assertFalse(self.extract("법에 의한 신고를 한다.",
            articles=[{"text": '제1조 「다른법」(이하 "법"이라 한다).'}]))

    def test_explicit_definition_of_own_parent_remains_unambiguous(self):
        for declaration in ('「법인세법」(이하 "법"이라 한다). ',
                            '법인세법(이하 "법"이라 한다). '):
            self.assertEqual(self.extract(declaration + "법에 의한 신고를 한다.")[0]["target_name"], "법인세법")
        self.assertEqual(self.extract("법 또는 다른 법률의 규정", aliases={"법": "법인세법"})[0]["target_name"], "법인세법")

    def test_nearby_different_law_is_ambiguous_but_new_sentence_is_independent(self):
        self.assertFalse(self.extract("「국세기본법」에 따른 법에 의한 신고를 한다."))
        rows = self.extract("「국세기본법」에 따른다. 법에 의한 신고를 한다.")
        self.assertEqual(rows[0]["target_name"], "법인세법")

    def test_other_unnumbered_law_words_are_outside_this_helper(self):
        for text in ("법에 따른 신고", "법 및 다른 법률", "법 제60조에 따른 신고",
                     "법으로 정하는 경우", "그 밖의 법률에 따른 신고", "법 또는 다른 법령"):
            self.assertFalse(self.extract(text))
        self.assertEqual(len(self.extract("법 또는 다른 법률의 규정")), 1)

    def test_input_remains_unchanged(self):
        law, article = inputs("법에 의한 신고를 한다.", name="법인세법 시행령")
        before = deepcopy((law, article))
        tax_law_level_references(law, article)
        self.assertEqual((law, article), before)


if __name__ == "__main__":
    unittest.main()
