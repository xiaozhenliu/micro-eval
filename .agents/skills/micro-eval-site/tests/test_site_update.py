from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = SKILL_ROOT / "scripts" / "site_update.py"
SPEC = importlib.util.spec_from_file_location("micro_eval_site_update", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
site_update = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = site_update
SPEC.loader.exec_module(site_update)


class SiteUpdatePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.impact_map = site_update._load_impact_map()

    def build_plan(self, paths: list[str]) -> dict:
        return site_update._build_plan(
            REPO_ROOT,
            self.impact_map,
            base="HEAD",
            paths=paths,
        )

    def test_cli_and_ui_changes_map_to_pages_and_source_checks(self) -> None:
        plan = self.build_plan(
            [
                "src/micro_eval/cli/run.py",
                "ui/src/app/api/runs/route.ts",
            ]
        )

        self.assertEqual(
            [rule["id"] for rule in plan["matched_rules"]],
            ["cli", "web-ui"],
        )
        self.assertIn("site/reference/cli.md", plan["candidate_pages"])
        self.assertIn("site/zh/reference/cli.md", plan["candidate_pages"])
        self.assertEqual(
            plan["checks"],
            ["cli-contract", "site-build", "ui-contract"],
        )
        self.assertEqual(plan["unmapped_behavior_paths"], [])

    def test_new_behavior_domain_fails_closed_as_unmapped(self) -> None:
        plan = self.build_plan(["src/micro_eval/new_domain/feature.py"])

        self.assertEqual(
            plan["unmapped_behavior_paths"],
            ["src/micro_eval/new_domain/feature.py"],
        )
        self.assertIn(
            "unmapped behavior path: src/micro_eval/new_domain/feature.py",
            site_update._plan_failures(plan),
        )

    def test_current_site_has_complete_locale_pairs_and_live_candidates(self) -> None:
        plan = self.build_plan(["src/micro_eval/models/task.py"])

        self.assertEqual(plan["locale_pair_issues"], [])
        self.assertEqual(plan["missing_candidate_pages"], [])

    def test_representative_behavior_paths_cover_every_impact_domain(self) -> None:
        plan = self.build_plan(
            [
                "VERSION",
                "src/micro_eval/cli/run.py",
                "src/micro_eval/config/loader.py",
                "src/micro_eval/models/task.py",
                "src/micro_eval/models/run.py",
                "src/micro_eval/engine/kernel.py",
                "src/micro_eval/evaluation/validator.py",
                "src/micro_eval/decision/trend.py",
                "src/micro_eval/store/sqlite_store.py",
                "src/micro_eval/trace/process_provider.py",
                "src/micro_eval/server/queue.py",
                "ui/src/app/page.tsx",
                "examples/agent-codefix-showdown/eval.yaml",
                "examples/multi-task-matrix/eval.mock.yaml",
                "examples/git-workspace-isolation/run.py",
                "examples/conversational-eval/run.py",
                "examples/team-server-quickstart/run.py",
                "examples/README.md",
                "docs/engineering/security-guidelines.md",
            ]
        )

        self.assertEqual(plan["unmapped_behavior_paths"], [])
        self.assertEqual(
            {rule["id"] for rule in plan["matched_rules"]},
            {
                "version-and-installation",
                "cli",
                "configuration",
                "task-schema",
                "result-model",
                "execution-and-sandbox",
                "evaluation",
                "decision-and-trends",
                "storage",
                "trace-and-cost",
                "team-server",
                "web-ui",
                "agent-codefix-example",
                "multi-task-example",
                "workspace-isolation-example",
                "conversational-example",
                "team-server-example",
                "example-inventory",
                "security-guidance",
            },
        )


class SiteUpdateVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.impact_map = site_update._load_impact_map()
        cls.source_path = "src/micro_eval/cli/run.py"
        cls.english_page = "site/reference/cli.md"
        cls.chinese_page = "site/zh/reference/cli.md"

    def build_plan(self, paths: list[str]) -> dict:
        return site_update._build_plan(
            REPO_ROOT,
            self.impact_map,
            base="HEAD",
            paths=paths,
        )

    def test_updated_resolution_requires_real_bilingual_diff(self) -> None:
        plan = self.build_plan([self.source_path])
        current = self.build_plan(
            [self.source_path, self.english_page, self.chinese_page]
        )
        resolution = site_update._resolution_skeleton(plan)
        resolution["resolutions"][0].update(
            outcome="updated",
            pages=[self.english_page, self.chinese_page],
            rationale="Updated the CLI reference in both locales.",
        )

        failures = site_update._validate_resolution(plan, current, resolution)

        self.assertEqual(failures, ())

    def test_updated_resolution_rejects_missing_locale_counterpart(self) -> None:
        plan = self.build_plan([self.source_path])
        current = self.build_plan([self.source_path, self.english_page])
        resolution = site_update._resolution_skeleton(plan)
        resolution["resolutions"][0].update(
            outcome="updated",
            pages=[self.english_page],
            rationale="Updated only one locale.",
        )

        failures = site_update._validate_resolution(plan, current, resolution)

        self.assertTrue(
            any("omits locale counterpart" in failure for failure in failures)
        )

    def test_no_doc_impact_requires_a_rationale(self) -> None:
        plan = self.build_plan([self.source_path])
        resolution = site_update._resolution_skeleton(plan)
        resolution["resolutions"][0].update(
            outcome="no-doc-impact",
            pages=[],
            rationale="",
        )

        failures = site_update._validate_resolution(plan, plan, resolution)

        self.assertIn("resolution cli requires a rationale", failures)

    def test_complete_no_doc_impact_resolution_is_accepted(self) -> None:
        plan = self.build_plan([self.source_path])
        resolution = site_update._resolution_skeleton(plan)
        resolution["resolutions"][0].update(
            outcome="no-doc-impact",
            pages=[],
            rationale="The refactor preserves every user-visible CLI contract.",
        )

        failures = site_update._validate_resolution(plan, plan, resolution)

        self.assertEqual(failures, ())

    def test_moved_comparison_base_invalidates_plan(self) -> None:
        plan = self.build_plan([self.source_path])
        current = {**plan, "base_commit": "0" * 40}
        resolution = site_update._resolution_skeleton(plan)
        resolution["resolutions"][0].update(
            outcome="no-doc-impact",
            pages=[],
            rationale="The refactor preserves every user-visible CLI contract.",
        )

        failures = site_update._validate_resolution(plan, current, resolution)

        self.assertIn(
            "comparison base moved after planning; regenerate the plan",
            failures,
        )

    def test_rule_cannot_claim_another_rules_candidate_page(self) -> None:
        source_paths = [
            self.source_path,
            "ui/src/app/api/runs/route.ts",
        ]
        wrong_english = "site/reference/web-ui.md"
        wrong_chinese = "site/zh/reference/web-ui.md"
        current = self.build_plan(
            [*source_paths, wrong_english, wrong_chinese]
        )
        plan = self.build_plan(source_paths)
        resolution = site_update._resolution_skeleton(plan)
        resolution["resolutions"][0].update(
            outcome="updated",
            pages=[wrong_english, wrong_chinese],
            rationale="Incorrectly attributed the UI pages to the CLI rule.",
        )
        resolution["resolutions"][1].update(
            outcome="no-doc-impact",
            pages=[],
            rationale="The UI change has no reader-visible effect.",
        )

        failures = site_update._validate_resolution(plan, current, resolution)

        self.assertTrue(
            any("resolution cli uses non-candidate page" in item for item in failures)
        )


if __name__ == "__main__":
    unittest.main()
