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
        choices=("common_layout_equivalence", "p4_backend_pair"),
        help="opt into a reviewed Task041 representative comparison",
    )
    parser.add_argument(
        "--task041-top-causal-replay",
        action="store_true",
        help="capture and replay the selected top fixed-RHS causal nodes",
    )
    parser.add_argument(
        "--task041-p4-response-correction-steps",
        type=int,
        choices=(0, 1),
        default=0,
        help="apply at most one same-factor P4 correction in the top causal diagnostic",
    )
    parser.add_argument(
        "--task041-p4-refinement-target-tolerance",
        type=float,
        choices=(5.0e-13,),
        default=None,
    )
    parser.add_argument(
        "--task041-p4-backend-pair-side",
        choices=("bottom", "top"),
        default=None,
    )
    parser.add_argument(
        "--task041-p4-correction-replay-from",
        type=Path,
        metavar="G1_CONSUMER_ROOT",
        help="run the fixed PC1 Q1/Q2 correction diagnostic from frozen G1 packets",
    )
    parser.add_argument(
        "--task041-resource-policy",
        choices=("task041_v8_swap_observe_continue",),
        default=None,
        help="opt into the Task041 V8 swap-observe-only resource policy",
    )
    parser.add_argument(
        "--task041-fixed-h6-modal-gmres-research",
        action="store_true",
        help="opt into the registered Task041 fixed-H6 modal research candidate",
    )
    parser.add_argument(
        "--task041-modal-feedback-method",
        choices=("fixed_physical_balh_once",),
        default=None,
        help="select the explicitly registered W0.7 fixed physical BAL_H feedback",
    )
    parser.add_argument(
        "--task041-expected-rank-cpus",
        help="comma-separated frozen Task041 rank-to-CPU map (fixed-H6 only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        specification = load_and_resolve(args.input_path)
        from src.io.input_validation import task041_balh_case

        registered_case = task041_balh_case(
            str(specification.identity.get("model_id", ""))
        )
        target_tolerance = args.task041_p4_refinement_target_tolerance
        target_side = args.task041_p4_backend_pair_side
        resource_policy_binding = None
        if args.task041_resource_policy is not None:
            from benchmarks.task041_balh_workflow import (
                task041_v8_resource_policy_binding,
            )

            try:
                resource_policy_binding = task041_v8_resource_policy_binding(
                    str(specification.identity.get("model_id", "")),
                    args.task041_resource_policy,
                )
            except ValueError as exc:
                raise InputError(str(exc)) from exc
        expected_rank_cpus = None
        fixed_h6_binding = None
        packet_source_binding = None
        fresh_fixed_h6_producer = False
        if args.task041_expected_rank_cpus is not None:
            from benchmarks.task041_balh_workflow import (
                task041_parse_expected_rank_cpus,
            )

            try:
                expected_rank_cpus = task041_parse_expected_rank_cpus(
                    args.task041_expected_rank_cpus
                )
            except (TypeError, ValueError) as exc:
                raise InputError(str(exc)) from exc
        if (
            args.task041_fixed_h6_modal_gmres_research
            or expected_rank_cpus is not None
            or args.task041_modal_feedback_method is not None
        ):
            from benchmarks.task041_balh_workflow import (
                task041_fixed_h6_modal_gmres_binding,
                task041_fixed_h6_packet_source_binding,
            )

            try:
                fixed_h6_binding = task041_fixed_h6_modal_gmres_binding(
                    str(specification.identity.get("model_id", "")),
                    enabled=args.task041_fixed_h6_modal_gmres_research,
                    candidate=bool(
                        registered_case is not None
                        and registered_case.get("route") == "balh"
                    ),
                    mpi_size=int(specification.execution.get("mpi_size", -1)),
                    mode_count=int(
                        specification.method.get(
                            "requested_modes_per_direction", -1
                        )
                    ),
                    p4_inverse_backend=(
                        str(registered_case.get("p4_inverse_backend"))
                        if registered_case is not None
                        else None
                    ),
                    p4_refinement_target_tolerance=target_tolerance,
                    task041_resource_policy=args.task041_resource_policy,
                    expected_rank_cpus=expected_rank_cpus,
                    modal_feedback_method=args.task041_modal_feedback_method,
                )
            except (TypeError, ValueError) as exc:
                raise InputError(str(exc)) from exc
            try:
                packet_source_binding = task041_fixed_h6_packet_source_binding(
                    fixed_h6_binding,
                    producer_packet_root=args.producer_packet_root,
                    legacy_native_packet_descriptor=(
                        args.legacy_native_packet_descriptor
                    ),
                )
            except (OSError, TypeError, ValueError) as exc:
                raise InputError(str(exc)) from exc
            if args.legacy_native_packet_descriptor is not None:
                from benchmarks.task041_legacy_native_packet import (
                    task041_legacy_native_profile,
                )

                if not task041_legacy_native_profile(specification):
                    raise InputError(
                        "fixed-H6 legacy-native packets require the registered 5 nm profile"
                    )
        if fixed_h6_binding is not None and (
            expected_rank_cpus is None
            or (
                args.producer_packet_root is None
                and packet_source_binding is None
            )
            or args.task041_balh_candidate_disable_time_stop
            or args.task041_performance_profile is not None
            or args.task041_rhs_probe is not None
            or args.task041_side_setup_schedule is not None
            or args.task041_comparison_mode is not None
            or args.task041_top_causal_replay
            or args.task041_p4_correction_replay_from is not None
            or args.task041_p4_response_correction_steps != 0
            or target_side is not None
        ):
            raise InputError(
                "fixed-H6 research requires a frozen rank map, registered packet-source route, P4 target, and no other diagnostics"
            )
        fresh_fixed_h6_producer = (
            isinstance(packet_source_binding, dict)
            and packet_source_binding
            == {"source_type": "fresh_registered_producer"}
            and registered_case is not None
            and registered_case.get("producer_mode") == "fresh"
        )
        target_binding = None
        if target_tolerance is not None or target_side is not None:
            from benchmarks.task041_balh_workflow import (
                task041_p4_refinement_target_binding,
            )

            try:
                target_binding = task041_p4_refinement_target_binding(
                    model_id=str(specification.identity.get("model_id", "")),
                    refinement_target_tolerance=target_tolerance,
                    p4_backend_pair_side=target_side,
                    profile_id=args.task041_performance_profile,
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
        if (
            not args.validate_only
            and not args.dry_run
            and registered_case is not None
            and registered_case.get("p4_inverse_backend") == "cell_condensed"
            and args.producer_packet_root is None
            and args.legacy_native_packet_descriptor is None
            and not fresh_fixed_h6_producer
        ):
            raise InputError(
                "cell-condensed Task041 consumer requires a registered packet source or the fixed-H6 fresh producer route"
            )
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
                    top_causal_replay=args.task041_top_causal_replay,
                    p4_correction_replay=(
                        args.task041_p4_correction_replay_from is not None
                    ),
                    p4_response_correction_steps=(
                        args.task041_p4_response_correction_steps
                    ),
                    p4_refinement_target_tolerance=target_tolerance,
                    p4_backend_pair_side=target_side,
                )
            except ValueError as exc:
                raise InputError(str(exc)) from exc
        else:
            from benchmarks.task041_balh_workflow import (
                task041_p4_registered_formal_target_scope,
            )

            registered_formal_target = bool(
                registered_case is not None
                and registered_case.get("p4_inverse_backend")
                == "cell_condensed"
                and isinstance(target_binding, dict)
                and target_binding.get("scope")
                == task041_p4_registered_formal_target_scope(
                    str(specification.identity.get("model_id", ""))
                )
                and args.task041_performance_profile is None
                and target_side is None
            )
            has_non_target_comparison_option = (
                args.task041_side_setup_schedule is not None
                or args.task041_comparison_mode is not None
                or args.task041_top_causal_replay
                or args.task041_p4_correction_replay_from is not None
                or args.task041_p4_response_correction_steps != 0
            )
            if has_non_target_comparison_option or (
                (target_tolerance is not None or target_side is not None)
                and not registered_formal_target
            ):
                raise InputError(
                    "Task041 comparison options require task041_schur_speed_v2"
                )
        if args.task041_supervision_record is not None:
            from src.io.input_validation import task041_balh_service_contract

            if (
                args.task041_performance_profile != "task041_schur_speed_v2"
                and task041_balh_service_contract(
                    str(specification.identity.get("model_id"))
                )
                is None
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
        if args.task041_p4_correction_replay_from is not None:
            if (
                args.task041_top_causal_replay
                or args.task041_performance_profile != "task041_schur_speed_v2"
                or args.task041_rhs_probe is None
                or args.task041_comparison_mode != "p4_backend_pair"
                or args.task041_side_setup_schedule != "sequential_component"
                or args.task041_p4_response_correction_steps != 0
                or (
                    args.producer_packet_root is None
                    and args.legacy_native_packet_descriptor is None
                )
            ):
                raise InputError(
                    "P4 correction replay requires the explicit 5 nm fixed-eight pair, "
                    "representative RHS manifest, and producer packet"
                )
            if not args.task041_p4_correction_replay_from.is_absolute():
                raise InputError(
                    "--task041-p4-correction-replay-from must be an absolute G1 consumer root"
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
            payload = dry_run_payload(specification)
            if resource_policy_binding is not None:
                payload["task041_resource_policy"] = resource_policy_binding
            print(
                json.dumps(
                    payload,
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
            task041_top_causal_replay=args.task041_top_causal_replay,
            task041_p4_correction_replay_from=(
                args.task041_p4_correction_replay_from
            ),
            task041_p4_response_correction_steps=(
                args.task041_p4_response_correction_steps
            ),
            task041_p4_refinement_target_tolerance=target_tolerance,
            task041_p4_backend_pair_side=target_side,
            task041_resource_policy=args.task041_resource_policy,
            fixed_h6_modal_gmres_research=(
                args.task041_fixed_h6_modal_gmres_research
            ),
            modal_feedback_method=args.task041_modal_feedback_method,
            expected_rank_cpus=expected_rank_cpus,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["result_classification"] == "worker_exit0" else 3
    except InputError as exc:
        print(f"Task38 input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
