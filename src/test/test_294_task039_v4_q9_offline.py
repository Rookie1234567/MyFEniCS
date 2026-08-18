import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task039_v4_q9_offline_audit import audit_q_a
from benchmarks.task039_v4_q9_qb_component import (
    _pair_targets,
    _json_default,
    audit_qep_sign_involution,
)
from benchmarks.task039_v4_q9_qc_component import match_beta_sets


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_case(
    tmp_path: Path, *, summary_status: str = "not_measured"
) -> dict[str, Path]:
    packet = tmp_path / "packet"
    packet.mkdir()
    mode_count = 3
    ownership = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, 12), (12, 14), (14, 17)]
    names = ("positive_right", "positive_left", "negative_right", "negative_left")
    shards = []
    for rank, (start, end) in enumerate(ownership):
        files = {}
        for column, name in enumerate(names):
            path = packet / f"rank{rank:04d}_{name}.npy"
            np.save(
                path,
                np.full((mode_count, end - start), column + rank, dtype=np.complex128),
            )
            files[name] = {
                "path": path.name,
                "sha256": _sha256(path),
                "shape": [mode_count, end - start],
                "dtype": "complex128",
                "layout": "mode_major",
                "bytes": path.stat().st_size,
            }
        shards.append(
            {
                "rank": rank,
                "ownership_range": [start, end],
                "rows": end - start,
                "files": files,
            }
        )
    identity = {"source_sha": "source", "mode_count": mode_count}
    (packet / "identity.json").write_text(json.dumps(identity))
    manifest = {
        "schema": "myfenics.modes.selected_mode_packet.v1",
        "scope": "tiny",
        "mode_count": mode_count,
        "rank_count": 8,
        "global_size": 17,
        "identity": identity,
        "identity_sha256": "unused-in-audit",
        "qep_workspace_persisted": False,
        "consumer_qep_required": False,
        "shards": shards,
    }
    manifest_path = packet / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    root = tmp_path / "summary.json"
    root.write_text(
        json.dumps(
            {
                "resource_authority": {
                    "process_tree_peak_rss_mb": 123.0,
                    "process_tree_peak_swap_mb": 0.0,
                    "peak_pss_mb": None,
                    "peak_uss_mb": None,
                    "telemetry_status": summary_status,
                }
            }
        )
    )
    telemetry = tmp_path / "markers.jsonl"
    telemetry.write_text(
        json.dumps(
            {
                "name": "lift",
                "detail": {
                    "replicated_numpy_array_bytes_per_rank": 48,
                    "replicated_numpy_array_bytes_process_tree": 384,
                    "classification": "derived_complex128_dense_buffer",
                },
            }
        )
        + "\n"
    )
    mode_worker = tmp_path / "mode_worker.json"
    mode_worker.write_text(
        json.dumps(
            {
                "status": "controlled_stop_packet_written",
                "producer_qep": {
                    branch: {
                        "requested_modes": 4,
                        "converged_modes": 4,
                        "iteration_count": 2,
                        "convergence_reason": 1,
                    }
                    for branch in ("positive", "negative")
                },
                "selection": {
                    branch: {"candidate_modes": 4, "selected_modes": 3}
                    for branch in ("positive", "negative")
                },
            }
        )
    )
    direct_worker = tmp_path / "direct_worker.json"
    direct_worker.write_text(
        json.dumps(
            {
                "selected_mode_packet_consumer": {
                    "modes_released_before_factor": {
                        "packet_bundle_destroyed": True,
                        "vector_count_after_destroy": 0,
                        "modal_bases_detached": True,
                        "factor_modes_overlap": False,
                    },
                    "post_factor_rehydrate": True,
                },
                "object_payload_ledger": {"retained_right_left_eigenvector_bytes": 96},
            }
        )
    )
    iterative_worker = tmp_path / "iterative_worker.json"
    iterative_worker.write_text(
        json.dumps({"selected_mode_packet_consumer": {"qep_calls": 0}})
    )
    output = tmp_path / "audit.json"
    return {
        "manifest": manifest_path,
        "summary": root,
        "mode_worker": mode_worker,
        "direct_worker": direct_worker,
        "iterative_worker": iterative_worker,
        "telemetry": telemetry,
        "output": output,
    }


def _audit(case: dict[str, Path]) -> dict[str, object]:
    return audit_q_a(
        manifest_path=case["manifest"],
        mode_prep_summary_path=case["summary"],
        mode_prep_worker_summary_path=case["mode_worker"],
        direct_summary_path=None,
        direct_worker_summary_path=case["direct_worker"],
        iterative_summary_path=None,
        iterative_worker_summary_path=case["iterative_worker"],
        direct_telemetry_path=case["telemetry"],
        iterative_telemetry_path=None,
        output_path=case["output"],
        audit_source_sha="test-source",
        git_clean=True,
    )


def test_q_a_validates_owner_rows_storage_and_provenance(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    result = _audit(case)
    packet = result["packet"]
    assert packet["rank_count"] == 8
    assert packet["global_size"] == 17
    assert packet["array_names"] == [
        "positive_right",
        "positive_left",
        "negative_right",
        "negative_left",
    ]
    assert packet["validated_file_count"] == 32
    assert packet["owner_only_already_implemented"] is True
    assert packet["npy_total_bytes"] == sum(
        row["four_array_bytes"] for row in packet["ownership"]
    )
    assert packet["ownership"][0]["four_array_bytes"] > 0
    assert result["resources"]["mode_prep_process_tree"]["rss"]["status"] == "measured"
    assert (
        result["resources"]["mode_prep_process_tree"]["pss"]["status"] == "not_measured"
    )
    assert result["mode_prep"]["selection"]["positive"] == {
        "candidate_modes": 4,
        "selected_modes": 3,
    }
    assert result["inputs"]["mode_prep_worker_summary"]["status"] == "present"
    assert result["provenance"]["git_clean"] is True
    assert result["derived_buffer_accounting"]["provenance"] == "derived"
    assert result["derived_buffer_accounting"]["not_rss"] is True
    assert (
        result["derived_buffer_accounting"]["direct"]["entries"][0]["provenance"]
        == "derived"
    )
    assert (
        result["derived_buffer_accounting"]["direct"]["entries"][0]["values"][
            "replicated_numpy_array_bytes_process_tree"
        ]
        == 384
    )
    assert result["lifetime"]["direct_packet_release"]["status"] == "measured"
    assert (
        result["lifetime"]["iterative_full_basis_lifetime"]["status"] == "not_measured"
    )
    assert case["output"].exists()


@pytest.mark.parametrize("field", ["shape", "dtype", "bytes"])
def test_q_a_rejects_manifest_file_mismatch(tmp_path: Path, field: str) -> None:
    case = _write_case(tmp_path)
    manifest = json.loads(case["manifest"].read_text())
    descriptor = manifest["shards"][0]["files"]["positive_right"]
    if field == "shape":
        descriptor["shape"] = [2, 2]
    elif field == "dtype":
        descriptor["dtype"] = "complex64"
    else:
        descriptor["bytes"] += 1
    case["manifest"].write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        _audit(case)


def test_q_a_rejects_null_pss_without_exact_status(tmp_path: Path) -> None:
    case = _write_case(tmp_path, summary_status="measured")
    with pytest.raises(ValueError, match="null resource field"):
        _audit(case)


def test_q_b_sign_involution_and_left_right_convention() -> None:
    sign = np.array([1.0, 1.0, -1.0, -1.0])
    k0 = np.diag([2.0, 3.0, 5.0, 7.0]).astype(np.complex128)
    k1 = np.array(
        [
            [0.0, 0.0, 1.0 + 2.0j, -0.5j],
            [0.0, 0.0, 0.25 - 1.0j, 2.0],
            [1.0 - 2.0j, 0.25 + 1.0j, 0.0, 0.0],
            [0.5j, 2.0, 0.0, 0.0],
        ],
        dtype=np.complex128,
    )
    k2 = np.diag([11.0, 13.0, 0.0, 0.0]).astype(np.complex128)
    audit = audit_qep_sign_involution(k0, k1, k2, sign)
    assert audit["pass"] is True
    assert audit["right_map"] == "S"
    assert audit["left_map"] == "S"
    assert audit["additional_conjugation"] is False


def test_q_b_pair_targets_preserve_complete_negative_groups() -> None:
    pairs = [
        {"positive_index": index, "negative_index": index, "relative_beta_error": 0.0}
        for index in range(4)
    ]
    blocks = [(0, 1), (2, 3)]
    assert _pair_targets(pairs, 4, [7, 7, 8, 8], blocks) == ((0, 1, 2, 3), 0.0)
    with pytest.raises(ValueError, match="complete negative group"):
        _pair_targets(pairs, 4, [7, 7, 7, 8], blocks)


def test_q_b_json_default_normalizes_numpy_scalars() -> None:
    assert _json_default(np.bool_(True)) is True
    assert _json_default(np.int64(4)) == 4


def test_q_c_beta_matching_is_one_to_one() -> None:
    matched = match_beta_sets([1.0 + 0j, 2.0 + 0j], [2.0 + 0j, 1.0 + 0j])
    assert matched["identity_pass"] is True
    missing = match_beta_sets([1.0 + 0j, 2.0 + 0j], [1.0 + 0j, 3.0 + 0j])
    assert missing["identity_pass"] is False
    assert missing["missing_count"] == 1
    assert missing["extra_count"] == 1
    duplicate = match_beta_sets([1.0 + 0j, 2.0 + 0j], [1.0 + 0j, 1.0 + 0j])
    assert duplicate["observed_duplicate_count"] == 2
