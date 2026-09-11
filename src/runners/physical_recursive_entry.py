"""Single supervised G1 component invocation; no outer solve or campaign routing."""
import argparse
import fcntl
import hashlib
import json
from math import isfinite
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from src.io.input_loader import InputError


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _git_command(*args: str) -> list[str]:
    """Use the canonical split-git worktree used by the Codex runner."""
    git_dir = _REPOSITORY_ROOT / '.git-codex'
    if git_dir.is_dir():
        return [
            'git', '--git-dir', str(git_dir), '--work-tree',
            str(_REPOSITORY_ROOT), *args,
        ]
    return ['git', *args]


def p4_bridge_status(path):
    from math import isfinite
    from .physical_diagnostic_completion import load_packet
    if not Path(path).exists():return 'NOT_REACHED'
    errors=load_packet(Path(path))['errors']
    return 'PASS' if len(errors)==3 and all(isfinite(v) and v<=1e-10 for v in errors.values()) else 'FAIL'


def component_contract(target):
    if target not in ('lo','hi'):
        raise ValueError('only frozen LO/HI component targets')
    return dict(identity='balanced_h6_recursive_p4_'+target+'_v6', scope='G1_components_only',
        physical_degrees=[6,4,2], I4=dict(method='right_FGMRES',restart=16,max_it=64,
        target=1e-4 if target=='lo' else 1e-6,zero_start=True,seconds=60,explicit_interval=16),
        B4='C42+(I-C42 A4)H4(I-A4 C42)',H4=dict(degree=3,power_steps=10),
        bottom=dict(physical_degree=2,total_rows_cap=8192,bytes_cap=512*1024**2,
            native_residual=1e-10,max_refinements=2),fixed_I4_calls=6,full_PC_calls=3,
        new_reference_factor=False,p4_global_matrix=False,p4_global_factor=False,
        full_outer_solve=False,global_swap_stop=True)


def p4_failure_contract():
    return dict(identity='p4_p2_failure_diagnostic_v6',scope='one_saved_A2R160_g1',
        physical_degrees=[6,4,2],I4_calls=0,outer_calls=0,
        projection=dict(count=1,metric='unweighted constrained M0',method='diagonal_CG',
            max_it=256,equation_limit=1e-10,pythagorean_limit=1e-9,seconds=600),
        A4_limit=40,p2_logical_limit=12,H4_standalone=1,B4_calls=2,
        component_calls=dict(curl=1,material_mass=1,dtn=1),workflow_seconds=1800,
        p2_rows_cap=8192,p2_budget_bytes=512*1024**2,p2_true_limit=1e-10,
        new_reference_factor=False,global_swap_stop=True)


def projected_component_contract():
    return dict(identity='projected_p4_complement_v1',scope='one_saved_A2R160_g1',
        workflow_seconds=900,physical_degrees=[6,4,2],I4_calls=1,old_I4_calls=0,outer_calls=0,
        projection_calls=0,B4_baseline_calls=0,A4_inner_limit=150,A4_identity_calls=1,
        p2_logical_limit=65,H4_limit=64,H4_positive_limit=128,
        I4=dict(method='right_FGMRES',restart=16,max_it=64,seconds=60,target=1e-4,
            residual_normalization='original ||g||',delta_zero_start=True),
        p2_rows_cap=8192,p2_budget_bytes=512*1024**2,p2_true_limit=1e-10,
        new_reference_factor=False,global_swap_stop=True)


def bubble_local_contract():
    return dict(identity='bubble_local_tensor_v1',scope='one_frozen_original_air_cell',workflow_seconds=300,
        local_p4=300,local_p2=54,interior_p4=108,retained_p2_bubble=6,Q_columns=102,
        I4_calls=0,outer_calls=0,p2_factor=0,p4_global_matrix=0,H6=0,
        tensor_limit=1e-10,basis_limit=1e-12,harmonic_limit=1e-11,trace_limit=1e-12,
        factorization='complex LU',shift=0,refinements=0,global_swap_stop=True)


def bubble_component_contract():
    return dict(identity='bubble_enriched_p2_component_v1',scope='one_saved_A2R160_g1',workflow_seconds=900,
        physical_degrees=[6,4,2],retained_p2_bubble=6,local_Q_columns=102,
        class_key='exact affine J/width/material/quadrature/orientation; no rounding',
        adjoint_limit=1e-11,S_assembly_limit=1e-10,range_identity_limit=1e-10,trace_limit=1e-12,
        bottom=dict(rows_cap=8192,unified_bytes_cap=512*1024**2,action='WH A4 W',true_limit=1e-10,max_refinements=2),
        I4=dict(method='original_V6_right_FGMRES',restart=16,max_it=64,seconds=60,target=1e-4,zero_start=True),
        I4_calls=1,Cg_calls=1,range_checks=1,B4_limit=64,H4_positive_limit=128,
        p2_logical_limit=130,MatSolve_limit=390,composed_A4_limit=392,external_A4_limit=220,B4_structure_A4_limit=128,
        old_p2_factor=0,p4_global_matrix=0,p4_global_factor=0,outer_calls=0,global_swap_stop=True)


def particular_contract():
    return dict(identity='bubble_particular_diagnostic_v1',scope='same_g_three_errors_two_E_inputs',workflow_seconds=300,
        source_component='d9462e486360a86e9635b504f37a0b762c2bf896',mesh=1,functionspace=0,
        error_decompositions=3,E_inputs=['g','Cg_residual'],local_LU=18,local_rhs=504,cached_A4=2,
        SVD=0,T_54_rhs=0,class_qualification_repeated=False,global_factor=0,H6=0,H4=0,I4=0,outer=0,
        payload_policy_bytes=128*1024**2,energy_bridge_limit=1e-10,identity_limit=1e-11,global_swap_stop=True)


def selected_contract(args):
    if getattr(args, 'p4_direction_diagnosis', False):
        from src.io.physical_recursive_profile import p4_direction_diagnosis_profile_facts
        contract = p4_direction_diagnosis_profile_facts()
        contract.update(
            workflow='P0_P4_direction_diagnosis',
            fixed_source='original 13.5nm physical model; no notch or outer solve',
            inventory_role='G0 hash-bound maps, g/c_ref/A4c_ref and old I4 identity packets',
            full_outer_solve=False,
            global_swap_stop=True,
            memory_policy='SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
        )
        return contract
    if getattr(args, 'macro_v12', False):
        from src.io.physical_recursive_profile import macro_v12_profile_facts
        contract = macro_v12_profile_facts()
        contract.update(
            workflow=getattr(args, 'macro_v12_stage', None) or 'profile_selected_stage',
            fixed_source='original physical model or existing V5 nonseparable notch for O3_NOTCH',
            inventory_role='G0 hash-bound maps and existing V5 reference bindings',
            reference_role='measurement only; no new reference factor or solve',
            full_outer_solve=True,
            global_swap_stop=True,
            memory_policy='SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
        )
        if getattr(args, 'macro_v12_supplement', False):
            contract.update(
                batch='V12_SUPPLEMENT',
                formal_workflow_limit_seconds=MACRO_V12_SUPPLEMENT_TOTAL_LIMIT_SECONDS,
                o1_workflow_limit_seconds=3600.0,
                o1_compute_limit_seconds=MACRO_V12_SUPPLEMENT_O1_COMPUTE_LIMIT_SECONDS,
                permitted_stages=tuple(MACRO_V12_SUPPLEMENT_STAGE_LIMITS),
                old_v12_ledger='not_used_or_merged',
            )
        return contract
    macro_v11 = (getattr(args, 'macro_v11_controls', False)
                 or getattr(args, 'macro_v11_calibration', False))
    if macro_v11 or getattr(args, 'macro_v10_controls', False):
        from src.io.physical_recursive_profile import (
            macro_v10_profile_facts, macro_v11_profile_facts,
        )

        contract = macro_v11_profile_facts() if macro_v11 else macro_v10_profile_facts()
        contract.update(
            workflow=('N1_calibration' if getattr(args, 'macro_v11_calibration', False)
                      else 'M1_controls'),
            fixed_source='original physical model; no cell notch',
            inventory_role='G0 hash-bound calibration and balanced e/q packets',
            reference_role='measurement only; never enters A4/B4/I4',
            bare_B4_I4_calls=6,
            shared_framework_samples=3,
            shared_framework_I4_calls_max=6,
            new_reference_factor=False,
            full_outer_solve=False,
            global_swap_stop=True,
            memory_policy=contract.get(
                'memory_policy', 'LEGACY_LOCAL_MUMPS_MEMORY_POLICY'
            ),
        )
        return contract
    if getattr(args, 'bounded_j1_controls', False):
        route = getattr(args, 'bounded_j1_route', 'ENTITY16')
        if route == 'ENTITY_GCROT8_NEW16':
            from src.io.physical_balanced_profile import (
                BOUNDED_ENTITY_GCROT8_NEW16_PROFILE, bounded_profile_facts)
            return dict(identity='balanced_h6_entity_gcrot8_new16_v9_j1_controls',
                profile=BOUNDED_ENTITY_GCROT8_NEW16_PROFILE,
                route='ENTITY_GCROT8_NEW16',
                scope='J1_equal_new_work_controls_with_recycled_I4',
                source='V9_L1_equal_new_work', labels=['A2R160', 'LIGHT448'],
                setup_count=1, complete_PC_calls=2, I4_calls=4,
                input_fields=['q', 'native_constraint_map_p6',
                              'native_constraint_map_p4', 'g_array_sha256'],
                forbidden_inputs=['e', 'reference_y', 'old_PC_outputs'],
                recycling=bounded_profile_facts(
                    BOUNDED_ENTITY_GCROT8_NEW16_PROFILE)['recycling'],
                l1_gate=dict(cold_start_excluded=True, minimum_pairs=3,
                             equal_new_work=True, all_target_time_ratio_le=0.90,
                             geometric_ratio_le=0.90, fraction_q_lt_one_ge=0.60,
                             q_max_le=2.0, time_ratio_le=1.50),
                j2_gate=dict(one_complete_PC_seconds_le=90.0,
                             both_over_90_action='COARSE_ACTION_COST_BLOCKED',
                             route='L4', exception_only='not_applicable'),
                one_apply_contraction_gate='not_applied',
                old_recursive_campaign='not_called', batch_limit_seconds=36000,
                k0_k1_limit_seconds=3600, finite_control_limit_seconds=900,
                ledger_schema='task39extra.review-v9-equal-new-work-budget.v1',
                old_v7_ledger='not_used_or_merged')
        if route == 'ENTITY_GCROT8':
            from src.io.physical_balanced_profile import (
                BOUNDED_ENTITY_GCROT8_PROFILE, bounded_profile_facts)
            return dict(identity='balanced_h6_entity_gcrot8_v8_j1_controls',
                profile=BOUNDED_ENTITY_GCROT8_PROFILE, route='ENTITY_GCROT8',
                scope='J1_two_real_q_controls_with_recycled_I4',
                source='V8_K1_prototype', labels=['A2R160', 'LIGHT448'],
                setup_count=1, complete_PC_calls=2, I4_calls=4,
                input_fields=['q', 'native_constraint_map_p6'],
                forbidden_inputs=['e', 'reference_y', 'old_PC_outputs'],
                recycling=bounded_profile_facts(BOUNDED_ENTITY_GCROT8_PROFILE)['recycling'],
                j2_gate=dict(one_complete_PC_seconds_le=90.0,
                             both_over_90_exception_outer=8,
                             both_over_90_exception_seconds=600.0),
                one_apply_contraction_gate='not_applied',
                old_recursive_campaign='not_called', batch_limit_seconds=36000,
                k0_k1_limit_seconds=3600, finite_control_limit_seconds=900,
                ledger_schema='task39extra.review-v8-k0-k1-budget.v1',
                old_v7_ledger='not_used_or_merged')
        if route == 'PROJECTED_SEQ2_16':
            from src.io.physical_balanced_profile import BOUNDED_PROJECTED_PROFILE
            return dict(identity='bounded_projected_seq2_16_j1_controls',
                profile=BOUNDED_PROJECTED_PROFILE, route='PROJECTED_SEQ2_16',
                scope='B finite original-mesh seq2/additive comparison plus two-q controls',
                control_mode='B_FINITE_COMPARISON_AND_CONTROLS',
                source='V5_E1_hash_bound_q_only', labels=['A2R160', 'LIGHT448'],
                setup_count=1, finite_comparison_count=1, complete_PC_calls=2, I4_calls=4,
                input_fields=['q', 'native_constraint_map_p6'],
                forbidden_inputs=['e', 'reference_y', 'old_PC_outputs'],
                j2_gate=dict(one_complete_PC_seconds_le=90.0,
                             both_over_90_exception_outer=8,
                             both_over_90_exception_seconds=600.0),
                finite_comparison=dict(
                    formula='M0 + M1 - M1*T*M0',
                    reference='same original-mesh p4 RHS for sequential and additive applies',
                    T='current F^H A4 (I-CU A4) F',
                    outer_calls=0, I4_calls=0,
                    qualification='comparison_only_not_B_formal_qualification'),
                one_apply_contraction_gate='not_applied',
                old_recursive_campaign='not_called', batch_limit_seconds=43200,
                controls_limit_seconds=5400)
        return dict(identity='bounded_entity16_v7_j1_controls', profile='bounded_entity16_v7',
            route='ENTITY16', scope='J1_two_real_q_controls',
            source='V5_E1_hash_bound_q_only', labels=['A2R160', 'LIGHT448'],
            setup_count=1, complete_PC_calls=2, I4_calls=4,
            input_fields=['q', 'native_constraint_map_p6'],
            forbidden_inputs=['e', 'reference_y', 'old_PC_outputs'],
            j2_gate=dict(one_complete_PC_seconds_le=90.0,
                         both_over_90_exception_outer=8,
                         both_over_90_exception_seconds=600.0),
            one_apply_contraction_gate='not_applied',
            old_recursive_campaign='not_called', batch_limit_seconds=43200,
            j0_j1_controls_limit_seconds=3600)
    if getattr(args,'cell_joint_trace_component',False):
        owner_args=argparse.Namespace(**vars(args));owner_args.cell_joint_trace_component=False
        owner_args.owner_route_trace_component=True
        contract=selected_contract(owner_args)
        contract.update(identity='physical_cell_joint_trace_component_v1',cell_joint_trace=True,
            entity_LU=0,entity_setup_rhs=0,entity_apply_rhs_limit=0,patch_LU=84,patch_setup_rhs=84,
            patch_count=252,patch_dimension=144,patch_apply_rhs_limit=65*252,
            patch_qualification=dict(physical_F_bridges=2,HT_calls=3),
            old_HT_B4_equality_required=False)
        return contract
    if getattr(args,'owner_route_trace_component',False):
        cached_args=argparse.Namespace(**vars(args))
        cached_args.owner_route_trace_component=False;cached_args.cached_trace_component=True
        contract=selected_contract(cached_args)
        contract.update(identity='physical_owner_route_trace_component_v1',
            fixed_serial_owner_route=True,owner_primal_qualification=3,
            owner_primal_limit=1e-11,owner_B4_bridge_limit=1e-10,
            owner_extra_budget_bytes=4117888)
        return contract
    return (dict(identity='physical_cached_trace_component_v1' if getattr(args,'cached_trace_component',False) else 'physical_high_trace_component_v1',workflow_seconds=600,
            physical_degrees=[4,2],scope='one_CUg_bridge_one_B4T_one_I4',B4_limit=65,CU_limit=131,
            S_logical_limit=131,MatSolve_limit=393,A4_limit=350,HT_limit=65,E_EH_limit=263,
            Q_LU=18,Q_setup_rhs=3456,entity_LU=1566,entity_setup_rhs=1566,entity_apply_rhs_limit=101790,
            bottom_rows_cap=8192,bottom_local_bytes_cap=512*1024**2,S_true_limit=1e-10,max_refinements=2,
            I4=dict(count=1,restart=16,max_it=64,seconds=60,target=1e-4,zero_start=True),
            H6=0,old_H4=0,outer=0,global_swap_stop=True,
            cached_exact=getattr(args,'cached_trace_component',False),native_authority_cap=75,
            cached_qualification=3 if getattr(args,'cached_trace_component',False) else 0,
            explicit_authority='native_A4') if getattr(args,'high_trace_component',False) or getattr(args,'cached_trace_component',False) else
            dict(identity='bubble_amplification_diagnostic_v1',workflow_seconds=300,
            scope='one_saved_delta_CUg',metadata_degrees=[4,2],A4=0,H4=0,H6=0,I4=0,outer=0,local_LU=0,
            p2_factor=1,p2_logical=1,max_refinements=2,p2_rows_cap=8192,p2_budget_bytes=512*1024**2,
            S_true_limit=1e-10,global_swap_stop=True) if getattr(args,'bubble_amplification_diagnostic',False) else
            particular_contract() if getattr(args,'bubble_particular_diagnostic',False) else
            bubble_component_contract() if getattr(args,'bubble_enriched_component',False) else
            bubble_local_contract() if args.bubble_local_tensor else
            projected_component_contract() if args.projected_p4_component else
            p4_failure_contract() if args.p4_failure_diagnostic else component_contract(args.target))


def dispatch_components(args,cfg,comm,directory,*,sample,marker,source_sha=None,input_path=None,
                        model_identity=None, build_started=None):
    from . import physical_recursive_controls as controls
    if getattr(args, 'p4_direction_diagnosis', False):
        from .physical_macro_controls import run_p4_direction_diagnosis
        return run_p4_direction_diagnosis(
            cfg, comm, args.inventory, directory, sample=sample, marker=marker,
            source_sha=source_sha, input_path=input_path,
            model_identity=model_identity, build_started=build_started,
        )
    if getattr(args, 'macro_v12', False):
        from .physical_macro_v12 import (
            run_macro_v12_finalize, run_macro_v12_outer, run_macro_v12_precheck,
        )
        stage = getattr(args, 'macro_v12_stage', None)
        if stage == 'O0_PRECHECK':
            return run_macro_v12_precheck(
                args.inventory, directory, source_sha=source_sha,
                input_path=input_path, model_identity=model_identity,
            )
        if stage in {'O2_RESTART_PROBE_32', 'O2_RESTART_PROBE_64', 'O3_ORIGINAL', 'O3_NOTCH'}:
            return run_macro_v12_outer(
                cfg, comm, args.inventory, directory, sample=sample, marker=marker,
                source_sha=source_sha, input_path=input_path,
                model_identity=model_identity, stage=stage,
                outer_restart=int(getattr(args, 'macro_v12_outer_restart', 0)),
                framework=getattr(args, 'macro_v12_framework', 'BAL_H'),
            )
        if stage == 'O1_FULL_PHYSICAL_CONTROLS':
            from .physical_macro_controls import run_macro_m1_controls
            return run_macro_m1_controls(
                cfg, comm, args.inventory, directory, sample=sample, marker=marker,
                source_sha=source_sha, input_path=input_path,
                model_identity=model_identity, build_started=build_started,
                profile='physical_macro_dd4_v12',
                memory_policy='SYMBOLIC_SIZED_LOCAL_MUMPS_V11',
            )
        if stage == 'O4_FINALIZE':
            return run_macro_v12_finalize(
                args.inventory, directory, source_sha=source_sha,
                input_path=input_path, model_identity=model_identity,
                budget_path=getattr(args, 'budget', None),
            )
        raise ValueError(f'unsupported V12 stage {stage!r}')
    if getattr(args, 'macro_v11_calibration', False):
        from .physical_macro_controls import run_macro_n1_calibration
        return run_macro_n1_calibration(
            cfg, comm, directory, sample=sample, marker=marker,
            source_sha=source_sha, input_path=input_path,
            model_identity=model_identity,
        )
    if getattr(args, 'macro_v11_controls', False) or getattr(args, 'macro_v10_controls', False):
        from .physical_macro_controls import run_macro_m1_controls
        from src.io.physical_recursive_profile import (
            MACRO_V10_PROFILE, MACRO_V11_PROFILE,
        )
        from src.solvers.fullspace_bounded_mumps import (
            LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
            SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        )
        is_v11 = getattr(args, 'macro_v11_controls', False)
        return run_macro_m1_controls(
            cfg, comm, args.inventory, directory, sample=sample, marker=marker,
            source_sha=source_sha, input_path=input_path,
            model_identity=model_identity,
            build_started=build_started,
            profile=MACRO_V11_PROFILE if is_v11 else MACRO_V10_PROFILE,
            memory_policy=(SYMBOLIC_SIZED_LOCAL_MUMPS_V11 if is_v11
                           else LEGACY_LOCAL_MUMPS_MEMORY_POLICY),
        )
    if getattr(args, 'bounded_j1_controls', False):
        from .physical_bounded_j1 import run_j1_controls
        return run_j1_controls(cfg, comm, args.inventory, directory,
            sample=sample, marker=marker, source_sha=source_sha,
            input_path=input_path, contract=selected_contract(args),
            model_identity=model_identity)
    if getattr(args,'high_trace_component',False) or getattr(args,'cached_trace_component',False) or getattr(args,'owner_route_trace_component',False) or getattr(args,'cell_joint_trace_component',False):
        from .physical_trace_controls import run_trace_component
        return run_trace_component(cfg,comm,args.inventory,directory,sample=sample,marker=marker,
            cached_exact=getattr(args,'cached_trace_component',False) or getattr(args,'owner_route_trace_component',False) or getattr(args,'cell_joint_trace_component',False),
            fixed_serial_owner_route=getattr(args,'owner_route_trace_component',False) or getattr(args,'cell_joint_trace_component',False),
            cell_joint_trace=getattr(args,'cell_joint_trace_component',False))
    if getattr(args,'bubble_amplification_diagnostic',False):
        from src.solvers.physical_bubble_amplification import run_amplification_diagnostic
        return run_amplification_diagnostic(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if getattr(args,'bubble_particular_diagnostic',False):
        from src.solvers.physical_bubble_particular import run_particular_diagnostic
        return run_particular_diagnostic(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if getattr(args,'bubble_enriched_component',False):
        from .physical_bubble_controls import run_bubble_component
        return run_bubble_component(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if args.bubble_local_tensor:
        from .physical_bubble_local_controls import run_bubble_local_tensor
        return run_bubble_local_tensor(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if args.projected_p4_component:
        return controls.run_projected_p4_component(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if args.p4_failure_diagnostic:
        return controls.run_p4_failure_diagnostic(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    return controls.run_recursive_components(cfg,comm,args.inventory,directory,
        target=component_contract(args.target)['I4']['target'],sample=sample,marker=marker)


def git_state(expected):
    def git(*args):
        return subprocess.check_output(
            _git_command(*args), cwd=_REPOSITORY_ROOT, text=True,
        ).strip()
    head=git('rev-parse','HEAD')
    if head!=expected or git('branch','--show-current')!='task39extra' or git('status','--porcelain'):
        raise RuntimeError('clean expected task39extra source required')
    return dict(head=head,branch='task39extra',git_dir=git('rev-parse','--absolute-git-dir'),
        upstream=git('rev-parse','--abbrev-ref','@{upstream}'),ahead_behind=git('rev-list','--left-right','--count','HEAD...@{upstream}'))


def atomic(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def _write_identity_files(root, *, source_sha, input_sha256, physical_model_sha256):
    """Write the small text identities required for every formal macro run."""
    (root / 'source_sha.txt').write_text(f'{source_sha}\n', encoding='utf-8')
    (root / 'input_sha256.txt').write_text(f'{input_sha256}\n', encoding='utf-8')
    (root / 'physical_model_sha256.txt').write_text(
        f'{physical_model_sha256}\n', encoding='utf-8')


def worker(args):
    cache_home=Path(getattr(args, 'jit_cache', None) or
                    (Path(args.output)/'jit_cache')).resolve()
    if os.environ.get('XDG_CACHE_HOME')!=str(cache_home):
        raise RuntimeError('isolated JIT cache must be inherited before worker imports')
    import numpy as np
    from petsc4py import PETSc
    from mpi4py import MPI
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from .workflow_timebase import clock_sample
    if (os.environ.get('_MYFENICS_WSL_QUALIFIED_ACTIVATION')!='1' or
        os.environ.get('PHYSICAL_TIMEBASE_GUARD')!='1' or not os.path.samefile(sys.executable,'.venv/bin/python') or
        MPI.COMM_WORLD.size!=1 or PETSc.ScalarType is not np.complex128 or PETSc.IntType is not np.int32):
        raise RuntimeError('qualified complex128/int32 MPI1 worker required')
    threads={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}
    if set(threads.values())!={'1'}:raise RuntimeError('threads must be one')
    source=git_state(args.source_sha)
    parent=int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID']);cap=int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    if parent==os.getpid() or not Path(f'/proc/{parent}').exists():raise RuntimeError('dedicated parent missing')
    macro=(getattr(args, 'macro_v10_controls', False)
           or getattr(args, 'macro_v11_controls', False)
           or getattr(args, 'macro_v11_calibration', False)
           or getattr(args, 'macro_v12', False)
           or getattr(args, 'p4_direction_diagnosis', False))
    macro_v11=(getattr(args, 'macro_v11_controls', False)
               or getattr(args, 'macro_v11_calibration', False))
    macro_v11_calibration=getattr(args, 'macro_v11_calibration', False)
    macro_v12=getattr(args, 'macro_v12', False)
    build_started = time.perf_counter() if macro else None
    payload=load_and_resolve(args.input).as_jsonable()
    if getattr(args, 'p4_direction_diagnosis', False):
        if payload['solver'].get('preconditioner') != 'physical_p4_direction_diagnosis_v13':
            raise ValueError('p4 direction diagnosis input must select its explicit profile')
        if payload['provenance']['physical_model_sha256'] != '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f':
            raise ValueError('p4 direction diagnosis requires the frozen original physical model')
        if payload['geometry'].get('cell_notch'):
            raise ValueError('p4 direction diagnosis does not admit a notch model')
    elif getattr(args, 'macro_v12', False):
        allowed_v12_models = {
            '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f',
            '7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec',
        }
        if payload['provenance']['physical_model_sha256'] not in allowed_v12_models:
            raise ValueError('V12 requires one of the frozen original or V5 notch physical models')
        if payload['geometry'].get('cell_notch') and getattr(args, 'macro_v12_stage', None) != 'O3_NOTCH':
            raise ValueError('cell_notch is authorized only for the conditional V12 O3_NOTCH stage')
    elif (payload['provenance']['physical_model_sha256']!='9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
          or payload['geometry'].get('cell_notch')):raise ValueError('G1 requires frozen original physical model')
    cfg=simulation_config_3d_from_normalized(payload)
    diagnostic=args.p4_failure_diagnostic;projected=args.projected_p4_component;bubble=args.bubble_local_tensor;enriched=args.bubble_enriched_component;particular=args.bubble_particular_diagnostic
    contract=selected_contract(args);root=Path(args.output)
    (root/'input_original.dat').write_bytes(Path(args.input).read_bytes())
    input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest()
    physical_sha256=payload['provenance']['physical_model_sha256']
    if macro:
        _write_identity_files(root, source_sha=source['head'],
            input_sha256=input_sha256, physical_model_sha256=physical_sha256)
    atomic(root/'resolved_config.json',dict(physical_input=payload,component_profile=contract,
        original_dat_solver_role='physical template only; old V5 PC is not invoked'))
    import petsc4py,slepc4py,dolfinx,basix,mpi4py
    from dolfinx.jit import get_options
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    cache_options=get_options(SAME_MESH_JIT_OPTIONS)
    if Path(cache_options['cache_dir']).resolve()!=cache_home/'fenics':
        raise RuntimeError('effective form JIT cache escaped isolated run root')
    module_objects = (petsc4py, slepc4py, dolfinx, basix, mpi4py)
    module_paths = {
        module.__name__: getattr(module, '__file__', None)
        for module in module_objects
    }
    module_versions = {
        module.__name__: getattr(module, '__version__', None)
        for module in module_objects
    }
    resolved_config_sha256 = hashlib.sha256(
        (root / 'resolved_config.json').read_bytes()
    ).hexdigest()
    if macro:
        control_phase = (
            'P4_DIRECTION_DIAGNOSIS_V13' if getattr(args, 'p4_direction_diagnosis', False)
            else f"V12_{getattr(args, 'macro_v12_stage', 'stage')}" if getattr(args, 'macro_v12', False)
            else 'V11_N1_calibration' if macro_v11_calibration
            else 'V11_M1_controls' if macro_v11 else 'V10_M1_controls'
        )
        manifest = {
            'source': source,
            'command': [sys.executable, *sys.argv],
            'input_sha256': input_sha256,
            'cwd': str(Path.cwd()), 'physical_sha256': physical_sha256,
            'resolved_config_sha256': resolved_config_sha256,
            'module_paths': module_paths,
            'module_versions': module_versions,
            'profile': selected_contract(args),
            'control_inventory': str(Path(args.inventory).resolve()),
            'jit_cache': {
                'xdg_cache_home': str(cache_home),
                'effective_cache_dir': str(cache_options['cache_dir']),
                'timeout': cache_options['timeout'],
                'initially_empty': not any(cache_home.iterdir()),
            },
            'abi': {
                'python': sys.executable, 'scalar': 'complex128', 'integer': 'int32',
                'threads': threads,
            },
        }
        atomic(root/'run_manifest.json', manifest)
        def sample():
            value=process_tree_snapshot(parent,control_phase,None);envelope=memory_envelope()
            value['launch_cap_bytes']=min(cap,value['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes'])
            if (not value['all_status_readable'] or value['swap_bytes'] or
                    value['rss_bytes']>=value['launch_cap_bytes'] or
                    envelope['effective_available_bytes']<envelope['reserve_bytes']):
                raise RuntimeError('whole-workflow resource gate failed')
            return value
        def marker(name,facts):
            stamp=clock_sample()
            atomic(root/'phase.json', {
                'phase': control_phase, 'stage': name, 'clock': stamp,
            })
            with (root/'stages.jsonl').open('a') as stream:
                stream.write(json.dumps({
                    'stage': name, 'clock': stamp, 'facts': facts,
                })+'\n')
        try:
            records_root = root / 'records'
            result=dispatch_components(args,cfg,MPI.COMM_WORLD,records_root,
                sample=sample,marker=marker,source_sha=source['head'],input_path=Path(args.input),
                model_identity={
                    'source_sha': source['head'],
                    'physical_model_sha256': physical_sha256,
                    'input_sha256': input_sha256,
                    'profile': contract.get('profile') or contract.get('identity'),
                    'scalar_type': 'complex128',
                    'mpi_size': int(MPI.COMM_WORLD.Get_size()),
                },
                build_started=build_started)
            manifest.update(
                status='finished', result=result.get('status', 'J1_CONTROLS_COMPLETED'),
                model_identity=result.get('model_identity'),
                native_map_sha256=result.get('maps', {}).get('native_map_sha256'),
                macro_stack_identity=result.get('macro_stack_identity'),
            )
            atomic(root/'run_manifest.json', manifest)
            atomic(root/'run_summary.json', {
            'schema': ('task39extra.review-v13.p4-direction-run-summary.v1'
                       if getattr(args, 'p4_direction_diagnosis', False) else
                       'task39extra.review-v12.stage-run-summary.v1'
                       if macro_v12 else
                       'task39extra.review-v11.m1-run-summary.v1'
                       if macro_v11 else 'task39extra.review-v10.m1-run-summary.v1'),
                'status': 'COMPLETED',
                'command': [sys.executable, *sys.argv],
                'source_sha': source['head'],
                'input_sha256': input_sha256,
                'physical_model_sha256': physical_sha256,
                'inventory_sha256': hashlib.sha256(
                    Path(args.inventory).read_bytes()).hexdigest(),
                'resolved_config_sha256': resolved_config_sha256,
                'module_paths': module_paths,
                'module_versions': module_versions,
                'result_status': result.get('status'),
                'new_i4_calls': result.get('new_i4_calls'),
                'attempted_i4_calls': result.get('attempted_i4_calls'),
                'completed_i4_calls': result.get('completed_i4_calls'),
                'bare_b4_calls': result.get('bare_b4_calls'),
                'bare_b4_attempted_calls': result.get('bare_b4_attempted_calls'),
                'bare_b4_completed_calls': result.get('bare_b4_completed_calls'),
                'framework_decision': result.get('framework_decision'),
                'stage_times': result.get('stage_times'),
                'model_identity': result.get('model_identity'),
                'native_map_sha256': result.get('maps', {}).get('native_map_sha256'),
                'macro_stack_identity': result.get('macro_stack_identity'),
                'run_manifest_sha256': hashlib.sha256(
                    (root/'run_manifest.json').read_bytes()).hexdigest(),
            })
            return result
        except BaseException as exc:
            partial_path = root / 'records' / (
                'p4_direction_summary.json' if getattr(args, 'p4_direction_diagnosis', False) else
                'outer_summary.json' if macro_v12 and getattr(args, 'macro_v12_stage', '').startswith(('O2_', 'O3_')) else
                'm1_summary.json' if macro_v12 and getattr(args, 'macro_v12_stage', '') == 'O1_FULL_PHYSICAL_CONTROLS' else
                'o0_summary.json' if macro_v12 else
                'n1_summary.json' if macro_v11_calibration else 'm1_summary.json'
            )
            partial = {}
            if partial_path.exists():
                try:
                    partial = json.loads(partial_path.read_text())
                except (OSError, json.JSONDecodeError) as partial_exc:
                    partial = {
                        'status': 'PARTIAL_SUMMARY_UNREADABLE',
                        'read_error': f'{type(partial_exc).__name__}: {partial_exc}',
                    }
            partial_evidence = {
                'path': str(partial_path),
                'sha256': hashlib.sha256(partial_path.read_bytes()).hexdigest()
                if partial_path.exists() else None,
                'status': partial.get('status'),
                'new_i4_calls': partial.get('new_i4_calls'),
                'attempted_i4_calls': partial.get('attempted_i4_calls'),
                'completed_i4_calls': partial.get('completed_i4_calls'),
                'bare_b4_calls': partial.get('bare_b4_calls'),
                'bare_b4_attempted_calls': partial.get('bare_b4_attempted_calls'),
                'bare_b4_completed_calls': partial.get('bare_b4_completed_calls'),
                'stage_times': partial.get('stage_times'),
                'last_safe_stage': partial.get('last_safe_stage'),
                'failure_gate': partial.get('failure_gate'),
                'numeric_attempts': partial.get('numeric_attempts'),
                'numeric_factorizations': partial.get('numeric_factorizations'),
                'comparisons': partial.get('comparisons'),
                'gate_pass': partial.get('gate_pass'),
                'exception_type': partial.get('exception_type'),
                'failure_classification': partial.get('failure_classification'),
                'macro_stack_identity': partial.get('macro_stack_identity'),
            }
            manifest.update(status='failed', exception_type=type(exc).__name__,
                            exception=str(exc), partial_m1_summary=partial_evidence)
            atomic(root/'run_manifest.json', manifest)
            atomic(root/'run_summary.json', {
                'schema': ('task39extra.review-v13.p4-direction-run-summary.v1'
                           if getattr(args, 'p4_direction_diagnosis', False) else
                           'task39extra.review-v12.stage-run-summary.v1'
                           if macro_v12 else
                           'task39extra.review-v11.m1-run-summary.v1'
                           if macro_v11 else 'task39extra.review-v10.m1-run-summary.v1'),
                'status': 'FAILED',
                'command': [sys.executable, *sys.argv],
                'source_sha': source['head'],
                'input_sha256': input_sha256,
                'physical_model_sha256': physical_sha256,
                'inventory_sha256': hashlib.sha256(
                    Path(args.inventory).read_bytes()).hexdigest(),
                'resolved_config_sha256': resolved_config_sha256,
                'module_paths': module_paths,
                'module_versions': module_versions,
                'result_status': partial.get('status'),
                'exception_type': type(exc).__name__,
                'exception': str(exc),
                'partial_m1_summary': partial_evidence,
                'new_i4_calls': partial.get('new_i4_calls'),
                'attempted_i4_calls': partial.get('attempted_i4_calls'),
                'completed_i4_calls': partial.get('completed_i4_calls'),
                'bare_b4_calls': partial.get('bare_b4_calls'),
                'bare_b4_attempted_calls': partial.get('bare_b4_attempted_calls'),
                'bare_b4_completed_calls': partial.get('bare_b4_completed_calls'),
                'framework_decision': partial.get('framework_decision'),
                'numeric_attempts': partial.get('numeric_attempts'),
                'numeric_factorizations': partial.get('numeric_factorizations'),
                'comparisons': partial.get('comparisons'),
                'gate_pass': partial.get('gate_pass'),
                'failure_classification': partial.get('failure_classification'),
                'stage_times': partial.get('stage_times'),
                'model_identity': partial.get('model_identity'),
                'native_map_sha256': partial.get('maps', {}).get('native_map_sha256'),
                'macro_stack_identity': partial.get('macro_stack_identity'),
                'run_manifest_sha256': hashlib.sha256(
                    (root/'run_manifest.json').read_bytes()).hexdigest(),
            })
            raise
        finally:
            if (root/'run_manifest.json').exists():
                manifest['source_after']=git_state(args.source_sha)
                atomic(root/'run_manifest.json', manifest)
                summary_path = root/'run_summary.json'
                if summary_path.exists():
                    run_summary = json.loads(summary_path.read_text())
                    run_summary['run_manifest_sha256'] = hashlib.sha256(
                        (root/'run_manifest.json').read_bytes()).hexdigest()
                    run_summary['source_after'] = manifest['source_after']
                    atomic(summary_path, run_summary)
    if getattr(args, 'bounded_j1_controls', False):
        # Preserve the established J1 worker contract; V10's run summary and
        # stage ledger are intentionally confined to the macro branch above.
        control_phase = ('B_projected_finite_compare_and_controls'
                         if getattr(args, 'bounded_j1_route', 'ENTITY16') == 'PROJECTED_SEQ2_16'
                         else 'J1_controls')
        manifest=dict(source=source,
            input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
            cwd=str(Path.cwd()), physical_sha256=payload['provenance']['physical_model_sha256'],
            profile=selected_contract(args),
            control_inventory=str(Path(args.inventory).resolve()),
            jit_cache=dict(xdg_cache_home=str(cache_home),
                effective_cache_dir=str(cache_options['cache_dir']),
                timeout=cache_options['timeout'], cold=True),
            abi=dict(python=sys.executable, scalar='complex128', integer='int32',
                threads=threads))
        atomic(root/'run_manifest.json', manifest)
        def sample():
            value=process_tree_snapshot(parent,control_phase,None);envelope=memory_envelope()
            value['launch_cap_bytes']=min(cap,value['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes'])
            if (not value['all_status_readable'] or value['swap_bytes'] or
                    value['rss_bytes']>=value['launch_cap_bytes'] or
                    envelope['effective_available_bytes']<envelope['reserve_bytes']):
                raise RuntimeError('whole-workflow resource gate failed')
            return value
        def marker(name,facts):
            stamp=clock_sample()
            atomic(root/'phase.json',dict(phase=control_phase,stage=name,clock=stamp))
            with (root/'stages.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(stage=name,clock=stamp,facts=facts))+'\n')
        try:
            result=dispatch_components(args,cfg,MPI.COMM_WORLD,root,
                sample=sample,marker=marker,source_sha=source,input_path=Path(args.input),
                model_identity=dict(
                    source_sha=source,
                    physical_model_sha256=payload['provenance']['physical_model_sha256'],
                    input_sha256=payload['provenance']['input_sha256'],
                    profile=contract['profile'], scalar_type='complex128',
                    mpi_size=int(MPI.COMM_WORLD.Get_size())))
            manifest.update(status='finished', result=result.get('status', 'J1_CONTROLS_COMPLETED'))
            atomic(root/'run_manifest.json', manifest)
            return result
        finally:
            if (root/'run_manifest.json').exists():
                manifest['source_after']=git_state(args.source_sha)
                atomic(root/'run_manifest.json', manifest)
    inventory=json.loads(Path(args.inventory).read_text())
    if bubble:
        native_maps={};mode_sha=inventory['mode_sha256']
    elif diagnostic or projected or enriched or particular or args.bubble_amplification_diagnostic or args.high_trace_component or args.cached_trace_component or args.owner_route_trace_component or args.cell_joint_trace_component:
        native_maps={'4':inventory['packets']['map']}
        mode_sha=inventory['mode_sha256']
    else:
        evidence_root=Path(inventory['six_calibration_rhs'][0]['input_json']).parent
        native_maps={str(level):dict(path=str(evidence_root/f'native_constraint_map_p{level}.json'),
            sha256=hashlib.sha256((evidence_root/f'native_constraint_map_p{level}.json').read_bytes()).hexdigest()) for level in (6,4)}
        mode_sha=inventory['models'][0]['mode_sha']
    manifest=dict(source=source,input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        resolved_sha256=hashlib.sha256((root/'resolved_config.json').read_bytes()).hexdigest(),
        command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:]],
        cwd=str(Path.cwd()),physical_sha256=payload['provenance']['physical_model_sha256'],
        mode_sha256=mode_sha,native_maps=native_maps,
        native_map_bridge='exact fieldwise comparison to saved maps before component calls',
        jit_cache=dict(xdg_cache_home=str(cache_home),effective_cache_dir=str(cache_options['cache_dir']),
            timeout=cache_options['timeout'],cold=True),
        profile=contract,abi=dict(python=sys.executable,scalar='complex128',integer='int32',threads=threads,
            modules={m.__name__:m.__file__ for m in (petsc4py,slepc4py,dolfinx,basix,mpi4py)}),
        inventory_sha256=hashlib.sha256(Path(args.inventory).read_bytes()).hexdigest())
    if particular:manifest['native_map_bridge']='frozen p4 DOF/MPC reused; rebuilt geometry/permutations exactly compared'
    atomic(root/'run_manifest.json',manifest)
    def sample():
        value=process_tree_snapshot(parent,'G1_components',None);envelope=memory_envelope()
        value['launch_cap_bytes']=min(cap,value['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes'])
        if (not value['all_status_readable'] or value['swap_bytes'] or value['rss_bytes']>=value['launch_cap_bytes']
            or envelope['effective_available_bytes']<envelope['reserve_bytes']):
            raise RuntimeError('whole-tree resource gate failed')
        return value
    def marker(name,facts):
        stamp=clock_sample()
        atomic(root/'phase.json',dict(phase='components',stage=name,clock=stamp))
        with (root/'stages.jsonl').open('a') as stream:stream.write(json.dumps(dict(stage=name,clock=stamp,facts=facts))+'\n')
    try:
        dispatch_components(args,cfg,MPI.COMM_WORLD,root/'records',sample=sample,marker=marker,
            source_sha=source,input_path=Path(args.input))
    finally:
        identity=root/'records'/(
            'n1_summary.json' if macro_v11_calibration else
            'm1_summary.json' if macro else
            'trace_source_bridge.json' if args.high_trace_component or args.cached_trace_component or args.owner_route_trace_component or args.cell_joint_trace_component else
            'amplification_map_bridge.json' if args.bubble_amplification_diagnostic else
            'particular_map_bridge.json' if particular else
            'bubble_source_bridge.json' if enriched else
            'bubble_cell_frozen.json' if bubble else
            'projected_source_bridge.json' if projected else
            'input_bridge.json' if diagnostic else 'fresh_identity.json'
        )
        if macro:
            stack_identity = root/'records'/'macro_stack_identity.json'
            summary_payload = json.loads(identity.read_text()) if identity.exists() else {}
            stack_payload = json.loads(stack_identity.read_text()) if stack_identity.exists() else {}
            map_ok = bool(
                summary_payload.get('status') == 'M1_CONTROLS_COMPLETED'
                and isinstance(summary_payload.get('maps'), dict)
                and summary_payload['maps'].get('p6_independent_rows')
                and summary_payload['maps'].get('p4_independent_rows')
                and stack_payload.get('profile') == selected_contract(args)['identity']
                and stack_payload.get('mode_sha256')
                and stack_payload.get('coverage')
            )
            manifest['native_map_bridge_status'] = (
                'PASS' if map_ok else 'FAIL' if identity.exists() else 'NOT_REACHED'
            )
        else:
            manifest['native_map_bridge_status']='PASS' if identity.exists() else 'NOT_REACHED'
        if diagnostic and identity.exists():
            manifest['native_map_bridge_status']=p4_bridge_status(identity)
        if (projected or enriched or particular or args.bubble_amplification_diagnostic or args.high_trace_component or args.cached_trace_component or args.owner_route_trace_component or args.cell_joint_trace_component) and identity.exists():
            from math import isfinite
            error=json.loads(identity.read_text())['relative_error']
            manifest['native_map_bridge_status']='PASS' if isfinite(error) and error<=1e-10 else 'FAIL'
        if bubble:manifest['native_map_bridge_status']='NOT_APPLICABLE_LOCAL_TENSOR_ONLY'
        if identity.exists():
            manifest['fresh_identity']=dict(path=str(identity),sha256=hashlib.sha256(identity.read_bytes()).hexdigest())
        atomic(root/'run_manifest.json',manifest)


def build_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input','inventory','output','source-sha'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--budget', required=False, default=None)
    parser.add_argument('--jit-cache', type=Path, default=None,
        help='reusable hash-bound JIT cache; defaults to the attempt-local cache')
    parser.add_argument('--target',choices=('lo',),default='lo')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--p4-failure-diagnostic',action='store_true')
    group.add_argument('--projected-p4-component',action='store_true')
    group.add_argument('--bubble-local-tensor',action='store_true')
    group.add_argument('--bubble-enriched-component',action='store_true')
    group.add_argument('--bubble-particular-diagnostic',action='store_true')
    group.add_argument('--bubble-amplification-diagnostic',action='store_true')
    group.add_argument('--high-trace-component',action='store_true')
    group.add_argument('--cached-trace-component',action='store_true')
    group.add_argument('--owner-route-trace-component',action='store_true')
    group.add_argument('--cell-joint-trace-component',action='store_true')
    group.add_argument('--bounded-j1-controls',action='store_true')
    group.add_argument('--macro-v10-controls', action='store_true')
    group.add_argument('--macro-v11-controls', action='store_true')
    group.add_argument('--macro-v11-calibration', action='store_true')
    group.add_argument('--macro-v12', action='store_true')
    group.add_argument('--p4-direction-diagnosis', action='store_true')
    parser.add_argument(
        '--macro-v12-supplement', action='store_true',
        help='use the independent bounded V12 supplement ledger',
    )
    parser.add_argument('--macro-v12-stage', choices=(
        'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS',
        'O2_RESTART_PROBE_32', 'O2_RESTART_PROBE_64',
        'O3_ORIGINAL', 'O3_NOTCH', 'O4_FINALIZE',
    ), default=None)
    parser.add_argument('--macro-v12-outer-restart', type=int, choices=(0, 32, 64), default=0)
    parser.add_argument('--macro-v12-framework', choices=('BAL_H', 'ONE_C'), default='BAL_H')
    parser.add_argument('--bounded-j1-route', choices=('ENTITY16', 'PROJECTED_SEQ2_16',
                                                       'ENTITY_GCROT8',
                                                       'ENTITY_GCROT8_NEW16'),
        default='ENTITY16',
        help='select the bounded J1 route; ENTITY_GCROT8 is V8 and ENTITY_GCROT8_NEW16 is the opt-in V9 equal-new-work screen')
    parser.add_argument('--amplification-recording-retry',action='store_true',
        help='one reviewed retry of the frozen pre-factor mappingproxy recording failure')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    return parser


def amplification_recording_retry(args,budget):
    """Admit only the audited dd9b pre-factor recording failure, once."""
    attempts=budget.get('bubble_amplification_diagnostic_attempts',[])
    if not args.amplification_recording_retry:
        if args.bubble_amplification_diagnostic and attempts:
            raise ValueError('unique amplification diagnosis already attempted')
        return None
    failed_sha='dd9b6fae5cc5509459d837a99197f9be34007e18'
    root=Path('benchmarks/artifacts/task39extra/v6_bubble_amplification_diagnostic')/failed_sha/'a2r160_g1'
    if (not args.bubble_amplification_diagnostic or args.source_sha==failed_sha or len(attempts)!=1
        or attempts[0]['source']!=failed_sha or attempts[0]['root']!=str(root)
        or attempts[0]['classification']!='WORKER_FAILED'):
        raise ValueError('recording retry requires the unique frozen failed attempt')
    path=Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_amplification_readout.json')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!='11e04fd284f5aa75a6b35a251320730f065c6b43e7276ef6a193cc951299c9be':
        raise ValueError('reviewed failure readout changed')
    readout=json.loads(path.read_text());hashes={e['path']:e['sha256'] for e in readout['evidence']}
    for p in (root/'terminal.json',root/'records/amplification_costs.json',root/'watchdog/worker.log'):
        if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p)]:
            raise ValueError('frozen failure evidence changed')
    terminal=json.loads((root/'terminal.json').read_text())
    costs=json.loads((root/'records/amplification_costs.json').read_text())
    log=(root/'watchdog/worker.log').read_text()
    if (not terminal['descendants_cleared'] or terminal['remaining_child_pids']
        or costs['counts']['factor']!=0 or costs['bottom']
        or 'TypeError: Object of type mappingproxy is not JSON serializable' not in log
        or "save('amplification_coarse_rhs'" not in log
        or not readout['all_checks_passed'] or not readout['resources']['host_ps_confirmed_absent']):
        raise ValueError('not the approved pre-factor serialization failure')
    return dict(failed_root=str(root),readout_sha256=digest,allowed_retries=1,
        reason='mappingproxy recording failure before factor; old attempt and charge preserved')


from .physical_bounded_budget import LIMIT_SECONDS as J1_BATCH_LIMIT_SECONDS
from .physical_bounded_budget import SCHEMA as J1_BUDGET_SCHEMA
J1_CONTROLS_LIMIT_SECONDS = 3600.0
V8_K0_K1_BUDGET_SCHEMA = 'task39extra.review-v8-k0-k1-budget.v1'
V8_K0_K1_LIMIT_SECONDS = 3600.0
V8_FINITE_CONTROLS_LIMIT_SECONDS = 900.0
V9_K0_K1_BUDGET_SCHEMA = 'task39extra.review-v9-equal-new-work-budget.v1'
V9_K0_K1_LIMIT_SECONDS = 3600.0
V9_FINITE_CONTROLS_LIMIT_SECONDS = 900.0
B_PROJECTED_CONTROLS_LIMIT_SECONDS = 5400.0
B_PROJECTED_CONTROLS_GROUP = 'B_projected_controls'
B_PROJECTED_CONTROLS_KIND = 'bounded_projected_controls'
MACRO_M1_CONTROLS_LIMIT_SECONDS = 1200.0
MACRO_M1_CONTROLS_GROUP = 'V10_M1_controls'
MACRO_M1_CONTROLS_KIND = 'physical_macro_dd4_v10_m1_controls'
MACRO_M1_TOTAL_LIMIT_SECONDS = 5400.0
MACRO_M1_BUILD_LIMIT_SECONDS = 3600.0
MACRO_M1_LEDGER_SCHEMA = 'task39extra.review-v10-m0-m1-budget.v1'
MACRO_V11_TOTAL_LIMIT_SECONDS = 7200.0
MACRO_V11_BUILD_LIMIT_SECONDS = 3600.0
MACRO_V11_CONTROLS_LIMIT_SECONDS = 1200.0
MACRO_V11_CALIBRATION_LIMIT_SECONDS = 900.0
MACRO_V11_LEDGER_SCHEMA = 'task39extra.review-v11-n0-n2-budget.v1'
MACRO_V12_LEDGER_SCHEMA = 'task39extra.review-v12-o0-o4-budget.v1'
MACRO_V12_SUPPLEMENT_LEDGER_SCHEMA = 'task39extra.review-v12-supplement-budget.v1'
MACRO_V12_STAGE_LIMITS = {
    'O0_PRECHECK': 7200.0,
    'O1_FULL_PHYSICAL_CONTROLS': 7200.0,
    'O2_RESTART_PROBE_32': 3600.0,
    'O2_RESTART_PROBE_64': 3600.0,
    'O3_ORIGINAL': 14400.0,
    'O3_NOTCH': 14400.0,
    'O4_FINALIZE': 43200.0,
}
MACRO_V12_SUPPLEMENT_STAGE_LIMITS = {
    'O1_FULL_PHYSICAL_CONTROLS': 3600.0,
    'O2_RESTART_PROBE_32': 3600.0,
    'O2_RESTART_PROBE_64': 3600.0,
}
MACRO_V12_SUPPLEMENT_TOTAL_LIMIT_SECONDS = 10800.0
MACRO_V12_SUPPLEMENT_O1_COMPUTE_LIMIT_SECONDS = 1200.0


def _j1_charge_seconds(budget):
    from .physical_bounded_budget import _charged_seconds
    return _charged_seconds(budget)


def _controls_charge_seconds(budget, group):
    total=0.0
    for item in budget.get('attempts', []):
        if item.get('budget_group') != group:
            continue
        value=(item.get('reserved_seconds') if item.get('status') == 'RESERVED'
               else item.get('elapsed_seconds', item.get('charge_seconds')))
        if value is not None:
            total += float(value)
    return total


def _j1_controls_charge_seconds(budget):
    return _controls_charge_seconds(budget, 'J0_J1_controls')


def _load_macro_ledger(path, *, v11=False):
    path = Path(path)
    if not path.exists():
        raise ValueError(
            ('V11 N0/N2 ledger is missing; initialize it once from the explicit preparation record'
             if v11 else
             'V10 M0/M1 ledger is missing; initialize it once from the explicit preparation record')
        )
    budget = json.loads(path.read_text())
    schema = MACRO_V11_LEDGER_SCHEMA if v11 else MACRO_M1_LEDGER_SCHEMA
    total = MACRO_V11_TOTAL_LIMIT_SECONDS if v11 else MACRO_M1_TOTAL_LIMIT_SECONDS
    build = MACRO_V11_BUILD_LIMIT_SECONDS if v11 else MACRO_M1_BUILD_LIMIT_SECONDS
    controls = MACRO_V11_CONTROLS_LIMIT_SECONDS if v11 else MACRO_M1_CONTROLS_LIMIT_SECONDS
    if budget.get('schema') != schema:
        raise ValueError(
            'V11 N0/N2 requires its independent ledger; old V10/V6 ledgers are not accepted'
            if v11 else
            'V10 M1 requires its independent M0/M1 ledger; V6 ledger is not accepted'
        )
    if budget.get('total_limit_seconds') != total:
        raise ValueError('selected macro ledger has the wrong total limit')
    if budget.get('build_limit_seconds') != build:
        raise ValueError('selected macro ledger has the wrong build limit')
    if budget.get('controls_limit_seconds') != controls:
        raise ValueError('selected macro ledger has the wrong controls limit')
    return budget


def _macro_charged_seconds(budget):
    return float(budget.get('charged_seconds', 0.0))


def _load_v12_ledger(path, *, supplement=False):
    """Load the pre-recorded V12 activity ledger; never invent its debit."""

    path = Path(path)
    if not path.is_file():
        raise ValueError(
            'V12 O0-O4 ledger is missing; create the explicit artifact ledger '
            'with its implementation_activity record before launching a stage'
        )
    budget = json.loads(path.read_text())
    expected_limits = (
        {
            'total_limit_seconds': MACRO_V12_SUPPLEMENT_TOTAL_LIMIT_SECONDS,
            'o1_workflow_limit_seconds': 3600.0,
            'o1_compute_limit_seconds': MACRO_V12_SUPPLEMENT_O1_COMPUTE_LIMIT_SECONDS,
        }
        if supplement else
        {
            'total_limit_seconds': 43200.0,
            'o0_o1_limit_seconds': 7200.0,
        }
    )
    expected_schema = (
        MACRO_V12_SUPPLEMENT_LEDGER_SCHEMA if supplement
        else MACRO_V12_LEDGER_SCHEMA
    )
    if budget.get('schema') != expected_schema:
        raise ValueError(
            'V12 supplement requires its independent supplement ledger'
            if supplement else 'V12 stage requires its independent O0-O4 ledger'
        )
    for key, expected in expected_limits.items():
        if budget.get(key) != expected:
            raise ValueError(f'V12 ledger has the wrong {key}')
    implementation = budget.get('implementation_activity')
    if not isinstance(implementation, dict):
        raise ValueError('V12 ledger must contain the explicit implementation_activity record')
    implementation_seconds = implementation.get('charged_seconds')
    if not isinstance(implementation_seconds, (int, float)) or not isfinite(float(implementation_seconds)):
        raise ValueError('V12 implementation_activity charged_seconds is invalid')
    if float(implementation_seconds) < 0.0:
        raise ValueError('V12 implementation_activity charged_seconds must be non-negative')
    if not supplement:
        if float(budget.get('charged_seconds', 0.0)) < float(implementation_seconds):
            raise ValueError('V12 ledger charged_seconds is below its implementation debit')
        if float(budget.get('o0_o1_charged_seconds', 0.0)) < float(implementation_seconds):
            raise ValueError('V12 O0/O1 ledger charge is below its implementation debit')
    return budget


def launch_p4_direction_diagnosis(args):
    """Supervise the one-shot V13 P0--P4 direction diagnosis.

    This profile intentionally has no budget ledger.  Its existing runner
    watchdog and the source/input identities provide the admission boundary;
    the worker owns the build, per-input, and total safe points.
    """
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME
    from src.io import load_and_resolve
    from src.io.physical_recursive_profile import P4_DIRECTION_DIAGNOSIS_PROFILE

    source = git_state(args.source_sha)
    input_path = Path(args.input).resolve()
    inventory_path = Path(args.inventory).resolve()
    root = Path(args.output).resolve()
    if not input_path.is_file():
        raise ValueError(f"p4 direction diagnosis input is missing: {input_path}")
    if not inventory_path.is_file():
        raise ValueError(f"p4 direction diagnosis inventory is missing: {inventory_path}")
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    if payload['solver'].get('preconditioner') != P4_DIRECTION_DIAGNOSIS_PROFILE:
        raise ValueError('p4 direction diagnosis input selected the wrong profile')
    if payload['solver'].get('stage') != 'P4_DIRECTION_DIAGNOSIS_V13':
        raise ValueError('p4 direction diagnosis input selected the wrong stage')
    if payload['provenance'].get('physical_model_sha256') != (
        '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
    ):
        raise ValueError('p4 direction diagnosis requires the frozen original physical model')
    if payload['geometry'].get('cell_notch'):
        raise ValueError('p4 direction diagnosis does not admit a notch model')
    if root.exists():
        raise FileExistsError(f"p4 direction diagnosis output must be fresh: {root}")
    root.mkdir(parents=True, exist_ok=False)
    cache_home = (root / 'jit_cache').resolve()
    cache_home.mkdir(parents=True, exist_ok=False)
    inventory_sha256 = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    atomic(root / 'launch_plan.json', {
        'schema': 'task39extra.review-v13.p4-direction-launch-plan.v1',
        'source': source,
        'input': str(input_path),
        'input_sha256': input_sha256,
        'inventory': str(inventory_path),
        'inventory_sha256': inventory_sha256,
        'profile': P4_DIRECTION_DIAGNOSIS_PROFILE,
        'stage': 'P4_DIRECTION_DIAGNOSIS_V13',
        'wall_seconds': 7200.0,
        'budget_policy': {
            'total_seconds': 7200.0,
            'build_seconds': 1200.0,
            'per_input_seconds': 1500.0,
            'ledger': 'not_used',
        },
        'jit_cache_home': str(cache_home),
        'jit_cache_initially_empty': True,
    })
    command = [
        sys.executable, '-m', 'src.runners.physical_recursive_entry',
        '--input', str(input_path), '--inventory', str(inventory_path),
        '--output', str(root), '--source-sha', args.source_sha,
        '--target', 'lo', '--p4-direction-diagnosis',
        '--jit-cache', str(cache_home), '--worker',
    ]
    result = None
    try:
        result = supervise(
            command, root / 'watchdog', wall_seconds=7200.0,
            phase_path=root / 'phase.json', hard_stop_immediate=True,
            timebase_guard=True, timebase_policy=CONSERVATIVE_REALTIME,
            stop_on_global_swap=True, source_state=source,
            worker_environment={'XDG_CACHE_HOME': str(cache_home)},
        )
        atomic(root / 'terminal.json', result)
        atomic(root / 'source_after.json', git_state(args.source_sha))
        if result.get('classification') != 'COMPLETED':
            raise SystemExit(1)
        return result
    except BaseException:
        if result is not None and not (root / 'terminal.json').exists():
            atomic(root / 'terminal.json', result)
        raise


def _launch_macro_m1_controls(args):
    """Supervise V10 M1 or V11 M1/N2 against its independent ledger."""
    from benchmarks.subreaper_watchdog import supervise

    from .workflow_timebase import CONSERVATIVE_REALTIME, ClockBudget, clock_sample

    source = git_state(args.source_sha)
    v11 = getattr(args, 'macro_v11_controls', False)
    total_limit = MACRO_V11_TOTAL_LIMIT_SECONDS if v11 else MACRO_M1_TOTAL_LIMIT_SECONDS
    build_limit = MACRO_V11_BUILD_LIMIT_SECONDS if v11 else MACRO_M1_BUILD_LIMIT_SECONDS
    controls_limit = MACRO_V11_CONTROLS_LIMIT_SECONDS if v11 else MACRO_M1_CONTROLS_LIMIT_SECONDS
    control_group = 'V11_N0_N2_controls' if v11 else MACRO_M1_CONTROLS_GROUP
    control_kind = 'physical_macro_dd4_v11_m1_n2_controls' if v11 else MACRO_M1_CONTROLS_KIND
    profile_label = 'V11' if v11 else 'V10'
    budget_path = Path(args.budget).resolve()
    inventory_path = Path(args.inventory).resolve()
    if not inventory_path.exists():
        raise ValueError(f'{profile_label} M1 requires the audited G0 inventory')
    input_path = Path(args.input).resolve()
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    inventory_sha256 = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    from src.io import load_and_resolve
    physical_sha256 = load_and_resolve(input_path).physical_model_sha256
    with (budget_path.with_suffix('.lock')).open('a') as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = _load_macro_ledger(budget_path, v11=v11)
        if v11:
            if any(item.get('kind') == control_kind and item.get('measurement_committed')
                   for item in budget.get('attempts', [])):
                raise ValueError('V11 N0/N2 control measurement is already committed')
            if not any(
                item.get('kind') == 'physical_macro_dd4_v11_n1_calibration'
                and item.get('measurement_committed')
                for item in budget.get('attempts', [])
            ):
                raise ValueError('V11 N2 requires a committed successful N1 calibration')
        elif any(item.get('measurement_committed') for item in budget.get('attempts', [])):
            raise ValueError('V10 M1 measurement is already committed; engineering-only retries must precede a completed control')
        remaining = total_limit - _macro_charged_seconds(budget)
        if remaining <= 0:
            raise RuntimeError(f'{profile_label} macro ledger exhausted')
        active_lock = budget_path.parent / (
            'macro_v11_n0_n2_active.lock' if v11 else 'macro_v10_m1_active.lock'
        )
        descriptor = os.open(active_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        root = Path(args.output)
        result = None
        clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
        entry = {
            'kind': control_kind,
            'budget_group': control_group,
            'source': args.source_sha,
            'root': str(root),
            'status': 'RESERVED',
            'reservation_seconds': remaining,
            'actual_seconds': None,
            'measurement_committed': False,
            'measurement_state': 'not_started',
            'controls_limit_seconds': controls_limit,
            'build_limit_seconds': build_limit,
            'total_limit_seconds': total_limit,
            'inventory': str(inventory_path),
            'inventory_sha256': inventory_sha256,
            'input': str(input_path),
            'input_sha256': input_sha256,
            'physical_model_sha256': physical_sha256,
            'nested_ledger': f'independent {profile_label} ledger',
        }
        budget.setdefault('attempts', []).append(entry)
        atomic(budget_path, budget)
        try:
            root.mkdir(parents=True, exist_ok=False)
            cache_home = (root.parent / 'jit_cache').resolve()
            cache_home.mkdir(parents=True, exist_ok=True)
            atomic(root / 'launch_plan.json', {
                'source': source,
                'contract': selected_contract(args),
                'wall_seconds': remaining,
                'budget_before': budget,
                'inventory': str(inventory_path),
                'control_group': control_group,
                'jit_cache_home': str(cache_home),
                'jit_cache_initially_empty': not any(cache_home.iterdir()),
                'jit_cache_reused': any(cache_home.iterdir()),
                'inclusive_budget': {
                    'total': total_limit,
                    'build': build_limit,
                    'controls': controls_limit,
                },
            })
            command = [
                sys.executable, '-m', 'src.runners.physical_recursive_entry',
                '--input', str(Path(args.input).resolve()),
                '--inventory', str(inventory_path),
                '--output', str(root), '--budget', str(budget_path),
                '--source-sha', args.source_sha, '--target', 'lo',
                ('--macro-v11-controls' if v11 else '--macro-v10-controls'),
                '--jit-cache', str(cache_home), '--worker',
            ]
            result = supervise(
                command, root / 'watchdog', wall_seconds=remaining,
                phase_path=root / 'phase.json', hard_stop_immediate=True,
                timebase_guard=True, timebase_policy=CONSERVATIVE_REALTIME,
                stop_on_global_swap=True, source_state=source,
                worker_environment={'XDG_CACHE_HOME': str(cache_home)},
            )
            interval = result['workflow_clock_interval']
            charge = float(interval['budget_seconds'])
            entry['clock_interval'] = interval
            entry.update(status=result['classification'],
                         actual_seconds=charge,
                         conservative_seconds=charge,
                         descendants_cleared=result.get('descendants_cleared'))
            summary_path = root / 'run_summary.json'
            if summary_path.exists():
                run_summary = json.loads(summary_path.read_text())
                entry['measurement_committed'] = (
                    run_summary.get('status') == 'COMPLETED'
                    and run_summary.get('result_status') == 'M1_CONTROLS_COMPLETED'
                )
                entry['measurement_state'] = (
                    'completed' if entry['measurement_committed'] else 'partial_or_engineering_failure'
                )
                entry['run_summary_sha256'] = hashlib.sha256(
                    summary_path.read_bytes()).hexdigest()
            budget['charged_seconds'] = _macro_charged_seconds(budget) + charge
            budget['remaining_seconds'] = total_limit - budget['charged_seconds']
            atomic(budget_path, budget)
            atomic(root / 'terminal.json', result)
            atomic(root / 'source_after.json', git_state(args.source_sha))
            if result['classification'] != 'COMPLETED':
                raise SystemExit(1)
            return result
        except BaseException as exc:
            if entry.get('status') == 'RESERVED':
                entry.update(status='FAILED', exception_type=type(exc).__name__,
                             exception_message=str(exc))
            raise
        finally:
            if entry.get('actual_seconds') is None:
                interval = clock.update(clock_sample())
                charge = float(interval['budget_seconds'])
                entry['clock_interval'] = interval
                entry['actual_seconds'] = charge
                entry['conservative_seconds'] = charge
                budget['charged_seconds'] = _macro_charged_seconds(budget) + charge
                budget['remaining_seconds'] = total_limit - budget['charged_seconds']
            atomic(budget_path, budget)
            if result is not None and result.get('descendants_cleared'):
                active_lock.unlink()


def launch_macro_v10_workflow(specification, budget_path, inventory_path):
    """Build the independent, supervised V10 M1 entry for ``run_case``."""
    try:
        source_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f'cannot determine V10 M1 source SHA: {exc}') from exc
    base = Path('benchmarks/artifacts/task39extra/v10_m1') / source_sha
    root = base / 'm1'
    if root.exists():
        index = 2
        while (base / f'm1_retry_{index:02d}').exists():
            index += 1
        root = base / f'm1_retry_{index:02d}'
    args = argparse.Namespace(
        input=Path(specification.source_path), inventory=Path(inventory_path),
        output=root, budget=Path(budget_path), source_sha=source_sha, target='lo',
        macro_v10_controls=True, macro_v11_controls=False, bounded_j1_controls=False,
        bounded_j1_route='ENTITY16', p4_failure_diagnostic=False,
        projected_p4_component=False, bubble_local_tensor=False,
        bubble_enriched_component=False, bubble_particular_diagnostic=False,
        bubble_amplification_diagnostic=False, high_trace_component=False,
        cached_trace_component=False, owner_route_trace_component=False,
        cell_joint_trace_component=False, amplification_recording_retry=False,
        worker=False,
    )
    return _launch_macro_m1_controls(args)


def launch_macro_v11_workflow(specification, budget_path, inventory_path):
    """Build the independent, supervised V11 M1/N2 entry for ``run_case``."""
    try:
        source_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f'cannot determine V11 M1 source SHA: {exc}') from exc
    base = Path('benchmarks/artifacts/task39extra/v11_n0_n2') / source_sha
    root = base / 'm1'
    if root.exists():
        index = 2
        while (base / f'm1_retry_{index:02d}').exists():
            index += 1
        root = base / f'm1_retry_{index:02d}'
    args = argparse.Namespace(
        input=Path(specification.source_path), inventory=Path(inventory_path),
        output=root, budget=Path(budget_path), source_sha=source_sha, target='lo',
        macro_v10_controls=False, macro_v11_controls=True,
        bounded_j1_controls=False, bounded_j1_route='ENTITY16',
        p4_failure_diagnostic=False, projected_p4_component=False,
        bubble_local_tensor=False, bubble_enriched_component=False,
        bubble_particular_diagnostic=False, bubble_amplification_diagnostic=False,
        high_trace_component=False, cached_trace_component=False,
        owner_route_trace_component=False, cell_joint_trace_component=False,
        amplification_recording_retry=False, worker=False,
    )
    return _launch_macro_m1_controls(args)


def _launch_macro_n1_calibration(args):
    """Supervise the independent, 900-second V11 N1 calibration stage."""
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME, ClockBudget, clock_sample

    source = git_state(args.source_sha)
    budget_path = Path(args.budget).resolve()
    inventory_path = Path(args.inventory).resolve()
    input_path = Path(args.input).resolve()
    with budget_path.with_suffix('.lock').open('a') as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = _load_macro_ledger(budget_path, v11=True)
        charged = _macro_charged_seconds(budget)
        remaining = min(MACRO_V11_CALIBRATION_LIMIT_SECONDS,
                        MACRO_V11_TOTAL_LIMIT_SECONDS - charged)
        if remaining <= 0:
            raise RuntimeError('V11 N1 calibration budget exhausted')
        if any(item.get('kind') == 'physical_macro_dd4_v11_n1_calibration'
               for item in budget.get('attempts', [])):
            raise ValueError('V11 N1 calibration already attempted')
        root = Path(args.output)
        entry = {
            'kind': 'physical_macro_dd4_v11_n1_calibration',
            'budget_group': 'V11_N1_calibration',
            'source': args.source_sha,
            'root': str(root),
            'status': 'RESERVED',
            'reservation_seconds': remaining,
            'actual_seconds': None,
            'calibration_limit_seconds': MACRO_V11_CALIBRATION_LIMIT_SECONDS,
            'input': str(input_path),
            'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest(),
            'inventory': str(inventory_path),
            'inventory_sha256': hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        }
        budget.setdefault('attempts', []).append(entry)
        atomic(budget_path, budget)
        result = None
        clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
        try:
            root.mkdir(parents=True, exist_ok=False)
            cache_home = (root.parent / 'jit_cache').resolve()
            cache_home.mkdir(parents=True, exist_ok=True)
            atomic(root / 'launch_plan.json', {
                'source': source,
                'contract': selected_contract(args),
                'wall_seconds': remaining,
                'budget_before': budget,
                'calibration_limit_seconds': MACRO_V11_CALIBRATION_LIMIT_SECONDS,
                'jit_cache_home': str(cache_home),
                'jit_cache_initially_empty': not any(cache_home.iterdir()),
            })
            command = [
                sys.executable, '-m', 'src.runners.physical_recursive_entry',
                '--input', str(input_path), '--inventory', str(inventory_path),
                '--output', str(root), '--budget', str(budget_path),
                '--source-sha', args.source_sha, '--target', 'lo',
                '--macro-v11-calibration', '--jit-cache', str(cache_home), '--worker',
            ]
            result = supervise(
                command, root / 'watchdog', wall_seconds=remaining,
                phase_path=root / 'phase.json', hard_stop_immediate=True,
                timebase_guard=True, timebase_policy=CONSERVATIVE_REALTIME,
                stop_on_global_swap=True, source_state=source,
                worker_environment={'XDG_CACHE_HOME': str(cache_home)},
            )
            interval = result['workflow_clock_interval']
            charge = float(interval['budget_seconds'])
            entry.update(status=result['classification'], actual_seconds=charge,
                         conservative_seconds=charge,
                         descendants_cleared=result.get('descendants_cleared'),
                         clock_interval=interval)
            budget['charged_seconds'] = charged + charge
            budget['remaining_seconds'] = MACRO_V11_TOTAL_LIMIT_SECONDS - budget['charged_seconds']
            summary_path = root / 'run_summary.json'
            if summary_path.exists():
                entry['run_summary_sha256'] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
                entry['measurement_committed'] = (
                    json.loads(summary_path.read_text()).get('status') == 'COMPLETED'
                )
            atomic(budget_path, budget)
            atomic(root / 'terminal.json', result)
            atomic(root / 'source_after.json', git_state(args.source_sha))
            if result['classification'] != 'COMPLETED':
                raise SystemExit(1)
            return result
        except BaseException as exc:
            entry.update(status='FAILED', exception_type=type(exc).__name__,
                         exception_message=str(exc))
            raise
        finally:
            if entry.get('actual_seconds') is None:
                interval = clock.update(clock_sample())
                charge = float(interval['budget_seconds'])
                entry['clock_interval'] = interval
                entry['actual_seconds'] = charge
                entry['conservative_seconds'] = charge
                budget['charged_seconds'] = charged + charge
                budget['remaining_seconds'] = MACRO_V11_TOTAL_LIMIT_SECONDS - budget['charged_seconds']
            atomic(budget_path, budget)


def launch_macro_v11_calibration(specification, budget_path, inventory_path):
    """Launch the independent V11 N1 representative-block calibration."""
    try:
        source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f'cannot determine V11 N1 source SHA: {exc}') from exc
    base = Path('benchmarks/artifacts/task39extra/v11_n0_n2') / source_sha
    root = base / 'n1'
    if root.exists():
        index = 2
        while (base / f'n1_retry_{index:02d}').exists():
            index += 1
        root = base / f'n1_retry_{index:02d}'
    args = argparse.Namespace(
        input=Path(specification.source_path), inventory=Path(inventory_path),
        output=root, budget=Path(budget_path), source_sha=source_sha, target='lo',
        macro_v10_controls=False, macro_v11_controls=False,
        macro_v11_calibration=True, bounded_j1_controls=False,
        bounded_j1_route='ENTITY16', p4_failure_diagnostic=False,
        projected_p4_component=False, bubble_local_tensor=False,
        bubble_enriched_component=False, bubble_particular_diagnostic=False,
        bubble_amplification_diagnostic=False, high_trace_component=False,
        cached_trace_component=False, owner_route_trace_component=False,
        cell_joint_trace_component=False, amplification_recording_retry=False,
        worker=False,
    )
    return _launch_macro_n1_calibration(args)


def _launch_macro_v12_stage(args):
    """Supervise one explicit V12 stage with serial, hash-bound admission."""
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME, ClockBudget, clock_sample

    stage = getattr(args, 'macro_v12_stage', None)
    supplement = bool(getattr(args, 'macro_v12_supplement', False))
    stage_limits = (
        MACRO_V12_SUPPLEMENT_STAGE_LIMITS if supplement
        else MACRO_V12_STAGE_LIMITS
    )
    if stage not in stage_limits:
        raise ValueError(
            'V12 supplement requires O1/O2 stages'
            if supplement else 'V12 requires an explicit O0/O1/O2/O3/O4 stage'
        )
    source = git_state(args.source_sha)
    budget_path = Path(args.budget).resolve()
    inventory_path = Path(args.inventory).resolve()
    input_path = Path(args.input).resolve()
    if not inventory_path.is_file():
        raise ValueError('V12 requires the audited G0 inventory')
    if not input_path.is_file():
        raise ValueError(f'V12 input is missing: {input_path}')
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    inventory_sha256 = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    from src.io import load_and_resolve
    specification = load_and_resolve(input_path)
    input_payload = specification.as_jsonable()
    if input_payload['solver'].get('preconditioner') != 'physical_macro_dd4_v12':
        raise ValueError('V12 stage input must select physical_macro_dd4_v12')
    if input_payload['solver'].get('stage') != stage:
        raise ValueError('V12 stage input solver.stage does not match the admitted stage')
    physical_model_sha256 = str(input_payload['provenance']['physical_model_sha256'])
    if physical_model_sha256 not in {
        '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f',
        '7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec',
    }:
        raise ValueError('V12 stage input is outside the two frozen physical model identities')

    def summary_path(entry):
        root = Path(entry['root'])
        name = (
            'o0_summary.json' if entry['stage'] == 'O0_PRECHECK' else
            'm1_summary.json' if entry['stage'] == 'O1_FULL_PHYSICAL_CONTROLS' else
            'outer_summary.json' if entry['stage'].startswith(('O2_', 'O3_')) else
            'o4_summary.json'
        )
        return root / 'records' / name

    def stage_entry(budget, selected_stage):
        entries = [item for item in budget.get('attempts', []) if item.get('stage') == selected_stage]
        if len(entries) > 1:
            raise ValueError(f'V12 stage has duplicate ledger attempts: {selected_stage}')
        return entries[0] if entries else None

    def load_summary(budget, selected_stage):
        entry = stage_entry(budget, selected_stage)
        if entry is None:
            return None
        path = summary_path(entry)
        if not path.is_file():
            raise ValueError(f'V12 completed ledger entry has no stage summary: {path}')
        return json.loads(path.read_text())

    def require_completed(budget, selected_stage):
        entry = stage_entry(budget, selected_stage)
        if entry is None or entry.get('status') != 'COMPLETED':
            raise ValueError(f'V12 stage {selected_stage} must complete before {stage}')
        return entry, load_summary(budget, selected_stage)

    def has_terminal_record(entry):
        if entry is None:
            return False
        terminal_path = Path(entry.get('root', '')) / 'terminal.json'
        if not terminal_path.is_file():
            return False
        try:
            terminal = json.loads(terminal_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        return (
            isinstance(terminal.get('classification'), str)
            and bool(terminal.get('classification'))
            and isinstance(terminal.get('descendants_cleared'), bool)
        )

    def select_o2(budget):
        available = []
        for restart, selected_stage in ((32, 'O2_RESTART_PROBE_32'), (64, 'O2_RESTART_PROBE_64')):
            entry = stage_entry(budget, selected_stage)
            if entry is None:
                continue
            if entry.get('status') != 'COMPLETED':
                raise ValueError(f'V12 O2 entry is not completed: {selected_stage}')
            summary = load_summary(budget, selected_stage)
            candidate = summary.get('candidates', [{}])[0]
            available.append((restart, entry, summary, candidate))
        if not available:
            raise ValueError('V12 O2 selection requires at least one completed probe')

        def watchdog_valid(entry):
            terminal_path = Path(entry['root']) / 'terminal.json'
            if not terminal_path.is_file():
                return False
            terminal = json.loads(terminal_path.read_text())
            global_activity = terminal.get('global_swap_activity')
            global_delta = (
                global_activity.get('delta')
                if isinstance(global_activity, dict) else None
            )
            global_zero = (
                isinstance(global_delta, dict)
                and all(global_delta.get(key) == 0 for key in (
                    'pswpin_pages', 'pswpout_pages',
                ))
            )
            job_zero = terminal.get('job_swap_activity') == (
                'zero_supported_by_zero_global_activity'
            )
            required = (
                terminal.get('classification') == 'COMPLETED'
                and terminal.get('descendants_cleared') is True
                and not terminal.get('remaining_child_pids')
                and terminal.get('sampled_process_tree_swap_peak_bytes') == 0
                and global_zero
                and job_zero
                and isinstance(terminal.get('launch_envelope'), dict)
            )
            return bool(required)

        def node_resources_valid(candidate):
            records = candidate.get('node_records', [])
            return bool(records) and all(
                item.get('resource', {}).get('all_status_readable') is True
                and item.get('resource', {}).get('swap_bytes') == 0
                for item in records
            )

        def load_node_checkpoint(candidate, iteration):
            facts = [
                item for item in candidate.get('node_checkpoint_facts', [])
                if int(item.get('iteration', -1)) == int(iteration)
            ]
            if len(facts) != 1:
                return None, {
                    'iteration': int(iteration),
                    'status': 'CHECKPOINT_MISSING_OR_DUPLICATE',
                    'count': len(facts),
                }
            fact = facts[0]
            manifest_path = Path(str(fact.get('manifest_path', ''))).resolve()
            if not manifest_path.is_file():
                return None, {
                    'iteration': int(iteration), 'status': 'MANIFEST_MISSING',
                    'path': str(manifest_path),
                }
            actual_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            if actual_manifest_sha != fact.get('manifest_sha256'):
                return None, {
                    'iteration': int(iteration), 'status': 'MANIFEST_HASH_MISMATCH',
                    'path': str(manifest_path),
                }
            manifest = json.loads(manifest_path.read_text())
            if (
                manifest.get('schema') != 'fixed-memory-krylov.solution-checkpoint.v1'
                or manifest.get('solution_only') is not True
                or manifest.get('numeric_allgather') is not False
                or int(manifest.get('iteration', -1)) != int(iteration)
                or int(manifest.get('mpi_size', -1)) != 1
            ):
                return None, {
                    'iteration': int(iteration), 'status': 'MANIFEST_CONTRACT_MISMATCH',
                }
            expected_operator = {
                item.get('operator_identity_sha256')
                for item in candidate.get('node_records', [])
                if int(item.get('iteration', -1)) == int(iteration)
            }
            expected_physical = {
                item.get('physical_model_sha256')
                for item in candidate.get('node_records', [])
                if int(item.get('iteration', -1)) == int(iteration)
            }
            if (
                len(expected_operator) != 1
                or len(expected_physical) != 1
                or manifest.get('operator_identity_sha256') not in expected_operator
                or manifest.get('physical_model_sha256') not in expected_physical
            ):
                return None, {
                    'iteration': int(iteration), 'status': 'IDENTITY_MISMATCH',
                }
            ranks = manifest.get('ranks', [])
            if len(ranks) != 1 or int(ranks[0].get('rank', -1)) != 0:
                return None, {
                    'iteration': int(iteration), 'status': 'RANK_INVENTORY_MISMATCH',
                }
            descriptor = ranks[0].get('solution', {})
            relative_path = descriptor.get('relative_path')
            if not isinstance(relative_path, str):
                return None, {
                    'iteration': int(iteration), 'status': 'SOLUTION_DESCRIPTOR_MISSING',
                }
            solution_path = (manifest_path.parent / relative_path).resolve()
            if manifest_path.parent not in solution_path.parents or not solution_path.is_file():
                return None, {
                    'iteration': int(iteration), 'status': 'SOLUTION_PATH_INVALID',
                }
            if hashlib.sha256(solution_path.read_bytes()).hexdigest() != descriptor.get('sha256'):
                return None, {
                    'iteration': int(iteration), 'status': 'SOLUTION_HASH_MISMATCH',
                }
            values = np.asarray(np.load(solution_path, allow_pickle=False))
            if (
                values.dtype != np.dtype('complex128')
                or list(values.shape) != list(descriptor.get('shape', []))
                or not np.isfinite(values).all()
            ):
                return None, {
                    'iteration': int(iteration), 'status': 'SOLUTION_ARRAY_INVALID',
                }
            return values.copy(), {
                'iteration': int(iteration),
                'status': 'AVAILABLE',
                'manifest_path': str(manifest_path),
                'manifest_sha256': actual_manifest_sha,
                'solution_path': str(solution_path),
                'solution_sha256': descriptor.get('sha256'),
                'operator_identity_sha256': manifest.get('operator_identity_sha256'),
                'physical_model_sha256': manifest.get('physical_model_sha256'),
                'input_identity_sha256': manifest.get('input_identity_sha256'),
            }

        def first32_identity(candidate):
            records = {int(item.get('iteration', -1)): item for item in candidate.get('node_records', [])}
            required_iterations = (8, 16, 24, 32)
            if any(iteration not in records for iteration in required_iterations):
                return False, None
            identity_keys = (
                'operator_identity_sha256', 'physical_model_sha256',
            )
            identities = {
                tuple(records[iteration].get(key) for key in identity_keys)
                for iteration in required_iterations
            }
            residuals = [
                float(records[iteration].get('true_residual'))
                for iteration in required_iterations
            ]
            norms = [
                float(records[iteration].get('solution_norm'))
                for iteration in required_iterations
            ]
            finite = all(isfinite(value) for value in residuals + norms)
            checkpoints = {}
            checkpoint_facts = {}
            for iteration in required_iterations:
                values, facts = load_node_checkpoint(candidate, iteration)
                checkpoint_facts[str(iteration)] = facts
                if values is None:
                    return False, {
                        'identity': None,
                        'iterations': list(required_iterations),
                        'true_residuals': residuals,
                        'solution_norms': norms,
                        'checkpoint_facts': checkpoint_facts,
                    }
                checkpoints[iteration] = values
            if not finite or len(identities) != 1:
                return False, None
            identity = next(iter(identities))
            if any(value is None for value in identity):
                return False, None
            return True, {
                'identity': list(identity),
                'iterations': list(required_iterations),
                'true_residuals': residuals,
                'solution_norms': norms,
                'checkpoint_facts': checkpoint_facts,
            }

        def compare_first32(candidate32, candidate64):
            if candidate32 is None or candidate64 is None:
                return False, {'status': 'CANDIDATE_MISSING'}
            rows = []
            qualified = True
            for iteration in (8, 16, 24, 32):
                left, left_facts = load_node_checkpoint(candidate32, iteration)
                right, right_facts = load_node_checkpoint(candidate64, iteration)
                if left is None or right is None:
                    qualified = False
                    rows.append({
                        'iteration': iteration,
                        'status': 'CHECKPOINT_UNAVAILABLE',
                        'left': left_facts,
                        'right': right_facts,
                    })
                    continue
                if left.shape != right.shape:
                    qualified = False
                    rows.append({
                        'iteration': iteration,
                        'status': 'SOLUTION_SHAPE_MISMATCH',
                        'left_shape': list(left.shape),
                        'right_shape': list(right.shape),
                    })
                    continue
                denominator = max(float(np.linalg.norm(right)), np.finfo(float).tiny)
                solution_relative = float(np.linalg.norm(left - right) / denominator)
                solution_max_absolute = float(np.max(np.abs(left - right), initial=0.0))
                left_record = next(
                    item for item in candidate32.get('node_records', [])
                    if int(item.get('iteration', -1)) == iteration
                )
                right_record = next(
                    item for item in candidate64.get('node_records', [])
                    if int(item.get('iteration', -1)) == iteration
                )
                left_residual = float(left_record['true_residual'])
                right_residual = float(right_record['true_residual'])
                residual_absolute = abs(left_residual - right_residual)
                residual_relative = residual_absolute / max(
                    abs(right_residual), np.finfo(float).tiny,
                )
                row_pass = bool(
                    isfinite(solution_relative)
                    and isfinite(solution_max_absolute)
                    and isfinite(residual_relative)
                    and solution_relative <= 1.0e-8
                    and residual_relative <= 1.0e-8
                )
                qualified = qualified and row_pass
                rows.append({
                    'iteration': iteration,
                    'status': 'PASS' if row_pass else 'DIFFERENCE_OVER_LIMIT',
                    'solution_relative_difference': solution_relative,
                    'solution_max_absolute_difference': solution_max_absolute,
                    'true_residual_32': left_residual,
                    'true_residual_64': right_residual,
                    'true_residual_absolute_difference': residual_absolute,
                    'true_residual_relative_difference': residual_relative,
                    'limit': 1.0e-8,
                    'left_checkpoint': left_facts,
                    'right_checkpoint': right_facts,
                })
            return qualified, {
                'status': 'PASS' if qualified else 'FAIL',
                'iterations': [8, 16, 24, 32],
                'limit': 1.0e-8,
                'nodes': rows,
            }

        candidate_facts = {}
        for restart, entry, summary, candidate in available:
            node_ok, first32 = first32_identity(candidate)
            candidate_facts[str(restart)] = {
                'root': entry['root'],
                'summary_status': summary.get('status'),
                'iterations': int(candidate.get('iterations', 0)),
                'final_true_residual': candidate.get('final_true_residual'),
                'elapsed_seconds_wall': candidate.get('elapsed_seconds_wall'),
                'elapsed_seconds_conservative': candidate.get(
                    'elapsed_seconds_conservative',
                    candidate.get('elapsed_seconds_wall'),
                ),
                'reached48': int(candidate.get('iterations', 0)) >= 48,
                'reached64': int(candidate.get('iterations', 0)) >= 64,
                'official_result_pass': (summary.get('official_result') or {}).get('status') == 'OFFICIAL_RESULT_PASS',
                'node_resources_valid': node_resources_valid(candidate),
                'watchdog_resources_valid': watchdog_valid(entry),
                'first32_identity_pass': node_ok,
                'first32': first32,
            }
        candidate32 = next((item[3] for item in available if item[0] == 32), None)
        candidate64 = next((item[3] for item in available if item[0] == 64), None)
        fact32 = candidate_facts.get('32')
        fact64 = candidate_facts.get('64')
        reached48_32 = bool(fact32 and fact32['reached48'])
        reached48_64 = bool(fact64 and fact64['reached48'])
        reached64_32 = bool(fact32 and fact32['reached64'])
        reached64_64 = bool(fact64 and fact64['reached64'])
        both64 = reached64_32 and reached64_64
        first32_cross_ok = False
        first32_cross = {'status': 'NOT_AVAILABLE'}
        if candidate32 is not None and candidate64 is not None:
            first32_cross_ok, first32_cross = compare_first32(candidate32, candidate64)
        first32_incomplete = bool(
            candidate32 is None
            or candidate64 is None
            or int(candidate32.get('iterations', 0)) < 32
            or int(candidate64.get('iterations', 0)) < 32
        )
        first32_identity_invalid = bool(
            candidate32 is not None
            and candidate64 is not None
            and not first32_cross_ok
            and not first32_incomplete
        )
        residual_ratio = None
        time_ratio = None
        choose64 = False
        if both64:
            denominator = float(candidate32.get('final_true_residual', 0.0))
            residual_ratio = float(candidate64.get('final_true_residual', 0.0)) / max(denominator, 1.0e-300)
            time32 = float(candidate32.get(
                'elapsed_seconds_conservative',
                candidate32.get('elapsed_seconds_wall', 0.0),
            ))
            time64 = float(candidate64.get(
                'elapsed_seconds_conservative',
                candidate64.get('elapsed_seconds_wall', 0.0),
            ))
            time_ratio = time64 / max(
                time32, 1.0e-300,
            )
            choose64 = bool(
                fact32['node_resources_valid'] and fact64['node_resources_valid']
                and fact32['watchdog_resources_valid'] and fact64['watchdog_resources_valid']
                and fact32['first32_identity_pass'] and fact64['first32_identity_pass']
                and first32_cross_ok
                and residual_ratio <= 0.50 and time_ratio <= 1.25
            )
        physical_shortcut = len(available) == 1 and candidate_facts[str(available[0][0])]['official_result_pass']
        if first32_identity_invalid:
            selection_status = 'O2_SELECTION_IDENTITY_INVALID'
        elif not reached48_32 and not reached48_64 and not physical_shortcut:
            selection_status = 'WHOLE_PC_COST_NOT_VIABLE'
        else:
            selection_status = 'O2_SELECTION_COMPLETED'
        selected_restart = available[0][0] if len(available) == 1 else (64 if choose64 else 32)
        if len(available) == 1 and available[0][0] == 64 and not physical_shortcut:
            selected_restart = 64
        selection = {
            'schema': 'task39extra.review-v12.o2-selection.v1',
            'status': selection_status,
            'selected_restart': selected_restart,
            'selected_framework': budget.get('selected_framework'),
            'candidates': candidate_facts,
            'both_reached64': both64,
            'physical_probe_shortcut': physical_shortcut,
            'first32_cross_identity_pass': first32_cross_ok,
            'first32_cross_identity': first32_cross,
            'first32_cross_identity_status': (
                'PASS' if first32_cross_ok else
                'NOT_REQUIRED_PHYSICAL_SHORTCUT' if physical_shortcut else
                'INCOMPLETE_AT_COST_CAP' if first32_incomplete else
                'IDENTITY_INVALID'
            ),
            'cost_classification': 'INCOMPLETE_AT_COST_CAP' if not both64 else 'COMPLETE_AT_64',
            'endpoint_residual_ratio_64_over_32': residual_ratio,
            'endpoint_time_ratio_64_over_32': time_ratio,
            'endpoint_time_ratio_basis': 'elapsed_seconds_conservative; legacy wall fallback only for pre-supplement records',
            'thresholds': {'residual': 0.50, 'time': 1.25},
            'selection_rule': '64 only if both reach64, resource gates pass, and both ratios pass; otherwise32',
        }
        budget['o2_selection'] = selection
        atomic(budget_path, budget)
        return selection

    budget_path.parent.mkdir(parents=True, exist_ok=True)
    with budget_path.with_suffix('.lock').open('a') as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = _load_v12_ledger(budget_path, supplement=supplement)
        expected_profile = (
            'physical_macro_dd4_v12_supplement' if supplement
            else 'physical_macro_dd4_v12'
        )
        if budget.get('profile') is None:
            budget['profile'] = expected_profile
        elif budget['profile'] != expected_profile:
            raise ValueError('V12 ledger profile identity does not match this stage')
        identities = set(budget.get('physical_model_sha256s', []))
        identities.add(physical_model_sha256)
        if not identities.issubset({
            '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f',
            '7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec',
        }):
            raise ValueError('V12 stages must use only the two frozen physical model identities')
        budget['physical_model_sha256s'] = sorted(identities)
        previous_source = budget.get('source_sha')
        if previous_source is not None and str(previous_source) != str(args.source_sha):
            budget.setdefault('source_transitions', []).append({
                'from': str(previous_source), 'to': str(args.source_sha),
                'reason': 'recorded clean engineering source transition; prior evidence remains hash-bound',
            })
        budget['source_sha'] = args.source_sha
        if stage_entry(budget, stage) is not None:
            raise ValueError(f'V12 stage already attempted; no repeat measurement: {stage}')

        if supplement and stage == 'O1_FULL_PHYSICAL_CONTROLS':
            pass
        elif stage == 'O1_FULL_PHYSICAL_CONTROLS':
            _, summary0 = require_completed(budget, 'O0_PRECHECK')
            if summary0.get('status') != 'O0_PRECHECK_COMPLETED':
                raise ValueError('V12 O0 did not complete its precheck gate')
        elif stage == 'O2_RESTART_PROBE_32':
            _, summary1 = require_completed(budget, 'O1_FULL_PHYSICAL_CONTROLS')
            if summary1.get('status') != 'M1_CONTROLS_COMPLETED':
                raise ValueError('V12 O1 did not complete its physical controls gate')
            decision = summary1.get('framework_decision', {})
            selected_framework = decision.get('selected_framework')
            if selected_framework not in ('BAL_H', 'ONE_C'):
                raise ValueError('V12 O1 has no selected framework authority')
            budget['selected_framework'] = selected_framework
        elif stage == 'O2_RESTART_PROBE_64':
            require_completed(budget, 'O2_RESTART_PROBE_32')
            if budget.get('selected_framework') not in ('BAL_H', 'ONE_C'):
                raise ValueError('V12 O1 framework binding is missing from the ledger')
        elif stage == 'O3_ORIGINAL':
            entry32 = stage_entry(budget, 'O2_RESTART_PROBE_32')
            entry64 = stage_entry(budget, 'O2_RESTART_PROBE_64')
            if entry32 is None or entry64 is None:
                selection = budget.get('o2_selection') or select_o2(budget)
                if selection.get('physical_probe_shortcut'):
                    raise ValueError(
                        'single physically passing O2 probe skips O3_ORIGINAL; '
                        'continue directly to O3_NOTCH'
                    )
                raise ValueError('V12 O3_ORIGINAL requires both finite O2 probes')
            if not has_terminal_record(entry32) or not has_terminal_record(entry64):
                raise ValueError('V12 O3_ORIGINAL requires real terminal records for both O2 probes')
            selection = budget.get('o2_selection') or select_o2(budget)
            if selection.get('status') != 'O2_SELECTION_COMPLETED':
                raise ValueError('V12 O2 selection is not viable for O3')
            if int(getattr(args, 'macro_v12_outer_restart', 0)) != int(selection['selected_restart']):
                raise ValueError('V12 O3 outer_restart must equal the selected O2 restart')
        elif stage == 'O3_NOTCH':
            original_entry = stage_entry(budget, 'O3_ORIGINAL')
            if original_entry is not None:
                _, summary3 = require_completed(budget, 'O3_ORIGINAL')
                if summary3.get('status') != 'O3_COMPLETED':
                    raise ValueError('V12 notch requires a passing original O3 when original was run')
            selection = budget.get('o2_selection') or select_o2(budget)
            selected_facts = selection.get('candidates', {}).get(str(selection.get('selected_restart')), {})
            if (
                selection.get('status') != 'O2_SELECTION_COMPLETED'
                or (original_entry is None and not selected_facts.get('official_result_pass'))
                or int(getattr(args, 'macro_v12_outer_restart', 0)) != int(selection['selected_restart'])
            ):
                raise ValueError('V12 notch must reuse the selected O2 restart')
        elif stage == 'O4_FINALIZE':
            prior_stages = (
                'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS',
                'O2_RESTART_PROBE_32', 'O2_RESTART_PROBE_64',
                'O3_ORIGINAL', 'O3_NOTCH',
            )
            if not any(has_terminal_record(stage_entry(budget, item)) for item in prior_stages):
                raise ValueError(
                    'V12 O4 requires at least one real O0/O1/O2/O3 terminal record'
                )

        total_remaining = float(budget['total_limit_seconds']) - float(budget.get('charged_seconds', 0.0))
        if supplement and stage == 'O1_FULL_PHYSICAL_CONTROLS':
            stage_remaining = (
                float(budget['o1_workflow_limit_seconds'])
                - float(budget.get('o1_charged_seconds', 0.0))
            )
        elif stage in {'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS'}:
            stage_remaining = float(budget['o0_o1_limit_seconds']) - float(budget.get('o0_o1_charged_seconds', 0.0))
        else:
            stage_remaining = float(stage_limits[stage])
        wall_seconds = min(float(stage_limits[stage]), stage_remaining, total_remaining)
        if wall_seconds <= 0.0:
            raise RuntimeError(f'V12 budget exhausted before {stage}')

        resolved_framework = budget.get('selected_framework') if stage.startswith(('O2_', 'O3_')) else None
        requested_framework = getattr(args, 'macro_v12_framework', None)
        if requested_framework is not None and resolved_framework is not None and requested_framework != resolved_framework:
            raise ValueError('requested V12 framework differs from the O1 selected framework')
        framework = resolved_framework or requested_framework or 'BAL_H'
        requested_restart = int(getattr(args, 'macro_v12_outer_restart', 0))
        if stage in {'O2_RESTART_PROBE_32', 'O2_RESTART_PROBE_64'}:
            expected_restart = 32 if stage.endswith('_32') else 64
            if requested_restart != expected_restart:
                raise ValueError(f'{stage} requires outer_restart={expected_restart}')
        if stage.startswith('O3_') and requested_restart not in (32, 64):
            raise ValueError('V12 O3 requires the selected outer_restart=32 or 64')

        root = Path(args.output).resolve()
        if root.exists():
            raise ValueError(f'V12 stage output already exists; choose a fresh path: {root}')
        cache_home = (root / 'jit_cache').resolve()
        entry = {
            'kind': f"physical_macro_dd4_v12{'_supplement' if supplement else ''}_{stage.lower()}",
            'stage': stage,
            'budget_group': (
                'SUPPLEMENT_O1' if supplement and stage == 'O1_FULL_PHYSICAL_CONTROLS'
                else 'O0_O1_shared' if stage in {'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS'}
                else stage
            ),
            'source': args.source_sha,
            'root': str(root),
            'status': 'RESERVED',
            'reserved_seconds': wall_seconds,
            'input': str(input_path), 'input_sha256': input_sha256,
            'inventory': str(inventory_path), 'inventory_sha256': inventory_sha256,
            'stage_limit_seconds': float(stage_limits[stage]),
            'admitted_wall_seconds': wall_seconds,
            'supplement': supplement,
            'o1_compute_limit_seconds': (
                MACRO_V12_SUPPLEMENT_O1_COMPUTE_LIMIT_SECONDS if supplement else None
            ),
            'framework': framework if stage.startswith(('O2_', 'O3_')) else None,
            'outer_restart': requested_restart,
        }
        budget.setdefault('attempts', []).append(entry)
        atomic(budget_path, budget)
        result = None
        clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
        try:
            root.mkdir(parents=True, exist_ok=False)
            cache_home.mkdir(parents=True, exist_ok=False)
            atomic(root / 'launch_plan.json', {
                'source': source, 'contract': selected_contract(args), 'stage': stage,
                'supplement': supplement,
                'wall_seconds': wall_seconds, 'inventory': str(inventory_path),
                'input_sha256': input_sha256, 'inventory_sha256': inventory_sha256,
                'framework': framework if stage.startswith(('O2_', 'O3_')) else None,
                'outer_restart': requested_restart,
                'jit_cache_home': str(cache_home), 'no_retry': True,
            })
            command = [
                sys.executable, '-m', 'src.runners.physical_recursive_entry',
                '--input', str(input_path), '--inventory', str(inventory_path),
                '--output', str(root), '--budget', str(budget_path),
                '--source-sha', args.source_sha, '--target', 'lo', '--macro-v12',
                '--macro-v12-stage', stage,
                '--macro-v12-outer-restart', str(requested_restart),
                '--macro-v12-framework', framework,
                *(['--macro-v12-supplement'] if supplement else []),
                '--jit-cache', str(cache_home), '--worker',
            ]
            result = supervise(
                command, root / 'watchdog', wall_seconds=wall_seconds,
                phase_path=root / 'phase.json', hard_stop_immediate=True,
                timebase_guard=True, timebase_policy=CONSERVATIVE_REALTIME,
                stop_on_global_swap=True, source_state=source,
                worker_environment={'XDG_CACHE_HOME': str(cache_home)},
            )
            interval = result['workflow_clock_interval']
            entry.update(
                status=result['classification'], actual_seconds=float(interval['budget_seconds']),
                clock_interval=interval, descendants_cleared=result.get('descendants_cleared'),
            )
            budget['charged_seconds'] = float(budget.get('charged_seconds', 0.0)) + entry['actual_seconds']
            if supplement and stage == 'O1_FULL_PHYSICAL_CONTROLS':
                budget['o1_charged_seconds'] = float(budget.get('o1_charged_seconds', 0.0)) + entry['actual_seconds']
            elif stage in {'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS'}:
                budget['o0_o1_charged_seconds'] = float(budget.get('o0_o1_charged_seconds', 0.0)) + entry['actual_seconds']
            budget['remaining_seconds'] = float(budget['total_limit_seconds']) - budget['charged_seconds']
            atomic(budget_path, budget)
            atomic(root / 'terminal.json', result)
            atomic(root / 'source_after.json', git_state(args.source_sha))
            entry['terminal_classification'] = result.get('classification')
            if result['classification'] != 'COMPLETED':
                raise SystemExit(1)
            if stage == 'O2_RESTART_PROBE_64':
                select_o2(budget)
            return result
        except BaseException as exc:
            if entry.get('terminal_classification') is None:
                entry.update(
                    status='FAILED', exception_type=type(exc).__name__,
                    exception_message=str(exc),
                )
            else:
                entry.update(
                    launcher_exception_type=type(exc).__name__,
                    launcher_exception_message=str(exc),
                )
            raise
        finally:
            if entry.get('actual_seconds') is None:
                interval = clock.update(clock_sample())
                entry['clock_interval'] = interval
                entry['actual_seconds'] = float(interval['budget_seconds'])
                budget['charged_seconds'] = float(budget.get('charged_seconds', 0.0)) + entry['actual_seconds']
                if supplement and stage == 'O1_FULL_PHYSICAL_CONTROLS':
                    budget['o1_charged_seconds'] = float(budget.get('o1_charged_seconds', 0.0)) + entry['actual_seconds']
                elif stage in {'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS'}:
                    budget['o0_o1_charged_seconds'] = float(budget.get('o0_o1_charged_seconds', 0.0)) + entry['actual_seconds']
                budget['remaining_seconds'] = float(budget['total_limit_seconds']) - budget['charged_seconds']
            atomic(budget_path, budget)


def _launch_j1_controls(args):
    """Supervise one A-J1 or B finite-control worker under the shared ledger."""
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import ClockBudget, CONSERVATIVE_REALTIME, clock_sample

    route = getattr(args, 'bounded_j1_route', 'ENTITY16')
    projected = route == 'PROJECTED_SEQ2_16'
    recycled = route == 'ENTITY_GCROT8'
    v9 = route == 'ENTITY_GCROT8_NEW16'
    recycled = recycled or v9
    ledger_schema = (V9_K0_K1_BUDGET_SCHEMA if v9 else
                     V8_K0_K1_BUDGET_SCHEMA if recycled else J1_BUDGET_SCHEMA)
    batch_limit = (V9_K0_K1_LIMIT_SECONDS if v9 else
                   V8_K0_K1_LIMIT_SECONDS if recycled else J1_BATCH_LIMIT_SECONDS)
    control_limit = (B_PROJECTED_CONTROLS_LIMIT_SECONDS if projected
                     else V9_FINITE_CONTROLS_LIMIT_SECONDS if v9
                     else V8_FINITE_CONTROLS_LIMIT_SECONDS if recycled
                     else J1_CONTROLS_LIMIT_SECONDS)
    control_group = (B_PROJECTED_CONTROLS_GROUP if projected else
                    'V9_finite_controls' if v9 else
                    'V8_finite_controls' if recycled else 'J0_J1_controls')
    control_kind = (B_PROJECTED_CONTROLS_KIND if projected else
                    'bounded_entity_gcrot8_new16_controls' if v9 else
                    'bounded_entity_gcrot8_controls' if recycled else 'j1_controls')
    source=git_state(args.source_sha)
    budget_path=Path(args.budget).resolve()
    budget=json.loads(budget_path.read_text())
    if (budget.get('schema') != ledger_schema or
            budget.get('limit_seconds') != batch_limit):
        raise ValueError('selected controls require their exact bounded ledger')
    if recycled:
        expected_finite_limit = (V9_FINITE_CONTROLS_LIMIT_SECONDS if v9
                                 else V8_FINITE_CONTROLS_LIMIT_SECONDS)
        if budget.get('finite_control_limit_seconds') != expected_finite_limit:
            raise ValueError('recycled controls require the independent finite-control budget')
    elif budget.get('j0_j1_controls_limit_seconds') != J1_CONTROLS_LIMIT_SECONDS:
        raise ValueError('V7 controls require the shared V7 bounded ledger')
    if any(item.get('kind') == control_kind for item in budget.get('attempts', [])):
        raise ValueError('selected bounded controls already attempted; no repeat measurement')
    used=_j1_charge_seconds(budget)
    controls_used=_controls_charge_seconds(budget, control_group)
    remaining=min(control_limit-controls_used,
                  batch_limit-used)
    if remaining <= 0:
        raise RuntimeError('selected bounded controls budget exhausted')
    lock=budget_path.with_suffix('.lock')
    with lock.open('a') as lock_stream:
        fcntl.flock(lock_stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        budget=json.loads(budget_path.read_text())
        used=_j1_charge_seconds(budget)
        controls_used=_controls_charge_seconds(budget, control_group)
        remaining=min(control_limit-controls_used,
                      batch_limit-used)
        if remaining <= 0:
            raise RuntimeError('selected bounded controls budget exhausted')
        root=Path(args.output)
        result=None
        entry=dict(kind=control_kind,budget_group=control_group,
            route=getattr(args, 'bounded_j1_route', 'ENTITY16'), status='RESERVED',
            source=args.source_sha,root=str(root),reserved_seconds=remaining,
            elapsed_seconds=remaining,controls_limit_seconds=control_limit,
            ledger_schema=ledger_schema, nested_intervals_not_added=True)
        budget.setdefault('attempts',[]).append(entry)
        budget['charged_seconds']=_j1_charge_seconds(budget)
        budget['remaining_seconds']=batch_limit-budget['charged_seconds']
        atomic(budget_path,budget)
        clock=ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
        try:
            root.mkdir(parents=True,exist_ok=False)
            cache_home=(root/'jit_cache').resolve()
            cache_home.mkdir(exist_ok=False)
            atomic(root/'launch_plan.json',dict(schema=ledger_schema,source=source,
                contract=selected_contract(args),wall_seconds=remaining,
                control_group=control_group,controls_limit_seconds=control_limit,
                budget_before=budget,jit_cache_home=str(cache_home),
                jit_cache_initially_empty=not any(cache_home.iterdir()),
                nested_v6_ledger=('not used; independent V9 K0/K1 ledger' if v9 else
                                  'not used; independent V8 K0/K1 ledger'
                                  if recycled else 'not used; shared V7 bounded ledger')))
            command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:],'--worker']
            result=supervise(command,root/'watchdog',wall_seconds=remaining,
                phase_path=root/'phase.json',hard_stop_immediate=True,
                timebase_guard=True,timebase_policy=CONSERVATIVE_REALTIME,
                stop_on_global_swap=True,source_state=source,
                worker_environment={'XDG_CACHE_HOME':str(cache_home)})
            entry.update(status=result['classification'])
            atomic(root/'terminal.json',result)
            atomic(root/'source_after.json',git_state(args.source_sha))
            if result['classification']!='COMPLETED':raise SystemExit(1)
            return result
        except BaseException as exc:
            entry.update(status='FAILED',exception_type=type(exc).__name__,
                         exception_message=str(exc))
            raise
        finally:
            try:
                interval=clock.update(clock_sample())
                entry['clock_interval']=interval
                entry['elapsed_seconds']=float(interval['budget_seconds'])
            except BaseException as exc:
                entry.update(status='TIMEBASE_INCONSISTENCY',
                             clock_error=f'{type(exc).__name__}: {exc}')
                if not entry.get('exception_type'):
                    raise
            finally:
                budget['charged_seconds']=_j1_charge_seconds(budget)
                budget['remaining_seconds']=batch_limit-budget['charged_seconds']
                if recycled:
                    prefix = 'v9' if v9 else 'v8'
                    budget[f'{prefix}_k0_k1_charged_seconds'] = budget['charged_seconds']
                    budget[f'{prefix}_k0_k1_remaining_seconds'] = (
                        batch_limit-budget['charged_seconds'])
                    budget[f'{prefix}_finite_controls_charged_seconds'] = _controls_charge_seconds(
                        budget, control_group)
                    budget[f'{prefix}_finite_controls_remaining_seconds'] = (
                        control_limit-budget[f'{prefix}_finite_controls_charged_seconds'])
                else:
                    budget['j0_j1_controls_charged_seconds']=_j1_controls_charge_seconds(budget)
                    budget['j0_j1_controls_remaining_seconds']=(
                        J1_CONTROLS_LIMIT_SECONDS-budget['j0_j1_controls_charged_seconds'])
                if projected:
                    budget['b_projected_controls_charged_seconds']=_controls_charge_seconds(
                        budget, B_PROJECTED_CONTROLS_GROUP)
                    budget['b_projected_controls_remaining_seconds']=(
                        B_PROJECTED_CONTROLS_LIMIT_SECONDS-
                        budget['b_projected_controls_charged_seconds'])
                atomic(budget_path,budget)
        if result is not None and result.get('descendants_cleared'):
            # The lock is the shared ledger lock; fcntl releases it on exit.
            pass


def main():
    args=build_parser().parse_args()
    if args.worker:return worker(args)
    if getattr(args, 'p4_direction_diagnosis', False):
        return launch_p4_direction_diagnosis(args)
    if getattr(args, 'macro_v12', False):
        return _launch_macro_v12_stage(args)
    if getattr(args, 'macro_v11_calibration', False):
        return _launch_macro_n1_calibration(args)
    if getattr(args, 'macro_v11_controls', False) or getattr(args, 'macro_v10_controls', False):
        return _launch_macro_m1_controls(args)
    if args.bounded_j1_controls:
        return _launch_j1_controls(args)
    source=git_state(args.source_sha)
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME
    budget_path=Path(args.budget);budget=json.loads(budget_path.read_text())
    diagnostic=args.p4_failure_diagnostic;projected=args.projected_p4_component;bubble=args.bubble_local_tensor;enriched=args.bubble_enriched_component;particular=args.bubble_particular_diagnostic
    if diagnostic and Path(args.output).parts[-3:]!=('v6_p4_failure_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('diagnostic requires fresh v6_p4_failure_diagnostic/source/a2r160_g1 root')
    if diagnostic and budget.get('p4_failure_diagnostic_attempts'):
        raise ValueError('unique p4 failure diagnostic already attempted')
    if projected and Path(args.output).parts[-3:]!=('v6_projected_p4_component',args.source_sha,'a2r160_g1'):
        raise ValueError('projected component requires fresh source/a2r160_g1 root')
    if projected and budget.get('projected_p4_component_attempts'):
        raise ValueError('unique projected p4 component already attempted')
    if bubble and Path(args.output).parts[-3:]!=('v6_bubble_local_tensor',args.source_sha,'air_fixed'):
        raise ValueError('bubble local tensor requires fresh source/air_fixed root')
    if bubble and budget.get('bubble_local_tensor_attempts'):
        raise ValueError('unique bubble local tensor already attempted')
    if enriched and Path(args.output).parts[-3:]!=('v6_bubble_enriched_component',args.source_sha,'a2r160_g1'):
        raise ValueError('bubble enriched component requires fresh source/a2r160_g1 root')
    if enriched and budget.get('bubble_enriched_component_attempts'):
        raise ValueError('unique bubble enriched component already attempted')
    if particular and Path(args.output).parts[-3:]!=('v6_bubble_particular_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('particular diagnostic requires fresh source/a2r160_g1 root')
    if particular and budget.get('bubble_particular_diagnostic_attempts'):
        raise ValueError('unique particular diagnostic already attempted')
    amplification=args.bubble_amplification_diagnostic
    joint_trace=args.cell_joint_trace_component
    owner_trace=args.owner_route_trace_component or joint_trace
    cached_trace=args.cached_trace_component;trace=args.high_trace_component or cached_trace or owner_trace
    if trace and Path(args.output).parts[-3:]!=('v6_cell_joint_trace_component' if joint_trace else 'v6_owner_route_trace_component' if owner_trace else 'v6_cached_trace_component' if cached_trace else 'v6_high_trace_component',args.source_sha,'a2r160_g1'):
        raise ValueError('trace component requires fresh source/a2r160_g1 root')
    if trace and budget.get('cell_joint_trace_component_attempts' if joint_trace else 'owner_route_trace_component_attempts' if owner_trace else 'cached_trace_component_attempts' if cached_trace else 'high_trace_component_attempts'):
        raise ValueError('unique high trace component already attempted')
    if amplification and Path(args.output).parts[-3:]!=('v6_bubble_amplification_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('amplification requires fresh source/a2r160_g1 root')
    retry=amplification_recording_retry(args,budget)
    remaining=min(selected_contract(args)['workflow_seconds'],budget['batch_remaining']) if diagnostic or projected or bubble or enriched or particular or amplification or trace else min(budget['G0_G1_remaining'],budget['batch_remaining'])
    if remaining<=0:raise RuntimeError('G1 compute budget exhausted')
    lock=budget_path.parent/('cell_joint_trace_active.lock' if joint_trace else 'owner_route_trace_active.lock' if owner_trace else 'cached_trace_active.lock' if cached_trace else 'high_trace_active.lock' if trace else 'bubble_amplification_active.lock' if amplification else 'bubble_particular_active.lock' if particular else 'bubble_enriched_active.lock' if enriched else 'bubble_local_active.lock' if bubble else 'projected_p4_active.lock' if projected else 'p4_failure_active.lock' if diagnostic else 'g1_active.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    root=Path(args.output)
    result=None
    try:
        root.mkdir(parents=True,exist_ok=False)
        cache_home=(root/'jit_cache').resolve()
        cache_home.mkdir(exist_ok=False)
        atomic(root/'launch_plan.json',dict(source=source,contract=selected_contract(args),
            wall_seconds=remaining,budget_before=budget,recording_retry=retry,jit_cache_home=str(cache_home),
            jit_cache_initially_empty=not any(cache_home.iterdir())))
        command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:],'--worker']
        result=supervise(command,root/'watchdog',wall_seconds=remaining,phase_path=root/'phase.json',
            hard_stop_immediate=True,timebase_guard=True,timebase_policy=CONSERVATIVE_REALTIME,
            stop_on_global_swap=True,source_state=source,
            worker_environment={'XDG_CACHE_HOME':str(cache_home)})
        charge=result['workflow_clock_interval']['budget_seconds']
        budget.setdefault('cell_joint_trace_component_attempts' if joint_trace else 'owner_route_trace_component_attempts' if owner_trace else 'cached_trace_component_attempts' if cached_trace else 'high_trace_component_attempts' if trace else 'bubble_amplification_diagnostic_attempts' if amplification else 'bubble_particular_diagnostic_attempts' if particular else 'bubble_enriched_component_attempts' if enriched else 'bubble_local_tensor_attempts' if bubble else 'projected_p4_component_attempts' if projected else 'p4_failure_diagnostic_attempts' if diagnostic else 'g1_component_attempts',[]).append(dict(root=str(root),target=args.target,
            source=args.source_sha,classification=result['classification'],conservative_seconds=charge))
        for key in (('batch_remaining',) if diagnostic or projected or bubble or enriched or particular or amplification or trace else ('G0_G1_remaining','batch_remaining')):budget[key]-=charge
        budget['charged_including_reserve']+=charge
        atomic(budget_path,budget)
        atomic(root/'terminal.json',result)
        if diagnostic or projected or bubble or enriched or particular or amplification or trace:
            atomic(root/'source_after.json',git_state(args.source_sha))
        if result['classification']!='COMPLETED':raise SystemExit(1)
    finally:
        # An uncertain launch keeps the lock for review instead of enabling duplicate work.
        if result is not None and result.get('descendants_cleared'):lock.unlink()


if __name__=='__main__':main()
