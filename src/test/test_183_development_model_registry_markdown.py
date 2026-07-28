from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "development_model_registry.md"
COMSOL_REPORT = ROOT / "docs" / "COMSOL_direct_solver_report.md"


def _split_table_row(line: str) -> list[str]:
    """Split one GitHub-Markdown table row, ignoring escaped/code-span pipes."""

    stripped = line.strip()
    if not stripped.startswith("|"):
        raise ValueError(f"not a table row: {line!r}")
    cells: list[str] = []
    buffer: list[str] = []
    in_code = False
    escaped = False
    for char in stripped[1:]:
        if escaped:
            buffer.append(char)
            escaped = False
            continue
        if char == "\\":
            buffer.append(char)
            escaped = True
            continue
        if char == "`":
            in_code = not in_code
            buffer.append(char)
            continue
        if char == "|" and not in_code:
            cells.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(char)
    if buffer or not stripped.endswith("|"):
        cells.append("".join(buffer).strip())
    if cells and cells[-1] == "" and stripped.endswith("|"):
        cells.pop()
    return cells


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) is not None
        for cell in cells
    )


def _table_errors(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    errors: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            index += 1
            continue
        block: list[tuple[int, str]] = []
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            block.append((index + 1, lines[index]))
            index += 1
        if len(block) < 2:
            continue
        parsed = [(line_no, _split_table_row(line)) for line_no, line in block]
        if not _is_separator(parsed[1][1]):
            continue
        expected = len(parsed[0][1])
        for (line_no, original), (_, cells) in zip(block, parsed, strict=True):
            if len(cells) != expected:
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_no}: "
                    f"expected {expected} cells, found {len(cells)}; row={original!r}"
                )
    return errors


class DevelopmentModelRegistryMarkdownTest(unittest.TestCase):
    def test_all_tables_have_consistent_columns(self) -> None:
        errors = _table_errors(REGISTRY) + _table_errors(COMSOL_REPORT)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_fenced_code_blocks_are_closed(self) -> None:
        for path in (REGISTRY, COMSOL_REPORT):
            fence_count = sum(
                1
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.lstrip().startswith("```")
            )
            self.assertEqual(
                fence_count % 2,
                0,
                f"{path.relative_to(ROOT)} has an unclosed fenced code block",
            )

    def test_no_replacement_characters(self) -> None:
        for path in (REGISTRY, COMSOL_REPORT):
            self.assertNotIn("\ufffd", path.read_text(encoding="utf-8"), str(path))

    def test_comsol_registry_coverage(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        required = (
            "C-COMSOL-HO-S",
            "#### 二阶（p2）直接法",
            "#### 三阶（p3）直接法",
            "#### 四阶（p4）直接法",
            "#### 五阶（p5）直接法",
            "#### 六阶（p6）直接法",
            "#### p2 GMRES + GMG 网格序列",
            "#### COMSOL P 偏振求解器 profile 对照",
            "四面体 | 1.0 | `dset1` / `sol1` | 19,056,646",
            "六面体 | 0.8 | `dset2` / `sol2` | 8,802,928",
        )
        for token in required:
            self.assertIn(token, text)
        self.assertNotIn("相对直接法 `|Δ(R+T)|`", text)

    def test_task034_compact_authority_sentinels(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        for token in (
            "21,317,860 | 258,736,244",
            "155,421,000 | 565,926,400",
            "`4.082573e-12`（MPI8 same-grid authority）",
        ):
            self.assertIn(token, text)
        self.assertIn(
            "`7.031e-12` | 5.961403 | 734.218",
            text,
            "the separate MPI4 p4/h5 M160 funnel authority must remain",
        )


if __name__ == "__main__":
    unittest.main()
