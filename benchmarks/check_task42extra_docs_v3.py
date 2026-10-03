"""Check the selected review and new Markdown sections without old-page rerender."""

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
    version = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    if version == 12:
        pages = [
            (TASK / "review_report_v11.md", None),
            (TASK / "response_v12.md", None),
            (TASK / "outcomes/diagnostic_attribution_v12.md", None),
            (TASK / "outcomes/auxiliary_role_decision_v12.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V11 后续：V12"),
            (TASK / "outcomes/test_summary.md", "Review V11 后续 V12 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V11 后续 V12 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-10-03 Task42extra V12"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.11 Task42extra Review V11 后续",
            ),
        ]
    elif version == 11:
        pages = [
            (TASK / "review_report_v10.md", None),
            (TASK / "response_v11.md", None),
            (TASK / "outcomes/parameter_metric_v11.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V10 后续：V11"),
            (TASK / "outcomes/test_summary.md", "Review V10 后续 V11 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V10 后续 V11 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-10-02 Task42extra V11"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.10 Task42extra Review V10 后续",
            ),
        ]
    elif version == 10:
        pages = [
            (TASK / "review_report_v9.md", None),
            (TASK / "response_v10.md", None),
            (TASK / "outcomes/derivative_reuse_v10.md", None),
            (TASK / "outcomes/cached_gn_v10.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V9 后续：V10"),
            (TASK / "outcomes/test_summary.md", "Review V9 后续 V10 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V9 后续 V10 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-10-02 Task42extra V10"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.9 Task42extra Review V9 后续",
            ),
        ]
    elif version == 9:
        pages = [
            (TASK / "review_report_v8.md", None),
            (TASK / "response_v9.md", None),
            (TASK / "outcomes/p_ladder_v9.md", None),
            (TASK / "outcomes/damped_gn_v9.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V8 后续：V9"),
            (TASK / "outcomes/test_summary.md", "Review V8 后续 V9 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V8 后续 V9 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-10-01 Task42extra V9"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.8 Task42extra Review V8 后续",
            ),
        ]
    elif version == 8:
        pages = [
            (TASK / "review_report_v7.md", None),
            (TASK / "response_v8.md", None),
            (TASK / "outcomes/authority_recovery_v8.md", None),
            (TASK / "outcomes/phase_feinn_v8.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V7 后续：V8"),
            (TASK / "outcomes/test_summary.md", "Review V7 后续 V8 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V7 后续 V8 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-10-01 Task42extra V8"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.7 Task42extra Review V7 后续",
            ),
        ]
    elif version == 7:
        pages = [
            (TASK / "review_report_v6.md", None),
            (TASK / "response_v7.md", None),
            (TASK / "outcomes/p3_p4_authority_v7.md", None),
            (TASK / "outcomes/phase_representation_plan_v7.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V6 后续：V7"),
            (TASK / "outcomes/test_summary.md", "Review V6 后续 V7 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V6 后续 V7 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-09-30 Task42extra V7"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.6 Task42extra Review V6 后续",
            ),
        ]
    elif version == 6:
        pages = [
            (TASK / "review_report_v5.md", None),
            (TASK / "response_v6.md", None),
            (TASK / "outcomes/frozen_feature_residual_v6.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V5 后续：V6"),
            (TASK / "outcomes/test_summary.md", "Review V5 后续 V6 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V5 后续 V6 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-09-30 Task42extra V6"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.5 Task42extra Review V5 后续",
            ),
        ]
    elif version == 5:
        pages = [
            (TASK / "review_report_v4.md", None),
            (TASK / "response_v5.md", None),
            (TASK / "outcomes/frozen_hidden_readout_v5.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V4 后续：V5"),
            (TASK / "outcomes/test_summary.md", "Review V4 后续 V5 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V4 后续 V5 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-09-30 Task42extra V5"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.4 Task42extra Review V4 后续",
            ),
        ]
    elif version == 4:
        pages = [
            (TASK / "review_report_v3.md", None),
            (TASK / "response_v4.md", None),
            (TASK / "outcomes/durable_replay_v4.md", None),
            (TASK / "outcomes/summary.md", "Task42extra Review V3 后续：V4"),
            (TASK / "outcomes/test_summary.md", "Review V3 后续 V4 定向资格"),
            (TASK / "outcomes/changed_files.md", "Review V3 后续 V4 文件级边界"),
            (ROOT / "docs/development_progress.md", "2026-09-30 Task42extra V4"),
            (
                ROOT / "docs/development_model_registry.md",
                "3.44.3 Task42extra Review V3 后续",
            ),
        ]
    elif version == 3:
        pages = [(path, None) for path in PAGES]
    else:
        raise ValueError("unsupported document version")
    records = [check_page(Path(path), heading) for path, heading in pages]
    output = ROOT / f"tmp/task42extra/development/markdown_check_v{version}.json"
    result = dict(
        schema=f"task42extra.markdown-local-check.v{version}",
        status="LOCAL_MARKDOWN_PASS",
        scope="Review V2 and V3 or modified docs only; old task/V1 pages excluded"
        if version == 3
        else f"new Review V{version - 1} and only new V{version} sections; historical Markdown contracts reused",
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
