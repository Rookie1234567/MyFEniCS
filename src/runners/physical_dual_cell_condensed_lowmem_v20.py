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
import time
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from src.io.physical_intermediate_profile import (
    LOWMEM_DUAL_CELL_CONDENSED_PROFILE,
    profile_facts,
)


_V22_BOUND_B_IDENTITY = {
    "n6": 667152,
    "n4": 201520,
    "p6_local_dimension": 882,
    "p6_interior_dimension": 450,
    "p6_trace_dimension": 432,
    "p6_raw_class_count": 12,
    "p6_oriented_class_count": 26,
    "p6_port_count": 80,
    "axis_cell_counts": (9, 5, 22),
    "surface_cells_per_side": 45,
}
_V22_BALANCED_KERNEL_TEMPORARY_BYTES = 1813760


def _v22_direct_term_payload_upper_bound(
    carrier, *, scalar_bytes: int, index_bytes: int
) -> dict[str, int | str | bool]:
    """Split resident direct maps from their bounded construction workspace.

    ``consume`` first normalizes carrier rows/values, ``P6CellCondensedAction``
    normalizes those direct terms again, and ``_prepare_direct_terms`` retains
    only the concatenated original/active maps.  Count only the existing
    carrier shapes here; the carrier itself remains common inventory.  The
    resident ledger is the two final original/active row/value sets.  A
    separate four-set shape upper bound covers construction-time normalized
    and parts arrays; it is checked against the existing 128 MiB p6 action
    workspace and is not added to the resident inventory.  This is a payload
    bound, not an RSS claim or a claim that every ``asarray`` path copies.
    """

    row_count = 0
    value_count = 0
    for entry_index, entry in enumerate(getattr(carrier, "entries", ())):
        for rows_name, values_name in (
            ("coupling_rows", "coupling_values"),
            ("projection_rows", "projection_values"),
        ):
            rows = np.asarray(getattr(entry, rows_name)).reshape(-1)
            values = np.asarray(getattr(entry, values_name)).reshape(-1)
            if rows.size != values.size:
                raise ValueError(
                    "V22 carrier row/value shape mismatch at entry "
                    f"{entry_index} ({rows_name})"
                )
            row_count += int(rows.size)
            value_count += int(values.size)

    resident_one_payload = (
        row_count * int(index_bytes) + value_count * int(scalar_bytes)
    )
    temporary_one_payload = (
        row_count * max(np.dtype(np.int64).itemsize, int(index_bytes))
        + value_count * int(scalar_bytes)
    )
    return {
        "carrier_row_count": int(row_count),
        "carrier_value_count": int(value_count),
        "resident_payload_bytes": int(2 * resident_one_payload),
        "temporary_payload_upper_bytes": int(4 * temporary_one_payload),
        "resident_formula": "2*(carrier_rows*index+carrier_values*scalar)",
        "temporary_formula": "4*(carrier_rows*max(int64,index)+carrier_values*scalar)",
        "temporary_window_bytes": 128 << 20,
        "temporary_within_existing_window": True,
        "temporary_counted_in_future_inventory": False,
        "classification": "derived_resident_payload_plus_bounded_construction_workspace",
    }


def v22_capacity_context(
    common: Mapping[str, object],
    *,
    cfg=None,
    p6_space_facts: Mapping[str, object],
    p4_metadata: Mapping[str, object],
) -> dict:
    """Derive the fixed-B future ledger from live common/class metadata.

    This is deliberately a small binding function, not a second allocation
    auditor.  The class payload and setup workspace are the formulas already
    used by ``build_unconstrained_assembly_time_condensation``.  Carrier
    counts, p4 ``Bi`` payload, and FE/MPC dimensions are read from the objects
    already built for this run; no future p6 arrays are constructed here.
    """

    if cfg is None:
        cfg = common["cfg"]
    if not isinstance(p6_space_facts, Mapping):
        raise TypeError("V22 requires live p6 FE/MPC space facts")
    if not isinstance(p4_metadata, Mapping):
        raise TypeError("V22 requires assembled p4 capacity metadata")

    fine_carrier = common["fine"]["dtn_action"].carrier
    p4_carrier = common["p4"]["dtn_action"].carrier
    n6 = int(fine_carrier.global_rows)
    n4 = int(p4_carrier.global_rows)
    port_count = int(len(fine_carrier.entries))
    if n6 != _V22_BOUND_B_IDENTITY["n6"] or n4 != _V22_BOUND_B_IDENTITY["n4"]:
        raise ValueError("V22 live carrier rows do not match the frozen original-B identity")
    if port_count != _V22_BOUND_B_IDENTITY["p6_port_count"]:
        raise ValueError("V22 live p6 carrier port count does not match original B")

    axis_counts = tuple(
        int(value) for value in (cfg.mesh_axis_cell_counts_requested or ())
    )
    if axis_counts != _V22_BOUND_B_IDENTITY["axis_cell_counts"]:
        raise ValueError("V22 live mesh cell counts do not match the frozen original B")
    cell_count = int(np.prod(axis_counts, dtype=np.int64))
    surface_cells_per_side = int(axis_counts[0] * axis_counts[1])
    if surface_cells_per_side != _V22_BOUND_B_IDENTITY["surface_cells_per_side"]:
        raise ValueError("V22 live boundary cell count does not match original B")

    side_counts: dict[str, int] = {}
    for entry in fine_carrier.entries:
        identity = getattr(entry, "mode_identity", None)
        if not isinstance(identity, Mapping) or not identity.get("side"):
            raise ValueError("V22 p6 carrier entry has no bound side identity")
        side = str(identity["side"])
        side_counts[side] = side_counts.get(side, 0) + 1
    if set(side_counts) != {"top", "bottom"} or sum(side_counts.values()) != port_count:
        raise ValueError("V22 p6 carrier sides are not the two bound physical sides")

    full_rows = int(p6_space_facts.get("full_rows", -1))
    trace_rows = int(p6_space_facts.get("trace_rows", -1))
    active_rows = int(p6_space_facts.get("active_rows", -1))
    slave_rows = int(p6_space_facts.get("slave_rows", -1))
    slave_master_entry_count = int(
        p6_space_facts.get("slave_master_entry_count", -1)
    )
    appended_rows = int(p6_space_facts.get("appended_rows", -1))
    if (
        (full_rows, appended_rows) != (n6, port_count)
        or trace_rows <= 0
        or active_rows <= 0
        or slave_rows < 0
        or slave_master_entry_count < 0
        or active_rows + slave_rows != trace_rows
    ):
        raise ValueError("V22 p6 FE/MPC facts do not close against the live carrier")
    p6_local_dimensions = tuple(
        int(p6_space_facts.get(key, -1))
        for key in (
            "local_tensor_dimension",
            "local_interior_dimension",
            "local_trace_dimension",
        )
    )
    if p6_local_dimensions != (
        _V22_BOUND_B_IDENTITY["p6_local_dimension"],
        _V22_BOUND_B_IDENTITY["p6_interior_dimension"],
        _V22_BOUND_B_IDENTITY["p6_trace_dimension"],
    ):
        raise ValueError(
            "V22 live p6 local space dimensions do not match original B: "
            f"{p6_local_dimensions!r}"
        )
    p4_class_counts = tuple(
        int(p4_metadata.get(key, -1))
        for key in ("p4_raw_class_count", "p4_oriented_class_count")
    )
    if p4_class_counts != (
        _V22_BOUND_B_IDENTITY["p6_raw_class_count"],
        _V22_BOUND_B_IDENTITY["p6_oriented_class_count"],
    ):
        raise ValueError(
            "V22 p4 build_audit class identity does not match original B: "
            f"{p4_class_counts!r}"
        )
    retained_rows = active_rows + port_count

    from src.runners.physical_p4_schur_v14 import (
        _v14_balanced_apply_workspace_bytes,
        _v14_balanced_h6_setup_facts,
        _v14_outer_krylov_workspace_bytes,
    )
    from src.runners.physical_retained_outer_adapter import (
        _retained_outer_scratch_workspace_bytes,
    )
    from src.solvers.hcurl_assembly_time_condensation import (
        assembly_time_condensation_capacity_facts,
    )
    from petsc4py import PETSc

    scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
    index_bytes = int(np.dtype(PETSc.IntType).itemsize)
    real_bytes = int(np.dtype(np.float64).itemsize)
    if (scalar_bytes, index_bytes, real_bytes) != (16, 4, 8):
        raise ValueError("V22 B capacity formulas require the qualified complex128/int32 ABI")

    p6_class_capacity = assembly_time_condensation_capacity_facts(
        dimension=_V22_BOUND_B_IDENTITY["p6_local_dimension"],
        interior_dimension=_V22_BOUND_B_IDENTITY["p6_interior_dimension"],
        trace_dimension=_V22_BOUND_B_IDENTITY["p6_trace_dimension"],
        raw_class_count=_V22_BOUND_B_IDENTITY["p6_raw_class_count"],
        oriented_class_count=_V22_BOUND_B_IDENTITY["p6_oriented_class_count"],
        identity_class_count=1,
        retain_local_schur=True,
        scalar_bytes=scalar_bytes,
        index_bytes=index_bytes,
        real_bytes=real_bytes,
    )
    h6_facts = _v14_balanced_h6_setup_facts(common)
    common_fine_payload = int(h6_facts["component_payload_bytes"])
    h6_setup_estimate = int(h6_facts["setup_estimate_bytes"])
    # The common fine component remains resident while the new H6 action,
    # kernel, and vectors are constructed.  The qualified setup estimate is
    # therefore charged in full; the common payload is retained only as an
    # identity/source fact, never subtracted from the future inventory.
    h6_future_inventory = h6_setup_estimate

    # The p6 action owns H_p/Hhat and the per-port Bi/Di/Bt/Dt/Bhat/Dhat/XiB
    # payloads.  Sum k^2 using the live top/bottom carrier counts; this is a
    # shape-derived upper estimate for Hlocal without assuming every cell has
    # an 80-port block.  Each side's arrays exist for every boundary cell, so
    # the per-side payload is multiplied by the live 9*5 surface count.
    # Existing carrier row/value arrays are common-cache inventory and are
    # intentionally not charged again here; their newly-created direct-term
    # copies are bounded separately below.
    interior = _V22_BOUND_B_IDENTITY["p6_interior_dimension"]
    trace = _V22_BOUND_B_IDENTITY["p6_trace_dimension"]
    per_side_port_payload = sum(
        count * (3 * interior + 4 * trace) * scalar_bytes
        + count * index_bytes
        + count * count * scalar_bytes
        for count in side_counts.values()
    )
    p6_port_terms_bytes = (
        2 * port_count * port_count * scalar_bytes
        + surface_cells_per_side * per_side_port_payload
    )
    p6_mapping_bytes = cell_count * (
        (interior + 2 * trace) * index_bytes
        + trace * scalar_bytes
        + (2 * trace + 1) * index_bytes
    ) + surface_cells_per_side * port_count * index_bytes
    p6_global_trace_map_bytes = (
        (trace_rows + active_rows) * index_bytes
        + (active_rows + slave_master_entry_count) * (index_bytes + scalar_bytes)
    )
    p6_direct_terms = _v22_direct_term_payload_upper_bound(
        fine_carrier, scalar_bytes=scalar_bytes, index_bytes=index_bytes
    )
    if int(p6_direct_terms["temporary_payload_upper_bytes"]) > int(
        p6_direct_terms["temporary_window_bytes"]
    ):
        raise ValueError(
            "V22 direct-term construction upper bound exceeds the existing "
            "128 MiB p6 action workspace"
        )

    xi_b_bytes = p4_metadata.get("xiB_payload_estimate_bytes")
    if type(xi_b_bytes) is not int or xi_b_bytes < 0:
        raise ValueError("V22 p4 metadata must provide actual Bi.nbytes for XiB estimate")

    bal_workspace = _v14_balanced_apply_workspace_bytes(
        n6,
        n4,
        _V22_BALANCED_KERNEL_TEMPORARY_BYTES,
    )
    p6_setup_workspace = int(p6_class_capacity["workspace_bytes_upper"])
    p6_scratch = _retained_outer_scratch_workspace_bytes(n6, retained_rows)
    outer_krylov = _v14_outer_krylov_workspace_bytes(retained_rows, restart=32)
    solve_workspace = bal_workspace + p6_scratch + outer_krylov
    return {
        "schema": "task039extra.v22.capacity-context.v2",
        "classification": "derived_pre_numeric_payload_estimates_live_RSS_separate",
        "identity": {
            "n6": n6,
            "n4": n4,
            "p6_port_count": port_count,
            "p6_side_port_counts": dict(sorted(side_counts.items())),
            "p6_full_rows": full_rows,
            "p6_trace_rows": trace_rows,
            "p6_active_trace_rows": active_rows,
            "p6_slave_rows": slave_rows,
            "p6_slave_master_entry_count": slave_master_entry_count,
            "p6_retained_rows": retained_rows,
            "p6_local_dimensions": {
                "local_tensor_dimension": p6_local_dimensions[0],
                "local_interior_dimension": p6_local_dimensions[1],
                "local_trace_dimension": p6_local_dimensions[2],
            },
            "p4_class_counts": {
                "raw": p4_class_counts[0],
                "oriented": p4_class_counts[1],
            },
            "mesh_axis_cell_counts": list(axis_counts),
            "owned_cell_count": cell_count,
            "surface_cells_per_side": surface_cells_per_side,
            "scalar_bytes": scalar_bytes,
            "index_bytes": index_bytes,
            "real_bytes": real_bytes,
        },
        "future_inventory_components": {
            "h6_field_and_mode_inventory_bytes": h6_future_inventory,
            "p6_retained_cache_inventory_bytes": int(
                p6_class_capacity["retained_numeric_bytes_upper"]
            ),
            "p6_port_terms_inventory_bytes": int(p6_port_terms_bytes),
            "p6_mapping_inventory_bytes": int(p6_mapping_bytes),
            "p6_global_trace_map_inventory_bytes": int(p6_global_trace_map_bytes),
            "p6_direct_term_resident_inventory_bytes": int(
                p6_direct_terms["resident_payload_bytes"]
            ),
            "p4_xib_recovery_inventory_bytes": int(xi_b_bytes),
        },
        "future_workspace_phases": {
            "h6_build": {
                "h6_build_workspace_bytes": 64 << 20,
            },
            "p6_setup_plus_bal_h": {
                "p6_setup_workspace_bytes": p6_setup_workspace,
                "bal_h_workspace_bytes": int(bal_workspace),
            },
            "p6_action_construction": {
                "p6_action_temporary_window_bytes": int(
                    p6_direct_terms["temporary_window_bytes"]
                ),
            },
            "outer_solve": {
                "bal_h_workspace_bytes": int(bal_workspace),
                "p6_full_scratch_workspace_bytes": int(p6_scratch),
                "outer_krylov_workspace_bytes": int(outer_krylov),
            },
        },
        "derived_sources": {
            "p6_class_capacity": dict(p6_class_capacity),
            "h6_setup_estimate": {
                **dict(h6_facts),
                "common_fine_payload_bytes_live_reference": common_fine_payload,
                "common_objects_remain_live_during_new_h6_setup": True,
                "future_inventory_bytes": h6_future_inventory,
                "classification": "derived_conservative_estimate_live_h6_gate_remains",
            },
            "p6_port_terms": {
                "formula": "2*ports^2*s+surface_cells_per_side*sum(side_ports*(3*i+4*t)*s+side_ports*index+side_ports^2*s)",
                "payload_only": True,
                "side_cell_count": surface_cells_per_side,
            },
            "p6_mapping": {
                "formula": "cells*((i+2*t)*index+t*s+(2*t+1)*index)+surface_cells_per_side*ports*index",
                "payload_only": True,
            },
            "p6_direct_terms": dict(p6_direct_terms),
            "p6_global_trace_map": {
                "formula": "(trace_rows+active_rows)*index+(active_rows+slave_master_entry_count)*(index+scalar)",
                "source": "live derive_condensed_space_identity trace/slave counts and existing MPC master-link lengths",
                "cache_identity_scatter_vectors_bytes": 0,
                "payload_only": True,
            },
            "p4_xib": {
                "formula": "sum(actual assembled p4 port_terms Bi.nbytes)",
                "payload_only": True,
                "source_metadata": dict(p4_metadata),
            },
            "balanced_workspace": {
                "formula": "40*n6*16+12*n4*16+kernel_temporary_bytes",
                "kernel_temporary_bytes": _V22_BALANCED_KERNEL_TEMPORARY_BYTES,
                "kernel_temporary_source": "qualified p6 positive kernel evidence; live H6 gate rechecks",
            },
            "solve_workspace": {
                "formula": "BAL+24*N6*16+84*Nret*16",
                "scratch_formula": "24*N6*16+10*Nret*16",
                "outer_formula": "74*Nret*16",
            },
        },
        "workspace_basis": {
            "runtime_pool_cap_is_runtime_owned": True,
            "simultaneous_setup_plus_bal_h_bytes": int(
                p6_setup_workspace + bal_workspace
            ),
            "outer_solve_workspace_bytes": int(solve_workspace),
            "rss_is_measured_separately": True,
        },
        "future_inventory_scope": {
            "h6_field_and_mode_inventory_bytes": "full derived H6 setup estimate; common fine remains live",
            "p6_retained_cache_inventory_bytes": "existing condensation class-shape formula; local LU/recovery/Schur plus shared identity",
            "p6_port_terms_inventory_bytes": "actual carrier port count and top/bottom side counts over each boundary cell; payload estimate",
            "p6_mapping_inventory_bytes": "actual 990 cells and existing p6 cell-map array shapes, including per-side port maps; payload estimate",
            "p6_global_trace_map_inventory_bytes": "trace_original/active_original plus expansion_by_original IDs/values from live trace rows and existing MPC master-link lengths; payload estimate",
            "p6_direct_term_resident_inventory_bytes": "two resident original/active PETSc index/value map sets from carrier row/value lengths; source carrier excluded",
            "p4_xib_recovery_inventory_bytes": "actual assembled p4 port_terms Bi.nbytes; XiB shape estimate",
        },
    }


def _v22_mumps_capacity_failure(native_state: Mapping[str, object]):
    """Recognize only explicit native MUMPS numeric capacity codes."""

    if native_state.get("saved") is not True:
        return None
    raw = native_state.get("numeric_raw")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("infog"), Mapping):
        return None
    infog = raw["infog"]
    code = infog.get("1")
    if type(code) is not int or code not in {-9, -19}:
        return None
    return {
        "native_error_code_infog1": int(code),
        "native_infog": dict(infog),
        "evidence": "v22_numeric_native_facts.json",
        "retry": False,
    }


def _v22_capacity_callbacks(
    *,
    runtime,
    common: Mapping[str, object],
    cfg,
    final_space_facts: Mapping[str, object],
    p4_metadata: Mapping[str, object],
    directory: Path,
    source_sha: str,
    summary: dict[str, object],
    native_observation_state: dict[str, object],
    write_json,
):
    """Build the production V22 factor callbacks from final live facts.

    The FE identity walk intentionally starts with ``appended_rows=0``.  This
    shared callback boundary accepts only the post-carrier fact copy so the
    capacity context cannot accidentally freeze that pre-carrier value.
    """

    if not isinstance(final_space_facts, Mapping) or not final_space_facts:
        raise RuntimeError("V22 requires non-empty final p6 space facts")
    carrier_count = len(common["fine"]["dtn_action"].carrier.entries)
    if int(final_space_facts.get("appended_rows", -1)) != int(carrier_count):
        raise RuntimeError(
            "V22 final p6 space facts are not bound to the live carrier"
        )

    from src.runners.physical_p4_schur_v14 import (
        V14ResourceStop,
        _factor_inventory_components,
        _mumps_memory_observation,
    )
    from src.solvers.mumps_capacity_budget_v22 import capacity_budget_v22

    def build_capacity_request(policy_facts, _factor):
        resource = policy_facts.get("symbolic_resource")
        if not isinstance(resource, Mapping):
            raise RuntimeError("V22 symbolic resource sample is missing")
        inventory_cap = runtime.inventory_cap
        if inventory_cap is None:
            raise RuntimeError("V22 requires a finite inventory cap")
        capacity_context = v22_capacity_context(
            common,
            cfg=cfg,
            p6_space_facts=final_space_facts,
            p4_metadata=p4_metadata,
        )
        # This is frozen before any post-numeric RSS or allocated-memory gate.
        write_json(directory / "v22_capacity_context.json", capacity_context)
        summary["capacity_trial"] = dict(capacity_context)
        budget = capacity_budget_v22(
            launch_cap_bytes=int(resource["launch_cap_bytes"]),
            inventory_cap_bytes=int(inventory_cap),
            current_tree_rss_bytes=int(resource["rss_bytes"]),
            current_inventory_bytes=int(runtime.inventory_used_bytes),
            future_inventory_components=dict(
                capacity_context["future_inventory_components"]
            ),
            future_workspace_phases=dict(
                capacity_context["future_workspace_phases"]
            ),
            numeric_untouched_pool_bytes=max(
                0,
                int(runtime.workspace_cap) - int(runtime.workspace_live_bytes),
            ),
            workspace_pool_cap_bytes=int(runtime.workspace_cap),
        )
        budget["workspace_pool_source"] = "runtime.workspace_cap"
        budget["capacity_context_schema"] = capacity_context["schema"]
        runtime.marker("v22_capacity_pre_numeric_frozen", budget)
        if budget["status"] != "capacity_available":
            raise V14ResourceStop(
                "V22 capacity unavailable before numeric: "
                + json.dumps(budget, sort_keys=True)
            )
        return {
            "policy": "CAPACITY_CONTROLLED_LOCAL_MUMPS_V22",
            "requested_memory_limit_mb": int(budget["icntl23_mb"]),
            "capacity_budget": budget,
        }

    def observe_numeric(observation):
        record = dict(observation)
        raw = record.get("numeric_raw")
        infog = raw.get("infog", {}) if isinstance(raw, Mapping) else {}
        native = dict(infog) if isinstance(infog, Mapping) else {}
        native_record = {
            "schema": "task039extra.v22.native-factor-observation.v1",
            "source_sha": source_sha,
            "saved_at_utc_ns": time.time_ns(),
            "observation": dict(record),
            "native_infog": native,
            "matrix_identity_before_factor": record.get(
                "matrix_identity_before_factor"
            ),
            "matrix_identity_after_factor": None,
            "matrix_identity_after_factor_status": record.get(
                "matrix_identity_after_factor_status",
                "pending_post_factor_hash",
            ),
        }
        write_json(directory / "v22_numeric_native_facts.json", native_record)
        native_observation_state.update(
            {"saved": True, "numeric_raw": raw, "native_infog": native}
        )
        record["native_infog"] = native
        try:
            record["numeric_resource_observer"] = runtime.sample(
                "v22_numeric_observer", enforce=False
            )
        except Exception as sample_error:
            record["numeric_resource_observer"] = {
                "status": "observation_failed",
                "error": {
                    "type": type(sample_error).__name__,
                    "message": str(sample_error),
                },
            }
        write_json(directory / "v22_numeric_observation.json", record)
        runtime.marker("v22_numeric_observed_before_post_gate", record)

    def continuation_gate(facts):
        budget = facts["memory_request"]["capacity_budget"]
        native = _mumps_memory_observation(facts)
        allocated = int(native["infog19_allocated_bytes_upper"])
        if allocated > int(budget["continuation_max_allocated_bytes"]):
            runtime.marker(
                "v22_continuation_allocated_gate_failed",
                {
                    "allocated_upper_bytes": allocated,
                    "continuation_max_allocated_bytes": budget[
                        "continuation_max_allocated_bytes"
                    ],
                    "native_used_upper_bytes": int(
                        native["infog22_used_bytes_upper"]
                    ),
                },
            )
            raise V14ResourceStop(
                "V22 native allocated factor exceeds frozen continuation ceiling"
            )
        components = _factor_inventory_components(facts)
        components["matrix_payload_bytes"] = 0
        future_inventory = int(budget["future_inventory_bytes"])
        runtime.check_inventory_projected(
            str(facts.get("label")), sum(components.values()) + future_inventory
        )
        resource = runtime.sample("v22_continuation_resource_gate", enforce=True)
        projected_tree = (
            int(resource["rss_bytes"])
            + future_inventory
            + int(budget["workspace_pool_cap_bytes"])
        )
        gate_facts = {
            "allocated_upper_bytes": allocated,
            "used_upper_bytes": int(native["infog22_used_bytes_upper"]),
            "future_inventory_bytes": future_inventory,
            "workspace_pool_cap_bytes": int(budget["workspace_pool_cap_bytes"]),
            "rss_bytes": int(resource["rss_bytes"]),
            "projected_tree_bytes": projected_tree,
            "launch_cap_bytes": int(resource["launch_cap_bytes"]),
            "gate": "native_allocated_then_live_tree_before_post_numeric_gate",
        }
        runtime.marker("v22_continuation_capacity_gate", gate_facts)
        if projected_tree >= int(resource["launch_cap_bytes"]):
            raise V14ResourceStop(
                "V22 continuation projected tree reaches launch cap"
            )

    return build_capacity_request, observe_numeric, continuation_gate


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
    reuse_qualified_jit=False,
    write_ordered_mode_manifest=False,
    write_geometry_audit=False,
    save_complete_field_packet=None,
    capacity_trial=False,
    capacity_context=None,
):
    """Run one parameterized dual-condensed robustness stage."""

    if save_complete_field_packet is None:
        # Preserve the historical V20/V21 packet contract at this shared
        # entry point.  New profiles must opt in explicitly; the resolved
        # boolean is passed to the adapter so this wiring is testable.
        save_complete_field_packet = evidence_prefix in {"v20", "v21"}
    else:
        save_complete_field_packet = bool(save_complete_field_packet)
    capacity_trial = bool(capacity_trial)
    # V22 context is intentionally derived after the live common/FE objects
    # and assembled p4 port metadata exist.  A caller-supplied static context
    # is not an admissible substitute for those identities.
    if capacity_trial and capacity_context is not None:
        raise ValueError("V22 capacity context must be derived from live metadata")
    capacity_context = None

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
    p4_capacity_metadata: dict[str, object] = {}
    stack_factory = outer_factory = None
    prebuilt_levels = None
    handlers = {}
    factor_memory_request_builder = None
    factor_numeric_observer = None
    factor_post_numeric_gate = None
    native_observation_state: dict[str, object] = {"saved": False}
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
        p6_pre_facts = None
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
        if write_ordered_mode_manifest:
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
            mode_manifest_path = directory / f"{evidence_prefix}_ordered_mode_manifest.json"
            mode_manifest_path.write_bytes(mode_manifest_bytes)
            mode_manifest = json.loads(mode_manifest_bytes.decode("utf-8"))
            summary["mode_manifest"] = {
                "schema": mode_manifest.get("schema"),
                "path": str(mode_manifest_path),
                "sha256": hashlib.sha256(mode_manifest_bytes).hexdigest(),
                "mode_sha256": mode_manifest_sha256,
                "mode_count": int(mode_manifest.get("mode_count", -1)),
            }
            runtime.marker(
                f"{evidence_prefix}_ordered_mode_manifest_complete",
                summary["mode_manifest"],
            )

        if write_geometry_audit:
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
            geometry_audit_path = directory / f"{evidence_prefix}_geometry_audit.json"
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
            runtime.marker(
                f"{evidence_prefix}_actual_mesh_material_entity_audit_complete",
                summary["geometry_audit"],
            )
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
            if reuse_qualified_jit
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

        if capacity_trial:
            if not isinstance(expected_space_facts, Mapping) or not expected_space_facts:
                raise RuntimeError(
                    "V22 final p6 space facts were not bound before numeric"
                )
            (
                factor_memory_request_builder,
                factor_numeric_observer,
                factor_post_numeric_gate,
            ) = _v22_capacity_callbacks(
                runtime=runtime,
                common=common,
                cfg=cfg,
                final_space_facts=expected_space_facts,
                p4_metadata=p4_capacity_metadata,
                directory=directory,
                source_sha=source_sha,
                summary=summary,
                native_observation_state=native_observation_state,
                write_json=_write_json,
            )

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
                factor_memory_request_builder=factor_memory_request_builder,
                factor_numeric_observer=factor_numeric_observer,
                factor_post_numeric_gate=factor_post_numeric_gate,
                capacity_metadata_callback=(
                    p4_capacity_metadata.update if capacity_trial else None
                ),
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
                save_complete_field_packet=save_complete_field_packet,
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
        native_capacity_failure = (
            _v22_mumps_capacity_failure(native_observation_state)
            if capacity_trial
            else None
        )
        error = {"type": type(exc).__name__, "message": str(exc)}
        if native_capacity_failure is not None:
            # The native record was atomically saved by the observer before
            # this exception reached the shared worker boundary.  Preserve
            # the original exception and INFOG evidence while classifying only
            # the explicit V22 MUMPS capacity result as a controlled stop.
            summary.update(
                status="CONTROLLED_STOP",
                stage_pass=False,
                result_classification="MUMPS_CAPACITY_CONTROLLED_STOP",
                error=error,
                mumps_capacity_failure=native_capacity_failure,
            )
        else:
            # No native -9/-19 evidence means this remains an ordinary worker
            # error; V22 must not infer a capacity cause from a Python error.
            summary.update(
                status="FAILED",
                stage_pass=False,
                result_classification="WORKER_FAILED",
                error=error,
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
