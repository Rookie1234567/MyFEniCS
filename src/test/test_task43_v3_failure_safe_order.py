from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    write_v3_primary_before_extra_packet,
    write_v3_primary_field_sample,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_a1_persists_primary_and_each_sample_before_same_lu_extra():
    source = (_ROOT / "benchmarks/task43_hp_adaptivity/h100_anchor.py").read_text(
        encoding="utf-8"
    )
    observer = source.split("    def active_observer(view) -> None:", 1)[1].split(
        '    _log_stage(comm, started, "solve_and_observe", "begin")', 1
    )[0]
    packet = observer.index('run_root / "primary_before_extra.npz"')
    first_sample = observer.index("capture_primary_fields(capture_v3_samples=True)")
    aggregate_sample = observer.index("primary_q8_q10_samples")
    extra = observer.index("_same_lu_tightening(")
    assert packet < first_sample < aggregate_sample < extra
    assert "primary_before_extra_q{int(order)}_samples.npz" in source
    assert "task43_v3_partial_terminal_record" in source


def test_normal_correction_vectors_are_copied_on_both_sides_of_existing_correction():
    source = (_ROOT / "src/solvers/dtn_port_3d.py").read_text(encoding="utf-8")
    implementation = source.split("def _solve_stage4_dtn_port_total_field_impl(", 1)[1]
    implementation = implementation.split("def solve_stage4_dtn_port_total_field(", 1)[
        0
    ]
    before = implementation.index('snapshot("before_normal_correction")')
    correct = implementation.index("single_petsc_residual_correction_in_place(")
    after = implementation.index('snapshot("after_normal_correction")')
    assert before < correct < after
    assert "variable_p_capture_normal_correction_vectors" in implementation


def test_partial_terminal_and_endpoint_failure_have_no_continuation_path():
    source = (_ROOT / "benchmarks/task43_hp_adaptivity/h100_anchor.py").read_text(
        encoding="utf-8"
    )
    assert '"same_group_R": False' in source
    assert '"A1_R": False' in source
    assert '"A2_R": False' in source
    assert '"B": False' in source
    assert '"C": False' in source


def test_v3_residual_gates_use_returned_and_transformed_scopes_for_primary_and_extra():
    from benchmarks.task43_hp_adaptivity import h100_anchor

    primary = h100_anchor._v3_residual_scope_gates(
        {"linear_system_relative_residual": 5.0e-9},
        {"linear_system_relative_residual": 5.0e-9},
    )
    # The legacy endpoint's mislabeled explicit <= 1e-8 condition would pass
    # 5e-9.  V3's correctly scoped returned-system <= 1e-9 condition must fail.
    legacy_limit = 1.0e-8
    legacy_explicit_gate_passes = 5.0e-9 <= legacy_limit
    assert legacy_explicit_gate_passes
    assert primary == {
        "returned_trace_dtn_condensed_relative_le_1e-9": False,
        "block_gaussian_full_transformed_relative_le_1e-8": True,
    }
    before = h100_anchor._v3_residual_scope_gates(
        {"linear_system_relative_residual": 5.0e-10},
        {"linear_system_relative_residual": 5.0e-9},
    )
    after_extra = h100_anchor._v3_residual_scope_gates(
        {"linear_system_relative_residual": 5.0e-9},
        {"linear_system_relative_residual": 5.0e-9},
    )
    assert all(before.values())
    assert not all(after_extra.values())


def test_v3_packet_shape_check_preserves_recovered_storage_identity_shapes():
    from benchmarks.task43_hp_adaptivity.h100_anchor import (
        _validate_v3_primary_packet_arrays,
    )

    packet_arrays = {
        "recovered_mesh_geometry_coordinates_nm": np.zeros((308, 3)),
        "recovered_mesh_geometry_dofmap": np.zeros((180, 8), dtype=np.int64),
        "recovered_p6_function_space_dofmap": np.zeros((180, 882), dtype=np.int64),
        "returned_trace_dtn_b_minus_Ax": np.zeros(612, dtype=np.complex128),
    }
    raw_vector_keys = {"returned_trace_dtn_b_minus_Ax"}
    _validate_v3_primary_packet_arrays(packet_arrays, raw_vector_keys)
    assert packet_arrays["recovered_mesh_geometry_coordinates_nm"].shape == (
        308,
        3,
    )
    assert packet_arrays["recovered_mesh_geometry_dofmap"].shape == (180, 8)
    assert packet_arrays["recovered_p6_function_space_dofmap"].shape == (180, 882)

    packet_arrays["returned_trace_dtn_b_minus_Ax"] = np.zeros(
        (612, 1), dtype=np.complex128
    )
    with pytest.raises(ValueError, match="one-dimensional"):
        _validate_v3_primary_packet_arrays(packet_arrays, raw_vector_keys)


@pytest.mark.parametrize("sample_role", ["primary", "extra"])
def test_native_a2_field_sample_callback_preserves_q8_before_q10_failure(
    tmp_path, monkeypatch, sample_role
):
    import src.postprocessing.physical_field_comparison as field_comparison
    import src.postprocessing.physical_field_sampling as field_sampling
    from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
        write_atomic_npz,
        write_v3_extra_before_output_packet,
        write_v3_primary_before_extra_packet,
    )
    from src.runners import p6_condensed_direct

    inputs = {}
    for key in ("q8", "q10"):
        path = tmp_path / f"{key}_reference.npz"
        np.savez_compressed(
            path,
            points_nm=np.asarray([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]),
            weights_nm3=np.asarray([0.5, 0.5]),
        )
        inputs[key] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "points_key": "points_nm",
            "weights_key": "weights_nm3",
        }
    export = SimpleNamespace(electric_dgq6=object(), curl_electric_dgq6=object())
    monkeypatch.setattr(
        field_sampling,
        "prepare_cell_local_vector_field_export",
        lambda _field: export,
    )
    calls = {"count": 0}

    def sample_fields(_fields, points):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("injected q10 sampler failure")
        return {
            "E_total": np.ones((len(points), 3), dtype=np.complex128),
            "curl_E_total": np.full((len(points), 3), 2.0 + 0.5j),
        }

    monkeypatch.setattr(
        field_sampling, "sample_cell_local_vector_fields", sample_fields
    )
    monkeypatch.setattr(
        field_comparison,
        "magnetic_field_from_electric_curl",
        lambda curl, **_kwargs: np.asarray(curl, dtype=np.complex128) * 3.0,
    )
    primary_packet = None
    extra_packet = None
    primary_packet_sha256 = None
    if sample_role == "extra":
        primary_packet = write_v3_primary_before_extra_packet(
            tmp_path / "primary_before_extra.npz",
            {
                "primary_solution": np.asarray([1.0 + 0.5j, 2.0 - 1.0j]),
                "primary_returned_trace_dtn_rhs": np.ones(2, dtype=np.complex128),
                "primary_native_A6_effective_rhs": np.ones(2, dtype=np.complex128),
                "primary_independent_A6_residual": np.full(2, 1.0e-11 + 0j),
                "primary_zero_slave_carrier_residual": np.full(
                    2, 1.0e-10 + 0j
                ),
                "primary_augmented_port_residual": np.asarray([1.0e-11 + 0j]),
            },
            identity={"phase": "A2_q", "attempt": 3},
        )
        primary_packet_sha256 = hashlib.sha256(
            Path(primary_packet["npz_path"]).read_bytes()
        ).hexdigest()
        common_rhs = np.ones(2, dtype=np.complex128)
        extra_condensed_residual = np.asarray([1.0e-12 + 0j, 2.0e-12 + 0j])
        extra_a6_residual = np.asarray([1.0e-11 + 0j, 1.0e-11 + 0j])
        extra_carrier_residual = np.asarray([1.2e-10 + 0j, 1.2e-10 + 0j])
        extra_port_residual = np.asarray([1.0e-11 + 0j])
        extra_condensed_relative = float(
            np.linalg.norm(extra_condensed_residual) / np.linalg.norm(common_rhs)
        )
        extra_a6_relative = float(
            np.linalg.norm(extra_a6_residual) / np.linalg.norm(common_rhs)
        )
        extra_full_active_relative = float(
            np.hypot(
                np.linalg.norm(extra_carrier_residual),
                np.linalg.norm(extra_port_residual),
            )
            / np.linalg.norm(common_rhs)
        )
        extra_packet = write_v3_extra_before_output_packet(
            tmp_path / "extra_before_output.npz",
            {
                "extra_recovered_p6_storage": np.asarray(
                    [1.0 + 0.5j, 2.0 - 1.0j]
                ),
                "extra_condensed_solution": np.asarray(
                    [1.0 + 0.5j, 2.0 - 1.0j]
                ),
                "extra_condensed_b_minus_Ax": extra_condensed_residual,
                "extra_condensed_rhs": common_rhs.copy(),
                "primary_condensed_rhs": common_rhs.copy(),
                "extra_independent_A6_residual": extra_a6_residual,
                "extra_native_A6_effective_rhs": common_rhs.copy(),
                "primary_native_A6_effective_rhs": common_rhs.copy(),
                "extra_zero_slave_carrier_residual": extra_carrier_residual,
                "extra_augmented_port_residual": extra_port_residual,
            },
            identity={
                "phase": "A2_q",
                "attempt": 3,
                "primary_before_extra_packet_sha256": primary_packet["npz_sha256"],
                "same_condensed_rhs_as_primary": True,
                "same_native_effective_rhs_as_primary": True,
                "factor_counts": {
                    "initial_factor_solve_calls": 2,
                    "final_factor_solve_calls": 3,
                    "exactly_one_extra_solve": True,
                    "factorization_calls_unchanged": True,
                },
                "residual_metrics": {
                    "extra_condensed_b_minus_Ax_relative": extra_condensed_relative,
                    "extra_independent_A6_relative": extra_a6_relative,
                    "extra_full_active_transformed_relative": extra_full_active_relative,
                    "extra_full_active_strict_decrease": False,
                    "extra_status": "FAIL_UNCONTROLLED_EXTRA_CORRECTION",
                },
            },
        )
    primary_samples = {}

    def persist(order, sample):
        primary_samples[f"q{order}"] = write_atomic_npz(
            tmp_path / f"{sample_role}_q{order}.npz",
            sample,
            schema=f"task43.v3.a2_{sample_role}_field_sample.v1",
            classification=f"measured_{sample_role}_sample_not_official",
            identity={
                "phase": "A2_q",
                "attempt": 3,
                "sample_role": sample_role,
                "quadrature_order": order,
            },
        )

    cfg = SimpleNamespace(
        magnetic_field_scale_A_per_m=1.0,
        k0=1.0,
        mu_r=1.0,
    )
    with pytest.raises(RuntimeError, match="injected q10 sampler failure"):
        p6_condensed_direct._task43_v2_capture_fixed_field_samples(
            SimpleNamespace(),
            cfg,
            {"field_reference_samples": inputs},
            sample_callback=persist,
        )
    assert "q8" in primary_samples
    assert "q10" not in primary_samples
    q8_path = Path(primary_samples["q8"]["npz_path"])
    assert (
        hashlib.sha256(q8_path.read_bytes()).hexdigest()
        == primary_samples["q8"]["npz_sha256"]
    )
    with np.load(q8_path, allow_pickle=False) as saved:
        assert saved["points_nm"].shape == (2, 3)
        assert saved["E_total_code"].shape == (2, 3)
        assert saved["H_total_A_per_m"].shape == (2, 3)
    assert not (tmp_path / f"{sample_role}_q10.npz").exists()
    assert q8_path != q8_path.with_name(f"{sample_role}_q10.npz")
    if extra_packet is not None:
        from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
            demote_v3_native_summary_after_error,
        )

        terminal_path = tmp_path / "task43_v3_partial_terminal.json"
        summary = {
            "source_sha": "d" * 40,
            "status": "SOLVER_MEASURED",
            "passed": True,
            "official_result": {"R_total": 0.25},
        }
        demote_v3_native_summary_after_error(
            summary,
            terminal_path,
            phase="A2_q",
            source_identity={"source_sha": "d" * 40},
            error=RuntimeError("injected q10 sampler failure"),
            primary_before_extra_packet=primary_packet,
            primary_q_samples={},
            extra_q_samples=primary_samples,
            extra_before_output_packet=extra_packet,
        )
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        assert terminal["extra_before_output_packet"]["npz_sha256"] == extra_packet[
            "npz_sha256"
        ]
        assert terminal["extra_q_samples"]["q8"]["npz_sha256"] == primary_samples[
            "q8"
        ]["npz_sha256"]
        assert hashlib.sha256(Path(extra_packet["npz_path"]).read_bytes()).hexdigest() == (
            extra_packet["npz_sha256"]
        )
        assert hashlib.sha256(
            Path(primary_packet["npz_path"]).read_bytes()
        ).hexdigest() == primary_packet_sha256
        with np.load(extra_packet["npz_path"], allow_pickle=False) as saved:
            condensed_relative = float(
                np.linalg.norm(saved["extra_condensed_b_minus_Ax"])
                / np.linalg.norm(saved["extra_condensed_rhs"])
            )
            a6_relative = float(
                np.linalg.norm(saved["extra_independent_A6_residual"])
                / np.linalg.norm(saved["extra_native_A6_effective_rhs"])
            )
            full_active_relative = float(
                np.hypot(
                    np.linalg.norm(saved["extra_zero_slave_carrier_residual"]),
                    np.linalg.norm(saved["extra_augmented_port_residual"]),
                )
                / np.linalg.norm(saved["extra_native_A6_effective_rhs"])
            )
            assert np.array_equal(
                saved["primary_condensed_rhs"], saved["extra_condensed_rhs"]
            )
            saved_record = json.loads(saved["__task43_record_json__"].tobytes())
            saved_metrics = saved_record["identity"]["residual_metrics"]
        assert condensed_relative == pytest.approx(
            saved_metrics["extra_condensed_b_minus_Ax_relative"],
            rel=1.0e-12,
            abs=0.0,
        )
        assert a6_relative == pytest.approx(
            saved_metrics["extra_independent_A6_relative"],
            rel=1.0e-12,
            abs=0.0,
        )
        assert full_active_relative == pytest.approx(
            saved_metrics["extra_full_active_transformed_relative"],
            rel=1.0e-12,
            abs=0.0,
        )
        assert a6_relative < 1.0e-8
        assert full_active_relative < 1.0e-8
        assert saved_metrics["extra_full_active_strict_decrease"] is False
        assert saved_metrics["extra_status"] == (
            "FAIL_UNCONTROLLED_EXTRA_CORRECTION"
        )


def test_a2_extra_raw_packet_precedes_output_recovery_sampling_and_failure_paths():
    source = (_ROOT / "src/runners/p6_condensed_direct.py").read_text(
        encoding="utf-8"
    )
    extra_start = source.index("extra_native_facts = action.evaluate_native_residual(")
    full_active = source.index(
        "extra_active_explicit_facts = _task43_v2_active_explicit_residual_facts(",
        extra_start,
    )
    recovered = source.index("extra_recovered = np.asarray(", full_active)
    packet = source.index("v3_extra_packet_record = write_v3_extra_before_output_packet(", recovered)
    extra_field = source.index("extra_saved_field = create_vector(", packet)
    physical_output = source.index(
        "extra_output_facts = recover_p0_outputs(", extra_field
    )
    field_restore = source.index(
        'name="Task43_A2_extra_lu_field_for_fixed_samples"', physical_output
    )
    sample = source.index(
        "extra_samples = _task43_v2_capture_fixed_field_samples(", field_restore
    )
    assert extra_start < full_active < recovered < packet < extra_field
    assert packet < physical_output < field_restore < sample
    failure_handler = source.split("except BaseException as exc:", 1)[-1]
    assert "extra_before_output_packet=v3_extra_packet_record" in failure_handler


@pytest.mark.parametrize("failure_point", ["extra_field_recovery", "collective_transport"])
def test_a2_extra_packet_survives_post_packet_recovery_or_transport_failure(
    tmp_path, failure_point
):
    from mpi4py import MPI

    from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
        demote_v3_native_summary_after_error,
        write_v3_extra_before_output_packet,
        write_v3_primary_before_extra_packet,
    )

    primary = write_v3_primary_before_extra_packet(
        tmp_path / "primary.npz",
        {
            "primary_returned_trace_dtn_rhs": np.asarray(
                [1.0 + 0j, 2.0 + 0j]
            ),
            "primary_native_A6_effective_rhs": np.asarray(
                [1.0 + 0j, 2.0 + 0j]
            ),
            "primary_independent_A6_residual": np.asarray(
                [1.0e-11 + 0j, 1.0e-11 + 0j]
            ),
            "primary_zero_slave_carrier_residual": np.asarray(
                [1.0e-10 + 0j, 1.0e-10 + 0j]
            ),
            "primary_augmented_port_residual": np.asarray([1.0e-11 + 0j]),
        },
        identity={"phase": "A2_q", "attempt": 3},
    )
    same_rhs = np.asarray([1.0 + 0j, 2.0 + 0j])
    extra_arrays = {
        "extra_condensed_solution": np.asarray([0.5 + 0.2j, 1.5 - 0.1j]),
        "extra_condensed_b_minus_Ax": np.asarray(
            [2.0e-12 + 0j, 1.0e-12 + 0j]
        ),
        "extra_condensed_rhs": same_rhs.copy(),
        "primary_condensed_rhs": same_rhs.copy(),
        "extra_independent_A6_residual": np.asarray(
            [1.0e-11 + 0j, 1.0e-11 + 0j]
        ),
        "extra_native_A6_effective_rhs": same_rhs.copy(),
        "primary_native_A6_effective_rhs": same_rhs.copy(),
        "extra_zero_slave_carrier_residual": np.asarray(
            [1.2e-10 + 0j, 1.2e-10 + 0j]
        ),
        "extra_augmented_port_residual": np.asarray([1.0e-11 + 0j]),
    }
    condensed_relative = float(
        np.linalg.norm(extra_arrays["extra_condensed_b_minus_Ax"])
        / np.linalg.norm(extra_arrays["extra_condensed_rhs"])
    )
    a6_relative = float(
        np.linalg.norm(extra_arrays["extra_independent_A6_residual"])
        / np.linalg.norm(extra_arrays["extra_native_A6_effective_rhs"])
    )
    full_active_relative = float(
        np.hypot(
            np.linalg.norm(extra_arrays["extra_zero_slave_carrier_residual"]),
            np.linalg.norm(extra_arrays["extra_augmented_port_residual"]),
        )
        / np.linalg.norm(extra_arrays["extra_native_A6_effective_rhs"])
    )
    assert condensed_relative < 1.0e-9
    assert a6_relative < 1.0e-8
    assert full_active_relative < 1.0e-8
    primary_bytes = Path(primary["npz_path"]).read_bytes()
    primary_sha256 = hashlib.sha256(primary_bytes).hexdigest()
    extra_identity = {
        "phase": "A2_q",
        "attempt": 3,
        "primary_before_extra_packet_sha256": primary["npz_sha256"],
        "same_condensed_rhs_as_primary": True,
        "same_native_effective_rhs_as_primary": True,
        "factor_counts": {
            "extra_correction_count": 1,
            "factorization_calls_unchanged": True,
        },
        "residual_metrics": {
            "extra_condensed_b_minus_Ax_relative": condensed_relative,
            "extra_independent_A6_relative": a6_relative,
            "extra_full_active_transformed_relative": full_active_relative,
            "extra_full_active_strict_decrease": False,
            "extra_status": "FAIL_UNCONTROLLED_EXTRA_CORRECTION",
        },
    }
    extra = write_v3_extra_before_output_packet(
        tmp_path / "extra_before_output.npz",
        extra_arrays,
        identity=extra_identity,
    )
    saved_bytes = Path(extra["npz_path"]).read_bytes()
    failure = None
    try:
        if failure_point == "extra_field_recovery":
            raise RuntimeError("injected extra field recovery failure")
        received = MPI.COMM_WORLD.bcast(extra, root=0)
        assert received["npz_sha256"] == extra["npz_sha256"]
        raise RuntimeError("injected post-packet transport failure")
    except RuntimeError as exc:
        failure = exc

    summary = {"source_sha": "e" * 40, "status": "SOLVER_MEASURED", "passed": True}
    terminal_path = tmp_path / "task43_v3_partial_terminal.json"
    demote_v3_native_summary_after_error(
        summary,
        terminal_path,
        phase="A2_q",
        source_identity={"source_sha": "e" * 40},
        error=failure,
        primary_before_extra_packet=primary,
        primary_q_samples={},
        extra_before_output_packet=extra,
    )
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["extra_before_output_packet"]["npz_sha256"] == extra[
        "npz_sha256"
    ]
    assert Path(extra["npz_path"]).read_bytes() == saved_bytes
    assert hashlib.sha256(Path(primary["npz_path"]).read_bytes()).hexdigest() == (
        primary_sha256
    )
    with np.load(extra["npz_path"], allow_pickle=False) as saved:
        recomputed_condensed = float(
            np.linalg.norm(saved["extra_condensed_b_minus_Ax"])
            / np.linalg.norm(saved["extra_condensed_rhs"])
        )
        recomputed_a6 = float(
            np.linalg.norm(saved["extra_independent_A6_residual"])
            / np.linalg.norm(saved["extra_native_A6_effective_rhs"])
        )
        recomputed_full_active = float(
            np.hypot(
                np.linalg.norm(saved["extra_zero_slave_carrier_residual"]),
                np.linalg.norm(saved["extra_augmented_port_residual"]),
            )
            / np.linalg.norm(saved["extra_native_A6_effective_rhs"])
        )
        assert np.array_equal(
            saved["primary_condensed_rhs"],
            saved["extra_condensed_rhs"],
        )
        assert np.array_equal(
            saved["primary_native_A6_effective_rhs"],
            saved["extra_native_A6_effective_rhs"],
        )
        saved_record = json.loads(saved["__task43_record_json__"].tobytes())
        saved_metrics = saved_record["identity"]["residual_metrics"]
    assert recomputed_condensed == pytest.approx(
        saved_metrics["extra_condensed_b_minus_Ax_relative"],
        rel=1.0e-12,
        abs=0.0,
    )
    assert recomputed_a6 == pytest.approx(
        saved_metrics["extra_independent_A6_relative"],
        rel=1.0e-12,
        abs=0.0,
    )
    assert recomputed_full_active == pytest.approx(
        saved_metrics["extra_full_active_transformed_relative"],
        rel=1.0e-12,
        abs=0.0,
    )
    assert saved_metrics["extra_full_active_strict_decrease"] is False
    assert saved_metrics["extra_status"] == (
        "FAIL_UNCONTROLLED_EXTRA_CORRECTION"
    )
    assert terminal["continuation_all_false"] is True


@pytest.mark.parametrize("failure_stage", ["comparison", "record_write"])
def test_a2_adapter_postprocess_exception_demotes_native_result(
    tmp_path, failure_stage
):
    from benchmarks.task43_hp_adaptivity.a2_native_p6_diagnostic import (
        _task43_v3_postprocess_fail_closed,
    )
    from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
        write_atomic_bytes,
        write_atomic_json,
        write_atomic_npz,
    )

    run_dir = tmp_path / "run"
    numerical = run_dir / "numerical_output"
    numerical.mkdir(parents=True)
    q8 = write_atomic_npz(
        numerical / "primary_q8.npz",
        {"E_total_code": np.ones((2, 3), dtype=np.complex128)},
        schema="task43.v3.a2_primary_field_sample.v1",
        classification="measured_primary_sample_before_extra_not_official",
        identity={"phase": "A2_q", "attempt": 3, "quadrature_order": 8},
    )
    packet = write_atomic_npz(
        numerical / "primary_before_extra.npz",
        {"primary_independent_A6_residual": np.asarray([1.0e-12 + 0j])},
        schema="task43.v3.a2_primary_before_extra.v1",
        classification="measured_primary_state_before_extra_not_official",
        identity={"phase": "A2_q", "attempt": 3},
    )
    primary_bytes_before_failure = Path(packet["npz_path"]).read_bytes()
    primary_sha256_before_failure = hashlib.sha256(
        primary_bytes_before_failure
    ).hexdigest()
    summary_path = run_dir / "p6_condensed_direct_summary.json"
    original_summary = {
        "source_sha": "a" * 40,
        "status": "A2_Q_COMPLETED_AUTHORITY_LIMITED",
        "passed": True,
        "official_result": {"port_metrics": {"R_total": 0.25}},
        "task43_v3_diagnostic_identity": {
            "contract_sha256": "b" * 64,
            "plan_sha256": "c" * 64,
        },
        "task43_v3_primary_before_extra_packet": packet,
        "task43_v3_primary_field_samples": {"q8": q8},
        "task43_v3_endpoint_authority": {
            "official_result": True,
            "passed": True,
            "continuation_all_false": False,
        },
        "task43_v2_comparison": {
            "endpoint_qualified": True,
            "same_group_R_factor_may_continue": True,
            "max_power_delta": 2.5e-8,
        },
    }
    write_atomic_json(summary_path, original_summary)
    comparison_path = run_dir / "comparison_record.json"
    original_comparison_bytes = (
        b'{\n  "endpoint_qualified": true,\n'
        b'  "official_result": true,\n'
        b'  "same_group_R_factor_may_continue": true,\n'
        b'  "primary_perturbation_gate": {"max_power_delta": 2.5e-8},\n'
        b'  "measured_R_total": 0.25000001\n}\n'
    )

    def failed_postprocess():
        write_atomic_bytes(comparison_path, original_comparison_bytes)
        if failure_stage == "record_write":
            # An interrupted adapter write may leave invalid JSON. The failure
            # guard must use its pre-callback snapshot, not reread this file.
            summary_path.write_text('{"partial":', encoding="utf-8")
            raise OSError("injected V3 adapter record failure")
        raise OSError("injected V3 comparison failure")

    expected_message = (
        "injected V3 adapter record failure"
        if failure_stage == "record_write"
        else "injected V3 comparison failure"
    )
    with pytest.raises(OSError, match=expected_message):
        _task43_v3_postprocess_fail_closed(
            failed_postprocess,
            summary_path=summary_path,
            run_directory=run_dir,
            phase="A2_q",
            comparison_path=comparison_path,
        )
    demoted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert demoted["official_result"] is False
    assert demoted["passed"] is False
    assert demoted["continuation_all_false"] is True
    assert demoted["selection_eligible"] is False
    assert demoted["task43_v2_comparison"]["endpoint_qualified"] is False
    assert demoted["task43_v2_comparison"]["same_group_R_factor_may_continue"] is False
    assert demoted["task43_v3_endpoint_authority"]["official_result"] is False
    assert demoted["task43_v3_endpoint_authority"]["passed"] is False
    assert demoted["task43_v3_comparison_failure_reference"]["sha256"] == hashlib.sha256(
        original_comparison_bytes
    ).hexdigest()
    assert demoted["task43_v3_postprocess_failure"]["exception_type"] == "OSError"
    assert demoted["task43_v3_postprocess_failure"]["exception_message"] == expected_message
    assert demoted["task43_v2_comparison"]["max_power_delta"] == 2.5e-8
    assert (
        demoted["measured_endpoint_output_not_official"]["port_metrics"]["R_total"]
        == 0.25
    )
    terminal = json.loads(
        (numerical / "task43_v3_partial_terminal.json").read_text(encoding="utf-8")
    )
    assert terminal["status"] == "FAILED"
    assert terminal["primary_before_extra_packet"]["npz_sha256"] == packet["npz_sha256"]
    assert hashlib.sha256(Path(packet["npz_path"]).read_bytes()).hexdigest() == (
        primary_sha256_before_failure
    )
    assert terminal["primary_q_samples"]["q8"]["npz_sha256"] == q8["npz_sha256"]
    assert terminal["continuation_all_false"] is True
    assert terminal["error"] == expected_message
    sidecar_ref = terminal["comparison_failure_reference"]
    sidecar = Path(sidecar_ref["path"])
    assert sidecar.read_bytes() == original_comparison_bytes
    assert hashlib.sha256(sidecar.read_bytes()).hexdigest() == sidecar_ref["sha256"]
    current_comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert current_comparison["endpoint_qualified"] is False
    assert current_comparison["same_group_R_factor_may_continue"] is False
    original_record_path = Path(current_comparison["original_record_path"])
    assert original_record_path.read_bytes() == original_comparison_bytes
    assert hashlib.sha256(original_record_path.read_bytes()).hexdigest() == (
        current_comparison["original_record_sha256"]
    )
    assert current_comparison["measured_R_total"] == 0.25000001
    assert current_comparison["original_record_sha256"] == sidecar_ref["sha256"]
    assert (
        demoted["task43_v2_comparison"]["sha256"]
        == hashlib.sha256(comparison_path.read_bytes()).hexdigest()
    )
    assert demoted["task43_v3_postprocess_failure"]["exception_type"] == "OSError"
    assert demoted["task43_v2_comparison"]["endpoint_qualified_before_failure"] is True


def _write_synthetic_joint_authority_files(
    root: Path,
    *,
    summary_path: Path | None = None,
    comparison_path: Path | None = None,
    primary_path: Path | None = None,
    terminal_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Create coherent files for a test-only, non-scientific joint-read rule."""

    root.mkdir(parents=True, exist_ok=True)
    primary_path = primary_path or root / "primary_fixture.npz"
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    source_sha = "a" * 40
    identity = {"contract_sha256": "b" * 64, "plan_sha256": "c" * 64}
    primary_ref = write_v3_primary_before_extra_packet(
        primary_path,
        {"primary_solution": np.asarray([0.25 + 0.5j], dtype=np.complex128)},
        identity={"source_sha": source_sha, **identity},
    )
    comparison_path = comparison_path or root / "comparison.json"
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison = {
        "status": "COMPLETED",
        "official_result": True,
        "passed": True,
        "endpoint_qualified": True,
        "authority": "FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION",
        "measured_R_total": 0.25000001,
        "source_sha": source_sha,
        "frozen_v3_contract_sha256": identity["contract_sha256"],
        "frozen_v3_plan_sha256": identity["plan_sha256"],
    }
    comparison_path.write_text(json.dumps(comparison, sort_keys=True), encoding="utf-8")
    comparison_ref = {
        "path": str(comparison_path),
        "sha256": hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
    }
    summary_path = summary_path or root / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "COMPLETED",
        "official_result": True,
        "passed": True,
        "authority": "FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION",
        "measured_R_total": 0.25000001,
        "source_sha": source_sha,
        "task43_v3_diagnostic_identity": identity,
        "task43_v3_primary_before_extra_packet": primary_ref,
        "task43_v2_comparison": {
            **comparison_ref,
            "endpoint_qualified": True,
            "official_result": True,
            "passed": True,
            "authority": "FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION",
        },
        "task43_v3_endpoint_authority": {"official_result": True, "passed": True},
    }
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    terminal_path = terminal_path or root / "terminal.json"
    terminal_path.parent.mkdir(parents=True, exist_ok=True)
    terminal = {
        "status": "COMPLETED",
        "official_result": True,
        "passed": True,
        "source_identity": {
            "source_sha": source_sha,
            "frozen_v3_contract_sha256": identity["contract_sha256"],
            "frozen_v3_plan_sha256": identity["plan_sha256"],
        },
        "primary_before_extra_packet": primary_ref,
    }
    terminal_path.write_text(json.dumps(terminal, sort_keys=True), encoding="utf-8")
    summary["task43_v3_partial_terminal"] = {
        "path": str(terminal_path),
        "sha256": hashlib.sha256(terminal_path.read_bytes()).hexdigest(),
    }
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    return summary_path, comparison_path, terminal_path


def _synthetic_joint_read_has_no_engineering_veto(
    summary_path: Path,
    terminal_path: Path,
    *,
    process_exit_code: int | None,
) -> bool:
    """Test-only file rule; a true result is not scientific qualification."""

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        comparison_ref = summary["task43_v2_comparison"]
        comparison_path = Path(comparison_ref["path"])
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        primary_ref = summary["task43_v3_primary_before_extra_packet"]
        terminal_primary_ref = terminal["primary_before_extra_packet"]
        primary_path = Path(primary_ref["npz_path"])
        actual_comparison_sha = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
        actual_primary_sha = hashlib.sha256(primary_path.read_bytes()).hexdigest()
        with np.load(primary_path, allow_pickle=False) as primary_npz:
            primary_record = json.loads(
                primary_npz["__task43_record_json__"].tobytes()
            )
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False

    identity = summary.get("task43_v3_diagnostic_identity")
    summary_comparison = summary.get("task43_v2_comparison", {})
    source_identity = {
        "source_sha": summary.get("source_sha"),
        "frozen_v3_contract_sha256": (
            identity.get("contract_sha256") if isinstance(identity, dict) else None
        ),
        "frozen_v3_plan_sha256": (
            identity.get("plan_sha256") if isinstance(identity, dict) else None
        ),
    }
    return bool(
        process_exit_code == 0
        and summary.get("status") == "COMPLETED"
        and terminal.get("status") == "COMPLETED"
        and terminal.get("official_result") is True
        and terminal.get("passed") is True
        and summary.get("task43_v3_endpoint_authority")
        == {"official_result": True, "passed": True}
        and summary.get("official_result") is True
        and summary.get("passed") is True
        and summary.get("authority") == "FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION"
        and summary.get("task43_v2_comparison", {}).get("endpoint_qualified") is True
        and summary.get("task43_v2_comparison", {}).get("official_result") is True
        and summary.get("task43_v2_comparison", {}).get("passed") is True
        and summary.get("task43_v2_comparison", {}).get("authority")
        == "FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION"
        and comparison.get("status") == "COMPLETED"
        and comparison.get("official_result") is True
        and comparison.get("passed") is True
        and comparison.get("endpoint_qualified") is True
        and comparison.get("authority") == "FIXTURE_ONLY_NO_SCIENTIFIC_QUALIFICATION"
        and comparison_ref.get("sha256") == actual_comparison_sha
        and summary_comparison.get("path") == str(comparison_path)
        and summary_comparison.get("sha256") == actual_comparison_sha
        and terminal.get("source_identity") == source_identity
        and summary.get("task43_v3_partial_terminal", {}).get("path")
        == str(terminal_path)
        and summary.get("task43_v3_partial_terminal", {}).get("sha256")
        == hashlib.sha256(terminal_path.read_bytes()).hexdigest()
        and terminal_primary_ref == primary_ref
        and primary_ref.get("npz_sha256") == actual_primary_sha
        and primary_record.get("identity") == primary_ref.get("identity")
        and primary_record.get("identity", {}).get("source_sha")
        == summary.get("source_sha")
        and primary_record.get("identity", {}).get("contract_sha256")
        == source_identity["frozen_v3_contract_sha256"]
        and primary_record.get("identity", {}).get("plan_sha256")
        == source_identity["frozen_v3_plan_sha256"]
        and comparison.get("source_sha") == summary.get("source_sha")
        and comparison.get("frozen_v3_contract_sha256")
        == source_identity["frozen_v3_contract_sha256"]
        and comparison.get("frozen_v3_plan_sha256")
        == source_identity["frozen_v3_plan_sha256"]
    )


def test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle(
    tmp_path: Path,
) -> None:
    summary_path, _comparison_path, terminal_path = _write_synthetic_joint_authority_files(
        tmp_path / "joint"
    )

    assert _synthetic_joint_read_has_no_engineering_veto(
        summary_path, terminal_path, process_exit_code=0
    )


@pytest.mark.parametrize(
    "defect",
    (
        "failed_terminal",
        "nonzero_exit",
        "unknown_exit",
        "summary_demotion",
        "summary_status_demotion",
        "summary_authority_demotion",
        "comparison_demotion",
        "terminal_demotion",
        "missing_comparison_file",
        "missing_binding",
        "wrong_hash",
        "source_identity_mismatch",
    ),
)
def test_synthetic_joint_authority_fixture_rejects_each_failure_independently(
    tmp_path: Path, defect: str
) -> None:
    summary_path, comparison_path, terminal_path = _write_synthetic_joint_authority_files(
        tmp_path / defect
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    process_exit_code: int | None = 0

    if defect == "failed_terminal":
        terminal["status"] = "FAILED"
    elif defect == "nonzero_exit":
        process_exit_code = 1
    elif defect == "unknown_exit":
        process_exit_code = None
    elif defect == "summary_demotion":
        summary["task43_v3_endpoint_authority"]["official_result"] = False
    elif defect == "summary_status_demotion":
        summary["status"] = "FAILED"
    elif defect == "summary_authority_demotion":
        summary["authority"] = "DIAGNOSTIC_ONLY_PARTIAL_NONOFFICIAL"
    elif defect == "comparison_demotion":
        comparison["endpoint_qualified"] = False
    elif defect == "terminal_demotion":
        terminal["official_result"] = False
    elif defect == "missing_comparison_file":
        comparison_path.unlink()
    elif defect == "missing_binding":
        summary.pop("task43_v2_comparison")
    elif defect == "wrong_hash":
        summary["task43_v2_comparison"]["sha256"] = "f" * 64
    elif defect == "source_identity_mismatch":
        comparison["source_sha"] = "c" * 40

    if defect not in {"missing_comparison_file"}:
        comparison_path.write_text(json.dumps(comparison, sort_keys=True), encoding="utf-8")
    if defect == "comparison_demotion" or defect == "source_identity_mismatch":
        summary["task43_v2_comparison"]["sha256"] = hashlib.sha256(
            comparison_path.read_bytes()
        ).hexdigest()
    if defect in {"failed_terminal", "terminal_demotion"}:
        summary["task43_v3_partial_terminal"]["sha256"] = hashlib.sha256(
            json.dumps(terminal, sort_keys=True).encode()
        ).hexdigest()
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    terminal_path.write_text(json.dumps(terminal, sort_keys=True), encoding="utf-8")

    assert not _synthetic_joint_read_has_no_engineering_veto(
        summary_path,
        terminal_path,
        process_exit_code=process_exit_code,
    )


@pytest.mark.parametrize(
    "writer_failure", ("sidecar", "comparison_demotion", "summary_demotion")
)
def test_a2_postprocess_writer_failures_keep_original_error_and_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    writer_failure: str,
) -> None:
    from benchmarks.task43_hp_adaptivity import candidate_checkpoints
    from benchmarks.task43_hp_adaptivity.a2_native_p6_diagnostic import (
        _task43_v3_postprocess_fail_closed,
    )

    run_directory = tmp_path / "writer_failure"
    numerical = run_directory / "numerical_output"
    numerical.mkdir(parents=True)
    summary_path = run_directory / "p6_condensed_direct_summary.json"
    comparison_path = run_directory / "comparison_record.json"
    summary_path, comparison_path, terminal_path = _write_synthetic_joint_authority_files(
        run_directory / "fixture_root",
        summary_path=summary_path,
        comparison_path=comparison_path,
        primary_path=numerical / "primary_before_extra.npz",
        terminal_path=numerical / "task43_v3_partial_terminal.json",
    )
    assert _synthetic_joint_read_has_no_engineering_veto(
        summary_path, terminal_path, process_exit_code=0
    )
    synthetic_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    primary = synthetic_summary["task43_v3_primary_before_extra_packet"]
    primary_path = Path(primary["npz_path"])
    primary_bytes = primary_path.read_bytes()
    primary_sha = hashlib.sha256(primary_bytes).hexdigest()
    original_summary_bytes = summary_path.read_bytes()
    original_comparison = comparison_path.read_bytes()
    original_sha = hashlib.sha256(original_comparison).hexdigest()
    sidecar_path = comparison_path.with_name(
        f"{comparison_path.name}.pre_failure.{original_sha}.json"
    )
    callback_error = OSError("original adapter failure remains authoritative")
    writer_error = OSError(f"injected {writer_failure} write failure")

    # A prior terminal would correctly refuse overwrite. Remove only the
    # synthetic control terminal so the production failure writer can create
    # this run's terminal after the baseline joint read has passed.
    terminal_path.unlink()

    real_write_atomic_bytes = candidate_checkpoints.write_atomic_bytes
    real_write_atomic_json = candidate_checkpoints.write_atomic_json

    def injected_write_atomic_bytes(path, payload, **kwargs):
        if writer_failure == "sidecar" and Path(path) == sidecar_path:
            raise writer_error
        return real_write_atomic_bytes(path, payload, **kwargs)

    def injected_write_atomic_json(path, record, **kwargs):
        path = Path(path)
        if writer_failure == "comparison_demotion" and path == comparison_path:
            raise writer_error
        if writer_failure == "summary_demotion" and path == summary_path:
            raise writer_error
        return real_write_atomic_json(path, record, **kwargs)

    monkeypatch.setattr(candidate_checkpoints, "write_atomic_bytes", injected_write_atomic_bytes)
    monkeypatch.setattr(candidate_checkpoints, "write_atomic_json", injected_write_atomic_json)

    def fail_callback():
        raise callback_error

    with pytest.raises(OSError) as raised:
        _task43_v3_postprocess_fail_closed(
            fail_callback,
            summary_path=summary_path,
            run_directory=run_directory,
            phase="A2_q",
            comparison_path=comparison_path,
        )
    assert raised.value is callback_error
    captured = capsys.readouterr()
    if writer_failure == "summary_demotion":
        assert "could not persist its fail-closed summary" in captured.err
    else:
        assert "failure-record warnings" in captured.err
        assert str(writer_error) in captured.err

    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "FAILED"
    assert terminal["official_result"] is False
    assert terminal["error"] == str(callback_error)
    assert primary_path.read_bytes() == primary_bytes
    assert hashlib.sha256(primary_path.read_bytes()).hexdigest() == primary_sha
    assert not _synthetic_joint_read_has_no_engineering_veto(
        summary_path, terminal_path, process_exit_code=1
    )
    assert not _synthetic_joint_read_has_no_engineering_veto(
        summary_path, terminal_path, process_exit_code=0
    )
    assert json.loads(comparison_path.read_text(encoding="utf-8"))[
        "measured_R_total"
    ] == 0.25000001
    if writer_failure == "sidecar":
        assert not sidecar_path.exists()
        assert comparison_path.read_bytes() == original_comparison
    elif writer_failure == "comparison_demotion":
        assert sidecar_path.read_bytes() == original_comparison
        assert hashlib.sha256(sidecar_path.read_bytes()).hexdigest() == original_sha
        assert comparison_path.read_bytes() == original_comparison
    else:
        assert sidecar_path.read_bytes() == original_comparison
        assert json.loads(comparison_path.read_text(encoding="utf-8"))[
            "endpoint_qualified"
        ] is False
        # The failed atomic summary replacement leaves its prior bytes intact;
        # the terminal and current comparison remain independent denial records.
        assert summary_path.read_bytes() == original_summary_bytes


def test_a2_adapter_guard_wraps_full_postprocess_callback():
    source = (_ROOT / "benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py").read_text(
        encoding="utf-8"
    )
    main = source.split("def main(", 1)[1].split('\n\nif __name__', 1)[0]
    callback = main.split("    def postprocess_native_result()", 1)[1].split(
        "\n    if v3_diagnostic is not None:\n        return _task43_v3_postprocess_fail_closed(",
        1,
    )[0]
    assert "write_postprocess_json(summary_path, runner_summary)" in callback
    assert "comparison_callback()" in callback
    assert "write_postprocess_json(comparison_path, comparison)" in callback
    assert "write_atomic_json(path, record, refuse_overwrite=False)" in callback
    assert "_task43_v3_postprocess_fail_closed(" in main
    assert "postprocess_native_result," in main


def test_v3_a2_entry_rechecks_review_ancestry_and_actual_attempt_terminals(
    tmp_path, monkeypatch
):
    from benchmarks.task43_hp_adaptivity import a2_native_p6_diagnostic as adapter

    repository = tmp_path / "repo"
    review = repository / "docs/task43_hp_adaptivity/review_report_v2.md"
    review.parent.mkdir(parents=True)
    review.write_text("frozen review fixture\n", encoding="utf-8")
    terminal_hashes = []
    for attempt in (1, 2):
        attempt_root = (
            repository
            / f"benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt{attempt}"
        )
        watchdog = attempt_root / "watchdog"
        watchdog.mkdir(parents=True)
        summary_path = watchdog / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "classification": "WORKER_FAILED",
                    "leader_exit_code": 1,
                    "descendants_cleared": True,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (attempt_root / "launcher_exit_code.txt").write_text("2\n", encoding="utf-8")
        terminal_hashes.append(hashlib.sha256(summary_path.read_bytes()).hexdigest())
    immutable = {
        "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json": adapter._CONTRACT_SHA256,
        "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_a2_native_contract.json": adapter._A2_NATIVE_CONTRACT_SHA256,
        "docs/task43_hp_adaptivity/review_report_v2.md": hashlib.sha256(
            review.read_bytes()
        ).hexdigest(),
    }
    contract = {
        "schema": "task43.v3.finite_diagnostic_contract.v1",
        "status": "frozen_for_execution",
        "authority": {
            "review_commit": "fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12",
            "review_path": "docs/task43_hp_adaptivity/review_report_v2.md",
            "execution_section": "10",
        },
        "immutable_prior_contracts_and_review": immutable,
        "formal_model_attempts": {
            "total_original_max": 6,
            "already_consumed": 3,
            "new_dispatches_max": 2,
            "A1_cumulative_max_this_review": 2,
            "A2_cumulative_max_this_review": 3,
            "cumulative_max_after_this_review": 5,
            "sealed_remaining_unallocated": 1,
            "no_automatic_retry": True,
        },
        "phases": {
            "A2": [
                {
                    "id": "A2_q",
                    "attempt": 3,
                    "new_dispatches_max": 1,
                    "operator_q": 19,
                    "incident_port_q": 32,
                    "modal_rectangle": "R13",
                    "normal_corrections_max": 2,
                    "extra_corrections_max": 1,
                    "old_attempt_terminal_hashes": terminal_hashes,
                }
            ],
            "A1_R": {"authorized": False},
            "A2_R": {"authorized": False},
            "B": {"authorized": False},
            "C": {"authorized": False},
        },
        "prohibited": ["A1_R", "A2_R", "B", "C"],
    }
    monkeypatch.setattr(adapter, "_REPO_ROOT", repository)
    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    adapter._validate_v3_a2_entry_contract(contract, phase="A2_q", attempt=3)

    bad_review = json.loads(json.dumps(contract))
    bad_review["authority"]["review_commit"] = "0" * 40
    with pytest.raises(ValueError, match="allocation|continuation|review"):
        adapter._validate_v3_a2_entry_contract(bad_review, phase="A2_q", attempt=3)

    bad_terminal = json.loads(json.dumps(contract))
    bad_terminal["phases"]["A2"][0]["old_attempt_terminal_hashes"][0] = "0" * 64
    with pytest.raises(ValueError, match="terminal/launcher"):
        adapter._validate_v3_a2_entry_contract(bad_terminal, phase="A2_q", attempt=3)

    with pytest.raises(ValueError, match="A2_q attempt-3"):
        adapter._validate_v3_a2_entry_contract(contract, phase="A2_q", attempt=2)


def test_v3_a1_contract_and_consumed_attempts_use_frozen_phase_schema(
    tmp_path
):
    from benchmarks.task43_hp_adaptivity import h100_anchor

    contract_path = (
        _ROOT
        / "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    h100_anchor._validate_v3_a1_entry_contract(contract)
    assert hashlib.sha256(contract_path.read_bytes()).hexdigest() == (
        h100_anchor._V3_CONTRACT_SHA256
    )

    for entry in contract["formal_model_attempts"]["consumed_attempts"]:
        attempt_root = tmp_path / entry["attempt_root"]
        watchdog = attempt_root / "watchdog"
        watchdog.mkdir(parents=True)
        summary = {
            "classification": entry["classification"],
            "leader_exit_code": entry["worker_exit"],
            "descendants_cleared": entry["descendants_cleared"],
        }
        summary_path = watchdog / "summary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        entry["watchdog_summary_sha256"] = hashlib.sha256(
            summary_path.read_bytes()
        ).hexdigest()
        launcher = attempt_root / "launcher_exit_code.txt"
        launcher.write_text(f"{entry['launcher_exit']}\n", encoding="utf-8")

    h100_anchor._validate_v3_consumed_formal_attempts(contract, tmp_path)
    contract["phases"]["B"]["authorized"] = True
    with pytest.raises(ValueError, match="frozen allocation"):
        h100_anchor._validate_v3_a1_entry_contract(contract)


@pytest.mark.parametrize("route", ["a1", "a2"])
def test_v3_worker_requires_direct_watchdog_parent_and_absolute_phase(
    monkeypatch, tmp_path, route
):
    from benchmarks.task43_hp_adaptivity import a2_native_p6_diagnostic, h100_anchor

    module = h100_anchor if route == "a1" else a2_native_p6_diagnostic
    phase_path = tmp_path / "watchdog" / "workflow_phase.json"
    phase_path.parent.mkdir(parents=True)
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PARENT_PID", "74001")
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(phase_path))
    monkeypatch.setattr(module.os, "getppid", lambda: 74001)
    identity = module._require_v3_watchdog_worker_identity()
    assert identity["worker_parent_pid"] == 74001
    assert identity["watchdog_parent_pid_environment"] == 74001
    assert identity["direct_watchdog_parent_verified"] is True
    assert identity["phase_path"] == str(phase_path)

    monkeypatch.setattr(module.os, "getppid", lambda: 74002)
    with pytest.raises(RuntimeError, match="direct child"):
        module._require_v3_watchdog_worker_identity()

    monkeypatch.setattr(module.os, "getppid", lambda: 74001)
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", "relative/phase.json")
    with pytest.raises(RuntimeError, match="absolute"):
        module._require_v3_watchdog_worker_identity()


@pytest.mark.parametrize("sample_role", ["primary", "extra"])
def test_real_field_capture_callback_persists_q8_and_demotes_after_q10_failure(
    tmp_path, monkeypatch, sample_role
):
    from benchmarks.task43_hp_adaptivity import h100_anchor
    from benchmarks.task43_hp_adaptivity.candidate_checkpoints import write_atomic_npz

    run_root = tmp_path / "A1_q"
    run_root.mkdir()
    packet_path = run_root / "primary_before_extra.npz"
    packet_arrays = {
        "normal_before_residual": np.asarray([1.0 + 0.5j, -0.25j]),
        "normal_after_residual": np.asarray([0.01 + 0.0j, -0.02j]),
        "returned_trace_dtn_rhs": np.asarray([1.0 + 2.0j]),
        "returned_trace_dtn_solution": np.asarray([0.5 - 0.25j]),
        "returned_trace_dtn_b_minus_Ax": np.asarray([0.001 + 0.002j]),
        "full_active_active_full_rhs": np.asarray([1.0 + 2.0j, 0.5 + 0.25j]),
        "full_active_eliminated_active_interior_residual": np.asarray(
            [0.0 + 0.0j, 1.0e-10 + 0.0j]
        ),
        "independent_A6_independent_active_residual_trace": np.asarray(
            [1.0e-11 + 1.0e-12j]
        ),
        "independent_A6_independent_active_residual_cell_interior": np.asarray(
            [1.0e-12 - 1.0e-13j]
        ),
        "independent_A6_independent_active_modal_lower_raw_original_equation": (
            np.asarray([1.0e-13 + 0.0j])
        ),
    }
    packet = write_v3_primary_before_extra_packet(
        packet_path,
        packet_arrays,
        identity=MappingProxyType(
            {
                "phase": "A1_q",
                "returned_trace_dtn_system_scope": "reduced trace/DtN system",
                "normal_correction_count": 1,
                "full_active_residual_scope": MappingProxyType(
                    {
                        "scope": "block-Gaussian transformed residual",
                        "relative": np.float64(1.0e-12),
                    }
                ),
            }
        ),
    )
    transported_packet = h100_anchor.MPI.COMM_WORLD.bcast(packet, root=0)
    assert transported_packet["npz_sha256"] == packet["npz_sha256"]
    assert transported_packet["identity"]["full_active_residual_scope"] == {
        "scope": "block-Gaussian transformed residual",
        "relative": 1.0e-12,
    }
    with np.load(packet_path, allow_pickle=False) as saved_packet:
        embedded = json.loads(
            bytes(saved_packet["__task43_record_json__"].tolist()).decode("utf-8")
        )
    assert embedded["identity"] == transported_packet["identity"]
    readonly_diagnostic = MappingProxyType(
        {
            "nested": MappingProxyType(
                {
                    "residual": np.asarray([1.0e-12 + 2.0e-12j]),
                    "normal_correction_count": np.int64(1),
                }
            )
        }
    )
    transported_diagnostic = h100_anchor.MPI.COMM_WORLD.bcast(
        h100_anchor._plain_nested_containers(readonly_diagnostic), root=0
    )
    diagnostic_json = json.loads(
        json.dumps(transported_diagnostic, default=h100_anchor._json_default)
    )
    assert diagnostic_json["nested"]["residual"] == [[1.0e-12, 2.0e-12]]
    assert diagnostic_json["nested"]["normal_correction_count"] == 1
    endpoint_path = run_root / "task43_v2_a1_endpoint.json"
    endpoint_path.write_text(
        json.dumps(
            {
                "pass": True,
                "status": "passed",
                "official_result": True,
                "selection_eligible": True,
                "selection_candidate": True,
                "candidate_selected": True,
                "gates": {"pass": True, "status": "passed"},
            }
        ),
        encoding="utf-8",
    )
    solve_dir = run_root / "solve"
    solve_dir.mkdir()
    run_summary_path = solve_dir / "run_summary.json"
    run_summary_path.write_text(
        json.dumps({"official_result": True, "case_status": "completed"}),
        encoding="utf-8",
    )

    axes = tuple(np.asarray([0.0, 1.0], dtype=np.float64) for _ in range(3))
    quadrature = SimpleNamespace()

    def build_quadrature(_axes, *, gauss_order):
        quadrature.points_nm = np.asarray(
            [[float(gauss_order), 0.0, 0.0], [float(gauss_order), 1.0, 1.0]]
        )
        quadrature.weights_nm3 = np.asarray([0.5, 0.5], dtype=np.float64)
        return quadrature

    monkeypatch.setattr(
        h100_anchor,
        "prepare_cell_local_vector_field_export",
        lambda _field: SimpleNamespace(
            electric_dgq6=object(),
            curl_electric_dgq6=object(),
            source_degree=6,
            target_degree=6,
            representation="fixture-dgq6",
        ),
    )
    monkeypatch.setattr(h100_anchor, "_mesh_axes", lambda _mesh, _comm: axes)
    monkeypatch.setattr(
        h100_anchor,
        "_assert_mesh_profile",
        lambda *_args, **_kwargs: {"global_cells": 1, "leaf_cells": 1},
    )
    monkeypatch.setattr(
        h100_anchor,
        "build_common_volume_quadrature",
        build_quadrature,
    )
    monkeypatch.setattr(
        h100_anchor,
        "magnetic_field_from_electric_curl",
        lambda curl, **_kwargs: np.zeros_like(curl),
    )

    def sample_fields(_fields, points):
        if points[0, 0] == 10.0:
            raise RuntimeError("injected q10 sampler failure")
        return {
            "E_total": np.ones((2, 3), dtype=np.complex128),
            "curl_E_total": np.full((2, 3), 2.0j, dtype=np.complex128),
        }

    monkeypatch.setattr(h100_anchor, "sample_cell_local_vector_fields", sample_fields)
    sample_records = {}
    sample_identity = {"phase": "A1_q", "contract_sha256": "fixture-contract"}

    def actual_sample_callback(order, sample):
        if sample_role == "primary":
            write_v3_primary_field_sample(
                run_root / f"primary_before_extra_q{order}_samples.npz",
                order,
                sample,
                identity=sample_identity,
                sample_records=sample_records,
            )
        else:
            sample_path = (
                run_root
                / "same_lu_tightening"
                / "after"
                / f"field_sample_q{order}.npz"
            )
            sample_records[f"q{order}"] = write_atomic_npz(
                sample_path,
                sample,
                schema="task43.v3.a1_extra_field_sample.v1",
                classification="measured_extra_sample_after_extra_not_official",
                identity={**sample_identity, "quadrature_order": order},
            )

    with pytest.raises(
        RuntimeError, match="field sample postprocessing failed collectively"
    ):
        h100_anchor._field_capture(
            object(),
            SimpleNamespace(mesh=object()),
            SimpleNamespace(
                magnetic_field_scale_A_per_m=1.0,
                k0=1.0,
                mu_r=1.0,
            ),
            h100_anchor.MPI.COMM_WORLD,
            None,
            on_sample=actual_sample_callback,
        )

    assert set(sample_records) == {"q8"}
    q8_path = Path(sample_records["q8"]["npz_path"])
    assert q8_path.is_file()
    if sample_role == "primary":
        q10_path = run_root / "primary_before_extra_q10_samples.npz"
    else:
        q10_path = run_root / "same_lu_tightening/after/field_sample_q10.npz"
    assert not q10_path.exists()
    original_packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    assert original_packet_sha == packet["npz_sha256"]
    with np.load(packet_path, allow_pickle=False) as saved_packet:
        np.testing.assert_array_equal(
            saved_packet["normal_after_residual"],
            packet_arrays["normal_after_residual"],
        )
        np.testing.assert_array_equal(
            saved_packet["returned_trace_dtn_rhs"],
            packet_arrays["returned_trace_dtn_rhs"],
        )
    with np.load(q8_path, allow_pickle=False) as saved_q8:
        np.testing.assert_array_equal(saved_q8["E_total"], np.ones((2, 3)))
        assert saved_q8["curl_E_total"].shape == (2, 3)

    captured = {
        "v3_primary_before_extra_packet": packet,
        "v3_primary_sample_records": (
            sample_records if sample_role == "primary" else {}
        ),
        "v3_extra_sample_records": (
            sample_records if sample_role == "extra" else {}
        ),
    }
    h100_anchor._write_v3_partial_terminal(
        run_root,
        phase="A1_q",
        source_identity={"git_head": "fixture-head"},
        captured=captured,
        error=RuntimeError("injected q10 sampler failure"),
    )
    terminal = json.loads(
        (run_root / "task43_v3_partial_terminal.json").read_text(encoding="utf-8")
    )
    demoted_endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
    demoted_run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "FAILED"
    assert terminal["official_result"] is False
    terminal_collection = (
        "primary_q_samples" if sample_role == "primary" else "extra_q_samples"
    )
    assert (
        terminal[terminal_collection]["q8"]["npz_sha256"]
        == sample_records["q8"]["npz_sha256"]
    )
    assert all(value is False for value in terminal["continuation"].values())
    assert demoted_endpoint["pass"] is False
    assert demoted_endpoint["official_result"] is False
    assert demoted_endpoint["candidate_selected"] is False
    assert demoted_endpoint["gates"]["pass"] is False
    assert demoted_run_summary["official_result"] is False
    assert demoted_run_summary["diagnostic_only"] is True
    assert demoted_run_summary["legacy_solver_reported_official_result"] is True
    assert hashlib.sha256(packet_path.read_bytes()).hexdigest() == original_packet_sha


@pytest.mark.parametrize(
    "failure",
    (
        "injected post-solve backend mismatch",
        "injected extra-correction comm.bcast failure",
    ),
)
def test_outer_v3_guard_records_escaped_postsolve_exception(tmp_path, failure):
    from benchmarks.task43_hp_adaptivity import h100_anchor

    run_root = tmp_path / "A1_q"
    solve_dir = run_root / "solve"
    run_summary_path = solve_dir / "run_summary.json"

    def fake_runner(**kwargs):
        context = kwargs["_failure_context"]
        context["run_root"].mkdir(parents=True)
        solve_dir.mkdir()
        run_summary_path.write_text(
            json.dumps({"official_result": True, "case_status": "completed"}),
            encoding="utf-8",
        )
        context["run_root_acquired"] = True
        context["source_identity"] = {"git_head": "fixture-head"}
        if "bcast" in failure:
            packet = write_v3_primary_before_extra_packet(
                run_root / "primary_before_extra.npz",
                {"rhs": np.asarray([1.0 + 2.0j]), "solution": np.asarray([0.5j])},
                identity={"phase": "A1_q", "contract_sha256": "fixture"},
            )
            context["captured"]["v3_primary_before_extra_packet"] = packet
        raise RuntimeError(failure)

    with pytest.raises(RuntimeError, match=failure):
        h100_anchor._run_with_v3_failure_terminal(
            fake_runner,
            case="round1_candidate",
            run_root=run_root,
            v2_diagnostic_phase="A1_q",
            v3_failure_evidence_enabled=True,
        )

    terminal = json.loads(
        (run_root / "task43_v3_partial_terminal.json").read_text(encoding="utf-8")
    )
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    expected_status = "FAILED" if "bcast" in failure else "INCOMPLETE"
    assert terminal["status"] == expected_status
    assert terminal["official_result"] is False
    assert terminal["passed"] is False
    assert "measurements only" in terminal["port_output_scope"]
    assert run_summary["official_result"] is False
    assert run_summary["legacy_solver_reported_official_result"] is True
    if "bcast" in failure:
        packet_path = run_root / "primary_before_extra.npz"
        packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        assert terminal["primary_before_extra_packet"]["npz_sha256"] == packet_sha
        with np.load(packet_path, allow_pickle=False) as packet:
            np.testing.assert_array_equal(packet["rhs"], np.asarray([1.0 + 2.0j]))


def test_raw_trace_metric_action_reproduces_the_existing_constraint_norm():
    from src.solvers.hcurl_variable_p_reduction import (
        _reduced_trace_auxiliary_norm,
    )

    class Comm:
        @staticmethod
        def allgather(values):
            return [np.asarray(values).copy()]

    class Vector:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.complex128)

        def getArray(self, readonly=True):
            assert readonly is True
            return self.values

    system = SimpleNamespace(
        active_trace_rows=2,
        appended_rows=1,
        trace_constraints=SimpleNamespace(
            component_gram=np.asarray([[2.0, 0.0], [0.0, 4.0]], dtype=np.complex128)
        ),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=Comm()),
        ),
    )
    dual_values = np.asarray([2.0 + 0.0j, 4.0 + 0.0j, 3.0j])
    default_norm = _reduced_trace_auxiliary_norm(
        system, Vector(dual_values), trace_kind="dual"
    )
    captured_norm, captured = _reduced_trace_auxiliary_norm(
        system,
        Vector(dual_values),
        trace_kind="dual",
        return_action=True,
    )
    trace = dual_values[:2]
    action = captured["trace_metric_action"]
    squared_from_raw = (
        np.vdot(trace, action).real + np.vdot(dual_values[2:], dual_values[2:]).real
    )
    assert default_norm == pytest.approx(captured_norm)
    assert captured_norm**2 == pytest.approx(squared_from_raw)
    np.testing.assert_array_equal(action, np.asarray([1.0, 1.0]))


def test_a2_q3_adapter_cli_isolated_before_native_mesh_or_solver(
    tmp_path, monkeypatch
):
    from benchmarks.task43_hp_adaptivity import a2_native_p6_diagnostic as adapter
    from src.runners import p6_condensed_direct

    repository = tmp_path / "repo"
    contract_rel = Path("docs/task43_hp_adaptivity/diagnostic_plan_v3_contract.json")
    plan_rel = Path("docs/task43_hp_adaptivity/diagnostic_plan_v3.md")
    contract_path = repository / contract_rel
    plan_path = repository / plan_rel
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text("{}\n", encoding="utf-8")
    plan_path.write_text("fixture plan\n", encoding="utf-8")
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    attempt_root = repository / "benchmarks/artifacts/task43/v3_diagnostics/A2_q_attempt3"
    attempt_root.mkdir(parents=True)
    resolved_path = repository / "frozen_y6_resolved.json"

    monkeypatch.setattr(adapter, "_REPO_ROOT", repository)
    monkeypatch.setattr(adapter, "_V3_CONTRACT_REL", contract_rel)
    monkeypatch.setattr(adapter, "_V3_PLAN_REL", plan_rel)
    monkeypatch.setattr(adapter, "_V3_CONTRACT_SHA256", contract_sha)
    monkeypatch.setattr(adapter, "_V3_PLAN_SHA256", plan_sha)
    phase_path = tmp_path / "native_watchdog" / "workflow_phase.json"
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PARENT_PID", "74003")
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(phase_path))
    monkeypatch.setattr(adapter.os, "getppid", lambda: 74003)
    validation_calls = []
    monkeypatch.setattr(
        adapter,
        "_validate_v3_a2_entry_contract",
        lambda contract, *, phase, attempt: validation_calls.append(
            (contract, phase, attempt)
        ),
    )
    diagnostic = {
        "current_source_sha": "source-fixture",
        "reference_resolved_config_path": str(resolved_path),
    }
    frozen = {
        "resolved_profile_compatibility": {"schema": "fixture"},
        "old_summary": {},
        "resolved_payload": {},
    }
    monkeypatch.setattr(
        adapter,
        "_validate_frozen_inputs",
        lambda phase: (diagnostic, frozen),
    )
    native_calls = []

    def fake_native_runner(
        resolved_payload,
        output_dir,
        *,
        source_sha,
        task43_v2_diagnostic,
        task43_v3_diagnostic,
    ):
        native_calls.append(
            {
                "output_dir": Path(output_dir),
                "source_sha": source_sha,
                "phase": task43_v3_diagnostic["phase"],
                "attempt": task43_v3_diagnostic["attempt"],
                "v2_bound": task43_v2_diagnostic is diagnostic,
                "watchdog_worker_identity": task43_v3_diagnostic[
                    "watchdog_worker_identity"
                ],
            }
        )
        summary_path = Path(output_dir) / "p6_condensed_direct_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "source_sha": source_sha,
                    "status": "fixture_native_completed",
                    "passed": True,
                    "official_result": {"fixture": True},
                    "task43_v3_diagnostic_identity": {
                        "contract_sha256": task43_v3_diagnostic[
                            "contract_sha256"
                        ],
                        "plan_sha256": task43_v3_diagnostic["plan_sha256"],
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"summary": str(summary_path), "passed": True}

    monkeypatch.setattr(
        p6_condensed_direct, "run_p6_condensed_direct", fake_native_runner
    )
    monkeypatch.setattr(
        adapter,
        "_comparison_record",
        lambda *_args: {
            "endpoint_qualified": True,
            "primary_perturbation_gate": True,
            "hard_solver_gate": True,
            "extra_same_lu_uncertainty": {
                "pass_10_percent_output_uncertainty_gate": True
            },
            "same_group_R_factor_may_continue": True,
            "A2_R_status": "would_continue_without_v3",
        },
    )

    code = adapter.main(
        [
            "--phase",
            "A2_q",
            "--attempt",
            "3",
            "--v3-contract",
            str(contract_path),
            "--v3-plan",
            str(plan_path),
        ]
    )

    output_dir = attempt_root / "run"
    assert code == 0
    assert len(validation_calls) == 1
    assert validation_calls[0][1:] == ("A2_q", 3)
    assert len(native_calls) == 1
    assert native_calls[0] == {
        "output_dir": output_dir,
        "source_sha": "source-fixture",
        "phase": "A2_q",
        "attempt": 3,
        "v2_bound": True,
        "watchdog_worker_identity": {
            "worker_pid": os.getpid(),
            "worker_parent_pid": 74003,
            "watchdog_parent_pid_environment": 74003,
            "direct_watchdog_parent_verified": True,
            "phase_path": str(phase_path),
        },
    }
    assert (output_dir / "p6_condensed_direct_summary.json").is_file()
    comparison = json.loads(
        (output_dir / "comparison_record.json").read_text(encoding="utf-8")
    )
    assert comparison["same_group_R_factor_may_continue"] is False
    assert comparison["A2_R_status"] == "not_run_locked_by_V3_scope"
