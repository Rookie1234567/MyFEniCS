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
        '--macro-v12-inventory', type=Path,
        default=Path('benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json'),
    )
    parser.add_argument('--profile-budget-ledger', '--batch-budget-ledger', dest='profile_budget_ledger', type=Path)
    parser.add_argument('--macro-v10-inventory', type=Path,
                        default=Path('benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json'))
    parser.add_argument('--profile-variant', choices=('R0', 'a2r_equivalent_fast_v1', 'a2r_packed_equivalent_v2'), default='R0')
    parser.add_argument('--profile-r0-reference', type=Path)
    parser.add_argument('--profile-recovery-from', '--profile-cache-recovery-from',
                        dest='profile_recovery_from', type=Path, metavar='FAILED_R0_DIRECTORY')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.profile_recovery_from is not None and args.physical_pc_profile is None:
            raise InputError('--profile-recovery-from requires --physical-pc-profile')
        if args.physical_pc_profile is None and (args.profile_variant != 'R0' or args.profile_r0_reference is not None):
            raise InputError('fast profile options require --physical-pc-profile')
        specification = load_and_resolve(args.input_path)
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
            result = launch_specification(specification)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["result_classification"] == "worker_exit0" else 3
    except InputError as exc:
        print(f"Task38 input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
