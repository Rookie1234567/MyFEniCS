"""Check only Review V2 and V3/newly edited Markdown, without old-page rerender."""

import json
from pathlib import Path
import sys

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
    version = int(sys.argv[1]) if len(sys.argv)>1 else 3
    if version == 4:
        pages = [(TASK/"review_report_v3.md",None), (TASK/"response_v4.md",None),
                 (TASK/"outcomes/durable_replay_v4.md",None),
                 (TASK/"outcomes/summary.md","Task42extra Review V3 后续：V4"),
                 (TASK/"outcomes/test_summary.md","Review V3 后续 V4 定向资格"),
                 (TASK/"outcomes/changed_files.md","Review V3 后续 V4 文件级边界"),
                 (ROOT/"docs/development_progress.md","2026-09-30 Task42extra V4"),
                 (ROOT/"docs/development_model_registry.md","3.44.3 Task42extra Review V3 后续")]
    elif version == 3:
        pages = [(path,None) for path in PAGES]
    else:
        raise ValueError("unsupported document version")
    records = [check_page(Path(path), heading) for path,heading in pages]
    output = ROOT / f"tmp/task42extra/development/markdown_check_v{version}.json"
    result = dict(
        schema=f"task42extra.markdown-local-check.v{version}",
        status="LOCAL_MARKDOWN_PASS",
        scope="Review V2 and V3 or modified docs only; old task/V1 pages excluded" if version==3 else "new Review V3 and only new V4 sections; historical Markdown contracts reused",
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
