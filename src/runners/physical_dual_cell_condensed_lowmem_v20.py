"""V20 low-memory dual-condensed original worker.

This module is intentionally a thin profile adapter.  The numerical route,
true-residual gates, watchdog, and official output remain in the reviewed V14
helpers; V20 supplies only the prepared-form/cache and post-KSP ownership
policy.
"""

from __future__ import annotations

import hashlib
import json
import signal
from pathlib import Path

from src.io.physical_intermediate_profile import (
    LOWMEM_DUAL_CELL_CONDENSED_PROFILE,
    profile_facts,
)


def _run_physical_dual_cell_condensed_lowmem(
    resolved_payload,
    run_directory,
    *,
    source_sha,
    profile_identity=LOWMEM_DUAL_CELL_CONDENSED_PROFILE,
    allowed_stages=("Y3_ORIGINAL",),
    batch_identity="review_v20_dual_condensed_memory_lifecycle",
    evidence_prefix="v20",
    summary_schema="task039extra.v20.worker-summary.v1",
    summary_filename="physical_dual_condensed_memory_v20_summary.json",
    expected_space_counts=(173802, 51192, 113400, 80),
    derive_live_space_identity=False,
    reference_mode_by_stage=None,
    predecessor_by_stage=None,
    notch_by_stage=None,
    rhs_identity_policy="fixed_historical_contract",
    restore_summary_schema=False,
):
    """Run one parameterized dual-condensed robustness stage."""

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
        derive_condensed_space_identity,
        prepare_dual_condensed_forms,
    )

    directory = Path(run_directory).resolve()
    profile = str(resolved_payload["solver"]["preconditioner"])
    stage = str(resolved_payload["solver"]["stage"])
    contract = profile_facts(profile)
    allowed_stages = tuple(str(value) for value in allowed_stages)
    reference_mode_by_stage = dict(reference_mode_by_stage or {})
    notch_by_stage = dict(notch_by_stage or {})
    summary = {
        "schema": summary_schema,
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
    prebuilt_levels = None
    handlers = {}
    try:
        if profile != profile_identity or stage not in allowed_stages:
            raise ValueError(
                f"{profile_identity} allows only stages {allowed_stages!r}"
            )
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
            batch_identity=batch_identity,
            evidence_prefix=evidence_prefix,
        )
        if runtime.time_policy != "observe_only":
            raise ValueError("V20 requires observe_only throughout the worker")
        summary["shared_budget"] = runtime.shared_budget
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum, lambda *_: setattr(runtime, "stop_requested", True)
            )
        runtime.sample(f"{evidence_prefix}_preflight")
        if not derive_live_space_identity:
            _v14_known_preallocation_gate(
                runtime, stage, include_common=True, include_matrices=False
            )
        expected_space_facts = None
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        if derive_live_space_identity:
            from mpi4py import MPI
            from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
            from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
                _build_same_mesh_levels,
            )

            # Build only the real FE/MPC mesh layer first.  This supplies the
            # exact cell-interior and slave counts for the projected common
            # allocation gate, while avoiding a second mesh construction when
            # the heavy physical actions are assembled below.
            prebuilt_levels = _build_same_mesh_levels(
                cfg,
                MPI.COMM_WORLD,
                (6, 4),
                include_positive_coefficients=True,
            )
            p6_pre_counts, p6_pre_facts = derive_condensed_space_identity(
                prebuilt_levels["spaces"][6],
                prebuilt_levels["floquets"][6].mpc,
                appended_rows=0,
            )
            p4_pre_counts, p4_pre_facts = derive_condensed_space_identity(
                prebuilt_levels["spaces"][4],
                prebuilt_levels["floquets"][4].mpc,
                appended_rows=0,
            )
            # Preserve the reviewed V20 common-cache accounting, substituting
            # live h7.5 FE/MPC storage rows and the actual mode inventory.
            mode_inventory = build_dynamic_mode_inventory(cfg)
            port_count = int(len(mode_inventory[0]))
            p6_storage_rows = int(p6_pre_counts[0])
            p4_storage_rows = int(p4_pre_counts[0])
            component_vectors = 4 * (p6_storage_rows + p4_storage_rows) * 16 * 8
            component_indices = 4 * (p6_storage_rows + p4_storage_rows) * 4 * 8
            metric_vectors = 2 * p6_storage_rows * 16 * 8
            transfer_and_owner_plan = 256 * 1024**2
            carrier_and_mode_metadata = 64 * 1024**2 + port_count * 16 * 8
            projected_bytes = (
                component_vectors
                + component_indices
                + metric_vectors
                + transfer_and_owner_plan
                + carrier_and_mode_metadata
            )
            runtime.check_projected(
                "v21_common_setup_preallocation", projected_bytes
            )
            runtime.marker(
                "v21_common_setup_preallocation_gate",
                {
                    "projected_bytes": int(projected_bytes),
                    "p6": p6_pre_facts,
                    "p4": p4_pre_facts,
                    "mode_count": port_count,
                    "formula": {
                        "component_vectors": "4*(N6_storage+N4_storage)*16*8",
                        "component_indices": "4*(N6_storage+N4_storage)*4*8",
                        "metric_vectors": "2*N6_storage*16*8",
                        "transfer_and_owner_plan": "256MiB",
                        "carrier_and_mode_metadata": "64MiB+mode_count*16*8",
                    },
                    "counts": {
                        "p6_storage_rows": p6_storage_rows,
                        "p4_storage_rows": p4_storage_rows,
                        "port_count": port_count,
                    },
                    "mesh_axis_cell_counts": list(
                        cfg.mesh_axis_cell_counts_requested or ()
                    ),
                    "source": "live_FE_MPC_before_physical_action_build",
                    "strict_upper_bound": False,
                },
            )
        common = _build_common(
            runtime, cfg, prebuilt_levels=prebuilt_levels
        )
        # The common builder now owns the FE/MPC levels.  Dropping this outer
        # alias avoids a duplicate mesh graph during form/condensation setup.
        prebuilt_levels = None
        if evidence_prefix == "v21":
            # Bind the checker to the exact ordered manifest used by the live
            # degree-6 carrier.  The mode digest alone is not enough: a
            # mutually-consistent but reordered manifest could otherwise pass
            # the two summary identity fields.
            mode_carrier = common["fine"]["dtn_action"].carrier
            mode_manifest_bytes = mode_carrier.mode_manifest_bytes
            mode_manifest_sha256 = mode_carrier.mode_manifest_sha256
            if mode_manifest_sha256 != str(common["fine"]["mode_sha256"]):
                raise ValueError(
                    "V21 ordered mode manifest differs from the live mode identity"
                )
            mode_manifest_path = directory / "v21_ordered_mode_manifest.json"
            mode_manifest_path.write_bytes(mode_manifest_bytes)
            mode_manifest = json.loads(mode_manifest_bytes.decode("utf-8"))
            summary["mode_manifest"] = {
                "schema": mode_manifest.get("schema"),
                "path": str(mode_manifest_path),
                "sha256": hashlib.sha256(mode_manifest_bytes).hexdigest(),
                "mode_sha256": mode_manifest_sha256,
                "mode_count": int(mode_manifest.get("mode_count", -1)),
            }
            runtime.marker("v21_ordered_mode_manifest_complete", summary["mode_manifest"])

            from src.geometry.v21_frozen_plan import audit_v21_mesh_identity

            geometry_payload = (
                resolved_payload.get("derived", {})
                .get("v21_identity", {})
                .get("geometry_entity_payload")
            )
            geometry_audit = audit_v21_mesh_identity(
                common["levels"]["mesh_data"],
                cfg,
                geometry_payload=geometry_payload,
            )
            geometry_audit_path = directory / "v21_geometry_audit.json"
            _write_json(geometry_audit_path, geometry_audit)
            summary["geometry_audit"] = {
                "schema": geometry_audit["schema"],
                "path": str(geometry_audit_path),
                "sha256": hashlib.sha256(geometry_audit_path.read_bytes()).hexdigest(),
                "variant": geometry_audit["variant"],
                "geometry_identity": geometry_audit["geometry_identity"],
                "actual_axis_cell_counts": geometry_audit["actual_axis_cell_counts"],
                "owned_cell_count": geometry_audit["owned_cell_count"],
                "notch_candidate_count": geometry_audit["notch_candidate_count"],
                "notch_changed_cells": geometry_audit["notch"].get("changed_cells"),
                "material_layout_sha256": geometry_audit["material_layout_sha256"],
                "geometry_entity_sha256": geometry_audit["geometry_entity_sha256"],
            }
            runtime.marker("v21_actual_mesh_material_entity_audit_complete", summary["geometry_audit"])
        if derive_live_space_identity:
            p6_port_count = int(len(common["fine"]["dtn_action"].carrier.entries))
            p4_port_count = int(len(common["p4"]["dtn_action"].carrier.entries))
            expected_space_counts = tuple(int(value) for value in p6_pre_counts[:3]) + (
                p6_port_count,
            )
            p4_counts = tuple(int(value) for value in p4_pre_counts[:3]) + (
                p4_port_count,
            )
            expected_space_facts = dict(p6_pre_facts)
            expected_space_facts.update(
                {
                    "appended_rows": p6_port_count,
                    "expected_space_counts": list(expected_space_counts),
                    "appended_rows_source": "live_fine_dtn_carrier_entries",
                }
            )
            p4_facts = dict(p4_pre_facts)
            p4_facts.update(
                {
                    "appended_rows": p4_port_count,
                    "expected_space_counts": list(p4_counts),
                    "appended_rows_source": "live_p4_dtn_carrier_entries",
                }
            )
            summary["actual_dimension_identity"] = {
                "p6": expected_space_facts,
                "p4": p4_facts,
                "p4_expected_space_counts": list(p4_counts),
                "geometry_semantic_identity": resolved_payload.get(
                    "derived", {}
                ).get("v21_identity"),
                "source": "live_FE_MPC_and_cell_interior_collection",
            }
            runtime.marker(
                "v21_actual_dimension_identity_complete",
                summary["actual_dimension_identity"],
            )
        form_cache_policy = (
            "v21_reuse_all_qualified"
            if evidence_prefix == "v21"
            else "v20_exclude_old_family"
        )
        prepared, prepared_facts = prepare_dual_condensed_forms(
            runtime, common, cache_policy=form_cache_policy
        )
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
                evidence_prefix=evidence_prefix,
                expected_space_counts=expected_space_counts,
                expected_space_facts=expected_space_facts,
                rhs_identity_policy=rhs_identity_policy,
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
                predecessor=(
                    dict(predecessor_by_stage.get(stage, {}))
                    if predecessor_by_stage is not None
                    else {
                        "accepted_v19": "physical_p6_trace_p4_condensed_balh_v19",
                        "original_only": True,
                        "old_notch": "USER_CLOSED",
                        "old_ledger": runtime.shared_budget,
                    }
                ),
                stack_factory=stack_factory,
                outer_adapter_factory=outer_factory,
                release_after_final_residual=True,
                official_jit_options=prepared_facts["jit_options"],
                reference_mode=reference_mode_by_stage.get(stage, "required"),
                notch_override=notch_by_stage.get(stage),
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
        prebuilt_levels = None
        if runtime is not None:
            try:
                runtime.set_phase("cleanup")
                if common is not None:
                    _destroy_common(common, runtime)
                runtime.sample(f"{evidence_prefix}_post_cleanup")
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
        if restore_summary_schema:
            # The shared V14 record contains its own schema and is merged into
            # this top-level worker summary above.  Only the opt-in V21 path
            # restores the adapter's public schema; the historical V20 route
            # keeps its existing write contract byte-for-byte.
            summary["schema"] = summary_schema
        _write_json(
            directory / summary_filename, summary
        )
        if runtime is not None:
            runtime.marker(f"{evidence_prefix}_worker_complete", summary)
    return {
        "passed": bool(summary["stage_pass"]),
        "errors": []
        if summary["stage_pass"]
        else [str(summary.get("error", summary["status"]))],
        "summary": summary,
        "numerical_output_directory": str(directory / "numerical_output"),
    }

def run_physical_dual_cell_condensed_lowmem_v20(
    resolved_payload, run_directory, *, source_sha
):
    """Run the historical V20 Y3 original with its unchanged contract."""

    return _run_physical_dual_cell_condensed_lowmem(
        resolved_payload, run_directory, source_sha=source_sha
    )


__all__ = [
    "_run_physical_dual_cell_condensed_lowmem",
    "run_physical_dual_cell_condensed_lowmem_v20",
]
