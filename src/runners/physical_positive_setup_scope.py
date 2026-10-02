"""Explicit positive-only preparation using the ordinary qualified launcher."""
from __future__ import annotations

from pathlib import Path
from time import perf_counter, process_time


def run_positive_setup_scope(payload, directory, *, cfg, contract, ledger,
                             sample, summary, source_sha):
    from mpi4py import MPI

    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.physical_light_setup import build_light_h6_setup

    from .physical_intermediate import _atomic_json

    if contract.get('identity') != 'dual_condensed_balh_native_2nm_h6_only_v6':
        raise ValueError('positive setup scope requires the explicit V6 H6-only identity')
    directory = Path(directory)
    started, cpu_started = perf_counter(), process_time()
    setup = None
    try:
        sample()
        ledger.marker('h6_only_mesh_spaces_started', {})
        levels = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6,))
        mesh = levels['mesh']
        cells = MPI.COMM_WORLD.allreduce(mesh.topology.index_map(3).size_local)
        modes, _rows, mode_sha = build_dynamic_mode_inventory(cfg)
        if cells != 54332 or len(modes) != 3904:
            raise ValueError('H6-only actual mesh/mode inventory differs from Review V6')
        space = levels['floquets'][6].mpc.function_space
        summary['mesh_space'] = {'cells': int(cells), 'degree': 6,
            'full_rows': int(space.dofmap.index_map.size_global),
            'mode_count': len(modes), 'mode_sha256': mode_sha,
            'port_carrier_constructed': False, 'positive_coefficients': levels['coefficient_audit']}
        ledger.marker('h6_only_mesh_spaces_complete', summary['mesh_space'])
        setup = build_light_h6_setup(levels, cfg, ledger.marker,
            packed_power10=True, packed_apply=True, sum_factorized_work=True,
            sum_factorized_power10=True, reference_metric_diagonal=True,
            direct_selected_backend=True, projection_layout_v31_natural_order_internal=True)
        facts = setup['light_facts']
        if facts['power_matrix_mult_count'] != 20 or not facts['reference_metric_diagonal_opt_in']:
            raise ValueError('H6-only preparation did not execute the qualified path')
        summary.update(status='H6_ONLY_COMPLETED', result_classification='h6_only',
            execution_mode='h6_only', complete_solve=False, source_sha=source_sha,
            provenance=dict(payload['provenance']), h6_setup=facts,
            elapsed_monotonic_seconds=perf_counter()-started,
            process_cpu_seconds=process_time()-cpu_started,
            p4_factor_counts={'symbolic_calls': 0, 'numeric_calls': 0, 'solve_calls': 0},
            outer_solve_status='NOT_RUN', rta_status='NOT_RUN',
            physical_checker_status='NOT_RUN', full_a6_recovery_status='NOT_RUN',
            official_result=None, resource_boundary_sample=sample())
        ledger.marker('H6_ONLY_COMPLETED', {'power_actions': 20, 'cells': int(cells),
            'p4_global_matrix_constructed': False, 'p4_factor_constructed': False})
        _atomic_json(directory/'physical_intermediate_summary.json', summary)
        return {'passed': True, 'errors': [], 'result_classification': 'h6_only',
            'complete_solve': False, 'summary': str(directory/'physical_intermediate_summary.json')}
    except BaseException as exc:
        summary.update(status='FAILED', exception_type=type(exc).__name__,
            exception_message=str(exc), failed_stage=ledger.last_stage,
            execution_mode='h6_only', complete_solve=False)
        _atomic_json(directory/'physical_intermediate_summary.json', summary)
        raise
    finally:
        if setup is not None:
            setup['h6'].destroy()
            setup['p6_shell'].destroy()
