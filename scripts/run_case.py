"""Thin public Task38 input entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from src.io import dry_run_payload, load_and_resolve  # noqa: E402
from src.io.input_loader import InputError  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Task38 .dat input; method and MPI come from the file."
    )
    parser.add_argument("input_path", type=Path, help="one Task38 .dat input")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--setup-only", action="store_true")
    mode.add_argument('--physical-pc-profile', type=Path, metavar='CHECKPOINT_DIRECTORY')
    parser.add_argument('--profile-budget-ledger', '--batch-budget-ledger', dest='profile_budget_ledger', type=Path)
    parser.add_argument('--profile-variant', choices=('R0', 'a2r_equivalent_fast_v1', 'a2r_packed_equivalent_v2'), default='R0')
    parser.add_argument('--profile-r0-reference', type=Path)
    parser.add_argument('--profile-recovery-from', '--profile-cache-recovery-from',
                        dest='profile_recovery_from', type=Path, metavar='FAILED_R0_DIRECTORY')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if any(marker in args.input_path.read_bytes() for marker in (b'[task042_v51]',b'[task042_v52]',b'[task042_v53]',b'[task042_v54]',b'[task042_v55]',b'[task042_v56]',b'[task042_v57]',b'[task042_v58]',b'[task042_v59]',b'[task042_v60]',b'[task042_v61]',b'[task042_v62]',b'[task042_v63]',b'[task042_v64]',b'[task042_v65]')):
            if b'[task042_v65]' in args.input_path.read_bytes():
                from src.io.independent_tetra_reference import load_tetra_reference
                from src.solvers import p6_completion_scope
                specification = load_tetra_reference(args.input_path,scope_module=p6_completion_scope)
            elif b'[task042_v64]' in args.input_path.read_bytes():
                from src.io.independent_tetra_reference import load_tetra_reference
                from src.solvers import local_h_pilot_scope
                specification = load_tetra_reference(args.input_path,scope_module=local_h_pilot_scope)
            elif b'[task042_v63]' in args.input_path.read_bytes():
                from src.io.independent_tetra_reference import load_tetra_reference
                from src.solvers import fine_tetra_scope
                specification = load_tetra_reference(args.input_path,scope_module=fine_tetra_scope)
            elif b'[task042_v62]' in args.input_path.read_bytes():
                from src.io.independent_tetra_reference import load_tetra_reference
                specification = load_tetra_reference(args.input_path)
            elif b'[task042_v61]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import face_trace_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v60]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import local_subcell_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v59]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import trace_interior_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v58]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import phase_deployment_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v57]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import common_weak_phase_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v56]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import phase_saved_closure_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v55]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import phase_spatial_resolution_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v54]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import phase_p_order_dtn_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v53]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                from src.solvers import phase_hp_completion_scope as scope
                specification = load_phase_notch_hp(args.input_path,scope=scope)
            elif b'[task042_v52]' in args.input_path.read_bytes():
                from src.io.phase_notch_hp import load_phase_notch_hp
                specification = load_phase_notch_hp(args.input_path)
            else:
                from src.io.phase_explicit_accuracy import load_phase_explicit_accuracy
                specification = load_phase_explicit_accuracy(args.input_path)
            if args.setup_only or args.physical_pc_profile or args.profile_budget_ledger:
                raise InputError('V51 requires one explicit stage')
            if args.validate_only or args.dry_run:
                print(json.dumps(dict(status='valid', stage=specification.derived['stage'],
                    input_sha256=specification.input_sha256, physical_sha256=specification.physical_model_sha256)))
                return 0
            from src.runners.port_preparation import launch
            result = launch(specification)
            print(json.dumps(dict(directory=result['directory'], classification=result['classification'],
                seconds=result['elapsed_seconds'], exit_code=result['leader_exit_code'])))
            return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 3
        if b'[task042_v50]' in args.input_path.read_bytes():
            from src.io.scattering_accuracy import load_scattering_accuracy
            specification = load_scattering_accuracy(args.input_path)
            if args.setup_only or args.physical_pc_profile or args.profile_budget_ledger:
                raise InputError('V50 requires one explicit stage')
            if args.validate_only or args.dry_run:
                print(json.dumps(dict(status='valid', stage=specification.derived['stage'],
                    input_sha256=specification.input_sha256, physical_sha256=specification.physical_model_sha256)))
                return 0
            from src.runners.port_preparation import launch
            result = launch(specification)
            print(json.dumps(dict(directory=result['directory'], classification=result['classification'],
                seconds=result['elapsed_seconds'], exit_code=result['leader_exit_code'])))
            return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 3
        if b'[task042_v49]' in args.input_path.read_bytes():
            from src.io.scattering_anchor import load_scattering_anchor
            specification = load_scattering_anchor(args.input_path)
            if args.setup_only or args.physical_pc_profile or args.profile_budget_ledger:
                raise InputError('V49 requires one explicit stage')
            if args.validate_only or args.dry_run:
                print(json.dumps(dict(status='valid', stage=specification.derived['stage'],
                    input_sha256=specification.input_sha256, physical_sha256=specification.physical_model_sha256)))
                return 0
            from src.runners.port_preparation import launch
            result = launch(specification)
            print(json.dumps(dict(directory=result['directory'], classification=result['classification'],
                seconds=result['elapsed_seconds'], exit_code=result['leader_exit_code'])))
            return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 3
        # Independent preparation opt-in: no historical live window and no
        # full-target solver dispatch. Ordinary inputs keep the existing path.
        if any(marker in args.input_path.read_bytes() for marker in (b'[task042_v36]', b'[task042_v37]', b'[task042_v38]', b'[task042_v39]', b'[task042_v40]', b'[task042_v41]', b'[task042_v42]', b'[task042_v43]', b'[task042_v44]', b'[task042_v45]', b'[task042_v47]')):
            from src.io.port_preparation import load_preparation
            preparation = load_preparation(args.input_path)
            if args.setup_only or args.physical_pc_profile or args.profile_budget_ledger:
                raise InputError('V36 accepts only one explicit preparation stage')
            if args.validate_only or args.dry_run:
                print(json.dumps(dict(status='valid', stage=preparation.derived['stage'],
                    input_sha256=preparation.input_sha256, target_solve=False)))
                return 0
            from src.runners.port_preparation import launch as launch_preparation
            result = launch_preparation(preparation)
            print(json.dumps(dict(directory=result['directory'], classification=result['classification'],
                seconds=result['elapsed_seconds'], exit_code=result['leader_exit_code'])))
            return 0 if result['classification']=='COMPLETED' and result['leader_exit_code']==0 else 3
        if args.profile_recovery_from is not None and args.physical_pc_profile is None:
            raise InputError('--profile-recovery-from requires --physical-pc-profile')
        if args.setup_only and (
            args.profile_budget_ledger is not None
            or args.profile_variant != 'R0'
            or args.profile_r0_reference is not None
            or args.profile_recovery_from is not None
        ):
            raise InputError('--setup-only cannot be combined with diagnostic profile options')
        if args.physical_pc_profile is None and (args.profile_variant != 'R0' or args.profile_r0_reference is not None):
            raise InputError('fast profile options require --physical-pc-profile')
        from src.io.neural_fe_interface import load_interface
        from src.io.neural_fe_continuation import load_continuation
        from src.io.neural_fe_calibration import load_calibration
        from src.io.frozen_fe_diagnostic import load_diagnostic
        from src.io.autonomous_neural_head import load_autonomous
        from src.io.stable_head_varpro import load_stable_head
        from src.io.actual_loss_block_descent import load_actual_loss
        from src.io.tangent_head_compensation import load_tangent_head
        from src.io.orthonormal_trace_reprofile import load_orthonormal_trace
        from src.io.local_trace_representation import load_local_trace
        from src.io.resumable_trace_campaign import load_resumable_trace
        from src.io.exact_action_recycling import load_recycling
        from src.io.local_block_pair import load_local_block
        from src.io.block_direction_diagnostic import load_block_diagnostic
        from src.io.return_block_continuation import load_return_diagnostic as load_return_continuation
        from src.io.full_input_online import load_online
        from src.io.full_input_block_v34 import load_return_diagnostic as load_full_input_v34
        from src.io.full_input_block_v33 import load_return_diagnostic as load_full_v33
        from src.io.return_block_v32 import load_return_diagnostic as load_return_v32
        from src.io.return_block_v31 import load_return_diagnostic as load_return_v31
        from src.io.return_block_diagnostic import load_return_diagnostic
        from src.io.joint_block_diagnostic import load_joint_diagnostic
        from src.io.p1_image_minres import load_image_minres
        from src.io.p1_trace_galerkin import load_p1_trace
        from src.io.fixed_p3_ilu0 import load_fixed_ilu0
        from src.io.post_lsqr_polish import load_post_lsqr
        from src.io.gmres_residual_completion import load_residual_completion
        from src.io.augmented_trace_lsqr import load_augmented_trace
        specification = load_online(args.input_path) or load_full_input_v34(args.input_path) or load_full_v33(args.input_path) or load_return_v32(args.input_path) or load_return_v31(args.input_path) or load_return_continuation(args.input_path) or load_return_diagnostic(args.input_path) or load_joint_diagnostic(args.input_path) or load_block_diagnostic(args.input_path) or load_local_block(args.input_path) or load_image_minres(args.input_path) or load_p1_trace(args.input_path) or load_recycling(args.input_path) or load_fixed_ilu0(args.input_path) or load_post_lsqr(args.input_path) or load_residual_completion(args.input_path) or load_resumable_trace(args.input_path) or load_augmented_trace(args.input_path) or load_local_trace(args.input_path) or load_orthonormal_trace(args.input_path) or load_tangent_head(args.input_path) or load_actual_loss(args.input_path) or load_stable_head(args.input_path) or load_autonomous(args.input_path) or load_diagnostic(args.input_path) or load_calibration(args.input_path) or load_continuation(args.input_path) or load_interface(args.input_path)
        if specification is None:
            specification = load_and_resolve(args.input_path)
        from src.io.task042_profile import TASK042_PROFILES
        if specification.solver.get('preconditioner') in TASK042_PROFILES:
            if args.validate_only or args.dry_run:
                print(json.dumps({'status': 'valid', 'profile': specification.solver['preconditioner'],
                                  'stage': TASK042_PROFILES[specification.solver['preconditioner']],
                                  'input_sha256': specification.input_sha256,
                                  'physical_model_sha256': specification.physical_model_sha256}))
                return 0
            if args.setup_only or args.physical_pc_profile or args.profile_budget_ledger:
                raise InputError('Task042 accepts one explicit stage dat without other campaign options')
            from src.runners.task042_shared import launch
            result = launch(specification)
            print(json.dumps(result, sort_keys=True))
            return 0 if result['classification'] == 'COMPLETED' and result['leader_exit_code'] == 0 else 3
        if args.setup_only:
            from src.io.native_capacity_profile import setup_only_5nm_identity_errors

            errors = setup_only_5nm_identity_errors(
                profile=str(specification.solver.get('preconditioner', '')),
                method=str(specification.method.get('kind', '')),
                input_sha256=specification.input_sha256,
                physical_model_sha256=specification.physical_model_sha256,
            )
            if errors:
                raise InputError('; '.join(errors))
            from src.runners.native_capacity import launch_native_capacity

            result = launch_native_capacity(specification, setup_only=True)
            print(json.dumps(result, sort_keys=True, separators=(',', ':')))
            return 0 if result['result_classification'] == 'setup_only' else 3
        if args.validate_only:
            payload = {
                "status": "valid",
                "model_id": specification.identity["model_id"],
                "run_id": specification.identity["run_id"],
                "method": specification.method["kind"],
                "direct_solver_profile": specification.solver.get("direct_solver_profile", "default"),
                "time_limit_mode": specification.execution.get("time_limit_mode", "bounded"),
                "timeout_seconds": specification.execution.get("timeout_seconds"),
            }
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            return 0
        if args.dry_run:
            print(
                json.dumps(
                    dry_run_payload(specification),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        from src.runners.task038_launcher import launch_specification

        if args.physical_pc_profile:
            if args.profile_budget_ledger is None:
                raise InputError('--physical-pc-profile requires --profile-budget-ledger')
            from src.runners.physical_profile_budget import launch_profile
            result = launch_profile(specification, args.physical_pc_profile, args.profile_budget_ledger,
                                    recovery_from=args.profile_recovery_from,
                                    **(dict(variant=args.profile_variant, r0_reference=args.profile_r0_reference)
                                       if args.profile_variant != 'R0' or args.profile_r0_reference is not None else {}))
        else:
            if (specification.method["kind"] == "full3d_direct" and
                    specification.solver.get("direct_solver_profile") == "native_matched_reference"):
                from src.runners.fine_reference_preflight import launch_native_matched_reference
                result = launch_native_matched_reference(specification)
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return 0 if result["result_classification"] == "worker_exit0" else 3
            from src.io.native_capacity_profile import NATIVE_PROFILES
            if specification.solver.get("preconditioner") in NATIVE_PROFILES:
                from src.runners.native_capacity import launch_native_capacity
                result = launch_native_capacity(specification)
                print(json.dumps(result, sort_keys=True))
                return 0 if result["result_classification"] == "worker_exit0" else 3
            from src.io.physical_intermediate_profile import LIGHT_PROFILE, JOINT_PROFILE
            from src.io.physical_balanced_profile import BALANCED_PROFILES
            from src.io.physical_recursive_profile import RECURSIVE_PROFILES
            if specification.solver.get('preconditioner') in RECURSIVE_PROFILES:
                from src.runners.physical_recursive_budget import launch_recursive_workflow
                result = launch_recursive_workflow(specification, args.profile_budget_ledger)
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return 0 if result['result_classification'] == 'worker_exit0' else 3
            if specification.solver.get('preconditioner') in BALANCED_PROFILES:
                from src.runners.physical_balanced_budget import launch_balanced_workflow
                result = launch_balanced_workflow(specification, args.profile_budget_ledger)
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return 0 if result['result_classification'] == 'worker_exit0' else 3
            if specification.solver.get('preconditioner') in (LIGHT_PROFILE, JOINT_PROFILE):
                from src.runners.physical_profile_budget import launch_light_workflow
                result = launch_light_workflow(specification, args.profile_budget_ledger)
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return 0 if result['result_classification'] == 'worker_exit0' else 3
            if args.profile_budget_ledger is not None:
                raise InputError('--profile-budget-ledger requires --physical-pc-profile')
            result = launch_specification(specification)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["result_classification"] == "worker_exit0" else 3
    except InputError as exc:
        print(f"Task38 input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
