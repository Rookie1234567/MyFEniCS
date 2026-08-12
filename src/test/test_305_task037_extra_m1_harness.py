from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

import benchmarks.run_task037_extra_m as m1
from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)


def _clean_source() -> dict[str, object]:
    return {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "cleanliness_semantics": "synthetic clean source",
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _canonical_ref(root: Path, prefix: str, role: str, mpi_size: int) -> dict[str, object]:
    packets = (
        (
            (
                "full_fe",
                1,
                ((0, 0, 0), (1, 0, 0)),
                0,
                ("identity",),
                None,
                (1.0, 0.0),
            ),
            0.25 + 0.5j,
        ),
        (
            ("full_fe", 3, ((0, 0, 0),), 1, ("cell",), None, (1.0, 0.0)),
            -0.2 + 0.1j,
        ),
    )
    shard_path = root / f"{prefix}_rank0.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets)
    shard.update({"rank": 0, "local_duplicate_count": 0})
    manifest = canonical_shard_manifest(
        role=role,
        mpi_size=mpi_size,
        shard_metadata=(shard,),
        extractor_audit={"numeric_allgather": False, "local_packet_count": 2},
    )
    manifest_path = root / f"{prefix}_manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    return {"path": manifest_path.name, "role": role, "sha256": manifest_sha}


def test_m1_checker_recomputed_manifest_streams_and_recomputes_duplicates(
    tmp_path: Path,
) -> None:
    consumed: list[int] = []

    def _packets():
        for index in range(3):
            consumed.append(index)
            yield (("full_fe", index), complex(index, -index))

    reference = m1._write_canonical_manifest(
        tmp_path,
        "serial",
        _packets(),
        {"role": "full_fe", "numeric_allgather": False},
        MPI.COMM_SELF,
    )
    manifest = json.loads(
        (tmp_path / "serial_manifest.json").read_text(encoding="utf-8")
    )
    assert consumed == [0, 1, 2]
    assert reference["packet_count"] == 3
    assert reference["duplicate_count"] is None
    assert manifest["duplicate_detection"] == "checker_recomputed_from_shards"
    assert manifest["summed_local_duplicate_count"] is None
    assert m1._canonical_ref_valid(tmp_path, reference, "serial")


def test_m1_numeric_failure_summary_keeps_values_and_skips_canonical() -> None:
    audit: dict[str, object] = {
        "p4_global_rows": 12,
        "p4_owned_rows": 12,
        "p4_ghost_rows": 0,
        "p4_original_local_rows": 12,
        "p4_original_ghost_rows": 0,
        "p4_mpc_extended_local_rows": 12,
        "p4_mpc_extended_ghost_rows": 0,
        "p4_mpc_added_master_ghost_rows": 0,
        "p6_global_rows": 32,
        "p6_owned_rows": 32,
        "p6_ghost_rows": 0,
        "p6_original_local_rows": 32,
        "p6_original_ghost_rows": 0,
        "p6_mpc_extended_local_rows": 32,
        "p6_mpc_extended_ghost_rows": 0,
        "p6_mpc_added_master_ghost_rows": 0,
        "p4_mpc_extended_local_work_bytes": 0,
        "p6_mpc_extended_local_work_bytes": 0,
        "p4_owned_constraint_count_global": 0,
        "p6_owned_constraint_count_global": 0,
        "missing_owned_p6_rows": 0,
        "extra_owned_p6_rows": 0,
        "duplicate_owned_p6_designations": 0,
        "retained_numeric_payload_components": {"reference": 128},
        "retained_numeric_payload_bytes": 128,
        "lazy_p6_work_vec_bytes": 64,
        "retained_transfer_numeric_payload_bytes": 192,
        "bounded_apply_workspace_components": {"forward": {"bytes": 256}},
        "bounded_apply_workspace_bytes": 256,
        "p4_mpc_phase_applied_once": True,
        "p6_mpc_phase_applied_once": True,
        "orientation_cell_count_global": 1,
        "orientation_nonzero_cell_count_global": 1,
        "orientation_metadata_sha256": "b" * 64,
        "reference_transform_sha256": "c" * 64,
        "construction_transient_numeric_payload_bytes": None,
        "measured_process_tree_rss_bytes": None,
    }
    payload = m1._m1_numeric_failure_payload(
        run_dir=Path("/tmp/m1-test"),
        phase="mpi1",
        mpi_size=1,
        source_start=_clean_source(),
        source_end=_clean_source(),
        runtime_identity={"synthetic": True},
        transfer=SimpleNamespace(audit=audit),
        image_error=2.0e-3,
        adjoint_error=3.0e-4,
        image_deterministic=False,
        adjoint_deterministic=True,
        finite=True,
        elapsed_wall_seconds=1.25,
    )
    assert payload["status"] == "gate_failed"
    assert payload["route"] == "M1-review-only"
    assert payload["error"] == "m1_transfer_numeric_gate_failed"
    assert payload["measurement"]["image_relative_error"] == 2.0e-3
    assert payload["measurement"]["adjoint_relative_error"] == 3.0e-4
    assert payload["measurement"]["image_deterministic"] is False
    assert payload["measurement"]["finite"] is True
    assert payload["measurement"]["canonical_manifests"] == {
        "p6_image": {"status": "not_run_by_gate"},
        "p4_adjoint": {"status": "not_run_by_gate"},
    }


def _worker(root: Path, phase: str, mpi_size: int, source: dict[str, object]) -> dict[str, object]:
    p6_ref = _canonical_ref(root, f"{phase}_p6_image", f"{phase}_p6_image", mpi_size)
    p4_ref = _canonical_ref(root, f"{phase}_p4_adjoint", f"{phase}_p4_adjoint", mpi_size)
    measurement = {
        "p4_global_rows": 12,
        "p4_owned_rows": 12,
        "p4_ghost_rows": 0,
        "p6_global_rows": 32,
        "p6_owned_rows": 32,
        "p6_ghost_rows": 0,
        "p4_global_constraints": 3,
        "p6_global_constraints": 4,
        "missing_rows": 0,
        "extra_rows": 0,
        "duplicate_rows": 0,
        "image_relative_error": 0.0,
        "adjoint_relative_error": 0.0,
        "image_deterministic": True,
        "adjoint_deterministic": True,
        "finite": True,
        "phase_once": True,
        "orientation": {"metadata_sha256": "b" * 64},
        "payload_audit": {
            "retained_numeric_payload_components": {"reference": 128},
            "retained_numeric_payload_bytes": 128,
            "lazy_p6_work_vec_bytes": 64,
            "retained_transfer_numeric_payload_bytes": 192,
            "bounded_apply_workspace_bytes": 256,
            "bounded_apply_workspace_components": {"forward": {"bytes": 256}},
            "construction_transient_numeric_payload_bytes": None,
            "measured_process_tree_rss_bytes": None,
        },
        "canonical_manifests": {"p6_image": p6_ref, "p4_adjoint": p4_ref},
        "materialization_identity": {
            "global_transfer_matrix": False,
            "global_matrix": False,
            "global_constraint_matrix": False,
            "condensed": False,
            "trace_only": False,
            "ksp_or_pde": False,
            "numeric_allgather": False,
            "replicated_global_numeric_vector": False,
        },
    }
    return m1._attach_evidence(
        {
            "schema": m1.M1_WORKER_SCHEMA,
            "status": "measurement_complete",
            "run_dir": str(root),
            "phase": phase,
            "mpi_size": mpi_size,
            "scope": m1._m1_scope(mpi_size),
            "identity": m1._m1_identity(),
            "phase_identity": m1._m1_phase_identity(),
            "runtime_identity": {
                "sys_executable": str(sys.executable),
                "petsc_scalar_type": "complex128",
                "petsc_int_type": "int32",
                "mpi_size": mpi_size,
                "linux_abi": True,
                "package_paths": {
                    "petsc4py": "/usr/lib/petsc4py.py",
                    "slepc4py": "/usr/lib/slepc4py.py",
                    "dolfinx": "/usr/lib/dolfinx.py",
                    "mpi4py": "/usr/lib/mpi4py.py",
                },
                "threads": {
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "NUMEXPR_NUM_THREADS": "1",
                },
            },
            "source_at_start": source,
            "source_at_end": source,
            "measurement": measurement,
            "m1_build_audit": {
                "structural_build_pass": True,
                "m1_gate_pass": False,
                "global_transfer_matrix_materialized": False,
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "numeric_allgather": False,
                "replicated_global_numeric_vector": False,
                "retained_numeric_payload_components": {"reference": 128},
                "retained_numeric_payload_bytes": 128,
                "lazy_p6_work_vec_bytes": 64,
                "retained_transfer_numeric_payload_bytes": 192,
                "retained_transfer_numeric_payload_gate": True,
                "bounded_apply_workspace_bytes": 256,
                "bounded_apply_workspace_gate": True,
                "bounded_apply_workspace_components": {"forward": {"bytes": 256}},
                "orientation_metadata_sha256": "b" * 64,
                "reference_transform_sha256": "c" * 64,
            },
            "error": None,
            "controlled_stop": None,
        }
    )


def _progress(root: Path, phase: str) -> None:
    path = root / f"{phase}_progress.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        for index, event in enumerate(m1.M1_EVENTS):
            stream.write(
                json.dumps(
                    {
                        "schema": f"{m1.M1_SCHEMA}.progress.v1",
                        "phase": phase,
                        "event": event,
                        "event_index": index,
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def _process(peak: int, return_code: int = 0) -> dict[str, object]:
    return {
        "return_code": return_code,
        "termination": None if return_code == 0 else {"reason": "worker_failed"},
        "peak_rss_bytes": peak,
        "swap_bytes": 0,
        "processes_gone": True,
        "drain": {"gone": True, "elapsed_wall_seconds": 0.0, "poll_count": 0},
        "root_pid": 100,
        "observed_process_tree_pids": [],
    }


def _raw_fixture(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    root.mkdir(exist_ok=True)
    source = _clean_source()
    workers = {phase: _worker(root, phase, size, source) for phase, size in (("mpi1", 1), ("mpi2", 2))}
    for phase in ("mpi1", "mpi2"):
        (root / f"{phase}_worker_summary.json").write_text(
            json.dumps(workers[phase], sort_keys=True), encoding="utf-8"
        )
        _progress(root, phase)
        for name in ("stdout.txt", "timeline.jsonl", "root_pid.json"):
            path = root / f"{phase}_{name}"
            if name == "timeline.jsonl":
                path.write_text(
                    json.dumps(
                        {
                            "phase": phase,
                            "sample_kind": "worker",
                            "all_status_readable": True,
                            "rss_bytes": 100 if phase == "mpi1" else 200,
                            "swap_bytes": 0,
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            else:
                path.write_text("{}\n", encoding="utf-8")
    watchdog = {
        "schema": m1.M1_WATCHDOG_SCHEMA,
        "status": "pass",
        "pass": True,
        "route": "M1",
        "run_dir": str(root),
        "scope": m1._m1_scope(),
        "identity": m1._m1_identity(),
        "source_at_start": source,
        "source_at_end": source,
        "command_identity": {
            "python": sys.executable,
            "mpi1_command": m1._m1_worker_command(sys.executable, root, "mpi1", 1),
            "mpi2_command": m1._m1_worker_command(sys.executable, root, "mpi2", 2),
        },
        "mpi1": _process(100),
        "mpi2": _process(200),
        "worker_summaries": {
            "mpi1": m1._artifact(root, "mpi1_worker_summary.json"),
            "mpi2": m1._artifact(root, "mpi2_worker_summary.json"),
        },
    }
    watchdog["raw_artifacts"] = m1._recorded_artifacts(root)
    watchdog = m1._attach_evidence(watchdog)
    (root / "m1_watchdog_summary.json").write_text(
        json.dumps(watchdog, sort_keys=True), encoding="utf-8"
    )
    return watchdog, source


def _rewrite_watchdog(root: Path, watchdog: dict[str, object]) -> None:
    watchdog["raw_artifacts"] = m1._recorded_artifacts(root)
    (root / "m1_watchdog_summary.json").write_text(
        json.dumps(m1._attach_evidence(watchdog), sort_keys=True), encoding="utf-8"
    )


def test_m1_evaluator_positive_and_canonical_comparison(tmp_path: Path) -> None:
    _watchdog, source = _raw_fixture(tmp_path)
    result = m1._m1_check_raw(tmp_path.resolve(), source)
    assert result["pass"] is True
    assert result["status"] == "pass"
    assert result["checks"]["canonical_p6_image"] is True
    assert result["checks"]["canonical_p4_adjoint"] is True
    assert result["measurements"]["canonical_comparisons"]["p6_image"]["relative_coefficient_l2"] == 0.0


def test_m1_missing_measurement_key_fails_closed(tmp_path: Path) -> None:
    watchdog, source = _raw_fixture(tmp_path)
    worker_path = tmp_path / "mpi1_worker_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    del worker["measurement"]["adjoint_relative_error"]
    worker_path.write_text(json.dumps(m1._attach_evidence(worker), sort_keys=True), encoding="utf-8")
    _rewrite_watchdog(tmp_path, watchdog)
    result = m1._m1_check_raw(tmp_path.resolve(), source)
    assert result["pass"] is False
    assert "mpi1_measurement_missing_key" in result["problems"]


def test_m1_rss_limit_is_strict(tmp_path: Path) -> None:
    watchdog, source = _raw_fixture(tmp_path)
    watchdog["mpi1"]["peak_rss_bytes"] = m1.M1_MPI1_RSS_LIMIT_BYTES
    _rewrite_watchdog(tmp_path, watchdog)
    result = m1._m1_check_raw(tmp_path.resolve(), source)
    assert result["pass"] is False
    assert "mpi1_process_gate" in result["problems"]


def test_m1_capacity_gates_are_inclusive_and_recomputed(tmp_path: Path) -> None:
    def _check(
        name: str,
        retained_bytes: int,
        workspace_bytes: int,
    ) -> dict[str, object]:
        root = tmp_path / name
        watchdog, source = _raw_fixture(root)
        worker_path = root / "mpi1_worker_summary.json"
        worker = json.loads(worker_path.read_text(encoding="utf-8"))
        payload = worker["measurement"]["payload_audit"]
        audit = worker["m1_build_audit"]
        payload["retained_transfer_numeric_payload_bytes"] = retained_bytes
        audit["retained_transfer_numeric_payload_bytes"] = retained_bytes
        audit["retained_transfer_numeric_payload_gate"] = (
            retained_bytes <= m1.M1_RETAINED_PAYLOAD_LIMIT_BYTES
        )
        payload["bounded_apply_workspace_bytes"] = workspace_bytes
        audit["bounded_apply_workspace_bytes"] = workspace_bytes
        audit["bounded_apply_workspace_gate"] = (
            workspace_bytes <= m1.M1_WORKSPACE_LIMIT_BYTES
        )
        worker_path.write_text(
            json.dumps(m1._attach_evidence(worker), sort_keys=True),
            encoding="utf-8",
        )
        _rewrite_watchdog(root, watchdog)
        return m1._m1_check_raw(root.resolve(), source)

    exact = _check(
        "exact",
        m1.M1_RETAINED_PAYLOAD_LIMIT_BYTES,
        m1.M1_WORKSPACE_LIMIT_BYTES,
    )
    assert exact["pass"] is True
    retained_over = _check(
        "retained_over",
        m1.M1_RETAINED_PAYLOAD_LIMIT_BYTES + 1,
        256,
    )
    assert retained_over["pass"] is False
    assert "mpi1_payload_contract" in retained_over["problems"]
    workspace_over = _check(
        "workspace_over",
        192,
        m1.M1_WORKSPACE_LIMIT_BYTES + 1,
    )
    assert workspace_over["pass"] is False
    assert "mpi1_payload_contract" in workspace_over["problems"]


def test_m1_mpi1_failure_locks_mpi2(tmp_path: Path) -> None:
    watchdog, source = _raw_fixture(tmp_path)
    watchdog["status"] = "gate_failed"
    watchdog["pass"] = False
    watchdog["route"] = "M1-review-only"
    watchdog["mpi1"] = _process(100, return_code=1)
    watchdog["mpi2"] = {"not_run_by_gate": True}
    _rewrite_watchdog(tmp_path, watchdog)
    result = m1._m1_check_raw(tmp_path.resolve(), source)
    assert result["pass"] is False
    assert result["checks"]["mpi2_not_run_by_gate"] is True


def test_m1_cli_writes_evidence_bound_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _watchdog, source = _raw_fixture(tmp_path)
    monkeypatch.setattr(m1, "_clean_source", lambda: source)
    output = tmp_path / "check.json"
    assert m1._run_m1_check(tmp_path, output) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["evidence_sha256"] == m1._attach_evidence(payload)["evidence_sha256"]


def test_m1_parser_exposes_only_requested_subcommands() -> None:
    parser = m1._parser()
    assert parser.parse_args(["m1-worker", "--run-dir", "/tmp/r", "--phase", "mpi1", "--expected-mpi-size", "1"]).command == "m1-worker"
    assert parser.parse_args(["m1-watchdog", "--run-dir", "/tmp/r"]).command == "m1-watchdog"
    assert parser.parse_args(["m1-check", "--run-dir", "/tmp/r", "--output", "/tmp/o"]).command == "m1-check"


def test_m1_dual_source_is_partition_independent_by_global_id() -> None:
    class _IndexMap:
        def __init__(self, start: int, size: int) -> None:
            self.start = int(start)
            self.size_local = int(size)

        def local_to_global(self, local_ids: np.ndarray) -> np.ndarray:
            return self.start + np.asarray(local_ids, dtype=np.int64)

    comm = MPI.COMM_WORLD
    global_size = 12
    base, remainder = divmod(global_size, comm.size)
    start = comm.rank * base + min(comm.rank, remainder)
    size = base + int(comm.rank < remainder)
    values = m1._deterministic_global_dual_values(_IndexMap(start, size))
    packets = comm.allgather((start, values))
    reconstructed = np.empty(global_size, dtype=np.complex128)
    for packet_start, packet_values in packets:
        reconstructed[packet_start : packet_start + len(packet_values)] = packet_values
    expected = m1._deterministic_global_dual_values(_IndexMap(0, global_size))
    np.testing.assert_array_equal(reconstructed, expected)


def test_m1_floquet_compatible_manufactured_field() -> None:
    cfg = SimpleNamespace(
        x_min=-2.0,
        x_max=3.0,
        y_min=-1.0,
        y_max=4.0,
        floquet_phase_x=np.exp(0.37j),
        floquet_phase_y=np.exp(-0.23j),
    )
    field = m1._floquet_compatible_hcurl(cfg)
    x_min = np.asarray(
        [[cfg.x_min, cfg.x_min], [0.25, 0.25], [0.5, 0.75]],
        dtype=np.float64,
    )
    x_max = x_min.copy()
    x_max[0] = cfg.x_max
    y_min = x_min.copy()
    y_min[1] = cfg.y_min
    y_max = x_min.copy()
    y_max[1] = cfg.y_max
    corner_min = np.asarray(
        [[cfg.x_min], [cfg.y_min], [0.5]],
        dtype=np.float64,
    )
    corner_max = corner_min.copy()
    corner_max[0] = cfg.x_max
    corner_max[1] = cfg.y_max

    np.testing.assert_allclose(
        field(x_max),
        complex(cfg.floquet_phase_x) * field(x_min),
        rtol=0.0,
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        field(y_max),
        complex(cfg.floquet_phase_y) * field(y_min),
        rtol=0.0,
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        field(corner_max),
        complex(cfg.floquet_phase_x)
        * complex(cfg.floquet_phase_y)
        * field(corner_min),
        rtol=0.0,
        atol=1.0e-14,
    )
    assert np.all(np.abs(field(corner_min)[:, 0]) > 0.0)
    assert m1._m1_scope()["manufactured_field"] == (
        "floquet_compatible_bilinear_p4_v1"
    )


def test_m1_canonical_route_is_owner_local() -> None:
    source = Path(m1.__file__).read_text(encoding="utf-8")
    assert "extract_canonical_full_fe_packets" not in source
    assert "_scatter_values" not in source
    assert "p6_packets = tuple" not in source
    assert "p4_packets = tuple" not in source
    assert "write_canonical_packet_shard" in source
