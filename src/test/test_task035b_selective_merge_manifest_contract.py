from benchmarks.check_selective_merge_manifest import check_manifest


def test_task035b_selective_merge_manifest_covers_live_source_diff():
    audit = check_manifest(compare_live_diff=True)

    assert audit["status"] == "pass", audit["errors"]
    assert audit["row_count"] == audit["unique_path_count"]
