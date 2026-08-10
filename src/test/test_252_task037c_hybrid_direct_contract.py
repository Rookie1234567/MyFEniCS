from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks import run_task032_phase6_augmented as direct
from benchmarks import run_task037b_hybrid_iterative as iterative
from benchmarks import run_task033_memory_watchdog as memory_watchdog
from benchmarks.task037c_robustness import make_task37c_profile


SHA40 = "a" * 40


def _direct_argv(tmp_path: Path) -> list[str]:
    return [
        "--task037c-robustness-gate",
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "10",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "modal-schur-memory-minimal",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--incident-grazing-deg",
        "1",
        "--incident-phi-deg",
        "-5",
        "--polarization-kind",
        "s",
        "--full3d-reference",
        str(tmp_path / "full3d.json"),
        "--full3d-reference-sha256",
        "b" * 64,
        "--task035c-p6-preflight-authority",
        str(tmp_path / "p6.json"),
        "--task035c-p6-preflight-sha256",
        "c" * 64,
        "--verified-clean-sha",
        SHA40,
    ]


def _memory_task37c_argv(tmp_path: Path, phi: float) -> list[str]:
    return [
        "--target",
        "hybrid",
        "--case-label",
        "task037c_watchdog_test",
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "10",
        "--mpi-size",
        "8",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "modal-schur-memory-minimal",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--incident-grazing-deg",
        "1",
        "--incident-phi-deg",
        str(phi),
        "--full3d-reference",
        str(tmp_path / "full3d.json"),
        "--full3d-reference-sha256",
        "b" * 64,
        "--task037c-robustness-gate",
        "--task035c-p6-preflight-authority",
        str(tmp_path / "p6.json"),
        "--task035c-p6-preflight-sha256",
        "c" * 64,
        "--verified-clean-sha",
        SHA40,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
    ]


def test_task037c_status_and_raw_official_contract() -> None:
    assert (
        direct._task037c_record_status(
            enabled=True,
            qualification={"pass": True},
            legacy_status="legacy",
        )
        == "task037c_direct_robustness_pass"
    )
    assert (
        direct._task037c_record_status(
            enabled=True,
            qualification={"pass": False},
            legacy_status="legacy",
        )
        == "task037c_direct_robustness_failed"
    )
    raw_fields = direct._task037c_raw_qualification_fields({"pass": True})
    assert raw_fields["task037c_direct_pass"] is True
    assert raw_fields["official_record"] is False
    assert memory_watchdog._formal_shard_pass(
        return_code=0,
        numerical_pass=True,
        resource_gate_pass=True,
        source_gate_pass=True,
        launch_gate_pass=True,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
    )
    assert not memory_watchdog._formal_shard_pass(
        return_code=0,
        numerical_pass=True,
        resource_gate_pass=False,
        source_gate_pass=True,
        launch_gate_pass=True,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
    )


@pytest.mark.parametrize(
    "override",
    [
        ["--polarization-kind", "p"],
        ["--incident-grazing-deg", "2"],
        ["--incident-phi-deg", "7"],
        ["--requested-modes", "80", "--candidate-modes", "160"],
    ],
)
def test_task037c_direct_parser_rejects_out_of_scope_values(
    tmp_path: Path, override: list[str]
) -> None:
    with pytest.raises(SystemExit):
        direct._parse_args(_direct_argv(tmp_path) + override)


def test_task035c_keeps_phi_zero_and_task037c_requires_mpi8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_lane = _direct_argv(tmp_path)
    old_lane[old_lane.index("--task037c-robustness-gate")] = "--task035c-p6-h10-gate"
    old_lane[old_lane.index("--incident-grazing-deg") + 1] = "10"
    old_lane[old_lane.index("--incident-phi-deg") + 1] = "0"
    assert direct._parse_args(old_lane).task035c_p6_h10_gate is True
    old_lane[old_lane.index("--incident-phi-deg") + 1] = "5"
    with pytest.raises(SystemExit):
        direct._parse_args(old_lane)

    monkeypatch.setattr(
        direct,
        "MPI",
        SimpleNamespace(COMM_WORLD=SimpleNamespace(size=7)),
    )
    monkeypatch.setattr(
        direct,
        "_source_provenance",
        lambda *_args, **_kwargs: {
            "commit_sha": SHA40,
            "tracked_source_dirty": False,
        },
    )
    with pytest.raises(SystemExit, match="MPI8"):
        direct.main(_direct_argv(tmp_path))

    assert direct._parse_args(["--incident-phi-deg", "0"]).incident_phi_deg == 0.0
    with pytest.raises(SystemExit):
        direct._parse_args(["--incident-phi-deg", "5"])

    for phi in (-5.0, 5.0):
        parsed = memory_watchdog._parse_args(_memory_task37c_argv(tmp_path, phi))
        assert parsed.task037c_robustness_gate is True
        assert parsed.incident_phi_deg == phi

    with pytest.raises(SystemExit):
        memory_watchdog._parse_args(
            [
                "--target",
                "qep",
                "--case-label",
                "ordinary_watchdog",
                "--degree",
                "2",
                "--h-nm",
                "10",
                "--mpi-size",
                "1",
                "--incident-phi-deg",
                "5",
            ]
        )


def _write_full3d_reference(path: Path, *, phi: float) -> str:
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "run_kind": "full-solve",
        "status": "task037c_full3d_robustness_pass",
        "return_code": 0,
        "no_swap": True,
        "source": {
            "commit_sha": SHA40,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
        },
        "solver_summary": {
            "config": {
                "incident_theta_deg": 89.0,
                "incident_phi_deg": phi,
                "polarization_kind": "s",
                "nedelec_degree": 6,
                "mesh_target_size": 10.0,
            },
            "linear_system_relative_residual": 1.0e-10,
        },
        "qualification": {"pass": True, "failures": []},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return direct._sha256(path)


def test_task037c_full3d_hash_and_phi_identity_are_bound(tmp_path: Path) -> None:
    path = tmp_path / "full3d.json"
    digest = _write_full3d_reference(path, phi=5.0)
    passed = direct._task037c_full3d_reference_gate(
        path,
        expected_sha256=digest,
        current_source_sha=SHA40,
        phi_deg=5.0,
    )
    assert passed["pass"] is True
    assert (
        direct._task037c_full3d_reference_gate(
            path,
            expected_sha256="b" * 64,
            current_source_sha=SHA40,
            phi_deg=5.0,
        )["pass"]
        is False
    )
    assert (
        direct._task037c_full3d_reference_gate(
            path,
            expected_sha256=digest,
            current_source_sha=SHA40,
            phi_deg=-5.0,
        )["pass"]
        is False
    )


def test_task037c_capacity_negative_preserves_direct_failure_identity() -> None:
    fields = direct._task037c_capacity_failure_fields(
        enabled=True,
        incident_phi_deg=-5.0,
        authority_gate={"pass": True},
    )
    assert fields["status"] == "task037c_direct_robustness_failed"
    assert fields["case"]["incident_phi_deg"] == -5.0
    assert fields["metadata"]["task037c_authority_gate"]["pass"] is True
    assert fields["qualification"]["task037c_direct"] is None
    assert fields["qualification"]["task037c_direct_pass"] is False
    assert fields["qualification"]["official_record"] is False
    assert (
        direct._task037c_capacity_failure_fields(
            enabled=False,
            incident_phi_deg=0.0,
            authority_gate=None,
        )["status"]
        == "insufficient_finite_admissible_modes"
    )


def test_task037c_dynamic_side_counts_do_not_require_equal_dimensions() -> None:
    def mode(side: str, m: int, n: int) -> SimpleNamespace:
        return SimpleNamespace(side=side, m=m, n=n, polarization="s")

    bottom = SimpleNamespace(external_modes=[mode("bottom", 0, 0)])
    top = SimpleNamespace(external_modes=[mode("top", 0, 0), mode("top", 1, 0)])
    rows = [
        {
            "side": side,
            "m": m,
            "n": n,
            "polarization": "s",
            "beta_per_nm": 1.0 + 0.0j,
            "total_projection": 1.0 + 0.0j,
            "outgoing_amplitude": 1.0 + 0.0j,
            "power_ratio": 1.0,
        }
        for side, m, n in (
            ("bottom", 0, 0),
            ("top", 0, 0),
            ("top", 1, 0),
        )
    ]
    result = direct._task037c_direct_order_gate(rows, (bottom, top))
    assert result["pass"] is True
    assert result["expected_count"] == 3


def test_task037c_own_gate_is_separate_from_full3d_comparison() -> None:
    gates = {
        "condensed_full_operator_relative_residual_le_1e-9": True,
        "condensed_eliminated_interior_max_residual_le_1e-9": True,
        "assembled_interface_h_t_exact_dual_le_1e-8": True,
        "volume_energy_closure_abs_le_1e-5": True,
        "volume_absorption_full3d_abs_delta_le_1e-5": False,
        "middle_plane_e_relative_l2_le_5e-3": False,
        "middle_plane_h_relative_l2_le_5e-3": False,
    }
    validation = {
        "port_power": {"R_total": 0.1, "T_total": 0.8, "A_balance": 0.1},
        "interface_e_projection": {"combined_relative_residual": 1.0e-9},
    }
    physical_fields = {
        "volume_absorption": {
            "A_volume_total": 0.1,
            "energy_closure_error": 0.0,
        }
    }
    payload_keys = {
        "x_nm",
        "y_nm",
        "z_nm",
        "E_V_per_m",
        "H_A_per_m",
        "modal_amplitudes",
        "bottom_q",
        "top_q",
    }
    canonical = {
        side: {
            "roles": {
                "active_trace": {"pass": True},
                "full_fe": {"pass": True},
            }
        }
        for side in ("bottom", "top")
    }
    result = direct._task037c_direct_qualification(
        solution=SimpleNamespace(relative_residual=1.0e-10),
        validation=validation,
        physical_fields=physical_fields,
        gates=gates,
        q_identity={"bottom": {"pass": True}, "top": {"pass": True}},
        order_gate={"pass": True},
        payload={
            "keys": payload_keys,
            "arrays": {key: {"finite": True} for key in payload_keys},
        },
        canonical=canonical,
        authority_gate={"pass": True},
    )
    assert result["pass"] is True
    assert result["checks"]["inherited_direct_gates_pass"] is True
    assert result["full3d_comparison"]["pass"] == "not_run"
    assert result["full3d_comparison"]["available_partial_gates_pass"] is False
    gates["volume_energy_closure_abs_le_1e-5"] = False
    assert (
        direct._task037c_direct_qualification(
            solution=SimpleNamespace(relative_residual=1.0e-10),
            validation=validation,
            physical_fields=physical_fields,
            gates=gates,
            q_identity={"bottom": {"pass": True}, "top": {"pass": True}},
            order_gate={"pass": True},
            payload={
                "keys": payload_keys,
                "arrays": {key: {"finite": True} for key in payload_keys},
            },
            canonical=canonical,
            authority_gate={"pass": True},
        )["pass"]
        is False
    )


class _FakeVec:
    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.complex128).copy()
        self.destroyed = False

    def getOwnershipRange(self) -> tuple[int, int]:
        return 0, self.values.size

    def getArray(self, *, readonly: bool = False) -> np.ndarray:
        return self.values

    def copy(self, target: "_FakeVec") -> None:
        target.values[...] = self.values

    def axpy(self, coefficient: complex, other: "_FakeVec") -> None:
        self.values[...] += complex(coefficient) * other.values

    def destroy(self) -> None:
        self.destroyed = True


class _FakeComm:
    def tompi4py(self):
        return MPI.COMM_SELF


class _FakeMatrix:
    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.comm = _FakeComm()

    def createVecLeft(self) -> _FakeVec:
        return _FakeVec(np.zeros(self.matrix.shape[0], dtype=np.complex128))

    def getComm(self) -> _FakeComm:
        return self.comm

    def mult(self, source: _FakeVec, target: _FakeVec) -> None:
        target.values[...] = self.matrix @ source.values


def test_task037c_external_q_identity_is_partition_safe_and_fail_closed() -> None:
    matrix = _FakeMatrix(np.eye(4, dtype=np.complex128))
    solution = _FakeVec(np.array([1.0, 2.0, 3.0, 4.0]))
    exact = SimpleNamespace(
        A=matrix,
        b=_FakeVec(np.array([1.0, 2.0, 3.0, 4.0])),
        n_fe=2,
        n_external_aux=2,
    )
    assert direct._task037c_external_q_identity(exact, solution)["pass"] is True
    corrupted = SimpleNamespace(
        A=matrix,
        b=_FakeVec(np.array([1.0, 2.0, 0.0, 4.0])),
        n_fe=2,
        n_external_aux=2,
    )
    failed = direct._task037c_external_q_identity(corrupted, solution)
    assert failed["external_row_count"] == 2
    assert failed["pass"] is False


def test_task37c_online_record_setup_failure_is_not_a_second_exception() -> None:
    record = iterative.build_frozen_m10_online_record(
        case_label="task037c_setup_failure",
        source_before={},
        source_after={"clean": True, "matches_verified_clean_sha": True},
        authority_bindings={},
        lifecycle={"pass": False},
        profile=make_task37c_profile(0.0, 120, 8),
        setup=None,
        error="RuntimeError: setup failed",
    )
    assert record["cfg_audit"] == {"status": "not_run", "pass": False}
    assert record["mode_identity"]["status"] == "not_run"
    assert record["mode_identity"]["pass"] is False
    assert record["online_pass"] is False
    assert record["error"] == "RuntimeError: setup failed"
