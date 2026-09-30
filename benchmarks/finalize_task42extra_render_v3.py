"""Verify exact published V3 GitHub DOM/math/table/screenshot evidence."""

import json
from pathlib import Path
import subprocess
import sys

from benchmarks.check_task42extra_v2 import ROOT, sha, write


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: finalize_task42extra_render_v3.py <raw-directory> <published-SHA>"
        )
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
            schema="task42extra.render-check.v3",
            status="RENDERED_VIEW_BLOCKED",
            published_commit=commit,
            raw_directory=str(raw),
            failure=failure,
        )
        write("render_check_v3.json", out)
        print(json.dumps(dict(status=out["status"], pages=0)))
        return
    captured = json.loads(source.read_text())
    pages = []
    for entry in captured["records"]:
        url = entry["url"]
        prefix = (
            "https://github.com/Rookie1234567/MyFEniCS/blob/" + commit + "/"
        )
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
        if relative.endswith("review_report_v2.md") and published_bytes != subprocess.check_output(
            ["git", "show", f"a668fb20dcf49f105cc4c7dfeeda145ee492ae14:{relative}"],
            cwd=ROOT,
        ):
            raise ValueError("Review V2 changed after publication")
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
    if not pages or not any("review_report_v2.md" in page["url"] for page in pages):
        raise ValueError("new review GitHub page was not captured")
    out = dict(
        schema="task42extra.render-check.v3",
        status="GITHUB_RENDERED_VIEW_PASS_DOM_AND_SAMPLED_VISUAL",
        published_commit=commit,
        raw_directory=str(raw),
        raw_DOM_sha256=sha(source),
        screenshots_hashed=sum(len(x["screenshots"]) for x in pages),
        pages=pages,
        scope="new Review V2 and V3/newly edited document sections only",
    )
    write("render_check_v3.json", out)
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
