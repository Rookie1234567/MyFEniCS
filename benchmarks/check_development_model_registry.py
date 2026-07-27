"""Read-only contract checker for the project development model registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


REGISTRY_RELATIVE_PATH = Path("docs/development_model_registry.md")
UNIFORM_HEADER = (
    "| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | "
    "总量/逐级/资源 | 结论/status | evidence |"
)
TASK_IDS = [
    *(f"Task{number:03d}" for number in range(14)),
    "Task014a",
    *(f"Task{number:03d}" for number in range(15, 36)),
    "Task035b",
    "Task035c",
    "Task035d",
]
SECTION_PATTERN = re.compile(
    r"^## 3\.(\d+) (Task(?:\d{3}|014a|035[bdc]))(?:：.*)?$",
    re.MULTILINE,
)
TRACKED_EVIDENCE_PATTERN = re.compile(
    r"`((?:docs|benchmarks)/[^`]+\.(?:md|csv|json))`"
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_registry(
    path: Path | None = None,
    *,
    root: Path | None = None,
) -> dict[str, object]:
    root = repository_root() if root is None else Path(root)
    path = root / REGISTRY_RELATIVE_PATH if path is None else Path(path)
    text = path.read_text(encoding="utf-8")
    matches = list(SECTION_PATTERN.finditer(text))
    errors: list[str] = []

    expected = [
        (index, task_id)
        for index, task_id in enumerate(TASK_IDS, start=1)
    ]
    actual = [
        (int(match.group(1)), match.group(2))
        for match in matches
    ]
    if actual != expected:
        errors.append(
            "Task sections are not the exact continuous 3.1–3.39 sequence"
        )

    hierarchy = (
        "## 1.1 COMSOL 收敛与求解器参考",
        "## 1.2 FEniCS 原始完整 FE 矩阵法：直接求解",
        "## 1.3 FEniCS 原始完整 FE 矩阵法：迭代求解",
        "## 1.4 静态凝聚法：直接求解",
        "## 1.5 静态凝聚法：迭代求解（待定）",
        "## 1.6 自适应求解",
    )
    for heading in hierarchy:
        if heading not in text:
            errors.append(f"missing method hierarchy heading: {heading}")

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else text.find(
            "\n# 4.",
            match.end(),
        )
        section = text[match.end() : end]
        task_id = match.group(2)
        if UNIFORM_HEADER not in section:
            errors.append(f"{task_id} lacks the uniform model table")
        prose = section.split(UNIFORM_HEADER, maxsplit=1)[0]
        if len(prose.strip()) < 35:
            errors.append(f"{task_id} lacks a plain-language task explanation")

    if "待回填" in text:
        errors.append("registry contains an unresolved placeholder")
    if "Task000–026 的逐 Task 重型模型尚未" in text:
        errors.append("registry still declares the historical ledger missing")
    if "0.161741" not in text:
        errors.append("Task009 corrected true residual is missing")
    for required_negative in (
        "T(-4)=4.354892e-7",
        "R(-4)=2.723391e-7",
        "0.861662/0.999661/0.996265",
    ):
        if required_negative not in text:
            errors.append(
                f"required concrete controlled-negative value missing: {required_negative}"
            )

    missing_evidence = sorted(
        {
            relative
            for relative in TRACKED_EVIDENCE_PATTERN.findall(text)
            if not (root / relative).exists()
        }
    )
    if missing_evidence:
        errors.extend(
            f"missing evidence path: {relative}"
            for relative in missing_evidence
        )

    return {
        "status": "pass" if not errors else "fail",
        "registry_path": str(path.relative_to(root)),
        "task_section_count": len(matches),
        "task_sequence": actual,
        "evidence_paths_checked": len(
            set(TRACKED_EVIDENCE_PATTERN.findall(text))
        ),
        "errors": errors,
        "read_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)
    audit = check_registry(args.registry)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
