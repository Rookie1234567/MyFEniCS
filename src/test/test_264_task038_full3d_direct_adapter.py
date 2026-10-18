"""Pure Task38 T4a contracts for the connected Full3D direct path."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

import src.runners.task038_full3d_direct as direct_adapter
from src.io import load_and_resolve
from src.io.execution_plan import CONNECTED_METHODS, method_adapter_available
from src.io.input_loader import InputError
from src.io.input_validation import simulation_config_3d_from_normalized
from src.runners.task038_full3d_direct import run_full3d_direct
from src.runners.task038_input_worker import _dispatch_resolved_payload
from src.solvers.full3d_lifecycle_packet import write_packet

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/full3d_direct_example.dat"
OFFICIAL = ROOT / "input/official/grazing1_phi0_full3d_direct_mpi8.dat"
SMOKE = ROOT / "input/smoke/full3d_direct_p2_h100_mpi1.dat"
ORDINARY_2D = ROOT / "input/templates/ordinary_2d_example.dat"
TASK42_13P5 = ROOT / (
    "input/official/task42hybrid_az90_50x50_17x20_0p7nm/"
    "13p5nm_p6h10_full3d_direct_mpi8.dat"
)


class _EightRankPacketFixtureComm:
    """Write a small rank-complete packet without launching the solver under MPI."""

    rank = 0
    size = 8

    def __init__(self, packet_directory: Path, solution: np.ndarray, rhs: np.ndarray):
        self.packet_directory = packet_directory
        self.solution = solution
        self.rhs = rhs
        self.shards_written = False

    def allgather(self, value):
        if isinstance(value, dict) and "ownership_range" in value:
            rows = [value]
            if not self.shards_written:
                total = self.solution.size
                quotient, remainder = divmod(total, self.size)
                for rank in range(1, self.size):
                    start = rank * quotient + min(rank, remainder)
                    stop = start + quotient + int(rank < remainder)
                    shard_name = f"rank{rank:04d}.npz"
                    shard_path = self.packet_directory / shard_name
                    np.savez(
                        shard_path,
                        solution=self.solution[start:stop],
                        rhs=self.rhs[start:stop],
                    )
                    rows.append(
                        {
                            "rank": rank,
                            "path": shard_name,
                            "sha256": hashlib.sha256(shard_path.read_bytes()).hexdigest(),
                            "size": stop - start,
                            "ownership_range": [start, stop],
                        }
                    )
                self.shards_written = True
            return rows
        return [value] * self.size

    @staticmethod
    def allreduce(value, op=None):
        return value

    @staticmethod
    def barrier():
        return None


def _payload(path: Path = TEMPLATE) -> dict:
    return load_and_resolve(path).as_jsonable()


def _write_task42_adapter_archive(tmp_path: Path, payload: dict) -> tuple[Path, str, str]:
    """Build a small, fully bound packet RUN envelope for the real adapter verifier."""

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise ValueError("the adapter archive fixture is a serial test fixture")
    payload = deepcopy(payload)
    # Preserve the registered MPI8 resolved identity while keeping the archived
    # vectors small; the fixture communicator writes all eight schema-valid shards.
    resolved_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    identity = direct_adapter._task42_packet_recovery_expected_identity(
        payload, resolved_config_sha256=resolved_sha
    )

    run_root = tmp_path / "archived-run"
    numerical_output = run_root / "numerical_output"
    packet_directory = numerical_output / "pre_recovery_packet"
    run_root.mkdir(parents=True)
    input_bytes = TASK42_13P5.read_bytes()
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    assert payload["provenance"]["input_sha256"] == input_sha
    physical_sha = payload["provenance"]["physical_model_sha256"]
    external_keys = payload["derived"]["external_mode_inventory"]["keys"]
    vector_size = max(8, len(external_keys))
    vector = np.arange(vector_size, dtype=np.float64).astype(np.complex128)
    rhs = 2.0 * vector
    quotient, remainder = divmod(vector_size, 8)
    rank_zero_end = quotient + int(remainder > 0)
    packet = write_packet(
        packet_directory,
        vector[:rank_zero_end],
        rhs[:rank_zero_end],
        identity=identity,
        metadata={
            "external_keys": external_keys,
            "external_q": [[0.0, 0.0] for _ in external_keys],
            "task42_direct_original_residual_pass": True,
        },
        ownership_range=(0, rank_zero_end),
        comm=_EightRankPacketFixtureComm(packet_directory, vector, rhs),
    )
    assert packet["pass"] is True

    (run_root / "resolved_config.json").write_bytes(resolved_bytes)
    (run_root / "input_original.dat").write_bytes(input_bytes)
    (run_root / "input_sha256.txt").write_text(input_sha + "\n", encoding="ascii")
    (run_root / "physical_model_sha256.txt").write_text(
        physical_sha + "\n", encoding="ascii"
    )
    (run_root / "source_sha.txt").write_text(
        direct_adapter.TASK42_RECOVERY_ARCHIVE_SOURCE_SHA + "\n", encoding="ascii"
    )
    run_manifest = {
        "source_sha": direct_adapter.TASK42_RECOVERY_ARCHIVE_SOURCE_SHA,
        "resolved_config_sha256": resolved_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "model_id": identity["model_id"],
        "run_id": identity["run_id"],
        "comparison_group": identity["comparison_group"],
        "method": identity["method"],
        "mpi_size": identity["mpi_size"],
        "output_directory": str(run_root),
        "numerical_output_directory": str(numerical_output),
    }
    (run_root / "run_manifest.json").write_text(
        json.dumps(run_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return packet_directory / "manifest.json", packet["manifest_sha256"], resolved_sha


def test_task42_recovery_adapter_validates_archive_without_creating_packet(
    tmp_path: Path,
):
    """Exercise the real adapter/archive verifier while intercepting only the solve."""

    payload = _payload(TASK42_13P5)
    manifest_path, manifest_sha, resolved_sha = _write_task42_adapter_archive(
        tmp_path, payload
    )
    seen = []

    def stage_gate(*_args, **_kwargs):
        return {"status": "fixture_authorized"}

    def fake_solver(_cfg, output_directory, **kwargs):
        seen.append(dict(kwargs))
        return _summary(canonical_root=output_directory)

    recovery_run = tmp_path / "recovery-run"
    result = run_full3d_direct(
        payload,
        recovery_run,
        solver_runner=fake_solver,
        source_sha="a" * 40,
        resolved_config_sha256=resolved_sha,
        task42_stage_gate=stage_gate,
        task42_bridge_path=None,
        task42_packet_recovery_manifest=manifest_path,
        task42_packet_recovery_manifest_sha256=manifest_sha,
    )
    assert result["passed"] is True, result["errors"]
    recovery_kwargs = seen[-1]
    assert recovery_kwargs["task42_packet_recovery_manifest"] == manifest_path.resolve()
    assert recovery_kwargs["task42_packet_recovery_manifest_sha256"] == manifest_sha
    assert recovery_kwargs["task42_bridge_path"] is None
    assert recovery_kwargs.get("pre_recovery_packet_directory") is None
    assert recovery_kwargs.get("pre_recovery_packet_identity") is None
    assert not (
        recovery_run / "numerical_output" / "pre_recovery_packet"
    ).exists()

    staged_run = tmp_path / "staged-run"
    staged = run_full3d_direct(
        payload,
        staged_run,
        solver_runner=fake_solver,
        source_sha="b" * 40,
        resolved_config_sha256="c" * 64,
        task42_stage_gate=stage_gate,
        task42_bridge_path=tmp_path / "staged-bridge.so",
    )
    assert staged["passed"] is True, staged["errors"]
    staged_kwargs = seen[-1]
    assert staged_kwargs["task42_bridge_path"] == str(tmp_path / "staged-bridge.so")
    assert staged_kwargs["pre_recovery_packet_directory"] == (
        staged_run.resolve() / "numerical_output" / "pre_recovery_packet"
    )
    assert staged_kwargs["pre_recovery_packet_identity"]["source_sha"] == "b" * 40
    assert not staged_kwargs["pre_recovery_packet_directory"].exists()

    wrong_profile = deepcopy(payload)
    wrong_profile["model_id"] = "not_a_registered_task42_profile"
    with pytest.raises(ValueError, match="not valid on other profiles"):
        run_full3d_direct(
            wrong_profile,
            tmp_path / "wrong-profile-run",
            solver_runner=fake_solver,
            task42_stage_gate=stage_gate,
        )
    assert len(seen) == 2


def _summary(*, canonical_root: Path | None = None, **updates):
    value = {
        "case_status": "completed",
        "official_result": True,
        "linear_system_relative_residual": 1.0e-12,
        "R_total": 0.2,
        "T_total": 0.7,
        "A_volume_total": 0.1,
    }
    if canonical_root is not None:
        canonical_root.mkdir(parents=True, exist_ok=True)
        roles = {}
        for role_name in ("active_trace", "full_fe"):
            manifest = canonical_root / f"{role_name}.json"
            manifest.write_text("{}\n", encoding="utf-8")
            roles[role_name] = {
                "manifest": str(manifest),
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "global_summed_packet_count": 1,
                "schema_version": "task037.canonical-vector-manifest.v1",
            }
        value["full3d_direct_canonical_export"] = {
            "status": "completed",
            "roles": roles,
        }
    value.update(updates)
    return value


def test_shared_conversion_preserves_resolved_stage4_identity():
    specification = load_and_resolve(TEMPLATE)
    payload = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(payload)
    assert cfg.stage_case == "stage4_block_grating"
    assert cfg.geometry_kind == "rectangular_block_grating"
    assert cfg.lambda0 == specification.incidence["wavelength_nm"]
    assert cfg.period_x == specification.geometry["period_x_nm"]
    assert cfg.period_y == specification.geometry["period_y_nm"]
    assert cfg.incident_theta_deg == 90.0 - specification.incidence["grazing_angle_deg"]
    assert cfg.incident_phi_deg == specification.incidence["azimuth_deg"]
    assert cfg.nedelec_degree == specification.discretization["nedelec_degree"]
    assert cfg.mesh_target_size == specification.discretization["mesh_target_nm"]
    assert cfg.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
    assert cfg.matrix_diagnostics_assemble_only is False
    assert cfg.matrix_diagnostics_factorization_only is False
    assert cfg.use_floquet_xy is True
    assert cfg.stage4_dtn_assembly == "auxiliary"


def test_small_smoke_matches_old_target_stage4_factory():
    from src.common.config_3d import target_stage4_config

    specification = load_and_resolve(SMOKE)
    assert specification.output["export_canonical_vectors"] is False
    dat_cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    old_cfg = target_stage4_config(degree=2, h_nm=100.0)
    old_cfg.matrix_diagnostics_assemble_only = False
    old_json = old_cfg.as_jsonable()
    dat_json = dat_cfg.as_jsonable()
    for snapshot in (old_json, dat_json):
        snapshot.pop("case_name")
        snapshot.pop("reporting_diffraction_order_max_m")
        snapshot.pop("reporting_diffraction_order_max_n")
    assert dat_json == old_json
    assert dat_cfg.reporting_diffraction_order_max_m == 2
    assert dat_cfg.reporting_diffraction_order_max_n == 2
    assert dat_cfg.diffraction_order_max_m is None
    assert dat_cfg.diffraction_order_max_n is None


def test_full3d_order_requests_are_preserved_but_not_injected_into_pde_cfg():
    first = _payload()
    second = deepcopy(first)
    second["output"]["diffraction_order_max_m"] = 99
    second["output"]["diffraction_order_max_n"] = 101
    captured = []

    def fake_solver(
        cfg, output_directory, *, canonical_vector_export, solution_observer
    ):
        captured.append((cfg, output_directory, canonical_vector_export))
        assert solution_observer is not None
        return _summary(canonical_root=output_directory)

    first_result = run_full3d_direct(
        first, "/tmp/task038-t4a", solver_runner=fake_solver
    )
    second_result = run_full3d_direct(
        second, "/tmp/task038-t4a-2", solver_runner=fake_solver
    )
    assert first_result["passed"] is True
    assert second_result["passed"] is True
    assert first["output"]["diffraction_order_max_m"] == 2
    assert second["output"]["diffraction_order_max_m"] == 99
    assert captured[0][0].diffraction_order_max_m is None
    assert captured[0][0].diffraction_order_max_n is None
    assert (
        captured[0][0].diffraction_order_max_m == captured[1][0].diffraction_order_max_m
    )
    assert captured[0][0].mesh_target_size == captured[1][0].mesh_target_size


def test_adapter_passes_exact_cfg_output_and_canonical_export(tmp_path):
    payload = _payload()
    seen = {}

    def fake_solver(
        cfg, output_directory, *, canonical_vector_export, solution_observer
    ):
        seen.update(
            cfg=cfg,
            output_directory=output_directory,
            canonical_vector_export=canonical_vector_export,
            solution_observer=solution_observer,
        )
        return _summary(canonical_root=output_directory)

    result = run_full3d_direct(payload, tmp_path, solver_runner=fake_solver)
    assert result["passed"] is True
    assert seen["output_directory"] == tmp_path.resolve() / "numerical_output"
    assert seen["canonical_vector_export"] is True
    assert seen["solution_observer"] is not None
    assert seen["cfg"].case_name == payload["model_id"]
    assert seen["cfg"].stage_case == "stage4_block_grating"


def test_v4_adapter_binds_packet_identity_and_run_relative_directory(tmp_path):
    payload = _payload(
        ROOT / "input/official/task039/5nm_p6h4_v4_1deg_full3d_direct_mpi8.dat"
    )
    seen = {}

    def fake_solver(cfg, output_directory, **kwargs):
        seen.update(cfg=cfg, output_directory=output_directory, kwargs=kwargs)
        return _summary(canonical_root=output_directory)

    result = run_full3d_direct(
        payload,
        tmp_path,
        source_sha="a" * 40,
        resolved_config_sha256="b" * 64,
        solver_runner=fake_solver,
    )
    assert result["passed"] is True
    assert seen["cfg"].direct_release_solver_before_postprocess is True
    packet_directory = seen["kwargs"]["pre_recovery_packet_directory"]
    assert (
        packet_directory
        == tmp_path.resolve() / "numerical_output" / "pre_recovery_packet"
    )
    identity = seen["kwargs"]["pre_recovery_packet_identity"]
    inventory = identity["external_mode_inventory"]
    assert identity["source_sha"] == "a" * 40
    assert identity["resolved_config_sha256"] == "b" * 64
    assert inventory["count"] == len(inventory["keys"])
    assert len({str(dict(key)) for key in inventory["keys"]}) == inventory["count"]


def test_canonical_observer_maps_reviewed_key_to_generic_full3d_key(
    monkeypatch, tmp_path
):
    import benchmarks.run_task033_full3d_watchdog as watchdog
    import src.runners.task038_full3d_direct as adapter

    roles = {
        "active_trace": {"manifest": "active", "manifest_sha256": "a" * 64},
        "full_fe": {"manifest": "full", "manifest_sha256": "b" * 64},
    }

    def fake_factory(_run_directory):
        def observe(**kwargs):
            kwargs["summary"]["task037_m3a_canonical_export"] = {
                "status": "completed",
                "roles": roles,
            }

        return observe

    monkeypatch.setattr(watchdog, "task037_m3a_solution_observer", fake_factory)
    summary = {}
    adapter._canonical_solution_observer(tmp_path)(summary=summary)
    assert summary["full3d_direct_canonical_export"]["roles"] == roles
    assert "task037_m3a_canonical_export" not in summary


def test_reviewed_observer_writes_original_summary_key_on_nonroot_rank(
    monkeypatch, tmp_path
):
    import benchmarks.run_task033_full3d_watchdog as watchdog

    roles = {"active_trace": {"manifest": "a"}, "full_fe": {"manifest": "b"}}
    monkeypatch.setattr(
        watchdog,
        "_task037_m3a_write_canonical_artifacts",
        lambda *_args, **_kwargs: roles,
    )
    observer = watchdog.task037_m3a_solution_observer(tmp_path)
    summary = {}
    observer(
        field=None,
        mesh_data=SimpleNamespace(mesh=SimpleNamespace(comm=SimpleNamespace(rank=1))),
        config=None,
        floquet_data=None,
        summary=summary,
        linear_system={},
        dtn_result={},
    )
    assert summary["task037_m3a_canonical_export"]["roles"] == roles


def test_canonical_summary_missing_full_fe_fails_closed(tmp_path):
    payload = _payload()

    def fake_solver(
        _cfg, output_directory, *, canonical_vector_export, solution_observer
    ):
        assert canonical_vector_export is True
        assert solution_observer is not None
        summary = _summary(canonical_root=output_directory)
        del summary["full3d_direct_canonical_export"]["roles"]["full_fe"]
        return summary

    result = run_full3d_direct(payload, tmp_path, solver_runner=fake_solver)
    assert result["passed"] is False
    assert any("roles" in error for error in result["errors"])


def test_canonical_false_keeps_legacy_solver_signature_and_summary(
    tmp_path,
):
    payload = _payload(SMOKE)
    seen = {}

    def fake_solver(_cfg, output_directory, *, canonical_vector_export):
        seen["canonical_vector_export"] = canonical_vector_export
        seen["output_directory"] = output_directory
        return _summary()

    result = run_full3d_direct(payload, tmp_path, solver_runner=fake_solver)
    assert result["passed"] is True
    assert seen["canonical_vector_export"] is False
    assert "full3d_direct_canonical_export" not in result["summary"]


@pytest.mark.parametrize(
    "updates",
    (
        {"case_status": "diagnostic_assemble_only"},
        {"official_result": False},
        {"linear_system_relative_residual": 1.0e-8},
        {"R_total": None},
        {"T_total": float("inf")},
        {"A_volume_total": None},
    ),
)
def test_adapter_rejects_non_authoritative_solver_summary(tmp_path, updates):
    payload = _payload()
    result = run_full3d_direct(
        payload,
        tmp_path,
        solver_runner=lambda *_args, **_kwargs: _summary(**updates),
    )
    assert result["passed"] is False
    assert result["errors"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("dimension", 2, "dimension=3"),
        ("method", {"kind": "hybrid_direct"}, "method.kind=full3d_direct"),
        ("solver", {"linear_solver": "fgmres"}, "linear_solver=direct"),
    ),
)
def test_adapter_rejects_wrong_method_identity(field, value, message, tmp_path):
    payload = _payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        run_full3d_direct(payload, tmp_path, solver_runner=lambda *_a, **_k: _summary())


def test_full3d_and_hybrid_direct_are_connected_and_other_methods_fail_closed():
    assert CONNECTED_METHODS == {
        "2d_scattered",
        "2d_port",
        "full3d_direct",
        "full3d_iterative",
        "hybrid_direct",
        "hybrid_iterative",
    }
    assert method_adapter_available("2d_scattered") is True
    assert method_adapter_available("2d_port") is True
    assert method_adapter_available("full3d_direct") is True
    assert method_adapter_available("full3d_iterative") is True
    assert method_adapter_available("hybrid_direct") is True
    assert method_adapter_available("hybrid_iterative") is True


def test_2d_still_rejects_the_3d_auto_cell_type(tmp_path):
    text = ORDINARY_2D.read_text(encoding="utf-8")
    text = text.replace('mesh_cell_type = "quadrilateral"', 'mesh_cell_type = "auto"')
    path = tmp_path / "bad_2d_auto.dat"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InputError, match="2D allows triangle or quadrilateral"):
        load_and_resolve(path)


@pytest.mark.parametrize("path", (OFFICIAL, SMOKE))
def test_official_and_smoke_inputs_are_strict_and_hash_stable(path):
    first = load_and_resolve(path)
    second = load_and_resolve(path)
    assert first.identity["dimension"] == 3
    assert first.method["kind"] == "full3d_direct"
    assert first.physical_model_sha256 == second.physical_model_sha256
    assert first.input_sha256 == second.input_sha256
    assert first.derived["internal"]["stage_case"] == "stage4_block_grating"


def test_worker_dispatch_uses_the_same_resolved_payload(monkeypatch, tmp_path):
    payload = _payload()
    received = []

    def fake_adapter(value, output_directory):
        received.append((value, output_directory))
        return {"passed": True, "errors": [], "summary": _summary()}

    import src.runners.task038_full3d_direct as adapter_module

    monkeypatch.setattr(adapter_module, "run_full3d_direct", fake_adapter)
    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="full3d_direct",
        output_directory=tmp_path,
    )
    assert status == 0
    assert errors == []
    assert received[0][0] is payload
    assert received[0][1] == tmp_path


def test_worker_dispatch_keeps_unconnected_methods_closed(tmp_path):
    status, errors = _dispatch_resolved_payload(
        _payload(), expected_method="not_a_public_method", output_directory=tmp_path
    )
    assert status == 3
    assert "unavailable" in errors[0]
