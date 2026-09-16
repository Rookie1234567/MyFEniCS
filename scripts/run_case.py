"""Thin public Task38 input entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from src.io import dry_run_payload, load_and_resolve
from src.io.input_loader import InputError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Task38 .dat input; method and MPI come from the file."
    )
    parser.add_argument("input_path", type=Path, help="one Task38 .dat input")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    packet_source = parser.add_mutually_exclusive_group()
    packet_source.add_argument(
        "--producer-packet-root",
        type=Path,
        help="reuse a completed Task041 BAL_H producer packet",
    )
    packet_source.add_argument(
        "--legacy-native-packet-descriptor",
        type=Path,
        help="import the explicitly qualified native Task039 V4 packet",
    )
    time_control = parser.add_mutually_exclusive_group()
    time_control.add_argument(
        "--task041-performance-profile",
        choices=("task041_schur_speed_v2",),
        help="opt into the reviewed Task041 Schur timing profile",
    )
    time_control.add_argument(
        "--task041-balh-candidate-disable-time-stop",
        action="store_true",
        help="disable only the time stops for one reused 5 nm BAL_H candidate",
    )
    parser.add_argument(
        "--task041-supervision-record",
        type=Path,
        help="absolute V2 outer-supervision launch manifest",
    )
    parser.add_argument(
        "--task041-rhs-probe",
        type=Path,
        metavar="MANIFEST",
        help="fixed V2 representative-RHS probe manifest",
    )
    parser.add_argument(
        "--task041-side-setup-schedule",
        choices=("sequential_component",),
        help="use the reviewed sequential representative-side setup schedule",
    )
    parser.add_argument(
        "--task041-comparison-mode",
        choices=("common_layout_equivalence",),
        help="opt into the reviewed common-layout representative comparison",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        specification = load_and_resolve(args.input_path)
        if args.task041_balh_candidate_disable_time_stop:
            from benchmarks.task041_balh_workflow import (
                TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
            )

            if (
                specification.identity.get("model_id")
                != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
                or args.producer_packet_root is None
                and args.legacy_native_packet_descriptor is None
            ):
                raise InputError(
                    "time-stop override requires the reused 5 nm BAL_H candidate"
                )
        if args.task041_performance_profile is not None:
            from benchmarks.task041_balh_workflow import (
                task041_schur_speed_v2_contract,
            )
            from src.io.input_validation import TASK041_BALH_CANDIDATE_MODEL_IDS

            if (
                specification.identity.get("model_id")
                not in TASK041_BALH_CANDIDATE_MODEL_IDS
                or args.producer_packet_root is None
                and args.legacy_native_packet_descriptor is None
            ):
                raise InputError(
                    "task041_schur_speed_v2 requires a reused BAL_H candidate packet"
                )
            try:
                task041_schur_speed_v2_contract(
                    str(specification.identity["model_id"]),
                    scope=(
                        "representative_rhs"
                        if args.task041_rhs_probe is not None
                        else None
                    ),
                    side_setup_schedule=args.task041_side_setup_schedule,
                    comparison_mode=args.task041_comparison_mode,
                )
            except ValueError as exc:
                raise InputError(str(exc)) from exc
        elif (
            args.task041_side_setup_schedule is not None
            or args.task041_comparison_mode is not None
        ):
            raise InputError(
                "Task041 comparison options require task041_schur_speed_v2"
            )
        if args.task041_supervision_record is not None:
            from src.io.input_validation import TASK041_BALH_2NM_MODEL_ID

            if (
                args.task041_performance_profile != "task041_schur_speed_v2"
                and specification.identity.get("model_id")
                != TASK041_BALH_2NM_MODEL_ID
            ):
                raise InputError(
                    "--task041-supervision-record requires a registered Task041 contract"
                )
            if not args.task041_supervision_record.is_absolute():
                raise InputError(
                    "--task041-supervision-record must be an absolute path"
                )
        if args.task041_rhs_probe is not None:
            if args.task041_performance_profile != "task041_schur_speed_v2":
                raise InputError(
                    "--task041-rhs-probe requires task041_schur_speed_v2"
                )
            if not args.task041_rhs_probe.is_absolute():
                raise InputError("--task041-rhs-probe must be an absolute path")
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

        result = launch_specification(
            specification,
            producer_packet_root=args.producer_packet_root,
            legacy_native_packet_descriptor=args.legacy_native_packet_descriptor,
            disable_time_stop=args.task041_balh_candidate_disable_time_stop,
            performance_profile=args.task041_performance_profile,
            task041_supervision_record=args.task041_supervision_record,
            task041_rhs_probe_manifest=args.task041_rhs_probe,
            task041_side_setup_schedule=args.task041_side_setup_schedule,
            task041_comparison_mode=args.task041_comparison_mode,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["result_classification"] == "worker_exit0" else 3
    except InputError as exc:
        print(f"Task38 input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
