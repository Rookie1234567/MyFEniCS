# MPI collective/callback/cleanup catches synchronize third-party exceptions across ranks.
# ruff: noqa: BLE001
"""Frozen S3b pilot contract and current-layout source identity helpers.

The numerical S3b orchestration remains outside this module.  This file holds
the reviewed route identity, immutable B1 material-copy and source-identity
helpers, and the two Gate decisions used by later runner wiring.
"""

from __future__ import annotations

import cmath
import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_layer_block import build_layer_sweep_action, build_real_layer_labels
from .static_local_schur_action import materialize_research_explicit_fine_matrix

S3B_ROUTE_ID = "V9_E_S3B"
S3B_SCHEMA = "task040.v9_e.s3b_structured_background.v1"
S3B_METHOD = "task040_v9_e_s3b_structured_background"

S3B_EXTERNAL_SOURCE_LABEL = "external_dtn_coupling"
S3B_EXTERNAL_SOURCE_SEED = 769
S3B_EXTERNAL_SOURCE_COLUMN = 177
S3B_EXTERNAL_SOURCE_SIGN = -1.0

S3B_MPI_SIZE = 8
S3B_FGMRES_RESTART = 64
S3B_FGMRES_INITIAL_MAX_IT = 64
S3B_FGMRES_CONDITIONAL_TOTAL_IT = 256
S3B_CANDIDATE_R64_LIMIT = 0.5
S3B_REQUIRED_J1_IMPROVEMENT = 4.0
S3B_CANDIDATE_R256_LIMIT = 1.0e-6

S3B_RSS_HARD_BYTES = 45 * 2**30
S3B_SWAP_LIMIT_BYTES = 0
S3B_WALL_CAP_SECONDS = 10800

S3B_EXPECTED_ACTIVE_ROWS = 8424
S3B_EXPECTED_MODE_COUNT = 18
S3B_EXPECTED_ROWS_PER_MODE = 468
S3B_MAX_LOCAL_ROWS = 1024

S3B_NEXT_CONDITIONAL_256 = "V9_E_S3B_CONDITIONAL_256"
S3B_NEXT_FIVE_SOURCE_BOTTOM = "V9_E_S3B_FIVE_SOURCE_BOTTOM"
S3B_NEXT_FIXED_LOR = "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR"

S3B_INITIAL_POSITIVE = "S3B_INITIAL_POSITIVE"
S3B_INITIAL_UNSTABLE = "S3B_INITIAL_UNSTABLE"
S3B_INITIAL_RESOURCE_STOP = "S3B_INITIAL_RESOURCE_STOP"
S3B_INITIAL_NO_SIGNAL = "S3B_INITIAL_NO_SIGNAL"
S3B_CONDITIONAL_PASS = "S3B_CONDITIONAL_256_PASS"
S3B_CONDITIONAL_UNSTABLE = "S3B_CONDITIONAL_256_UNSTABLE"
S3B_CONDITIONAL_RESOURCE_STOP = "S3B_CONDITIONAL_256_RESOURCE_STOP"
S3B_CONDITIONAL_NOT_QUALIFIED = "S3B_CONDITIONAL_256_NOT_QUALIFIED"


__all__ = (
    "S3B_CANDIDATE_R64_LIMIT",
    "S3B_CANDIDATE_R256_LIMIT",
    "S3B_CONDITIONAL_NOT_QUALIFIED",
    "S3B_CONDITIONAL_PASS",
    "S3B_CONDITIONAL_RESOURCE_STOP",
    "S3B_CONDITIONAL_UNSTABLE",
    "S3B_EXPECTED_ACTIVE_ROWS",
    "S3B_EXPECTED_MODE_COUNT",
    "S3B_EXPECTED_ROWS_PER_MODE",
    "S3B_EXTERNAL_SOURCE_COLUMN",
    "S3B_EXTERNAL_SOURCE_LABEL",
    "S3B_EXTERNAL_SOURCE_SEED",
    "S3B_EXTERNAL_SOURCE_SIGN",
    "S3B_FGMRES_CONDITIONAL_TOTAL_IT",
    "S3B_FGMRES_INITIAL_MAX_IT",
    "S3B_FGMRES_RESTART",
    "S3B_INITIAL_NO_SIGNAL",
    "S3B_INITIAL_POSITIVE",
    "S3B_INITIAL_RESOURCE_STOP",
    "S3B_INITIAL_UNSTABLE",
    "S3B_MAX_LOCAL_ROWS",
    "S3B_METHOD",
    "S3B_MPI_SIZE",
    "S3B_NEXT_CONDITIONAL_256",
    "S3B_NEXT_FIVE_SOURCE_BOTTOM",
    "S3B_NEXT_FIXED_LOR",
    "S3B_REQUIRED_J1_IMPROVEMENT",
    "S3B_ROUTE_ID",
    "S3B_RSS_HARD_BYTES",
    "S3B_SCHEMA",
    "S3B_SWAP_LIMIT_BYTES",
    "S3B_WALL_CAP_SECONDS",
    "S3CurrentLayoutSourceFactory",
    "S3FixedRightFgmres",
    "adjudicate_s3_b1_conditional_gate",
    "adjudicate_s3_b1_initial_gate",
    "audit_s3_preconditioner_one_apply",
    "build_s3_b1_background_config",
    "build_s3_external_dtn_source",
    "build_s3_j1_baseline_action",
)


def _finite_complex(value: complex) -> bool:
    number = complex(value)
    return math.isfinite(number.real) and math.isfinite(number.imag)


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, (tuple, list)) or isinstance(right, (tuple, list)):
        if not isinstance(left, (tuple, list)) or not isinstance(right, (tuple, list)):
            return False
        return len(left) == len(right) and all(
            _same_value(item_left, item_right)
            for item_left, item_right in zip(left, right, strict=True)
        )
    try:
        result = left == right
    except Exception:
        return False
    return bool(result)


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def build_s3_b1_background_config(cfg: Any) -> tuple[Any, dict[str, Any]]:
    """Return the fixed B1 volume-average material copy and its audit.

    Only ``case_name``, ``n_air`` and ``n_grating`` are changed.  Geometry,
    mesh, substrate, boundary, and all other physical settings are inherited
    from the supplied target configuration.
    """

    try:
        n_air = complex(cfg.n_air)
        n_grating = complex(cfg.grating_index)
    except (AttributeError, TypeError, ValueError) as exc:
        raise TypeError("S3b B1 requires a configuration with finite indices") from exc
    eps_air = n_air**2
    eps_grating = n_grating**2
    eps_avg = (17.0 / 50.0) * eps_grating + (33.0 / 50.0) * eps_air
    if not all(_finite_complex(value) for value in (n_air, n_grating, eps_avg)):
        raise ValueError("S3b B1 material values must be finite")
    n_average = complex(cmath.sqrt(eps_avg))
    if not _finite_complex(n_average):
        raise ValueError("S3b B1 principal square root is nonfinite")
    relative_sqrt_error = abs(n_average**2 - eps_avg) / max(abs(eps_avg), 1.0e-300)
    if not math.isfinite(relative_sqrt_error) or relative_sqrt_error > 1.0e-12:
        raise ValueError(
            "S3b B1 principal square root does not reproduce the averaged permittivity"
        )

    background = replace(
        cfg,
        case_name=f"{cfg.case_name}__s3b_b1_background",
        n_air=n_average,
        n_grating=n_average,
    )
    changed_fields = []
    for field in fields(cfg):
        before = getattr(cfg, field.name)
        after = getattr(background, field.name)
        if not _same_value(before, after):
            changed_fields.append(field.name)
    if not changed_fields or not set(changed_fields).issubset(
        {"case_name", "n_air", "n_grating"}
    ):
        raise RuntimeError(
            "S3b B1 background copy changed fields outside case_name/n_air/n_grating"
        )
    if "case_name" not in changed_fields:
        raise RuntimeError("S3b B1 background copy did not change case_name")
    if not _same_value(background.n_substrate, cfg.n_substrate):
        raise RuntimeError("S3b B1 background copy changed n_substrate")

    audit = {
        "route": S3B_ROUTE_ID,
        "material_model": "volume_average",
        "volume_average_weights": {"grating": 17.0 / 50.0, "air": 33.0 / 50.0},
        "eps_air": _complex_pair(eps_air),
        "eps_grating": _complex_pair(eps_grating),
        "eps_avg": _complex_pair(eps_avg),
        "n_average": _complex_pair(n_average),
        "principal_complex_sqrt": True,
        "sqrt_relative_error": float(relative_sqrt_error),
        "additional_absorbing_shift": 0.0,
        "ordinary_defaults_changed": False,
        "n_substrate_unchanged": True,
        "changed_fields": list(changed_fields),
        "geometry_mesh_physics_fields_unchanged": True,
    }
    return background, audit


def _build_s3_external_dtn_source_vector(system: Any) -> tuple[Any, dict[str, Any]]:
    """Build the frozen source from the current target C column only."""

    from mpi4py import MPI

    fine_action = getattr(system, "fine_action", None)
    blocks = getattr(system, "blocks", None)
    coupling = getattr(blocks, "C", None)
    if fine_action is None or coupling is None:
        raise TypeError("S3b source requires system.fine_action and system.blocks.C")

    fine_shape = tuple(int(value) for value in fine_action.getSize())
    c_shape = tuple(int(value) for value in coupling.getSize())
    if fine_shape[0] != fine_shape[1]:
        raise ValueError(f"S3b target fine_action must be square, got {fine_shape}")
    if c_shape != (fine_shape[0], 296):
        raise ValueError(
            "S3b target C shape must be (fine rows, 296), "
            f"got {c_shape} for fine shape {fine_shape}"
        )
    fine_ownership = tuple(int(value) for value in fine_action.getOwnershipRange())
    c_ownership = tuple(int(value) for value in coupling.getOwnershipRange())
    if fine_ownership != c_ownership:
        raise ValueError(
            "S3b target fine_action and C active ownership differ: "
            f"{fine_ownership} != {c_ownership}"
        )

    comm = fine_action.getComm().tompi4py()
    coefficient = None
    source = None
    try:
        coefficient = coupling.createVecRight()
        coefficient_ownership = tuple(
            int(value) for value in coefficient.getOwnershipRange()
        )
        if coefficient.getSize() != 296:
            raise ValueError(
                "S3b C coefficient Vec must have global size 296, "
                f"got {coefficient.getSize()}"
            )
        coefficient.set(0.0)
        coefficient_start, coefficient_stop = coefficient_ownership
        if coefficient_start <= S3B_EXTERNAL_SOURCE_COLUMN < coefficient_stop:
            coefficient.getArray()[
                S3B_EXTERNAL_SOURCE_COLUMN - coefficient_start
            ] = 1.0 + 0.0j
        coefficient.assemble()
        coefficient_values = np.asarray(
            coefficient.getArray(readonly=True), dtype=np.complex128
        )
        local_bad_coefficient = bool(
            not np.isfinite(coefficient_values).all()
            or np.any(
                (coefficient_values != 0.0)
                & (coefficient_values != (1.0 + 0.0j))
            )
        )
        global_nonzero_count = int(
            comm.allreduce(
                int(np.count_nonzero(coefficient_values != 0.0)),
                op=MPI.SUM,
            )
        )
        global_unit_count = int(
            comm.allreduce(
                int(np.count_nonzero(coefficient_values == (1.0 + 0.0j))),
                op=MPI.SUM,
            )
        )
        any_bad_coefficient = bool(
            comm.allreduce(local_bad_coefficient, op=MPI.LOR)
        )
        if (
            any_bad_coefficient
            or global_nonzero_count != 1
            or global_unit_count != 1
        ):
            raise ValueError(
                "S3b C coefficient column does not contain exactly one global unit "
                f"entry: nonzero={global_nonzero_count}, unit={global_unit_count}"
            )

        source = coupling.createVecLeft()
        source.set(0.0)
        source_ownership = tuple(int(value) for value in source.getOwnershipRange())
        if source_ownership != fine_ownership:
            raise ValueError("S3b source ownership differs from target active ownership")
        coupling.mult(coefficient, source)
        source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        source_finite = bool(
            comm.allreduce(bool(np.isfinite(source_values).all()), op=MPI.LAND)
        )
        source_norm = float(source.norm())
        source_nonzero = bool(
            np.isfinite(source_norm) and source_norm > np.finfo(float).tiny
        )
        source_nonzero = bool(comm.allreduce(source_nonzero, op=MPI.LAND))
        if not source_finite or not np.isfinite(source_norm) or not source_nonzero:
            raise ValueError("S3b external C-column source is not finite and nonzero")

        ownership_by_rank = comm.allgather(
            {
                "rank": int(comm.rank),
                "fine": list(fine_ownership),
                "C_rows": list(c_ownership),
                "coefficient": list(coefficient_ownership),
                "source": list(source_ownership),
            }
        )
        audit = {
            "schema": S3B_SCHEMA,
            "route": S3B_ROUTE_ID,
            "label": S3B_EXTERNAL_SOURCE_LABEL,
            "seed": S3B_EXTERNAL_SOURCE_SEED,
            "column": S3B_EXTERNAL_SOURCE_COLUMN,
            "resolved_column": S3B_EXTERNAL_SOURCE_COLUMN,
            "sign": S3B_EXTERNAL_SOURCE_SIGN,
            "sign_application_count": 1,
            "sign_embedded_in": "current_DtnBlockAssembler_C_traction_values",
            "additional_sign_scale": 1.0,
            "extra_sign_applied": False,
            "H_inverse_created": False,
            "raw_global_row_remap": False,
            "fine_shape": list(fine_shape),
            "C_shape": list(c_shape),
            "active_ownership_match": True,
            "coefficient_global_unit_entry_count": global_unit_count,
            "coefficient_global_nonzero_entry_count": global_nonzero_count,
            "source_finite": source_finite,
            "source_nonzero": source_nonzero,
            "source_norm": source_norm,
            "fine_ownership_range": list(fine_ownership),
            "C_ownership_range": list(c_ownership),
            "coefficient_ownership_range": list(coefficient_ownership),
            "source_ownership_range": list(source_ownership),
            "ownership_by_rank": ownership_by_rank,
            "numeric_allgather": False,
            "full_vector_replication": False,
        }
        coefficient.destroy()
        coefficient = None
        return source, audit
    except Exception:
        if source is not None:
            source.destroy()
            source = None
        raise
    finally:
        if coefficient is not None:
            coefficient.destroy()


def _s3b_canonical_source_identity(
    system: Any,
    source: Any,
    comm: Any,
) -> dict[str, Any]:
    """Build a rank-independent source identity from string metadata only."""

    from .hcurl_canonical_vector_dolfinx import (
        extract_canonical_active_trace_packets,
    )
    from .hybrid_bare_f_authority import _canonical_key_token
    from .hybrid_source_canonical_bridge import packet_pair_digest

    local_error: dict[str, Any] | None = None
    local_exception: Exception | None = None
    local_tokens: list[str] = []
    local_pair_digests: list[str] = []
    extractor_audit: dict[str, Any] = {}
    try:
        packets, extractor_audit = extract_canonical_active_trace_packets(
            system.static_condensation.condensed,
            system.V,
            system.floquet_data,
            source,
        )
        seen: set[str] = set()
        for key, value in packets:
            token = _canonical_key_token(key)
            if token in seen:
                raise ValueError(f"duplicate canonical source token: {token}")
            seen.add(token)
            local_tokens.append(token)
            local_pair_digests.append(
                packet_pair_digest(
                    token,
                    complex(value),
                    label=S3B_EXTERNAL_SOURCE_LABEL,
                    side="bottom",
                )
            )
        del packets
    except Exception as exc:
        local_exception = exc
        local_error = {
            "rank": int(comm.rank),
            "type": type(exc).__name__,
            "message": str(exc),
        }

    errors = comm.allgather(local_error)
    first_error = next((item for item in errors if item is not None), None)
    if first_error is not None:
        error = RuntimeError(
            "S3b canonical source identity failed: "
            f"rank {int(first_error['rank'])} {first_error['type']}: "
            f"{first_error['message']}"
        )
        if local_exception is not None:
            raise error from local_exception
        raise error

    gathered_tokens = comm.gather(tuple(sorted(local_tokens)), root=0)
    gathered_pair_digests = comm.gather(tuple(sorted(local_pair_digests)), root=0)
    expected_count = int(system.fine_action.getSize()[0])
    root_result: dict[str, Any] | None
    if comm.rank == 0:
        try:
            all_tokens = [
                str(token)
                for shard in gathered_tokens
                for token in shard
            ]
            all_pair_digests = [
                str(digest)
                for shard in gathered_pair_digests
                for digest in shard
            ]
            duplicate_count = len(all_tokens) - len(set(all_tokens))
            if duplicate_count:
                root_result = {
                    "error": (
                        "duplicate canonical source tokens across MPI owners "
                        f"(count={duplicate_count})"
                    )
                }
            elif len(all_tokens) != expected_count:
                root_result = {
                    "error": (
                        "canonical source token count does not equal target active rows: "
                        f"{len(all_tokens)} != {expected_count}"
                    )
                }
            elif len(all_pair_digests) != len(all_tokens):
                root_result = {
                    "error": "canonical source token and pair-digest counts differ"
                }
            else:
                key_payload = "\n".join(sorted(all_tokens)).encode("utf-8")
                value_payload = "\n".join(sorted(all_pair_digests)).encode("ascii")
                canonical_key_sha256 = hashlib.sha256(key_payload).hexdigest()
                canonical_value_sha256 = hashlib.sha256(value_payload).hexdigest()
                source_definition = {
                    "label": S3B_EXTERNAL_SOURCE_LABEL,
                    "seed": S3B_EXTERNAL_SOURCE_SEED,
                    "column": S3B_EXTERNAL_SOURCE_COLUMN,
                    "sign": S3B_EXTERNAL_SOURCE_SIGN,
                    "sign_application_count": 1,
                    "sign_embedded_in": (
                        "current_DtnBlockAssembler_C_traction_values"
                    ),
                }
                source_definition_sha256 = hashlib.sha256(
                    json.dumps(
                        source_definition,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                identity_payload = {
                    "source_definition_sha256": source_definition_sha256,
                    "canonical_key_set_sha256": canonical_key_sha256,
                    "canonical_value_sha256": canonical_value_sha256,
                    "canonical_key_count": len(all_tokens),
                }
                source_canonical_identity_sha256 = hashlib.sha256(
                    json.dumps(
                        identity_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                root_result = {
                    "error": None,
                    "canonical_key_count": len(all_tokens),
                    "canonical_key_set_sha256": canonical_key_sha256,
                    "canonical_value_sha256": canonical_value_sha256,
                    "source_definition_sha256": source_definition_sha256,
                    "source_canonical_identity_sha256": (
                        source_canonical_identity_sha256
                    ),
                }
        except Exception as exc:
            root_result = {
                "error": f"{type(exc).__name__}: {exc}",
            }
    else:
        root_result = None
    root_result = comm.bcast(root_result, root=0)
    if root_result.get("error") is not None:
        raise RuntimeError(
            "S3b canonical source identity failed: "
            f"{root_result['error']}"
        )
    return {
        **root_result,
        "canonical_value_pair_digest_sha256": root_result[
            "canonical_value_sha256"
        ],
        "canonical_extractor_audit": dict(extractor_audit),
        "numeric_allgather": False,
        "full_vector_replication": False,
        "roundtrip_repeated": False,
    }


def build_s3_external_dtn_source(system: Any) -> tuple[Any, dict[str, Any]]:
    """Build and identity-bind the frozen current-layout external source."""

    source = None
    try:
        source, audit = _build_s3_external_dtn_source_vector(system)
        canonical = _s3b_canonical_source_identity(
            system,
            source,
            system.fine_action.getComm().tompi4py(),
        )
        audit.update(canonical)
        return source, audit
    except Exception:
        if source is not None:
            source.destroy()
            source = None
        raise


def _s3_json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _s3_json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_s3_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_s3_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _s3_json_safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"S3 audit contains unsupported value type: {type(value).__name__}")


class S3CurrentLayoutSourceFactory:
    """Borrow one target layout while dispatching the frozen five sources."""

    def __init__(
        self,
        target: Any,
        *,
        source_work_directory: str | Path | None = None,
        selected_mode_provider: Any | None = None,
        external_mode_authority: Mapping[str, Any] | None = None,
        external_mode_current_resolved_config_sha256: str | None = None,
        source_factor_marker_callback: Any | None = None,
    ) -> None:
        required = (
            "cfg", "side", "local_mesh",
            "V", "floquet_data", "static_condensation",
            "fine_action", "full_fe_rhs", "external_modes")
        missing = [name for name in required if not hasattr(target, name)]
        if missing:
            raise TypeError(f"S3 source target is missing fields: {missing}")
        if target.side != "bottom":
            raise ValueError("S3 source factory requires the bottom target")
        condensed = getattr(target.static_condensation, "condensed", None)
        if condensed is None:
            raise TypeError("S3 source target has no condensed active layout")

        from .hybrid_bare_f_authority import (
            V5_BARE_F_SOURCE_LABELS,
            V5_BARE_F_SOURCE_SPECS,
        )

        self._target = target
        self.cfg = target.cfg
        self.side = target.side
        self.local_mesh = target.local_mesh
        self.V = target.V
        self.floquet_data = target.floquet_data
        self.static_condensation = target.static_condensation
        self.condensed = condensed
        self.F = self.fine_action = target.fine_action
        self.full_fe_rhs, self.external_modes = target.full_fe_rhs, target.external_modes
        self.source_work_directory = (
            Path(source_work_directory) if source_work_directory is not None else None
        )
        self.selected_mode_provider = selected_mode_provider
        self.external_mode_authority = external_mode_authority
        self.external_mode_current_resolved_config_sha256 = (
            external_mode_current_resolved_config_sha256
        )
        self.source_factor_marker_callback = source_factor_marker_callback
        self._selected_mode_context = self._selected_exact_source_cache = None
        self._released = False
        self._source_labels, self._source_specs = (
            tuple(V5_BARE_F_SOURCE_LABELS), V5_BARE_F_SOURCE_SPECS)
        self.source_inventory: dict[str, Any] = {
            "source_order": list(self._source_labels),
            "source_build_counts": {label: 0 for label in self._source_labels},
            "source_audits": {},
            "source_builder_matrix_objects_constructed": dict.fromkeys(
                ("C", "D", "H"), 0),
            "target_action_blocks_borrowed": {
                name: getattr(getattr(target, "blocks", None), name, None) is not None
                for name in ("C", "D", "H")
            },
            "metadata_collective_present": True,
            "metadata_collective_scope": "ownership/hash/error metadata",
            "numeric_allgather": False, "full_vector_replication": False,
            "released": False,
        }
        self.construction_inventory = {
            "objects": dict(self.source_inventory["source_builder_matrix_objects_constructed"]),
            "source_build_counts": {label: 0 for label in self._source_labels},
        }
        zero_fields = ["one_cell_source_factor_active", "one_cell_source_factor_ready", "one_cell_source_factor_peak", "one_cell_source_factor_construction_count", "one_cell_source_factor_apply_count", "one_cell_source_factor_mat_solve_call_count", "one_cell_source_factor_rhs_columns_solved", "minimal_external_coupling_objects_constructed", "minimal_external_surface_component_count", "minimal_external_coupling_construction_call_count", "minimal_external_component_instances_total", "minimal_external_peak_live_components", "minimal_external_coupling_kind_count"]
        self.construction_inventory.update(dict.fromkeys(zero_fields, 0))
        self.construction_inventory.update(
            {
                "one_cell_source_factor_events": [], "one_cell_source_factor_destroyed": False,
                "one_cell_source_factor_factor_count_after": None,
            }
        )
    @property
    def comm(self) -> Any:
        return self.F.getComm().tompi4py()
    @property
    def dtn_objects_constructed(self) -> dict[str, int]:
        return dict(self.source_inventory["source_builder_matrix_objects_constructed"])
    @property
    def source_order(self) -> tuple[str, ...]:
        return self._source_labels
    def build(self, label: str) -> tuple[Any, dict[str, Any]]:
        if self._released:
            raise RuntimeError("S3 source factory has been released")
        label = str(label)
        if label not in self._source_specs:
            raise ValueError(f"unknown S3 source label: {label!r}")
        if label == S3B_EXTERNAL_SOURCE_LABEL:
            source, audit = build_s3_external_dtn_source(self._target)
        else:
            from .hybrid_bare_f_authority import build_current_bare_f_rhs

            source, audit = build_current_bare_f_rhs(self, label)
        try:
            safe_audit = _s3_json_safe(dict(audit))
            safe_audit.update(
                source_factory="S3CurrentLayoutSourceFactory",
                source_builder_matrix_objects_constructed=dict(
                    self.source_inventory["source_builder_matrix_objects_constructed"]
                ),
                target_action_blocks_borrowed=dict(
                    self.source_inventory["target_action_blocks_borrowed"]
                ),
                metadata_collective_present=True,
                metadata_collective_scope="ownership/hash/error metadata",
                numeric_allgather=False,
                full_vector_replication=False,
            )
        except Exception as exc:
            destroy = getattr(source, "destroy", None)
            if callable(destroy):
                try:
                    destroy()
                except Exception as cleanup_exc:
                    exc.add_note(f"S3 source cleanup failed: {cleanup_exc!r}")
            raise
        self.source_inventory["source_build_counts"][label] += 1
        self.source_inventory["source_audits"][label] = safe_audit
        return source, safe_audit

    def release(self) -> dict[str, Any]:
        if not self._released:
            self._selected_mode_context = self._selected_exact_source_cache = None
            for name in (
                "cfg", "side", "local_mesh", "V", "floquet_data",
                "static_condensation", "condensed", "F", "fine_action",
                "full_fe_rhs", "external_modes", "selected_mode_provider",
                "source_work_directory", "external_mode_authority",
                "external_mode_current_resolved_config_sha256", "source_factor_marker_callback",
            ):
                setattr(self, name, None)
            self._target, self._released = None, True
            self.source_inventory["released"] = True
        return _s3_json_safe(
            {
                "released": True,
                "non_owning": True,
                "target_destroy_called_by_factory": False,
                "petsc_objects_destroyed_by_factory": False,
                "source_order": list(self._source_labels),
                "source_build_counts": dict(self.source_inventory["source_build_counts"]),
                "built_labels": sorted(self.source_inventory["source_audits"]),
                "source_inventory": self.source_inventory,
            }
        )


def build_s3_j1_baseline_action(
    system: Any,
    progress_callback: Any | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Build the six-layer J1 action while releasing its temporary fine matrix."""

    if progress_callback is not None and not callable(progress_callback):
        raise TypeError("progress_callback must be callable when provided")
    static_condensation = getattr(system, "static_condensation", None)
    condensed = getattr(static_condensation, "condensed", None)
    if condensed is None:
        raise TypeError("S3b J1 baseline requires system.static_condensation.condensed")

    fine_matrix = None
    action = None

    def emit(stage: str, payload: dict[str, Any]) -> None:
        if progress_callback is not None:
            progress_callback(stage, payload)

    try:
        emit(
            "s3b_j1_f_materialize_begin",
            {
                "method": "J1",
                "layer_count": 6,
                "explicit_f_destroyed": False,
            },
        )
        fine_matrix = materialize_research_explicit_fine_matrix(condensed)
        emit(
            "s3b_j1_f_materialize_ready",
            {
                "method": "J1",
                "shape": list(map(int, fine_matrix.getSize())),
                "explicit_f_destroyed": False,
            },
        )
        labels, mapping_metadata = build_real_layer_labels(fine_matrix, system)
        layer_count = len(mapping_metadata["z_layer_boundaries"]) - 1
        if layer_count != 6:
            raise ValueError(
                f"S3b J1 baseline requires exactly six real layers, got {layer_count}"
            )
        action = build_layer_sweep_action(
            fine_matrix,
            labels,
            layer_count=layer_count,
            method="J1",
            fine_action=None,
            lifecycle_callback=progress_callback,
        )
        ready_diagnostics = deepcopy(action.diagnostics)
        if ready_diagnostics.get("layer_factor_count") != 6:
            raise RuntimeError(
                "S3b J1 baseline did not build exactly six layer factors"
            )
        fine_matrix.destroy()
        fine_matrix = None
        emit(
            "s3b_j1_f_destroyed",
            {
                "method": "J1",
                "explicit_f_destroyed": True,
                "explicit_f_retained": False,
            },
        )
        audit = {
            "method": "J1",
            "layer_count": 6,
            "layer_factor_count": 6,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "coarse_factor_count": 0,
            "global_coarse_factor_count": 0,
            "explicit_f_created": True,
            "explicit_f_destroyed": True,
            "explicit_f_retained": False,
            "explicit_f_lifecycle": {
                "created": True,
                "destroyed": True,
                "retained": False,
            },
            "mapping_metadata": dict(mapping_metadata),
            "ready_diagnostics": ready_diagnostics,
            "candidate_structure_gate": "not_evaluated",
            "candidate_max_local_rows_gate": "not_evaluated",
        }
        emit(
            "s3b_j1_action_ready",
            {
                "method": "J1",
                "layer_factor_count": 6,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "coarse_factor_count": 0,
                "explicit_f_destroyed": True,
            },
        )
        return action, audit
    except Exception:
        if action is not None:
            action.destroy()
        if fine_matrix is not None:
            fine_matrix.destroy()
        raise


def _read_s3_action_apply_count(action: Any) -> int | None:
    diagnostics = None
    try:
        diagnostics = action.diagnostics
        if callable(diagnostics):
            diagnostics = diagnostics()
    except Exception:
        diagnostics = None
    if isinstance(diagnostics, Mapping):
        value = diagnostics.get("apply_count")
        if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
            return int(value)
    try:
        value = action.apply_count
    except Exception:
        return None
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    return None


def audit_s3_preconditioner_one_apply(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    action: Any,
    label: str,
) -> dict[str, Any]:
    """Apply one borrowed preconditioner action and audit one explicit matvec."""

    if not isinstance(operator, PETSc.Mat):
        raise TypeError("S3b one-apply audit requires a PETSc Mat operator")
    shape = tuple(int(value) for value in operator.getSize())
    if len(shape) != 2 or shape[0] != shape[1]:
        raise ValueError(f"S3b one-apply audit requires a square operator, got {shape}")
    if not isinstance(rhs, PETSc.Vec):
        raise TypeError("S3b one-apply audit requires a PETSc Vec RHS")
    if int(rhs.getSize()) != shape[0]:
        raise ValueError("S3b one-apply RHS global size differs from the operator")
    operator_ownership = tuple(int(value) for value in operator.getOwnershipRange())
    rhs_ownership = tuple(int(value) for value in rhs.getOwnershipRange())
    if rhs_ownership != operator_ownership:
        raise ValueError("S3b one-apply RHS ownership differs from the operator")
    if not callable(getattr(action, "apply", None)):
        raise TypeError("S3b one-apply audit requires an action with callable apply")

    comm = operator.getComm().tompi4py()
    output = operator.createVecRight()
    residual = operator.createVecLeft()
    started = perf_counter()
    apply_before = _read_s3_action_apply_count(action)
    operator_matvec_count = 0
    try:
        action.apply(rhs, output)
        apply_after = _read_s3_action_apply_count(action)
        operator.mult(output, residual)
        operator_matvec_count = 1
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        source_norm = float(rhs.norm())
        output_norm = float(output.norm())
        residual_norm = float(residual.norm())
        denominator = (
            max(source_norm, np.finfo(float).tiny)
            if math.isfinite(source_norm)
            else math.nan
        )
        relative_residual = residual_norm / denominator
        elapsed_wall = float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        )
        finite = bool(
            math.isfinite(source_norm)
            and math.isfinite(output_norm)
            and math.isfinite(residual_norm)
            and math.isfinite(relative_residual)
            and math.isfinite(elapsed_wall)
        )
        apply_delta = (
            None
            if apply_before is None or apply_after is None
            else int(apply_after - apply_before)
        )
        if apply_delta is not None and apply_delta != 1:
            raise RuntimeError(
                "S3b one-apply action count delta must equal one, "
                f"got {apply_delta}"
            )
        return {
            "label": str(label),
            "source_norm": source_norm,
            "output_norm": output_norm,
            "residual_norm": residual_norm,
            "true_residual_norm": residual_norm,
            "relative_residual": relative_residual,
            "true_residual_relative": relative_residual,
            "finite": finite,
            "elapsed_wall_seconds": elapsed_wall,
            "elapsed_seconds": elapsed_wall,
            "action_apply_count_before": apply_before,
            "action_apply_count_after": apply_after,
            "action_apply_count_delta": apply_delta,
            "action_apply_count_exactly_one": (
                None if apply_delta is None else apply_delta == 1
            ),
            "operator_matvec_count": operator_matvec_count,
        }
    finally:
        residual.destroy()
        output.destroy()


class S3FixedRightFgmres:
    """Own the fixed S3b right-FGMRES shell around a borrowed action.

    The operator and action are deliberately borrowed.  This class only owns
    the KSP and the three vectors used by the later solve/callback stages; the
    solve stages themselves are intentionally kept outside this pilot shell.
    """

    class _NonOwningPcContext:
        """Forward a PETSc Python-PC apply to an action without owning it."""

        def __init__(self, action: Any) -> None:
            self._action: Any | None = action
            self.apply_count = 0
            self.destroyed = False

        def apply(
            self,
            _pc: PETSc.PC,
            source: PETSc.Vec,
            target: PETSc.Vec,
        ) -> None:
            if self._action is None:
                raise RuntimeError("S3b Python PC context has been destroyed")
            self._action.apply(source, target)
            self.apply_count += 1

        def destroy(self, _pc: PETSc.PC | None = None) -> None:
            if self.destroyed:
                return
            self._action = None
            self.destroyed = True

    # Keep a short alias for callers that need to identify the nested PETSc
    # context without making it part of the module-level public API.
    _PcContext = _NonOwningPcContext

    def __init__(self, operator: PETSc.Mat, action: Any) -> None:
        if not isinstance(operator, PETSc.Mat):
            raise TypeError("S3b FGMRES requires a PETSc Mat operator")
        shape = tuple(int(value) for value in operator.getSize())
        if len(shape) != 2 or shape[0] != shape[1]:
            raise ValueError(
                "S3b FGMRES requires a square PETSc Mat operator, "
                f"got {shape}"
            )
        if not callable(getattr(action, "apply", None)):
            raise TypeError("S3b FGMRES requires an action with callable apply")

        self.operator = operator
        self.action = action
        self._shape = shape
        self._ownership = tuple(int(value) for value in operator.getOwnershipRange())
        self._pc_context = self._NonOwningPcContext(action)
        self.pc_context = self._pc_context
        self.solution = operator.createVecRight()
        self.monitor = operator.createVecRight()
        self.residual = operator.createVecLeft()
        self._solution = self.solution
        self._monitor = self.monitor
        self._residual = self.residual
        self.ksp = None
        self._ksp = None
        self._setup_count = 0
        self._destroyed = False
        self._initial_attempted = False
        self._initial_completed = False
        self._initial_solve_count = 0
        self._true_residual_matvec_count = 0
        self._initial_rhs: PETSc.Vec | None = None
        self._initial_label: str | None = None
        self._initial_result: dict[str, Any] | None = None
        self._conditional_attempted = False
        self._conditional_completed = False
        self._conditional_solve_count = 0
        self._conditional_result: dict[str, Any] | None = None
        self._current_max_it = S3B_FGMRES_INITIAL_MAX_IT
        self._current_initial_guess_nonzero = False

        try:
            ksp = PETSc.KSP().create(operator.getComm())
            self.ksp = ksp
            self._ksp = ksp
            ksp.setOperators(operator)
            ksp.setType(PETSc.KSP.Type.FGMRES)
            ksp.setPCSide(PETSc.PC.Side.RIGHT)
            ksp.setGMRESRestart(S3B_FGMRES_RESTART)
            ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            ksp.setTolerances(
                rtol=0.0,
                atol=0.0,
                max_it=S3B_FGMRES_INITIAL_MAX_IT,
            )
            ksp.setInitialGuessNonzero(False)
            ksp.setErrorIfNotConverged(False)
            pc = ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(self._pc_context)
            ksp.setUp()
            self._setup_count = 1
        except Exception:
            if self.ksp is not None:
                self.ksp.destroy()
                self.ksp = None
                self._ksp = None
            self.residual.destroy()
            self.monitor.destroy()
            self.solution.destroy()
            self._pc_context.destroyed = True
            self._pc_context._action = None
            raise

    @staticmethod
    def _raise_collective_error(
        comm: Any,
        stage: str,
        local_exception: Exception | None,
    ) -> None:
        local_error = None
        if local_exception is not None:
            local_error = {
                "rank": int(comm.rank),
                "type": type(local_exception).__name__,
                "message": str(local_exception),
            }
        errors = comm.allgather(local_error)
        first_error = next((item for item in errors if item is not None), None)
        if first_error is None:
            return
        error = RuntimeError(
            f"S3b {stage} failed on rank {int(first_error['rank'])} "
            f"{first_error['type']}: {first_error['message']}"
        )
        if local_exception is not None:
            raise error from local_exception
        raise error

    @classmethod
    def _invoke_checkpoint_callback(
        cls,
        comm: Any,
        callback: Any,
        row: dict[str, Any],
        *,
        stage: str = "initial checkpoint callback",
    ) -> None:
        local_exception = None
        try:
            callback(row)
        except Exception as exc:
            local_exception = exc
        cls._raise_collective_error(
            comm,
            stage,
            local_exception,
        )

    @staticmethod
    def _validate_checkpoint_callback(comm: Any, callback: Any) -> bool:
        """Validate callback presence and callability collectively on every rank."""

        present = callback is not None
        local_exception = None
        try:
            if present and not callable(callback):
                raise TypeError("checkpoint_callback must be callable when provided")
        except Exception as exc:
            local_exception = exc
        local_error = None
        if local_exception is not None:
            local_error = {
                "rank": int(comm.rank),
                "type": type(local_exception).__name__,
                "message": str(local_exception),
            }
        packets = comm.allgather(
            {"rank": int(comm.rank), "present": bool(present), "error": local_error}
        )
        presence = {bool(packet["present"]) for packet in packets}
        first_error = next(
            (packet["error"] for packet in packets if packet["error"] is not None),
            None,
        )
        if len(presence) != 1 and first_error is None:
            first_error = {
                "rank": int(next(packet["rank"] for packet in packets)),
                "type": "ValueError",
                "message": "checkpoint_callback presence differs across MPI ranks",
            }
        if first_error is not None:
            error = RuntimeError(
                "S3b initial checkpoint callback validation failed on rank "
                f"{int(first_error['rank'])} {first_error['type']}: "
                f"{first_error['message']}"
            )
            if local_exception is not None:
                raise error from local_exception
            raise error
        return bool(next(iter(presence)))

    def _true_residual_row(
        self,
        rhs: PETSc.Vec,
        current: PETSc.Vec,
        *,
        label: str,
        iteration: int,
        checkpoint_kind: str,
        reported_absolute: float,
        rhs_norm: float,
        started: float,
        comm: Any,
        leg: str = "initial",
        error_stage: str = "initial true-residual checkpoint",
        leg_iteration: int | None = None,
    ) -> dict[str, Any]:
        local_exception = None
        true_absolute = math.nan
        solution_norm = math.nan
        local_values_finite = False
        residual_values_finite = False
        try:
            self.residual.set(0.0)
            self.operator.mult(current, self.residual)
            self._true_residual_matvec_count += 1
            self.residual.axpy(PETSc.ScalarType(-1.0), rhs)
            current_values = np.asarray(
                current.getArray(readonly=True), dtype=np.complex128
            )
            residual_values = np.asarray(
                self.residual.getArray(readonly=True), dtype=np.complex128
            )
            local_values_finite = bool(np.isfinite(current_values).all())
            residual_values_finite = bool(np.isfinite(residual_values).all())
            true_absolute = float(self.residual.norm())
            solution_norm = float(current.norm())
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(
            comm,
            error_stage,
            local_exception,
        )
        values_finite = bool(
            comm.allreduce(
                bool(local_values_finite and residual_values_finite),
                op=MPI.LAND,
            )
        )
        elapsed_wall = float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        )
        reported_absolute = float(reported_absolute)
        reported_relative = reported_absolute / rhs_norm
        true_relative = true_absolute / rhs_norm
        finite = bool(
            values_finite
            and math.isfinite(reported_absolute)
            and math.isfinite(reported_relative)
            and math.isfinite(true_absolute)
            and math.isfinite(true_relative)
            and math.isfinite(rhs_norm)
            and math.isfinite(solution_norm)
            and math.isfinite(elapsed_wall)
        )
        return {
            "label": label,
            "leg": leg,
            "iteration": int(iteration),
            "checkpoint_kind": checkpoint_kind,
            "reported_residual_absolute": reported_absolute,
            "reported_residual_relative": reported_relative,
            "reported_absolute": reported_absolute,
            "reported_relative": reported_relative,
            "true_residual_absolute": true_absolute,
            "true_residual_relative": true_relative,
            "true_residual_norm": true_absolute,
            "rhs_norm": float(rhs_norm),
            "solution_norm": solution_norm,
            "finite": finite,
            "pc_apply_count": int(self._pc_context.apply_count),
            "elapsed_wall_seconds": elapsed_wall,
            "elapsed_seconds": elapsed_wall,
            **(
                {"leg_iteration": int(leg_iteration)}
                if leg_iteration is not None
                else {}
            ),
        }

    def solve_initial(
        self,
        rhs: PETSc.Vec,
        label: str,
        checkpoint_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Run the single fixed-budget S3b initial FGMRES attempt.

        This method intentionally leaves conditional continuation and runner
        orchestration to the caller.  ``solution`` remains owned by this
        object after the attempt for that later continuation.
        """

        if self._destroyed:
            raise RuntimeError("S3b FGMRES has been destroyed")
        if self._initial_attempted:
            raise RuntimeError("S3b initial FGMRES may only be attempted once")
        self._initial_attempted = True
        self._initial_solve_count += 1
        comm = self.operator.getComm().tompi4py()
        label = str(label)
        checkpoint_iterations = (8, 16, 32, 64)
        local_exception = None
        try:
            if not isinstance(rhs, PETSc.Vec):
                raise TypeError("S3b initial RHS must be a PETSc Vec")
            if int(rhs.getSize()) != int(self._shape[0]):
                raise ValueError(
                    "S3b initial RHS global size differs from the operator: "
                    f"{rhs.getSize()} != {self._shape[0]}"
                )
            rhs_ownership = tuple(int(value) for value in rhs.getOwnershipRange())
            if rhs_ownership != self._ownership:
                raise ValueError(
                    "S3b initial RHS ownership differs from the operator: "
                    f"{rhs_ownership} != {self._ownership}"
                )
            rhs_values = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
            if not bool(np.isfinite(rhs_values).all()):
                raise ValueError("S3b initial RHS contains non-finite local values")
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(comm, "initial RHS validation", local_exception)

        rhs_finite = bool(
            comm.allreduce(
                bool(np.isfinite(np.asarray(rhs.getArray(readonly=True))).all()),
                op=MPI.LAND,
            )
        )
        if not rhs_finite:
            raise ValueError("S3b initial RHS is not finite on every rank")

        local_exception = None
        rhs_norm = math.nan
        try:
            rhs_norm = float(rhs.norm())
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(comm, "initial RHS norm", local_exception)
        norm_valid = bool(math.isfinite(rhs_norm) and rhs_norm > np.finfo(float).tiny)
        if not bool(comm.allreduce(norm_valid, op=MPI.LAND)):
            raise ValueError("S3b initial RHS norm must be finite and nonzero")

        callback_enabled = self._validate_checkpoint_callback(
            comm,
            checkpoint_callback,
        )

        started = perf_counter()
        self.solution.set(0.0)
        self.monitor.set(0.0)
        self.residual.set(0.0)
        r0 = self._true_residual_row(
            rhs,
            self.solution,
            label=label,
            iteration=0,
            checkpoint_kind="r0",
            reported_absolute=rhs_norm,
            rhs_norm=rhs_norm,
            started=started,
            comm=comm,
        )
        if callback_enabled:
            self._invoke_checkpoint_callback(comm, checkpoint_callback, dict(r0))

        checkpoints: dict[str, dict[str, Any]] = {}
        reported_history: list[dict[str, Any]] = []

        def convergence_test(
            current_ksp: PETSc.KSP,
            iteration: int,
            norm: float,
        ) -> int:
            reported_absolute = float(norm)
            reported_relative = reported_absolute / rhs_norm
            reported_history.append(
                {
                    "iteration": int(iteration),
                    "reported_residual_absolute": reported_absolute,
                    "reported_residual_relative": reported_relative,
                }
            )
            if int(iteration) not in checkpoint_iterations:
                return 0
            local_exception = None
            view = None
            try:
                view = current_ksp.buildSolution(self.monitor)
            except Exception as exc:
                local_exception = exc
            self._raise_collective_error(
                comm,
                "initial solution checkpoint",
                local_exception,
            )
            current = self.monitor if view is None else view
            row = self._true_residual_row(
                rhs,
                current,
                label=label,
                iteration=int(iteration),
                checkpoint_kind="explicit_true_residual",
                reported_absolute=reported_absolute,
                rhs_norm=rhs_norm,
                started=started,
                comm=comm,
            )
            checkpoints[str(int(iteration))] = dict(row)
            if checkpoint_callback is not None:
                self._invoke_checkpoint_callback(comm, checkpoint_callback, dict(row))
            return 0

        pc_apply_count_before = int(self._pc_context.apply_count)
        solve_started = perf_counter()
        local_exception = None
        try:
            self.ksp.setConvergenceTest(convergence_test)
            self.ksp.solve(rhs, self.solution)
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(comm, "initial FGMRES solve", local_exception)
        solve_elapsed_wall = float(
            comm.allreduce(perf_counter() - solve_started, op=MPI.MAX)
        )

        local_exception = None
        reason = 0
        iterations = 0
        reported_final = math.nan
        try:
            reason = int(self.ksp.getConvergedReason())
            iterations = int(self.ksp.getIterationNumber())
            reported_final = float(self.ksp.getResidualNorm())
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(comm, "initial FGMRES outcome", local_exception)

        if iterations in checkpoint_iterations and str(iterations) not in checkpoints:
            final_checkpoint = self._true_residual_row(
                rhs,
                self.solution,
                label=label,
                iteration=iterations,
                checkpoint_kind="explicit_true_residual_final",
                reported_absolute=reported_final,
                rhs_norm=rhs_norm,
                started=solve_started,
                comm=comm,
            )
            checkpoints[str(iterations)] = dict(final_checkpoint)
            if callback_enabled:
                self._invoke_checkpoint_callback(
                    comm,
                    checkpoint_callback,
                    dict(final_checkpoint),
                )

        postsolve = self._true_residual_row(
            rhs,
            self.solution,
            label=label,
            iteration=iterations,
            checkpoint_kind="postsolve_true_residual",
            reported_absolute=reported_final,
            rhs_norm=rhs_norm,
            started=solve_started,
            comm=comm,
        )
        pc_apply_count_after = int(self._pc_context.apply_count)
        missing = [
            int(checkpoint)
            for checkpoint in checkpoint_iterations
            if str(checkpoint) not in checkpoints
        ]
        checkpoint_complete = not missing
        bounded_reasons = {
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)),
        }
        happy_breakdown_reason = int(
            getattr(PETSc.KSP.ConvergedReason, "CONVERGED_HAPPY_BREAKDOWN", 7)
        )
        bounded = bool(reason in bounded_reasons)
        happy_breakdown = bool(reason == happy_breakdown_reason)
        reason_is_breakdown = bool(reason < 0 and not bounded)
        early_final = bool(iterations < S3B_FGMRES_INITIAL_MAX_IT)
        result = {
            "label": label,
            "leg": "initial",
            "restart": int(S3B_FGMRES_RESTART),
            "max_it": int(S3B_FGMRES_INITIAL_MAX_IT),
            "zero_initial_guess": True,
            "checkpoint_iterations": list(checkpoint_iterations),
            "checkpoint_complete": checkpoint_complete,
            "reported_residual_history": reported_history,
            "checkpoints": checkpoints,
            "r0": r0,
            "postsolve": postsolve,
            "ksp_reason": reason,
            "final_reason": reason,
            "ksp_breakdown": reason_is_breakdown,
            "breakdown": reason_is_breakdown,
            "bounded_termination": bounded,
            "bounded_reason": (
                "DIVERGED_ITS"
                if reason == int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3))
                else "DIVERGED_MAX_IT"
                if reason
                == int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3))
                else None
            ),
            "happy_breakdown": happy_breakdown,
            "iterations": iterations,
            "final_iteration": iterations,
            "postsolve_iteration": iterations,
            "actual_final_iteration": iterations,
            "early_final": early_final,
            "early_stop": early_final,
            "missing_checkpoints": [str(value) for value in missing],
            "missing": missing,
            "pc_apply_count_before": pc_apply_count_before,
            "pc_apply_count_after": pc_apply_count_after,
            "pc_apply_count_delta": pc_apply_count_after - pc_apply_count_before,
            "right_pc_apply_count_delta": pc_apply_count_after
            - pc_apply_count_before,
            "right_pc_apply_count_total": pc_apply_count_after,
            "true_residual_matvec_count": int(self._true_residual_matvec_count),
            "solve_elapsed_wall_seconds": solve_elapsed_wall,
            "setup_count": int(self._setup_count),
            "setup_reused": False,
            "finite": bool(
                checkpoint_complete
                and all(row["finite"] for row in checkpoints.values())
                and r0["finite"]
                and postsolve["finite"]
            ),
        }
        self._initial_completed = True
        self._initial_rhs = rhs
        self._initial_label = label
        self._initial_result = result
        return result

    def solve_conditional_to_256(
        self,
        rhs: PETSc.Vec,
        label: str,
        initial_gate: Mapping[str, Any],
        checkpoint_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Continue the completed initial solve through total iteration 256."""

        if self._destroyed:
            raise RuntimeError("S3b FGMRES has been destroyed")
        if self._conditional_attempted:
            raise RuntimeError("S3b conditional FGMRES may only be attempted once")
        self._conditional_attempted = True
        self._conditional_solve_count += 1
        comm = self.operator.getComm().tompi4py()
        callback_enabled = self._validate_checkpoint_callback(
            comm,
            checkpoint_callback,
        )
        label = str(label)
        local_exception = None
        try:
            if not self._initial_completed or self._initial_result is None:
                raise RuntimeError(
                    "S3b conditional FGMRES requires a completed initial solve"
                )
            if self._initial_result.get("iterations") != S3B_FGMRES_INITIAL_MAX_IT:
                raise RuntimeError(
                    "S3b conditional FGMRES requires initial termination at iteration 64"
                )
            if self._initial_result.get("checkpoint_complete") is not True:
                raise RuntimeError(
                    "S3b conditional FGMRES requires all initial checkpoints"
                )
            if self._initial_result.get("finite") is not True:
                raise RuntimeError(
                    "S3b conditional FGMRES requires finite initial checkpoints"
                )
            if not isinstance(initial_gate, Mapping):
                raise TypeError("initial_gate must be a mapping")
            if (
                initial_gate.get("classification") != S3B_INITIAL_POSITIVE
                or initial_gate.get("next_stage") != S3B_NEXT_CONDITIONAL_256
            ):
                raise ValueError(
                    "S3b conditional FGMRES requires the explicit initial positive Gate"
                )
            if rhs is not self._initial_rhs:
                raise ValueError(
                    "S3b conditional FGMRES requires the identical initial RHS object"
                )
            if label != self._initial_label:
                raise ValueError(
                    "S3b conditional FGMRES requires the identical initial label"
                )
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(
            comm,
            "conditional precondition",
            local_exception,
        )

        checkpoint_iterations = (128, 192, 256)
        leg_checkpoint_iterations = (64, 128, 192)
        reported_history: list[dict[str, Any]] = []
        checkpoints: dict[str, dict[str, Any]] = {}
        solve_started = perf_counter()
        matvec_count_before = int(self._true_residual_matvec_count)
        pc_apply_count_before = int(self._pc_context.apply_count)
        self._current_max_it = S3B_FGMRES_CONDITIONAL_TOTAL_IT - (
            S3B_FGMRES_INITIAL_MAX_IT
        )
        self._current_initial_guess_nonzero = True

        def convergence_test(
            current_ksp: PETSc.KSP,
            iteration: int,
            norm: float,
        ) -> int:
            leg_iteration = int(iteration)
            total_iteration = S3B_FGMRES_INITIAL_MAX_IT + leg_iteration
            reported_absolute = float(norm)
            reported_relative = reported_absolute / float(
                self._initial_result["r0"]["rhs_norm"]
            )
            reported_history.append(
                {
                    "iteration": total_iteration,
                    "leg_iteration": leg_iteration,
                    "reported_residual_absolute": reported_absolute,
                    "reported_residual_relative": reported_relative,
                }
            )
            if leg_iteration not in leg_checkpoint_iterations:
                return 0
            local_exception = None
            view = None
            try:
                view = current_ksp.buildSolution(self.monitor)
            except Exception as exc:
                local_exception = exc
            self._raise_collective_error(
                comm,
                "conditional solution checkpoint",
                local_exception,
            )
            current = self.monitor if view is None else view
            row = self._true_residual_row(
                rhs,
                current,
                label=label,
                iteration=total_iteration,
                checkpoint_kind="explicit_true_residual",
                reported_absolute=reported_absolute,
                rhs_norm=float(self._initial_result["r0"]["rhs_norm"]),
                started=solve_started,
                comm=comm,
                leg="conditional",
                error_stage="conditional true-residual checkpoint",
                leg_iteration=leg_iteration,
            )
            checkpoints[str(total_iteration)] = dict(row)
            if callback_enabled:
                self._invoke_checkpoint_callback(
                    comm,
                    checkpoint_callback,
                    dict(row),
                    stage="conditional checkpoint callback",
                )
            return 0

        local_exception = None
        try:
            self.ksp.setInitialGuessNonzero(True)
            self.ksp.setTolerances(
                rtol=0.0,
                atol=0.0,
                max_it=self._current_max_it,
            )
            self.ksp.setConvergenceTest(convergence_test)
            self.ksp.solve(rhs, self.solution)
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(comm, "conditional FGMRES solve", local_exception)
        solve_elapsed_wall = float(
            comm.allreduce(perf_counter() - solve_started, op=MPI.MAX)
        )

        local_exception = None
        reason = 0
        leg_iterations = 0
        reported_final = math.nan
        try:
            reason = int(self.ksp.getConvergedReason())
            leg_iterations = int(self.ksp.getIterationNumber())
            reported_final = float(self.ksp.getResidualNorm())
        except Exception as exc:
            local_exception = exc
        self._raise_collective_error(
            comm,
            "conditional FGMRES outcome",
            local_exception,
        )
        total_iterations = S3B_FGMRES_INITIAL_MAX_IT + leg_iterations

        if (
            total_iterations in checkpoint_iterations
            and str(total_iterations) not in checkpoints
        ):
            final_checkpoint = self._true_residual_row(
                rhs,
                self.solution,
                label=label,
                iteration=total_iterations,
                checkpoint_kind="explicit_true_residual_final",
                reported_absolute=reported_final,
                rhs_norm=float(self._initial_result["r0"]["rhs_norm"]),
                started=solve_started,
                comm=comm,
                leg="conditional",
                error_stage="conditional true-residual checkpoint",
                leg_iteration=leg_iterations,
            )
            checkpoints[str(total_iterations)] = dict(final_checkpoint)
            if callback_enabled:
                self._invoke_checkpoint_callback(
                    comm,
                    checkpoint_callback,
                    dict(final_checkpoint),
                    stage="conditional checkpoint callback",
                )

        postsolve = self._true_residual_row(
            rhs,
            self.solution,
            label=label,
            iteration=total_iterations,
            checkpoint_kind="postsolve_true_residual",
            reported_absolute=reported_final,
            rhs_norm=float(self._initial_result["r0"]["rhs_norm"]),
            started=solve_started,
            comm=comm,
            leg="conditional",
            error_stage="conditional true-residual checkpoint",
            leg_iteration=leg_iterations,
        )
        pc_apply_count_after = int(self._pc_context.apply_count)
        matvec_count_after = int(self._true_residual_matvec_count)
        missing = [
            int(checkpoint)
            for checkpoint in checkpoint_iterations
            if str(checkpoint) not in checkpoints
        ]
        checkpoint_complete = not missing
        bounded_reasons = {
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)),
        }
        happy_breakdown_reason = int(
            getattr(PETSc.KSP.ConvergedReason, "CONVERGED_HAPPY_BREAKDOWN", 7)
        )
        bounded = bool(reason in bounded_reasons)
        happy_breakdown = bool(reason == happy_breakdown_reason)
        reason_is_breakdown = bool(reason < 0 and not bounded)
        result = {
            "label": label,
            "leg": "conditional",
            "initial_total_iteration": S3B_FGMRES_INITIAL_MAX_IT,
            "restart": int(S3B_FGMRES_RESTART),
            "max_it": int(self._current_max_it),
            "leg_max_it": int(self._current_max_it),
            "total_max_it": int(S3B_FGMRES_CONDITIONAL_TOTAL_IT),
            "zero_initial_guess": False,
            "nonzero_initial_guess": True,
            "checkpoint_iterations": list(checkpoint_iterations),
            "leg_checkpoint_iterations": list(leg_checkpoint_iterations),
            "checkpoint_complete": checkpoint_complete,
            "reported_residual_history": reported_history,
            "checkpoints": checkpoints,
            "postsolve": postsolve,
            "r128": checkpoints.get("128", {}).get("true_residual_relative"),
            "r192": checkpoints.get("192", {}).get("true_residual_relative"),
            "r256": checkpoints.get("256", {}).get("true_residual_relative"),
            "ksp_reason": reason,
            "final_reason": reason,
            "ksp_breakdown": reason_is_breakdown,
            "breakdown": reason_is_breakdown,
            "bounded_termination": bounded,
            "bounded_reason": (
                "DIVERGED_ITS"
                if reason
                == int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3))
                else "DIVERGED_MAX_IT"
                if reason
                == int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3))
                else None
            ),
            "happy_breakdown": happy_breakdown,
            "iterations": leg_iterations,
            "leg_iterations": leg_iterations,
            "total_iterations": total_iterations,
            "final_iteration": total_iterations,
            "postsolve_iteration": total_iterations,
            "actual_final_iteration": total_iterations,
            "early_final": bool(leg_iterations < self._current_max_it),
            "early_stop": bool(leg_iterations < self._current_max_it),
            "missing_checkpoints": [str(value) for value in missing],
            "missing": missing,
            "pc_apply_count_before": pc_apply_count_before,
            "pc_apply_count_after": pc_apply_count_after,
            "pc_apply_count_delta": pc_apply_count_after - pc_apply_count_before,
            "right_pc_apply_count_delta": pc_apply_count_after
            - pc_apply_count_before,
            "right_pc_apply_count_total": pc_apply_count_after,
            "true_residual_matvec_count_before": matvec_count_before,
            "true_residual_matvec_count_after": matvec_count_after,
            "true_residual_matvec_count_delta": matvec_count_after
            - matvec_count_before,
            "true_residual_matvec_count": matvec_count_after,
            "solve_elapsed_wall_seconds": solve_elapsed_wall,
            "setup_count": int(self._setup_count),
            "setup_reused": True,
            "continuation_strategy": (
                "same_ksp_pc_service_nonzero_initial_restart_continuation"
            ),
            "finite": bool(
                checkpoint_complete
                and all(row["finite"] for row in checkpoints.values())
                and postsolve["finite"]
            ),
        }
        self._conditional_completed = True
        self._conditional_result = result
        return result

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Return a small immutable-by-copy setup/lifecycle snapshot."""

        return {
            "setup_count": int(self._setup_count),
            "pc_apply_count": int(self._pc_context.apply_count),
            "ksp_type": "fgmres",
            "pc_type": "python",
            "pc_side": "right",
            "restart": int(S3B_FGMRES_RESTART),
            "max_it": int(self._current_max_it),
            "initial_max_it": int(S3B_FGMRES_INITIAL_MAX_IT),
            "norm_type": "unpreconditioned",
            "rtol": 0.0,
            "atol": 0.0,
            "zero_initial_guess": not bool(self._current_initial_guess_nonzero),
            "initial_guess_nonzero": bool(self._current_initial_guess_nonzero),
            "current_max_it": int(self._current_max_it),
            "error_if_not_converged": False,
            "ownership": list(self._ownership),
            "ownership_range": list(self._ownership),
            "shape": list(self._shape),
            "operator_borrowed": True,
            "action_borrowed": True,
            "pc_context_destroyed": bool(self._pc_context.destroyed),
            "initial_attempted": bool(self._initial_attempted),
            "initial_completed": bool(self._initial_completed),
            "initial_solve_count": int(self._initial_solve_count),
            "conditional_attempted": bool(self._conditional_attempted),
            "conditional_completed": bool(self._conditional_completed),
            "conditional_solve_count": int(self._conditional_solve_count),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        """Destroy only the KSP and owned vectors; safe to call repeatedly."""

        if self._destroyed:
            return
        self._destroyed = True
        if self.ksp is not None:
            self.ksp.destroy()
        self._pc_context.destroy()
        self.residual.destroy()
        self.monitor.destroy()
        self.solution.destroy()


def _finite_metric(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def adjudicate_s3_b1_initial_gate(
    j1_r64: Any,
    candidate_r64: Any,
    *,
    finite: bool,
    breakdown: bool,
    resource_ok: bool,
) -> dict[str, Any]:
    """Apply the frozen initial B1 Gate without changing any threshold."""

    j1 = float(j1_r64) if _finite_metric(j1_r64) else math.nan
    candidate = float(candidate_r64) if _finite_metric(candidate_r64) else math.nan
    if not resource_ok:
        classification = S3B_INITIAL_RESOURCE_STOP
        next_stage = S3B_NEXT_FIXED_LOR
    elif not finite or breakdown or not (
        _finite_metric(j1)
        and _finite_metric(candidate)
        and j1 >= 0.0
        and candidate >= 0.0
    ):
        classification = S3B_INITIAL_UNSTABLE
        next_stage = S3B_NEXT_FIXED_LOR
    else:
        improvement = (
            math.inf
            if candidate == 0.0 and j1 > 0.0
            else j1 / candidate
            if candidate > 0.0
            else 0.0
        )
        positive = (
            candidate <= S3B_CANDIDATE_R64_LIMIT
            and improvement >= S3B_REQUIRED_J1_IMPROVEMENT
        )
        classification = (
            S3B_INITIAL_POSITIVE if positive else S3B_INITIAL_NO_SIGNAL
        )
        next_stage = (
            S3B_NEXT_CONDITIONAL_256 if positive else S3B_NEXT_FIXED_LOR
        )
    improvement = (
        math.inf
        if candidate == 0.0 and j1 > 0.0
        else j1 / candidate
        if _finite_metric(j1) and _finite_metric(candidate) and candidate > 0.0
        else 0.0
    )
    return {
        "classification": classification,
        "next_stage": next_stage,
        "positive": classification == S3B_INITIAL_POSITIVE,
        "gate_pass": classification == S3B_INITIAL_POSITIVE,
        "task40_open": True,
        "finite": bool(finite),
        "breakdown": bool(breakdown),
        "resource_ok": bool(resource_ok),
        "j1_r64": j1 if math.isfinite(j1) else None,
        "candidate_r64": candidate if math.isfinite(candidate) else None,
        "improvement_ratio": improvement if math.isfinite(improvement) else "infinite",
        "candidate_r64_limit": S3B_CANDIDATE_R64_LIMIT,
        "required_j1_improvement": S3B_REQUIRED_J1_IMPROVEMENT,
    }


def adjudicate_s3_b1_conditional_gate(
    r256: Any,
    *,
    finite: bool,
    resource_ok: bool,
) -> dict[str, Any]:
    """Apply the fixed 256-step continuation Gate."""

    residual = float(r256) if _finite_metric(r256) else math.nan
    if not resource_ok:
        classification = S3B_CONDITIONAL_RESOURCE_STOP
        next_stage = S3B_NEXT_FIXED_LOR
    elif not finite or not math.isfinite(residual) or residual < 0.0:
        classification = S3B_CONDITIONAL_UNSTABLE
        next_stage = S3B_NEXT_FIXED_LOR
    elif residual <= S3B_CANDIDATE_R256_LIMIT:
        classification = S3B_CONDITIONAL_PASS
        next_stage = S3B_NEXT_FIVE_SOURCE_BOTTOM
    else:
        classification = S3B_CONDITIONAL_NOT_QUALIFIED
        next_stage = S3B_NEXT_FIXED_LOR
    return {
        "classification": classification,
        "next_stage": next_stage,
        "positive": classification == S3B_CONDITIONAL_PASS,
        "gate_pass": classification == S3B_CONDITIONAL_PASS,
        "task40_open": True,
        "finite": bool(finite),
        "resource_ok": bool(resource_ok),
        "r256": residual if math.isfinite(residual) else None,
        "r256_limit": S3B_CANDIDATE_R256_LIMIT,
    }
