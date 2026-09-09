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
