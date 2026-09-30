"""Validate the bounded GitHub review/task DOM and screenshot evidence."""

import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "tmp/task42extra/render/v2_review_task_eager_sha11ba4d"
FIRST = ROOT / "tmp/task42extra/render/v2_review_task_sha11ba4d"
CHECKS = ROOT / "tmp/task42extra/checks"
DEST = ROOT / "docs/task042extra_feinn_5nm/outcomes/records/render_check_v2.json"
PUBLISHED = "11ba4d46bee4fc2a8b06e28c191b35091f759782"
REVIEW = "0b61816c0189a2c05812044ab8e1d1513ef0407d"
TASK_PATH = "docs/task042extra_feinn_5nm/task.md"
REVIEW_PATH = "docs/task042extra_feinn_5nm/review_report_v1.md"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def rev_blob(revision, path):
    return subprocess.check_output(
        ["git", "rev-parse", f"{revision}:{path}"], cwd=ROOT, text=True
    ).strip()


def supervisor(label):
    candidates = sorted(
        path for path in CHECKS.glob(label + "_*")
        if re.fullmatch(r"\d{8}T\d{6}\d{6}Z", path.name[len(label) + 1:])
    )
    if len(candidates) != 1:
        raise ValueError(f"expected one supervision directory: {label}")
    return json.loads((candidates[0] / "summary.json").read_text())


def main():
    old = blob(REVIEW, TASK_PATH)
    new = blob(PUBLISHED, TASK_PATH)
    if old.count(b"\\operatorname{Re}") != 1:
        raise ValueError("old task macro identity differs")
    if old.replace(b"\\operatorname{Re}", b"\\mathrm{Re}") != new:
        raise ValueError("task changed beyond the one authorized macro replacement")
    if new != (ROOT / TASK_PATH).read_bytes():
        raise ValueError("local task differs from the published commit")
    if blob(PUBLISHED, REVIEW_PATH) != (ROOT / REVIEW_PATH).read_bytes():
        raise ValueError("local review differs from the published commit")
    if rev_blob(REVIEW, TASK_PATH) != "e231804fd8173acf7fc48cb17fc752e9b505c7ab":
        raise ValueError("old task blob differs")
    if rev_blob(PUBLISHED, TASK_PATH) != "a0d3606aedbbce37066338de3763fe802590dedb":
        raise ValueError("new task blob differs")

    raw = json.loads((RAW / "render_records.json").read_text())
    if len(raw["records"]) != 2:
        raise ValueError("both requested GitHub pages were not captured")
    pages = []
    for record, path, expected_math in zip(
        raw["records"], (REVIEW_PATH, TASK_PATH), (3, 7), strict=True
    ):
        dom = record["DOM"]
        if (f"/{PUBLISHED}/{path}" not in record["url"]
                or PUBLISHED not in dom["title"]
                or dom["ready"] != "complete" or dom["fonts"] != "loaded"
                or not dom["scopeHeading"].startswith(record["heading_prefix"])):
            raise ValueError(f"wrong GitHub rendered page: {path}")
        if len(dom["tables"]) != 6 or len(dom["mathAfterScroll"]) != expected_math:
            raise ValueError(f"missing rendered table or math element: {path}")
        columns = []
        for table in dom["tables"]:
            count = table["columns"]
            if len(count) < 3 or len(set(count)) != 1 or count[0] < 2:
                raise ValueError(f"rendered table columns differ: {path}")
            columns.append(count[0])
        for math in dom["mathAfterScroll"]:
            markup = (math["html"] or "") + (math["shadow"] or "")
            if (math["width"] <= 0 or math["height"] <= 0
                    or "katex-error" in markup or "macro not allowed" in markup):
                raise ValueError(f"rendered math error: {path}")
        shots = []
        for shot in record["screenshots"]:
            path_to_image = Path(shot["path"])
            if not path_to_image.is_relative_to(RAW) or digest(path_to_image) != shot["sha256"]:
                raise ValueError(f"screenshot hash differs: {path_to_image}")
            shots.append(dict(name=path_to_image.name, sha256=shot["sha256"]))
        pages.append(dict(
            path=path, url=record["url"], git_blob_sha=rev_blob(PUBLISHED, path),
            title=dom["title"], heading=dom["scopeHeading"],
            table_count=len(columns), table_columns=columns,
            math_count=len(dom["mathAfterScroll"]), math_error_count=0,
            screenshot_count=len(shots), screenshots=shots,
        ))
    first = supervisor("v2_render_review_task")
    second = supervisor("v2_render_review_task_eager")
    if (first["classification"] != "WORKER_FAILED"
            or second["classification"] != "COMPLETED"
            or second["leader_exit_code"] != 0
            or any(x["sampled_process_tree_rss_peak_bytes"] > 2 * 2**30
                   or x["sampled_process_tree_swap_peak_bytes"] != 0
                   or not x["descendants_cleared"] for x in (first, second))):
        raise ValueError("browser supervision or 2 GiB resource gate failed")
    failure = json.loads((FIRST / "render_failure.json").read_text())
    out = dict(
        schema="task42extra.render-check.v2",
        status="GITHUB_RENDERED_VIEW_PASS_AFTER_BOUNDED_RETRY",
        browser="native Linux Firefox/geckodriver; GitHub Preview rich HTML",
        published_commit=PUBLISHED,
        task_authorized_one_line_replacement=dict(
            old_blob=rev_blob(REVIEW, TASK_PATH), new_blob=rev_blob(PUBLISHED, TASK_PATH),
            old_macro="\\operatorname{Re}", new_macro="\\mathrm{Re}",
            exact_other_bytes_unchanged=True,
        ),
        pages=pages,
        first_attempt=dict(status=failure["status"],
                           reason="WebDriver GitHub navigation timed out after 60000 ms before any DOM capture",
                           completed_pages=len(failure["completed_records"]),
                           supervised_seconds=first["elapsed_seconds"],
                           peak_tree_RSS_bytes=first["sampled_process_tree_rss_peak_bytes"],
                           own_swap_peak_bytes=first["sampled_process_tree_swap_peak_bytes"]),
        successful_retry=dict(
            change="Firefox pageLoadStrategy=eager; no page content or numerical changes",
            supervised_seconds=second["elapsed_seconds"],
            peak_tree_RSS_bytes=second["sampled_process_tree_rss_peak_bytes"],
            own_swap_peak_bytes=second["sampled_process_tree_swap_peak_bytes"],
            descendants_cleared=second["descendants_cleared"],
            raw_DOM_sha256=digest(RAW / "render_records.json"),
            raw_directory=str(RAW),
        ),
        sampled_visual_inspection=[
            "00_top.png", "00_math-renderer_01.png",
            "01_math-renderer_06.png", "01_table_05.png",
        ],
        visual_scope="four sampled screenshots viewed; all 24 screenshots hash-checked and DOM inspected",
    )
    DEST.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": out["status"], "pages": len(pages),
                      "tables": sum(x["table_count"] for x in pages),
                      "math": sum(x["math_count"] for x in pages),
                      "screenshots": sum(x["screenshot_count"] for x in pages)}))


if __name__ == "__main__":
    main()
