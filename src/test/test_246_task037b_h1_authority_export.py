from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from benchmarks.run_task032_phase6_augmented import (
    _array_descriptor,
    _canonical_active_trace_view,
    _parse_args,
    _write_authority_grid_payload,
)
from benchmarks.run_task033_memory_watchdog import (
    _parse_args as _watchdog_parse_args,
    _worker_command,
)
from benchmarks.task037b_v4_full_qualification_checker import (
    _compare_to_significant_reference,
    _compare_order_maps,
    _load_significant_reference,
    _significant_reference_order_map,
    check_v4_evidence,
)
from src.test.test_243_task037b_v4_full_qualification import _write_bundle
from src.test.test_244_task037b_v5_multimetric_convergence import (
    _v5_parser_args,
    _watchdog_v4_v5_args,
)


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _h1_runner_args(*, export: bool) -> list[str]:
    args = _v5_parser_args()
    args[args.index("--task037b-v5-gate")] = "--task037b-h1-gate"
    solver_index = args.index("--solver-path") + 1
    args[solver_index] = "augmented"
    if export:
        args.append("--task037b-h1-authority-export")
    return args


def _h1_watchdog_args(*, export: bool) -> list[str]:
    args = _watchdog_v4_v5_args(v5=False)
    args.remove("--task037b-v4-gate")
    args[args.index("--solver-path") + 1] = "augmented"
    args.append("--task037b-h1-gate")
    if export:
        args.append("--task037b-h1-authority-export")
    return args


def _add_numeric_h1_payload(summary_path: Path) -> tuple[Path, dict[str, object]]:
    root = summary_path.parent
    candidate_path = root / "solver_record.json"
    solver_path = root / "h1_solver.json"
    candidate = json.loads(candidate_path.read_text())
    h1 = json.loads(solver_path.read_text())
    with np.load(root / "own_grid.npz", allow_pickle=False) as payload:
        arrays = {name: np.asarray(payload[name]) for name in payload.files}
    np.savez_compressed(
        root / "own_grid.npz",
        x_nm=np.linspace(0.0, 1.0, 40),
        y_nm=np.linspace(0.0, 1.0, 20),
        z_nm=np.array([10.0, 30.0, 60.0, 90.0, 110.0]),
        **arrays,
    )
    candidate["v4_telemetry"]["own_grid"]["sha256"] = _sha256(root / "own_grid.npz")
    candidate_path.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
    authority_grid = _write_authority_grid_payload(
        root / "h1_authority_grid.npz",
        sample_x=np.linspace(0.0, 1.0, 40),
        sample_y=np.linspace(0.0, 1.0, 20),
        sample_z=np.array([10.0, 30.0, 60.0, 90.0, 110.0]),
        electric=arrays["E_V_per_m"],
        magnetic=arrays["H_A_per_m"],
        modal=arrays["modal_amplitudes"],
        bottom_q=arrays["bottom_q"],
        top_q=arrays["top_q"],
        schema="task037b.h1-authority-grid-EH-modal-q.v1",
    )
    h1.setdefault("h1_telemetry", {}).update(
        {
            "own_grid": authority_grid,
            "canonical_export": candidate["v4_telemetry"]["canonical_export"],
        }
    )
    solver_path.write_text(json.dumps(h1, sort_keys=True), encoding="utf-8")
    summary = json.loads(summary_path.read_text())
    summary["v4_artifacts"]["solver_record_sha256"] = _sha256(candidate_path)
    summary["v4_authorities"]["h1_direct"]["sha256"] = _sha256(solver_path)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    return solver_path, h1


def test_h1_export_flag_is_opt_in_and_worker_forwards_once() -> None:
    invalid = _h1_runner_args(export=False)
    invalid.remove("--task037b-h1-gate")
    invalid.append("--task037b-h1-authority-export")
    with pytest.raises(SystemExit):
        _parse_args(invalid)
    parsed = _parse_args(_h1_runner_args(export=True))
    assert parsed.task037b_h1_gate is True
    assert parsed.task037b_h1_authority_export is True
    ordinary = _parse_args(_h1_runner_args(export=False))
    assert ordinary.task037b_h1_authority_export is False

    watchdog = _watchdog_parse_args(_h1_watchdog_args(export=True))
    command = _worker_command(
        watchdog,
        Path("/tmp/h1-record.json"),
        Path("/tmp/h1-stages.jsonl"),
    )
    assert command.count("--task037b-h1-gate") == 1
    assert command.count("--task037b-h1-authority-export") == 1
    ordinary_command = _worker_command(
        _watchdog_parse_args(_h1_watchdog_args(export=False)),
        Path("/tmp/h1-record.json"),
        Path("/tmp/h1-stages.jsonl"),
    )
    assert "--task037b-h1-authority-export" not in ordinary_command


def test_h1_numeric_grid_writer_roundtrip(tmp_path: Path) -> None:
    arrays = {
        "E_V_per_m": np.ones((5, 20, 40, 3), dtype=np.complex128),
        "H_A_per_m": np.ones((5, 20, 40, 3), dtype=np.complex128) * (1.0 + 1.0j),
        "modal_amplitudes": np.ones(240, dtype=np.complex128),
        "bottom_q": np.ones(40, dtype=np.complex128),
        "top_q": np.ones(40, dtype=np.complex128) * (2.0 + 0.0j),
    }
    path = tmp_path / "h1_grid.npz"
    metadata = _write_authority_grid_payload(
        path,
        sample_x=np.arange(40, dtype=float),
        sample_y=np.arange(20, dtype=float),
        sample_z=np.array([10.0, 30.0, 60.0, 90.0, 110.0]),
        electric=arrays["E_V_per_m"],
        magnetic=arrays["H_A_per_m"],
        modal=arrays["modal_amplitudes"],
        bottom_q=arrays["bottom_q"],
        top_q=arrays["top_q"],
        schema="task037b.h1-authority-grid-EH-modal-q.v1",
    )
    assert metadata["schema"] == "task037b.h1-authority-grid-EH-modal-q.v1"
    assert metadata["arrays"]["modal_amplitudes"]["shape"] == [240]
    assert metadata["sha256"] == _sha256(path)
    with np.load(path, allow_pickle=False) as payload:
        for name, expected in arrays.items():
            assert payload[name].dtype == np.dtype("complex128")
            np.testing.assert_array_equal(payload[name], expected)
        modal_bytes = np.ascontiguousarray(payload["modal_amplitudes"]).tobytes()
        modal_descriptor = metadata["arrays"]["modal_amplitudes"]
        assert modal_descriptor["dtype"] == "complex128"
        assert modal_descriptor["bytes"] == payload["modal_amplitudes"].nbytes
        assert modal_descriptor["sha256"] == hashlib.sha256(modal_bytes).hexdigest()


def test_canonical_active_trace_view_preserves_prefix_and_lifecycle() -> None:
    comm = PETSc.COMM_WORLD
    mpi = comm.tompi4py()
    size = int(mpi.Get_size())
    rank = int(mpi.Get_rank())
    local_active = 4
    active_rows = local_active * size
    appended_rows = 2
    condensed = SimpleNamespace(
        active_rows=active_rows,
        appended_rows=appended_rows,
    )

    local_source = local_active + (appended_rows if rank == size - 1 else 0)
    source = PETSc.Vec().createMPI(
        (local_source, active_rows + appended_rows),
        comm=comm,
    )
    first, last = map(int, source.getOwnershipRange())
    source.getArray()[:] = np.arange(first, last, dtype=np.complex128)
    source.assemble()
    before = np.array(source.getArray(readonly=True), copy=True)
    with _canonical_active_trace_view(source, condensed) as active:
        assert int(active.getSize()) == active_rows
        assert int(
            active.getOwnershipRange()[1] - active.getOwnershipRange()[0]
        ) == len(active.getArray(readonly=True))
        gathered = mpi.allgather(np.array(active.getArray(readonly=True), copy=True))
        assert np.array_equal(
            np.concatenate(gathered), np.arange(active_rows, dtype=np.complex128)
        )
    np.testing.assert_array_equal(source.getArray(readonly=True), before)
    source.destroy()

    exact = PETSc.Vec().createMPI((local_active, active_rows), comm=comm)
    first, last = map(int, exact.getOwnershipRange())
    exact.getArray()[:] = np.arange(first, last, dtype=np.complex128) + 1.0j
    exact.assemble()
    with _canonical_active_trace_view(exact, condensed) as active:
        assert active is exact
        assert int(active.getSize()) == active_rows
    exact.destroy()


def test_checker_compares_numeric_h1_payload_and_keeps_candidate_read_only(
    tmp_path: Path,
) -> None:
    summary_path = _write_bundle(tmp_path / "complete")
    solver_path, _h1 = _add_numeric_h1_payload(summary_path)
    candidate_path = summary_path.parent / "solver_record.json"
    candidate = json.loads(candidate_path.read_text())
    candidate["validation"]["A_volume"].pop("R_plus_T_plus_A_volume")
    candidate["validation"]["energy_closure"] = {
        "R_plus_T_plus_A_volume": 1.0,
    }
    candidate_path.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
    summary = json.loads(summary_path.read_text())
    summary["v4_artifacts"]["solver_record_sha256"] = _sha256(candidate_path)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    before = json.loads((summary_path.parent / "solver_record.json").read_text())
    result = check_v4_evidence(summary_path)
    after = json.loads((summary_path.parent / "solver_record.json").read_text())
    assert result["authority_payload_gap"] is False
    assert result["evidence_integrity_pass"] is True
    assert result["comparisons"]["q"]["status"] == "pass"
    assert result["comparisons"]["twelve_plus_twelve"]["status"] == "pass"
    assert (
        result["comparisons"]["modal"]["status"]
        == "diagnostic_not_comparable_independent_qep_gauge"
    )
    assert result["comparisons"]["modal"]["qualification_pass"] is True
    assert result["comparisons"]["selected_fields"]["status"] == "pass"
    assert result["comparisons"]["canonical"]["status"] == "pass"
    assert result["comparisons"]["energy"]["status"] == "pass"
    assert (
        result["comparisons"]["energy"]["fields"]["R_plus_T_plus_A_volume"][
            "absolute_difference"
        ]
        == 0.0
    )
    full3d_dimensions = result["comparisons"]["iterative_vs_full3d"]["dimensions"]
    assert (
        full3d_dimensions["twelve_plus_twelve_powers_amplitudes"]["status"]
        == result["comparisons"]["significant_reference"]["status"]
    )
    assert full3d_dimensions["modal"]["status"] == "not_available"
    assert full3d_dimensions["canonical"]["status"] == "not_available"
    assert full3d_dimensions["selected_interface_fields"]["status"] == ("not_available")
    assert full3d_dimensions["selected_middle_fields"]["status"] == ("not_available")
    assert solver_path.is_file()
    assert before == after


def test_checker_recomputes_numeric_difference_after_hash_bound_modal_tamper(
    tmp_path: Path,
) -> None:
    summary_path = _write_bundle(tmp_path / "numeric_tamper")
    solver_path, h1 = _add_numeric_h1_payload(summary_path)
    grid_path = Path(h1["h1_telemetry"]["own_grid"]["path"])
    with np.load(grid_path, allow_pickle=False) as payload:
        arrays = {name: np.asarray(payload[name]) for name in payload.files}
    arrays["modal_amplitudes"] = arrays["modal_amplitudes"].copy()
    arrays["modal_amplitudes"][0] += 0.25 + 0.5j
    np.savez_compressed(grid_path, **arrays)
    h1["h1_telemetry"]["own_grid"]["sha256"] = _sha256(grid_path)
    h1["h1_telemetry"]["own_grid"]["arrays"]["modal_amplitudes"] = _array_descriptor(
        arrays["modal_amplitudes"]
    )
    solver_path.write_text(json.dumps(h1, sort_keys=True), encoding="utf-8")
    summary = json.loads(summary_path.read_text())
    summary["v4_authorities"]["h1_direct"]["sha256"] = _sha256(solver_path)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["evidence_integrity_pass"] is True
    assert result["authority_payload_gap"] is False
    assert (
        result["comparisons"]["modal"]["status"]
        == "diagnostic_not_comparable_independent_qep_gauge"
    )
    assert result["comparisons"]["modal"]["relative_l2_error"] > 1.0e-5
    assert result["comparisons"]["modal"]["qualification_pass"] is True
    assert result["pass"] is False
    assert result["fail_closed"] is True


def test_order_coverage_without_numeric_agreement_is_not_pass() -> None:
    left = {}
    right = {}
    for index in range(80):
        key = ("bottom" if index < 40 else "top", index, 0, "s")
        row = {
            "power_ratio": 1.0,
            "outgoing_amplitude_at_boundary": [1.0, 0.0],
        }
        left[key] = row
        right[key] = copy.deepcopy(row)
    right[("top", 40, 0, "s")]["power_ratio"] = 10.0

    result = _compare_order_maps(left, right)
    assert result["all_order_coverage"] is True
    assert result["key_and_finite_coverage_pass"] is True
    assert result["numeric_pass"] is False
    assert result["status"] == "fail"


def test_order_below_floor_is_coverage_diagnostic_only() -> None:
    left = {}
    right = {}
    for index in range(80):
        key = ("bottom" if index < 40 else "top", index, 0, "s")
        power = 1.0 if index < 12 else 1.0e-12
        row = {
            "power_ratio": power,
            "outgoing_amplitude_at_boundary": [1.0, 0.0],
        }
        left[key] = row
        right[key] = copy.deepcopy(row)
        if index == 12:
            right[key]["power_ratio"] = 2.0e-12
            right[key]["outgoing_amplitude_at_boundary"] = [3.0, 4.0]

    result = _compare_order_maps(left, right)
    assert result["status"] == "pass"
    assert result["all_order_coverage"] is True
    assert result["significant_numeric_comparison"]["pass"] is True
    assert result["significant_count"] == 12
    assert result["below_floor_count"] == 68
    below_floor_row = next(
        row for row in result["rows"] if row["key"] == list(("bottom", 12, 0, "s"))
    )
    assert below_floor_row["diagnostic_pass"] is False


def test_hash_bound_significant_reference_maps_frozen_full3d_channels() -> None:
    root = Path(__file__).resolve().parents[2]
    reference = _load_significant_reference(
        root / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
        "significant_channel_reference_v1.json",
        "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3",
    )
    frozen_orders = _significant_reference_order_map(reference)
    comparison = _compare_to_significant_reference(
        frozen_orders, frozen_orders, reference
    )
    assert len(frozen_orders) == 12
    assert comparison["analytic_identity_pass_count"] == 12
    assert comparison["pass"] is True


def test_checker_field_tamper_fails_physical_modal_qualification(
    tmp_path: Path,
) -> None:
    summary_path = _write_bundle(tmp_path / "field_tamper")
    solver_path, h1 = _add_numeric_h1_payload(summary_path)
    grid_path = Path(h1["h1_telemetry"]["own_grid"]["path"])
    with np.load(grid_path, allow_pickle=False) as payload:
        arrays = {name: np.asarray(payload[name]) for name in payload.files}
    arrays["E_V_per_m"] = arrays["E_V_per_m"].copy()
    arrays["E_V_per_m"][0, 0, 0, 0] = 1.0 + 1.0j
    np.savez_compressed(grid_path, **arrays)
    h1["h1_telemetry"]["own_grid"]["sha256"] = _sha256(grid_path)
    h1["h1_telemetry"]["own_grid"]["arrays"]["E_V_per_m"] = _array_descriptor(
        arrays["E_V_per_m"]
    )
    solver_path.write_text(json.dumps(h1, sort_keys=True), encoding="utf-8")
    summary = json.loads(summary_path.read_text())
    summary["v4_authorities"]["h1_direct"]["sha256"] = _sha256(solver_path)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["comparisons"]["selected_fields"]["status"] == "fail"
    assert result["comparisons"]["modal"]["qualification_pass"] is False
    assert result["pass"] is False


@pytest.mark.parametrize("missing", ("modal", "selected", "canonical"))
def test_checker_rejects_incomplete_h1_numeric_payload(
    tmp_path: Path, missing: str
) -> None:
    summary_path = _write_bundle(tmp_path / missing)
    solver_path, h1 = _add_numeric_h1_payload(summary_path)
    tampered = copy.deepcopy(h1)
    if missing == "modal":
        tampered["h1_telemetry"]["own_grid"]["arrays"]["modal_amplitudes"]["sha256"] = (
            "0" * 64
        )
    elif missing == "selected":
        tampered["h1_telemetry"]["own_grid"]["arrays"]["E_V_per_m"]["sha256"] = "0" * 64
    else:
        tampered["h1_telemetry"]["canonical_export"] = {}
    solver_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
    summary = json.loads(summary_path.read_text())
    summary["v4_authorities"]["h1_direct"]["sha256"] = _sha256(solver_path)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["authority_payload_gap"] is True
    assert result["pass"] is False
