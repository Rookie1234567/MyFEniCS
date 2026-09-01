"""Focused contracts for the Stage-B/C adaptive screen."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import task040_level_a as level_a
from benchmarks import task040_level_a_watchdog as watchdog
from src.solvers import hybrid_adaptive_impedance_screen as screen
from src.solvers import hybrid_adaptive_impedance_stage_bc as stage_bc
from src.solvers import hybrid_maxwell_harmonic_economical as economical

INITIAL = ("external_dtn_coupling", "fixed_random_repeat_0")
HOLDOUT = ("modal_traction_positive", "modal_traction_negative", "fixed_random_repeat_1")
POSITIVE = "ADAPTIVE_SPECTRAL_SCHWARZ_POSITIVE_AT_H4"
NO_SIGNAL = "ADAPTIVE_SPECTRAL_SCHWARZ_NO_SIGNAL_AT_H4"
UNSTABLE = "ADAPTIVE_SPECTRAL_SCHWARZ_UNSTABLE_AT_H4"
INCONCLUSIVE = "ADAPTIVE_SPECTRAL_SCHWARZ_INCONCLUSIVE_AT_H4"
RESOURCE = "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE"
C0_POSITIVE = "ADAPTIVE_COARSE_CONTENT_POSITIVE_EXPLICIT_ORACLE"
C0_NO_SIGNAL = "CURRENT_160_PER_PATCH_HARMONIC_COARSE_NO_SIGNAL"
C0_RESOURCE = "ADAPTIVE_COARSE_EXPLICIT_RESOURCE_OR_TIME_UNAVAILABLE"
C0_NEXT_C1 = "V9_C1_MATRIX_FREE_GALERKIN_COARSE"
C0_NEXT_E = "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR"
pytestmark = pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2")


def _record(values: tuple[float, float, float]) -> dict[str, object]:
    reason = int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3))
    names = ("reported_residual_relative", "reported_residual_absolute",
             "true_residual_relative", "true_residual_absolute")
    checkpoints = {
        str(iteration): dict(iteration=iteration, rhs_norm=1.0, solution_norm=1.0,
                             finite=True, **dict.fromkeys(names, value))
        for iteration, value in zip((16, 32, 64), values, strict=True)
    }
    return {
        "checkpoints": checkpoints,
        "rhs_norm": 1.0,
        "solution_norm": 1.0,
        "final_true_residual_absolute": values[-1],
        "final_true_residual_relative": values[-1],
        "finite": True,
        "ksp_reason": reason,
        "wall_seconds": 0.0,
    }


def _classify(values: tuple[float, float, float], implementation=False) -> str:
    record = _record(values)
    if implementation:
        record["implementation_failure"] = True
    return screen._classify_stage_bc_sources({label: record for label in INITIAL})[
        "classification"
    ]


def test_stage_bc_classifier_and_zero_slope_boundaries() -> None:
    assert screen._stage_bc_slope(0.0, 0.0) is None
    assert screen._stage_bc_slope(1.0, 0.0) == float("inf")
    assert screen._stage_bc_slope(0.0, 1.0) == float("-inf")
    assert _classify((0.8, 0.4, 0.2)) == POSITIVE
    assert _classify((0.95, 0.9, 0.85)) == NO_SIGNAL
    assert _classify((0.8, 0.75, 0.7)) == INCONCLUSIVE
    assert _classify((0.8, 0.0, 0.0)) == INCONCLUSIVE
    assert _classify((0.8, float("nan"), 0.2)) == UNSTABLE
    assert _classify((0.8, 0.4, 0.2), implementation=True) == (
        screen._STAGE_BC_IMPLEMENTATION_FAILURE
    )


@pytest.mark.parametrize(
    ("rho", "classification", "needs_outer"),
    ((0.5, C0_POSITIVE, False), (1.0, C0_POSITIVE, False),
     (1.1952487048622035, C0_POSITIVE, False), (1.2, None, True),
     (1.5, C0_NO_SIGNAL, False),
     (float("nan"), C0_NO_SIGNAL, False)),
)
def test_v9_c0_classifier_boundaries(rho, classification, needs_outer) -> None:
    result = screen._classify_v9_c0_one_apply(rho)
    assert result["classification"] == classification
    assert result["needs_outer_fgmres"] is needs_outer


def _diagonal_matrix(comm: MPI.Intracomm, size: int = 65) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(size=(size, size), nnz=1, comm=comm)
    matrix.setUp()
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValues(
            row,
            np.asarray([row], dtype=PETSc.IntType),
            np.asarray([2.0 + 0.01 * row], dtype=PETSc.ScalarType),
        )
    matrix.assemble()
    return matrix


def test_stage_bc_reuses_right_fgmres_and_borrowed_f() -> None:
    comm = MPI.COMM_WORLD
    matrix = _diagonal_matrix(comm)
    rhs = matrix.createVecRight()
    first, last = map(int, rhs.getOwnershipRange())
    rhs.array[:] = np.asarray(
        [1.0 + 0.01 * row for row in range(first, last)], dtype=PETSc.ScalarType
    )
    action = SimpleNamespace(diagnostics={"apply_count": 0})
    def apply(source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        action.diagnostics["apply_count"] += 1

    action.apply = apply
    solver = screen._StageBCRightFGMRES(matrix, action)
    ksp_identity = id(solver.ksp)
    try:
        records = [solver.solve(rhs, label) for label in INITIAL]
        assert id(solver.ksp) == ksp_identity
        assert "gmres" in str(solver.ksp.getType()).lower()
        for record in records:
            assert set(record["checkpoints"]) == {"16", "32", "64"}
            assert not {"8", "128"} & set(record["checkpoints"])
            assert (record["restart"], record["max_it"],
                    record["zero_initial_guess"], record["pc_side"]) == (
                        32, 64, True, "right"
                    )
            assert record["right_pc_apply_count"] > 0
            assert screen._stage_bc_record_usable(record)
        assert action.diagnostics["apply_count"] == sum(
            record["right_pc_apply_count"] for record in records
        )
    finally:
        solver.destroy()
        check = matrix.createVecLeft()
        try:
            matrix.mult(rhs, check)
            assert np.all(np.isfinite(check.array))
        finally:
            check.destroy()
            rhs.destroy()
            matrix.destroy()


class _Tracked:
    def __init__(self, diagnostics: dict[str, object] | None = None) -> None:
        self.diagnostics = diagnostics or {}
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


def _install_screen_fakes(monkeypatch, comm: MPI.Intracomm, coarse_builder):
    provider = _Tracked()
    provider.collective_audit = lambda: {"status": "verified_exact_provider"}
    preparation = _Tracked({"global_patch_count": comm.size})
    preparation.diagnostics["prepared_rhs_released"] = True
    local_action = _Tracked({"factor_lifecycle": {"ready": 1}, "apply_count": 0})
    local_action.release_diagnostic_matrices = lambda: None
    harmonic = _Tracked({
        "global_patch_count": comm.size, "local_patch_count": 1,
        "global_retained_rank": comm.size,
        "harmonic_multi_rhs_solve_count": comm.size,
    })
    harmonic.local_patch_records = [SimpleNamespace(
        columns=np.ones((1, 1), dtype=np.complex128)
    )]
    patches = (
        (screen, "build_actual_hcurl_cell_tangential_mass_provider",
         lambda *args, **kwargs: provider),
        (screen, "build_adaptive_impedance_schwarz_action",
         lambda *args, **kwargs: local_action),
        (economical, "prepare_economical_gamma_rhs",
         lambda *args, **kwargs: preparation),
        (economical, "solve_prepared_economical_columns",
         lambda *args, **kwargs: harmonic),
        (stage_bc, "build_adaptive_impedance_stage_bc_action", coarse_builder),
    )
    for target, name, value in patches:
        monkeypatch.setattr(target, name, value)
    return provider, preparation, local_action, harmonic


def _resource(*, passed: bool) -> dict[str, object]:
    return dict(all_status_readable=True, **{"pass": passed}, rss_bytes=1,
                swap_bytes=0, source="fixture", wall_observation={"pass": True})


def test_stage_bc_resource_denial_has_no_source_or_coarse(monkeypatch) -> None:
    comm = MPI.COMM_WORLD
    bare_f = _diagonal_matrix(comm, size=2)
    calls = {"source": 0, "coarse": 0}

    def forbidden_coarse(*args, **kwargs):
        calls["coarse"] += 1
        raise AssertionError("coarse allocation followed a resource denial")

    components = _install_screen_fakes(monkeypatch, comm, forbidden_coarse)
    events = []
    def callback(event, detail):
        events.append((event, detail))
        return _resource(passed=False)
    def source_builder(_label):
        calls["source"] += 1
        raise AssertionError("source construction followed a resource denial")
    try:
        result = _run_screen(bare_f, source_builder, callback)
        assert result["classification"] == RESOURCE
        assert result["executed_source_order"] == []
        assert result["harmonic_audit"]["generalized_eigenproblem"] is False
        assert result["cleanup"]["status"] == "complete"
        assert calls == {"source": 0, "coarse": 0}
        assert all(item.destroyed for item in components)
        assert [event for event, _detail in events][-2:] == [
            "classification", "cleanup"
        ]
    finally:
        bare_f.destroy()


def test_stage_bc_positive_extends_same_setup(monkeypatch) -> None:
    comm = MPI.COMM_WORLD
    bare_f = _diagonal_matrix(comm, size=2)
    coarse_action = _Tracked(
        {"apply_count": 0, "memory_preflight": {"allocation_allowed": True}}
    )
    def coarse_builder(*args, **kwargs):
        return SimpleNamespace(
            action=coarse_action,
            status="ready",
            diagnostics={
                "memory_preflight": {"allocation_allowed": True},
                "allocated_object_count": {"P": 1, "P_H": 0, "FP": 0, "Ac": 1},
            },
        )

    _install_screen_fakes(monkeypatch, comm, coarse_builder)
    labels = []
    outer_instances = []
    class FakeOuter:
        def __init__(self, _operator, action):
            self.action = action
            self.context = SimpleNamespace(count=0)
            outer_instances.append(self)

        def solve(self, _rhs, label, checkpoint_callback=None):
            del checkpoint_callback
            labels.append(label)
            self.context.count += 1
            self.action.diagnostics["apply_count"] += 1
            return _record((0.8, 0.4, 0.2))

        def destroy(self):
            self.destroyed = True

    monkeypatch.setattr(screen, "_StageBCRightFGMRES", FakeOuter)
    events = []
    def callback(event, detail):
        events.append((event, detail))
        return _resource(passed=True)

    sources = []
    def source_builder(label):
        source = _Tracked()
        sources.append(source)
        return source, {"source": label}
    try:
        result = _run_screen(bare_f, source_builder, callback)
        coarse_details = [detail for event, detail in events if event == "coarse_ready"]
        assert len(coarse_details) == 1
        assert "status" not in coarse_details[0]
        assert coarse_details[0]["coarse_status"] == "ready"
        assert labels == list(INITIAL + HOLDOUT)
        assert result["initial_classification"] == POSITIVE
        assert result["classification"] == POSITIVE
        assert result["executed_source_order"] == list(INITIAL + HOLDOUT)
        assert result["five_source_extension_status"] == "executed"
        assert result["cleanup"]["source_vectors_destroyed"] == 5
        assert result["cleanup"]["action_apply_count"] == 5
        assert result["coarse_diagnostics"]["coarse_setup_wall_seconds"] >= 0.0
        assert len(outer_instances) == 1
        assert all(source.destroyed for source in sources)
        assert coarse_action.destroyed is True
        assert events[-1][0] == "cleanup"
    finally:
        bare_f.destroy()


def _c0_action(factor: float) -> _Tracked:
    action = _Tracked({"apply_count": 0})

    def apply(source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        target.scale(factor)
        action.diagnostics["apply_count"] += 1

    action.apply = apply
    return action


def _c0_builder(action: _Tracked):
    def build(*_args, **kwargs):
        assert kwargs["hard_memory_bytes"] == 64 * 2**30
        assert callable(kwargs["phase_callback"])
        kwargs["harmonic_space"].destroy()
        return SimpleNamespace(
            action=action,
            status="ready",
            diagnostics={
                "memory_preflight": {"allocation_allowed": True},
                "allocated_object_count": {"P": 1, "P_H": 0, "FP": 0, "Ac": 1, "KSP": 1},
            },
        )

    return build


def _c0_source_builder(bare_f: PETSc.Mat, labels: list[str]):
    def build(label: str):
        labels.append(label)
        source = bare_f.createVecRight()
        source.set(1.0)
        return source, {"source_label": label}

    return build


def _run_screen(
    bare_f: PETSc.Mat,
    source_builder,
    event_callback,
    *,
    c0: bool = False,
    **kwargs,
) -> dict[str, object]:
    runner = (
        screen.run_v9_c0_explicit_coarse_oracle
        if c0
        else screen.run_adaptive_impedance_stage_bc_screen
    )
    return runner(
        function_space=None,
        condensed=None,
        bare_f=bare_f,
        facet_tags=None,
        external_facet_tag=5,
        beta=0.1,
        quadrature_degree=2,
        source_builder=source_builder,
        event_callback=event_callback,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("factor", "expected"), ((0.5, C0_POSITIVE), (1.5, C0_NO_SIGNAL))
)
def test_v9_c0_external_one_apply_and_cleanup(monkeypatch, factor, expected) -> None:
    comm = MPI.COMM_WORLD
    bare_f = _diagonal_matrix(comm, size=2)
    action = _c0_action(factor)
    components = _install_screen_fakes(monkeypatch, comm, _c0_builder(action))
    events, labels = [], []
    try:
        result = _run_screen(
            bare_f,
            _c0_source_builder(bare_f, labels),
            lambda event, detail: events.append((event, detail)),
            c0=True,
            resource_callback=lambda: _resource(passed=True),
            phase_callback=None,
            hard_memory_bytes=64 * 2**30,
        )
        assert result["classification"] == expected
        assert result["next_required_stage"] == (
            C0_NEXT_C1 if expected == C0_POSITIVE else C0_NEXT_E
        )
        assert labels == ["external_dtn_coupling"]
        assert result["outer_record"] is None
        assert result["cleanup"]["status"] == "complete"
        assert result["cleanup"]["source_vectors_destroyed"] == 1
        assert result["cleanup"]["action_apply_count"] == 1
        assert result["cleanup"]["bare_f_unchanged"] is True
        assert [
            event
            for event, _detail in events
            if event.endswith(("apply_begin", "apply_end"))
        ] == [
            "external_one_apply_begin", "external_one_apply_end"
        ]
        assert all(component.destroyed for component in components)
    finally:
        bare_f.destroy()


@pytest.mark.parametrize("scenario", ("intermediate", "pre_apply_resource"))
def test_v9_c0_intermediate_or_resource_gate(monkeypatch, scenario) -> None:
    comm = MPI.COMM_WORLD
    bare_f = _diagonal_matrix(comm, size=2)
    action = _c0_action(1.1)
    _install_screen_fakes(monkeypatch, comm, _c0_builder(action))
    events, labels = [], []
    resource_values = iter((True, True) if scenario == "intermediate" else (True, False))

    def resource_callback():
        return _resource(passed=next(resource_values))

    if scenario == "intermediate":
        class FakeOuter:
            def __init__(self, _operator, action, *, max_it, checkpoints):
                assert (max_it, checkpoints) == (8, (8,))
                self.action = action
                self.context = SimpleNamespace(count=0)

            def solve(self, _rhs, _label, checkpoint_callback=None):
                self.context.count = 8
                self.action.diagnostics["apply_count"] += 8
                row = {"iteration": 8, "true_residual_relative": 0.7, "finite": True}
                if checkpoint_callback is not None:
                    checkpoint_callback(row)
                return {"checkpoints": {"8": row}, "finite": True, "iterations": 8, "max_it": 8}

            def destroy(self):
                self.destroyed = True

        monkeypatch.setattr(screen, "_StageBCRightFGMRES", FakeOuter)
        source_builder = _c0_source_builder(bare_f, labels)
    else:
        def source_builder(_label):
            raise AssertionError("resource denial reached source construction")

    try:
        result = _run_screen(
            bare_f,
            source_builder,
            lambda event, detail: events.append((event, detail)),
            c0=True,
            resource_callback=resource_callback,
            phase_callback=None,
            hard_memory_bytes=64 * 2**30,
        )
        if scenario == "intermediate":
            assert result["classification"] == C0_POSITIVE
            assert result["outer_record"]["max_it"] == 8
            assert set(result["outer_record"]["checkpoints"]) == {"8"}
            assert result["cleanup"]["action_apply_count"] == 9
            assert labels == ["external_dtn_coupling"]
        else:
            assert result["classification"] == C0_RESOURCE
            assert result["next_required_stage"] == C0_NEXT_C1
            assert result["numerical_negative"] is False
            assert result["cleanup"]["action_apply_count"] == 0
            assert labels == []
            assert not any(event == "external_one_apply_begin" for event, _ in events)
    finally:
        bare_f.destroy()


def test_stage_bc_plan_argv_total_timeout_and_failure_priority(tmp_path: Path) -> None:
    values = {"input_path": tmp_path / "input.dat", "exact_spool_root": tmp_path / "spool",
              "run_directory": tmp_path / "run", "source_sha": "d" * 40,
              "v8_adaptive_stage_bc_only": True}
    plan = level_a.build_task040_level_a_plan(**values)
    assert (plan["source_order"], plan["planned_source_order"],
            plan["timeout_seconds"], plan["mandatory_checkpoints"]) == (
                list(INITIAL), list(INITIAL + HOLDOUT), 10800, [16, 32, 64]
            )
    assert {"P", "P_H", "FP", "Ac"}.isdisjoint(plan["forbidden"])
    assert "dense_global_coarse_factor" in plan["forbidden"]
    watchdog_plan = watchdog.build_task040_level_a_watchdog_plan(**values)
    argv = watchdog._worker_command(watchdog_plan)
    assert {"--v8-adaptive-stage-bc-only", "--watchdog-enabled",
            "--bottom-route-only"}.issubset(argv)
    assert watchdog._v8_adaptive_stage_bc_total_timeout("b1", 20000.0, 1.0)["timed_out"] is False
    timeout = watchdog._v8_adaptive_stage_bc_total_timeout("b1", 1.0, 10801.0)
    assert timeout["timed_out"] is True and timeout["kind"] == "total"
    with pytest.raises(ValueError, match="mutually exclusive"):
        level_a.build_task040_level_a_plan(**{**values, "v8_adaptive_schwarz_only": True})
    source = inspect.getsource(watchdog.run_task040_level_a_watchdog)
    assert source.index("if resource_stop:") < source.index(
        "elif stage_bc_failure_manifest.is_file():"
    )
