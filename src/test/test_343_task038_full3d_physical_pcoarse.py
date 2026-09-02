"""Pure focused contracts for the V16 physical p-coarse core."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

import src.solvers.common_3d_forms as common_forms_module
import src.solvers.dtn_port_3d as dtn_port_module
import src.solvers.fullspace_dtn_action as dtn_module
import src.solvers.fullspace_physical_action as physical_action_module
import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical_module
import src.solvers.fullspace_same_mesh_physical_pcoarse as pcoarse
from src.solvers.fullspace_memory_first_krylov import destroy_krylov_result
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
    destroy_same_mesh_physical_action,
)


def _diagonal(values: tuple[complex, ...]) -> PETSc.Mat:
    size = len(values)
    matrix = PETSc.Mat().createAIJ(
        ((size, size), (size, size)), comm=PETSc.COMM_SELF
    )
    matrix.setUp()
    for index, value in enumerate(values):
        matrix.setValue(index, index, value)
    matrix.assemble()
    return matrix


class _Action:
    def __init__(self, matrix: PETSc.Mat) -> None:
        self.matrix = matrix
        self.calls = 0
        self.destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.matrix.mult(source, target)
        self.calls += 1


class _Smoother:
    def __init__(self) -> None:
        self.calls = 0
        self.destroyed = False

    def apply_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        target.scale(0.25)
        self.calls += 1


class _Transfer:
    def __init__(self) -> None:
        self.adjoint_calls = 0
        self.primal_calls = 0

    def apply_adjoint_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        self.adjoint_calls += 1

    def apply_primal_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        self.primal_calls += 1


class _LowerCycle:
    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        result = source.duplicate()
        source.copy(result)
        return result


class _Disposable:
    def __init__(self, label: str) -> None:
        self.label = label
        self.destroy_count = 0

    def destroy(self) -> None:
        self.destroy_count += 1


class _FakePhysicalAction:
    def __init__(self, volume: object, dtn: object) -> None:
        self.volume = volume
        self.dtn = dtn
        self.destroy_count = 0

    def destroy(self) -> None:
        self.destroy_count += 1


def _core_case(*, inner_max_it: int = 20):
    p6_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    p3_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    smoother = _Smoother()
    transfer = _Transfer()
    floquet = SimpleNamespace(
        mpc=SimpleNamespace(
            slaves=np.asarray((0,), dtype=np.int32),
            function_space=SimpleNamespace(
                dofmap=SimpleNamespace(
                    index_map=SimpleNamespace(size_local=4), index_map_bs=1
                )
            ),
        )
    )
    setup = {
        "p6_shell": SimpleNamespace(matrix=p6_matrix),
        "p3_matrix": p3_matrix,
        "upper_cycle": SimpleNamespace(smoother=smoother),
        "lower_cycle": _LowerCycle(),
        "p63_owner_transfer": transfer,
        "floquets": {6: floquet},
    }
    p6_action = _Action(p6_matrix)
    p3_action = _Action(p3_matrix)
    core = pcoarse.SameMeshPhysicalPcoarseV1(
        setup, p6_action, p3_action, inner_max_it=inner_max_it
    )
    return core, setup, p6_matrix, p3_matrix, smoother, transfer, p6_action, p3_action


def test_physical_pcycle_contract_uses_mocked_galerkin_composition() -> None:
    core, _setup, p6_matrix, p3_matrix, smoother, transfer, p6_action, p3_action = (
        _core_case()
    )
    rhs = p6_matrix.createVecLeft()
    target = p6_matrix.createVecRight()
    rhs.array[:] = (1.0 + 0.5j, 2.0 - 0.25j, -1.0 + 0.75j, 3.0j)
    work_ids = tuple(id(vector) for vector in core.work_vectors)

    coarse_probe = p3_matrix.createVecRight()
    fine_probe = p6_matrix.createVecRight()
    fine_action = p6_matrix.createVecLeft()
    coarse_action = p3_matrix.createVecLeft()
    direct_action = p3_matrix.createVecLeft()
    coarse_probe.array[:] = (1.0 + 0.5j, -2.0j, 0.25 + 1.0j, 3.0 - 0.5j)
    transfer.apply_primal_into(coarse_probe, fine_probe)
    p6_matrix.mult(fine_probe, fine_action)
    transfer.apply_adjoint_into(fine_action, coarse_action)
    p3_matrix.mult(coarse_probe, direct_action)
    assert np.allclose(coarse_action.array, direct_action.array, atol=1.0e-12)
    transfer.adjoint_calls = transfer.primal_calls = 0

    def fake_inner(inner_rhs, *, max_it):
        assert max_it == 20
        result = inner_rhs.duplicate()
        inner_rhs.copy(result)
        result.scale(0.5)
        core.last_inner_facts = {
            "max_it": 20,
            "iterations": 20,
            "ksp_type": "fgmres",
            "restart": 20,
            "residual_replacement": True,
        }
        return {"final_solution": result}

    original = core.solve_inner
    core.solve_inner = fake_inner
    try:
        before = rhs.array.copy()
        facts = core.apply_into(rhs, target)
        assert np.array_equal(rhs.array, before)
        assert facts["formula"].startswith("S6 -> A6 -> P63^H")
        assert facts["p6_smoother_count"] == 2
        assert facts["p63_adjoint_count"] == facts["p63_primal_count"] == 1
        assert facts["physical_action_count"] == 2
        assert facts["owned_slave_max"] == 0.0
        assert np.all(np.isfinite(target.array))
        assert len(core.work_vectors) == 10
        assert core.audit["dedicated_p6_vector_count"] == 8
        assert core.audit["dedicated_p3_vector_count"] == 2
        assert tuple(id(vector) for vector in core.work_vectors) == work_ids
        assert smoother.calls == 2
        assert transfer.adjoint_calls == transfer.primal_calls == 1
        assert p6_action.calls == 2
        assert p3_action.calls == 0
    finally:
        core.solve_inner = original
        target.destroy()
        rhs.destroy()
        coarse_probe.destroy()
        fine_probe.destroy()
        fine_action.destroy()
        coarse_action.destroy()
        direct_action.destroy()
        core.destroy()
        core.destroy()
        p6_matrix.destroy()
        p3_matrix.destroy()


def test_inner_contract_selects_right_fgmres_and_keeps_legacy_default(monkeypatch) -> None:
    core, _setup, p6_matrix, p3_matrix, _smoother, _transfer, _a6, _a3 = _core_case()
    core100, _setup100, p6_matrix100, p3_matrix100, _smoother100, _transfer100, _a6100, _a3100 = _core_case(
        inner_max_it=100
    )
    rhs = p3_matrix.createVecLeft()
    rhs100 = p3_matrix100.createVecLeft()
    calls = []

    def fake_run(rhs, action, pc, **kwargs):
        calls.append(kwargs)
        solution = rhs.duplicate()
        rhs.copy(solution)
        return {
            "settings": {
                "ksp_type": kwargs["ksp_type"],
                "restart": 20,
                "residual_replacement": True,
            },
            "iterations": kwargs["max_it"],
            "explicit_action_count": 2,
            "pc_apply_count": 1,
            "ksp_destroy_count": 1,
            "final_true_residual": 0.0,
            "final_solution": solution,
        }

    monkeypatch.setattr(pcoarse, "run_restart20_cycles", fake_run)
    try:
        first = core.solve_inner(rhs, max_it=20)
        second = core.solve_inner(rhs, max_it=100)
        assert first["settings"]["ksp_type"] == "fgmres"
        assert second["settings"]["ksp_type"] == "fgmres"
        assert [call["max_it"] for call in calls] == [20, 100]
        assert all(call["ksp_type"] == "fgmres" for call in calls)
        assert all(call["checkpoint_writer"] is None for call in calls)
        assert all(call["stop_on_true_residual"] is False for call in calls)
        assert core.audit["inner_max_it"] == 20
        assert core100.audit["inner_max_it"] == 100
        output100 = p6_matrix100.createVecRight()
        try:
            core100.apply_into(rhs100, output100)
            assert calls[-1]["max_it"] == 100
            assert core100.last_apply_facts["inner_max_it"] == 100
        finally:
            output100.destroy()
        with pytest.raises(ValueError, match="20 or 100"):
            pcoarse.SameMeshPhysicalPcoarseV1(
                _setup, _a6, _a3, inner_max_it=10000
            )
        assert inspect.signature(
            __import__(
                "src.solvers.fullspace_memory_first_krylov",
                fromlist=("run_restart20_cycles",),
            ).run_restart20_cycles
        ).parameters["ksp_type"].default == "gmres"
    finally:
        destroy_krylov_result(first)
        destroy_krylov_result(second)
        rhs.destroy()
        rhs100.destroy()
        core.destroy()
        core100.destroy()
        p6_matrix.destroy()
        p3_matrix.destroy()
        p6_matrix100.destroy()
        p3_matrix100.destroy()


def test_physical_action_builder_selects_requested_level_and_keeps_p6_entrypoint(
    monkeypatch,
) -> None:
    spaces = {3: object(), 6: object()}
    floquets = {
        degree: SimpleNamespace(mpc=object()) for degree in (3, 6)
    }
    setup = {
        "spaces": spaces,
        "floquets": floquets,
        "mesh_data": object(),
        "mesh": SimpleNamespace(comm=PETSc.COMM_SELF),
    }
    calls = {"surface": [], "carrier": [], "dtn": [], "volume": []}

    monkeypatch.setattr(common_forms_module, "_validate_physical_split_profile", lambda _cfg: None)
    monkeypatch.setattr(
        dtn_port_module, "_dtn_surface_quadrature_degree", lambda _cfg, _modes: 11
    )
    monkeypatch.setattr(
        dtn_port_module,
        "_incident_projection_onto_top_mode",
        lambda _mode, _cfg: 0.0j,
    )
    monkeypatch.setattr(
        physical_module,
        "_surface_assemblers",
        lambda space, *_args, **_kwargs: calls["surface"].append(space) or {"a": 1},
    )
    monkeypatch.setattr(
        dtn_module,
        "build_fullspace_dtn_carrier_from_surface",
        lambda modes, _assemblers, mpc, _cfg: calls["carrier"].append(
            (modes, mpc)
        )
        or _Disposable("carrier"),
    )
    monkeypatch.setattr(
        dtn_module,
        "build_fullspace_dtn_action",
        lambda carrier, comm: calls["dtn"].append((carrier, comm))
        or _Disposable("dtn"),
    )
    monkeypatch.setattr(
        physical_module,
        "_build_split_volume_action",
        lambda _mesh_data, _cfg, space, _floquet, **_kwargs: calls["volume"].append(
            space
        )
        or _Disposable("volume"),
    )
    monkeypatch.setattr(
        physical_action_module,
        "FullspacePhysicalAction",
        _FakePhysicalAction,
    )

    mode_inventory = (("mode",), ({"mode_index": 0},), "mode-sha")
    bundle3 = build_same_mesh_physical_action(
        setup, SimpleNamespace(), 3, mode_inventory=mode_inventory
    )
    bundle6 = build_same_mesh_physical_action(
        setup, SimpleNamespace(), 6, mode_inventory=mode_inventory
    )
    try:
        assert calls["surface"] == [spaces[3], spaces[6]]
        assert calls["volume"] == [spaces[3], spaces[6]]
        assert [item[1] for item in calls["carrier"]] == [
            floquets[3].mpc,
            floquets[6].mpc,
        ]
        assert bundle3["degree"] == 3
        assert bundle6["degree"] == 6
        assert bundle3["physical_action"] is bundle3["action"]
        assert bundle6["physical_action"] is bundle6["action"]
    finally:
        destroy_same_mesh_physical_action(bundle3)
        destroy_same_mesh_physical_action(bundle6)

    signature = inspect.signature(build_same_mesh_physical_action)
    assert tuple(signature.parameters)[:3] == ("setup", "cfg", "degree")
    assert "mode_inventory" in signature.parameters
    assert destroy_same_mesh_physical_action.__name__.startswith("destroy_")
    old_signature = inspect.signature(physical_module.build_p6_same_mesh_physical_bundle)
    assert tuple(old_signature.parameters) == ("cfg", "comm", "stage_callback")


def test_small_probe_contract_reuses_physical_rhs_and_rejects_missing_r3(
    monkeypatch,
) -> None:
    assert pcoarse.SMALL_PHYSICAL_PROBE_NAMES == (
        "random",
        "gradient",
        "curl",
        "checkerboard",
        "physical_component_derived",
        "r3_long_tail_derived",
    )
    p3_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    high_rhs = p3_matrix.createVecLeft()
    high_rhs.array[:] = (1.0 + 0.5j, 2.0, -1.0j, 0.25)
    expected = high_rhs.array.copy()

    def fake_physical_rhs(_bundle):
        return high_rhs, {"generation": "dtn_port_modal_physical_rhs"}

    monkeypatch.setattr(physical_module, "build_physical_rhs", fake_physical_rhs)
    try:
        source, facts = pcoarse.build_small_same_mesh_probe_source(
            {
                "p6_action": {},
                "setup": {
                    "p3_matrix": p3_matrix,
                    "p63_owner_transfer": _Transfer(),
                },
            },
            "physical_component_derived",
        )
        assert np.array_equal(source.array, expected)
        assert facts["formula"] == "physical_rhs_compose_then_p63_adjoint"
        assert facts["dual_role"] == "full_fe_dual"
        source.destroy()
    finally:
        p3_matrix.destroy()

    with pytest.raises(NotImplementedError, match="R3 requires canonical full-FE dual packets"):
        pcoarse.build_small_same_mesh_probe_source({}, "r3_long_tail_derived")
