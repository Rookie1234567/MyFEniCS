"""Pure focused contracts for the V16 physical p-coarse core."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.common_3d_forms as common_forms_module
import src.solvers.dtn_port_3d as dtn_port_module
import src.solvers.fullspace_dtn_action as dtn_module
import src.solvers.fullspace_physical_action as physical_action_module
import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical_module
import src.solvers.fullspace_same_mesh_physical_pcoarse as pcoarse
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    build_nonmatching_hcurl_primal_bridge,
    destroy_nonmatching_hcurl_primal_bridge,
    extract_canonical_full_fe_packets,
    reconstruct_canonical_full_fe_function,
)
from src.solvers.fullspace_memory_first_krylov import destroy_krylov_result
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
    destroy_same_mesh_physical_action,
)
from src.test.test_46_task033_high_order_floquet_topology import _fixed_target_fixture


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
        self.adjoint_inputs = []

    def apply_adjoint_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.adjoint_inputs.append(source.array.copy())
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


@pytest.mark.parametrize("degree", (3, 6))
def test_physical_rhs_uses_bundle_degree_for_form_and_mpc(
    monkeypatch, degree: int
) -> None:
    spaces = {3: object(), 6: object()}
    mpcs = {3: object(), 6: object()}
    forms = []
    assembled = []

    class _Vector:
        def __init__(self) -> None:
            self.destroyed = False

        def duplicate(self):
            return _Vector()

        def destroy(self) -> None:
            self.destroyed = True

    class _Action:
        def __init__(self) -> None:
            self.calls = []

        def compose_physical_rhs(self, base, projections, target) -> None:
            self.calls.append((base, projections, target))

    action = _Action()

    def fake_form(space, mesh_data, cfg):
        form = (space, mesh_data, cfg)
        forms.append(form)
        return form

    def fake_assemble(form, mpc, *, quadrature_degree, jit_options):
        base = _Vector()
        assembled.append((form, mpc, quadrature_degree, jit_options, base))
        return base

    monkeypatch.setattr(dtn_port_module, "_incident_top_traction_form", fake_form)
    monkeypatch.setattr(dtn_port_module, "_assemble_mpc_vector", fake_assemble)
    bundle = {
        "setup": {
            "spaces": spaces,
            "floquets": {
                item: SimpleNamespace(mpc=mpcs[item]) for item in (3, 6)
            },
            "mesh_data": "mesh-data",
        },
        "cfg": "cfg",
        "degree": degree,
        "dtn_quadrature_degree": 25,
        "physical_action": action,
        "incident_projections": ("projection",),
        "modes": ("mode",),
        "mode_sha256": "mode-sha",
    }

    rhs, facts = physical_module.build_physical_rhs(bundle)
    try:
        assert forms == [(spaces[degree], "mesh-data", "cfg")]
        assert assembled[0][:3] == (forms[0], mpcs[degree], 25)
        assert action.calls == [(assembled[0][4], ("projection",), rhs)]
        assert facts["degree"] == degree
    finally:
        rhs.destroy()


def test_small_inner_case_builds_only_p3_p1_and_destroys_borrowed_setup(
    monkeypatch,
) -> None:
    from src.solvers import fullspace_same_mesh_hcurl_pmg_global as positive_module

    cfg = SimpleNamespace(nedelec_degree=3, mesh_target_size=50.0)
    positive = {
        "mesh": "mesh",
        "mesh_data": "mesh-data",
        "fine_space": "p3-space",
        "coarse_space": "p1-space",
        "fine_floquet": SimpleNamespace(mpc="p3-mpc"),
        "coarse_floquet": SimpleNamespace(mpc="p1-mpc"),
    }
    calls = {
        "positive": 0,
        "physical": [],
        "destroy_positive": 0,
        "destroy_physical": 0,
    }

    def fake_positive(_cfg, _comm, *, source_name):
        assert source_name == "random"
        calls["positive"] += 1
        return dict(positive)

    def fake_physical(setup, _cfg, degree, *, mode_inventory):
        calls["physical"].append((setup, degree, mode_inventory))
        return {"action": "p3-action"}

    monkeypatch.setattr(positive_module, "build_small_same_mesh_positive_case", fake_positive)
    monkeypatch.setattr(
        positive_module,
        "destroy_small_same_mesh_positive_case",
        lambda _case: calls.__setitem__(
            "destroy_positive", calls["destroy_positive"] + 1
        ),
    )
    monkeypatch.setattr(
        physical_module, "build_same_mesh_physical_action", fake_physical
    )
    monkeypatch.setattr(
        physical_module,
        "destroy_same_mesh_physical_action",
        lambda _physical: calls.__setitem__(
            "destroy_physical", calls["destroy_physical"] + 1
        ),
    )

    case = pcoarse.build_small_same_mesh_physical_inner_case(
        cfg, "comm", mode_inventory=("modes", "rows", "sha")
    )
    setup, degree, _inventory = calls["physical"][0]
    assert calls["positive"] == 1
    assert degree == 3
    assert set(setup["spaces"]) == {3, 1}
    assert set(setup["floquets"]) == {3, 1}
    assert 6 not in setup["spaces"] and 6 not in setup["floquets"]
    pcoarse.destroy_small_same_mesh_physical_inner_case(case)
    assert calls["destroy_physical"] == calls["destroy_positive"] == 1


def test_small_inner_solver_uses_fixed_5000_step_fgmres_driver(monkeypatch) -> None:
    calls = {}
    rhs = object()
    target = object()
    resource_sample = lambda: {"sampled": True}

    class _Matrix:
        def createVecLeft(self):
            calls["created_target"] = True
            return target

    class _Action:
        def apply(self, source, output) -> None:
            calls["action"] = (source, output)

    def fake_pc(_source):
        return "pc-result"

    def fake_driver(rhs_arg, action, pc, **kwargs):
        calls["rhs"] = rhs_arg
        calls["pc"] = pc
        calls["kwargs"] = kwargs
        action(rhs_arg)
        return {"final_solution": target}

    monkeypatch.setattr(pcoarse, "run_restart20_cycles", fake_driver)
    case = {
        "physical_action": {"action": _Action()},
        "fine_matrix": _Matrix(),
        "pmg": SimpleNamespace(apply=fake_pc),
    }
    result = pcoarse.solve_small_same_mesh_physical_inner(
        case, rhs, resource_sample=resource_sample
    )
    kwargs = calls["kwargs"]
    assert result["final_solution"] is target
    assert calls["rhs"] is rhs
    assert calls["action"] == (rhs, target)
    assert calls["pc"] is fake_pc
    assert kwargs["max_it"] == 5000
    assert kwargs["residual_limit"] == 1.0e-6
    assert kwargs["resource_sample"] is resource_sample
    assert kwargs["start_iteration"] == 0
    assert kwargs["checkpoint_writer"] is None
    assert kwargs["first_checkpoint_iteration"] is None
    assert kwargs["checkpoint_interval"] == 20
    assert kwargs["stop_on_true_residual"] is True
    assert kwargs["ksp_type"] == "fgmres"
    assert "initial_solution" not in kwargs


def test_surface_quadrature_degree_is_integral_metadata() -> None:
    coordinate_element = element(
        "Lagrange", "triangle", 1, shape=(2,), dtype=np.float64
    )
    domain = ufl.Mesh(coordinate_element)
    measure = ufl.Measure(
        "ds",
        domain=domain,
        metadata={"custom": "keep", "quadrature_rule": "vertex"},
    )
    form = 2.0 * measure(7) + 3.0 * measure(8)
    original = form.integrals()
    original_metadata = [dict(integral.metadata()) for integral in original]
    original_integrands = [str(integral.integrand()) for integral in original]

    assert dtn_port_module._with_quadrature_degree(form, None) is form
    rewritten = dtn_port_module._with_quadrature_degree(form, 25)
    assert rewritten is not form
    assert [dict(integral.metadata()) for integral in form.integrals()] == (
        original_metadata
    )
    assert [str(integral.integrand()) for integral in rewritten.integrals()] == (
        original_integrands
    )
    for integral in rewritten.integrals():
        assert integral.metadata()["quadrature_degree"] == 25
        assert integral.metadata()["custom"] == "keep"
        assert integral.metadata()["quadrature_rule"] == "vertex"

    entrances = (
        dtn_port_module._assemble_mpc_vector,
        dtn_port_module._assemble_unconstrained_vector,
        dtn_port_module._ReusableSurfaceComponentAssembler.__init__,
        dtn_port_module._mode_projection_from_solution,
        dtn_port_module._surface_scalar,
    )
    for entrance in entrances:
        source = inspect.getsource(entrance)
        assert "_with_quadrature_degree" in source
        assert "form_compiler_options" not in source


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


def test_r3_long_tail_composes_current_rhs_action_and_p63(monkeypatch) -> None:
    p6_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    p3_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    action = _Action(p6_matrix)
    transfer = _Transfer()
    setup = {
        "p6_shell": SimpleNamespace(matrix=p6_matrix),
        "p3_matrix": p3_matrix,
        "p63_owner_transfer": transfer,
    }
    case = {"setup": setup, "p6_action": {"action": action}}
    mapped = p6_matrix.createVecRight()
    mapped.array[:] = (1.0 + 0.5j, -2.0j, 0.25 + 1.0j, 3.0 - 0.5j)
    mapped_before = mapped.array.copy()
    rhs_values = np.asarray(
        (2.0 - 0.5j, 1.0 + 0.25j, -1.0j, 4.0 + 0.5j), dtype=np.complex128
    )
    rhs_vectors = []

    def fake_physical_rhs(_bundle):
        rhs = p6_matrix.createVecLeft()
        rhs.array[:] = rhs_values
        rhs_vectors.append(rhs)
        return rhs, {"generation": "dtn_port_modal_physical_rhs"}

    monkeypatch.setattr(physical_module, "build_physical_rhs", fake_physical_rhs)
    first = second = None
    try:
        first, first_facts = pcoarse.build_r3_long_tail_derived_probe(
            case, mapped
        )
        second, second_facts = pcoarse.build_r3_long_tail_derived_probe(
            case, mapped
        )
        expected = rhs_values - np.asarray((2.0, 3.0, 4.0, 5.0)) * mapped_before
        np.testing.assert_allclose(first.array, expected, atol=1.0e-12, rtol=0.0)
        np.testing.assert_allclose(second.array, expected, atol=1.0e-12, rtol=0.0)
        assert np.array_equal(mapped.array, mapped_before)
        assert all(
            np.array_equal(values, expected) for values in transfer.adjoint_inputs
        )
        assert first_facts["formula"] == "r50=b50-A6*x50; r3=P63^H*r50"
        assert first_facts["mapped_primal_authority_role"] == "full_fe"
        assert first_facts["mapped_primal_action_storage"] == "fullspace_slave_zero"
        assert first_facts["residual_role"] == "full_fe_dual"
        assert first_facts["probe_role"] == "full_fe_dual"
        assert second_facts["physical_rhs_facts"] == {
            "generation": "dtn_port_modal_physical_rhs"
        }
        assert action.calls == 2
        assert transfer.adjoint_calls == 2
        assert len(rhs_vectors) == 2
    finally:
        if first is not None:
            first.destroy()
        if second is not None:
            second.destroy()
        mapped.destroy()
        p6_matrix.destroy()
        p3_matrix.destroy()


def test_action_identity_homogenizes_transferred_full_primal(monkeypatch) -> None:
    p6_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    p3_matrix = _diagonal((2.0, 3.0, 4.0, 5.0))
    seen = []
    algebraic_vectors = []

    class _CapturingAction(_Action):
        def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            seen.append(source.array.copy())
            super().apply(source, target)

    class _TransferWithSlave(_Transfer):
        def apply_primal_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            super().apply_primal_into(source, target)
            target.array[0] = 7.0

    class _FakeFunction:
        def __init__(self, _space: object) -> None:
            vector = p6_matrix.createVecRight()
            algebraic_vectors.append(vector)
            self.x = SimpleNamespace(
                petsc_vec=vector,
                array=vector.array,
                scatter_forward=lambda: None,
            )

    floquet = SimpleNamespace(
        mpc=SimpleNamespace(
            slaves=np.asarray((0,), dtype=np.int32),
            function_space=object(),
            homogenize=lambda field: field.x.petsc_vec.__setitem__(0, 0.0),
        )
    )
    transfer = _TransferWithSlave()
    action = _CapturingAction(p6_matrix)
    source = p3_matrix.createVecRight()
    source.array[:] = (1.0, -2.0j, 0.5 + 1.0j, 3.0)
    setup = {
        "p6_shell": SimpleNamespace(matrix=p6_matrix),
        "p3_matrix": p3_matrix,
        "p63_owner_transfer": transfer,
        "floquets": {6: floquet},
    }
    case = {
        "setup": setup,
        "p3_action": {"action": _Action(p3_matrix)},
        "p6_action": {"action": action},
    }
    import src.solvers.fullspace_same_mesh_hcurl_pmg_runtime as runtime_module

    monkeypatch.setattr(fem, "Function", _FakeFunction)
    monkeypatch.setattr(
        runtime_module,
        "_mpc_constraint_residual",
        lambda field, _floquet: float(abs(field.x.array[0])),
    )
    monkeypatch.setattr(
        runtime_module,
        "_slave_storage_max",
        lambda field, _floquet: float(abs(field.x.array[0])),
    )
    direct = composed = None
    try:
        direct, composed, facts = pcoarse.measure_small_same_mesh_physical_action_identity(
            case, source
        )
        assert seen[0][0] == 0.0
        assert facts["projected_full_constraint_residual"] == 7.0
        assert facts["algebraic_owned_slave_max"] == 0.0
        assert facts["phase_application"] == "finalized_floquet_mpc_once"
    finally:
        if direct is not None:
            direct.destroy()
        if composed is not None:
            composed.destroy()
        source.destroy()
        for vector in algebraic_vectors:
            vector.destroy()
        p6_matrix.destroy()
        p3_matrix.destroy()


def test_nonmatching_hcurl_primal_bridge_roundtrip() -> None:
    source_cfg, source_mesh_data, source_space = _fixed_target_fixture(
        3, h_nm=25.0
    )
    target_cfg, target_mesh_data, target_space = _fixed_target_fixture(
        3, h_nm=50.0
    )
    source_floquet = build_double_floquet_mpc(
        source_space, source_mesh_data, source_cfg
    )
    target_floquet = build_double_floquet_mpc(
        target_space, target_mesh_data, target_cfg
    )
    source_cells = source_mesh_data.mesh.topology.index_map(
        source_mesh_data.mesh.topology.dim
    ).size_global
    target_cells = target_mesh_data.mesh.topology.index_map(
        target_mesh_data.mesh.topology.dim
    ).size_global
    assert int(source_cells) != int(target_cells)
    source_field = fem.Function(source_floquet.mpc.function_space)
    source_field.interpolate(
        lambda x: np.vstack(
            (
                x[0] + 0.25j * x[1],
                x[1] - 0.5j * x[2],
                x[2] + 0.75j * x[0],
            )
        )
    )
    source_field.x.scatter_forward()
    source_floquet.mpc.homogenize(source_field)
    source_field.x.scatter_forward()
    source_floquet.mpc.backsubstitution(source_field)
    source_field.x.scatter_forward()
    source_before = source_field.x.array.copy()
    bridge = None
    bridge_repeat = None
    restored = None
    try:
        bridge = build_nonmatching_hcurl_primal_bridge(
            source_field, target_space, target_floquet
        )
        assert bridge["audit"] == {
            "schema": "task038.nonmatching_hcurl_primal_bridge.v1",
            "method": "dolfinx.create_interpolation_data+interpolate_nonmatching",
            "padding": 1.0e-10,
            "target_mpc_homogenize_count": 1,
            "target_mpc_backsubstitution_count": 1,
            "global_matrix": False,
            "numeric_allgather": False,
        }
        assert np.array_equal(source_field.x.array, source_before)
        target_function_space = target_floquet.mpc.function_space
        local_size = int(target_function_space.dofmap.index_map.size_local)
        owned_slaves = np.asarray(target_floquet.mpc.slaves, dtype=np.int64)
        owned_slaves = owned_slaves[
            (owned_slaves >= 0) & (owned_slaves < local_size)
        ]
        assert bridge["action_vector"].norm() > 0.0
        assert bridge["canonical_field"].x.petsc_vec.norm() > 0.0
        comm = target_function_space.mesh.comm
        owned_slave_count = comm.allreduce(len(owned_slaves), op=MPI.SUM)
        local_action_slave_max = float(
            np.max(
                np.abs(bridge["action_vector"].array[owned_slaves]),
                initial=0.0,
            )
        )
        local_canonical_slave_max = float(
            np.max(
                np.abs(bridge["canonical_field"].x.array[owned_slaves]),
                initial=0.0,
            )
        )
        action_slave_max = comm.allreduce(
            local_action_slave_max,
            op=MPI.MAX,
        )
        canonical_slave_max = comm.allreduce(
            local_canonical_slave_max,
            op=MPI.MAX,
        )
        assert owned_slave_count > 0
        assert action_slave_max == 0.0
        assert canonical_slave_max > 0.0
        bridge_repeat = build_nonmatching_hcurl_primal_bridge(
            source_field, target_space, target_floquet
        )
        np.testing.assert_array_equal(
            bridge["action_vector"].array, bridge_repeat["action_vector"].array
        )
        packets, _audit = extract_canonical_full_fe_packets(
            target_function_space,
            bridge["canonical_field"].x.petsc_vec,
            target_floquet,
        )
        repeat_packets, _repeat_audit = extract_canonical_full_fe_packets(
            target_function_space,
            bridge_repeat["canonical_field"].x.petsc_vec,
            target_floquet,
        )
        repeat_comparison = compare_canonical_packets(
            packets, repeat_packets, relative_tolerance=1.0e-12
        )
        assert repeat_comparison["pass"], repeat_comparison
        restored = reconstruct_canonical_full_fe_function(
            target_function_space, packets, target_floquet
        )
        restored_packets, _restored_audit = extract_canonical_full_fe_packets(
            target_function_space, restored.x.petsc_vec, target_floquet
        )
        comparison = compare_canonical_packets(
            packets, restored_packets, relative_tolerance=1.0e-12
        )
        assert comparison["pass"], comparison
        assert np.all(np.isfinite(bridge["action_vector"].array))
        assert np.all(np.isfinite(bridge["canonical_field"].x.array))
    finally:
        destroy_nonmatching_hcurl_primal_bridge(bridge_repeat)
        destroy_nonmatching_hcurl_primal_bridge(bridge)
