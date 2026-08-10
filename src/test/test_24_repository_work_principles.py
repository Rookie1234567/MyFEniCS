from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROTECTED_FILES = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "docs" / "README.md",
    REPOSITORY_ROOT / "docs" / "repository_work_principles.md",
)
BEGIN_MARKER = "REPOSITORY_WORK_PRINCIPLES_BEGIN"
END_MARKER = "REPOSITORY_WORK_PRINCIPLES_END"
REQUIRED_CLAUSES = (
    "ChatGPT 不创建执行分支",
    "执行分支由 Codex 创建",
    "failed solver code 默认留在对应 research branch",
    "ordinary solver default 不得静默改变",
    "未通过最终 review 之前，不建议合并到 `master`",
    "official R/T/A 只能从通过 residual Gate 的场计算",
    "从 Task029 起，每个新 Task 必须同时维护结构化 `outcomes/summary.md` 和 `docs/development_progress.md`",
    (
        "从 Task032 起，中型和大型算法、物理或性能任务的 `outcomes/summary.md` "
        "必须以表格作为主要信息载体"
    ),
)

SAME_TASK_BRANCH_CLAUSES = (
    "一个 Task 从创建执行分支到最终批准期间，ChatGPT 与 Codex 的全部任务材料都只能提交到同一个执行分支",
    "ChatGPT 不得在活动任务期间向 `master` 写入 task、review 或规则修订",
    "review 直接提交同一执行分支",
    "Codex 从同一分支 fast-forward 拉取 review",
    "未经最终 review approval 和用户授权，不得 merge master",
    "最终 merge 由 Codex 执行并报告精确 master SHA、测试和工作树",
    "`master` 只接受最终批准的合并，不作为 review 中转分支",
)

FORMULA_STANDARD_CLAUSES = (
    "所有新建或修改的独立公式使用 GitHub fenced math block",
    "开 fence 为三个反引号加 math，闭 fence 为三个反引号",
    r"禁止新增多行 `$$` 或 `\[...\]`",
    "行内公式规则保持现有标准",
)


class RepositoryWorkPrinciplesTests(unittest.TestCase):
    def test_protected_files_exist_and_keep_markers(self) -> None:
        for path in PROTECTED_FILES:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                self.assertTrue(
                    path.is_file(), f"missing protected governance file: {path}"
                )
                text = path.read_text(encoding="utf-8")
                self.assertIn(BEGIN_MARKER, text)
                self.assertIn(END_MARKER, text)
                self.assertLess(text.index(BEGIN_MARKER), text.index(END_MARKER))

    def test_canonical_principles_keep_required_clauses(self) -> None:
        path = REPOSITORY_ROOT / "docs" / "repository_work_principles.md"
        text = path.read_text(encoding="utf-8")
        for clause in REQUIRED_CLAUSES:
            with self.subTest(clause=clause):
                self.assertIn(clause, text)

    def test_readmes_link_to_canonical_principles(self) -> None:
        root_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        docs_readme = (REPOSITORY_ROOT / "docs" / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("docs/repository_work_principles.md", root_readme)
        self.assertIn("repository_work_principles.md", docs_readme)

    def test_same_task_branch_rules_are_synchronized(self) -> None:
        for clause in SAME_TASK_BRANCH_CLAUSES:
            for path in PROTECTED_FILES:
                with self.subTest(
                    clause=clause, path=path.relative_to(REPOSITORY_ROOT)
                ):
                    self.assertIn(clause, path.read_text(encoding="utf-8"))

    def test_retrospective_clauses_are_synchronized_in_protected_files(self) -> None:
        for clause in REQUIRED_CLAUSES[-2:]:
            for path in PROTECTED_FILES:
                with self.subTest(
                    clause=clause, path=path.relative_to(REPOSITORY_ROOT)
                ):
                    self.assertIn(clause, path.read_text(encoding="utf-8"))

    def test_readmes_link_to_retrospective_standard(self) -> None:
        for path in PROTECTED_FILES[:2]:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                self.assertIn(
                    "task_retrospective_standard.md",
                    path.read_text(encoding="utf-8"),
                )

    def test_fenced_math_standard_is_synchronized(self) -> None:
        old_default_phrases = (
            "独立公式使用空行隔开的 `$$` block",
            "独立公式必须使用空行隔开的 `$$` block",
        )
        for path in PROTECTED_FILES:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                text = path.read_text(encoding="utf-8")
                for clause in FORMULA_STANDARD_CLAUSES:
                    with self.subTest(clause=clause):
                        self.assertIn(clause, text)
                for phrase in old_default_phrases:
                    with self.subTest(phrase=phrase):
                        self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
