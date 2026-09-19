"""API 키 없이 실행 가능한 오프라인 테스트 일괄 실행."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODULES: tuple[str, ...] = (
    "scripts.smoke_parallel_hints",
    "scripts.test_article_comparison_format",
    "scripts.test_citation_parser",
    "scripts.test_byeolpyo",
    "scripts.test_relative_law_resolution",
    "scripts.test_junyo_tagging",
    "scripts.test_article_relations",
    "scripts.test_new_article_scanner",
    "scripts.test_draft_bill_parser",
    "scripts.test_renumber_scan",
    "scripts.test_parallel_omission",
    "scripts.test_bridge_pairs",
    "scripts.test_ego_graph",
    "scripts.test_detail_plan",
    "scripts.test_document_text",
    "scripts.test_llm_fallback",
    "scripts.test_outline_intent",
    "scripts.test_related_article_129",
    "scripts.test_related_article_27",
    "scripts.test_review_queue",
    "scripts.test_citation_graph",
    "scripts.test_citation_scope",
    "scripts.test_boundary_review",
    "scripts.test_impact_ui",
    "scripts.test_galaxy_focus",
    "scripts.test_law_domains",
    "scripts.test_fsc_collection",
    "scripts.test_fsc_graph",
    "scripts.test_fsc_isolation",
    "scripts.test_fsc_sectors",
    "scripts.test_law_universe",
    "scripts.test_law_library",
    "scripts.test_app_navigation",
    "scripts.test_galaxy_updates",
    "scripts.test_local_tax_collection",
    "scripts.test_local_tax_graph",
    "scripts.test_procurement",
    "scripts.test_procurement_ui",
    "scripts.test_housing",
    "scripts.test_housing_ui",
    "scripts.test_environment",
    "scripts.test_environment_ui",
    "scripts.test_related_relation_types",
    "scripts.test_parallel_matrix",
)


def main() -> int:
    failed: list[str] = []
    print("Offline test suite (no API keys)\n")

    for mod in MODULES:
        print(f"--- {mod} ---")
        result = subprocess.run(
            [sys.executable, "-m", mod],
            cwd=ROOT,
        )
        if result.returncode != 0:
            failed.append(mod)
        print()

    if failed:
        print(f"FAILED ({len(failed)}/{len(MODULES)}):", ", ".join(failed), file=sys.stderr)
        return 1

    print(f"ALL PASSED ({len(MODULES)} modules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
