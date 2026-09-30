"""Check only Review V2 and V3/newly edited Markdown, without old-page rerender."""

import json
from pathlib import Path

from benchmarks.check_task42extra_docs import ROOT, TASK, check_page


PAGES = [
    TASK / "review_report_v2.md",
    TASK / "response_v3.md",
    TASK / "outcomes/representation_diagnostic_v3.md",
    TASK / "outcomes/summary.md",
    TASK / "outcomes/test_summary.md",
    TASK / "outcomes/changed_files.md",
    ROOT / "docs/development_progress.md",
    ROOT / "docs/development_model_registry.md",
]


def main():
    records = [check_page(Path(path)) for path in PAGES]
    output = ROOT / "tmp/task42extra/development/markdown_check_v3.json"
    result = dict(
        schema="task42extra.markdown-local-check.v3",
        status="LOCAL_MARKDOWN_PASS",
        scope="Review V2 and V3 or modified docs only; old task/V1 pages excluded",
        pages=records,
    )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                status=result["status"],
                pages=len(records),
                tables=sum(x["markdown_tables"] for x in records),
            )
        )
    )


if __name__ == "__main__":
    main()
