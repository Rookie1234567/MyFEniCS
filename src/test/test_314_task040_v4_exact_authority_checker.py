"""Synthetic raw-evidence tests for the Task040 V4-1 checker."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest

import benchmarks.check_task040_v4_exact_authority as checker
from benchmarks.check_task040_v4_exact_authority import (
    EXPECTED_CLASSIFICATION,
    EXPECTED_FAILURE_CODE,
    EXPECTED_FAILURE_REASON,
    IMPLEMENTATION_FAILURE,
    _canonical_json_sha256,
    _load_probe_manifest,
    _resolved_config_path,
    check_v4_exact_authority,
    main,
)
from benchmarks.task040_level_a import (
    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
    TASK040_V1_2_INPUT_SHA256,
    TASK040_V1_2_PHYSICAL_MODEL_SHA256,
    TASK040_V1_2_PROBE_MANIFEST,
    TASK040_V1_2_PROBE_MANIFEST_SHA256,
    TASK040_V1_2_SELECTED_MANIFEST_SHA256,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA,
    TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA,
    TASK040_V4_FROZEN_BRANCH,
)
from src.solvers.hybrid_exact_authority_compat import V4_EXACT_AUTHORITY_LABELS


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_SOURCE_SHA = "9f3d6e39cb607125a773b35d9a2a9f7459c7f2dc"
CHECKER_SOURCE_SHA = "c" * 40
PROBE_MANIFEST_PATH = REPO_ROOT / TASK040_V1_2_PROBE_MANIFEST
PROBE_MANIFEST = json.loads(PROBE_MANIFEST_PATH.read_text(encoding="utf-8"))
MANIFEST_IDENTITY = PROBE_MANIFEST["identity"]
PHYSICAL_PROBES = PROBE_MANIFEST["physical_probes"]
PROBE_IDENTITIES = PHYSICAL_PROBES["probe_identities"]
EXACT_OUTPUT_IDENTITIES = PHYSICAL_PROBES["exact_output_identity_sha256"]
PRODUCER_SOURCE_SHA = MANIFEST_IDENTITY["exact_spool_source_sha"]
SELECTED_MANIFEST_SHA = TASK040_V1_2_SELECTED_MANIFEST_SHA256
GLOBAL_SIZE = int(PHYSICAL_PROBES["global_size"])
OWNERSHIP_RANGES = [
    [0, 15582],
    [15582, 32868],
    [32868, 49596],
    [49596, 64416],
    [64416, 80712],
    [80712, 96834],
    [96834, 115074],
    [115074, 132300],
]
PACKET_IDENTITY = {
    "comparison_group": "synthetic_task040_checker",
    "mpi_size": 8,
    "source_sha": PRODUCER_SOURCE_SHA,
}
INPUT_SOURCE = (
    REPO_ROOT / "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
)
CONFIG_BYTES = b'{"synthetic_config":"task040-v4-checker"}\n'
SYNTHETIC_CONFIG_SHA256 = hashlib.sha256(CONFIG_BYTES).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _metadata_hash(record: dict[str, Any]) -> str:
    payload = dict(record)
    payload.pop("metadata_payload_sha256_excluding_self", None)
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _synthetic_probe_manifest(resolved_sha: str) -> dict[str, Any]:
    manifest = deepcopy(PROBE_MANIFEST)
    manifest["identity"]["exact_spool_resolved_config_sha256"] = resolved_sha
    manifest["identity"]["selected_identity_sha256"] = _canonical_json_sha256(
        PACKET_IDENTITY
    )
    return manifest


@pytest.fixture(autouse=True)
def _synthetic_probe_manifest_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _synthetic_probe_manifest(SYNTHETIC_CONFIG_SHA256)

    def loader() -> tuple[Path, dict[str, Any], str]:
        return (
            PROBE_MANIFEST_PATH,
            deepcopy(manifest),
            TASK040_V1_2_PROBE_MANIFEST_SHA256,
        )

    monkeypatch.setattr(checker, "_load_probe_manifest", loader)


def _producer_identity_summary() -> dict[str, Any]:
    entries = {
        f"{label}:{role}": {
            "check": True,
            "expected_match_count": 8,
            "expected_mpi_size": 8,
            "observed_source_shas": [PRODUCER_SOURCE_SHA],
            "shard_count": 8,
            "valid_source_sha_count": 8,
        }
        for label in V4_EXACT_AUTHORITY_LABELS
        for role in ("rhs", "exact_output")
    }
    return {
        "expected_mpi_size": 8,
        "expected_source_sha": PRODUCER_SOURCE_SHA,
        "observed_source_sha": PRODUCER_SOURCE_SHA,
        "observed_source_shas": [PRODUCER_SOURCE_SHA],
        "per_label_role": entries,
        "pass": True,
    }


def _identity_checks() -> dict[str, dict[str, Any]]:
    return {
        name: {"pass": value}
        for name, value in {
            "input_sha256": True,
            "physical_model_sha256": True,
            "frozen_branch": True,
            "freeze_source": True,
            "selected_manifest": True,
            "resolved_config": True,
            "packet_manifest": True,
            "spool_catalog": True,
            "spool_producer_source": True,
            "exact_output_metadata": True,
            "canonical_source_binding": False,
        }.items()
    }


def _source_ownership() -> dict[str, dict[str, list[list[int]]]]:
    return {
        label: {
            role: [list(pair) for pair in OWNERSHIP_RANGES]
            for role in ("rhs", "exact_output")
        }
        for label in V4_EXACT_AUTHORITY_LABELS
    }


def _source_canonical_authority() -> dict[str, Any]:
    missing_entries = [
        f"{label}:{role}"
        for label in V4_EXACT_AUTHORITY_LABELS
        for role in ("rhs", "exact_output")
    ]
    return {
        "array_hash_validation_only": True,
        "bridge_qualified": False,
        "canonical_map_content_hash_verified": False,
        "canonical_map_opened": False,
        "canonical_reconstruction_verified": False,
        "descriptor_available": False,
        "descriptor_complete": False,
        "entries": {
            label: {
                role: {
                    "descriptor_available": False,
                    "ownership_ranges": [list(pair) for pair in OWNERSHIP_RANGES],
                    "reason": EXPECTED_FAILURE_CODE,
                }
                for role in ("rhs", "exact_output")
            }
            for label in V4_EXACT_AUTHORITY_LABELS
        },
        "failure_code": EXPECTED_FAILURE_CODE,
        "inconsistent_fields": [],
        "labels": list(V4_EXACT_AUTHORITY_LABELS),
        "malformed_entries": [],
        "missing_entries": missing_entries,
        "numeric_vectors_constructed": False,
        "pass": False,
        "raw_global_row_remap_forbidden": True,
        "raw_npy_mmap_hash_read": True,
        "reason": EXPECTED_FAILURE_REASON,
        "required_roles": ["rhs", "exact_output"],
        "source_current_key_equality_verified": False,
        "values_retained": False,
    }


def _exact_output_metadata_identity() -> dict[str, Any]:
    return {
        "array_hash_validation_only": True,
        "checks": {label: True for label in V4_EXACT_AUTHORITY_LABELS},
        "expected": dict(EXACT_OUTPUT_IDENTITIES),
        "expected_mpi_size": 8,
        "numeric_vectors_constructed": False,
        "observed": dict(EXACT_OUTPUT_IDENTITIES),
        "pass": True,
        "shard_counts": {label: 8 for label in V4_EXACT_AUTHORITY_LABELS},
        "values_retained": False,
    }


def _zero_inventory() -> dict[str, int]:
    return {
        "exact_output_vectors_loaded": 0,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "cross_section_group_factor_count": 0,
        "reduced_dense_factor_count": 0,
        "factor_objects_created": 0,
    }


def _downstream() -> dict[str, str]:
    return {
        name: "not_run_by_gate"
        for name in (
            "projection",
            "lift",
            "trace",
            "dual",
            "response",
            "fgmres",
            "coarse",
            "level_b",
            "full_hybrid",
            "h3",
        )
    }


def _make_formal_summary(resolved_sha: str) -> dict[str, Any]:
    downstream = _downstream()
    identity = {
        "source_sha": FORMAL_SOURCE_SHA,
        "current_source_sha": FORMAL_SOURCE_SHA,
        "spool_producer_source_sha": PRODUCER_SOURCE_SHA,
        "input_sha256": TASK040_V1_2_INPUT_SHA256,
        "physical_model_sha256": TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        "frozen_branch": TASK040_V4_FROZEN_BRANCH,
        "task040_manifest_freeze_source_sha": TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA,
        "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "selected_identity_sha256": _canonical_json_sha256(PACKET_IDENTITY),
        "spool_packet_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "resolved_config_sha256": resolved_sha,
        "spool_catalog_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        "identity_checks": _identity_checks(),
        "identity_failures": ["canonical_source_binding"],
        "identity_checks_pass": False,
        "exact_output_metadata_identity": _exact_output_metadata_identity(),
        "source_canonical_authority": _source_canonical_authority(),
        "source_ownership": _source_ownership(),
        "packet_identity": dict(PACKET_IDENTITY),
        "probe_authority": dict(PROBE_IDENTITIES),
        "labels": list(V4_EXACT_AUTHORITY_LABELS),
        "spool_producer_source_identity": _producer_identity_summary(),
        "system_inventory": {
            "explicit_bare_f_created": False,
            "system_created": False,
        },
    }
    factor_inventory = _zero_inventory()
    exact_authority = {
        "classification": EXPECTED_CLASSIFICATION,
        "failure_code": EXPECTED_FAILURE_CODE,
        "failure_reason": EXPECTED_FAILURE_REASON,
        "identity_pass": False,
        "gate_pass": False,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "exact_output_vectors_loaded": 0,
        "labels": list(V4_EXACT_AUTHORITY_LABELS),
        "reports": [],
        "residual_status": "not_run_by_identity_gate",
        "bare_f_residual": "not_run_by_identity_gate",
        "a_side_explanatory_residual": "not_run_by_identity_gate",
        "numerical_gate_pass": None,
        "finite_pass": None,
        "repeat_pass": None,
        "bare_f_residual_pass": None,
        "bare_f_hash_unchanged_pass": None,
        "factor_inventory": dict(factor_inventory),
        "cleanup": {
            "factor_objects_created": 0,
            "interface_masses_built": False,
            "packet_built": False,
        },
        "downstream": downstream,
    }
    return {
        "schema": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA,
        "method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
        "profile": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID,
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": TASK040_V1_2_INPUT_SHA256,
        "physical_model_sha256": TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        "identity_observed": identity,
        "identity_pass": False,
        "identity_failure_code": EXPECTED_FAILURE_CODE,
        "identity_failure_reason": EXPECTED_FAILURE_REASON,
        "classification": EXPECTED_CLASSIFICATION,
        "gate_pass": False,
        "numerical_gate_pass": None,
        "residual_status": "not_run_by_identity_gate",
        "qep_calls": 0,
        "pde_solve": "not_run",
        "factor_inventory": factor_inventory,
        "exact_authority": exact_authority,
        "source_loading": {
            "array_hash_validation_only": True,
            "canonical_reconstruction": "not_run_by_identity_gate",
            "exact_output_metadata_hash_validation_only": True,
            "exact_output_vectors_loaded": 0,
            "labels": list(V4_EXACT_AUTHORITY_LABELS),
            "numeric_vectors_constructed": False,
            "raw_global_row_remap_used": False,
            "rhs_vectors_loaded": 0,
            "values_retained": False,
        },
        "construction": {
            "system_created": False,
            "explicit_bare_f_created": False,
            "interface_masses_built": False,
            "pde_solved": False,
            "qep_called": False,
        },
        "not_run_by_gate": downstream,
        "projection": "not_run_by_gate",
        "lift": "not_run_by_gate",
        "resource_authority": {
            "status": "not_run_by_identity_gate",
            "sample_count": 0,
            "all_status_readable": None,
            "swap_authority_readable": None,
            "swap_zero_authoritative": None,
        },
        "resource_samples": {},
    }


def _make_spool(spool_parent: Path) -> tuple[Path, str]:
    spool_root = spool_parent / "v5_blr_reference_spool"
    for rank in range(8):
        rank_root = spool_root / f"rank{rank:04d}"
        for label in V4_EXACT_AUTHORITY_LABELS + ("physical_side_rhs",):
            for role in ("rhs", "exact_output"):
                if label in EXACT_OUTPUT_IDENTITIES and role == "rhs":
                    global_id = PROBE_IDENTITIES[label]["rhs_identity_sha256"]
                elif label in EXACT_OUTPUT_IDENTITIES and role == "exact_output":
                    global_id = EXACT_OUTPUT_IDENTITIES[label]
                else:
                    global_id = "e" * 64
                array_sha = f"{rank + 1:064x}"
                ownership = list(OWNERSHIP_RANGES[rank])
                vector_identity = {
                    "dtype": "complex128",
                    "global_sha256": global_id,
                    "global_size": GLOBAL_SIZE,
                    "local_sha256": array_sha,
                    "ownership_range": ownership,
                }
                if role == "rhs" and label in PROBE_IDENTITIES:
                    probe_identity = PROBE_IDENTITIES[label]
                    probe_metadata = {
                        "identity": dict(vector_identity),
                        "label": label,
                        "seed": probe_identity["seed"],
                        "source": probe_identity["source"],
                    }
                    if "resolved_column" in probe_identity:
                        probe_metadata["resolved_column"] = probe_identity[
                            "resolved_column"
                        ]
                else:
                    probe_metadata = {"label": label}
                metadata_path = (rank_root / f"bottom_{label}_{role}.json").resolve()
                record = {
                    "array_path": str(metadata_path.with_suffix(".npy")),
                    "array_sha256": array_sha,
                    "dtype": "complex128",
                    "global_size": GLOBAL_SIZE,
                    "label": label,
                    "local_size": ownership[1] - ownership[0],
                    "metadata_path": str(metadata_path),
                    "ownership_range": ownership,
                    "role": role,
                    "side": "bottom",
                    "source_identity": {
                        "artifact_role": role,
                        "packet_identity": {
                            "manifest_sha256": SELECTED_MANIFEST_SHA,
                            "packet_identity": dict(PACKET_IDENTITY),
                            "source_sha": PRODUCER_SOURCE_SHA,
                        },
                        "probe_metadata": probe_metadata,
                        "vector_identity": vector_identity,
                    },
                }
                record["metadata_payload_sha256_excluding_self"] = _metadata_hash(
                    record
                )
                _write_json(metadata_path, record)
    resolved = spool_parent / "resolved_config.json"
    resolved.write_bytes(CONFIG_BYTES)
    return spool_root, _sha256(resolved)


def _make_fixture(tmp_path: Path) -> dict[str, Path | str]:
    formal_root = tmp_path / "formal"
    spool_parent = tmp_path / "spool"
    spool_root, resolved_sha = _make_spool(spool_parent)
    input_path = tmp_path / "official_input.dat"
    input_path.write_bytes(INPUT_SOURCE.read_bytes())
    run_summary = _make_formal_summary(resolved_sha)
    _write_json(formal_root / "worker" / "run_summary.json", run_summary)
    marker_rows = [
        {
            "stage": "construction_begin",
            "detail": {"method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD},
        },
        {
            "stage": "v4_identity_stop",
            "detail": {
                "array_hash_validation_only": True,
                "failure_code": EXPECTED_FAILURE_CODE,
                "numeric_vectors_constructed": False,
                "residual_status": "not_run_by_identity_gate",
                "system_created": False,
                "values_retained": False,
            },
        },
    ]
    _write_jsonl(formal_root / "memory_stage_markers.raw.jsonl", marker_rows)
    _write_jsonl(
        formal_root / "memory_stages.jsonl",
        [
            {
                "stage": "construction_begin",
                "method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
                "status": "running",
            },
            {
                "stage": "v4_identity_stop",
                "array_hash_validation_only": True,
                "failure_code": EXPECTED_FAILURE_CODE,
                "numeric_vectors_constructed": False,
                "residual_status": "not_run_by_identity_gate",
                "status": "complete",
                "system_created": False,
                "values_retained": False,
            },
        ],
    )
    process_rows = []
    for index in range(20):
        rss = 1_764_352_000 if index == 19 else 1_000_000
        process_rows.append(
            {
                "authoritative_sample": True,
                "rss_bytes": rss,
                "swap_bytes": 0,
                "terminal_teardown_excluded": False,
                "resource_authority": {
                    "memory_authority_bytes": rss,
                    "job_cgroup": {"readable": True, "swap_current_bytes": 0},
                    "process_tree": {
                        "all_status_readable": True,
                        "swap_bytes": 0,
                    },
                },
            }
        )
    _write_jsonl(formal_root / "process_tree_samples.jsonl", process_rows)
    stdout_path = formal_root / "worker_stdout.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("", encoding="utf-8")
    command = [
        "mpiexec",
        "-n",
        "8",
        "python",
        "-m",
        "benchmarks.task040_level_a",
        "--input",
        str(input_path.resolve()),
        "--source-sha",
        FORMAL_SOURCE_SHA,
        "--exact-spool-root",
        str(spool_parent.resolve()),
        "--run-directory",
        str((formal_root / "worker").resolve()),
        "--memory-stages",
        str((formal_root / "memory_stages.jsonl").resolve()),
        "--memory-markers",
        str((formal_root / "memory_stage_markers.raw.jsonl").resolve()),
        "--v4-exact-authority-compatibility",
    ]
    artifact_names = (
        "memory_stage_markers.raw.jsonl",
        "memory_stages.jsonl",
        "process_tree_samples.jsonl",
        "worker_stdout.txt",
    )
    run_path = formal_root / "worker" / "run_summary.json"
    artifact_hashes = {name: _sha256(formal_root / name) for name in artifact_names}
    watchdog = {
        "schema": "task040.level_a.watchdog.v1",
        "method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
        "source_sha": FORMAL_SOURCE_SHA,
        "command": command,
        "return_code": 0,
        "termination_reason": "natural_exit",
        "run_summary_present": True,
        "run_summary_sha256": _sha256(run_path),
        "artifact_hashes": artifact_hashes,
        "sample_count": 20,
        "authoritative_sample_count": 20,
        "all_status_readable": True,
        "swap_authority_readable": True,
        "peak_rss_bytes": 1_764_352_000,
        "peak_swap_bytes": 0,
        "dedicated_cgroup_present": False,
        "dedicated_cgroup_swap_readable": None,
        "peak_dedicated_cgroup_swap_bytes": 0,
        "terminal_teardown_excluded_count": 0,
        "process_control": {
            "process_group_exited": True,
            "requested": True,
            "sigkill_required": False,
            "worker_exited": True,
        },
    }
    _write_json(formal_root / "watchdog_summary.json", watchdog)
    return {
        "formal_root": formal_root,
        "input_path": input_path,
        "spool_parent": spool_parent,
        "spool_root": spool_root,
        "output": tmp_path / "checker.json",
    }


def _check(fixture: dict[str, Path | str]) -> dict[str, Any]:
    return check_v4_exact_authority(
        fixture["formal_root"],
        FORMAL_SOURCE_SHA,
        CHECKER_SOURCE_SHA,
        exact_spool_root=fixture["spool_parent"],
    )


def _rewrite_run(
    fixture: dict[str, Path | str], mutation: Callable[[dict], None]
) -> None:
    path = Path(fixture["formal_root"]) / "worker" / "run_summary.json"
    run = json.loads(path.read_text(encoding="utf-8"))
    mutation(run)
    _write_json(path, run)


def test_v4_checker_accepts_evidence_valid_controlled_negative(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    result = _check(fixture)
    assert result["evidence_valid"] is True
    assert result["checker_pass"] is True
    assert result["gate_pass"] is False
    assert result["classification"] == EXPECTED_CLASSIFICATION
    assert len(result["read_files"]) == 105
    assert all(not path["path"].endswith(".npy") for path in result["read_files"])
    assert not list(Path(fixture["spool_parent"]).rglob("*.npy"))


def test_real_tracked_probe_manifest_authority_is_frozen() -> None:
    path, manifest, digest = _load_probe_manifest()
    assert path == PROBE_MANIFEST_PATH
    assert digest == TASK040_V1_2_PROBE_MANIFEST_SHA256
    assert manifest["physical_probes"]["labels"] == list(V4_EXACT_AUTHORITY_LABELS)
    assert manifest["identity"]["selected_identity_sha256"] == (
        "cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9"
    )


def test_non_frozen_probe_manifest_digest_is_implementation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _make_fixture(tmp_path)
    manifest = _synthetic_probe_manifest(SYNTHETIC_CONFIG_SHA256)
    monkeypatch.setattr(
        checker,
        "_load_probe_manifest",
        lambda: (PROBE_MANIFEST_PATH, manifest, "0" * 64),
    )
    result = _check(fixture)
    assert result["checks"]["probe_manifest_identity"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert result["checker_pass"] is False


def test_synthetic_authority_does_not_need_ignored_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _make_fixture(tmp_path)
    monkeypatch.setattr(checker, "_repo_root", lambda: tmp_path / "clean_checkout")
    result = _check(fixture)
    assert result["checker_pass"] is True
    assert result["classification"] == EXPECTED_CLASSIFICATION


def test_v4_checker_cli_returns_zero_for_controlled_negative(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    rc = main(
        [
            "--formal-root",
            str(fixture["formal_root"]),
            "--exact-spool-root",
            str(fixture["spool_parent"]),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(fixture["output"]),
        ]
    )
    assert rc == 0
    output = json.loads(Path(fixture["output"]).read_text())
    assert output["checker_pass"] is True
    assert output["gate_pass"] is False


def test_v4_checker_resolves_artifact_level_config_for_nested_spool(
    tmp_path: Path,
) -> None:
    exact_spool_root = tmp_path / "numerical_output"
    spool_root = exact_spool_root / "v5_blr_reference_spool"
    resolved_config = tmp_path / "resolved_config.json"
    resolved_config.write_text("{}\n", encoding="utf-8")
    spool_root.mkdir(parents=True)
    assert _resolved_config_path(exact_spool_root, spool_root) == resolved_config


def test_v4_checker_rejects_missing_shard_and_producer_mismatch(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path / "missing")
    missing = (
        Path(fixture["spool_root"])
        / "rank0007"
        / "bottom_modal_traction_positive_rhs.json"
    )
    missing.unlink()
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert "spool_expected_pairs" in result["failures"]

    fixture = _make_fixture(tmp_path / "producer")
    producer_path = (
        Path(fixture["spool_root"])
        / "rank0000"
        / "bottom_modal_traction_positive_rhs.json"
    )
    producer = json.loads(producer_path.read_text())
    producer["source_identity"]["packet_identity"]["source_sha"] = "a" * 40
    _write_json(producer_path, producer)
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert "producer_source_identity" in result["failures"]


@pytest.mark.parametrize(
    "mutation,expected_failure",
    [
        (
            lambda run: run["exact_authority"]["reports"].append({"residual": 1.0}),
            "identity_stop_contract",
        ),
        (
            lambda run: run["construction"].update({"system_created": True}),
            "construction_contract",
        ),
        (
            lambda run: run["source_loading"].update(
                {"raw_global_row_remap_used": True}
            ),
            "source_loading_contract",
        ),
    ],
)
def test_v4_checker_rejects_numerical_or_raw_row_mutation(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    expected_failure: str,
) -> None:
    fixture = _make_fixture(tmp_path)
    _rewrite_run(fixture, mutation)
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert expected_failure in result["failures"]


@pytest.mark.parametrize("mutation", ["timeline", "marker", "artifact", "resource"])
def test_v4_checker_rejects_watchdog_evidence_mutation(
    tmp_path: Path, mutation: str
) -> None:
    fixture = _make_fixture(tmp_path)
    root = Path(fixture["formal_root"])
    if mutation == "timeline":
        path = root / "process_tree_samples.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["swap_bytes"] = 1
        _write_jsonl(path, rows)
    elif mutation == "marker":
        path = root / "memory_stage_markers.raw.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[1]["detail"]["values_retained"] = True
        _write_jsonl(path, rows)
    else:
        path = root / "watchdog_summary.json"
        watchdog = json.loads(path.read_text())
        if mutation == "artifact":
            watchdog["artifact_hashes"]["process_tree_samples.jsonl"] = "0" * 64
        else:
            watchdog["peak_rss_bytes"] = 1
        _write_json(path, watchdog)
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert any(
        name in result["failures"]
        for name in (
            "watchdog_samples",
            "marker_contract",
            "watchdog_artifact_hashes",
            "watchdog_resource",
        )
    )


@pytest.mark.parametrize("field", ["label", "ownership_range"])
def test_v4_checker_rejects_metadata_self_hash_or_descriptor_mutation(
    tmp_path: Path, field: str
) -> None:
    fixture = _make_fixture(tmp_path)
    path = (
        Path(fixture["spool_root"])
        / "rank0000"
        / "bottom_modal_traction_positive_rhs.json"
    )
    record = json.loads(path.read_text())
    record[field] = "wrong_label" if field == "label" else [1, OWNERSHIP_RANGES[0][1]]
    _write_json(path, record)
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert any(
        name in result["failures"]
        for name in (
            "metadata_self_hash",
            "array_descriptor_contract",
            "ownership_contract",
        )
    )


def test_v4_checker_rejects_input_hash_mutation_and_does_not_claim_stop(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    _rewrite_run(fixture, lambda run: run.update({"input_sha256": "0" * 64}))
    result = _check(fixture)
    assert result["evidence_valid"] is False
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE


def test_v4_checker_ignores_old_checker_artifact(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    formal_root = Path(fixture["formal_root"])
    old_checker = formal_root / "checker_old.json"
    new_checker = formal_root / "checker_new.json"
    _write_json(old_checker, {"classification": "old", "fake": True})
    rc = main(
        [
            "--formal-root",
            str(formal_root),
            "--exact-spool-root",
            str(fixture["spool_parent"]),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(new_checker),
        ]
    )
    assert rc == 0
    output = json.loads(new_checker.read_text())
    read_paths = {item["path"] for item in output["read_files"]}
    assert str(old_checker.resolve()) not in read_paths
    assert str(new_checker.resolve()) not in read_paths
    assert output["classification"] == EXPECTED_CLASSIFICATION


def test_nested_packet_identity_hash_mismatch_fails_after_self_hash_rewrite(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    path = (
        Path(fixture["spool_root"])
        / "rank0000"
        / "bottom_modal_traction_positive_rhs.json"
    )
    record = json.loads(path.read_text())
    record["source_identity"]["packet_identity"]["packet_identity"][
        "comparison_group"
    ] = "tampered"
    record["metadata_payload_sha256_excluding_self"] = _metadata_hash(record)
    _write_json(path, record)
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert "packet_wrapper_identity" in result["failures"]


def test_internal_resource_authority_mutation_fails(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    _rewrite_run(
        fixture,
        lambda run: run["resource_authority"].update({"status": "running"}),
    )
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert "run_summary_resource_authority_contract" in result["failures"]


def test_mpi_command_identity_mutation_fails(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    watchdog_path = Path(fixture["formal_root"]) / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text())
    watchdog["command"][watchdog["command"].index("8")] = "4"
    _write_json(watchdog_path, watchdog)
    result = _check(fixture)
    assert result["checker_pass"] is False
    assert result["classification"] == IMPLEMENTATION_FAILURE
    assert "formal_command_identity" in result["failures"]


def test_v4_checker_cli_exception_is_implementation_failure(tmp_path: Path) -> None:
    output = tmp_path / "exception.json"
    missing_formal = tmp_path / "missing_formal"
    rc = main(
        [
            "--formal-root",
            str(missing_formal),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert rc != 0
    report = json.loads(output.read_text())
    assert report["classification"] == IMPLEMENTATION_FAILURE
    assert report["evidence_valid"] is False
