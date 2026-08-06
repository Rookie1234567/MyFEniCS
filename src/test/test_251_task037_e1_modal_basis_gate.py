import json
import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.run_task033_full3d_watchdog as watchdog
import src.solvers.static_modal_coarse_gate as modal_gate
from src.solvers.condensed_dtn import (
    PetscCondensedBlocks,
    create_matrix_free_condensed_operator,
)
from src.solvers.static_modal_coarse_gate import (
    OwnerLocalBasis,
    _call_e2_live_callback,
    _diagnose_interface_packets,
    load_owner_local_basis_shard,
    qualify_e1_modal_basis_audit,
    save_owner_local_basis_shard,
)
from src.solvers.hcurl_canonical_vector import canonical_key


def _e1_args():
    return SimpleNamespace(
        task037_e1_modal_basis_gate=True,
        task037_e0_matrix_free_dtn_gate=False,
        task037_f0_vector_observer=False,
        task037_canonical_vector_export=False,
        task037_f1_direct_trace_oracle=None,
        task037_f3_screen=None,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=False,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_optimized_schwarz=False,
        mpi_size=8,
        polarization_kind="s",
    )


def _aij(values):
    values = np.asarray(values, dtype=PETSc.ScalarType)
    rows, columns = values.shape
    matrix = PETSc.Mat().createAIJ(
        size=(rows, columns),
        nnz=max(columns, 1),
        comm=MPI.COMM_SELF,
    )
    matrix.setUp()
    matrix.setValues(
        np.arange(rows, dtype=PETSc.IntType),
        np.arange(columns, dtype=PETSc.IntType),
        values,
    )
    matrix.assemble()
    return matrix


def _e1_summary(**overrides):
    audit = {
        "research_only": True,
        "ordinary_default_changed": False,
        "implementation_gate_pass": True,
        "gate_pass": True,
        "n_aux": 80,
        "column_count": 240,
        "forward_column_count": 120,
        "backward_column_count": 120,
        "global_active_rows": 51192,
        "finite_nonzero_columns": True,
        "missing": 0,
        "extra": 0,
        "duplicate": 0,
        "max_repeat_error": 1.0e-13,
        "random_action_relative_error": 1.0e-13,
        "max_bottom_retained_residual": 1.0e-13,
        "max_top_retained_residual": 1.0e-13,
        "max_local_interface_mismatch": 1.0e-13,
        "max_stitch_interface_mismatch": 1.0e-13,
        "factors_released": True,
        "official_result": False,
        "ksp_iterations": 0,
        "column_audit_summary": {
            "first_pass_column_count": 240,
            "second_pass_column_count": 240,
            "all_columns_recreated": True,
        },
        "action_space": {
            "effective_rank": 200,
            "normal_equations_used": False,
        },
        "materialization": {
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
        "factor_inventory": {
            "bottom": {"setup_count": 1},
            "top": {"setup_count": 1},
        },
    }
    audit.update(overrides.pop("audit", {}))
    summary = {
        "matrix_stats": {
            "matrix_rows": 51192,
            "matrix_nnz_used": None,
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_solver_profile": "task037_e1_component_only",
        "official_result": False,
        "ksp_iterations": 0,
    }
    summary.update(overrides)
    return summary, audit


def test_research_only_shard_manifest_round_trip(tmp_path):
    values = np.asarray(
        [[1.0 + 2.0j, 0.0], [0.5 - 1.0j, 3.0 + 0.25j]],
        dtype=np.complex128,
    )
    with pytest.raises(ValueError, match="research-only"):
        OwnerLocalBasis.from_local_array(
            values,
            global_rows=2,
            comm=MPI.COMM_SELF,
            label="Z",
        )
    basis = OwnerLocalBasis.from_local_array(
        values,
        global_rows=2,
        comm=MPI.COMM_SELF,
        label="Z",
        research_opt_in=True,
    )
    try:
        manifest = save_owner_local_basis_shard(
            basis,
            tmp_path,
            source_sha="a" * 40,
            prefix="Z",
            research_opt_in=True,
        )
        assert manifest["owner_local"] is True
        assert manifest["replicated_global_basis"] is False
        shard = manifest["shards"][0]
        loaded = load_owner_local_basis_shard(
            shard["path"],
            expected_sha256=shard["sha256"],
        )
        np.testing.assert_array_equal(loaded["local_values"], values)
        assert loaded["source_sha"] == "a" * 40
        assert loaded["sha256"] == shard["sha256"]
    finally:
        basis.destroy()


def test_e1_uses_full_condensed_action_and_optional_live_callback():
    f_values = np.asarray(
        [
            [2.0 + 0.2j, 0.3 - 0.1j],
            [0.15 + 0.05j, 1.4 - 0.25j],
        ]
    )
    c_values = np.asarray([[0.8 + 0.3j], [0.25 - 0.15j]])
    d_values = np.asarray([[0.4 - 0.2j, -0.35 + 0.1j]])
    h_values = np.asarray([[1.7 + 0.45j]])
    f_matrix = _aij(f_values)
    c_matrix = _aij(c_values)
    d_matrix = _aij(d_values)
    h_matrix = _aij(h_values)
    b_fe = f_matrix.createVecLeft()
    b_aux = h_matrix.createVecLeft()
    blocks = PetscCondensedBlocks(
        f_matrix,
        c_matrix,
        d_matrix,
        h_matrix,
        b_fe,
        b_aux,
        2,
        1,
    )
    a6 = None
    z_basis = None
    y_basis = None
    f_basis = None
    try:
        a6, _a6_context = create_matrix_free_condensed_operator(
            blocks,
            fine_operator=f_matrix,
        )
        z_values = np.asarray(
            [
                [1.0 + 0.2j, -0.3 + 0.4j],
                [0.5 - 0.1j, 1.2 + 0.0j],
            ]
        )
        z_basis = OwnerLocalBasis.from_local_array(
            z_values,
            global_rows=2,
            comm=MPI.COMM_SELF,
            label="Z",
            research_opt_in=True,
        )
        y_basis = z_basis.apply(a6, label="Y", research_opt_in=True)
        f_basis = z_basis.apply(f_matrix, label="FZ", research_opt_in=True)
        expected_a6 = f_values - c_values @ np.linalg.solve(h_values, d_values)
        np.testing.assert_allclose(
            y_basis.local_matrix(),
            expected_a6 @ z_values,
            rtol=0.0,
            atol=1.0e-12,
        )
        assert np.linalg.norm(y_basis.local_matrix() - f_basis.local_matrix()) > 1.0e-8

        calls = []
        _call_e2_live_callback(None, z_basis, y_basis, a6)
        assert calls == []

        def callback(z_seen, y_seen, operator_seen):
            calls.append((z_seen, y_seen, operator_seen))
            assert z_seen._destroyed is False
            assert y_seen._destroyed is False
            assert operator_seen.getSize() == (2, 2)

        _call_e2_live_callback(callback, z_basis, y_basis, a6)
        assert len(calls) == 1
        signature = inspect.signature(modal_gate.run_e1_modal_basis_gate)
        assert signature.parameters["e2_live_callback"].default is None
        source = inspect.getsource(modal_gate._run_e1_modal_basis_gate)
        assert "if gate_pass:" in source
        assert "_call_e2_live_callback" in source
    finally:
        if f_basis is not None:
            f_basis.destroy()
        if y_basis is not None:
            y_basis.destroy()
        if z_basis is not None:
            z_basis.destroy()
        if a6 is not None:
            a6.destroy()
        blocks.destroy()


def test_e2_callback_failure_preserves_completed_e1_audit(tmp_path, monkeypatch):
    audit_path = tmp_path / "task037_e1_modal_basis_audit.json"
    failure_writes = []
    run_source = inspect.getsource(modal_gate._run_e1_modal_basis_gate)

    def callback(_z_basis, _y_basis, _a6_operator):
        raise RuntimeError("synthetic E2 failure")

    def fake_run(_request, *, run_dir, source_sha, e2_live_callback=None):
        del source_sha
        run_dir.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(
                {
                    "classification": "M120_GLOBAL_MODAL_BASIS_GATE_PASSED",
                    "gate_pass": True,
                }
            ),
            encoding="utf-8",
        )
        try:
            e2_live_callback(None, None, None)
        except Exception as error:
            raise modal_gate._E2LiveCallbackError(
                "E2 live callback failed after E1 audit completion"
            ) from error

    monkeypatch.setattr(modal_gate, "_run_e1_modal_basis_gate", fake_run)
    monkeypatch.setattr(
        modal_gate,
        "_write_e1_failure_audit",
        lambda *args, **kwargs: failure_writes.append((args, kwargs)),
    )
    with pytest.raises(modal_gate._E2LiveCallbackError):
        modal_gate.run_e1_modal_basis_gate(
            SimpleNamespace(),
            run_dir=tmp_path,
            source_sha="a" * 40,
            research_opt_in=True,
            e2_live_callback=callback,
        )
    assert json.loads(audit_path.read_text(encoding="utf-8"))["gate_pass"] is True
    assert failure_writes == []
    assert run_source.index("_write_json") < run_source.index("_call_e2_live_callback")


def test_e1_checker_positive_and_failure_classifications():
    args = _e1_args()
    summary, audit = _e1_summary()
    positive = watchdog._qualify(
        args=args,
        solver_summary=summary,
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=8,
        resource_summary={},
        task037_e1_audit=audit,
    )
    assert positive["pass"] is True
    assert positive["e1_checker_classification"] == (
        "M120_GLOBAL_MODAL_BASIS_GATE_PASSED"
    )

    _, collapsed_audit = _e1_summary(
        audit={"action_space": {"effective_rank": 179, "normal_equations_used": False}}
    )
    collapsed = watchdog._qualify(
        args=args,
        solver_summary=summary,
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=8,
        resource_summary={},
        task037_e1_audit=collapsed_audit,
    )
    assert collapsed["pass"] is False
    assert collapsed["e1_checker_classification"] == (
        "M120_GLOBAL_ACTION_BASIS_COLLAPSED"
    )

    for overrides, expected_failure in (
        ({"action_space": {}}, "rank_gate"),
        ({"max_repeat_error": 2.0e-12}, "repeat_gate"),
        ({"random_action_relative_error": 2.0e-11}, "action_gate"),
        ({"max_top_retained_residual": 2.0e-10}, "interface_gate"),
    ):
        _, negative_audit = _e1_summary(audit=overrides)
        negative = watchdog._qualify(
            args=args,
            solver_summary=summary,
            events=[],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=8,
            resource_summary={},
            task037_e1_audit=negative_audit,
        )
        assert negative["pass"] is False
        assert expected_failure in negative["e1_checker"]["failures"]
        assert negative["e1_checker_classification"] == (
            "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
        )

    _, missing_action_audit = _e1_summary(audit={"action_space": None})
    missing_action = qualify_e1_modal_basis_audit(
        missing_action_audit,
        solver_summary=summary,
        return_code=0,
        no_swap=True,
    )
    assert missing_action["classification"] == (
        "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
    )


def _e1_cli(*extra, tmp_path):
    return [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        str(tmp_path / "authority.json"),
        "--task035c-p6-preflight-sha256",
        "0" * 64,
        "--verified-clean-sha",
        "0" * 40,
        "--task037-e1-modal-basis-gate",
        *extra,
    ]


def test_e1_parser_forwarding_and_source_wiring(tmp_path):
    args = watchdog._parse_args(
        _e1_cli("--worker", "--run-dir", str(tmp_path), tmp_path=tmp_path)
    )
    assert args.task037_e1_modal_basis_gate is True
    command = watchdog._worker_command(args, tmp_path)
    assert "--task037-e1-modal-basis-gate" in command
    assert "--task037-e0-matrix-free-dtn-gate" not in command

    with pytest.raises(SystemExit):
        watchdog._parse_args(
            _e1_cli("--task037-e0-matrix-free-dtn-gate", tmp_path=tmp_path)
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(_e1_cli("--task037-f3-full", tmp_path=tmp_path))

    source = inspect.getsource(watchdog._worker)
    assert "run_e1_modal_basis_gate" in source
    assert "Stage4NeverMaterializedLinearSolverPort(e1_callback)" in source
    assert "matrix_free_dtn=e0_gate or e1_gate" in source
    assert "matrix_free_dtn_probe=e0_gate" in source
    assert "static_retain_local_schur_for_matrix_free=(" in source
    assert "task037_e1_modal_basis_generation" in source


def test_first_column_interface_diagnostic_reports_scale_and_subgroups():
    edge = canonical_key(
        role="active_trace",
        entity_dimension=1,
        physical_entity=((0, 0, 100), (1, 0, 100)),
        entity_local_basis_index=0,
        orientation_state="identity",
    )
    face = canonical_key(
        role="active_trace",
        entity_dimension=2,
        physical_entity=((0, 0, 100), (1, 0, 100), (0, 1, 100), (1, 1, 100)),
        entity_local_basis_index=1,
        orientation_state="identity",
    )
    middle = ((edge, 1.0 + 0.0j), (face, 2.0 + 0.0j))
    local = ((edge, 2.0 + 0.0j), (face, 4.0 + 0.0j))
    identical = _diagnose_interface_packets(
        middle,
        middle,
        interface_keys={edge, face},
        label="identical",
    )
    assert identical["absolute_l2_difference"] == pytest.approx(0.0)
    assert identical["relative_l2_difference"] == pytest.approx(0.0)
    audit = _diagnose_interface_packets(
        middle,
        local,
        interface_keys={edge, face},
        label="top",
        propagation_factor=1.0 + 0.0j,
        effective_beta=0.0 + 0.0j,
        log_magnitude=0.0,
        roundoff_growth_clipped=False,
    )
    assert audit["local_norm"] == pytest.approx(np.sqrt(20.0))
    assert audit["middle_norm"] == pytest.approx(np.sqrt(5.0))
    assert audit["absolute_l2_difference"] == pytest.approx(np.sqrt(5.0))
    assert audit["best_global_complex_scalar"] == pytest.approx([2.0, 0.0])
    assert audit["relative_residual_after_best_global_scalar"] == pytest.approx(0.0)
    assert audit["dimension_errors"]["edge"]["relative_l2_difference"] == pytest.approx(
        0.5
    )
    assert audit["dimension_errors"]["face"]["relative_l2_difference"] == pytest.approx(
        0.5
    )
    assert audit["factor"]["stable_factor"] == pytest.approx([1.0, 0.0])
    assert audit["factor"]["relative_difference"] == pytest.approx(0.0)
    assert audit["identifiability"]["numerically_identifiable"] is True
