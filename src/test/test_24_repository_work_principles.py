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
)


class RepositoryWorkPrinciplesTests(unittest.TestCase):
    def test_protected_files_exist_and_keep_markers(self) -> None:
        for path in PROTECTED_FILES:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                self.assertTrue(path.is_file(), f"missing protected governance file: {path}")
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


if __name__ == "__main__":
    unittest.main()
