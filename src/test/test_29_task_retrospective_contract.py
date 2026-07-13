from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPOSITORY_ROOT / "docs"
STANDARD = DOCS / "task_retrospective_standard.md"
PROGRESS = DOCS / "development_progress.md"


def _task029_progress_section() -> str:
    text = PROGRESS.read_text(encoding="utf-8")
    start_match = re.search(
        r"^# 36\. Task029：Stage4 direct memory forensics\s*$", text, re.MULTILINE
    )
    if start_match is None:
        return ""
    end_match = re.search(r"^# 37\.", text[start_match.end() :], re.MULTILINE)
    end = len(text) if end_match is None else start_match.end() + end_match.start()
    return text[start_match.start() : end]


def _task030_progress_section() -> str:
    text = PROGRESS.read_text(encoding="utf-8")
    start_match = re.search(
        r"^# 41\. Task030：3D H\(curl\) 多层与低内存迭代研究\s*$",
        text,
        re.MULTILINE,
    )
    if start_match is None:
        return ""
    end_match = re.search(r"^# 42\.", text[start_match.end() :], re.MULTILINE)
    end = len(text) if end_match is None else start_match.end() + end_match.start()
    return text[start_match.start() : end]


class TaskRetrospectiveContractTests(unittest.TestCase):
    def test_retrospective_standard_exists_and_is_indexed(self) -> None:
        self.assertTrue(STANDARD.is_file())
        docs_readme = (DOCS / "README.md").read_text(encoding="utf-8")
        self.assertIn("task_retrospective_standard.md", docs_readme)
        self.assertIn("所有新 Task", docs_readme)

    def test_repository_principles_make_retrospective_mandatory(self) -> None:
        principles = (DOCS / "repository_work_principles.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "每个新 Task 必须同时维护结构化 `outcomes/summary.md` 和 "
            "`docs/development_progress.md`",
            principles,
        )
        self.assertIn("一句状态或纯文件链接不构成完成", principles)
        self.assertIn("task_retrospective_standard.md", principles)

    def test_task029_has_a_substantive_independent_progress_chapter(self) -> None:
        section = _task029_progress_section()
        self.assertGreater(len(section), 5000)
        required_headings = (
            "为什么启动",
            "冻结问题与 baseline",
            "采用的方法",
            "关键结果",
            "结果解释",
            "最终决策与合并边界",
            "局限",
            "下一步及原因",
            "证据入口",
        )
        for heading in required_headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, section)

    def test_task029_chapter_has_status_and_evidence_links(self) -> None:
        section = _task029_progress_section()
        required_status = (
            "classification = diagnostic_success",
            "engineering_success = no",
            "h2 = not_run",
            "threaded_direct_capability = unavailable_in_current_image",
        )
        required_links = (
            "task029_stage4_direct_memory_forensics/outcomes/summary.md",
            "task029_stage4_direct_memory_forensics/review_report_v1.md",
            "../benchmarks/cases/050_stage4_direct_memory_forensics/README.md",
        )
        for value in (*required_status, *required_links):
            with self.subTest(value=value):
                self.assertIn(value, section)

    def test_task029_outcome_summary_uses_the_standard_structure(self) -> None:
        summary = (
            DOCS / "task029_stage4_direct_memory_forensics" / "outcomes" / "summary.md"
        ).read_text(encoding="utf-8")
        required = (
            "任务目标与非目标",
            "基线、冻结配置和环境",
            "实现与方法",
            "实验/运行矩阵",
            "关键结果表",
            "根因解释",
            "失败、负结果与未运行项",
            "最终合并建议",
            "下一步决定",
            "证据索引",
        )
        for heading in required:
            with self.subTest(heading=heading):
                self.assertIn(heading, summary)

    def test_future_task_process_references_the_standard(self) -> None:
        standard = STANDARD.read_text(encoding="utf-8")
        docs_readme = (DOCS / "README.md").read_text(encoding="utf-8")
        self.assertIn("从 Task029 起", standard)
        self.assertIn(
            "task.md -> outcomes -> development_progress -> review_report/response",
            docs_readme,
        )
        self.assertIn("task_retrospective_standard.md", docs_readme)

    def test_task030_has_substantive_progress_and_outcome_records(self) -> None:
        section = _task030_progress_section()
        self.assertGreater(len(section), 4500)
        required = (
            "为什么启动",
            "冻结基线",
            "层级与 transfer 基础设施",
            "多 lane 漏斗与负结果",
            "正反馈如何继续深化",
            "h5/h3/h2 正式结果",
            "h2 预测、实测与当前边界",
            "合并边界",
            "局限与下一步因果关系",
            "证据入口",
        )
        for heading in required:
            with self.subTest(heading=heading):
                self.assertIn(heading, section)

        outcomes = (
            DOCS / "task030_multilevel_hcurl_low_memory_iterative_solver" / "outcomes"
        )
        summary = (outcomes / "summary.md").read_text(encoding="utf-8")
        for value in (
            "workstation_success",
            "ordinary_default_changed = false",
            "五个 p/h 候选",
            "正式 h5/h3/h2 结果",
            "合并决策",
            "局限与下一步",
            "证据入口",
        ):
            with self.subTest(value=value):
                self.assertIn(value, summary)

    def test_case060_lightweight_contract_is_indexed_and_parseable(self) -> None:
        import json

        case = (
            REPOSITORY_ROOT
            / "benchmarks"
            / "cases"
            / "060_multilevel_hcurl_iterative_solver"
        )
        cases_index = (case.parent / "README.md").read_text(encoding="utf-8")
        docs_index = (DOCS / "README.md").read_text(encoding="utf-8")
        self.assertIn("060_multilevel_hcurl_iterative_solver", cases_index)
        self.assertIn("Task030", docs_index)
        for relative in (
            "config.json",
            "expected/gates.json",
            "records/h5_baseline.json",
            "records/hierarchy_contract.json",
            "records/transfer_contract.json",
            "records/candidate_screen_summary.json",
            "records/best_h5.json",
            "records/best_h3.json",
            "records/best_h2.json",
        ):
            with self.subTest(relative=relative):
                payload = json.loads((case / relative).read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
        config = json.loads((case / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["ordinary_default_changed"])


if __name__ == "__main__":
    unittest.main()
