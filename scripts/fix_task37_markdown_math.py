#!/usr/bin/env python3
"""Normalize Task37 Markdown math delimiters for GitHub rendering.

GitHub renders inline math with ``$...$`` and display math with delimiter lines
containing ``$$``.  A number of Task37 documents were written with LaTeX-style
``\\(...\\)`` and ``\\[...\\]`` delimiters, which are not rendered consistently
by GitHub Markdown.

The script intentionally limits its scope to Task37 documentation and the
matching Case100 Markdown evidence.  Fenced code blocks are never modified.

Usage:

    python scripts/fix_task37_markdown_math.py
    python scripts/fix_task37_markdown_math.py --check
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ROOTS = (
    REPOSITORY_ROOT / "docs/task037_static_condensed_full3d_iterative",
    REPOSITORY_ROOT / "benchmarks/cases/100_static_condensed_full3d_iterative",
)

FENCE_PATTERN = re.compile(r"^\s*(```+|~~~+)")
DISPLAY_OPEN_PATTERN = re.compile(r"^(?P<indent>\s*)\\\[\s*$")
DISPLAY_CLOSE_PATTERN = re.compile(r"^(?P<indent>\s*)\\\]\s*$")
SAME_LINE_DISPLAY_PATTERN = re.compile(r"\\\[(?P<body>.+?)\\\]")
INLINE_CODE_SPLIT_PATTERN = re.compile(r"(`+[^`]*`+)")


class MarkdownMathError(RuntimeError):
    """Raised when a document still contains unsupported delimiters."""


def _transform_text_segment(segment: str) -> str:
    """Transform a non-code text segment."""

    # A same-line display expression is semantically inline in Markdown.  Use
    # single-dollar delimiters so it does not create an invalid block in a
    # paragraph.
    segment = SAME_LINE_DISPLAY_PATTERN.sub(
        lambda match: f"${match.group('body').strip()}$",
        segment,
    )
    segment = segment.replace(r"\(", "$ ").replace(r"\)", " $")
    # Remove the helper spaces only when they touch an existing space.  This
    # keeps words from being glued to the formula while avoiding doubled gaps.
    segment = segment.replace("$  ", "$ ").replace("  $", " $")
    return segment


def _transform_inline_outside_code(line: str) -> str:
    """Transform inline delimiters while preserving Markdown code spans."""

    parts = INLINE_CODE_SPLIT_PATTERN.split(line)
    for index in range(0, len(parts), 2):
        parts[index] = _transform_text_segment(parts[index])
    return "".join(parts)


def transform_markdown(text: str) -> str:
    """Return normalized Markdown without touching fenced code blocks."""

    output: list[str] = []
    in_fence = False
    fence_marker: str | None = None

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        newline = raw_line[len(line) :]
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_kind = marker[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker_kind
            elif marker_kind == fence_marker:
                in_fence = False
                fence_marker = None
            output.append(raw_line)
            continue

        if in_fence:
            output.append(raw_line)
            continue

        open_match = DISPLAY_OPEN_PATTERN.match(line)
        if open_match:
            output.append(f"{open_match.group('indent')}$$" + newline)
            continue

        close_match = DISPLAY_CLOSE_PATTERN.match(line)
        if close_match:
            output.append(f"{close_match.group('indent')}$$" + newline)
            continue

        output.append(_transform_inline_outside_code(line) + newline)

    return "".join(output)


def _unsupported_tokens(text: str) -> list[tuple[int, str]]:
    """Return unsupported delimiter occurrences outside fenced code blocks."""

    failures: list[tuple[int, str]] = []
    in_fence = False
    fence_marker: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            marker_kind = fence_match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker_kind
            elif marker_kind == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue

        text_parts = INLINE_CODE_SPLIT_PATTERN.split(line)
        prose = "".join(text_parts[0::2])
        if any(token in prose for token in (r"\[", r"\]", r"\(", r"\)")):
            failures.append((line_number, line))

    return failures


def _markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in DOCUMENT_ROOTS:
        if root.exists():
            files.extend(path for path in root.rglob("*.md") if path.is_file())
    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not modify files; fail if normalization is needed",
    )
    arguments = parser.parse_args()

    files = _markdown_files()
    if not files:
        raise MarkdownMathError("no Task37 Markdown files were found")

    changed: list[Path] = []
    validation_failures: list[str] = []

    for path in files:
        original = path.read_text(encoding="utf-8")
        normalized = transform_markdown(original)
        failures = _unsupported_tokens(normalized)
        if failures:
            relative = path.relative_to(REPOSITORY_ROOT)
            details = ", ".join(str(line) for line, _text in failures[:10])
            validation_failures.append(f"{relative}: lines {details}")
            continue

        if normalized != original:
            changed.append(path)
            if not arguments.check:
                path.write_text(normalized, encoding="utf-8")

    if validation_failures:
        print("Unsupported math delimiters remain:", file=sys.stderr)
        for failure in validation_failures:
            print(f"  {failure}", file=sys.stderr)
        return 2

    if arguments.check and changed:
        print("Markdown math normalization is required:", file=sys.stderr)
        for path in changed:
            print(f"  {path.relative_to(REPOSITORY_ROOT)}", file=sys.stderr)
        return 1

    action = "would normalize" if arguments.check else "normalized"
    print(f"{action} {len(changed)} Markdown file(s)")
    for path in changed:
        print(path.relative_to(REPOSITORY_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
