'''Focused MPI8 real-side old/full versus cell-condensed qualification.'''

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from time import perf_counter

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
)
from src.solvers.physical_balanced_side_inverse import (
    build_side_balanced_inverse,
)
from src.solvers.physical_balanced_trace_bridge import (
    inject_active_residual_to_full_p6,
)
from src.test.test_347_task041_balh_physical_operator import (
    _fill_active,
    _fixture_config,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size != 8,
    reason='This targeted qualification node requires exactly MPI8',
)

_Q_TOLERANCE = 1.0e-11
_PC_TOLERANCE = 1.0e-8
_A4_TOLERANCE = 1.0e-10
_SIDE_RESIDUAL_TOLERANCE = 1.0e-2
_PROFILE = 'task041_schur_speed_v2'


def _collective_require(
    comm: MPI.Intracomm,
    local: bool,
    message: str,
) -> None:
    passed = bool(comm.allreduce(bool(local), op=MPI.LAND))
    if not passed:
        raise AssertionError(message)


def _collective_array_unchanged(
    comm: MPI.Intracomm,
    vector: PETSc.Vec,
    before: np.ndarray,
    message: str,
) -> None:
    local = bool(
        np.array_equal(
            np.asarray(vector.getArray(readonly=True)),
            before,
        )
    )
    _collective_require(comm, local, message)


def _max_elapsed(comm: MPI.Intracomm, elapsed: float) -> float:
    return float(comm.allreduce(float(elapsed), op=MPI.MAX))


def _relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        numerator = float(difference.norm())
        denominator = float(right.norm())
        return numerator / denominator if denominator != 0.0 else numerator
    finally:
        difference.destroy()


def _explicit_side_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
) -> dict[str, float | bool]:
    action = operator.createVecLeft()
    residual = rhs.duplicate()
    try:
        operator.mult(solution, action)
        rhs.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), action)
        rhs_norm = float(rhs.norm())
        residual_norm = float(residual.norm())
        solution_norm = float(solution.norm())
        relative = (
            residual_norm / rhs_norm if rhs_norm != 0.0 else residual_norm
        )
        finite = bool(
            np.isfinite(rhs_norm)
            and np.isfinite(residual_norm)
            and np.isfinite(solution_norm)
            and np.isfinite(relative)
        )
        return {
            'rhs_norm': rhs_norm,
            'residual_norm': residual_norm,
            'solution_norm': solution_norm,
            'relative_residual': relative,
            'finite': finite,
        }
    finally:
        action.destroy()
        residual.destroy()


def _p4_audit_values(inverse) -> dict[str, object]:
    last_solve = inverse.diagnostics['p4_factor']['last_solve']
    return {
        'status': str(last_solve['status']),
        'a4_relative': float(last_solve['physical_relative_residual']),
        'backsolve_count': int(last_solve['backsolve_count']),
        'refinement_count': int(last_solve['refinement_count']),
    }


def _lifecycle_values(diagnostics: dict[str, object]) -> dict[str, object]:
    names = (
        'destroyed',
        'p4_factor_live',
        'p4_factor_created_count',
        'p4_factor_destroy_count',
        'nested_iterative_ksp_count',
        'nested_ksp_created_count',
        'nested_ksp_destroy_count',
    )
    return {name: diagnostics[name] for name in names if name in diagnostics}


def _compact_backend(result: dict[str, object]) -> dict[str, object]:
    names = (
        'backend',
        'setup_seconds',
        'q_seconds',
        'pc_seconds',
        'response_seconds',
        'timing_semantics',
        'ready_lifecycle',
        'released_lifecycle',
        'q_p4_audit',
        'pc_p4_audit',
        'response_p4_audit',
        'response_audit',
        'response_residual',
        'owner_facts',
        'input_unchanged',
        'rank_layout',
        'p6_v_identity',
        'p6_mpc_identity',
        'mapping',
    )
    return {name: result[name] for name in names}


def _mapping_summary(side_system) -> dict[str, object]:
    condensed = side_system.static_condensation.condensed
    original = np.asarray(
        condensed.trace_constraints.owned_active_original_dofs,
        dtype=np.int64,
    )
    return {
        'owned_active_original_dofs_count': int(original.size),
        'owned_active_original_dofs_sha256': hashlib.sha256(
            original.tobytes(),
        ).hexdigest(),
    }


def _rank_layout(side_system, transfer=None) -> dict[str, object]:
    comm = side_system.A.getComm().tompi4py()
    condensed = side_system.static_condensation.condensed
    mesh = side_system.local_mesh.mesh
    cell_map = mesh.topology.index_map(mesh.topology.dim)
    active_start, active_end = map(int, side_system.A.getOwnershipRange())
    remote_count = 0
    remote_ranks: set[int] = set()
    if transfer is not None:
        stops = np.asarray(
            [int(right) for _left, right in transfer.coarse_ranges],
            dtype=np.int64,
        )
        for record in transfer._records:
            coarse_global = np.asarray(
                record['coarse_global'],
                dtype=np.int64,
            )
            owners = np.searchsorted(stops, coarse_global, side='right')
            remote = owners[owners != comm.rank]
            remote_count += int(remote.size)
            remote_ranks.update(int(rank) for rank in remote)
    return {
        'rank': int(comm.rank),
        'owned_cells': int(cell_map.size_local),
        'ghost_cells': int(cell_map.num_ghosts),
        'active_range': [active_start, active_end],
        'owned_active_rows': int(condensed.owned_active_rows),
        'owned_port_rows': int(condensed.owned_appended_rows),
        'active_rows': int(condensed.active_rows),
        'port_rows': int(condensed.appended_rows),
        'mapping': _mapping_summary(side_system),
        'remote_candidate_dofs': int(remote_count),
        'remote_candidate_ranks': sorted(remote_ranks),
    }


def _run_backend(
    side_system,
    source: PETSc.Vec,
    rhs: PETSc.Vec,
    full_source: PETSc.Vec | None,
    backend: str,
    side: str,
) -> dict[str, object]:
    comm = side_system.A.getComm().tompi4py()
    operator = side_system.A
    inverse = None
    q_output = None
    pc_output = None
    response_output = None
    local_full_source = full_source
    stage = 'setup'
    try:
        setup_started = perf_counter()
        inverse = build_side_balanced_inverse(
            side_system,
            detailed_timing=True,
            performance_profile=_PROFILE,
            p4_inverse_backend=backend,
        )
        setup_seconds = _max_elapsed(comm, perf_counter() - setup_started)
        ready_lifecycle = _lifecycle_values(inverse.diagnostics)
        _collective_require(
            comm,
            inverse._side_system is side_system,
            f'{backend}: side system identity changed',
        )
        p6_v_identity = inverse._full_action.V is side_system.V
        p6_mpc_identity = (
            inverse._full_action.floquet_data.mpc
            is side_system.floquet_data.mpc
        )
        _collective_require(
            comm,
            p6_v_identity and p6_mpc_identity,
            f'{backend}: p6 V/MPC is not borrowed from the side system',
        )
        _collective_require(
            comm,
            inverse._condensed
            is side_system.static_condensation.condensed,
            f'{backend}: condensed system is not borrowed from the side system',
        )
        _collective_require(
            comm,
            inverse._full_action.local_mesh is side_system.local_mesh,
            f'{backend}: full action mesh is not borrowed from the side system',
        )
        _collective_require(
            comm,
            bool(inverse._ksp.getInitialGuessNonzero()) is False,
            f'{backend}: KSP initial guess is enabled',
        )
        if local_full_source is None:
            local_full_source = inverse._full_action.matrix.createVecRight()
            inject_active_residual_to_full_p6(
                side_system.static_condensation.condensed,
                source,
                local_full_source,
            )
        _collective_require(
            comm,
            local_full_source.getSize()
            == inverse._full_action.matrix.getSize()[1]
            and tuple(local_full_source.getOwnershipRange())
            == tuple(inverse._full_action.matrix.getOwnershipRange()),
            f'{backend}: full p6 source ownership does not match',
        )

        full_source_before_q = np.asarray(
            local_full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        stage = 'q'
        q_started = perf_counter()
        q_output = inverse._apply_q_callback(local_full_source)
        q_seconds = _max_elapsed(comm, perf_counter() - q_started)
        _collective_array_unchanged(
            comm,
            local_full_source,
            full_source_before_q,
            f'{backend}: Q modified full p6 source',
        )
        q_p4_audit = _p4_audit_values(inverse)

        full_source_before_pc = np.asarray(
            local_full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        source_before_pc = np.asarray(
            source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        pc_output = operator.createVecLeft()
        pc_output.set(0.0)
        stage = 'pc'
        pc_started = perf_counter()
        inverse._apply_balanced_pc(source, pc_output)
        pc_seconds = _max_elapsed(comm, perf_counter() - pc_started)
        _collective_array_unchanged(
            comm,
            local_full_source,
            full_source_before_pc,
            f'{backend}: PC modified full p6 source',
        )
        _collective_array_unchanged(
            comm,
            source,
            source_before_pc,
            f'{backend}: PC modified active source',
        )
        pc_p4_audit = _p4_audit_values(inverse)

        rhs_before_response = np.asarray(
            rhs.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        full_source_before_response = np.asarray(
            local_full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        response_output = operator.createVecLeft()
        response_output.set(0.0)
        stage = 'response'
        response_started = perf_counter()
        inverse.apply(rhs, response_output)
        response_seconds = _max_elapsed(
            comm,
            perf_counter() - response_started,
        )
        response_audit = dict(inverse.diagnostics['last_apply'])
        response_p4_audit = _p4_audit_values(inverse)
        response_residual = _explicit_side_residual(
            operator,
            rhs,
            response_output,
        )
        _collective_array_unchanged(
            comm,
            rhs,
            rhs_before_response,
            f'{backend}: response modified RHS',
        )
        _collective_array_unchanged(
            comm,
            local_full_source,
            full_source_before_response,
            f'{backend}: response modified full p6 source',
        )
        transfer = inverse._owner_transfer
        owner_facts = dict(transfer.last_apply_facts)
        rank_layout = comm.allgather(_rank_layout(side_system, transfer))

        stage = 'release'
        inverse.destroy()
        released = inverse.diagnostics
        released_lifecycle = _lifecycle_values(released)
        _collective_require(
            comm,
            released['destroyed'] is True
            and released['p4_factor_live'] == 0
            and released['nested_iterative_ksp_count'] == 0,
            f'{backend}: factor/KSP cleanup was incomplete',
        )
        inverse = None
        return {
            'backend': backend,
            'setup_seconds': setup_seconds,
            'q_seconds': q_seconds,
            'pc_seconds': pc_seconds,
            'response_seconds': response_seconds,
            'timing_semantics': (
                'setup and action values are per-action MPI.MAX across ranks; '
                'they are not service or parent wall-clock intervals'
            ),
            'ready_lifecycle': ready_lifecycle,
            'released_lifecycle': released_lifecycle,
            'q_p4_audit': q_p4_audit,
            'pc_p4_audit': pc_p4_audit,
            'response_p4_audit': response_p4_audit,
            'response_audit': dict(response_audit),
            'response_residual': response_residual,
            'owner_facts': owner_facts,
            'input_unchanged': True,
            'rank_layout': rank_layout,
            'p6_v_identity': p6_v_identity,
            'p6_mpc_identity': p6_mpc_identity,
            'mapping': _mapping_summary(side_system),
            'full_source': local_full_source,
            'q_output': q_output,
            'pc_output': pc_output,
            'response_output': response_output,
        }
    except BaseException as exc:
        if comm.rank == 0:
            failure = {
                'schema': 'task041.h1e.mpi8.side_backend_failure.v1',
                'side': side,
                'backend': backend,
                'stage': stage,
                'exception_type': type(exc).__name__,
                'exception': str(exc),
            }
            if inverse is not None:
                diagnostics = inverse.diagnostics
                if 'p4_factor' in diagnostics:
                    failure['p4_last_solve'] = dict(
                        diagnostics['p4_factor']['last_solve']
                    )
                if 'last_apply' in diagnostics:
                    failure['last_apply'] = dict(diagnostics['last_apply'])
            print(json.dumps(failure, sort_keys=True, default=str), flush=True)
        if inverse is not None:
            inverse.destroy()
        if local_full_source is not None and full_source is None:
            local_full_source.destroy()
        for vector in (q_output, pc_output, response_output):
            if vector is not None:
                vector.destroy()
        raise


def test_task041_h1e_mpi8_side_inverse_old_new_q_pc_and_apply() -> None:
    '''Run one bottom-to-top MPI8 paired side comparison only.'''

    comm = MPI.COMM_WORLD
    cfg = replace(
        _fixture_config(6, condensed=True),
        mesh_axis_cell_counts=(4, 2, 2),
    )
    side_records: list[dict[str, object]] = []

    for side in ('bottom', 'top'):
        mesh = None
        side_system = None
        source = None
        rhs = None
        full_source = None
        old = None
        new = None
        try:
            mesh = build_hybrid_local_mesh(
                cfg,
                side,
                bottom_interface_z_nm=0.5,
                top_interface_z_nm=0.5,
                comm=comm,
            )
            side_system = assemble_hybrid_local_dtn_action_system(
                cfg,
                side,
                local_mesh_override=mesh,
                comm=comm,
            )
            preflight_layout = comm.allgather(_rank_layout(side_system))
            global_cells_preflight = sum(
                int(item['owned_cells']) for item in preflight_layout
            )
            every_rank_owns_cells = all(
                int(item['owned_cells']) > 0 for item in preflight_layout
            )
            partition_ok = (
                global_cells_preflight == 8 and every_rank_owns_cells
            )
            if not partition_ok and comm.rank == 0:
                print(
                    json.dumps(
                        {
                            'schema': (
                                'task041.h1e.mpi8.partition_failure.v1'
                            ),
                            'side': side,
                            'mpi_size': int(comm.size),
                            'global_owned_cells': global_cells_preflight,
                            'every_rank_owns_cells': every_rank_owns_cells,
                            'rank_layout_preflight': preflight_layout,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            _collective_require(
                comm,
                partition_ok,
                f'{side}: MPI8 partition must own eight cells with every rank nonzero',
            )
            operator = side_system.A
            source = operator.createVecRight()
            rhs = operator.createVecLeft()
            _fill_active(source, 1.25)
            operator.mult(source, rhs)
            rhs_norm = float(rhs.norm())
            _collective_require(
                comm,
                np.isfinite(rhs_norm) and rhs_norm > 0.0,
                f'{side}: fixed nonzero RHS norm is invalid',
            )
            source_before = np.asarray(
                source.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
            rhs_before = np.asarray(
                rhs.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
            b_before = np.asarray(
                side_system.b.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()

            old = _run_backend(
                side_system,
                source,
                rhs,
                None,
                'full',
                side,
            )
            full_source = old['full_source']
            borrowed_after_old = _explicit_side_residual(
                operator,
                rhs,
                source,
            )
            new = _run_backend(
                side_system,
                source,
                rhs,
                full_source,
                'cell_condensed',
                side,
            )
            borrowed_after_new = _explicit_side_residual(
                operator,
                rhs,
                source,
            )

            q_relative = _relative_difference(
                new['q_output'],
                old['q_output'],
            )
            pc_relative = _relative_difference(
                new['pc_output'],
                old['pc_output'],
            )
            e_x = _relative_difference(
                new['response_output'],
                old['response_output'],
            )
            response_delta = new['response_output'].duplicate()
            delta_action = operator.createVecLeft()
            try:
                new['response_output'].copy(response_delta)
                response_delta.axpy(
                    PETSc.ScalarType(-1.0),
                    old['response_output'],
                )
                operator.mult(response_delta, delta_action)
                delta_action_norm = float(delta_action.norm())
                rhs_norm = float(rhs.norm())
                e_a = (
                    delta_action_norm / rhs_norm
                    if rhs_norm != 0.0
                    else delta_action_norm
                )
            finally:
                response_delta.destroy()
                delta_action.destroy()

            old_layout = old['rank_layout']
            new_layout = new['rank_layout']
            global_cells = global_cells_preflight
            global_active_rows = sum(
                int(item['owned_active_rows']) for item in old_layout
            )
            global_port_rows = sum(
                int(item['owned_port_rows']) for item in old_layout
            )
            remote_candidate_dofs = sum(
                int(item['remote_candidate_dofs']) for item in old_layout
            )
            old_rank_remote = sum(
                bool(item['remote_candidate_ranks']) for item in old_layout
            )
            new_rank_remote = sum(
                bool(item['remote_candidate_ranks']) for item in new_layout
            )
            input_unchanged_local = (
                np.array_equal(
                    source.getArray(readonly=True),
                    source_before,
                )
                and np.array_equal(
                    rhs.getArray(readonly=True),
                    rhs_before,
                )
                and np.array_equal(
                    side_system.b.getArray(readonly=True),
                    b_before,
                )
                and old['input_unchanged']
                and new['input_unchanged']
            )
            input_unchanged = bool(
                comm.allreduce(input_unchanged_local, op=MPI.LAND)
            )
            same_layout_local = (
                old_layout == new_layout
                and old['p6_v_identity']
                and old['p6_mpc_identity']
                and new['p6_v_identity']
                and new['p6_mpc_identity']
            )
            same_layout = bool(
                comm.allreduce(same_layout_local, op=MPI.LAND)
            )
            same_mapping_local = (
                old['mapping'] == new['mapping']
                and all(
                    item_old['mapping'] == item_new['mapping']
                    for item_old, item_new in zip(
                        old_layout,
                        new_layout,
                        strict=True,
                    )
                )
            )
            same_mapping = bool(
                comm.allreduce(same_mapping_local, op=MPI.LAND)
            )
            side_record = {
                'schema': 'task041.h1e.mpi8.side_backend_compare.v1',
                'diagnostic_before_assertions': True,
                'side': side,
                'mpi_size': int(comm.size),
                'mesh_axis_cell_counts': [4, 2, 2],
                'global_owned_cells': global_cells,
                'global_owned_active_rows': global_active_rows,
                'global_owned_port_rows': global_port_rows,
                'remote_candidate_dofs': remote_candidate_dofs,
                'ranks_with_remote_candidates_old': old_rank_remote,
                'ranks_with_remote_candidates_new': new_rank_remote,
                'rank_layout_preflight': preflight_layout,
                'rank_layout_old': old_layout,
                'rank_layout_new': new_layout,
                'profile': _PROFILE,
                'backend_sequence': 'full_destroyed_then_cell_condensed',
                'same_p6_v_mpc_layout': same_layout,
                'same_owned_active_mapping': same_mapping,
                'input_unchanged': input_unchanged,
                'rhs_norm': rhs_norm,
                'borrowed_A_after_old_destroy': borrowed_after_old,
                'borrowed_A_after_new_destroy': borrowed_after_new,
                'q_relative': float(q_relative),
                'q_tolerance': _Q_TOLERANCE,
                'pc_relative': float(pc_relative),
                'pc_tolerance': _PC_TOLERANCE,
                'e_x': float(e_x),
                'e_A': float(e_a),
                'e_tolerance': 1.0e-8,
                'old': _compact_backend(old),
                'new': _compact_backend(new),
            }
            side_records.append(side_record)
            if comm.rank == 0:
                print(
                    json.dumps(side_record, sort_keys=True, default=str),
                    flush=True,
                )

            _collective_require(
                comm,
                global_cells == 8,
                f'{side}: expected exactly 8 owned cells globally',
            )
            _collective_require(
                comm,
                every_rank_owns_cells,
                f'{side}: at least one MPI rank owns no cell',
            )
            _collective_require(
                comm,
                global_active_rows == old_layout[0]['active_rows'],
                f'{side}: active ownership does not close globally',
            )
            _collective_require(
                comm,
                global_port_rows == old_layout[0]['port_rows'],
                f'{side}: port ownership does not close globally',
            )
            _collective_require(
                comm,
                remote_candidate_dofs > 0
                and old_rank_remote > 0
                and new_rank_remote > 0,
                f'{side}: no cross-rank owner evidence was observed',
            )
            _collective_require(
                comm,
                same_layout and input_unchanged,
                f'{side}: borrowed layout or input changed',
            )
            _collective_require(
                comm,
                same_mapping,
                f'{side}: owned active original mapping changed',
            )
            _collective_require(
                comm,
                np.isfinite(rhs_norm) and rhs_norm > 0.0,
                f'{side}: fixed RHS norm is not positive',
            )
            _collective_require(
                comm,
                np.isfinite(q_relative) and q_relative <= _Q_TOLERANCE,
                f'{side}: Q comparison gate failed',
            )
            _collective_require(
                comm,
                np.isfinite(pc_relative) and pc_relative <= _PC_TOLERANCE,
                f'{side}: PC comparison gate failed',
            )
            for backend, borrowed in (
                (old, borrowed_after_old),
                (new, borrowed_after_new),
            ):
                _collective_require(
                    comm,
                    bool(borrowed['finite'])
                    and borrowed['relative_residual'] <= 1.0e-12,
                    f'{side}/{backend["backend"]}: borrowed A changed',
                )
            _collective_require(
                comm,
                np.isfinite(e_x)
                and np.isfinite(e_a)
                and e_x <= 1.0e-8
                and e_a <= 1.0e-8,
                f'{side}: e_x/e_A diagnostic gate failed',
            )
            for backend in (old, new):
                for audit_name in (
                    'q_p4_audit',
                    'pc_p4_audit',
                    'response_p4_audit',
                ):
                    audit = backend[audit_name]
                    _collective_require(
                        comm,
                        audit['status'] == 'passed'
                        and np.isfinite(audit['a4_relative'])
                        and audit['a4_relative'] <= _A4_TOLERANCE
                        and 1 <= audit['backsolve_count'] <= 3
                        and audit['refinement_count'] <= 2,
                        f'{side}/{backend["backend"]}/{audit_name}: '
                        'p4 audit gate failed',
                    )
                response = backend['response_residual']
                _collective_require(
                    comm,
                    bool(response['finite'])
                    and response['relative_residual']
                    <= _SIDE_RESIDUAL_TOLERANCE,
                    f'{side}/{backend["backend"]}: side residual gate failed',
                )
                response_audit = backend['response_audit']
                counts = response_audit['counts']
                operation_seconds = response_audit['operation_seconds']
                _collective_require(
                    comm,
                    response_audit['status'] == 'KSP_CONVERGED'
                    and isinstance(response_audit['reason'], int)
                    and response_audit['reason'] > 0
                    and response_audit['ksp_positive'] is True
                    and response_audit[
                        'explicit_true_target_reached'
                    ] is True
                    and isinstance(counts, dict)
                    and 'delta' in counts
                    and 'cumulative' in counts
                    and isinstance(operation_seconds, dict),
                    f'{side}/{backend["backend"]}: KSP audit is incomplete',
                )
                ready = backend['ready_lifecycle']
                released = backend['released_lifecycle']
                lifecycle_names = (
                    'destroyed',
                    'p4_factor_live',
                    'p4_factor_created_count',
                    'p4_factor_destroy_count',
                    'nested_iterative_ksp_count',
                    'nested_ksp_created_count',
                    'nested_ksp_destroy_count',
                )
                _collective_require(
                    comm,
                    all(name in ready for name in lifecycle_names)
                    and all(name in released for name in lifecycle_names)
                    and ready['destroyed'] is False
                    and ready['p4_factor_live'] == 1
                    and ready['p4_factor_created_count'] == 1
                    and ready['p4_factor_destroy_count'] == 0
                    and ready['nested_iterative_ksp_count'] == 1
                    and ready['nested_ksp_created_count'] == 1
                    and ready['nested_ksp_destroy_count'] == 0
                    and released['destroyed'] is True
                    and released['p4_factor_live'] == 0
                    and released['nested_iterative_ksp_count'] == 0
                    and released['p4_factor_created_count'] == 1
                    and released['p4_factor_destroy_count'] == 1
                    and released['nested_ksp_created_count'] == 1
                    and released['nested_ksp_destroy_count'] == 1,
                   f'{side}/{backend["backend"]}: lifecycle evidence incomplete',
               )
        finally:
            for backend in (new, old):
                if backend is not None:
                    for name in ('q_output', 'pc_output', 'response_output'):
                        vector = backend.get(name)
                        if vector is not None:
                            vector.destroy()
            if full_source is not None:
                full_source.destroy()
            for vector in (rhs, source):
                if vector is not None:
                    vector.destroy()
            if side_system is not None:
                side_system.destroy()

    if comm.rank == 0:
        print(
            json.dumps(
                {
                    'schema': 'task041.h1e.mpi8.side_backend_compare.summary.v1',
                    'mpi_size': int(comm.size),
                    'sides': [record['side'] for record in side_records],
                    'backend_sequence': 'bottom_then_top',
                },
                sort_keys=True,
            ),
            flush=True,
        )
