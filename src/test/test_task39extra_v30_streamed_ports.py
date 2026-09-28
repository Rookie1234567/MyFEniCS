"""L4 streamed-port diagnostics for Task39extra V30."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import json
import time

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from src.solvers.p6_cell_condensed_action import (
    P6CellCondensedAction,
    P6CellPortTerms,
    build_p6_cell_condensed_action_from_carrier,
)


@contextmanager
def _real_v30_80_mode_case(
    tmp_path: Path, *, degree: int = 6, materialize_global_matrix: bool = False,
    build_port_actions: bool = True,
):
    """Build the actual V30 Fourier carrier on a reduced physical FE mesh."""

    from dolfinx import fem
    import ufl

    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )

    setup_started = time.perf_counter()
    resolved = load_and_resolve(
        "input/task39extra/v30_workstation_guided_original_h7p5.dat"
    )
    cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
    degree = int(degree)
    cfg = replace(
        cfg,
        mesh_target_size=60.0,
        nedelec_degree=degree,
        visualization_degree=degree,
        mesh_axis_cell_counts=None,
        mesh_axis_x_values=None,
        mesh_axis_y_values=None,
        mesh_axis_z_values=None,
        mesh_axis_z_profile=None,
        mesh_plan_id=None,
        mesh_plan_sha256=None,
    )
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_SELF, (degree,), include_positive_coefficients=False
    )
    physical = None
    condensed = None
    cached = streamed = None
    try:
        physical = build_same_mesh_physical_action(levels, cfg, degree)
        carrier = physical["dtn_action"].carrier
        assert len(carrier.entries) == 80
        space = levels["spaces"][degree]
        u = ufl.TrialFunction(space)
        v = ufl.TestFunction(space)
        dx = ufl.Measure(
            "dx", domain=levels["mesh_data"].mesh,
            subdomain_data=levels["mesh_data"].cell_tags,
        )
        curl_curl, material_mass = _build_physical_volume_terms(cfg, u, v, dx)
        compiled = fem.form(curl_curl + material_mass)
        owned_cells = int(
            space.mesh.topology.index_map(space.mesh.topology.dim).size_local
        )
        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            space,
            levels["mesh_data"].cell_tags,
            mpc=levels["floquets"][degree].mpc,
            appended_global_rows=len(carrier.entries),
            appended_support_owned_cell_groups=(
                np.arange(owned_cells, dtype=np.int32),
            ),
            appended_support_group_by_row=tuple(
                0 for _ in carrier.entries
            ),
            dense_appended_block=bool(materialize_global_matrix),
            defer_final_assembly=bool(materialize_global_matrix),
            materialize_global_matrix=materialize_global_matrix,
            retain_local_schur_for_matrix_free=True,
            sum_duplicate_cell_integrals=True,
        )
        if build_port_actions:
            cached = build_p6_cell_condensed_action_from_carrier(
                condensed, carrier, port_coupling_mode="cached"
            )
            streamed = build_p6_cell_condensed_action_from_carrier(
                condensed, carrier, port_coupling_mode="streamed"
            )
        yield {
            "resolved": resolved,
            "cfg": cfg,
            "degree": degree,
            "levels": levels,
            "physical": physical,
            "carrier": carrier,
            "condensed": condensed,
            "cached": cached,
            "streamed": streamed,
            "setup_seconds": float(time.perf_counter() - setup_started),
        }
    finally:
        if streamed is not None:
            streamed.destroy()
        if cached is not None:
            cached.destroy()
        if condensed is not None:
            condensed.destroy()
        if physical is not None:
            destroy_same_mesh_physical_action(physical)
        levels.clear()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(left), np.linalg.norm(right), np.finfo(float).tiny)
    )


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="small V30 carrier fixture is serial")
def test_v30_real_80_mode_carrier_streamed_fe_closure(tmp_path: Path) -> None:
    """Exercise the real mode inventory, FE carrier, RHS, recovery and A6 action."""

    with _real_v30_80_mode_case(tmp_path) as case:
        condensed = case["condensed"]
        cached = case["cached"]
        streamed = case["streamed"]
        carrier = case["carrier"]
        physical_action = case["physical"]["physical_action"]
        degree = case["degree"]
        rng = np.random.default_rng(39080)
        storage = np.zeros(condensed.full_rows, dtype=np.complex128)
        active_original = condensed.trace_constraints.owned_active_original_dofs
        storage[active_original] = (
            0.1 * rng.normal(size=len(active_original))
            + 0.1j * rng.normal(size=len(active_original))
        )
        interiors = np.unique(
            np.concatenate(
                [cell.interior_original_dofs for cell in condensed.cell_recovery_maps]
            )
        )
        storage[interiors] = (
            0.1 * rng.normal(size=len(interiors))
            + 0.1j * rng.normal(size=len(interiors))
        )
        storage[np.asarray(case["levels"]["floquets"][degree].mpc.slaves, dtype=np.int64)] = 0.0
        alpha = np.asarray(
            [
                np.dot(entry.projection_values, storage[entry.projection_rows])
                / entry.normalization_h
                for entry in carrier.entries
            ],
            dtype=np.complex128,
        )
        active = np.empty(condensed.active_rows, dtype=np.complex128)
        for original in active_original:
            active_id = condensed.trace_constraints.original_to_active[int(original)]
            active[active_id] = storage[int(original)]
        reduced = np.concatenate((active, alpha))

        def native_apply(field: np.ndarray) -> np.ndarray:
            source = PETSc.Vec().createSeq(condensed.full_rows, comm=PETSc.COMM_SELF)
            target = source.duplicate()
            try:
                source.array[:] = field
                source.assemble()
                physical_action.apply(source, target)
                return np.asarray(target.array, dtype=np.complex128).copy()
            finally:
                target.destroy()
                source.destroy()

        full_rhs = native_apply(storage)
        assert np.linalg.norm(full_rhs) > 0.0
        assert _relative(cached.apply(reduced), streamed.apply(reduced)) <= 1.0e-10
        assert _relative(
            cached.reduce_rhs(full_rhs), streamed.reduce_rhs(full_rhs)
        ) <= 1.0e-10
        cached_storage = cached.recover_storage(reduced, full_rhs=full_rhs)
        streamed_storage = streamed.recover_storage(reduced, full_rhs=full_rhs)
        assert _relative(cached_storage, streamed_storage) <= 1.0e-10
        assert _relative(streamed_storage, storage) <= 1.0e-10
        np.testing.assert_array_equal(
            streamed_storage[np.asarray(case["levels"]["floquets"][degree].mpc.slaves, dtype=np.int64)],
            0.0,
        )

        closure = np.asarray(
            [
                -np.dot(entry.projection_values, streamed_storage[entry.projection_rows])
                + entry.normalization_h * alpha[index]
                for index, entry in enumerate(carrier.entries)
            ],
            dtype=np.complex128,
        )
        closure_scale = max(
            np.linalg.norm(
                [
                    np.dot(entry.projection_values, streamed_storage[entry.projection_rows])
                    for entry in carrier.entries
                ]
            )
            + np.linalg.norm(
                [entry.normalization_h * alpha[i] for i, entry in enumerate(carrier.entries)]
            ),
            np.finfo(float).tiny,
        )
        assert float(np.linalg.norm(closure) / closure_scale) <= 1.0e-10
        residual_facts = streamed.evaluate_native_residual(
            reduced,
            full_rhs,
            native_apply,
            port_rhs=np.zeros(len(carrier.entries), dtype=np.complex128),
            rhs_is_mpc_dual=True,
        )
        for field in (
            "internal_residual_relative",
            "port_residual_relative",
            "native_residual_relative",
            "native_identity_relative",
        ):
            assert residual_facts[field] <= 1.0e-10, (field, residual_facts[field])
        inventory = streamed.buffer_inventory
        assert inventory["transformed_port_payload_bytes_sum"] == 0
        assert inventory["resident_Hhat_bytes"] == 0
        assert inventory["per_cell_transformed_arrays_resident"] is False
        assert streamed.audit["streamed_action_lu_solve_count"] >= 0
        assert streamed.audit["streamed_recovery_lu_solve_count"] >= 0

        operation_functions = {
            "apply": lambda action: action.apply(reduced),
            "reduce_rhs": lambda action: action.reduce_rhs(full_rhs),
            "recover_storage": lambda action: action.recover_storage(
                reduced, full_rhs=full_rhs
            ),
        }
        for action in (cached, streamed):
            for operation in operation_functions.values():
                output = operation(action)
                del output
        samples = {
            mode: {name: [] for name in operation_functions}
            for mode in ("cached", "streamed")
        }
        sample_orders = []
        actions = {"cached": cached, "streamed": streamed}
        for sample_index in range(3):
            order = ("cached", "streamed") if sample_index % 2 == 0 else ("streamed", "cached")
            sample_orders.append(list(order))
            for mode in order:
                for name, operation in operation_functions.items():
                    started = time.perf_counter()
                    output = operation(actions[mode])
                    samples[mode][name].append(float(time.perf_counter() - started))
                    del output
        inventory = dict(streamed.buffer_inventory)
        cached_inventory = dict(cached.buffer_inventory)
        internal_ported_cell_count = sum(bool(len(cell.ports)) for cell in streamed._cells)
        record = {
            "schema": "task039extra.v30.l4-real-80-mode-streamed-diagnostic.v1",
            "classification": "DIAGNOSTIC_REAL_80_MODE_P6_CARRIER",
            "input_path": "input/task39extra/v30_workstation_guided_original_h7p5.dat",
            "input_sha256": case["resolved"].input_sha256,
            "physical_model_sha256": case["resolved"].physical_model_sha256,
            "mode_manifest_sha256": case["physical"]["mode_sha256"],
            "mode_count": len(carrier.entries),
            "degree": 6,
            "mesh_target_nm": float(case["cfg"].mesh_target_size),
            "cell_count": len(condensed.cell_recovery_maps),
            "full_rows": int(condensed.full_rows),
            "active_trace_rows": int(condensed.active_rows),
            "reduced_rows": int(streamed.reduced_size),
            "global_schur_materialized": False,
            "p4_global_factor_built": False,
            "setup_seconds_including_mesh_jit_condensation_and_action_builders": case["setup_seconds"],
            "measured_defects": {
                "cached_vs_streamed_action_relative": _relative(
                    cached.apply(reduced), streamed.apply(reduced)
                ),
                "cached_vs_streamed_rhs_reduction_relative": _relative(
                    cached.reduce_rhs(full_rhs), streamed.reduce_rhs(full_rhs)
                ),
                "cached_vs_streamed_recovery_relative": _relative(
                    cached_storage, streamed_storage
                ),
                "recovered_storage_relative_to_seed": _relative(
                    streamed_storage, storage
                ),
                "independent_carrier_port_closure_relative": float(
                    np.linalg.norm(closure) / closure_scale
                ),
                "original_A6_native_residual_relative": residual_facts[
                    "native_residual_relative"
                ],
                "original_A6_identity_relative": residual_facts[
                    "native_identity_relative"
                ],
                "internal_residual_relative": residual_facts[
                    "internal_residual_relative"
                ],
                "augmented_port_residual_relative": residual_facts[
                    "port_residual_relative"
                ],
            },
            "timing": {
                "warmup_calls_per_mode_and_operation": 1,
                "interleaved_sample_orders": sample_orders,
                "wall_seconds_samples": samples,
                "arithmetic_mean_seconds": {
                    mode: {
                        name: float(np.mean(values))
                        for name, values in operation_samples.items()
                    }
                    for mode, operation_samples in samples.items()
                },
                "scope": "one small real-carrier p6 action/RHS/recovery operation; not a PDE solve",
            },
            "cell_internal_port_support": {
                "cells_with_ports": sum(bool(len(cell.ports)) for cell in streamed._cells),
                "ports_per_cell": [int(len(cell.ports)) for cell in streamed._cells],
                "additional_streamed_action_local_solves_per_call": int(
                    internal_ported_cell_count
                ),
                "additional_streamed_recovery_local_solves_per_call": int(
                    internal_ported_cell_count
                ),
                "streamed_action_local_solves_total_in_test": streamed.audit[
                    "streamed_action_lu_solve_count"
                ],
                "streamed_recovery_local_solves_total_in_test": streamed.audit[
                    "streamed_recovery_lu_solve_count"
                ],
            },
            "resident_inventory_bytes": {
                "cached": cached_inventory,
                "streamed": inventory,
            },
            "scratch": {
                "streamed_max_named_local_bytes": streamed.audit[
                    "streamed_max_local_scratch_bytes"
                ],
                "scope": streamed.audit["streamed_scratch_scope"],
            },
            "selected": False,
            "selection_reason": "diagnostic only; candidate decision is recorded after reading measured timing and resident-buffer difference",
        }
        (tmp_path / "l4_real_80_mode_record.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )



def _synthetic_80_nonhermitian_action_pair():
    from src.test.test_task39extra_v19_p6_cell_condensed_action import (
        _FakeCondensed,
        _matrix,
    )

    rng = np.random.default_rng(39081)
    mode_count = 80
    cell_count = 6
    block = {
        "Vii": _matrix(rng, 2, 2, 5.0),
        "Vit": _matrix(rng, 2, 2),
        "Vti": _matrix(rng, 2, 2),
        "Vtt": _matrix(rng, 2, 2, 3.0),
        "Bi": _matrix(rng, 2, mode_count),
        "Bt": _matrix(rng, 2, mode_count),
        "Di": _matrix(rng, mode_count, 2),
        "Dt": _matrix(rng, mode_count, 2),
        "H": np.zeros((2, 2), dtype=np.complex128),
    }
    blocks = tuple(
        {name: value.copy() for name, value in block.items()}
        for _ in range(cell_count)
    )
    condensed = _FakeCondensed(blocks, appended_rows=mode_count)
    ports = np.arange(mode_count, dtype=PETSc.IntType)
    port_terms = {
        index: P6CellPortTerms(
            Bi=block["Bi"].copy(),
            Di=block["Di"].copy(),
            port_indices=ports.copy(),
            Bt=block["Bt"].copy(),
            Dt=block["Dt"].copy(),
        )
        for index in range(cell_count)
    }
    hp = np.diag(
        np.asarray(
            [1.0 + 0.001 * index + 0.3j for index in range(mode_count)],
            dtype=np.complex128,
        )
    )
    cached = P6CellCondensedAction(
        condensed, H_p=hp, port_terms=port_terms, port_coupling_mode="cached"
    )
    streamed = P6CellCondensedAction(
        condensed, H_p=hp, port_terms=port_terms, port_coupling_mode="streamed"
    )
    return condensed, cached, streamed, block


def test_diagnostic_synthetic_80_nonhermitian_cached_streamed_timing(tmp_path: Path) -> None:
    """Compare all changed local operations on six cells with 80 ports."""

    condensed, cached, streamed, block = _synthetic_80_nonhermitian_action_pair()
    rng = np.random.default_rng(39082)
    reduced = rng.normal(size=cached.reduced_size) + 1j * rng.normal(size=cached.reduced_size)
    full_rhs = rng.normal(size=condensed.full_rows) + 1j * rng.normal(size=condensed.full_rows)
    port_rhs = rng.normal(size=condensed.appended_rows) + 1j * rng.normal(size=condensed.appended_rows)
    try:
        operation_functions = {
            "apply": lambda action: action.apply(reduced),
            "reduce_rhs": lambda action: action.reduce_rhs(
                full_rhs, port_rhs=port_rhs
            ),
            "recover_storage": lambda action: action.recover_storage(
                reduced, full_rhs=full_rhs
            ),
        }
        defects = {}
        for name, operation in operation_functions.items():
            defects[name] = _relative(operation(cached), operation(streamed))
            assert defects[name] <= 1.0e-10
        stream_before = dict(streamed.audit)
        streamed.apply(reduced)
        action_solves_per_call = (
            streamed.audit["streamed_action_lu_solve_count"]
            - stream_before["streamed_action_lu_solve_count"]
        )
        stream_before = dict(streamed.audit)
        streamed.recover_storage(reduced, full_rhs=full_rhs)
        recovery_solves_per_call = (
            streamed.audit["streamed_recovery_lu_solve_count"]
            - stream_before["streamed_recovery_lu_solve_count"]
        )
        for action in (cached, streamed):
            for operation in operation_functions.values():
                output = operation(action)
                del output
        samples = {
            mode: {name: [] for name in operation_functions}
            for mode in ("cached", "streamed")
        }
        sample_orders = []
        actions = {"cached": cached, "streamed": streamed}
        for sample_index in range(3):
            order = ("cached", "streamed") if sample_index % 2 == 0 else ("streamed", "cached")
            sample_orders.append(list(order))
            for mode in order:
                for name, operation in operation_functions.items():
                    started = time.perf_counter()
                    output = operation(actions[mode])
                    samples[mode][name].append(float(time.perf_counter() - started))
                    del output
        cached_inventory = dict(cached.buffer_inventory)
        streamed_inventory = dict(streamed.buffer_inventory)
        record = {
            "schema": "task039extra.v30.l4-synthetic-80-nonhermitian-pair.v1",
            "classification": "DIAGNOSTIC_SYNTHETIC_NONHERMITIAN_80_MODE",
            "mode_count": 80,
            "cell_count": 6,
            "local_interior_rows": 2,
            "local_trace_rows": 2,
            "distinct_Bi_Di": bool(not np.allclose(block["Di"], block["Bi"].conj().T)),
            "global_schur_materialized": False,
            "global_factor_built": False,
            "cached_vs_streamed_relative_defects": defects,
            "streamed_additional_local_lu_solves_per_call": {
                "apply": int(action_solves_per_call),
                "recovery": int(recovery_solves_per_call),
            },
            "timing": {
                "warmup_calls_per_mode_and_operation": 1,
                "interleaved_sample_orders": sample_orders,
                "wall_seconds_samples": samples,
                "arithmetic_mean_seconds": {
                    mode: {
                        name: float(np.mean(values))
                        for name, values in operation_samples.items()
                    }
                    for mode, operation_samples in samples.items()
                },
                "scope": "one six-cell synthetic local action/RHS/recovery; not a physical solve",
            },
            "resident_inventory_bytes": {
                "cached": cached_inventory,
                "streamed": streamed_inventory,
                "cached_minus_streamed_unique_owner_bytes": int(
                    cached_inventory["unique_port_payload_owner_bytes"]
                    - streamed_inventory["unique_port_payload_owner_bytes"]
                ),
            },
            "scratch": {
                "streamed_max_named_local_bytes": streamed.audit[
                    "streamed_max_local_scratch_bytes"
                ],
                "scope": streamed.audit["streamed_scratch_scope"],
            },
            "selected": False,
            "selection_reason": "synthetic timing and memory diagnostic only",
        }
        (tmp_path / "l4_synthetic_80_pair_record.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        streamed.destroy()
        cached.destroy()
        condensed.destroy()

@pytest.mark.parametrize("mode_count", (80, 512, 3904))
def test_diagnostic_mode_scaling_uses_only_streamed_local_cell_action(
    mode_count: int, tmp_path: Path
) -> None:
    """DIAGNOSTIC_MODE_SCALING; avoid a dense H_p or a mode-square oracle."""

    rng = np.random.default_rng(39390 + mode_count)
    vii = np.asarray([[4.0 + 0.2j, 0.3 - 0.1j], [0.2 + 0.4j, 3.5 - 0.3j]])
    vit = np.asarray([[0.1 + 0.2j, -0.2j], [0.3 - 0.1j, 0.15 + 0.2j]])
    vti = np.asarray([[0.2 - 0.1j, 0.05 + 0.2j], [-0.1 + 0.3j, 0.25 - 0.2j]])
    vtt = np.asarray([[2.5 + 0.4j, 0.2 - 0.1j], [0.1 + 0.3j, 2.0 - 0.2j]])
    factor = lu_factor(vii)
    recovery = -lu_solve(factor, vit)
    trace_from_interior = -vti @ lu_solve(factor, np.eye(2, dtype=np.complex128))
    cell = SimpleNamespace(
        S_V=vtt - vti @ lu_solve(factor, vit),
        recovery=recovery,
        trace_from_interior=trace_from_interior,
        interior_lu=factor,
        Bi=0.02 * (rng.normal(size=(2, mode_count)) + 1j * rng.normal(size=(2, mode_count))),
        Bt=0.03 * (rng.normal(size=(2, mode_count)) + 1j * rng.normal(size=(2, mode_count))),
        Di=0.02 * (rng.normal(size=(mode_count, 2)) + 1j * rng.normal(size=(mode_count, 2))),
        Dt=0.03 * (rng.normal(size=(mode_count, 2)) + 1j * rng.normal(size=(mode_count, 2))),
        ports=np.arange(mode_count, dtype=np.int64),
    )
    alpha = rng.normal(size=mode_count) + 1j * rng.normal(size=mode_count)
    local_trace = rng.normal(size=2) + 1j * rng.normal(size=2)
    local_action, port_action, scratch_bytes, solve_calls = (
        P6CellCondensedAction._streamed_cell_action(cell, local_trace, alpha)
    )
    bi_alpha = cell.Bi @ alpha
    expected_trace = (
        cell.S_V @ local_trace
        + cell.Bt @ alpha
        + cell.trace_from_interior @ bi_alpha
    )
    expected_port = (
        -cell.Dt @ local_trace
        - cell.Di @ (cell.recovery @ local_trace)
        + cell.Di @ lu_solve(cell.interior_lu, bi_alpha)
    )
    trace_defect = _relative(local_action, expected_trace)
    port_defect = _relative(port_action, expected_port)
    assert trace_defect <= 1.0e-12
    assert port_defect <= 1.0e-12
    assert solve_calls == 1
    assert scratch_bytes <= 128 * mode_count + 4096
    assert not hasattr(cell, "H_p") and not hasattr(cell, "Hhat")
    timing_samples = []
    for _ in range(3):
        started = time.perf_counter()
        _observed_trace, _observed_port, _scratch, _solves = (
            P6CellCondensedAction._streamed_cell_action(cell, local_trace, alpha)
        )
        timing_samples.append(float(time.perf_counter() - started))
        del _observed_trace, _observed_port
    record = {
        "schema": "task039extra.v30.l4-mode-scaling-streamed-cell.v1",
        "classification": "DIAGNOSTIC_MODE_SCALING",
        "mode_count": int(mode_count),
        "cell_count": 1,
        "local_interior_rows": 2,
        "local_trace_rows": 2,
        "local_lu_solve_calls_per_cell_action": int(solve_calls),
        "persistent_local_port_array_bytes": int(sum(
            array.nbytes for array in (cell.Bi, cell.Bt, cell.Di, cell.Dt, cell.ports)
        )),
        "input_alpha_bytes": int(alpha.nbytes),
        "measured_named_local_scratch_bytes": int(scratch_bytes),
        "scratch_formula_upper_bytes": int(128 * mode_count + 4096),
        "trace_action_relative_defect": trace_defect,
        "port_action_relative_defect": port_defect,
        "one_cell_action_wall_seconds_samples": timing_samples,
        "one_cell_action_wall_seconds_arithmetic_mean": float(np.mean(timing_samples)),
        "dense_H_p_or_Hhat_allocated": False,
        "mode_square_or_global_factor_allocated": False,
        "scope": "one local streamed action helper call; no full operator or PDE claim",
    }
    (tmp_path / f"l4_mode_scaling_{mode_count}.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
