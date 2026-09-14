"""One reviewed original case with an action-only p6 condensed outer space."""

import json
import signal
from pathlib import Path

from src.io.physical_intermediate_profile import DUAL_CELL_CONDENSED_PROFILE, profile_facts


def run_physical_dual_cell_condensed_v19(resolved_payload, run_directory, *, source_sha):
    """Reuse common setup, accurate p4, watchdog and native final evaluation."""
    from src.io.input_validation import simulation_config_3d_from_normalized
    from .physical_p4_cell_condensed_v18 import cell_condensed_stack_factory
    from .physical_p4_schur_v14 import (
        V14ResourceStop, _V14Runtime, _abi_facts, _build_common, _destroy_common,
        _repo_root, _v14_known_preallocation_gate, _v14_q4_q5_fullspace, _write_json,
    )
    from .physical_retained_outer_adapter import build_retained_outer_adapter

    directory = Path(run_directory).resolve()
    profile, stage = (str(resolved_payload["solver"][key]) for key in ("preconditioner", "stage"))
    contract = profile_facts(profile)
    summary = {"schema": "task039extra.v19.worker-summary.v1", "profile": profile,
               "stage": stage, "source_sha": source_sha, "status": "STARTED",
               "official_result": False, "stage_pass": False, "time_policy": "observe_only"}
    runtime = common = None
    handlers = {}
    try:
        if profile != DUAL_CELL_CONDENSED_PROFILE or stage != "X2_ORIGINAL":
            raise ValueError("V19 allows only the frozen dual-condensed original")
        if resolved_payload.get("derived", {}).get("physical_intermediate_profile") != contract:
            raise ValueError("resolved V19 contract changed")
        summary["abi"] = _abi_facts()
        runtime = _V14Runtime(
            directory, stage, contract, root=_repo_root(), source_sha=source_sha,
            batch_identity="review_v19_p6_p4_cell_condensed", evidence_prefix="v19",
        )
        if runtime.time_policy != "observe_only":
            raise ValueError("V19 requires observe_only throughout the worker")
        summary["shared_budget"] = runtime.shared_budget
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(signum, lambda *_: setattr(runtime, "stop_requested", True))
        runtime.sample("v19_preflight")
        _v14_known_preallocation_gate(runtime, stage, include_common=True, include_matrices=False)
        common = _build_common(runtime, simulation_config_3d_from_normalized(resolved_payload))
        summary.update(_v14_q4_q5_fullspace(
            runtime, common, resolved_payload, stage=stage,
            predecessor={"accepted_p4": "V18_exact", "old_notch": "USER_CLOSED",
                         "original_only": True, "old_ledger": runtime.shared_budget},
            stack_factory=cell_condensed_stack_factory(backend="exact"),
            outer_adapter_factory=build_retained_outer_adapter,
        ))
    except V14ResourceStop as exc:
        summary.update(status="CONTROLLED_STOP", stage_pass=False,
                       result_classification=exc.classification, error=str(exc))
    except FloatingPointError as exc:
        summary.update(status="NUMERICAL_GATE_STOP", stage_pass=False,
                       result_classification="NONFINITE_NUMERICAL_RESULT", error=str(exc))
    except Exception as exc:
        summary.update(status="FAILED", stage_pass=False, result_classification="WORKER_FAILED",
                       error={"type": type(exc).__name__, "message": str(exc)})
    finally:
        if runtime is not None:
            try:
                runtime.set_phase("cleanup")
                if common is not None:
                    _destroy_common(common, runtime)
                runtime.sample("v19_post_cleanup")
            except Exception as exc:
                summary.update(status="FAILED", stage_pass=False, result_classification="CLEANUP_FAILED",
                               cleanup_error={"type": type(exc).__name__, "message": str(exc)})
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        # X1 and checkpoints are already durable if later setup/solve failed.
        for name in ("x1_setup_checks", "x2_retained_final"):
            path = directory / f"{name}.json"
            if path.exists():
                summary[name] = json.loads(path.read_text())
        _write_json(directory / "physical_dual_cell_condensed_v19_summary.json", summary)
        if runtime is not None:
            runtime.marker("v19_worker_complete", summary)
    return {"passed": bool(summary["stage_pass"]),
            "errors": [] if summary["stage_pass"] else [str(summary.get("error", summary["status"]))],
            "summary": summary, "numerical_output_directory": str(directory / "numerical_output")}
