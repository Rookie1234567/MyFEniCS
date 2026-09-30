"""Verify published GitHub DOM/math/table/screenshots for V3 or opt-in V4."""

import json
from pathlib import Path
import subprocess
import sys

from benchmarks.check_task42extra_v2 import ROOT, sha, write


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit(
            "usage: finalize_task42extra_render_v3.py <raw-directory> <published-SHA> [3|4]"
        )
    version = int(sys.argv[3]) if len(sys.argv) == 4 else 3
    if version not in (3, 4):
        raise ValueError("unsupported evidence version")
    review_name = "review_report_v2.md" if version == 3 else "review_report_v3.md"
    review_commit = "a668fb20dcf49f105cc4c7dfeeda145ee492ae14" if version == 3 else "4dc7c38b60acf2a5ee3d9c6b9770b084a874fb04"
    record_name = f"render_check_v{version}.json"
    raw = (ROOT / "tmp/task42extra/render" / sys.argv[1]).resolve()
    if not raw.is_relative_to((ROOT / "tmp/task42extra/render").resolve()):
        raise ValueError("render directory escapes task-local cache")
    commit = sys.argv[2]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("full published commit SHA required")
    source = raw / "render_records.json"
    if not source.exists():
        failure = (
            json.loads((raw / "render_failure.json").read_text())
            if (raw / "render_failure.json").exists()
            else "NO_BROWSER_RECORD"
        )
        out = dict(
            schema=f"task42extra.render-check.v{version}",
            status="RENDERED_VIEW_BLOCKED",
            published_commit=commit,
            raw_directory=str(raw),
            failure=failure,
        )
        write(record_name, out)
        print(json.dumps(dict(status=out["status"], pages=0)))
        return
    captured = json.loads(source.read_text())
    if version == 4:
        expected = json.loads((raw / "expected_urls.json").read_text())
        actual = [entry["url"] for entry in captured["records"]]
        if actual != [entry["url"] for entry in expected] or (raw / "render_failure.json").exists():
            write(record_name, dict(schema="task42extra.render-check.v4", status="RENDERED_VIEW_BLOCKED",
                                    published_commit=commit, raw_directory=str(raw),
                                    raw_DOM_sha256=sha(source), captured_pages=len(actual),
                                    reason="partial browser capture or render failure; incomplete pages not qualified"))
            return
    pages = []
    for entry in captured["records"]:
        url = entry["url"]
        prefix = "https://github.com/Rookie1234567/MyFEniCS/blob/" + commit + "/"
        if not url.startswith(prefix):
            raise ValueError("rendered GitHub URL is not the published commit")
        relative = url[len(prefix) :]
        if (
            f"/{commit}/docs/task042extra_feinn_5nm/" not in url
            and f"/{commit}/docs/development_" not in url
        ):
            raise ValueError("rendered URL not exact published task document")
        published_bytes = subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"], cwd=ROOT
        )
        if published_bytes != (ROOT / relative).read_bytes():
            raise ValueError("local Markdown differs from the published blob")
        git_blob = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{relative}"], cwd=ROOT, text=True
        ).strip()
        if relative.endswith(review_name) and published_bytes != subprocess.check_output(
            ["git", "show", f"{review_commit}:{relative}"],
            cwd=ROOT,
        ):
            raise ValueError("review changed after publication")
        dom = entry["DOM"]
        if (
            commit not in dom["title"]
            or dom["ready"] != "complete"
            or dom["fonts"] != "loaded"
        ):
            raise ValueError("wrong/incomplete GitHub rendered DOM")
        if entry["heading_prefix"] and not dom["scopeHeading"].startswith(
            entry["heading_prefix"]
        ):
            raise ValueError("requested new heading not rendered")
        cols = []
        for table in dom["tables"]:
            shape = table["columns"]
            if len(shape) < 3 or len(set(shape)) != 1 or shape[0] < 2:
                raise ValueError("GitHub table columns broken")
            cols.append(shape[0])
        if relative.endswith("review_report_v2.md") and (
            len(cols) != 4 or len(dom["mathAfterScroll"]) != 5
        ):
            raise ValueError("Review V2 table/math DOM inventory incomplete")
        if relative.endswith("review_report_v3.md") and (
            len(cols) != 4 or len(dom["mathAfterScroll"]) != 1
        ):
            raise ValueError("Review V3 table/math DOM inventory incomplete")
        if relative.endswith("representation_diagnostic_v3.md") and (
            len(cols) != 3 or len(dom["mathAfterScroll"]) != 2
        ):
            raise ValueError("V3 diagnostic table/math DOM inventory incomplete")
        for math in dom["mathAfterScroll"]:
            markup = (math["html"] or "") + (math["shadow"] or "")
            if (
                math["width"] <= 0
                or math["height"] <= 0
                or "katex-error" in markup
                or "macro not allowed" in markup
            ):
                raise ValueError("GitHub math rendering failed")
        shots = []
        for item in entry["screenshots"]:
            path = Path(item["path"]).resolve()
            if not path.is_relative_to(raw) or sha(path) != item["sha256"]:
                raise ValueError("screenshot outside task cache or digest mismatch")
            shots.append(dict(name=path.name, sha256=item["sha256"]))
        pages.append(
            dict(
                url=url,
                git_blob_sha=git_blob,
                heading=dom["scopeHeading"],
                title=dom["title"],
                tables=len(cols),
                columns=cols,
                math=len(dom["mathAfterScroll"]),
                screenshots=shots,
                visual_review="sampled screenshots only",
            )
        )
    if not pages or not any(review_name in page["url"] for page in pages):
        raise ValueError("new review GitHub page was not captured")
    out = dict(
        schema=f"task42extra.render-check.v{version}",
        status="GITHUB_RENDERED_VIEW_PASS_DOM_AND_SAMPLED_VISUAL",
        published_commit=commit,
        raw_directory=str(raw),
        raw_DOM_sha256=sha(source),
        screenshots_hashed=sum(len(x["screenshots"]) for x in pages),
        pages=pages,
        scope="new Review V2 and V3/newly edited document sections only" if version == 3 else "new Review V3 and V4/newly edited sections only; no historical batch rerender",
    )
    write(record_name, out)
    print(
        json.dumps(
            dict(
                status=out["status"],
                pages=len(pages),
                tables=sum(x["tables"] for x in pages),
                math=sum(x["math"] for x in pages),
            )
        )
    )


if __name__ == "__main__":
    main()
