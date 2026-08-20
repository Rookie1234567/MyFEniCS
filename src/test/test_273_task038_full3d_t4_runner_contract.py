"""Pure contracts for the T4 worker and read-only checker."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
import sys
import types

import pytest

from benchmarks import run_task038_full3d_t4 as runner
from benchmarks import task038_full3d_t4_checker as checker
from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)


def _packets(value: complex):
    return (
        (
            "full_fe",
            1,
            ((0, 0, 0), (1, 0, 0)),
            0,
            ("canonical_edge", "contract"),
            None,
            (1.0, 0.0),
        ),
        value,
    ), (
        (
            "full_fe",
            2,
            ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)),
            0,
            ("canonical_face", "contract"),
            None,
            (1.0, 0.0),
        ),
        value * (0.5 - 0.25j),
    )


def _manifest(raw_dir: Path, role: str, mpi_size: int, value: complex) -> dict:
    canonical_dir = raw_dir / "canonical"
    canonical_dir.mkdir(exist_ok=True)
    packet_rows = _packets(value)
    shards = []
    for rank in range(mpi_size):
        shard_path = canonical_dir / f"{role}.rank{rank:04d}.jsonl"
        shard = write_canonical_packet_shard(
            shard_path, packet_rows[rank::mpi_size], audit_packets=True
        )
        shards.append(shard)
    manifest = canonical_shard_manifest(
        role=role,
        mpi_size=mpi_size,
        shard_metadata=shards,
        extractor_audit={"contract": True},
    )
    manifest_path = canonical_dir / f"{role}.manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    return {
        "kind": "physical_hcurl_packet_manifest",
        "relative_path": str(manifest_path.relative_to(raw_dir)),
        "bytes": int(manifest_path.stat().st_size),
        "sha256": manifest_sha,
        "packet_count": int(manifest["global_summed_packet_count"]),
        "mpi_size": mpi_size,
    }


def _record(root: Path, case: str) -> Path:
    spec = runner.T4_CASES[case]
    raw_dir = root / case / "raw"
    raw_dir.mkdir(parents=True)
    artifacts = {}
    for role in (
        "source_1",
        "source_2",
        "source_1_forward",
        "source_1_backward",
        "source_2_forward",
        "source_2_backward",
    ):
        artifacts[role] = _manifest(
            raw_dir,
            role,
            spec["mpi_size"],
            1.0 + 0.2j,
        )
    actions = {}
    telemetry = []
    for source in ("source_1", "source_2"):
        actions[source] = {}
        for direction in ("forward", "backward"):
            actions[source][direction] = {
                "oracle_pairing": [1.0, 0.0],
                "candidate_pairing": [1.0, 0.0],
                "relative_error": 0.0,
                "finite": True,
                "repeat_relative_difference": 0.0,
                "canonical": artifacts[f"{source}_{direction}"],
            }
            for repeat in (0, 1):
                telemetry.append(
                    {
                        "source": source,
                        "direction": direction,
                        "repeat": repeat,
                        "elapsed_seconds": 0.01,
                        "rss_semantics": "mpi_rank_max_current_self_rss",
                        "swap_semantics": "current_process_VmSwap",
                        "rank_max_current_rss_bytes": 100,
                        "rank_max_swap_used_bytes": 0,
                    }
                )
    peer = [0] if spec["mpi_size"] == 1 else [0, 1]
    record = {
        "schema": runner.T4_SCHEMA,
        "case": case,
        "degree": spec["degree"],
        "mpi_size": spec["mpi_size"],
        "raw_dir": str(raw_dir),
        "profile": runner.T4_PROFILE,
        "source": {
            "branch": runner.T4_BRANCH,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "expected_sha": "a" * 40,
            "tracked_status_start": "",
            "tracked_status_end": "",
            "clean_start": True,
            "clean_end": True,
        },
        "model": {
            "profile": runner.T4_PROFILE,
            "slab_count": 2,
            "transmission": runner.T4_TRANSMISSION,
            "wavelength_nm": 13.5,
            "mesh_target_nm": 50.0,
            "degree": spec["degree"],
            "analytic_source": "incident_air_plane_wave_field",
            "incident_theta_deg": 21.131,
            "incident_phi_deg": 33.690,
            "source_family": "fixed_oblique_s_p",
            "source_polarizations": {"source_1": "s", "source_2": "p"},
            "test_polarization": "fixed_s_plus_p_linear_combination",
            "test_linear_combination": {
                "s": [0.6, 0.1],
                "p": [0.35, -0.2],
            },
        },
        "topology": {
            "profile": runner.T4_PROFILE,
            "slab_count": 2,
            "transmission": runner.T4_TRANSMISSION,
            "global_facet_count": 4,
            "local_facet_count": 2,
            "canonical_sha256": ("b" if spec["degree"] == 2 else "c") * 64,
            "local_canonical_sha256": "d" * 64,
            "owned_trace_rows": 2,
            "ghost_trace_rows": 0,
            "owner_closure": True,
            "neighbor_plan": {
                "forward_send_peers": [],
                "forward_recv_peers": [],
                "backward_send_peers": [],
                "backward_recv_peers": [],
                "lower_participant_ranks": peer,
                "upper_participant_ranks": peer,
            },
            "restriction_prolongation_adjoint_relative_error": 0.0,
            "floquet_phases": {
                "x": [0.2, 0.3],
                "y": [0.4, -0.1],
                "corner": [0.11, 0.05],
            },
            "floquet_phase_nontrivial": True,
            "interface_classifications": ["homogeneous", "nonhomogeneous"],
            "audit": {
                "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
                "phase_application": "finalized_floquet_mpc_once",
                "bounded_material_class_collective": True,
                "material_class_collective": "bounded_inventory_allgather_with_error_allreduce",
                "numeric_allgather": False,
                "global_aij_materialized": False,
                "dense_interface_mass_materialized": False,
                "dense_interface_schur_materialized": False,
                "slab_factor_materialized": False,
                "slave_rows_excluded": True,
            },
        },
        "reconstruction": {
            "first_reconstruction_relation_error": 0.0,
            "second_reconstruction_relation_error": 0.0,
            "second_full_owned_ghost_idempotence_error": 0.0,
            "second_slave_idempotence_error": 0.0,
        },
        "artifacts": artifacts,
        "actions": actions,
        "candidate_audit": {
            "candidate": "A",
            "action": "interior_facet_tangential_robin_weak_form",
            "phase_application": "finalized_floquet_mpc_once",
            "numeric_allgather": False,
            "global_aij_materialized": False,
            "dense_interface_mass_materialized": False,
            "dense_interface_schur_materialized": False,
            "slab_factor_materialized": False,
            "directions": {
                direction: {
                    "retained_numeric_payload_local_bytes": 100,
                    "retained_numeric_payload_global_max_bytes": 100,
                    "per_apply_bounded_temporary_bytes": 20,
                    "apply_count": 4,
                }
                for direction in ("forward", "backward")
            },
        },
        "telemetry": telemetry,
        "resource": {
            "rss_semantics": "mpi_rank_max_current_self_rss",
            "process_tree_evidence": "not_measured_t4",
            "swap_semantics": "mpi_rank_max_current_process_VmSwap",
            "swap_used_bytes": 0,
        },
        "execution": {
            "ksp_created": False,
            "pde_run": False,
            "official_physics": "not_run",
        },
    }
    path = root / case / "record.json"
    path.write_bytes(runner._canonical_json(record))
    return path


def test_checker_has_no_runner_solver_or_mpi_import() -> None:
    tree = ast.parse(inspect.getsource(checker))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any(
        module == "mpi4py"
        or module == "petsc4py"
        or module.startswith("src")
        or module.endswith("run_task038_full3d_t4")
        for module in imports
    )


def test_runner_is_action_only_and_has_exact_case_parser() -> None:
    source = inspect.getsource(runner)
    assert "petsc4py" not in source
    assert "slepc4py" not in source
    assert "createKSP" not in source
    args = runner._parser().parse_args(
        [
            "run",
            "--case",
            "p3-mpi2",
            "--raw-dir",
            "raw",
            "--record",
            "record.json",
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.case == "p3-mpi2"
    assert args.expected_source_sha == "a" * 40
    assert set(runner.T4_CASES) == {"p2-mpi1", "p2-mpi2", "p3-mpi1", "p3-mpi2"}


def test_analytic_field_import_path_is_exercised(monkeypatch: pytest.MonkeyPatch) -> None:
    source = inspect.getsource(runner._analytic_field)
    assert (
        "from src.solvers.common_3d_fields import incident_air_plane_wave_field"
        in source
    )
    assert "from src.common_3d_fields import" not in source

    calls: list[str] = []

    class FakeX:
        def scatter_forward(self) -> None:
            calls.append("scatter")

    class FakeField:
        x = FakeX()

    module = types.ModuleType("src.solvers.common_3d_fields")
    module.incident_air_plane_wave_field = (
        lambda function_space, cfg: calls.append(cfg.polarization_kind) or FakeField()
    )
    monkeypatch.setitem(sys.modules, "src.solvers.common_3d_fields", module)
    monkeypatch.delitem(sys.modules, "src.common_3d_fields", raising=False)

    @dataclass(frozen=True)
    class FakeConfig:
        polarization_kind: str = "s"
        custom_polarization: object | None = None

    class FakeMpc:
        def homogenize(self, field: FakeField) -> None:
            calls.append("homogenize")

        def backsubstitution(self, field: FakeField) -> None:
            calls.append("backsubstitution")

    floquet_data = types.SimpleNamespace(mpc=FakeMpc())
    result = runner._analytic_field(object(), floquet_data, FakeConfig(), "p")
    assert isinstance(result, FakeField)
    assert calls == ["p", "homogenize", "backsubstitution", "scatter"]


def test_runner_registers_each_action_manifest() -> None:
    source = inspect.getsource(runner._run_case)
    assert 'artifacts[f"{source_name}_{direction}"] = output_manifest' in source


def test_record_checker_passes_and_derives_pairing(tmp_path: Path) -> None:
    path = _record(tmp_path, "p2-mpi1")
    result = checker.check_t4_record(path)
    assert result["passed"] is True
    assert result["derived"]["source_1_forward_relative_error"] == pytest.approx(0.0)


def test_checker_fails_closed_for_missing_identity(tmp_path: Path) -> None:
    path = _record(tmp_path, "p2-mpi1")
    payload = json.loads(path.read_text())
    del payload["topology"]["canonical_sha256"]
    path.write_bytes(runner._canonical_json(payload))
    result = checker.check_t4_record(path)
    assert result["passed"] is False
    assert any("canonical digest" in problem for problem in result["problems"])


def test_exact_four_aggregate_and_canonical_mpi_identity(tmp_path: Path) -> None:
    paths = {
        case: _record(tmp_path, case) for case in runner.T4_CASES
    }
    result = checker.check_t4_aggregate(
        p2_mpi1_record_path=paths["p2-mpi1"],
        p2_mpi2_record_path=paths["p2-mpi2"],
        p3_mpi1_record_path=paths["p3-mpi1"],
        p3_mpi2_record_path=paths["p3-mpi2"],
    )
    assert result["passed"] is True
    assert result["checks"]["exact_four_record_set"] is True
    assert result["checks"]["canonical_source_action_identity"] is True


def test_aggregate_rejects_non_exact_case_set(tmp_path: Path) -> None:
    p2 = _record(tmp_path, "p2-mpi1")
    p3 = _record(tmp_path, "p3-mpi1")
    result = checker.check_t4_aggregate(
        p2_mpi1_record_path=p2,
        p2_mpi2_record_path=p2,
        p3_mpi1_record_path=p3,
        p3_mpi2_record_path=p3,
    )
    assert result["passed"] is False
    assert result["checks"]["exact_four_record_set"] is False
