"""Check the new Task42extra Markdown and appended registry sections locally."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "docs/task042extra_feinn_5nm"
PAGES = [
    TASK / "task.md",
    TASK / "review_report_v1.md",
    TASK / "response_v1.md",
    TASK / "response_v2.md",
    *(
        TASK / "outcomes" / name
        for name in (
            "summary.md",
            "scaling_diagnostic_v2.md",
            "method_and_paper_mapping.md",
            "environment_and_isolation.md",
            "accuracy_performance_memory.md",
            "target_5nm_scale_plan.md",
            "test_summary.md",
            "changed_files.md",
        )
    ),
    ROOT / "docs/development_progress.md",
    ROOT / "docs/development_model_registry.md",
]
MD = MarkdownIt("commonmark").enable("table")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def table_columns(line):
    count = 0
    escaped = False
    for char in line:
        if char == "|" and not escaped:
            count += 1
        if char == "\\":
            escaped = not escaped
        else:
            escaped = False
    return count - 1 if line.rstrip().endswith("|") else count


def check_page(path, heading_prefix=None):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if heading_prefix:
        lines = text.splitlines(keepends=True)
        start = next((i for i,line in enumerate(lines)
                      if re.match(r"^#{1,6} ",line) and line.lstrip("# ").startswith(heading_prefix)), None)
        if start is None:
            raise ValueError(f"missing requested new section: {path}")
        level = len(lines[start])-len(lines[start].lstrip("#"))
        end = next((i for i in range(start+1,len(lines))
                    if re.match(r"^#{1,6} ",lines[i])
                    and len(lines[i])-len(lines[i].lstrip("#")) <= level),len(lines))
        text = "".join(lines[start:end])
    elif path.name in ("development_progress.md", "development_model_registry.md"):
        marker = (
            "## 2026-09-29 Task42extra"
            if path.name == "development_progress.md"
            else "## 3.44 Task42extra："
        )
        if marker not in text:
            raise ValueError(f"missing appended section: {path}")
        text = text[text.index(marker) :]
        if path.name == "development_model_registry.md":
            end = text.find("# 4. 今后新增模型的登记模板")
            if end < 0:
                raise ValueError("model registry section escaped chapter 3")
            text = text[:end]
    if "\ufffd" in text:
        raise ValueError(f"replacement character: {path}")
    lines = text.splitlines()
    fence = None
    math_count = 0
    tables = []
    active_table = []
    for i, line in enumerate(lines):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if match and fence is None:
            if active_table:
                tables.append(active_table)
                active_table = []
            fence = (match.group(1)[0], len(match.group(1)), match.group(2).strip())
            if fence[2] == "math":
                math_count += 1
                if i and lines[i - 1].strip():
                    raise ValueError(
                        f"math fence lacks preceding blank: {path}:{i + 1}"
                    )
            continue
        if fence and re.match(
            r"^ {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*$", line
        ):
            if fence[2] == "math" and i + 1 < len(lines) and lines[i + 1].strip():
                raise ValueError(f"math fence lacks following blank: {path}:{i + 1}")
            fence = None
            continue
        if fence:
            continue
        if "$$" in line or "\\[" in line or "\\]" in line:
            raise ValueError(f"nonstandard display math: {path}:{i + 1}")
        if line.strip() in ("=", "-"):
            raise ValueError(f"accidental Setext heading: {path}:{i + 1}")
        if line.startswith("|"):
            active_table.append(table_columns(line))
        elif active_table:
            tables.append(active_table)
            active_table = []
    if fence is not None:
        raise ValueError(f"unclosed fence: {path}")
    if active_table:
        tables.append(active_table)
    for columns in tables:
        if len(columns) < 3 or len(set(columns)) != 1:
            raise ValueError(f"misaligned Markdown table: {path} {columns}")
    tokens = MD.parse(text)
    parsed_tables = sum(token.type == "table_open" for token in tokens)
    if parsed_tables != len(tables):
        raise ValueError(
            f"Markdown parser disagrees on tables: {path} {parsed_tables}/{len(tables)}"
        )
    links = []
    for token in tokens:
        for child in token.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            links.append(href)
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            target = (path.parent / unquote(parts.path)).resolve()
            if not target.is_file():
                raise ValueError(f"broken local link: {path} -> {href}")
    if path.name == "summary.md" and not heading_prefix:
        headings = [
            int(m.group(1)) for line in lines if (m := re.match(r"^## (\d+)\. ", line))
        ]
        if headings != list(range(1, 17)) or len(tables) < 8:
            raise ValueError(
                f"summary contract failed: headings {headings}, tables {len(tables)}"
            )
    return dict(
        path=str(path.relative_to(ROOT)),
        sha256=sha(raw),
        checked_scope=heading_prefix or ("appended Task42extra section"
        if path.parent == ROOT / "docs"
        else "entire page"),
        markdown_tables=len(tables),
        parsed_tables=parsed_tables,
        math_fences=math_count,
        links=len(links),
    )


def main():
    baseline = subprocess.check_output(
        [
            "git",
            "show",
            "3b8474bff1b3cb9321a89afbca36868a9b95153d:docs/repository_work_principles.md",
        ],
        cwd=ROOT,
    )
    current = (ROOT / "docs/repository_work_principles.md").read_bytes()
    if current != baseline:
        raise ValueError("protected repository work principles changed")
    result = dict(
        schema="task42extra.markdown-local-check.v1",
        status="LOCAL_MARKDOWN_PASS",
        parser="markdown-it-py commonmark+table; independent raw fence/table/link checks",
        principles_unchanged_sha256=sha(current),
        pages=[check_page(path) for path in PAGES],
    )
    output = ROOT / "tmp/task42extra/development/markdown_check_v1.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            dict(
                status=result["status"],
                pages=len(PAGES),
                tables=sum(p["markdown_tables"] for p in result["pages"]),
            )
        )
    )


if __name__ == "__main__":
    main()
