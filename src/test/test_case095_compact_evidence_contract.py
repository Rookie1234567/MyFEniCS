from benchmarks.check_case095_compact_evidence import check_case095


def test_case095_compact_evidence_contract():
    audit = check_case095()

    assert audit["status"] == "case095_compact_authority_pass", audit[
        "failures"
    ]
    assert audit["record_count"] == 19
    assert audit["hash_verified_count"] == 19
    assert audit["h13_significant_gate"] == {
        "powers": 10,
        "amplitudes": 10,
    }
    assert audit["selective_trace_formal_pde_runs"] == 0
    assert audit["candidate_count"] == 68
    assert audit["candidate_availability_counts"] == {
        "source_branch_archive_not_merged": 45,
        "tracked_compact_authority": 18,
        "tracked_project_document": 5,
    }
    assert audit["candidate_compact_unique_records"] == 15
    assert audit["candidate_archive_local_reads"] == 0
