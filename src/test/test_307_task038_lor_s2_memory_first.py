"""Focused contracts for the V11 S2 memory-first foundation harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import run_task038_full3d_lor_hx_foundation as foundation_watchdog
from benchmarks import run_task038_full3d_lor_s2_memory_first as runner
from benchmarks import task038_full3d_lor_s2_memory_first_checker as checker
from src.solvers.fullspace_lor_memory_first_foundation import (
    S2_APPLY_NAMES,
    S2_RESERVE_VECTOR_COUNT,
    allocate_restart20_reserve,
    destroy_restart20_reserve,
    run_fixed_apply_ledger,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA = "a" * 40
MARKER_NAMES = (
    "paths_ready",
    "source_runtime_closed",
    "fixture_built",
    "reserve_built",
    "apply_ledger_written",
    "retained_ready",
    "record_written",
)


def _write_json(path: Path, value: object) -> str:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "campaign"
    raw = root / "worker_raw"
    raw.mkdir(parents=True)
    record_path = tmp_path / "docs" / "record.json"
    record_path.parent.mkdir()
    watchdog_raw = root / "watchdog.raw.jsonl"
    watchdog_compact = root / "watchdog.json"
    repo_root = Path(__file__).resolve().parents[2]
    input_path = repo_root / checker.TEMPLATE_RELATIVE_PATH
    command = [
        str(Path(sys.executable).absolute()),
        "-m",
        "benchmarks.run_task038_full3d_lor_s2_memory_first",
        "--stage",
        "s2",
        "--case",
        "p6-h10-mpi1",
        "--raw-dir",
        str(raw.resolve()),
        "--record",
        str(record_path.resolve()),
        "--expected-source-sha",
        SOURCE_SHA,
        "--expected-mpi-size",
        "1",
        "--input",
        str(input_path.resolve()),
    ]
    base_wall_time_ns = time.time_ns()
    samples = []
    for repeat in range(10):
        samples.append(
            {
                "wall_time_ns": base_wall_time_ns + 10 + repeat,
                "authority": {
                    "process_tree": {
                        "rss_bytes": 100,
                        "swap_bytes": 0,
                        "all_status_readable": True,
                    }
                },
            }
        )
    watchdog_raw.write_text("".join(json.dumps(row) + "\n" for row in samples), encoding="utf-8")
    watchdog = {
        "schema": "task038.lor-native-complex-hx.foundation-e-watchdog.v1",
        "source_sha": SOURCE_SHA,
        "worker_command": command,
        "worker_raw_dir": str(raw.resolve()),
        "worker_record": str(record_path.resolve()),
        "watchdog_raw": str(watchdog_raw.resolve()),
        "returncode": 0,
        "natural_exit": True,
        "no_orphan": True,
        "stop_reason": "natural_exit",
        "sample_count": len(samples),
        "all_status_readable": True,
        "peak_process_tree_rss_bytes": 100,
        "max_process_tree_swap_bytes": 0,
        "watchdog_rss_limit_bytes": 1_800_000_000,
        "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
    }
    _write_json(watchdog_compact, watchdog)
    rows = []
    for repeat in range(10):
        row = {"repeat": repeat, "resource": samples[repeat]["authority"]}
        for name in S2_APPLY_NAMES:
            row[name] = {
                "finite": True,
                "norm": 1.0,
                "digest": "b" * 64,
            }
        rows.append(row)
    ledger_path = raw / "apply_ledger.json"
    ledger = {
        "operation_names": list(S2_APPLY_NAMES),
        "repeat_count": 10,
        "rows": rows,
        "retains_vectors": False,
    }
    ledger_sha = _write_json(ledger_path, ledger)
    retained_resource = samples[0]["authority"]
    record = {
        "schema": checker.SCHEMA,
        "stage": "s2",
        "case": "p6-h10-mpi1",
        "degree": 6,
        "h_nm": 10.0,
        "wavelength_nm": 13.5,
        "mpi_size": 1,
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "command": command,
        "source": {
            "start": {"expected_sha": SOURCE_SHA, "commit_sha": SOURCE_SHA, "branch": BRANCH, "clean": True},
            "end": {"expected_sha": SOURCE_SHA, "commit_sha": SOURCE_SHA, "branch": BRANCH, "clean": True},
        },
        "runtime": {
            "qualified_activation": "1",
            "sys_executable": command[0],
            "mpi_size": 1,
            "petsc_scalar_type": str(PETSc.ScalarType),
            "petsc_int_type": str(PETSc.IntType),
        },
        "settings": {
            "apply_names": list(S2_APPLY_NAMES),
            "repeat_count": 10,
            "restart_basis_count": 21,
            "auxiliary_vector_count": 4,
            "reserve_vector_count": S2_RESERVE_VECTOR_COUNT,
            "restart_semantics": "21 basis + solution/rhs/residual/action; no iteration history",
            "retained_rss_limit_bytes": checker.RETAINED_LIMIT,
            "cold_rss_limit_bytes": checker.COLD_LIMIT,
            "repeat_growth_limit_bytes": checker.GROWTH_LIMIT,
        },
        "architecture": {
            "scalar_node_matrix_built": False,
            "hx_hierarchy_built": False,
            "pcgamg_hierarchy_built": False,
            "p6_exact_edge_factor_built": False,
            "global_direct_coarse_built": False,
            "recovery_field_arrays_built": False,
            "global_high_order_aij": False,
            "global_dense_transfer": False,
            "global_numeric_allgather": False,
            "numeric_allgather": False,
            "hx_or_node_action_built": False,
            "production_local_spectral_built": False,
            "high_space": {
                "global_rows": 8,
                "local_storage_entries": 8,
            },
            "low_space": {
                "global_rows": 1,
                "local_storage_entries": 1,
            },
            "high_positive_action": {
                "global_rows": 8,
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "global_condensed_schur_materialized": False,
                "cell_schur_matrix_materialized": False,
                "slab_matrix_materialized": False,
                "dense_cell_tensor_materialized_per_apply": False,
                "retained_dense_cell_tensor_count": 0,
                "cell_schur_matrix_nnz": 0,
                "slab_matrix_nnz": 0,
                "ksp_created": False,
                "factor_count": 0,
                "numeric_allgather": False,
            },
            "physical_action": {
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
                "volume_action": {
                    "global_rows": 8,
                    "global_matrix_materialized": False,
                    "global_constraint_matrix_materialized": False,
                    "global_condensed_schur_materialized": False,
                    "cell_schur_matrix_materialized": False,
                    "slab_matrix_materialized": False,
                    "dense_cell_tensor_materialized_per_apply": False,
                    "retained_dense_cell_tensor_count": 0,
                    "cell_schur_matrix_nnz": 0,
                    "slab_matrix_nnz": 0,
                    "ksp_created": False,
                    "factor_count": 0,
                    "numeric_allgather": False,
                },
                "dtn_action": {
                    "global_aij_materialized": False,
                    "global_schur_materialized": False,
                    "trace_matrix_materialized": False,
                    "ksp_created": False,
                    "factor_count": 0,
                    "numeric_allgather": False,
                    "explicit_c_matrix_count": 0,
                    "explicit_d_matrix_count": 0,
                },
            },
            "setup_resources": [
                {
                    "stage": stage,
                    "process_tree": {
                        "rss_bytes": 100,
                        "swap_bytes": 0,
                        "all_status_readable": True,
                    },
                    **({"rss_delta_bytes": 0} if index else {}),
                }
                for index, stage in enumerate(checker.SETUP_RESOURCE_STAGES)
            ],
            "low_raw_map": {
                "owned_raw_rows": 1,
                "active_raw_rows": 1,
                "phase_rows": 0,
            },
            "low_matrix": {
                "rows": 1,
                "cols": 1,
                "nnz": 1,
                "index_bytes": 8,
                "numeric_bytes": 16,
                "petsc_reported_memory_bytes": 32,
            },
            "transfer": {
                "global_transfer_matrix": False,
                "batch_scratch_bytes": 1_053_696,
                "retained_numeric_bytes": 16,
                "reference_factor_index_metadata_bytes": 8,
                "reference_factor_approx_retained_bytes": 24,
            },
        },
        "input_identity": {
            "path_absolute": str(input_path.resolve()),
            "path_relative": checker.TEMPLATE_RELATIVE_PATH,
            "raw_bytes": checker.EXPECTED_INPUT_BYTES,
            "raw_sha256": checker.EXPECTED_INPUT_SHA256,
            "physical_model_sha256": checker.EXPECTED_PHYSICAL_MODEL_SHA256,
            "resolved_bytes": checker.EXPECTED_RESOLVED_BYTES,
            "resolved_sha256": checker.EXPECTED_RESOLVED_SHA256,
        },
        "reserve": {
            "basis_count": 21,
            "auxiliary_vector_count": 4,
            "vector_count": 25,
            "touched": True,
            "local_entries_per_vector": 1,
            "local_numeric_bytes": 400,
        },
        "apply_ledger": {"relative_path": ledger_path.name, "sha256": ledger_sha},
        "input_facts": {
            role: {"before_digest": "c" * 64, "after_digest": "c" * 64, "unchanged": True}
            for role in ("high_primal", "high_dual", "low_primal")
        },
        "retained_ready_wall_time_ns": base_wall_time_ns - 10 + MARKER_NAMES.index("retained_ready"),
        "retained_dwell_seconds": 2.0,
        "markers": {"relative_dir": "markers", "names": list(MARKER_NAMES)},
        "retained": {
            "known_bytes": {
                "mesh_space_mpc_known_array_bytes": None,
                "foundation_high_work_vectors_bytes": 48,
                "foundation_low_work_vectors_bytes": 48,
                "restart_reserve_numeric_bytes": 400,
                "high_topology_retained_array_bytes": 8,
                "low_topology_retained_array_bytes": 8,
                "lor_matrix_index_bytes": 8,
                "lor_matrix_numeric_bytes": 16,
                "transfer_reference_factor_approx_retained_bytes": 24,
            },
            "measured_process_tree_rss_bytes": 1000,
            "known_total_bytes": 560,
            "unattributed_remainder_bytes": 440,
            "mesh_space_mpc": {
                "known_array_bytes": None,
                "measured_separately": False,
                "included_in_unattributed": True,
            },
            "vector_facts": {
                "high_bytes_per_vector": 16,
                "high_vector_count": 3,
                "low_bytes_per_vector": 16,
                "low_vector_count": 3,
            },
            "bounded_temporary_bytes": {
                "included_in_known_total": False,
            },
            "resource": {
                "process_tree": {
                    "rss_bytes": 1000,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                }
            },
        },
    }
    marker_dir = raw / "markers"
    marker_dir.mkdir()
    for index, marker in enumerate(MARKER_NAMES):
        _write_json(
            marker_dir / f"{marker}.json",
            {
                "schema": "task038.full3d.lor-memory-first.s2-marker.v1",
                "marker": marker,
                "source_sha": SOURCE_SHA,
                "wall_time_ns": base_wall_time_ns - 10 + index,
            },
        )
    _write_json(record_path, record)
    return record_path, watchdog_compact


def _rewrite_ledger(record_path: Path, mutate) -> None:
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    raw_dir = Path(payload["raw_dir"])
    ledger_path = raw_dir / payload["apply_ledger"]["relative_path"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    mutate(ledger)
    ledger_sha = _write_json(ledger_path, ledger)
    payload["apply_ledger"]["sha256"] = ledger_sha
    record_path.write_text(json.dumps(payload), encoding="utf-8")


def _rewrite_watchdog(watchdog_path: Path, rss: int) -> None:
    compact = json.loads(watchdog_path.read_text(encoding="utf-8"))
    raw_path = Path(compact["watchdog_raw"])
    rows = []
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["authority"]["process_tree"]["rss_bytes"] = int(rss)
        rows.append(row)
    raw_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    compact["peak_process_tree_rss_bytes"] = int(rss)
    compact["raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    watchdog_path.write_text(json.dumps(compact), encoding="utf-8")


def test_high_positive_apply_keeps_borrowed_output_alive_across_repeats():
    class Vec:
        def __init__(self, value: int = 0):
            self.value = value
            self.destroyed = False

        def copy(self, target=None):
            if target is None:
                return Vec(self.value)
            target.value = self.value

        def destroy(self):
            self.destroyed = True
            raise AssertionError("borrowed action output was destroyed")

    class Action:
        def __init__(self):
            self.output = Vec()
            self.destroy_count = 0

        def apply(self, _source):
            self.output.value += 1
            return self.output

        def destroy(self):
            self.destroy_count += 1

    from src.solvers.fullspace_lor_memory_first_foundation import S2FoundationCase

    action = Action()
    case = S2FoundationCase({"high_positive": action})
    target = Vec()
    case.high_positive_into(object(), target)
    case.high_positive_into(object(), target)
    assert target.value == 2
    assert action.output.destroyed is False
    case.destroy()
    assert action.destroy_count == 1


def test_restart20_reserve_is_real_and_fixed():
    template = PETSc.Vec().create(comm=PETSc.COMM_SELF)
    template.setSizes(4)
    template.setFromOptions()
    template.set(0.0 + 0.0j)
    reserve = allocate_restart20_reserve(template)
    try:
        assert reserve["vector_count"] == S2_RESERVE_VECTOR_COUNT == 25
        assert reserve["basis_count"] == 21
        assert reserve["auxiliary_vector_count"] == 4
        assert reserve["touched"] is True
        assert len(reserve["vectors"]) == 25
        assert all(float(vector.norm()) > 0.0 for vector in reserve["vectors"])
    finally:
        destroy_restart20_reserve(reserve)
        template.destroy()


def test_fixed_apply_ledger_has_only_scalar_rows():
    calls = {name: 0 for name in S2_APPLY_NAMES}

    def operation(name: str):
        def apply():
            calls[name] += 1
            return {"finite": True, "norm": float(calls[name]), "digest": "a" * 64}

        return apply

    ledger = run_fixed_apply_ledger(tuple((name, operation(name)) for name in S2_APPLY_NAMES))
    assert ledger["operation_names"] == list(S2_APPLY_NAMES)
    assert ledger["repeat_count"] == 10
    assert len(ledger["rows"]) == 10
    assert ledger["retains_vectors"] is False
    assert calls == {name: 10 for name in S2_APPLY_NAMES}


def test_checker_rejects_nonfinite_json(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text('{"value": NaN}\n', encoding="utf-8")
    with np.testing.assert_raises(ValueError):
        checker._read(path)


def test_s2_source_does_not_build_forbidden_old_paths():
    core = Path("src/solvers/fullspace_lor_memory_first_foundation.py").read_text(encoding="utf-8")
    runner = Path("benchmarks/run_task038_full3d_lor_s2_memory_first.py").read_text(encoding="utf-8")
    for forbidden in ("RealL2PositiveHXFixture", "PCGAMG", "global_high_order_aij = True"):
        assert forbidden not in core
        assert forbidden not in runner


def test_checker_recomputes_watchdog_and_rejects_missing_ledger(tmp_path):
    record, watchdog = _synthetic_record(tmp_path)
    checked = checker.check_record(record, watchdog, SOURCE_SHA)
    assert checked["passed"] is True, checked
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["apply_ledger"]["relative_path"] = "missing.json"
    record.write_text(json.dumps(payload), encoding="utf-8")
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert failed["passed"] is False
    assert any("apply ledger" in item for item in failed["contract_errors"])


def test_checker_requires_ten_identical_repeat_digests_and_norms(tmp_path):
    record, watchdog = _synthetic_record(tmp_path / "digest")
    _rewrite_ledger(
        record,
        lambda ledger: ledger["rows"][7]["high_positive"].update(digest="c" * 64),
    )
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert failed["passed"] is False
    assert any("repeat digest" in item for item in failed["contract_errors"])

    record, watchdog = _synthetic_record(tmp_path / "norm")
    _rewrite_ledger(
        record,
        lambda ledger: ledger["rows"][7]["high_positive"].update(norm=1.25),
    )
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert failed["passed"] is False
    assert any("repeat norm" in item for item in failed["contract_errors"])


def test_checker_reserve_nested_and_known_ledger_fail_closed(tmp_path):
    record, watchdog = _synthetic_record(tmp_path / "reserve")
    payload = json.loads(record.read_text(encoding="utf-8"))
    del payload["reserve"]
    record.write_text(json.dumps(payload), encoding="utf-8")
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert failed["classification"] == "CONTRACT_INVALID"
    assert any("reserve facts" in item for item in failed["contract_errors"])

    record, watchdog = _synthetic_record(tmp_path / "nested")
    payload = json.loads(record.read_text(encoding="utf-8"))
    del payload["architecture"]["physical_action"]["dtn_action"]["trace_matrix_materialized"]
    record.write_text(json.dumps(payload), encoding="utf-8")
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert any("dtn_action.trace_matrix_materialized is missing" in item for item in failed["contract_errors"])

    record, watchdog = _synthetic_record(tmp_path / "known_sum")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["retained"]["known_total_bytes"] += 1
    record.write_text(json.dumps(payload), encoding="utf-8")
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert any("known retained bytes do not sum" in item for item in failed["contract_errors"])


def test_checker_identity_and_resource_boundaries(tmp_path):
    record, watchdog = _synthetic_record(tmp_path / "identity")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["wavelength_nm"] = 12.5
    record.write_text(json.dumps(payload), encoding="utf-8")
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert any("wavelength" in item for item in failed["contract_errors"])

    record, watchdog = _synthetic_record(tmp_path / "input")
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["input_identity"]["raw_sha256"] = "0" * 64
    record.write_text(json.dumps(payload), encoding="utf-8")
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert any("input SHA" in item for item in failed["contract_errors"])

    record, watchdog = _synthetic_record(tmp_path / "growth_exact")
    _rewrite_ledger(
        record,
        lambda ledger: ledger["rows"][1]["resource"]["process_tree"].update(
            rss_bytes=100 + checker.GROWTH_LIMIT
        ),
    )
    assert checker.check_record(record, watchdog, SOURCE_SHA)["passed"] is True

    record, watchdog = _synthetic_record(tmp_path / "growth_over")
    _rewrite_ledger(
        record,
        lambda ledger: ledger["rows"][1]["resource"]["process_tree"].update(
            rss_bytes=101 + checker.GROWTH_LIMIT
        ),
    )
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert any("RSS growth" in item for item in failed["gate_failures"])

    record, watchdog = _synthetic_record(tmp_path / "retained_exact")
    _rewrite_watchdog(watchdog, checker.RETAINED_LIMIT)
    assert checker.check_record(record, watchdog, SOURCE_SHA)["passed"] is True

    record, watchdog = _synthetic_record(tmp_path / "retained_over")
    _rewrite_watchdog(watchdog, checker.RETAINED_LIMIT + 1)
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert "BASE_FITS_BUT_NO_PRODUCTION_HEADROOM" == failed["classification"]
    assert any("retained process-tree RSS" in item for item in failed["gate_failures"])

    record, watchdog = _synthetic_record(tmp_path / "cold_limit")
    _rewrite_watchdog(watchdog, checker.COLD_LIMIT)
    failed = checker.check_record(record, watchdog, SOURCE_SHA)
    assert any("cold process-tree RSS" in item for item in failed["gate_failures"])


def test_s2_paths_and_checker_output_fail_closed(tmp_path):
    raw_dir = tmp_path / "raw"
    record_path = tmp_path / "record.json"
    runner._prepare_paths(raw_dir, record_path, MPI.COMM_SELF)
    with np.testing.assert_raises(FileExistsError):
        runner._prepare_paths(raw_dir, record_path, MPI.COMM_SELF)

    record, watchdog = _synthetic_record(tmp_path / "output")
    output = tmp_path / "check.json"
    output.write_text("existing", encoding="utf-8")
    with np.testing.assert_raises(FileExistsError):
        checker.main(
            [
                "--record", str(record),
                "--watchdog-compact", str(watchdog),
                "--expected-source-sha", SOURCE_SHA,
                "--output", str(output),
            ]
        )


def test_watchdog_path_and_terminal_race_contract(tmp_path):
    worker_raw = tmp_path / "worker_raw"
    worker_raw.mkdir()
    with np.testing.assert_raises(ValueError):
        foundation_watchdog._validate_watchdog_paths(
            worker_raw, (worker_raw / "watchdog.json",)
        )

    class Exited:
        def poll(self):
            return 0

    class Live:
        def poll(self):
            return None

    assert foundation_watchdog._watchdog_terminal_exit_race(Exited(), "authority_unreadable")
    assert not foundation_watchdog._watchdog_terminal_exit_race(Live(), "authority_unreadable")
