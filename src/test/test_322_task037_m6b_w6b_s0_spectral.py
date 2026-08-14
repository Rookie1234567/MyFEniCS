from __future__ import annotations

import numpy as np

import benchmarks.run_task037_extra_m6b as runner
import src.solvers.hcurl_m6b_w6b_s0_spectral as w6b


def test_w6b_s0_fixed_subset_collection_is_not_a_scan():
    subsets = w6b.fixed_w6b_s0_subsets()
    assert tuple(subsets) == w6b.W6B_S0_SUBSET_NAMES
    assert len(subsets["legacy75"]) == 75
    assert len(subsets["full390"]) == 390
    for offset, order in enumerate((-7, -6, -5, -4, -3, -2, -1), 1):
        assert len(subsets[f"cumulative_through_order_m{order}"]) == 75 + 45 * offset
        assert len(subsets[f"leave_out_order_m{order}"]) == 345
    for component in range(3):
        assert len(subsets[f"legacy75_plus_component_{component}"]) == 180
    assert subsets["full390"] == tuple(range(390))


def test_w6b_s0_subset_energy_matches_dense_lstsq():
    matrix = np.asarray(
        [
            [1.0 + 0.2j, 0.5 - 0.1j, 0.0, 0.3j],
            [0.2 + 0.4j, 2.0 + 0.0j, 0.7 - 0.2j, 0.0],
            [0.0, 0.1 + 0.3j, 1.5 + 0.2j, 0.4],
            [0.3 - 0.1j, 0.0, 0.2j, 1.2 - 0.3j],
            [0.4, 0.2j, 0.6 - 0.1j, 0.8],
        ],
        dtype=np.complex128,
    )
    rhs = np.asarray(
        [1.0 + 0.5j, -0.2 + 0.1j, 0.7 - 0.4j, 0.3j, -0.5 + 0.2j],
        dtype=np.complex128,
    )
    gram = matrix.conjugate().T @ matrix
    indices = (0, 2, 3)
    factor_info = w6b._subset_factor(gram, indices)
    observed = w6b._subset_measurement(
        factor_info,
        matrix[:, indices].conjugate().T @ rhs,
        float(np.vdot(rhs, rhs).real),
    )
    reference = np.linalg.lstsq(matrix[:, indices], rhs, rcond=None)[0]
    reference_residual = rhs - matrix[:, indices] @ reference
    reference_rho = np.linalg.norm(reference_residual) / np.linalg.norm(rhs)
    assert abs(observed["rho"] - reference_rho) <= 1.0e-12
    assert observed["normal_equation_closure"] <= 1.0e-11
    assert observed["energy_closure"] <= 1.0e-11
    assert observed["finite"] is True


def test_w6b_s0_parser_is_fixed_and_source_bound():
    args = runner._parser().parse_args(
        [
            "m6b-w6b-s0",
            "--w6a-raw-dir",
            "w6a",
            "--w5-raw-dir",
            "w5",
            "--output",
            "result.json",
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.command == "m6b-w6b-s0"
    assert args.expected_source_sha == "a" * 40


def test_w6b_s0_w6a_summary_authority_rejects_self_consistent_wrong_hash():
    source = {
        "source_commit_full_sha": runner.M6B_W6B_S0_W6A_PRODUCER_SOURCE_SHA,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    summary = runner._attach_evidence(
        {
            "schema": runner.M6B_W6A_SCHEMA,
            "status": "gate_failed",
            "numeric_gate": {"pass": False},
            "source_at_start": source,
            "source_at_end": source,
        }
    )
    artifact = {
        "present": True,
        "path": "w6a_summary.json",
        "bytes": 1,
        "sha256": runner.M6B_W6B_S0_W6A_SUMMARY_FILE_SHA256,
    }
    assert runner._m6b_w6b_s0_w6a_summary_authority_valid(summary, artifact)
    wrong_hash = dict(artifact, sha256="0" * 64)
    assert not runner._m6b_w6b_s0_w6a_summary_authority_valid(summary, wrong_hash)
    wrong_source = dict(summary)
    wrong_source["source_at_end"] = dict(source, source_commit_full_sha="a" * 40)
    wrong_source = runner._attach_evidence(wrong_source)
    assert not runner._m6b_w6b_s0_w6a_summary_authority_valid(
        wrong_source, artifact
    )
