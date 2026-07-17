from __future__ import annotations

import json

from benchmarks.task033_reduced_scope_completion import (
    DEFAULT_RECORD,
    ROOT,
    build_reduced_scope_completion,
    verify_reduced_scope_completion,
)


def test_task033_reduced_scope_completion_is_current_and_fail_closed() -> None:
    record = build_reduced_scope_completion()
    assert record["status"] == "task033_reduced_scope_complete"
    assert record["identity"]["task033_reduced_scope_complete"]
    assert not record["identity"]["original_task033_full_scope_complete"]
    assert record["identity"]["adaptive_transferred_to_next_task"]
    assert not record["identity"]["ordinary_default_changed"]
    assert record["evidence"]["selective_merge_manifest"][
        "all_paths_file_level_exact"
    ]

    stored = json.loads((ROOT / DEFAULT_RECORD).read_text(encoding="utf-8"))
    assert stored == record
    verification = verify_reduced_scope_completion()
    assert verification["verified"]
