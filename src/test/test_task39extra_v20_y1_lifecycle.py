"""Focused Y1 tests for the V20 cache, ownership, and release contract."""

from __future__ import annotations

import hashlib
import json
import gc
from pathlib import Path
from types import SimpleNamespace
import weakref

import numpy as np
import pytest
import ufl
import dolfinx_mpc
from basix.ufl import element
from dolfinx import default_real_type, fem, jit, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    DUAL_CELL_CONDENSED_PROFILE,
    LOWMEM_DUAL_CELL_CONDENSED_PROFILE,
    profile_facts,
)
from src.runners import task038_launcher as launcher
from src.runners.physical_p4_cell_condensed_v18 import cell_condensed_stack
from src.runners.physical_retained_outer_adapter import (
    _compiled_form_identity,
    _identity_cache_facts,
    RetainedOuterAdapter,
    prepare_dual_condensed_forms,
)
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    recover_owned_cell_interiors,
)
from src.solvers.p4_cell_condensed_inverse import P4CellCondensedInverse
from src.solvers.physical_interface_balanced import InterfaceBalancedCoupling
from src.test.test_115_task035b_assembly_time_condensation import _two_cell_problem
from src.test.test_task39extra_v18_stack_fixture import TinyRuntime
from src.test.test_task39extra_v19_p6_cell_condensed_action import _problem


ROOT = Path(__file__).resolve().parents[2]
V20_CASE = ROOT / "input/task39extra/v20_y3_lowmem_original.dat"


def _small_form(*, degree: int = 2):
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tags = mesh.meshtags(
        domain,
        domain.topology.dim,
        np.asarray([0], dtype=np.int32),
        np.asarray([1], dtype=np.int32),
    )
    space = fem.functionspace(
        domain,
        element("N1curl", domain.basix_cell(), degree, dtype=default_real_type),
    )
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    expression = (
        ufl.inner(ufl.curl(trial), ufl.curl(test))
        + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(trial, test)
    ) * dx(1)
    return domain, tags, space, expression


def test_shared_identity_recovers_a_nonzero_internal_rhs_from_a_real_form():
    domain, tags, space, expression = _small_form()
    compiled = fem.form(expression)
    condensed = None
    full = None
    rhs = None
    try:
        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            space,
            tags,
            strict_local_checks=True,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            share_identity_cache=True,
        )
        identity = _identity_cache_facts(condensed)
        assert identity["semantic"]["operator"] == "identity"
        assert identity["representation"]["read_only"] is True
        assert identity["representation"]["unique_storage_count"] == 1
        assert condensed.build_audit["identity_cache_readonly"] is True

        full = fem_petsc.assemble_matrix(compiled, bcs=[])
        full.assemble()
        rhs = full.createVecRight()
        rhs.array[:] = np.arange(1, condensed.full_rows + 1, dtype=np.complex128)
        rhs.assemble()
        active = np.zeros(condensed.active_rows, dtype=np.complex128)
        recovered = recover_owned_cell_interiors(
            condensed, active, full_rhs=rhs
        )
        assert recovered
        assert any(np.linalg.norm(values) > 0.0 for _rows, values in recovered)
        for rows, values in recovered:
            global_rows = [int(row) for row in rows]
            matrix_ii = np.asarray(full.getValues(global_rows, global_rows))
            rhs_i = np.asarray(rhs.getValues(global_rows), dtype=np.complex128)
            np.testing.assert_allclose(
                values,
                np.linalg.solve(matrix_ii, rhs_i),
                rtol=2.0e-11,
                atol=2.0e-11,
            )
    finally:
        if rhs is not None:
            rhs.destroy()
        if full is not None:
            full.destroy()
        if condensed is not None:
            condensed.destroy()


def test_small_form_is_precompiled_reused_and_postprocesses_with_same_jit_options(
    tmp_path, monkeypatch
):
    domain, tags, space, expression = _small_form(degree=1)
    cache_dir = tmp_path / "fenics-cache"
    cache_dir.mkdir()
    options = {
        "cache_dir": str(cache_dir),
        "cffi_extra_compile_args": ["-O2", "-g0"],
        "cffi_debug": False,
    }
    calls = []
    original = jit.ffcx_jit

    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result[2])
        return result

    monkeypatch.setattr(jit, "ffcx_jit", observed)
    first = fem.form(expression, jit_options=dict(options))
    second = fem.form(expression, jit_options=dict(options))
    first_identity = _compiled_form_identity(first)
    second_identity = _compiled_form_identity(second)
    assert first_identity["dtype"] == second_identity["dtype"] == "complex128"
    assert first_identity["rank"] == second_identity["rank"] == 2
    assert first_identity["module_file"]
    assert first_identity["module_files"] == second_identity["module_files"]
    assert calls
    assert any(any(code is not None for code in returned) for returned in calls)

    from src.postprocessing.postprocess_3d import _field_component_l2_metrics

    cfg = target_stage4_config(degree=1, h_nm=10.0)
    field = fem.Function(space)
    field.x.array[:] = 0.25 + 0.125j
    mesh_data = SimpleNamespace(mesh=domain, cell_tags=tags)
    metrics = _field_component_l2_metrics(
        mesh_data, cfg, field, jit_options=dict(options)
    )
    assert np.isfinite(metrics["component_l2_total_E_V_per_m_sqrt_nm3"])
    assert sum(metrics["component_l2_energy_fraction_Ex_Ey_Ez"]) == pytest.approx(1.0)
    with pytest.raises(TypeError):
        _field_component_l2_metrics(mesh_data, cfg, object(), jit_options=dict(options))


class _DestroyCountingFactor:
    def __init__(self):
        self.destroy_count = 0

    def destroy(self):
        self.destroy_count += 1


def test_p6_owner_handles_normal_error_and_double_cleanup():
    condensed, _block, action = _problem()
    action.owns_condensed = True
    try:
        source = np.ones(action.reduced_size, dtype=np.complex128)
        result = action.apply(source)
        assert np.isfinite(result).all()
        with pytest.raises(ValueError):
            action.apply(np.zeros(action.reduced_size + 1, dtype=np.complex128))
        action.destroy()
        action.destroy()
        assert action._destroyed is True
        assert condensed.matrix is None
        with pytest.raises(RuntimeError):
            action.apply(source)
    finally:
        action.destroy()


def test_p4_owner_handles_error_and_double_cleanup_on_a_real_condensed_matrix():
    _domain, tags, space, expression = _small_form(degree=2)
    compiled = fem.form(expression)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        space,
        tags,
        strict_local_checks=True,
        materialize_global_matrix=True,
    )
    factor = _DestroyCountingFactor()
    inverse = P4CellCondensedInverse(
        condensed, factor, owns_condensed=True, owns_factor=True
    )
    try:
        bad_rhs = PETSc.Vec().createSeq(1, comm=PETSc.COMM_SELF)
        with pytest.raises(ValueError):
            inverse.apply(bad_rhs)
        bad_rhs.destroy()
        inverse.destroy()
        inverse.destroy()
        assert factor.destroy_count == 1
        assert inverse.destroyed is True
        assert inverse.condensed is None
        released_rhs = PETSc.Vec().createSeq(1, comm=PETSc.COMM_SELF)
        with pytest.raises(RuntimeError):
            inverse.apply(released_rhs)
        released_rhs.destroy()
    finally:
        inverse.destroy()


def _tiny_cell_condensed_common():
    domain, tags, space, _compiled = _two_cell_problem(distinct_materials=False)
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    form = (
        ufl.inner(ufl.curl(trial), ufl.curl(test))
        + (2.5 - 0.2j) * ufl.inner(trial, test)
    ) * dx(1)
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.finalize()
    n = space.dofmap.index_map.size_global
    entry = SimpleNamespace(
        coupling_rows=np.array([], dtype=PETSc.IntType),
        coupling_values=np.array([], dtype=np.complex128),
        projection_rows=np.array([], dtype=PETSc.IntType),
        projection_values=np.array([], dtype=np.complex128),
        normalization_h=1.0,
    )
    carrier = SimpleNamespace(entries=(entry,), global_rows=n)
    common = {
        "levels": {
            "mesh": domain,
            "mesh_data": SimpleNamespace(cell_tags=tags),
            "spaces": {4: space, 6: space},
            "floquets": {4: SimpleNamespace(mpc=mpc), 6: SimpleNamespace(mpc=mpc)},
        },
        "p4": {
            "volume_action": SimpleNamespace(bilinear_form=form),
            "dtn_action": SimpleNamespace(carrier=carrier),
        },
        "fine": {
            "mode_sha256": "m" * 64,
            "dtn_action": SimpleNamespace(carrier=carrier),
        },
        "quadrature": [{"quadrature_degree": 4}, {"quadrature_degree": 4}],
    }
    return domain, common


def test_actual_v20_p4_release_hook_streams_matrix_and_is_idempotent():
    _domain, common = _tiny_cell_condensed_common()
    runtime = TinyRuntime()
    with cell_condensed_stack(
        runtime,
        common,
        {},
        stage="Y3_FIXTURE",
        matrix_lifecycle_policy="MATRIX_RETAINED_BACKEND_DEPENDENCY",
    ) as stack:
        inverse, factor, condensed = (
            stack["inverse"],
            stack["factor"],
            stack["condensed"],
        )
        release = stack["release_after_final_residual"]
        facts = release()
        assert facts["status"] == "RELEASED"
        assert facts["matrix_identity_before_release_consistent"] is True
        assert facts["matrix_identity_before_release_seconds"] >= 0.0
        assert inverse.destroyed is True
        assert factor.destroyed is True
        assert condensed.matrix.handle == 0
        assert stack["released_after_final_residual"] is True
        assert release() == {"status": "ALREADY_RELEASED"}
        assert any(
            name == "v20_p4_matrix_identity_before_release"
            for name, _facts in runtime.events
        )


class _AdapterRuntime:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.source_sha = "s" * 40
        self.events = []

    def marker(self, name, facts):
        self.events.append((name, dict(facts)))

    def release_workspace(self, _label):
        return None

    def release_inventory(self, _label):
        return None


class _Owner:
    def __init__(self):
        self.destroy_count = 0
        self.audit = {}

    def destroy(self):
        self.destroy_count += 1


def test_actual_retained_adapter_release_clears_owner_refs_and_repeats_safely(
    tmp_path,
):
    runtime = _AdapterRuntime(tmp_path)
    owner = _Owner()
    weak_owner = weakref.ref(owner)
    adapter = RetainedOuterAdapter(
        runtime,
        owner,
        owner,
        None,
        None,
        p4_identity_sha256="p" * 64,
        pc_counts=lambda: {},
        identity_cache_mode="shared_read_only_per_interior_shape",
        evidence_prefix="v20",
    )
    adapter.action = _Owner()
    adapter.condensed = _Owner()
    adapter.rhs = _Owner()
    adapter.full_source = _Owner()
    adapter.full_target = _Owner()
    adapter.bal_h = owner
    adapter.full_rhs = owner
    adapter.cache = {}
    adapter._final_packet_saved = True
    facts = adapter.release_after_final_residual()
    assert facts["status"] == "RELEASED"
    assert adapter.release_after_final_residual() == {"status": "ALREADY_RELEASED"}
    assert adapter.common is None
    assert adapter.resolved is None
    assert adapter.bal_h is None
    assert adapter.full_rhs is None
    del owner
    gc.collect()
    assert weak_owner() is None

    error_adapter = RetainedOuterAdapter(
        runtime,
        None,
        None,
        None,
        None,
        p4_identity_sha256="p" * 64,
        pc_counts=lambda: {},
        evidence_prefix="v20",
    )
    with pytest.raises(RuntimeError, match="complete field packet"):
        error_adapter.release_after_final_residual()
    error_adapter.destroy()


def test_v20_entry_passes_legacy_complete_packet_contract_to_real_outer_factory(
    tmp_path, monkeypatch
):
    """The reviewed V20 entry must resolve its old default before adapter creation."""

    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import physical_dual_cell_condensed_lowmem_v20 as worker
    from src.runners import physical_p4_cell_condensed_v18 as p4_worker
    from src.runners import physical_p4_schur_v14 as v14_worker
    from src.runners import physical_retained_outer_adapter as retained_worker

    class FakeRuntime:
        time_policy = "observe_only"
        shared_budget = {}
        contract = {"resources": {}}
        source_sha = "s" * 40

        def __init__(self):
            self.directory = Path(tmp_path)

        def sample(self, _label):
            return {}

        def marker(self, _name, _facts=None):
            return None

        def set_phase(self, _phase):
            return None

    runtime = FakeRuntime()
    captured = {}
    payload = {
        "solver": {
            "preconditioner": LOWMEM_DUAL_CELL_CONDENSED_PROFILE,
            "stage": "Y3_ORIGINAL",
        },
        "derived": {
            "physical_intermediate_profile": profile_facts(
                LOWMEM_DUAL_CELL_CONDENSED_PROFILE
            )
        },
    }

    monkeypatch.setattr(v14_worker, "_V14Runtime", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(v14_worker, "_abi_facts", lambda: {})
    monkeypatch.setattr(v14_worker, "_repo_root", lambda: Path(tmp_path))
    monkeypatch.setattr(v14_worker, "_build_common", lambda *args, **kwargs: {})
    monkeypatch.setattr(v14_worker, "_destroy_common", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        v14_worker, "_v14_known_preallocation_gate", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        v14_worker,
        "_v14_q4_q5_fullspace",
        lambda runtime_, common_, resolved_, **kwargs: (
            kwargs["outer_adapter_factory"](
                runtime_, common_, resolved_, None, None
            ),
            {"stage_pass": False},
        )[1],
    )
    monkeypatch.setattr(
        retained_worker,
        "prepare_dual_condensed_forms",
        lambda *args, **kwargs: (
            {"p4_condensation": object(), "p6_condensation": object()},
            {"jit_options": {}},
        ),
    )

    def fake_outer_factory(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(retained_worker, "build_retained_outer_adapter", fake_outer_factory)
    monkeypatch.setattr(
        p4_worker,
        "cell_condensed_stack",
        lambda *args, **kwargs: pytest.fail("V20 mock must not enter p4 stack"),
    )
    monkeypatch.setattr(
        "src.io.input_validation.simulation_config_3d_from_normalized",
        lambda _payload: object(),
    )

    result = worker.run_physical_dual_cell_condensed_lowmem_v20(
        payload, tmp_path, source_sha="s" * 40
    )

    assert result["passed"] is False
    assert captured["save_complete_field_packet"] is True
    assert captured["evidence_prefix"] == "v20"


def test_prepare_dual_condensed_forms_real_small_common_has_nine_official_kernels(
    tmp_path,
):
    domain, tags, space, expression = _small_form(degree=1)

    class PrepareRuntime:
        def __init__(self):
            self.directory = Path(tmp_path) / "prepared-run"
            self.events = []

        def marker(self, name, facts):
            self.events.append((name, dict(facts)))

    runtime = PrepareRuntime()
    common = {
        "fine": {"volume_action": SimpleNamespace(bilinear_form=expression)},
        "p4": {"volume_action": SimpleNamespace(bilinear_form=expression)},
        "levels": {
            "mesh_data": SimpleNamespace(mesh=domain, cell_tags=tags),
            "floquets": {
                6: SimpleNamespace(mpc=SimpleNamespace(function_space=space))
            },
        },
        "cfg": target_stage4_config(degree=1, h_nm=10.0),
    }
    prepared, facts = prepare_dual_condensed_forms(runtime, common)
    try:
        expected = {
            *(f"postprocess_component_l2_{i}" for i in range(3)),
            *(f"rta_region_{quantity}_{region}"
              for quantity in ("volume", "absorption")
              for region in ("grating", "substrate")),
            "postprocess_E_to_H_expression",
            "diffraction_E_to_H_expression",
        }
        assert facts["official_evaluation_role_count"] == 9
        assert {row["role"] for row in facts["official_evaluation_roles"]} == expected
        assert facts["roles"]["p6_condensation"]["rank"] == 2
        assert facts["roles"]["p4_condensation"]["rank"] == 2
        assert facts["cache"]["source_cache_untouched"] is True
        json.dumps(facts, allow_nan=False)
    finally:
        prepared.clear()
        gc.collect()


def _vec(values):
    result = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
    result.array[:] = values
    return result


def _zero_fint(source):
    return _vec(np.zeros_like(source.array_r)), {"fixture": "zero"}


def test_balanced_pc_owner_handles_normal_error_and_double_cleanup():
    def identity_transfer(source):
        return _vec(source.array_r)

    pc = InterfaceBalancedCoupling(
        lambda source: _vec(source.array_r),
        lambda source: _vec(np.zeros_like(source.array_r)),
        SimpleNamespace(
            apply_adjoint=identity_transfer,
            apply_primal=identity_transfer,
        ),
        SimpleNamespace(apply_with_facts=_zero_fint),
        lambda source: _vec(np.zeros_like(source.array_r)),
        save=lambda *_args: None,
    )
    source = _vec([1.0 + 0.25j, -0.5 + 0.75j])
    output = pc.apply(source)
    output.destroy()
    assert pc.apply_count == 1
    pc.destroy()
    pc.destroy()
    assert pc._destroyed is True
    with pytest.raises((TypeError, AttributeError)):
        pc.apply(source)
    source.destroy()

    class FailingFint:
        def apply_with_facts(self, _source):
            raise RuntimeError("fixture failure")

    failing = InterfaceBalancedCoupling(
        lambda value: _vec(value.array_r),
        lambda value: _vec(np.zeros_like(value.array_r)),
        SimpleNamespace(
            apply_adjoint=identity_transfer,
            apply_primal=identity_transfer,
        ),
        FailingFint(),
        lambda value: _vec(np.zeros_like(value.array_r)),
        save=lambda *_args: None,
    )
    failed_source = _vec([1.0, 2.0])
    try:
        with pytest.raises(RuntimeError, match="fixture failure"):
            failing.apply(failed_source)
    finally:
        failing.destroy()
        failing.destroy()
        failed_source.destroy()


def test_v20_profile_input_and_ledger_replay_boundaries(tmp_path, monkeypatch):
    v19_before = profile_facts(DUAL_CELL_CONDENSED_PROFILE)
    resolved = load_and_resolve(V20_CASE)
    assert resolved.solver["stage"] == "Y3_ORIGINAL"
    v20 = profile_facts(LOWMEM_DUAL_CELL_CONDENSED_PROFILE)
    assert v20["identity"] == LOWMEM_DUAL_CELL_CONDENSED_PROFILE
    assert v20["resources"]["time_policy"] == "observe_only"
    assert set(v20["resources"]["stage_budgets"]) == {"Y3_ORIGINAL"}
    assert v20["gates"]["shared_identity_readonly"] is True
    assert profile_facts(DUAL_CELL_CONDENSED_PROFILE) == v19_before

    predecessor_path = launcher._dual_condensed_v19_shared_ledger_path(tmp_path)
    predecessor_path.parent.mkdir(parents=True, exist_ok=True)
    predecessor = {
        "schema": "task039extra.v19.shared-workflow-ledger.v1",
        "batch_identity": "review_v19_p6_p4_cell_condensed",
        "total_budget_seconds": 43200.0,
        "elapsed_seconds": 12.0,
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [],
        "fresh_worker_count": 1,
        "source_attempts": [],
        "stages": {},
        "unique_bug_replay_count": 0,
        "predecessors": {"v18": {"read_only": True, "sha256": "v" * 64}},
    }
    predecessor_path.write_text(json.dumps(predecessor), encoding="utf-8")
    monkeypatch.setattr(
        launcher,
        "V20_PREDECESSOR_V19_LEDGER_SHA256",
        hashlib.sha256(predecessor_path.read_bytes()).hexdigest(),
    )

    def reserve(source, run):
        return launcher._reserve_v20_shared_budget(
            tmp_path,
            run,
            source_sha=source,
            stage="Y3_ORIGINAL",
            stage_budget={"workflow_seconds": 43200, "solve_seconds": 43200},
            workflow_clock_start={"monotonic_seconds": 1.0, "boottime_seconds": 1.0, "utc_seconds": 1.0},
            time_policy="observe_only",
        )

    def settle_as_worker_failure(lease, fixed_source):
        ledger = json.loads(Path(lease["path"]).read_text(encoding="utf-8"))
        attempt = ledger["stages"][lease["stage"]]["attempts"][lease["attempt_index"]]
        run_directory = Path(attempt["run_directory"])
        run_directory.mkdir(parents=True, exist_ok=True)
        failed_source = attempt["source_sha"]
        (run_directory / "implementation_bug_replay.json").write_text(
            json.dumps(
                {
                    "classification": "IMPLEMENTATION_BUG",
                    "stage": "Y3_ORIGINAL",
                    "failed_source_sha": failed_source,
                    "fixed_source_sha": fixed_source,
                    "bug_and_fix": "Y1 focused replay fixture",
                }
            ),
            encoding="utf-8",
        )
        (run_directory / "physical_dual_condensed_memory_v20_summary.json").write_text(
            json.dumps(
                {
                    "status": "FAILED",
                    "result_classification": "WORKER_FAILED",
                    "source_sha": failed_source,
                    "error": "Y1 focused worker exception",
                }
            ),
            encoding="utf-8",
        )
        launcher._settle_v14_shared_budget(
            lease,
            status="WORKER_FAILED",
            authority=None,
            parent_interval={"budget_seconds": 1.0},
            parent_clock_end={
                "monotonic_seconds": 2.0,
                "boottime_seconds": 2.0,
                "utc_seconds": 2.0,
            },
        )

    first = reserve("a" * 40, tmp_path / "first")
    ledger = json.loads(Path(first["path"]).read_text(encoding="utf-8"))
    assert ledger["elapsed_seconds"] == 0.0
    assert ledger["predecessor_v19_ledger"]["historical_effective_budget_snapshot"]["measured_elapsed_seconds"] == 12.0
    with pytest.raises(InputError, match="unsettled"):
        reserve("b" * 40, tmp_path / "blocked")
    settle_as_worker_failure(first, "b" * 40)
    replay = reserve("b" * 40, tmp_path / "replay")
    assert replay["replay"] is True
    settle_as_worker_failure(replay, "c" * 40)
    with pytest.raises(InputError, match="exhausted"):
        reserve("c" * 40, tmp_path / "third")
