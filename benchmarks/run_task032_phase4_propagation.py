from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI
import numpy as np

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host research path
    resource = None

from src.modes.stable_propagation import (
    TwoSidedPropagation,
    build_two_sided_propagation,
    diagnose_reciprocity_and_passivity,
)


ROOT = Path(__file__).resolve().parents[1]
PHASE3_RECORD = (
    ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "modes_phase3.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "080"
    / "phase4"
    / "stable_propagation.json"
)


@dataclass(frozen=True)
class _RecordMode:
    beta: complex
    direction: str
    passive_branch_valid: bool = True


def _complex(value: list[float]) -> complex:
    return complex(float(value[0]), float(value[1]))


def _complex_json(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    comm: MPI.Intracomm,
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        tracked_status = (
            None
            if verified_clean_sha is not None
            else _git("status", "--porcelain", "--untracked-files=all")
        )
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or (verified_clean_sha is None and tracked_status is None):
        raise SystemExit("Cannot verify Task32 Phase4 source identity and cleanliness.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            character not in "0123456789abcdef" for character in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match HEAD {head}."
            )
        tracked_dirty = False
        verification = "host_git_clean_attestation"
    else:
        if tracked_status and not allow_dirty_research:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase4 code first or pass "
                "--allow-dirty-research for a non-qualifying run."
            )
        tracked_dirty = bool(tracked_status)
        verification = "dirty_research_opt_in" if tracked_dirty else "local_git_status"
    return {
        "commit_sha": head,
        "branch": branch,
        "git_dirty": tracked_dirty,
        "tracked_source_dirty": tracked_dirty,
        "verification": verification,
        "verified_clean_sha": verified_clean_sha,
    }


def _relative_error(first: complex, second: complex) -> float:
    return float(abs(first - second) / max(abs(first), abs(second), 1.0e-15))


def _historical_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _propagation_record(propagation: TwoSidedPropagation) -> dict[str, Any]:
    return {
        "length_nm": propagation.length_nm,
        "representation": propagation.representation,
        "local_reflection_terms_present": (propagation.local_reflection_terms_present),
        "growing_inverse_factors_present": (
            propagation.growing_inverse_factors_present
        ),
        "stored_complex_scalars": propagation.stored_complex_scalars,
        "max_factor_magnitude": propagation.max_factor_magnitude,
        "passivity_valid": propagation.passivity_valid,
        "forward": {
            "source_indices": list(propagation.forward.source_indices),
            "beta_per_nm": [
                _complex_json(value) for value in propagation.forward.beta_per_nm
            ],
            "factors": [_complex_json(value) for value in propagation.forward.factors],
            "log_magnitudes": list(propagation.forward.log_magnitudes),
            "phase_advances_rad": list(propagation.forward.phase_advances_rad),
        },
        "backward": {
            "source_indices": list(propagation.backward.source_indices),
            "beta_per_nm": [
                _complex_json(value) for value in propagation.backward.beta_per_nm
            ],
            "factors": [_complex_json(value) for value in propagation.backward.factors],
            "log_magnitudes": list(propagation.backward.log_magnitudes),
            "phase_advances_rad": list(propagation.backward.phase_advances_rad),
        },
    }


def _case_record(
    case: dict[str, Any],
    *,
    length_nm: float,
    first_length_nm: float,
) -> dict[str, Any]:
    positive_modes = case["positive"]["modes"]
    forward = [
        _RecordMode(
            beta=_complex(mode["beta_per_nm"]),
            direction="forward",
            passive_branch_valid=bool(mode["passive_branch_valid"]),
        )
        for mode in positive_modes
    ]
    if case.get("negative") is not None:
        backward = [
            _RecordMode(
                beta=_complex(mode["beta_per_nm"]),
                direction="backward",
                passive_branch_valid=bool(mode["passive_branch_valid"]),
            )
            for mode in case["negative"]["modes"]
        ]
        backward_source = "phase3_negative_basis"
    else:
        backward = [
            _RecordMode(beta=-mode.beta, direction="backward") for mode in forward
        ]
        backward_source = "reciprocal_mirror_of_phase3_positive_beta"
    modes = [*forward, *backward]
    propagation = build_two_sided_propagation(modes, length_nm)
    first = build_two_sided_propagation(modes, first_length_nm)
    second = build_two_sided_propagation(modes, length_nm - first_length_nm)
    composed = first.compose(second)
    composition_error = max(
        (
            _relative_error(composed_value, direct_value)
            for composed_value, direct_value in zip(
                [*composed.forward.factors, *composed.backward.factors],
                [*propagation.forward.factors, *propagation.backward.factors],
            )
        ),
        default=0.0,
    )

    forward_input = np.ones(propagation.forward.mode_count, dtype=np.complex128)
    backward_input = np.ones(propagation.backward.mode_count, dtype=np.complex128)
    forward_only = propagation.apply(
        forward_input,
        np.zeros_like(backward_input),
    )
    backward_only = propagation.apply(
        np.zeros_like(forward_input),
        backward_input,
    )
    reflection_norm = max(
        float(np.linalg.norm(forward_only.bottom_backward)),
        float(np.linalg.norm(backward_only.top_forward)),
    )
    input_power = float(
        np.vdot(forward_input, forward_input).real
        + np.vdot(backward_input, backward_input).real
    )
    both = propagation.apply(forward_input, backward_input)
    output_power = float(
        np.vdot(both.top_forward, both.top_forward).real
        + np.vdot(both.bottom_backward, both.bottom_backward).real
    )
    diagnostic = diagnose_reciprocity_and_passivity(propagation)
    return {
        "case_id": case["case_id"],
        "phase3_record_h_nm": float(case["h_nm"]),
        "backward_source": backward_source,
        "propagation": _propagation_record(propagation),
        "composition_lengths_nm": [
            first_length_nm,
            length_nm - first_length_nm,
        ],
        "composition_max_relative_error": composition_error,
        "reflection_norm": reflection_norm,
        "input_coefficient_power": input_power,
        "output_coefficient_power": output_power,
        "coefficient_power_gain": output_power / input_power,
        "reciprocity": {
            "pair_count": len(diagnostic.pairs),
            "unmatched_forward": list(diagnostic.unmatched_forward),
            "unmatched_backward": list(diagnostic.unmatched_backward),
            "max_relative_beta_error": (diagnostic.max_relative_beta_error),
            "max_relative_factor_error": (diagnostic.max_relative_factor_error),
            "reciprocity_valid": diagnostic.reciprocity_valid,
            "passivity_valid": diagnostic.passivity_valid,
        },
    }


def _negative_and_evanescent_controls(length_nm: float) -> dict[str, Any]:
    evanescent = build_two_sided_propagation(
        [
            _RecordMode(0.0 + 10.0j, "forward"),
            _RecordMode(0.0 - 10.0j, "backward"),
        ],
        length_nm,
    )
    outgoing = evanescent.apply([1.0], [1.0])
    growing_rejected = False
    try:
        build_two_sided_propagation(
            [
                _RecordMode(0.08 - 0.01j, "forward"),
                _RecordMode(-0.08 - 0.01j, "backward"),
            ],
            length_nm,
        )
    except ValueError:
        growing_rejected = True
    ambiguous_rejected = False
    try:
        build_two_sided_propagation(
            [
                _RecordMode(0.0j, "ambiguous", False),
                _RecordMode(-0.08, "backward"),
            ],
            length_nm,
        )
    except ValueError:
        ambiguous_rejected = True
    return {
        "evanescent_beta_per_nm": [0.0, 10.0],
        "forward_factor": _complex_json(evanescent.forward.factors[0]),
        "backward_factor": _complex_json(evanescent.backward.factors[0]),
        "all_outputs_finite": bool(
            np.all(np.isfinite(outgoing.top_forward))
            and np.all(np.isfinite(outgoing.bottom_backward))
        ),
        "underflow_without_overflow": bool(
            evanescent.forward.factors[0] == 0.0j
            and evanescent.backward.factors[0] == 0.0j
        ),
        "growing_branch_rejected": growing_rejected,
        "ambiguous_branch_rejected": ambiguous_rejected,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase4 stable two-sided propagation validation"
    )
    parser.add_argument("--phase3-record", type=Path, default=PHASE3_RECORD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument("--length-nm", type=float, default=100.0)
    parser.add_argument("--first-length-nm", type=float, default=37.0)
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default="sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d",
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if not 0.0 < args.first_length_nm < args.length_nm:
        raise SystemExit("Require 0 < first-length-nm < length-nm.")
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    started = time.perf_counter()
    phase3_bytes = args.phase3_record.read_bytes()
    phase3 = json.loads(phase3_bytes)
    if phase3.get("status") != "pass":
        raise SystemExit("Phase3 mode record must have pass status.")
    cases = [
        _case_record(
            case,
            length_nm=args.length_nm,
            first_length_nm=args.first_length_nm,
        )
        for case in phase3["cases"]
    ]
    controls = _negative_and_evanescent_controls(args.length_nm)
    local_signature = hashlib.sha256(
        json.dumps(
            {"cases": cases, "controls": controls},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    rank_signatures = comm.gather(local_signature, root=0)
    rank_agreement = comm.bcast(
        len(set(rank_signatures)) == 1 if comm.rank == 0 else None,
        root=0,
    )
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    rss = comm.gather(
        {
            "rank": comm.rank,
            "historical_peak_rss_mb": _historical_peak_rss_mb(),
        },
        root=0,
    )

    gates = {
        "all_cases_use_100_nm_two_port_scattering": all(
            case["propagation"]["length_nm"] == 100.0
            and case["propagation"]["representation"] == "two_port_diagonal_scattering"
            for case in cases
        ),
        "all_cases_reflection_free": all(
            case["reflection_norm"] <= 1.0e-15
            and not case["propagation"]["local_reflection_terms_present"]
            for case in cases
        ),
        "all_cases_passive_without_growing_inverse": all(
            case["propagation"]["passivity_valid"]
            and not case["propagation"]["growing_inverse_factors_present"]
            and case["propagation"]["max_factor_magnitude"] <= 1.0 + 1.0e-12
            and case["coefficient_power_gain"] <= 1.0 + 1.0e-12
            for case in cases
        ),
        "all_cases_composition_le_1e-12": all(
            case["composition_max_relative_error"] <= 1.0e-12 for case in cases
        ),
        "all_cases_reciprocity_diagnostic_pass": all(
            case["reciprocity"]["reciprocity_valid"]
            and case["reciprocity"]["passivity_valid"]
            for case in cases
        ),
        "strong_evanescent_underflows_without_overflow": (
            controls["all_outputs_finite"] and controls["underflow_without_overflow"]
        ),
        "growing_and_ambiguous_branches_fail_closed": (
            controls["growing_branch_rejected"]
            and controls["ambiguous_branch_rejected"]
        ),
        "mpi_ranks_agree_and_storage_is_linear": (
            rank_agreement
            and all(
                case["propagation"]["stored_complex_scalars"]
                == len(case["propagation"]["forward"]["factors"])
                + len(case["propagation"]["backward"]["factors"])
                for case in cases
            )
        ),
    }
    status = "pass" if all(gates.values()) else "fail"
    if comm.rank == 0:
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "schema_version": 1,
            "benchmark_id": "case080_task032_phase4_stable_propagation",
            "status": status,
            "timestamp_utc": timestamp,
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase4_propagation "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "coefficient_distribution": "small_mode_count_replicated",
                "full_field_vector_gather": False,
                "provenance": (
                    "clean_task032_phase4_stable_propagation"
                    if not provenance["tracked_source_dirty"]
                    else "dirty_task032_phase4_stable_propagation_research"
                ),
            },
            "phase3_record": str(args.phase3_record),
            "phase3_record_sha256": hashlib.sha256(phase3_bytes).hexdigest(),
            "cases": cases,
            "controls": controls,
            "gates": gates,
            "mpi_rank_signatures": rank_signatures,
            "elapsed_seconds_max_rank": elapsed,
            "historical_peak_rss_by_rank": rss,
            "memory_note": (
                "Per-rank process-lifetime historical peaks are not simultaneous. "
                "Only small modal coefficient arrays are replicated."
            ),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": status, "gates": gates}, indent=2))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
