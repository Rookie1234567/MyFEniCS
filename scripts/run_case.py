"""Thin public Task38 input entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from src.io import dry_run_payload, load_and_resolve  # noqa: E402
from src.io.input_loader import InputError  # noqa: E402


def _git_command(*args: str) -> list[str]:
    """Use the canonical Codex worktree git directory when present."""
    git_dir = _REPOSITORY_ROOT / '.git-codex'
    if git_dir.is_dir():
        return [
            'git', '--git-dir', str(git_dir), '--work-tree',
            str(_REPOSITORY_ROOT), *args,
        ]
    return ['git', *args]


def _source_sha() -> str:
    return subprocess.check_output(
        _git_command('rev-parse', 'HEAD'),
        cwd=_REPOSITORY_ROOT,
        text=True,
    ).strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Task38 .dat input; method and MPI come from the file."
    )
    parser.add_argument("input_path", type=Path, help="one Task38 .dat input")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument('--physical-pc-profile', type=Path, metavar='CHECKPOINT_DIRECTORY')
    mode.add_argument('--macro-v10-controls', action='store_true')
    mode.add_argument('--macro-v11-controls', action='store_true')
    mode.add_argument('--macro-v11-calibration', action='store_true')
    mode.add_argument('--macro-v12', action='store_true')
    mode.add_argument('--p4-direction-diagnosis', action='store_true')
    mode.add_argument(
        '--recover-v15-q0-eio-once', action='store_true',
        help='apply the one reviewed administrative V15 Q0 recovery; does not run PDE',
    )
    parser.add_argument(
        '--macro-v12-supplement', action='store_true',
        help='use the independent bounded V12 supplement ledger',
    )
    parser.add_argument(
        '--macro-v12-stage',
        choices=(
            'O0_PRECHECK', 'O1_FULL_PHYSICAL_CONTROLS',
            'O2_RESTART_PROBE_32', 'O2_RESTART_PROBE_64',
            'O3_ORIGINAL', 'O3_NOTCH', 'O4_FINALIZE',
        ),
    )
    parser.add_argument('--macro-v12-outer-restart', type=int, choices=(0, 32, 64))
    parser.add_argument('--macro-v12-framework', choices=('BAL_H', 'ONE_C'))
    parser.add_argument('--macro-v12-output', type=Path)
    parser.add_argument('--p4-direction-output', type=Path)
    parser.add_argument(
        '--p4-direction-reuse-root', type=Path,
        help='hash-bound prior P4 diagnosis directory whose qualified packets may be reused',
    )
    parser.add_argument(
        '--macro-v12-inventory', type=Path,
        default=Path('benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json'),
    )
    parser.add_argument('--profile-budget-ledger', '--batch-budget-ledger', dest='profile_budget_ledger', type=Path)
    parser.add_argument(
        '--task40-reference-from', type=Path, metavar='G0_RUN_DIRECTORY',
        help='compare the Task40 direct reference with the frozen G0 iterative run',
    )
    parser.add_argument('--macro-v10-inventory', type=Path,
                        default=Path('benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json'))
    parser.add_argument('--profile-variant', choices=('R0', 'a2r_equivalent_fast_v1', 'a2r_packed_equivalent_v2'), default='R0')
    parser.add_argument('--profile-r0-reference', type=Path)
    parser.add_argument('--profile-recovery-from', '--profile-cache-recovery-from',
                        dest='profile_recovery_from', type=Path, metavar='FAILED_R0_DIRECTORY')
    parser.add_argument(
        '--v14-time-policy',
        choices=('enforce', 'observe_only'),
        default='enforce',
        help='reviewed V14/V16/V17/V18 timing policy; observe_only keeps finite timing evidence without deadline termination',
    )
    parser.add_argument(
        '--task40-v10-campaign-window', type=Path, metavar='CAMPAIGN_WINDOW_JSON',
        help='required existing fixed 24-hour campaign window for reviewed Task40 V10/V11/V13 p6 cases',
    )
    parser.add_argument(
        '--task40-v10-postprocess-from', type=Path, metavar='FAILED_RUN_DIRECTORY',
        help='recover the frozen V10/V15 B0 outputs from its saved full field without rerunning the solve',
    )
    parser.add_argument(
        '--v24-p4-prefix-target',
        type=int,
        choices=(3,),
        help='V24-only bounded diagnostic stop after total logical p4 sequence 3',
    )
    parser.add_argument(
        '--r0-evidence', type=Path, metavar='ACCEPTED_R0_JSON',
        help='fixed accepted R0 record required by --recover-v15-q0-eio-once',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.task40_v10_postprocess_from is not None and (
            args.validate_only
            or args.dry_run
            or args.physical_pc_profile is not None
            or args.macro_v10_controls
            or args.macro_v11_controls
            or args.macro_v11_calibration
            or args.macro_v12
            or args.macro_v12_supplement
            or args.macro_v12_stage is not None
            or args.macro_v12_outer_restart is not None
            or args.macro_v12_framework is not None
            or args.macro_v12_output is not None
            or args.p4_direction_diagnosis
            or args.p4_direction_output is not None
            or args.p4_direction_reuse_root is not None
            or args.recover_v15_q0_eio_once
            or args.task40_reference_from is not None
            or args.profile_budget_ledger is not None
            or args.profile_recovery_from is not None
            or args.profile_variant != 'R0'
            or args.profile_r0_reference is not None
            or args.v24_p4_prefix_target is not None
            or args.r0_evidence is not None
        ):
            raise InputError('--task40-v10-postprocess-from is a standalone supervised workflow')
        if args.r0_evidence is not None and not args.recover_v15_q0_eio_once:
            raise InputError('--r0-evidence requires --recover-v15-q0-eio-once')
        if args.recover_v15_q0_eio_once:
            if args.r0_evidence is None:
                raise InputError('--recover-v15-q0-eio-once requires --r0-evidence')
            from src.runners.task038_launcher import recover_v15_q0_eio_once
            result = recover_v15_q0_eio_once(
                _REPOSITORY_ROOT, r0_evidence=args.r0_evidence,
            )
            print(json.dumps(result, sort_keys=True, separators=(',', ':')))
            return 0
        if args.profile_recovery_from is not None and args.physical_pc_profile is None:
            raise InputError('--profile-recovery-from requires --physical-pc-profile')
        if args.physical_pc_profile is None and (args.profile_variant != 'R0' or args.profile_r0_reference is not None):
            raise InputError('fast profile options require --physical-pc-profile')
        specification = load_and_resolve(args.input_path)
        from src.geometry.task40_nonseparable_plan import (
            TASK40_B0_CONTROL_RUN_ID,
            TASK40_B0_P6_CANDIDATE_RUN_ID,
            TASK40_B0_P6_V13_RUN_ID,
            TASK40_B0_P6_V15_RUN_ID,
            TASK40_E1_V15_RUN_ID,
            TASK40_B0_P4_CONTROL_PROFILE,
            TASK40_GX560_V11_P6_RUN_ID,
            TASK40_GX560_V13_RUN_ID,
            TASK40_GX560_V15_RUN_ID,
            TASK40_GX560_V16_RUN_ID,
            TASK40_E1_V16_RUN_ID,
            TASK40_B0_P6_V17_RUN_ID,
            TASK40_B0_P6_V18_Y8_RUN_ID,
            TASK40_B0_P6_V19_Y8_RUN_ID,
            TASK40_GX560_V17_RUN_ID,
            TASK40_E1_V17_RUN_ID,
            TASK40_E1_V19_RUN_ID,
            TASK40_GX784_V11_P6_RUN_ID,
            TASK40_GX784_V13_RUN_ID,
            TASK40_Q_ASSEMBLY_LEGACY,
            TASK40_V13_REFERENCE_PC_STRATEGY,
            TASK40_V15_REFERENCE_PC_STRATEGY,
            TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
            TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
            TASK40_Q_ASSEMBLY_BOUNDED_V16,
            TASK40_Q_ASSEMBLY_ROW_TILE_V17,
            task40_q_assembly_strategy_is_allowed,
        )
        from src.io.physical_intermediate_profile import (
            TASK40_V10_P6_REFERENCE_PROFILE,
            TASK40_V11_P6_GX560_PROFILE,
            TASK40_V11_P6_GX784_PROFILE,
            TASK40_V15_P6_B0_PROFILE,
            TASK40_V15_P6_GX560_PROFILE,
            TASK40_V15_P6_E1_PROFILE,
            TASK40_V16_P6_GX560_PROFILE,
            TASK40_V16_P6_E1_PROFILE,
            TASK40_V17_P6_B0_PROFILE,
            TASK40_V18_P6_B0_Y8_PROFILE,
            TASK40_V17_P6_GX560_PROFILE,
            TASK40_V17_P6_E1_PROFILE,
        )

        v10_identity = (
            specification.identity.get('run_id') == TASK40_B0_CONTROL_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_B0_P4_CONTROL_PROFILE
        ) or (
            specification.identity.get('run_id') == TASK40_B0_P6_CANDIDATE_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_V10_P6_REFERENCE_PROFILE
        )
        v10_candidate_identity = (
            specification.identity.get('run_id') == TASK40_B0_P6_CANDIDATE_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_V10_P6_REFERENCE_PROFILE
        )
        v11_grid_identity = (
            specification.identity.get('run_id') == TASK40_GX560_V11_P6_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_V11_P6_GX560_PROFILE
        ) or (
            specification.identity.get('run_id') == TASK40_GX784_V11_P6_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_V11_P6_GX784_PROFILE
        )
        v13_case_identity = (
            specification.identity.get('run_id'),
            specification.solver.get('preconditioner'),
        ) in {
            (TASK40_B0_P6_V13_RUN_ID, TASK40_V10_P6_REFERENCE_PROFILE),
            (TASK40_GX560_V13_RUN_ID, TASK40_V11_P6_GX560_PROFILE),
            (TASK40_GX784_V13_RUN_ID, TASK40_V11_P6_GX784_PROFILE),
        }
        v13_campaign_identity = (
            v13_case_identity
            and specification.solver.get('task40_reference_pc_strategy')
            == TASK40_V13_REFERENCE_PC_STRATEGY
            and task40_q_assembly_strategy_is_allowed(
                str(specification.solver.get('task40_reference_pc_strategy')),
                str(
                    specification.solver.get(
                        'task40_q_assembly_strategy', TASK40_Q_ASSEMBLY_LEGACY
                    )
                ),
            )
        )
        v15_case_identity = (
            specification.identity.get('run_id'),
            specification.solver.get('preconditioner'),
        ) in {
            (TASK40_B0_P6_V15_RUN_ID, TASK40_V15_P6_B0_PROFILE),
            (TASK40_GX560_V15_RUN_ID, TASK40_V15_P6_GX560_PROFILE),
            (TASK40_E1_V15_RUN_ID, TASK40_V15_P6_E1_PROFILE),
        }
        v15_campaign_identity = (
            v15_case_identity
            and specification.solver.get('task40_reference_pc_strategy')
            == TASK40_V15_REFERENCE_PC_STRATEGY
            and task40_q_assembly_strategy_is_allowed(
                str(specification.solver.get('task40_reference_pc_strategy')),
                str(
                    specification.solver.get(
                        'task40_q_assembly_strategy', TASK40_Q_ASSEMBLY_LEGACY
                    )
                ),
            )
        )
        v16_case_identity = (
            specification.identity.get('run_id'),
            specification.solver.get('preconditioner'),
        ) in {
            (TASK40_GX560_V16_RUN_ID, TASK40_V16_P6_GX560_PROFILE),
            (TASK40_E1_V16_RUN_ID, TASK40_V16_P6_E1_PROFILE),
        }
        v16_campaign_identity = (
            v16_case_identity
            and specification.solver.get('task40_reference_pc_strategy')
            == TASK40_V15_REFERENCE_PC_STRATEGY
            and specification.solver.get('task40_q_assembly_strategy')
            == TASK40_Q_ASSEMBLY_BOUNDED_V16
            and task40_q_assembly_strategy_is_allowed(
                str(specification.solver.get('task40_reference_pc_strategy')),
                str(specification.solver.get('task40_q_assembly_strategy')),
            )
        )
        v17_case_identity = (
            specification.identity.get('run_id'),
            specification.solver.get('preconditioner'),
        ) in {
            (TASK40_B0_P6_V17_RUN_ID, TASK40_V17_P6_B0_PROFILE),
            (TASK40_GX560_V17_RUN_ID, TASK40_V17_P6_GX560_PROFILE),
            (TASK40_E1_V17_RUN_ID, TASK40_V17_P6_E1_PROFILE),
        }
        v17_campaign_identity = (
            v17_case_identity
            and specification.solver.get('task40_reference_pc_strategy')
            == TASK40_V15_REFERENCE_PC_STRATEGY
            and specification.solver.get('task40_q_assembly_strategy')
            == TASK40_Q_ASSEMBLY_ROW_TILE_V17
            and task40_q_assembly_strategy_is_allowed(
                str(specification.solver.get('task40_reference_pc_strategy')),
                str(specification.solver.get('task40_q_assembly_strategy')),
            )
        )
        v18_campaign_identity = (
            specification.identity.get('run_id') == TASK40_B0_P6_V18_Y8_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_V18_P6_B0_Y8_PROFILE
            and specification.solver.get('task40_reference_pc_strategy')
            == TASK40_V15_REFERENCE_PC_STRATEGY
            and specification.solver.get('task40_q_assembly_strategy')
            == TASK40_Q_ASSEMBLY_ROW_TILE_V17
            and task40_q_assembly_strategy_is_allowed(
                str(specification.solver.get('task40_reference_pc_strategy')),
                str(specification.solver.get('task40_q_assembly_strategy')),
            )
        )
        v19_case_identity = (
            specification.identity.get('run_id'),
            specification.solver.get('preconditioner'),
        ) in {
            (TASK40_E1_V19_RUN_ID, TASK40_V17_P6_E1_PROFILE),
            (TASK40_B0_P6_V19_Y8_RUN_ID, TASK40_V18_P6_B0_Y8_PROFILE),
        }
        v19_campaign_identity = (
            v19_case_identity
            and specification.solver.get('task40_factor_lifecycle_strategy')
            == TASK40_V19_FACTOR_LIFECYCLE_STRATEGY
            and specification.solver.get('task40_reference_pc_strategy')
            == TASK40_V15_REFERENCE_PC_STRATEGY
            and specification.solver.get('task40_q_assembly_strategy')
            == TASK40_Q_ASSEMBLY_ROW_TILE_V17
            and task40_q_assembly_strategy_is_allowed(
                str(specification.solver.get('task40_reference_pc_strategy')),
                str(specification.solver.get('task40_q_assembly_strategy')),
            )
        )
        requested_factor_lifecycle = specification.solver.get(
            'task40_factor_lifecycle_strategy', TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT
        )
        if requested_factor_lifecycle not in {
            TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
            TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
        }:
            raise InputError(
                f'unsupported Task40 factor lifecycle strategy: {requested_factor_lifecycle!r}'
            )
        if requested_factor_lifecycle == TASK40_V19_FACTOR_LIFECYCLE_STRATEGY and not v19_campaign_identity:
            raise InputError('ONE_Q_REFACTOR_V19 is restricted to the exact reviewed V19 run/profile/strategy combinations')
        v15_b0_candidate_identity = (
            v15_campaign_identity
            and specification.identity.get('run_id') == TASK40_B0_P6_V15_RUN_ID
            and specification.solver.get('preconditioner') == TASK40_V15_P6_B0_PROFILE
        )
        task40_campaign_identity = (
            v10_identity or v11_grid_identity or v13_campaign_identity
            or v15_campaign_identity or v16_campaign_identity or v17_campaign_identity
            or v18_campaign_identity or v19_campaign_identity
        )
        from src.runners.task038_launcher import _validate_task40_v10_postprocess_request

        _validate_task40_v10_postprocess_request(
            candidate_identity=(v10_candidate_identity or v15_b0_candidate_identity),
            campaign_window=args.task40_v10_campaign_window,
            saved_run_directory=args.task40_v10_postprocess_from,
        )
        if args.task40_v10_campaign_window is not None and not task40_campaign_identity:
            raise InputError(
                '--task40-v10-campaign-window is restricted to reviewed Task40 V10/V11 identities or exact V13/V15/V16/V17/V18/V19 p6 run/profile/strategy combinations'
            )
        if task40_campaign_identity and not args.task40_v10_campaign_window and not (
            args.validate_only or args.dry_run
        ):
            raise InputError('Task40 V10/V11/V13/V15/V16/V17/V18/V19 p6 launches require --task40-v10-campaign-window')
        if args.task40_v10_campaign_window is not None and (args.validate_only or args.dry_run):
            from src.runners.task40_v10_campaign import load_fixed_campaign_window
            load_fixed_campaign_window(args.task40_v10_campaign_window)
        if args.task40_reference_from is not None:
            if args.dry_run:
                raise InputError('--task40-reference-from cannot be combined with --dry-run')
            from src.runners.fine_reference_preflight import (
                load_task40_reference_witness,
            )
            if args.validate_only:
                witness, identity = load_task40_reference_witness(
                    args.input_path, specification.as_jsonable(),
                    args.task40_reference_from,
                )
                print(json.dumps({
                    'status': 'valid',
                    'workflow': 'task40_direct_reference_preflight',
                    'g0_run_directory': identity['g0_run_directory'],
                    'g0_source_sha': identity['g0_source_sha'],
                    'g0_input_sha256': identity['g0_input_sha256'],
                    'direct_input_sha256': identity['direct_input_sha256'],
                    'physical_model_sha256': identity['physical_model_sha256'],
                    'g0_physical_model_sha256': identity[
                        'g0_physical_model_sha256'
                    ],
                    'original_physical_sha256': identity[
                        'original_physical_sha256'
                    ],
                    'normalized_physical_sections_sha256': identity[
                        'normalized_physical_sections_sha256'
                    ],
                    'identity_difference': identity['identity_difference'],
                    'ordered_mode_sha256': identity['ordered_mode_sha256'],
                    'p6_native_map_sha256': identity['p6_native_map_sha256'],
                    'expected_dimensions': identity['expected_dimensions'],
                    'g0_full_A6_residual_relative': identity[
                        'g0_full_A6_residual_relative'
                    ],
                    'witness_vector_rows': int(witness['rhs']['b'].size),
                }, sort_keys=True, separators=(',', ':')))
                return 0
            if any((args.physical_pc_profile, args.macro_v10_controls,
                    args.macro_v11_controls, args.macro_v11_calibration,
                    args.macro_v12, args.macro_v12_supplement,
                    args.p4_direction_diagnosis, args.recover_v15_q0_eio_once,
                    args.profile_budget_ledger is not None)):
                raise InputError('--task40-reference-from is a standalone direct-reference workflow')
            try:
                source_sha = _source_sha()
            except (OSError, subprocess.CalledProcessError) as exc:
                raise InputError(f'cannot determine Task40 reference source SHA: {exc}') from exc
            output = (Path('benchmarks/artifacts/task40extra_0p7nm_engineering')
                      / 'direct_reference_v1' / source_sha)
            cache_path=args.task40_reference_from / 'v20_jit_cache'
            if not cache_path.is_dir():
                raise InputError(f'Task40 G0 qualified JIT cache is missing: {cache_path}')
            from src.runners.fine_reference_preflight import main as reference_main
            return reference_main([
                '--input', str(args.input_path), '--directory', str(output),
                '--expected-sha', source_sha, '--workflow-seconds', '43200',
                '--task40-witness-run-dir', str(args.task40_reference_from),
                '--cache-path', str(cache_path),
            ])
        if (
            args.v14_time_policy == 'observe_only'
            and specification.solver.get('preconditioner') not in {
                'physical_p4_schur_v14',
                'physical_p4_blr_bal_h_v16',
                'physical_p4_blr_tradeoff_v17',
                'physical_p4_cell_condensed_exact_v18',
                'physical_p4_cell_condensed_blr_v18',
                'physical_p6_trace_p4_condensed_balh_v19',
                'physical_p6_trace_p4_condensed_lowmem_v20',
                'physical_p6_trace_p4_condensed_robustness_v21',
                'physical_p6_trace_p4_condensed_capacity_v22',
                'physical_p6_trace_p4_condensed_physical_memory_v23',
                'physical_p6_trace_p4_condensed_laptop_speed_v24',
                'physical_p6_trace_coarse_degree_speed_v25',
                'physical_p6_trace_setup_efficiency_v26',
                'physical_p6_trace_workingset_efficiency_v27',
                'physical_p6_trace_fused_kernel_v28',
                'physical_p6_trace_a4_tensor_h6_v29',
                'physical_p6_trace_workstation_guided_v30',
                'physical_p6_trace_projection_layout_v31',
                'task40extra_0p7nm_p6trace_p4_v1',
                'task40extra_0p7nm_p6trace_p4_reference_metric_v2',
            }
        ):
            raise InputError(
                '--v14-time-policy observe_only requires '
                'a reviewed physical iterative profile with a frozen '
                'observe_only resource contract'
            )
        if args.validate_only:
            payload = {
                "status": "valid",
                "model_id": specification.identity["model_id"],
                "run_id": specification.identity["run_id"],
                "method": specification.method["kind"],
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
        from src.io.physical_recursive_profile import (
            MACRO_V10_PROFILE, MACRO_V11_PROFILE, MACRO_V12_PROFILE,
            P4_DIRECTION_DIAGNOSIS_PROFILE,
        )
        p4_direction = (
            args.p4_direction_diagnosis
            or specification.solver.get('preconditioner') == P4_DIRECTION_DIAGNOSIS_PROFILE
        )
        if p4_direction:
            if specification.solver.get('preconditioner') != P4_DIRECTION_DIAGNOSIS_PROFILE:
                raise InputError(
                    '--p4-direction-diagnosis requires a .dat with '
                    f'solver.preconditioner={P4_DIRECTION_DIAGNOSIS_PROFILE}'
                )
            if args.profile_budget_ledger is not None:
                raise InputError('--p4-direction-diagnosis uses the existing runner without a new ledger')
            try:
                source_sha = _source_sha()
            except (OSError, subprocess.CalledProcessError) as exc:
                raise InputError(f'cannot determine diagnosis source SHA: {exc}') from exc
            output = args.p4_direction_output or (
                Path('benchmarks/artifacts/task39extra/p4_direction_diagnosis_v13')
                / source_sha / 'diagnosis'
            )
            from src.runners.physical_recursive_entry import launch_p4_direction_diagnosis
            result = launch_p4_direction_diagnosis(argparse.Namespace(
                input=args.input_path, inventory=args.macro_v12_inventory,
                output=output, source_sha=source_sha, target='lo',
                p4_direction_diagnosis=True,
                p4_direction_reuse_root=args.p4_direction_reuse_root,
            ))
            print(json.dumps(result, sort_keys=True, separators=(',', ':')))
            return 0 if result.get('classification') == 'COMPLETED' else 3
        macro_v12 = args.macro_v12 or specification.solver.get('preconditioner') == MACRO_V12_PROFILE
        if args.macro_v12_supplement and not macro_v12:
            raise InputError('--macro-v12-supplement requires a V12 input')
        if macro_v12:
            if specification.solver.get('preconditioner') != MACRO_V12_PROFILE:
                raise InputError(
                    '--macro-v12 requires a .dat with solver.preconditioner=physical_macro_dd4_v12'
                )
            stage = specification.solver.get('stage')
            if args.macro_v12_stage is not None and args.macro_v12_stage != stage:
                raise InputError('--macro-v12-stage must match solver.stage in the .dat')
            if stage is None:
                raise InputError('V12 requires an explicit solver.stage')
            outer_restart = int(specification.solver.get('outer_restart', 0))
            if args.macro_v12_outer_restart is not None and args.macro_v12_outer_restart != outer_restart:
                raise InputError('--macro-v12-outer-restart must match solver.outer_restart in the .dat')
            try:
                source_sha = _source_sha()
            except (OSError, subprocess.CalledProcessError) as exc:
                raise InputError(f'cannot determine V12 source SHA: {exc}') from exc
            ledger = args.profile_budget_ledger or Path(
                'benchmarks/artifacts/task39extra/v12_supplement/v12_supplement_budget.json'
                if args.macro_v12_supplement else
                'benchmarks/artifacts/task39extra/v12_o0_o4/v12_o0_o4_budget.json'
            )
            output = args.macro_v12_output or (
                Path(
                    'benchmarks/artifacts/task39extra/v12_supplement'
                    if args.macro_v12_supplement else
                    'benchmarks/artifacts/task39extra/v12_o0_o4'
                )
                / source_sha / stage.lower()
            )
            from src.runners.physical_recursive_entry import _launch_macro_v12_stage
            launch_args = argparse.Namespace(
                input=args.input_path, inventory=args.macro_v12_inventory,
                output=output, budget=ledger, source_sha=source_sha, target='lo',
                jit_cache=None, macro_v12=True, macro_v12_stage=stage,
                macro_v12_outer_restart=outer_restart,
                macro_v12_framework=args.macro_v12_framework,
                macro_v12_supplement=args.macro_v12_supplement,
            )
            result = _launch_macro_v12_stage(launch_args)
            print(json.dumps(result, sort_keys=True, separators=(',', ':')))
            return 0 if result.get('classification') == 'COMPLETED' else 3
        macro_v11 = (args.macro_v11_controls or args.macro_v11_calibration
                     or specification.solver.get('preconditioner') == MACRO_V11_PROFILE)
        macro_v10 = args.macro_v10_controls or specification.solver.get('preconditioner') == MACRO_V10_PROFILE
        if macro_v10 or macro_v11:
            selected_profile = MACRO_V11_PROFILE if macro_v11 else MACRO_V10_PROFILE
            if ((args.macro_v10_controls or args.macro_v11_controls)
                    and specification.solver.get('preconditioner') != selected_profile):
                raise InputError(
                    'macro controls require a .dat with '
                    f'solver.preconditioner={selected_profile}'
                )
            if macro_v11:
                stage = specification.solver.get('stage')
                if args.macro_v11_calibration and stage != 'N1_CALIBRATION':
                    raise InputError(
                        '--macro-v11-calibration requires solver.stage=N1_CALIBRATION'
                    )
                if not args.macro_v11_calibration and stage != 'N2_M1_CONTROLS':
                    raise InputError(
                        'V11 M1 controls require solver.stage=N2_M1_CONTROLS'
                    )
            from src.runners.physical_recursive_entry import (
                launch_macro_v10_workflow, launch_macro_v11_workflow,
                launch_macro_v11_calibration,
            )
            if macro_v11:
                ledger = args.profile_budget_ledger or Path(
                    'benchmarks/artifacts/task39extra/v11_n0_n2/v11_n0_n2_budget.json'
                )
                result = (launch_macro_v11_calibration(
                    specification, ledger, args.macro_v10_inventory,
                ) if args.macro_v11_calibration else launch_macro_v11_workflow(
                    specification, ledger, args.macro_v10_inventory,
                ))
            else:
                ledger = args.profile_budget_ledger or Path(
                    'benchmarks/artifacts/task39extra/v10_m1/v10_m1_budget.json'
                )
                result = launch_macro_v10_workflow(
                    specification, ledger, args.macro_v10_inventory,
                )
            print(json.dumps(result, sort_keys=True, separators=(',', ':')))
            return 0 if result.get('classification') == 'COMPLETED' else 3
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
            from src.io.physical_intermediate_profile import LIGHT_PROFILE, JOINT_PROFILE
            from src.io.physical_balanced_profile import BALANCED_PROFILES, BOUNDED_PROFILES
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
            if specification.solver.get('preconditioner') in BOUNDED_PROFILES:
                from src.runners.physical_bounded_budget import launch_bounded_workflow
                result = launch_bounded_workflow(specification, args.profile_budget_ledger)
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return 0 if result['result_classification'] == 'worker_exit0' else 3
            if specification.solver.get('preconditioner') in (LIGHT_PROFILE, JOINT_PROFILE):
                from src.runners.physical_profile_budget import launch_light_workflow
                result = launch_light_workflow(specification, args.profile_budget_ledger)
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return 0 if result['result_classification'] == 'worker_exit0' else 3
            if args.profile_budget_ledger is not None:
                raise InputError('--profile-budget-ledger requires --physical-pc-profile')
            result = launch_specification(
                specification,
                v14_time_policy=args.v14_time_policy,
                v24_p4_prefix_target=args.v24_p4_prefix_target,
                task40_v10_campaign_window=args.task40_v10_campaign_window,
                task40_v10_postprocess_from=args.task40_v10_postprocess_from,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["result_classification"] == "worker_exit0" else 3
    except InputError as exc:
        print(f"Task38 input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
