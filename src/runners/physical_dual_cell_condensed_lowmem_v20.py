"""V20 low-memory dual-condensed original worker.

This module is intentionally a thin profile adapter.  The numerical route,
true-residual gates, watchdog, and official output remain in the reviewed V14
helpers; V20 supplies only the prepared-form/cache and post-KSP ownership
policy.
"""

from __future__ import annotations

import json
import signal
from pathlib import Path

from src.io.physical_intermediate_profile import (
    LOWMEM_DUAL_CELL_CONDENSED_PROFILE,
    profile_facts,
)


def run_physical_dual_cell_condensed_lowmem_v20(
    resolved_payload, run_directory, *, source_sha
):
    """Run the Y3 original with the V20 release and cache contract."""

    from src.io.input_validation import simulation_config_3d_from_normalized
    from .physical_p4_cell_condensed_v18 import cell_condensed_stack
    from .physical_p4_schur_v14 import (
        V14ResourceStop,
        V20ReleaseGateStop,
        _V14Runtime,
        _abi_facts,
        _build_common,
        _destroy_common,
        _repo_root,
        _v14_known_preallocation_gate,
        _v14_q4_q5_fullspace,
        _write_json,
    )
    from .physical_retained_outer_adapter import (
        build_retained_outer_adapter,
        prepare_dual_condensed_forms,
    )

    directory = Path(run_directory).resolve()
    profile = str(resolved_payload["solver"]["preconditioner"])
    stage = str(resolved_payload["solver"]["stage"])
    contract = profile_facts(profile)
    summary = {
        "schema": "task039extra.v20.worker-summary.v1",
        "profile": profile,
        "stage": stage,
        "source_sha": source_sha,
        "status": "STARTED",
        "official_result": False,
        "stage_pass": False,
        "time_policy": "observe_only",
    }
    runtime = common = None
    prepared = None
    prepared_facts = None
    p4_holder = {"form": None}
    p6_holder = {"form": None}
    stack_factory = outer_factory = None
    handlers = {}
    try:
        if profile != LOWMEM_DUAL_CELL_CONDENSED_PROFILE or stage != "Y3_ORIGINAL":
            raise ValueError("V20 allows only the frozen Y3 original")
        if resolved_payload.get("derived", {}).get(
            "physical_intermediate_profile"
        ) != contract:
            raise ValueError("resolved V20 contract changed")
        summary["abi"] = _abi_facts()
        runtime = _V14Runtime(
            directory,
            stage,
            contract,
            root=_repo_root(),
            source_sha=source_sha,
            batch_identity="review_v20_dual_condensed_memory_lifecycle",
            evidence_prefix="v20",
        )
        if runtime.time_policy != "observe_only":
            raise ValueError("V20 requires observe_only throughout the worker")
        summary["shared_budget"] = runtime.shared_budget
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum, lambda *_: setattr(runtime, "stop_requested", True)
            )
        runtime.sample("v20_preflight")
        _v14_known_preallocation_gate(
            runtime, stage, include_common=True, include_matrices=False
        )
        common = _build_common(
            runtime, simulation_config_3d_from_normalized(resolved_payload)
        )
        prepared, prepared_facts = prepare_dual_condensed_forms(runtime, common)
        summary["form_preparation"] = prepared_facts
        # Transfer the two compiled forms directly to their setup consumers.
        # The preparation result must not retain a second owner while the
        # retained p6/p4 setup is running; the form holders are cleared by
        # their respective builders before the first outer KSP iteration.
        p4_holder["form"] = prepared.pop("p4_condensation")
        p6_holder["form"] = prepared.pop("p6_condensation")
        prepared.clear()
        prepared = None

        def stack_factory(runtime_, common_, resolved_, *, stage):
            return cell_condensed_stack(
                runtime_,
                common_,
                resolved_,
                stage=stage,
                backend="exact",
                compiled_form=p4_holder["form"],
                compiled_form_holder=p4_holder,
                matrix_lifecycle_policy="MATRIX_RETAINED_BACKEND_DEPENDENCY",
            )

        def outer_factory(runtime_, common_, resolved_, full_rhs, apply_pc, **kwargs):
            adapter = build_retained_outer_adapter(
                runtime_,
                common_,
                resolved_,
                full_rhs,
                apply_pc,
                compiled_form=p6_holder["form"],
                identity_cache_mode="shared_read_only_per_interior_shape",
                evidence_prefix="v20",
                **kwargs,
            )
            # The adapter has consumed the prepared form during setup.  The
            # holder is cleared before the first KSP iteration so the large
            # Form.code string is not part of the solve resident set.
            p6_holder["form"] = None
            return adapter

        summary.update(
            _v14_q4_q5_fullspace(
                runtime,
                common,
                resolved_payload,
                stage=stage,
                predecessor={
                    "accepted_v19": "physical_p6_trace_p4_condensed_balh_v19",
                    "original_only": True,
                    "old_notch": "USER_CLOSED",
                    "old_ledger": runtime.shared_budget,
                },
                stack_factory=stack_factory,
                outer_adapter_factory=outer_factory,
                release_after_final_residual=True,
                official_jit_options=prepared_facts["jit_options"],
            )
        )
    except V20ReleaseGateStop as exc:
        summary.update(
            status="RELEASE_GATE_STOP",
            stage_pass=False,
            result_classification=exc.classification,
            error=str(exc),
            release_gate=exc.facts,
        )
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            stage_pass=False,
            result_classification=exc.classification,
            error=str(exc),
        )
    except FloatingPointError as exc:
        summary.update(
            status="NUMERICAL_GATE_STOP",
            stage_pass=False,
            result_classification="NONFINITE_NUMERICAL_RESULT",
            error=str(exc),
        )
    except Exception as exc:
        summary.update(
            status="FAILED",
            stage_pass=False,
            result_classification="WORKER_FAILED",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        # Drop prepared forms/factory holders before common numerical cleanup;
        # no compiled C-code string is needed after the setup consumers have
        # built their owned kernels.
        p4_holder["form"] = None
        p6_holder["form"] = None
        if prepared is not None:
            prepared.clear()
        prepared = None
        prepared_facts = None
        stack_factory = outer_factory = None
        if runtime is not None:
            try:
                runtime.set_phase("cleanup")
                if common is not None:
                    _destroy_common(common, runtime)
                runtime.sample("v20_post_cleanup")
            except Exception as exc:
                summary.update(
                    status="FAILED",
                    stage_pass=False,
                    result_classification="CLEANUP_FAILED",
                    cleanup_error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        for name in (
            "x1_setup_checks",
            "x2_retained_final",
            "v20_release_gate",
        ):
            path = directory / f"{name}.json"
            if path.exists():
                summary[name] = json.loads(path.read_text(encoding="utf-8"))
        _write_json(
            directory / "physical_dual_condensed_memory_v20_summary.json", summary
        )
        if runtime is not None:
            runtime.marker("v20_worker_complete", summary)
    return {
        "passed": bool(summary["stage_pass"]),
        "errors": []
        if summary["stage_pass"]
        else [str(summary.get("error", summary["status"]))],
        "summary": summary,
        "numerical_output_directory": str(directory / "numerical_output"),
    }


__all__ = ["run_physical_dual_cell_condensed_lowmem_v20"]
