"""Task41 V4's bounded, volume-only owner and raw-cell evidence extraction."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import shutil
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from scipy import sparse
import ufl

from .common_3d_forms import _build_physical_volume_terms
from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
    build_unconstrained_assembly_time_condensation,
    iter_selected_volume_audit_cells,
    tabulate_volume_audit_cell,
)
from .p6_cell_condensed_action import P6CellCondensedAction

TASK41_V4_DONOR_MANIFEST_SHA256 = (
    "f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465"
)
TASK41_V4_DONOR_NPY_BYTES = 9_379_882_344
TASK41_V4_EVIDENCE_CAP_BYTES = 16 * 1024**3
TASK41_V4_FREE_SPACE_FLOOR_BYTES = 2 * 1024**3
TASK41_V4_FULL_STORAGE_ROWS = 18_501_024
TASK41_V4_ACTIVE_TRACE_ROWS = 5_688_000
TASK41_V4_APPENDED_ROWS = 64_120
TASK41_V4_SELECTED_ACTIVE_ROW = 5_458_716
TASK41_V4_SELECTED_ORIGINAL_ROW = 17_692_332
TASK41_V5_FROZEN_DENOMINATORS = (2225.481253487629, 2225.4807123031883)
TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE = 1.0e-11
TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT = 12
TASK41_V9_COMPACT_EVIDENCE_RESERVE_BYTES = (
    2 * (TASK41_V4_ACTIVE_TRACE_ROWS + TASK41_V4_APPENDED_ROWS) * 2 * 16
    + 6 * TASK41_V4_FULL_STORAGE_ROWS * 16
    + 10 * 4096
)


def _class_key(value: Sequence[Any]) -> tuple[Any, ...]:
    """Read legacy canonical keys and the explicitly tagged exact-geometry keys."""

    if len(value) == 5:
        return (
            int(value[0]),
            float(value[1]),
            float(value[2]),
            float(value[3]),
            int(value[4]),
        )
    if len(value) == 8 and value[0] == "mesh_actual_exact":
        tag, material_sha, layout_sha, shape, dtype, coordinate_sha, permutation = value[1:]
        if (
            isinstance(tag, bool)
            or not isinstance(tag, (int, np.integer))
            or isinstance(permutation, bool)
            or not isinstance(permutation, (int, np.integer))
            or any(
                not isinstance(item, str) or len(item) != 64
                for item in (material_sha, layout_sha, coordinate_sha)
            )
            or tuple(shape) != (8, 3)
            or dtype != np.dtype(np.float64).str
        ):
            raise ValueError(f"Task41 mesh_actual_exact key is malformed: {value!r}")
        return (
            "mesh_actual_exact",
            int(tag),
            str(material_sha),
            str(layout_sha),
            (8, 3),
            str(dtype),
            str(coordinate_sha),
            int(permutation),
        )
    raise ValueError(f"Task41 class key has an unsupported schema: {value!r}")


def _task41_material_identity_by_tag(cfg: Any) -> dict[int, dict[str, Any]]:
    def complex_identity(value: Any) -> dict[str, str]:
        number = complex(value)
        return {
            "real_hex": float(number.real).hex(),
            "imag_hex": float(number.imag).hex(),
        }

    coefficients = {
        int(cfg.tags.air): complex(cfg.eps_r),
        int(cfg.tags.substrate): complex(cfg.substrate_index) ** 2,
        int(cfg.tags.grating): complex(cfg.grating_index) ** 2,
    }
    return {
        tag: {
            "mu_r": complex_identity(cfg.mu_r),
            "k0": complex_identity(cfg.k0),
            "curl_coefficient": complex_identity(1.0 / complex(cfg.mu_r)),
            "mass_coefficient": complex_identity(-complex(cfg.k0) ** 2 * epsilon),
            "epsilon_r": complex_identity(epsilon),
        }
        for tag, epsilon in coefficients.items()
    }


def _check_artifact_array(record: Mapping[str, Any], array: Any, label: str) -> np.ndarray:
    value = np.asarray(array)
    if list(value.shape) != list(record.get("shape", ())) or str(value.dtype) != str(
        record.get("dtype")
    ):
        raise ValueError(f"Task41 V4 donor array metadata differs for {label}")
    return value


def _csr_equal(left: sparse.csr_matrix, right: sparse.csr_matrix) -> bool:
    return (
        left.shape == right.shape
        and np.array_equal(left.indptr, right.indptr)
        and np.array_equal(left.indices, right.indices)
        and np.array_equal(left.data, right.data)
    )


def _vector_norm(value: np.ndarray) -> float:
    flat = np.asarray(value).reshape(-1)
    scale = 0.0
    squares = 1.0
    for start in range(0, flat.size, 262_144):
        chunk = np.asarray(flat[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(chunk).all():
            raise ValueError("Task41 V4 norm input contains non-finite values")
        magnitude = np.abs(chunk)
        if magnitude.size:
            chunk_scale = float(np.max(magnitude))
            if chunk_scale:
                local = float(np.linalg.norm(chunk / chunk_scale)) * chunk_scale
                if scale < local:
                    squares = 1.0 + squares * (scale / local) ** 2
                    scale = local
                elif local:
                    squares += (local / scale) ** 2
    return float(scale * np.sqrt(squares)) if scale else 0.0


def _difference_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    a = np.asarray(left).reshape(-1)
    b = np.asarray(right).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("Task41 V4 replay vectors have different lengths")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, a.size, 262_144):
        left_chunk = np.asarray(a[start : start + 262_144], dtype=np.complex128)
        right_chunk = np.asarray(b[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(left_chunk).all() or not np.isfinite(right_chunk).all():
            raise ValueError("Task41 V4 difference input contains non-finite values")
        delta = left_chunk - right_chunk
        magnitude = np.abs(delta)
        if not magnitude.size:
            continue
        local_max_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_max_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = start + local_max_index
        local_norm = float(np.linalg.norm(delta))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _vector_metrics(
    value: np.ndarray, *, row_indices: np.ndarray | None = None
) -> dict[str, Any]:
    flat = np.asarray(value).reshape(-1)
    indices = None if row_indices is None else np.asarray(row_indices, dtype=np.int64)
    if indices is not None and indices.shape != flat.shape:
        raise ValueError("Task41 V4 metric row-index map differs from its vector")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, flat.size, 262_144):
        chunk = np.asarray(flat[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(chunk).all():
            raise ValueError("Task41 V4 vector contains non-finite values")
        magnitude = np.abs(chunk)
        if not magnitude.size:
            continue
        local_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = int(indices[start + local_index]) if indices is not None else start + local_index
        local_norm = float(np.linalg.norm(chunk))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _map_original_rows_to_active(
    original_rows: np.ndarray, active_original_rows: np.ndarray
) -> np.ndarray:
    """Map original storage rows to active ids without applying MPC twice."""
    rows = np.asarray(original_rows, dtype=np.int64)
    active = np.asarray(active_original_rows, dtype=np.int64)
    if rows.ndim != 1 or active.ndim != 1 or np.unique(active).size != active.size:
        raise ValueError("Task41 V4 original/active row maps are malformed")
    if rows.size and not active.size:
        raise ValueError("saved B-alpha rows cannot map to an empty active trace")
    order = np.argsort(active, kind="stable")
    sorted_active = active[order]
    positions = np.searchsorted(sorted_active, rows)
    if positions.size and (
        np.any(positions >= sorted_active.size)
        or np.any(sorted_active[np.minimum(positions, sorted_active.size - 1)] != rows)
    ):
        raise ValueError("saved B-alpha row is not an independent active trace row")
    return order[positions]


def _rhs_split_metrics(
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
) -> dict[str, Any]:
    if native_rhs.shape != native_volume_rhs.shape or native_rhs.ndim != 1:
        raise ValueError("Task41 V4 full and volume RHS layouts differ")
    if b_alpha_rows.shape != b_alpha_values.shape or b_alpha_rows.ndim != 1:
        raise ValueError("Task41 V4 B-alpha sparse frame is malformed")
    residual = np.array(native_rhs, dtype=np.complex128, copy=True)
    residual -= np.asarray(native_volume_rhs, dtype=np.complex128)
    np.add.at(residual, np.asarray(b_alpha_rows, dtype=np.int64), -b_alpha_values)
    metrics = _vector_metrics(residual)
    del residual
    return metrics


class Task41V5VolumeAttributionAccumulator:
    """Bounded per-cell attribution using the exact tensors before release."""

    def __init__(
        self,
        donor: Mapping[str, Any],
        *,
        artifact_prefix: str = "task41_p0_v5_candidate",
        attribution_prefix: str = "task41_p0_v5_attribution",
        candidate_identity: str | None = None,
        candidate_cache_identity: str | None = None,
    ) -> None:
        self.donor = donor
        self.artifact_prefix = str(artifact_prefix)
        self.attribution_prefix = str(attribution_prefix)
        self.candidate_identity = candidate_identity
        self.candidate_cache_identity = candidate_cache_identity
        self.pending: list[dict[str, Any]] = []
        self.accumulators: dict[tuple[int, str], dict[str, Any]] | None = None

    def _merge(self, piece: Mapping[str, Any]) -> None:
        if self.accumulators is None:
            self.pending.append(dict(piece))
            return
        key = (int(piece["column"]), str(piece["state"]))
        target = self.accumulators[key]
        ids = np.asarray(piece["active_ids"], dtype=np.int64)
        for name in ("delta_t", "T_r_i", "attributed_terms"):
            np.add.at(target[name], ids, np.asarray(piece[name], dtype=np.complex128))
        for name, value in piece["local_l2"].items():
            target["local_l2_sum"][name] = math.hypot(
                float(target["local_l2_sum"][name]), float(value)
            )

    def observe(
        self,
        _cell_index: int,
        _coordinates: np.ndarray,
        blocks: Mapping[str, np.ndarray],
        context: Mapping[str, Any],
    ) -> None:
        original = np.asarray(context["original_dofs"], dtype=np.int64)
        interior_positions = np.asarray(context["interior_positions"], dtype=np.int64)
        trace_positions = np.asarray(context["trace_positions"], dtype=np.int64)
        interior_rows = original[interior_positions]
        trace_expansion = context["trace_expansion"]
        active_ids = np.asarray(context["active_ids"], dtype=np.int64)
        R = np.asarray(context["R"], dtype=np.complex128)
        T = np.asarray(context["T"], dtype=np.complex128)
        S = np.asarray(context["S"], dtype=np.complex128)
        K = np.asarray(blocks["K"], dtype=np.complex128)
        G = np.asarray(blocks["G"], dtype=np.complex128)
        J = np.asarray(blocks["J"], dtype=np.complex128)
        L = np.asarray(blocks["L"], dtype=np.complex128)
        for column_index, column in enumerate(self.donor["columns"]):
            native_volume_rhs = np.asarray(column["native_volume_rhs"])
            native_rhs = np.asarray(column["native_rhs"])
            for state in column["states"]:
                state_label = str(state["label"])
                storage = np.asarray(state["storage"])
                native_action = np.asarray(state["native_volume_action"])
                active_original = np.asarray(
                    column["active_original_rows"], dtype=np.int64
                )
                if (
                    trace_expansion.shape != (len(trace_positions), len(active_ids))
                    or (active_ids.size and (active_ids.min() < 0 or active_ids.max() >= active_original.size))
                ):
                    raise ValueError("V5 cell MPC expansion differs from the saved active-row map")
                if not np.array_equal(
                    native_rhs[interior_rows], native_volume_rhs[interior_rows]
                ):
                    raise ValueError("V7 requires native full and volume RHS to match on every visited interior row")
                u_i = np.asarray(storage[interior_rows], dtype=np.complex128)
                # Saved storage vectors deliberately keep MPC slave rows zero.
                # Reconstruct each physical local trace from active values and
                # the cell's exact complex expansion before applying K/G/J/L.
                active_trace = storage[active_original[active_ids]]
                t_c = np.asarray(trace_expansion @ active_trace).reshape(-1)
                native_i = np.asarray(native_action[interior_rows], dtype=np.complex128)
                r_i = np.asarray(native_volume_rhs[interior_rows], dtype=np.complex128) - native_i
                K_u = K @ u_i
                G_t = G @ t_c
                actual_i = K_u + G_t
                delta_i = actual_i - native_i
                J_u = J @ u_i
                L_t = L @ t_c
                actual_t = J_u + L_t
                local_t_r_i = T @ r_i
                # Apply (J + T K) and (S - L - T G) to the vectors directly.
                # This preserves the review identity without materializing two
                # extra dense defect matrices for every cell.
                E_T_u = J_u + T @ K_u
                E_S_t = S @ t_c - L_t - T @ G_t
                T_delta_i = T @ delta_i
                local_attributed = T_delta_i + E_S_t - E_T_u
                projected_actual_t = np.asarray(trace_expansion.conj().T @ actual_t).reshape(-1)
                self._merge(
                    {
                        "column": column_index,
                        "state": state_label,
                        "active_ids": active_ids,
                        "delta_t": projected_actual_t,
                        "T_r_i": np.asarray(trace_expansion.conj().T @ local_t_r_i).reshape(-1),
                        "attributed_terms": np.asarray(
                            trace_expansion.conj().T @ local_attributed
                        ).reshape(-1),
                        "local_l2": {
                            "delta_i": _vector_norm(delta_i),
                            "T_delta_i": _vector_norm(T_delta_i),
                            "E_S_t": _vector_norm(E_S_t),
                            "E_T_u_i": _vector_norm(E_T_u),
                            "projected_actual_trace": _vector_norm(projected_actual_t),
                        },
                    }
                )

    def admit(self, active_rows: int) -> None:
        if self.accumulators is not None:
            raise RuntimeError("V5 attribution accumulator was admitted more than once")
        self.accumulators = {}
        for column_index, column in enumerate(self.donor["columns"]):
            active_original = np.asarray(column["active_original_rows"], dtype=np.int64)
            if active_original.shape != (active_rows,):
                raise ValueError("V5 attribution active row map differs from the owner")
            for state in column["states"]:
                key = (column_index, str(state["label"]))
                native_action = np.asarray(state["native_volume_action"])
                self.accumulators[key] = {
                    "delta_t": -np.asarray(
                        native_action[active_original], dtype=np.complex128
                    ).copy(),
                    "T_r_i": np.zeros(active_rows, dtype=np.complex128),
                    "attributed_terms": np.zeros(active_rows, dtype=np.complex128),
                    "local_l2_sum": {
                        "delta_i": 0.0,
                        "T_delta_i": 0.0,
                        "E_S_t": 0.0,
                        "E_T_u_i": 0.0,
                        "projected_actual_trace": 0.0,
                    },
                }
        pending, self.pending = self.pending, []
        for piece in pending:
            self._merge(piece)

    def finalize(
        self,
        candidate_p6: np.ndarray,
        candidate_reduced: np.ndarray,
        *,
        active_rows: int,
        candidate_d_volume_columns: Sequence[np.ndarray] | None = None,
        persist_array: Callable[[str, np.ndarray], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.accumulators is None:
            raise RuntimeError("V5 attribution accumulator was not admitted")
        if candidate_d_volume_columns is None or len(candidate_d_volume_columns) != len(
            self.donor["columns"]
        ):
            raise ValueError("V7 attribution requires each hash-bound candidate volume d vector")
        columns = []
        state_d_hat: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for column_index, column in enumerate(self.donor["columns"]):
            active_original = np.asarray(column["active_original_rows"], dtype=np.int64)
            native_rhs = np.asarray(column["native_rhs"])
            native_volume_rhs = np.asarray(column["native_volume_rhs"])
            b_alpha_rows = np.asarray(column["b_alpha_rows"], dtype=np.int64)
            b_alpha_values = np.asarray(column["b_alpha_values"], dtype=np.complex128)
            if (
                native_rhs.shape != native_volume_rhs.shape
                or native_rhs.ndim != 1
                or b_alpha_rows.shape != b_alpha_values.shape
                or b_alpha_rows.ndim != 1
                or b_alpha_values.dtype != np.dtype(np.complex128)
                or not np.isfinite(b_alpha_values).all()
                or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= native_rhs.size)))
            ):
                raise ValueError("V7 attribution donor RHS/B-alpha identities are malformed")
            beta_active = np.zeros(active_rows, dtype=np.complex128)
            beta_active_ids = _map_original_rows_to_active(b_alpha_rows, active_original)
            np.add.at(beta_active, beta_active_ids, b_alpha_values)
            d_volume = np.asarray(candidate_d_volume_columns[column_index])
            if d_volume.shape != (active_rows,) or d_volume.dtype != np.dtype(np.complex128):
                raise ValueError("V7 candidate volume d vector has an invalid layout")
            rhs_split = _rhs_split_metrics(
                native_rhs, native_volume_rhs, b_alpha_rows, b_alpha_values
            )
            states = []
            for state in column["states"]:
                label = str(state["label"])
                accumulated = self.accumulators[(column_index, label)]
                native_action = np.asarray(state["native_volume_action"])
                d_full = np.asarray(
                    candidate_p6[:active_rows, column_index]
                    - candidate_reduced[:active_rows, column_index],
                    dtype=np.complex128,
                )
                f_t = np.asarray(native_rhs[active_original], dtype=np.complex128)
                b_t = np.asarray(native_volume_rhs[active_original], dtype=np.complex128)
                n_t = np.asarray(native_action[active_original], dtype=np.complex128)
                r_t_legacy = np.asarray(
                    f_t - n_t,
                    dtype=np.complex128,
                )
                right = accumulated["delta_t"] + accumulated["attributed_terms"]
                legacy_left = d_full + r_t_legacy + accumulated["T_r_i"]
                legacy_closure_vector = legacy_left - right
                closure = _vector_metrics(legacy_closure_vector)
                left_l2 = _vector_norm(legacy_left)
                right_l2 = _vector_norm(right)
                frozen_denominator = TASK41_V5_FROZEN_DENOMINATORS[column_index]
                closure_frozen_relative = closure["absolute_l2"] / frozen_denominator
                accumulation_scale = (
                    _vector_norm(d_full)
                    + _vector_norm(r_t_legacy)
                    + _vector_norm(accumulated["T_r_i"])
                    + _vector_norm(accumulated["delta_t"])
                    + _vector_norm(accumulated["attributed_terms"])
                )
                legacy_minus_beta = legacy_closure_vector - beta_active
                r_volume = b_t - n_t
                r_full = f_t - n_t - beta_active
                volume_left = d_volume + r_volume + accumulated["T_r_i"]
                full_left = d_full + r_full + accumulated["T_r_i"]
                corrected_volume = volume_left - right
                corrected_full = full_left - right
                d_hat_volume = right - r_volume - accumulated["T_r_i"]
                d_hat_full = right - r_full - accumulated["T_r_i"]
                rhs_split_active = f_t - b_t - beta_active
                d_full_split = (d_full - d_volume) + rhs_split_active
                cross_product = np.vdot(beta_active, legacy_closure_vector)
                support_mask = np.zeros(active_rows, dtype=np.bool_)
                support_mask[beta_active_ids] = True
                beta_support_ids = np.flatnonzero(support_mask)
                beta_nonsupport_ids = np.flatnonzero(~support_mask)
                beta_support_closure = _vector_metrics(
                    legacy_closure_vector[beta_support_ids], row_indices=beta_support_ids
                )
                beta_nonsupport_closure = _vector_metrics(
                    legacy_closure_vector[beta_nonsupport_ids], row_indices=beta_nonsupport_ids
                )
                accumulator_artifacts = {}
                if persist_array is not None:
                    for artifact_name, values in (
                        ("T_r_i", accumulated["T_r_i"]),
                        ("delta_t", accumulated["delta_t"]),
                        ("attributed_terms", accumulated["attributed_terms"]),
                    ):
                        name = (
                            f"{self.attribution_prefix}_col{column_index}_"
                            f"{label}_{artifact_name}"
                        )
                        accumulator_artifacts[artifact_name] = {
                            "name": name,
                            **dict(persist_array(name, values)),
                        }
                states.append(
                    {
                        "state": label,
                        "accumulator_artifacts": accumulator_artifacts,
                        "delta_t_actual_trace_minus_native_trace_l2": _vector_norm(
                            accumulated["delta_t"]
                        ),
                        "delta_i_l2_over_cells": accumulated["local_l2_sum"]["delta_i"],
                        "T_r_i_global_l2": _vector_norm(accumulated["T_r_i"]),
                        "T_delta_i_l2_over_cells": accumulated["local_l2_sum"]["T_delta_i"],
                        "E_S_t_l2_over_cells": accumulated["local_l2_sum"]["E_S_t"],
                        "E_T_u_i_l2_over_cells": accumulated["local_l2_sum"]["E_T_u_i"],
                        "left_d_plus_r_t_plus_T_r_i_l2": left_l2,
                        "right_delta_t_plus_local_defects_l2": right_l2,
                        "closure_difference": closure,
                        "closure_frozen_denominator": frozen_denominator,
                        "closure_frozen_denominator_relative": closure_frozen_relative,
                        "closure_relative_to_accumulation_scale": (
                            closure["absolute_l2"] / max(accumulation_scale, np.finfo(float).tiny)
                        ),
                        "accumulation_scale_l2_sum": accumulation_scale,
                        "v7_formula_diagnostics": {
                            "legacy_closure_minus_beta_active": _vector_metrics(legacy_minus_beta),
                            "legacy_closure_vector": _vector_metrics(legacy_closure_vector),
                            "legacy_closure_beta_active_l2": _vector_norm(beta_active),
                            "legacy_beta_conjugate_inner_product": {
                                "real": float(cross_product.real),
                                "imag": float(cross_product.imag),
                            },
                            "legacy_closure_on_beta_support": beta_support_closure,
                            "legacy_closure_off_beta_support": beta_nonsupport_closure,
                            "corrected_full_closure": _vector_metrics(corrected_full),
                            "corrected_volume_closure": _vector_metrics(corrected_volume),
                            "corrected_full_closure_frozen_denominator_relative": (
                                _vector_norm(corrected_full) / frozen_denominator
                            ),
                            "corrected_volume_closure_frozen_denominator_relative": (
                                _vector_norm(corrected_volume) / frozen_denominator
                            ),
                            "corrected_full_closure_relative_to_d_full": (
                                _vector_norm(corrected_full)
                                / max(_vector_norm(d_full), np.finfo(float).tiny)
                            ),
                            "corrected_volume_closure_relative_to_d_volume": (
                                _vector_norm(corrected_volume)
                                / max(_vector_norm(d_volume), np.finfo(float).tiny)
                            ),
                            "term_scales": {
                                "delta_t": {
                                    "absolute_l2": _vector_norm(accumulated["delta_t"]),
                                    "frozen_denominator_relative": _vector_norm(accumulated["delta_t"]) / frozen_denominator,
                                },
                                "attributed_terms_Q": {
                                    "absolute_l2": _vector_norm(accumulated["attributed_terms"]),
                                    "frozen_denominator_relative": _vector_norm(accumulated["attributed_terms"]) / frozen_denominator,
                                },
                                "r_volume_trace": {
                                    "absolute_l2": _vector_norm(r_volume),
                                    "frozen_denominator_relative": _vector_norm(r_volume) / frozen_denominator,
                                },
                                "T_r_i": {
                                    "absolute_l2": _vector_norm(accumulated["T_r_i"]),
                                    "frozen_denominator_relative": _vector_norm(accumulated["T_r_i"]) / frozen_denominator,
                                },
                                "candidate_d_full": {
                                    "absolute_l2": _vector_norm(d_full),
                                    "frozen_denominator_relative": _vector_norm(d_full) / frozen_denominator,
                                },
                                "saved_d_volume": {
                                    "absolute_l2": _vector_norm(d_volume),
                                    "frozen_denominator_relative": _vector_norm(d_volume) / frozen_denominator,
                                },
                            },
                            "epsilon_rhs_native_minus_volume_minus_Balpha": rhs_split,
                            "full_minus_volume_d_plus_rhs_split": _vector_metrics(d_full_split),
                            "d_hat_full_minus_candidate_d_full": _difference_metrics(
                                d_hat_full, d_full
                            ),
                            "d_hat_volume_minus_saved_d_volume": _difference_metrics(
                                d_hat_volume, d_volume
                            ),
                        },
                    }
                )
                previous_hat = state_d_hat.get(column_index)
                if previous_hat is None:
                    state_d_hat[column_index] = (d_hat_volume.copy(), d_hat_full.copy())
                else:
                    state_metrics = states[-1]["v7_formula_diagnostics"]
                    state_metrics["d_hat_volume_vs_previous_donor_state"] = _difference_metrics(
                        d_hat_volume, previous_hat[0]
                    )
                    state_metrics["d_hat_full_vs_previous_donor_state"] = _difference_metrics(
                        d_hat_full, previous_hat[1]
                    )
                    del state_d_hat[column_index]
                del (
                    legacy_left,
                    legacy_closure_vector,
                    legacy_minus_beta,
                    r_volume,
                    r_full,
                    volume_left,
                    full_left,
                    corrected_volume,
                    corrected_full,
                    d_hat_volume,
                    d_hat_full,
                    d_full_split,
                    support_mask,
                    beta_support_closure,
                    beta_nonsupport_closure,
                    cross_product,
                )
            columns.append({"column": column_index, "states": states})
        return {
            "schema": (
                "task41.p0.v6.global_geometry_native_elimination_attribution.v1"
                if self.candidate_identity is not None
                else "task41.p0.v5.global_geometry_native_elimination_attribution.v1"
            ),
            "identity": "d + r_t + sum(E^H T r_i) = Delta_t + sum(E^H(T Delta_i + E_S t - E_T u_i))",
            "accumulation_order": "cell order with local E^H projections; native trace action subtracted once globally",
            "slave_trace_reconstruction": "local E times saved active trace values; saved slave storage remains zero",
            "defect_application": "E_T u_i and E_S t applied as vector products without dense defect-matrix materialization",
            "raw_actual_tensor_retention": "none; observe then release each exact key",
            "diagnostic_scales": [
                "left_and_right_identity_norms",
                "frozen_candidate_denominator",
                "sum_of_accumulated_term_norms",
            ],
            "formula_version": "task41.p0.v7.full_and_volume_attribution.v1",
            "legacy_closure_difference_definition": "d_full + (native_rhs_trace - native_volume_action_trace) + T_r_i - (delta_t + attributed_terms); retained only to reproduce the V6 receipt",
            "corrected_full_residual_definition": "native_rhs_trace - native_volume_action_trace - B_alpha_trace",
            "corrected_volume_residual_definition": "native_volume_rhs_trace - native_volume_action_trace",
            "corrected_full_identity_definition": "d_full + r_full_trace + T_r_i = delta_t + attributed_terms",
            "corrected_volume_identity_definition": "d_volume + r_volume_trace + T_r_i = delta_t + attributed_terms",
            "rhs_split": "native_rhs - native_volume_rhs - B_alpha; B_alpha rows are renumbered to active ids once",
            "interior_rhs_identity": "observe verifies native_rhs == native_volume_rhs on every visited cell interior row",
            "global_closure_status": "DIAGNOSTIC_ONLY",
            "columns": columns,
        }


def audit_task41_v4_geometry_pair_attribution(
    *,
    cell_pairs: Mapping[int, Mapping[str, Any]],
    saved_maps: Mapping[int, Mapping[str, np.ndarray]],
    columns: Sequence[Mapping[str, Any]],
    saved_classes: Mapping[int, Mapping[str, np.ndarray] | None],
    saved_d_volume: Sequence[np.ndarray],
    saved_reduce_r_volume: Mapping[tuple[int, str], np.ndarray],
    original_denominators: Sequence[float],
    target_active_row: int,
    target_original_row: int,
) -> dict[str, Any]:
    """Attribute the saved selected-row discrepancy on two cell geometry paths."""

    from scipy.sparse import csr_matrix

    cell_indices = tuple(sorted(int(value) for value in cell_pairs))
    if len(cell_indices) != 2 or len(columns) != 2:
        raise ValueError("Task41 V4 geometry attribution requires the frozen two cells and two columns")
    if not (
        len(saved_d_volume) == len(columns)
        and len(original_denominators) == len(columns)
    ):
        raise ValueError("Task41 V4 geometry attribution column inputs do not align")

    local_maps: dict[int, tuple[Any, np.ndarray, int]] = {}
    for cell_index in cell_indices:
        pair = cell_pairs[cell_index]
        map_arrays = saved_maps[cell_index]
        trace_rows = np.asarray(map_arrays["trace_original_rows"], dtype=np.int64)
        active_ids = np.asarray(map_arrays["active_ids"], dtype=np.int64)
        E = csr_matrix(
            (
                np.asarray(map_arrays["trace_expansion_data"], dtype=np.complex128),
                np.asarray(map_arrays["trace_expansion_indices"], dtype=np.int32),
                np.asarray(map_arrays["trace_expansion_indptr"], dtype=np.int32),
            ),
            shape=(trace_rows.size, active_ids.size),
        )
        if not E.has_canonical_format:
            raise ValueError(f"Task41 V4 cell expansion is not canonical for cell {cell_index}")
        target_columns = np.flatnonzero(active_ids == int(target_active_row))
        if target_columns.size != 1:
            raise ValueError(f"Task41 V4 cell expansion omits or duplicates target row in cell {cell_index}")
        local_maps[cell_index] = (
            E,
            np.asarray(E[:, int(target_columns[0])].toarray()).reshape(-1),
            int(target_columns[0]),
        )

    output: list[dict[str, Any]] = []
    delta_i_arrays: dict[str, np.ndarray] = {}
    for column_index, column in enumerate(columns):
        active_original_rows = np.asarray(column["active_original_rows"], dtype=np.int64)
        if int(active_original_rows[target_active_row]) != int(target_original_row):
            raise ValueError("Task41 V4 active/original target row identity differs")
        fields = (
            ("known", np.asarray(column["known_field"], dtype=np.complex128), None),
            (
                "j0",
                np.asarray(column["states"][0]["storage"], dtype=np.complex128),
                np.asarray(column["states"][0]["native_volume_action"], dtype=np.complex128),
            ),
            (
                "j3",
                np.asarray(column["states"][1]["storage"], dtype=np.complex128),
                np.asarray(column["states"][1]["native_volume_action"], dtype=np.complex128),
            ),
        )
        for state_label, field_values, native_action in fields:
            state_result: dict[str, Any] = {
                "column": column_index,
                "state": state_label,
                "native_action_reference": (
                    "saved split rank-1 volume action" if native_action is not None else None
                ),
                "paths": {},
            }
            path_cells: dict[str, dict[int, dict[str, Any]]] = {}
            for path_name in ("actual", "canonical"):
                target_sum = 0.0 + 0.0j
                term_a = 0.0 + 0.0j
                term_t_di = 0.0 + 0.0j
                selected_cells: list[dict[str, Any]] = []
                path_cells[path_name] = {}
                all_delta_i: list[np.ndarray] = []
                for cell_index in cell_indices:
                    pair = cell_pairs[cell_index]
                    map_arrays = saved_maps[cell_index]
                    E, target_weights, _target_col = local_maps[cell_index]
                    interior_rows = np.asarray(
                        map_arrays["interior_original_rows"], dtype=np.int64
                    )
                    active_ids = np.asarray(map_arrays["active_ids"], dtype=np.int64)
                    active_values = field_values[active_original_rows[active_ids]]
                    local_trace = np.asarray(E @ active_values, dtype=np.complex128).reshape(-1)
                    local_interior = np.asarray(field_values[interior_rows], dtype=np.complex128)
                    blocks = pair[path_name]
                    action_i = blocks["K"] @ local_interior + blocks["G"] @ local_trace
                    action_t = blocks["J"] @ local_interior + blocks["L"] @ local_trace
                    target_cell_action = complex(np.vdot(target_weights, action_t))
                    target_sum += target_cell_action
                    cell_result: dict[str, Any] = {
                        "cell_index": cell_index,
                        "target_trace_action": [float(target_cell_action.real), float(target_cell_action.imag)],
                    }
                    path_cells[path_name][cell_index] = {
                        "target_trace_action": target_cell_action,
                        "delta_i": None,
                    }
                    if native_action is not None:
                        delta_i = np.asarray(
                            action_i - native_action[interior_rows], dtype=np.complex128
                        )
                        all_delta_i.append(delta_i)
                        array_name = (
                            f"col{column_index}_{state_label}_{path_name}_cell{cell_index}_delta_i"
                        )
                        delta_i_arrays[array_name] = delta_i
                        path_cells[path_name][cell_index]["delta_i"] = delta_i
                        cell_result["delta_i"] = _difference_metrics(
                            action_i, native_action[interior_rows]
                        )
                        saved_class = saved_classes.get(cell_index)
                        if saved_class is not None:
                            term_a += complex(
                                np.vdot(
                                    target_weights,
                                    (saved_class["S"] - blocks["L"] - saved_class["T"] @ blocks["G"])
                                    @ local_trace
                                    - (blocks["J"] + saved_class["T"] @ blocks["K"])
                                    @ local_interior,
                                )
                            )
                            term_t_di += complex(
                                np.vdot(target_weights, saved_class["T"] @ delta_i)
                            )
                            cell_result["T_delta_i_target"] = [
                                float(np.real(np.vdot(target_weights, saved_class["T"] @ delta_i))),
                                float(np.imag(np.vdot(target_weights, saved_class["T"] @ delta_i))),
                            ]
                    selected_cells.append(cell_result)

                path_report: dict[str, Any] = {
                    "selected_cells": selected_cells,
                    "selected_cells_target_trace_action_sum": [
                        float(target_sum.real), float(target_sum.imag)
                    ],
                }
                if native_action is not None:
                    delta_t = complex(target_sum - native_action[target_original_row])
                    path_report["native_comparison"] = {
                        "delta_t": [float(delta_t.real), float(delta_t.imag)],
                        "delta_t_abs": float(abs(delta_t)),
                        "saved_native_target_action": [
                            float(np.real(native_action[target_original_row])),
                            float(np.imag(native_action[target_original_row])),
                        ],
                        "delta_i_total_l2": float(np.linalg.norm(np.concatenate(all_delta_i))),
                    }
                    if all(saved_classes.get(cell_index) is not None for cell_index in cell_indices):
                        predicted = term_a + delta_t + term_t_di
                        saved_target = complex(
                            saved_d_volume[column_index][target_active_row]
                            + saved_reduce_r_volume[(column_index, state_label)][target_active_row]
                        )
                        residual = predicted - saved_target
                        denominator = float(original_denominators[column_index])
                        path_report["native_comparison"].update(
                            {
                                "identity_term_A": [float(term_a.real), float(term_a.imag)],
                                "identity_term_delta_t": [float(delta_t.real), float(delta_t.imag)],
                                "identity_term_T_delta_i": [float(term_t_di.real), float(term_t_di.imag)],
                                "predicted_d_volume_plus_reduce_r_volume": [
                                    float(predicted.real), float(predicted.imag)
                                ],
                                "saved_d_volume_plus_reduce_r_volume": [
                                    float(saved_target.real), float(saved_target.imag)
                                ],
                                "selected_row_identity_residual_abs": float(abs(residual)),
                                "selected_row_residual_over_original_global_denominator": float(
                                    abs(residual) / denominator
                                ),
                                "original_global_denominator": denominator,
                                "global_column_gate_claim": False,
                            }
                        )
                state_result["paths"][path_name] = path_report
            for cell_index in cell_indices:
                actual_value = path_cells["actual"][cell_index]["target_trace_action"]
                canonical_value = path_cells["canonical"][cell_index]["target_trace_action"]
                delta = actual_value - canonical_value
                for path_name in ("actual", "canonical"):
                    next(
                        item
                        for item in state_result["paths"][path_name]["selected_cells"]
                        if item["cell_index"] == cell_index
                    )["actual_minus_canonical_target_trace_action"] = [
                        float(delta.real), float(delta.imag)
                    ]
                if native_action is not None:
                    state_result["paths"]["actual"]["selected_cells"][
                        cell_indices.index(cell_index)
                    ]["actual_minus_canonical_delta_i"] = _difference_metrics(
                        path_cells["actual"][cell_index]["delta_i"],
                        path_cells["canonical"][cell_index]["delta_i"],
                    )
            output.append(state_result)

    return {"attribution": output, "delta_i_arrays": delta_i_arrays}


def _sum_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    a = np.asarray(left).reshape(-1)
    b = np.asarray(right).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("Task41 V4 identity vectors have different lengths")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, a.size, 262_144):
        left_chunk = np.asarray(a[start : start + 262_144], dtype=np.complex128)
        right_chunk = np.asarray(b[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(left_chunk).all() or not np.isfinite(right_chunk).all():
            raise ValueError("Task41 V4 sum input contains non-finite values")
        total = left_chunk + right_chunk
        magnitude = np.abs(total)
        if not magnitude.size:
            continue
        local_max_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_max_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = start + local_max_index
        local_norm = float(np.linalg.norm(total))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _rhs_decomposition_metrics(
    total_rhs: np.ndarray,
    volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
) -> dict[str, Any]:
    total = np.asarray(total_rhs).reshape(-1)
    volume = np.asarray(volume_rhs).reshape(-1)
    if total.shape != volume.shape:
        raise ValueError("Task41 V4 total and volume RHS have different lengths")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, total.size, 262_144):
        stop = min(total.size, start + 262_144)
        delta = np.array(total[start:stop], dtype=np.complex128, copy=True)
        lo = int(np.searchsorted(b_alpha_rows, start))
        hi = int(np.searchsorted(b_alpha_rows, stop))
        if hi > lo:
            delta[b_alpha_rows[lo:hi] - start] -= b_alpha_values[lo:hi]
        delta -= np.asarray(volume[start:stop], dtype=np.complex128)
        if not np.isfinite(delta).all():
            raise ValueError("Task41 V4 RHS decomposition contains non-finite values")
        magnitude = np.abs(delta)
        if not magnitude.size:
            continue
        local_max_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_max_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = start + local_max_index
        local_norm = float(np.linalg.norm(delta))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _local_class_identity(
    key: tuple[Any, ...],
    raw: Mapping[str, Any],
    *,
    T: np.ndarray,
    R: np.ndarray,
    S: np.ndarray,
) -> dict[str, Any]:
    K = np.asarray(raw["K"], dtype=np.complex128)
    G = np.asarray(raw["G"], dtype=np.complex128)
    J = np.asarray(raw["J"], dtype=np.complex128)
    L = np.asarray(raw["L"], dtype=np.complex128)
    TG = T @ G
    TK = T @ K
    KR = K @ R
    residuals = {
        "S_minus_L_plus_TG": S - (L + TG),
        "TK_plus_J": TK + J,
        "KR_plus_G": KR + G,
    }
    scales = {
        "S_minus_L_plus_TG": max(_vector_norm(S), _vector_norm(L), _vector_norm(TG), np.finfo(float).tiny),
        "TK_plus_J": max(_vector_norm(TK), _vector_norm(J), np.finfo(float).tiny),
        "KR_plus_G": max(_vector_norm(KR), _vector_norm(G), np.finfo(float).tiny),
    }
    metrics = {
        name: {
            "absolute_frobenius": _vector_norm(value),
            "relative_to_local_terms": _vector_norm(value) / scales[name],
            "max_abs": float(np.max(np.abs(value))) if value.size else 0.0,
        }
        for name, value in residuals.items()
    }
    return {"class_key": list(key), "identities": metrics}


def build_task41_v4_volume_only_owner(
    cfg: Any,
    donor: Mapping[str, Any],
    output_directory: str | Path,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    progress_callback: Callable[[Mapping[str, Any]], Any],
    persist_array: Callable[[str, np.ndarray], Mapping[str, Any]],
    geometry_policy: str = "canonical",
    raw_tensor_evaluator_kind: str | None = None,
    ffcx_c_source_path: str | Path | None = None,
    internal_rhs_strategy: str = "stored_T",
    internal_rhs_refinement_max_steps: int = 0,
    levels: Mapping[str, Any] | None = None,
    volume_form: Any | None = None,
    compiled_form: Any | None = None,
    appended_support_owned_cell_groups: Sequence[Sequence[int]] | None = None,
    appended_support_group_by_row: Sequence[int] | None = None,
    persist_selected_evidence: bool = True,
    reserved_followup_evidence_bytes: int = 0,
    required_prefix_cells: Sequence[int] = (),
    prefix_cell_validator: Callable[
        [int, np.ndarray, Mapping[str, np.ndarray], Mapping[str, Any]], Mapping[str, Any]
    ]
    | None = None,
    exact_cell_observer: Callable[
        [int, np.ndarray, Mapping[str, np.ndarray], Mapping[str, Any]], None
    ]
    | None = None,
) -> dict[str, Any]:
    """Build one fresh MPI1 volume owner and persist only selected local evidence.

    ``donor`` is a normalized read-only view of the existing recovery manifest:
    it has ``manifest``, ``manifest_sha256``, ``existing_evidence_bytes``, two
    ``columns`` (active/slave rows, known field, native RHS), three
    ``raw_classes`` (``class_key``, ``Vii``, ``Vit``), and six ``cell_maps``
    (rows, active IDs, permutation, and CSR expansion arrays).  It never copies
    those donor arrays.  On success the returned ``condensed`` owner remains
    alive for the caller's later full-domain identity audit and cleanup.
    """

    if not all(callable(item) for item in (allocation_gate, progress_callback, persist_array)):
        raise TypeError("Task41 V4 requires allocation, progress, and persistence callbacks")
    if geometry_policy not in {"canonical", "mesh_actual_exact"}:
        raise ValueError(f"unknown Task41 geometry policy {geometry_policy!r}")
    if raw_tensor_evaluator_kind not in {None, "actual_qmetric_blocked_gram"}:
        raise ValueError(
            f"unknown Task41 raw-tensor evaluator {raw_tensor_evaluator_kind!r}"
        )
    if raw_tensor_evaluator_kind is not None and geometry_policy != "mesh_actual_exact":
        raise ValueError("actual q-metric evaluation requires mesh_actual_exact geometry")
    if (raw_tensor_evaluator_kind is None) != (ffcx_c_source_path is None):
        raise ValueError(
            "--ffcx-c-source is required exactly when an actual q-metric evaluator is selected"
        )
    if internal_rhs_strategy not in {"stored_T", "same_lu_rhs_solve"}:
        raise ValueError(f"unknown Task41 internal RHS strategy {internal_rhs_strategy!r}")
    if (
        isinstance(internal_rhs_refinement_max_steps, bool)
        or not isinstance(internal_rhs_refinement_max_steps, int)
        or internal_rhs_refinement_max_steps not in (0, 2)
        or (internal_rhs_refinement_max_steps and internal_rhs_strategy != "same_lu_rhs_solve")
    ):
        raise ValueError("Task41 volume-owner same-LU refinement must be 0 or 2")
    reused_setup = levels is not None or volume_form is not None or compiled_form is not None
    if reused_setup and (levels is None or volume_form is None):
        raise ValueError("reused Task41 FE construction requires both levels and volume_form")
    if compiled_form is not None and not reused_setup:
        raise ValueError("compiled_form can only be reused with its levels and volume_form")
    if (appended_support_owned_cell_groups is None) != (appended_support_group_by_row is None):
        raise ValueError("reused Task41 port support requires both cell groups and row groups")
    manifest = donor["manifest"]
    if donor.get("manifest_sha256") != TASK41_V4_DONOR_MANIFEST_SHA256:
        raise ValueError("Task41 V4 donor recovery-manifest identity differs")
    donor_existing_bytes = int(donor.get("existing_evidence_bytes", -1))
    if donor_existing_bytes != TASK41_V4_DONOR_NPY_BYTES:
        raise ValueError("Task41 V4 donor NPY byte count differs from the frozen 141-array set")
    existing_bytes = donor_existing_bytes + int(donor.get("prior_new_evidence_bytes", 0))
    if (
        isinstance(reserved_followup_evidence_bytes, bool)
        or not isinstance(reserved_followup_evidence_bytes, (int, np.integer))
        or int(reserved_followup_evidence_bytes) < 0
    ):
        raise ValueError("reserved Task41 follow-up evidence bytes must be a non-negative integer")
    reserved_followup_evidence_bytes = int(reserved_followup_evidence_bytes)
    if existing_bytes + reserved_followup_evidence_bytes > TASK41_V4_EVIDENCE_CAP_BYTES:
        raise MemoryError("Task41 V4 owner plus reserved follow-up evidence exceeds the 16 GiB cap")
    preflight_path = Path(output_directory)
    preflight_probe = preflight_path if preflight_path.exists() else preflight_path.parent
    while not preflight_probe.exists() and preflight_probe != preflight_probe.parent:
        preflight_probe = preflight_probe.parent
    preflight_free_bytes = int(shutil.disk_usage(preflight_probe).free)
    if preflight_free_bytes - reserved_followup_evidence_bytes < TASK41_V4_FREE_SPACE_FLOOR_BYTES:
        raise OSError("Task41 follow-up evidence reservation would breach the 2 GiB free-space floor")
    allocation_gate(
        "task41_v4_initial_followup_evidence_reservation",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 0,
            "existing_evidence_bytes": existing_bytes,
            "reserved_followup_evidence_bytes": reserved_followup_evidence_bytes,
            "cumulative_evidence_bytes_upper": existing_bytes + reserved_followup_evidence_bytes,
            "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
            "free_space_bytes": preflight_free_bytes,
            "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
            "before_fresh_volume_owner": True,
        },
    )
    if (
        int(manifest.get("full_storage_rows", -1)) != TASK41_V4_FULL_STORAGE_ROWS
        or int(manifest.get("active_trace_rows", -1)) != TASK41_V4_ACTIVE_TRACE_ROWS
        or int(manifest.get("port_rows", -1)) != TASK41_V4_APPENDED_ROWS
        or len(manifest.get("columns", ())) != 2
    ):
        raise ValueError("Task41 V4 donor manifest has an unexpected B0 layout")
    if (
        manifest.get("local_interior_Bi_Di_exact_zero") is not True
        or manifest.get("local_interior_Bi_Di_nonzero_entry_count") != 0
        or manifest.get("saved_surface_support_certificate_passed") is not True
    ):
        raise ValueError("Task41 V4 donor lacks the saved exact-zero Bi/Di support certificate")
    owner: AssemblyTimeCondensedSystem | None = None
    phase = "fresh_same_mesh_levels"

    def progress(stage: str, status: str, **facts: Any) -> None:
        progress_callback({"phase": stage, "status": status, **facts})

    try:
        if levels is None:
            progress(phase, "STARTED", degree=6, include_positive_coefficients=False)
            levels = _build_same_mesh_levels(
                cfg,
                MPI.COMM_SELF,
                (6,),
                include_positive_coefficients=False,
            )
            progress(phase, "COMPLETED", owned_cells=int(
                levels["mesh"].topology.index_map(3).size_local
            ))
        else:
            for key in ("mesh", "mesh_data", "spaces", "floquets"):
                if key not in levels:
                    raise ValueError(f"reused Task41 FE levels omit {key!r}")
            if 6 not in levels["spaces"] or 6 not in levels["floquets"]:
                raise ValueError("reused Task41 FE levels do not contain degree 6")
            progress(
                phase,
                "REUSED",
                degree=6,
                include_positive_coefficients=False,
                owned_cells=int(levels["mesh"].topology.index_map(3).size_local),
            )

        phase = "direct_volume_form_compile"
        progress(phase, "STARTED")
        space = levels["spaces"][6]
        mesh_data = levels["mesh_data"]
        if volume_form is None:
            trial = ufl.TrialFunction(space)
            test = ufl.TestFunction(space)
            dx = ufl.Measure("dx", domain=levels["mesh"], subdomain_data=mesh_data.cell_tags)
            curl_curl, material_mass = _build_physical_volume_terms(cfg, trial, test, dx)
            volume_form = curl_curl + material_mass
        if compiled_form is None:
            compiled_form = fem.form(
                volume_form,
                jit_options=dict(SAME_MESH_JIT_OPTIONS),
            )
        raw_tensor_evaluator = None
        if raw_tensor_evaluator_kind == "actual_qmetric_blocked_gram":
            from src.solvers.task41_actual_qmetric_blocked_gram import (
                Task41ActualQMetricBlockedGramCandidate,
            )

            raw_tensor_evaluator = Task41ActualQMetricBlockedGramCandidate(
                space.element.basix_element,
                volume_form,
                compiled_form,
                c_source_path=ffcx_c_source_path,
                scratch_directory=output_directory,
            )
        material_identity_by_tag = _task41_material_identity_by_tag(cfg)
        progress(phase, "COMPLETED", construction="curl_plus_mass_only")

        phase = "fresh_volume_owner"
        progress(
            phase,
            "STARTED",
            appended_rows=TASK41_V4_APPENDED_ROWS,
            matrix_materialized=False,
        )
        owner = build_unconstrained_assembly_time_condensation(
            compiled_form,
            space,
            mesh_data.cell_tags,
            mpc=levels["floquets"][6].mpc,
            appended_global_rows=TASK41_V4_APPENDED_ROWS,
            appended_support_owned_cell_groups=appended_support_owned_cell_groups,
            appended_support_group_by_row=appended_support_group_by_row,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            internal_rhs_strategy=internal_rhs_strategy,
            internal_rhs_refinement_max_steps=internal_rhs_refinement_max_steps,
            share_identity_cache=True,
            preserve_exact_geometry=True,
            geometry_policy=geometry_policy,
            geometry_material_identity_by_tag=material_identity_by_tag,
            raw_tensor_evaluator=raw_tensor_evaluator,
            required_prefix_cells=required_prefix_cells,
            prefix_cell_validator=prefix_cell_validator,
            exact_cell_observer=exact_cell_observer,
            allocation_gate=allocation_gate,
        )
        owner.build_audit["geometry_policy"] = geometry_policy
        owner.build_audit["geometry_material_identity_by_tag"] = material_identity_by_tag
        progress(
            phase,
            "COMPLETED",
            active_rows=owner.active_rows,
            slave_rows=owner.trace_constraints.slave_rows,
            class_count=len(owner.interior_lu_by_class),
            retained_cache_bytes=owner.build_audit.get("retained_cache_bytes_local"),
        )

        phase = "donor_identity_validation"
        progress(phase, "STARTED", raw_classes=3, cell_maps=6)
        if (
            owner.full_rows != int(manifest["full_storage_rows"])
            or owner.active_rows != int(manifest["active_trace_rows"])
            or owner.appended_rows != int(manifest["port_rows"])
            or owner.trace_constraints.owned_active_range != (0, owner.active_rows)
        ):
            raise ValueError("fresh Task41 V4 owner layout differs from the saved donor")

        constraints = owner.trace_constraints
        fresh_active = np.asarray(constraints.owned_active_original_dofs)
        mpc = levels["floquets"][6].mpc
        mpc_index_map = space.dofmap.index_map
        local_slave_rows = np.asarray(mpc.slaves, dtype=np.int64).reshape(-1)
        owned_local_slaves = local_slave_rows[
            (local_slave_rows >= 0)
            & (local_slave_rows < int(mpc_index_map.size_local))
        ]
        if len(np.unique(owned_local_slaves)) != len(owned_local_slaves):
            raise ValueError("fresh finalized MPC contains duplicate owned slave rows")
        fresh_slave = np.asarray(
            mpc_index_map.local_to_global(owned_local_slaves.astype(np.int32, copy=False)),
            dtype=np.int64,
        ).reshape(-1)
        fresh_slave.sort()
        if len(fresh_slave) != constraints.slave_rows:
            raise ValueError("fresh finalized MPC slave rows do not match the condensed owner")
        columns = tuple(donor["columns"])
        if len(columns) != 2:
            raise ValueError("Task41 V4 donor must provide the two saved input columns")
        active_name = "active_original_rows"
        slave_name = "slave_rows"
        known_name = "known_field"
        rhs_name = "native_rhs"
        active_saved: np.ndarray | None = None
        slave_saved: np.ndarray | None = None
        for column_index, column in enumerate(columns):
            metadata = manifest["columns"][column_index]["artifacts"]
            active = _check_artifact_array(
                metadata[active_name], column[active_name], f"column {column_index} active rows"
            )
            slave = _check_artifact_array(
                metadata[slave_name], column[slave_name], f"column {column_index} slave rows"
            )
            known = _check_artifact_array(
                metadata[known_name], column[known_name], f"column {column_index} known field"
            )
            rhs = _check_artifact_array(
                metadata[rhs_name], column[rhs_name], f"column {column_index} native RHS"
            )
            if (
                not np.array_equal(active, fresh_active)
                or not np.array_equal(slave, fresh_slave)
                or known.shape != (owner.full_rows,)
                or rhs.shape != (owner.full_rows,)
                or known.dtype != np.dtype(np.complex128)
                or rhs.dtype != np.dtype(np.complex128)
                or np.any(known[slave] != 0.0)
                or np.any(rhs[slave] != 0.0)
            ):
                raise ValueError(f"fresh Task41 V4 numbering or donor vectors differ in column {column_index}")
            if column_index == 0:
                active_saved, slave_saved = active, slave
            elif not (
                np.array_equal(active, active_saved)
                and np.array_equal(slave, slave_saved)
            ):
                raise ValueError("saved Task41 V4 columns disagree on active/slave original rows")

        if (
            int(fresh_active[TASK41_V4_SELECTED_ACTIVE_ROW])
            != TASK41_V4_SELECTED_ORIGINAL_ROW
            or int(constraints.original_to_active[TASK41_V4_SELECTED_ORIGINAL_ROW])
            != TASK41_V4_SELECTED_ACTIVE_ROW
        ):
            raise ValueError("fresh active/storage row identity differs for the frozen target row")

        manifest_cells: dict[tuple[int, int], Mapping[str, Any]] = {}
        manifest_classes: dict[tuple[int, float, float, float, int], Mapping[str, Any]] = {}
        raw_groups = manifest.get("raw_cell_diagnostics", ())
        if len(raw_groups) != 2:
            raise ValueError("Task41 V4 donor does not contain two raw-cell groups")
        for column_index, group in enumerate(raw_groups):
            if (
                group.get("structure_identity_passed") is not True
                or group.get("raw_matrices_are_independently_retabulated") is not True
                or len(group.get("cells", ())) != 3
            ):
                raise ValueError(f"Task41 V4 donor raw group {column_index} is incomplete")
            for cell in group["cells"]:
                cell_index = int(cell["cell_index"])
                key = _class_key(cell["class_key"])
                manifest_cells[(column_index, cell_index)] = cell
                class_artifacts = cell["class_artifacts"]
                if key in manifest_classes:
                    existing = manifest_classes[key]
                    if any(
                        existing[name].get("path") != class_artifacts[name].get("path")
                        for name in ("Vii", "Vit")
                    ):
                        raise ValueError(f"saved matrices are not shared for class {key!r}")
                else:
                    manifest_classes[key] = class_artifacts

        raw_classes = tuple(donor["raw_classes"])
        raw_by_key = {_class_key(item["class_key"]): item for item in raw_classes}
        if len(raw_classes) != 3 or len(raw_by_key) != 3 or set(raw_by_key) != set(manifest_classes):
            raise ValueError("Task41 V4 donor raw class set differs from its six cell maps")
        cell_maps = {
            (int(item["column"]), int(item["cell_index"])): item
            for item in donor["cell_maps"]
        }
        if len(cell_maps) != 6 or set(cell_maps) != set(manifest_cells):
            raise ValueError("Task41 V4 donor must provide exactly the six manifested cell maps")

        owner_cells_by_class: dict[tuple[Any, ...], int] = {}
        for cell_index, cell in enumerate(owner.cell_recovery_maps):
            owner_cells_by_class.setdefault(_class_key(cell.class_key), cell_index)
        fresh_class_records: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        dimension = int(space.element.space_dimension)
        raw_class_workspace_bytes = (
            4 * dimension * dimension * np.dtype(np.complex128).itemsize
        )

        def independently_tabulate(
            cell_index: int,
            class_key: tuple[Any, ...],
            *,
            geometry_policy: str | None = None,
        ):
            allocation_gate(
                "task41_v4_raw_class_retabulation",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": raw_class_workspace_bytes,
                    "cell_index": int(cell_index),
                    "class_key": class_key,
                    "workspace_model": "four complex128 local dimension-squared tensors",
                },
            )
            return tabulate_volume_audit_cell(
                compiled_form,
                space,
                mesh_data.cell_tags,
                owner,
                cell_index,
                geometry_policy=geometry_policy,
            )

        canonical_representative_by_key: dict[tuple[Any, ...], int] = {}
        for saved in cell_maps.values():
            canonical_representative_by_key.setdefault(
                _class_key(saved["class_key"]), int(saved["cell_index"])
            )
        for key, saved_class in raw_by_key.items():
            if geometry_policy == "canonical" and key not in owner_cells_by_class:
                raise ValueError(f"fresh owner is missing saved raw class {key!r}")
            saved_vii = _check_artifact_array(
                manifest_classes[key]["Vii"], saved_class["Vii"], f"saved Vii class {key!r}"
            )
            saved_vit = _check_artifact_array(
                manifest_classes[key]["Vit"], saved_class["Vit"], f"saved Vit class {key!r}"
            )
            representative = (
                owner_cells_by_class[key]
                if geometry_policy == "canonical"
                else canonical_representative_by_key.get(key)
            )
            if representative is None:
                raise ValueError(f"V4 donor has no cell map representative for class {key!r}")
            fresh = independently_tabulate(
                representative,
                key,
                geometry_policy=("canonical" if geometry_policy == "mesh_actual_exact" else None),
            )
            if not (np.array_equal(saved_vii, fresh["K"]) and np.array_equal(saved_vit, fresh["G"])):
                raise ValueError(f"fresh independent K/G differ from saved class {key!r}")
            fresh_class_records[key] = fresh

        local_class_identities = []
        if geometry_policy == "canonical":
            for key in sorted(fresh_class_records):
                local_class_identities.append(
                    _local_class_identity(
                        key,
                        fresh_class_records[key],
                        T=owner.trace_from_interior_rhs_by_class[key],
                        R=owner.interior_from_trace_by_class[key],
                        S=owner.retained_local_schur_by_class[key],
                    )
                )

        for identity, saved in cell_maps.items():
            column_index, cell_index = identity
            manifest_cell = manifest_cells[identity]
            key = _class_key(saved["class_key"])
            cell = owner.cell_recovery_maps[cell_index]
            if key != _class_key(manifest_cell["class_key"]):
                raise ValueError(f"V4 donor/manifest canonical class identity differs for cell {identity}")
            if geometry_policy == "canonical" and key != _class_key(cell.class_key):
                raise ValueError(f"fresh canonical Task41 class identity differs for cell {identity}")
            if geometry_policy == "mesh_actual_exact" and int(cell.class_key[-1]) != key[-1]:
                raise ValueError(f"fresh exact Task41 orientation differs from the V4 map for cell {identity}")
            arrays_meta = manifest_cell["artifacts"]
            for field, name in (
                ("interior_original_rows", "interior_original_rows"),
                ("trace_original_rows", "trace_original_rows"),
                ("active_ids", "active_ids"),
                ("cell_permutation_info", "cell_permutation_info"),
                ("trace_expansion_data", "trace_expansion_data"),
                ("trace_expansion_indices", "trace_expansion_indices"),
                ("trace_expansion_indptr", "trace_expansion_indptr"),
            ):
                _check_artifact_array(arrays_meta[name], saved[field], f"saved cell {identity} {field}")
            if (
                not np.array_equal(
                    saved["interior_original_rows"], cell.interior_original_dofs
                )
                or not np.array_equal(saved["trace_original_rows"], cell.trace_original_dofs)
                or int(np.asarray(saved["cell_permutation_info"]).reshape(-1)[0]) != key[-1]
            ):
                raise ValueError(f"fresh Task41 V4 original rows or direction differ for cell {identity}")
            active_ids, fresh_E, _identity = _cell_trace_expansion(
                cell.trace_original_dofs,
                constraints,
            )
            if not np.array_equal(saved["active_ids"], active_ids):
                raise ValueError(f"fresh Task41 V4 active IDs differ for cell {identity}")
            saved_E = sparse.csr_matrix(
                (
                    saved["trace_expansion_data"],
                    saved["trace_expansion_indices"],
                    saved["trace_expansion_indptr"],
                ),
                shape=(len(cell.trace_original_dofs), len(saved["active_ids"])),
            )
            if not _csr_equal(saved_E, fresh_E):
                raise ValueError(f"fresh Task41 V4 MPC expansion differs for cell {identity}")
        progress(phase, "COMPLETED", active_rows=len(fresh_active), slave_rows=len(fresh_slave))

        phase = "selected_active_row_incidence"
        progress(phase, "STARTED", active_row=TASK41_V4_SELECTED_ACTIVE_ROW)
        selected_cells = list(
            iter_selected_volume_audit_cells(owner, [TASK41_V4_SELECTED_ACTIVE_ROW])
        )
        if not selected_cells:
            raise ValueError("fresh owner has no cells incident to the selected active row")
        selected_classes = tuple(dict.fromkeys(record["class_key"] for record in selected_cells))
        progress(
            phase,
            "COMPLETED",
            incident_cells=len(selected_cells),
            incident_classes=len(selected_classes),
        )

        phase = "evidence_budget_preflight"
        arrays_by_class: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        for class_key in selected_classes:
            record = fresh_class_records.get(class_key)
            if record is None:
                representative = next(
                    cell["cell_index"]
                    for cell in selected_cells
                    if cell["class_key"] == class_key
                )
                record = independently_tabulate(
                    representative,
                    class_key,
                    geometry_policy=("mesh_actual_exact" if geometry_policy == "mesh_actual_exact" else None),
                )
                fresh_class_records[class_key] = record
            arrays_by_class[class_key] = record

        if geometry_policy == "mesh_actual_exact":
            for key in selected_classes:
                local_class_identities.append(
                    _local_class_identity(
                        key,
                        arrays_by_class[key],
                        T=owner.trace_from_interior_rhs_by_class[key],
                        R=owner.interior_from_trace_by_class[key],
                        S=owner.retained_local_schur_by_class[key],
                    )
                )

        class_cache_bytes = 0
        for class_key in selected_classes:
            lu, pivots = owner.interior_lu_by_class[class_key]
            class_cache_bytes += sum(
                value.nbytes
                for value in (
                    owner.trace_from_interior_rhs_by_class[class_key],
                    owner.interior_from_trace_by_class[class_key],
                    owner.retained_local_schur_by_class[class_key],
                    lu,
                    pivots,
                )
            )
        block_bytes = sum(
            record[name].nbytes
            for record in arrays_by_class.values()
            for name in ("K", "G", "J", "L")
        )
        map_arrays = [
            array
            for cell in selected_cells
            for array in (
                cell["interior_original_dofs"],
                cell["trace_original_dofs"],
                cell["active_ids"],
                cell["E"].data,
                cell["E"].indices,
                cell["E"].indptr,
            )
        ]
        map_bytes = sum(array.nbytes for array in map_arrays)
        array_count = 9 * len(selected_classes) + 6 * len(selected_cells)
        selected_evidence_upper = (
            class_cache_bytes + block_bytes + map_bytes + array_count * 4096 + 1_048_576
            if persist_selected_evidence
            else 0
        )
        new_evidence_upper = selected_evidence_upper + reserved_followup_evidence_bytes
        cumulative_upper = existing_bytes + new_evidence_upper
        if cumulative_upper > TASK41_V4_EVIDENCE_CAP_BYTES:
            raise MemoryError(
                f"Task41 V4 evidence cap exceeded: {cumulative_upper} > "
                f"{TASK41_V4_EVIDENCE_CAP_BYTES} bytes"
            )
        output_path = Path(output_directory)
        disk_probe = output_path if output_path.exists() else output_path.parent
        while not disk_probe.exists() and disk_probe != disk_probe.parent:
            disk_probe = disk_probe.parent
        free_bytes = int(shutil.disk_usage(disk_probe).free)
        if free_bytes - new_evidence_upper < TASK41_V4_FREE_SPACE_FLOOR_BYTES:
            raise OSError("Task41 V4 volume evidence would breach the 2 GiB free-space floor")

        peak_workspace = class_cache_bytes + 3 * dimension * dimension * np.dtype(np.complex128).itemsize
        allocation_gate(
            "task41_v4_volume_only_evidence_preflight",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": peak_workspace,
                "incident_cells": len(selected_cells),
                "incident_classes": len(selected_classes),
                "existing_donor_bytes": existing_bytes,
                "new_evidence_bytes_upper": new_evidence_upper,
                "selected_evidence_bytes_upper": selected_evidence_upper,
                "reserved_followup_evidence_bytes": reserved_followup_evidence_bytes,
                "cumulative_evidence_bytes_upper": cumulative_upper,
                "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
                "free_space_bytes": free_bytes,
                "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
                "donor_arrays_copied": False,
                "selected_evidence_persisted": bool(persist_selected_evidence),
            },
        )
        progress(
            phase,
            "COMPLETED",
            existing_bytes=existing_bytes,
            new_bytes_upper=new_evidence_upper,
            cumulative_bytes_upper=cumulative_upper,
            free_bytes=free_bytes,
        )

        phase = "selected_volume_class_and_map_persist"
        progress(
            phase,
            "STARTED" if persist_selected_evidence else "REUSED_NO_DUPLICATE_PERSIST",
            classes=len(selected_classes),
            cells=len(selected_cells),
        )

        def persist(name: str, array: np.ndarray) -> Mapping[str, Any]:
            return persist_array(name, np.asarray(array))

        class_records = []
        persisted_bytes = 0
        for class_key in selected_classes:
            class_digest = hashlib.sha256(repr(class_key).encode("ascii")).hexdigest()[:16]
            raw = arrays_by_class[class_key]
            lu, pivots = owner.interior_lu_by_class[class_key]
            payloads = {
                "K": raw["K"],
                "G": raw["G"],
                "J": raw["J"],
                "L": raw["L"],
                "T": owner.trace_from_interior_rhs_by_class[class_key],
                "R": owner.interior_from_trace_by_class[class_key],
                "S": owner.retained_local_schur_by_class[class_key],
                "LU_factor": lu,
                "LU_pivots": pivots,
            }
            artifacts = {}
            if persist_selected_evidence:
                for name, array in payloads.items():
                    artifact = persist(
                        f"task41_v4_volume_class_{class_digest}_{name}",
                        np.asarray(array),
                    )
                    artifacts[name] = dict(artifact)
                    persisted_bytes += int(artifact.get("bytes", array.nbytes + 4096))
            class_records.append(
                {
                    "class_key": class_key,
                    "representative_cell": raw["cell_index"],
                    "hashes": dict(raw["hashes"]),
                    "artifacts": artifacts,
                }
            )

        cell_records = []
        for cell in selected_cells:
            cell_index = int(cell["cell_index"])
            payloads = {
                "interior_original_rows": cell["interior_original_dofs"],
                "trace_original_rows": cell["trace_original_dofs"],
                "active_ids": cell["active_ids"],
                "trace_expansion_data": cell["E"].data,
                "trace_expansion_indices": cell["E"].indices,
                "trace_expansion_indptr": cell["E"].indptr,
            }
            artifacts = {}
            if persist_selected_evidence:
                for name, array in payloads.items():
                    artifact = persist(
                        f"task41_v4_volume_cell_{cell_index:05d}_{name}",
                        np.asarray(array),
                    )
                    artifacts[name] = dict(artifact)
                    persisted_bytes += int(artifact.get("bytes", array.nbytes + 4096))
            cell_records.append(
                {
                    "cell_index": cell_index,
                    "class_key": cell["class_key"],
                    "original_row_identity_passed": True,
                    "artifacts": artifacts,
                }
            )
        if (
            existing_bytes + reserved_followup_evidence_bytes + persisted_bytes
            > TASK41_V4_EVIDENCE_CAP_BYTES
        ):
            raise MemoryError("Task41 V4 persisted evidence exceeded its cumulative 16 GiB cap")
        progress(
            phase,
            "COMPLETED",
            persisted_bytes=persisted_bytes,
            cumulative_bytes=existing_bytes + persisted_bytes,
            class_records=len(class_records),
            cell_records=len(cell_records),
        )
        return {
            "levels": levels,
            "compiled_form": compiled_form,
            "condensed": owner,
            "class_records": tuple(class_records),
            "cell_records": tuple(cell_records),
            "audit": {
                "donor_manifest_sha256": donor["manifest_sha256"],
                "fresh_active_rows_match": True,
                "fresh_slave_rows_match": True,
                "saved_raw_class_count_verified": len(raw_by_key),
                "saved_cell_map_count_verified": len(cell_maps),
                "selected_active_row": TASK41_V4_SELECTED_ACTIVE_ROW,
                "selected_original_row": TASK41_V4_SELECTED_ORIGINAL_ROW,
                "donor_arrays_copied": False,
                "matrix_materialized": False,
                "surface_or_carrier_constructed": False,
                "selected_evidence_persisted": bool(persist_selected_evidence),
                "reserved_followup_evidence_bytes": reserved_followup_evidence_bytes,
                "local_class_identities": local_class_identities,
                "evidence_bytes_existing": existing_bytes,
                "evidence_bytes_added": persisted_bytes,
                "evidence_bytes_cumulative": existing_bytes + persisted_bytes,
            },
        }
    except Exception as exc:
        progress(phase, "FAILED", error=f"{type(exc).__name__}: {exc}")
        if owner is not None:
            owner.destroy()
        raise


def _task41_v9_array_sha256(values: np.ndarray) -> str:
    array = np.asarray(values)
    if not array.flags.c_contiguous:
        array = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _task41_v9_chunked_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    left = np.asarray(left)
    right = np.asarray(right)
    if left.shape != right.shape:
        raise ValueError("Task41 V9 compact comparison arrays have different shapes")
    square = 0.0
    reference_square = 0.0
    max_abs = 0.0
    max_row = None
    for start in range(0, left.size, 262_144):
        stop = min(left.size, start + 262_144)
        a = np.asarray(left[start:stop], dtype=np.complex128)
        b = np.asarray(right[start:stop], dtype=np.complex128)
        delta = a - b
        square += float(np.vdot(delta, delta).real)
        reference_square += float(np.vdot(b, b).real)
        if delta.size:
            position = int(np.argmax(np.abs(delta)))
            value = float(abs(delta[position]))
            if value > max_abs:
                max_abs = value
                max_row = start + position
    return {
        "absolute_l2": float(np.sqrt(max(0.0, square))),
        "reference_l2": float(np.sqrt(max(0.0, reference_square))),
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _task41_v9_compact_volume_identity(
    owner: AssemblyTimeCondensedSystem,
    donor: Mapping[str, Any],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    progress_callback: Callable[[Mapping[str, Any]], Any],
    persist_array: Callable[[str, np.ndarray], Mapping[str, Any]],
    output_directory: str | Path,
    native_volume_apply: Callable[[np.ndarray], np.ndarray] | None,
    artifact_prefix: str | None,
    candidate_identity: str | None,
    candidate_cache_identity: str | None,
    recovery_refinement_max_steps: int,
    reserved_followup_evidence_bytes: int,
) -> dict[str, Any]:
    """Replay the two full volume actions and retain compact recovery evidence."""

    if (
        owner.build_audit.get("geometry_policy") != "mesh_actual_exact"
        or getattr(owner, "internal_rhs_strategy", None) != "same_lu_rhs_solve"
        or int(owner.appended_rows) != TASK41_V4_APPENDED_ROWS
        or not callable(native_volume_apply)
    ):
        raise ValueError("Task41 V9 requires the live exact-geometry same-LU owner and native volume action")
    if (
        isinstance(recovery_refinement_max_steps, bool)
        or not isinstance(recovery_refinement_max_steps, (int, np.integer))
        or not 0 <= int(recovery_refinement_max_steps) <= 3
    ):
        raise ValueError("Task41 V9 same-LU recovery refinement must be bounded to 0..3 steps")
    recovery_refinement_max_steps = int(recovery_refinement_max_steps)
    if int(reserved_followup_evidence_bytes) != TASK41_V9_COMPACT_EVIDENCE_RESERVE_BYTES:
        raise ValueError("Task41 V9 compact evidence must use its frozen full reservation")

    columns = tuple(donor.get("columns", ()))
    joint = donor.get("attribution", {}).get("joint", {})
    saved_p6 = np.asarray(joint.get("p6_result"))
    saved_reduced = np.asarray(joint.get("reduced_rhs"))
    saved_port_rhs = np.asarray(joint.get("port_rhs"))
    active_rows = int(owner.active_rows)
    port_rows = int(owner.appended_rows)
    full_rows = int(owner.full_rows)
    candidate_rows = active_rows + port_rows
    if (
        len(columns) != 2
        or active_rows != TASK41_V4_ACTIVE_TRACE_ROWS
        or port_rows != TASK41_V4_APPENDED_ROWS
        or full_rows != TASK41_V4_FULL_STORAGE_ROWS
        or saved_p6.shape != (candidate_rows, 2)
        or saved_reduced.shape != saved_p6.shape
        or saved_port_rhs.shape != (port_rows, 2)
        or any(
            value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all()
            for value in (saved_p6, saved_reduced, saved_port_rhs)
        )
    ):
        raise ValueError("Task41 V9 donor and live owner differ from the frozen two-column layout")
    active_original = np.asarray(columns[0]["active_original_rows"])
    slave_rows = np.asarray(columns[0]["slave_rows"])
    if (
        active_original.shape != (active_rows,)
        or active_original.dtype.kind not in "iu"
        or slave_rows.ndim != 1
        or slave_rows.dtype.kind not in "iu"
        or not np.array_equal(
            active_original,
            np.asarray(owner.trace_constraints.owned_active_original_dofs),
        )
        or any(
            not np.array_equal(active_original, np.asarray(column["active_original_rows"]))
            or not np.array_equal(slave_rows, np.asarray(column["slave_rows"]))
            for column in columns[1:]
        )
    ):
        raise ValueError("Task41 V9 donor numbering differs from the live owner")
    if artifact_prefix is None:
        artifact_prefix = "task41_p0_b0_v9_compact_candidate"

    new_evidence_upper = TASK41_V9_COMPACT_EVIDENCE_RESERVE_BYTES
    prior_new_bytes = int(donor.get("prior_new_evidence_bytes", 0))
    existing_bytes = int(donor["existing_evidence_bytes"])
    cumulative_upper = existing_bytes + prior_new_bytes + new_evidence_upper
    if cumulative_upper > TASK41_V4_EVIDENCE_CAP_BYTES:
        raise MemoryError("Task41 V9 compact evidence would exceed the cumulative 16 GiB cap")
    output_path = Path(output_directory)
    disk_probe = output_path if output_path.exists() else output_path.parent
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    free_bytes = int(shutil.disk_usage(disk_probe).free)
    if free_bytes - new_evidence_upper < TASK41_V4_FREE_SPACE_FLOOR_BYTES:
        raise OSError("Task41 V9 compact evidence would breach the 2 GiB free-space floor")

    action_matrix_bytes = 2 * candidate_rows * 2 * np.dtype(np.complex128).itemsize
    recovery_vector_bytes = 6 * full_rows * np.dtype(np.complex128).itemsize
    progress_callback(
        {
            "phase": "task41_v9_compact_volume_identity_preflight",
            "status": "STARTED",
            "full_rows": full_rows,
            "active_rows": active_rows,
            "appended_rows": port_rows,
            "new_evidence_bytes_upper": new_evidence_upper,
            "cumulative_evidence_bytes_upper": cumulative_upper,
            "free_space_bytes": free_bytes,
        }
    )
    allocation_gate(
        "task41_v9_compact_volume_identity_and_recovery",
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": (
                4 * full_rows * np.dtype(np.complex128).itemsize
                + action_matrix_bytes
                + 2 * active_rows * np.dtype(np.complex128).itemsize
            ),
            "new_evidence_bytes_upper": new_evidence_upper,
            "candidate_full_action_array_bytes": action_matrix_bytes,
            "initial_final_residual_storage_bytes_upper": recovery_vector_bytes,
            "cumulative_evidence_bytes_upper": cumulative_upper,
            "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
            "free_space_bytes": free_bytes,
            "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
            "native_volume_action_calls_upper": 8,
            "maximum_same_lu_corrections_per_column": recovery_refinement_max_steps,
            "ports_scanned_or_replayed": False,
        },
    )

    volume_owner = replace(owner, appended_rows=0, owned_appended_rows=0)
    action = P6CellCondensedAction(volume_owner, H_p=np.zeros((0, 0), dtype=np.complex128))
    candidate_p6 = np.array(saved_p6, dtype=np.complex128, copy=True, order="C")
    candidate_reduced = np.array(saved_reduced, dtype=np.complex128, copy=True, order="C")
    persisted_bytes = 0
    artifacts: list[dict[str, Any]] = []
    column_reports: list[dict[str, Any]] = []

    def persist(name: str, values: np.ndarray) -> dict[str, Any]:
        nonlocal persisted_bytes
        record = dict(persist_array(name, np.asarray(values)))
        if not all(key in record for key in ("path", "bytes", "sha256", "shape", "dtype")):
            raise ValueError("Task41 V9 persistence callback returned an incomplete artifact binding")
        persisted_bytes += int(record["bytes"])
        if (
            persisted_bytes > new_evidence_upper
            or existing_bytes + prior_new_bytes + persisted_bytes > TASK41_V4_EVIDENCE_CAP_BYTES
        ):
            raise MemoryError("Task41 V9 compact output exceeded its admitted evidence reservation")
        artifact = {"name": name, **record}
        artifacts.append(artifact)
        return artifact

    def any_nonzero(values: np.ndarray, rows: np.ndarray) -> bool:
        for start in range(0, rows.size, 262_144):
            if np.any(np.asarray(values[rows[start : start + 262_144]]) != 0.0):
                return True
        return False

    try:
        prepared_columns: list[dict[str, Any]] = []
        for column_index, column in enumerate(columns):
            known = np.asarray(column["known_field"])
            native_rhs = np.asarray(column["native_rhs"])
            volume_rhs = np.asarray(column["native_volume_rhs"])
            b_rows = np.asarray(column["b_alpha_rows"])
            b_values = np.asarray(column["b_alpha_values"])
            if (
                known.shape != (full_rows,)
                or native_rhs.shape != (full_rows,)
                or volume_rhs.shape != (full_rows,)
                or any(
                    value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all()
                    for value in (known, native_rhs, volume_rhs)
                )
                or b_rows.ndim != 1
                or b_rows.dtype.kind not in "iu"
                or b_values.shape != b_rows.shape
                or b_values.dtype != np.dtype(np.complex128)
                or not np.isfinite(b_values).all()
                or (b_rows.size and (int(b_rows.min()) < 0 or int(b_rows.max()) >= full_rows))
                or any_nonzero(known, slave_rows)
                or any_nonzero(native_rhs, slave_rows)
                or any_nonzero(volume_rhs, slave_rows)
            ):
                raise ValueError(f"Task41 V9 donor column {column_index} has invalid full-space vectors")
            b_active = np.empty(b_rows.size, dtype=np.int64)
            for position, original_row in enumerate(b_rows):
                active_id = owner.trace_constraints.original_to_active.get(int(original_row))
                if active_id is None:
                    raise ValueError("Task41 V9 B-alpha row is not an independent active trace row")
                b_active[position] = int(active_id)

            progress_callback(
                {"phase": "task41_v9_full_action", "status": "STARTED", "column": column_index}
            )
            active_source = np.array(known[active_original], dtype=np.complex128, copy=True)
            full_trace_action = action.apply(active_source)
            full_trace_rhs = action.reduce_rhs(native_rhs, rhs_is_mpc_dual=True)
            if (
                full_trace_action.shape != (active_rows,)
                or full_trace_rhs.shape != (active_rows,)
                or not np.isfinite(full_trace_action).all()
                or not np.isfinite(full_trace_rhs).all()
            ):
                raise ValueError("Task41 V9 P6 action/reducer returned an invalid full trace")
            np.add.at(full_trace_action, b_active, b_values)
            candidate_p6[:active_rows, column_index] = full_trace_action
            candidate_reduced[:active_rows, column_index] = full_trace_rhs
            prepared_columns.append(
                {
                    "column": column,
                    "known": known,
                    "volume_rhs": volume_rhs,
                }
            )
            progress_callback(
                {"phase": "task41_v9_full_action", "status": "COMPLETED", "column": column_index}
            )
            del active_source, full_trace_action, full_trace_rhs

        port_action_unchanged = np.array_equal(candidate_p6[active_rows:], saved_p6[active_rows:])
        port_reduced_unchanged = np.array_equal(candidate_reduced[active_rows:], saved_reduced[active_rows:])
        port_rhs_unchanged = np.array_equal(candidate_p6[active_rows:], saved_port_rhs) and np.array_equal(
            candidate_reduced[active_rows:], saved_port_rhs
        )
        full_p6_ref = persist(f"{artifact_prefix}_full_p6", candidate_p6)
        full_reduced_ref = persist(f"{artifact_prefix}_full_reduced_rhs", candidate_reduced)
        action_columns = []
        for column_index, frozen_denominator in enumerate(TASK41_V5_FROZEN_DENOMINATORS):
            difference = _task41_v9_chunked_metrics(
                candidate_p6[:, column_index], candidate_reduced[:, column_index]
            )
            dynamic_denom = max(
                _vector_norm(candidate_p6[:, column_index]),
                _vector_norm(candidate_reduced[:, column_index]),
                np.finfo(float).tiny,
            )
            dynamic_relative = difference["absolute_l2"] / dynamic_denom
            frozen_relative = difference["absolute_l2"] / frozen_denominator
            action_columns.append(
                {
                    "column": column_index,
                    "difference": difference,
                    "dynamic_denominator": dynamic_denom,
                    "dynamic_denominator_relative": dynamic_relative,
                    "frozen_denominator": frozen_denominator,
                    "frozen_denominator_relative": frozen_relative,
                    "dynamic_gate_passed": bool(
                        dynamic_relative <= TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE
                    ),
                    "frozen_gate_passed": bool(
                        frozen_relative <= TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE
                    ),
                }
            )
        action_passed = bool(
            port_action_unchanged
            and port_reduced_unchanged
            and port_rhs_unchanged
            and all(item["dynamic_gate_passed"] and item["frozen_gate_passed"] for item in action_columns)
        )
        candidate_action_gate = {
            "status": "PASS" if action_passed else "GATE_FAILED",
            "relative_tolerance": TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE,
            "columns": action_columns,
            "full_action_artifact": full_p6_ref,
            "full_reduced_rhs_artifact": full_reduced_ref,
            "saved_port_rows_unchanged": bool(
                port_action_unchanged and port_reduced_unchanged and port_rhs_unchanged
            ),
        }
        progress_callback(
            {
                "phase": "task41_v9_full_action_gate",
                "status": "COMPLETED" if action_passed else "GATE_FAILED",
                "action_artifacts_saved_before_recovery": True,
                "columns": action_columns,
            }
        )
        if not action_passed:
            return {
                "schema": "task41.p0.b0.v9.compact_volume_identity.v1",
                "status": "GATE_FAILED",
                "completed": True,
                "official_result": False,
                "candidate_evaluator_identity": candidate_identity,
                "candidate_evaluator_cache_identity": candidate_cache_identity,
                "donor_manifest_sha256": str(donor["manifest_sha256"]),
                "existing_evidence_bytes": existing_bytes,
                "prior_new_evidence_bytes": prior_new_bytes,
                "internal_rhs_strategy": "same_lu_rhs_solve",
                "geometry_policy": "mesh_actual_exact",
                "active_rows": active_rows,
                "appended_rows": port_rows,
                "full_storage_rows": full_rows,
                "global_volume_matrix_materialized": False,
                "dense_port_matrix_materialized": False,
                "surface_or_carrier_replayed": False,
                "saved_port_rows_unchanged": candidate_action_gate["saved_port_rows_unchanged"],
                "new_evidence_bytes_upper": new_evidence_upper,
                "new_evidence_bytes": persisted_bytes,
                "cumulative_evidence_bytes": existing_bytes + prior_new_bytes + persisted_bytes,
                "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
                "free_space_bytes_before_persist": free_bytes,
                "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
                "persisted_artifacts": artifacts,
                "candidate_full_action_gate": candidate_action_gate,
                "candidate_recovery_gate": {
                    "status": "NOT_RUN_ACTION_GATE_FAILED",
                    "relative_forward_tolerance": 1.0e-11,
                    "native_volume_residual_relative_tolerance": 1.0e-10,
                    "maximum_same_lu_corrections_per_column": recovery_refinement_max_steps,
                    "native_volume_action_calls": 0,
                    "columns": [],
                },
            }

        for column_index, prepared in enumerate(prepared_columns):
            column = prepared["column"]
            known = prepared["known"]
            volume_rhs = prepared["volume_rhs"]
            progress_callback(
                {
                    "phase": "task41_v9_same_lu_recovery",
                    "status": "STARTED",
                    "column": column_index,
                    "maximum_corrections": recovery_refinement_max_steps,
                }
            )
            initial_storage = action.recover_storage(
                known[active_original], full_rhs=volume_rhs, expand_trace=False
            )
            initial_volume_action = np.array(
                native_volume_apply(initial_storage), dtype=np.complex128, copy=True
            )
            if (
                initial_volume_action.shape != (full_rows,)
                or not np.isfinite(initial_volume_action).all()
            ):
                raise ValueError("Task41 V9 native volume action returned an invalid initial vector")
            initial_residual = np.asarray(volume_rhs - initial_volume_action, dtype=np.complex128)
            initial_storage_sha256 = _task41_v9_array_sha256(initial_storage)
            initial_ref: dict[str, Any] = {
                "kind": "artifact",
                **persist(f"{artifact_prefix}_initial_storage_col{column_index}", initial_storage),
            }
            step_records: list[dict[str, Any]] = []

            def capture_step(
                step: int,
                storage: np.ndarray,
                _volume_action: np.ndarray,
                residual: np.ndarray,
                facts: Mapping[str, Any],
            ) -> None:
                trace_equal = all(
                    np.array_equal(
                        storage[active_original[start : start + 262_144]],
                        known[active_original[start : start + 262_144]],
                    )
                    for start in range(0, active_rows, 262_144)
                )
                step_records.append(
                    {
                        "step": int(step),
                        "forward_relative_error": facts.get("forward_relative_error"),
                        "native_volume_residual_norm": facts.get("native_volume_residual_norm"),
                        "native_volume_residual_relative": facts.get("native_volume_residual_relative"),
                        "native_internal_residual_relative": facts.get("native_internal_residual_relative"),
                        "native_volume_action_calls": int(step) + 1,
                        "storage_sha256": _task41_v9_array_sha256(storage),
                        "residual_sha256": _task41_v9_array_sha256(residual),
                        "active_trace_unchanged": bool(trace_equal),
                        "slave_rows_zero": not any_nonzero(storage, slave_rows),
                    }
                )

            refined = action.refine_internal_storage_with_native_volume_residual(
                initial_storage,
                volume_rhs,
                native_volume_apply,
                max_steps=recovery_refinement_max_steps,
                initial_volume_action=initial_volume_action,
                initial_residual=initial_residual,
                forward_reference=known,
                on_state=capture_step,
            )
            if _task41_v9_array_sha256(initial_storage) != initial_storage_sha256:
                raise ValueError("Task41 V9 recovery refinement mutated the frozen initial storage")
            final_storage = np.asarray(refined["storage_solution"], dtype=np.complex128)
            final_residual = np.asarray(refined["native_volume_residual"], dtype=np.complex128)
            final_volume_action = np.asarray(refined["native_volume_action"], dtype=np.complex128)
            initial_matches_known = np.array_equal(initial_storage, known)
            if np.array_equal(final_storage, known):
                final_ref: dict[str, Any] = {"kind": "v4_donor_known_field", "column": column_index}
            elif not initial_matches_known and np.array_equal(final_storage, initial_storage):
                final_ref = dict(initial_ref)
            else:
                final_ref = {
                    "kind": "artifact",
                    **persist(f"{artifact_prefix}_final_storage_col{column_index}", final_storage),
                }
            donor_initial_residual = np.asarray(column["states"][0]["native_volume_residual"])
            if np.array_equal(final_residual, donor_initial_residual):
                residual_ref: dict[str, Any] = {
                    "kind": "v4_donor_initial_native_volume_residual",
                    "column": column_index,
                }
            else:
                residual_ref = {
                    "kind": "artifact",
                    **persist(f"{artifact_prefix}_final_native_volume_residual_col{column_index}", final_residual),
                }
            forward = _task41_v9_chunked_metrics(final_storage, known)
            forward_relative = forward["absolute_l2"] / max(
                _vector_norm(known), np.finfo(float).tiny
            )
            residual_norm = _vector_norm(final_residual)
            residual_relative = residual_norm / max(_vector_norm(volume_rhs), np.finfo(float).tiny)
            active_trace_exact = all(
                np.array_equal(
                    final_storage[active_original[start : start + 262_144]],
                    known[active_original[start : start + 262_144]],
                )
                for start in range(0, active_rows, 262_144)
            )
            slave_rows_zero = not any_nonzero(final_storage, slave_rows)
            residual_slave_rows_zero = not any_nonzero(final_residual, slave_rows)
            action_calls = len(step_records)
            recovery_passed = bool(
                np.isfinite(forward_relative)
                and forward_relative <= 1.0e-11
                and np.isfinite(residual_relative)
                and residual_relative <= 1.0e-10
                and active_trace_exact
                and slave_rows_zero
                and residual_slave_rows_zero
                and action_calls <= recovery_refinement_max_steps + 1
            )
            column_reports.append(
                {
                    "column": column_index,
                    "initial_matches_saved_known_field": initial_matches_known,
                    "initial_storage_artifact": initial_ref,
                    "initial_storage_sha256": initial_storage_sha256,
                    "final_storage_artifact": final_ref,
                    "final_native_volume_residual_artifact": residual_ref,
                    "forward_error_absolute_l2": forward["absolute_l2"],
                    "forward_error_relative": forward_relative,
                    "forward_gate_tolerance": 1.0e-11,
                    "native_volume_residual_absolute_l2": residual_norm,
                    "native_volume_residual_relative": residual_relative,
                    "native_volume_residual_gate_tolerance": 1.0e-10,
                    "active_trace_exact": active_trace_exact,
                    "slave_rows_zero": slave_rows_zero,
                    "residual_slave_rows_zero": residual_slave_rows_zero,
                    "native_volume_action_calls": action_calls,
                    "same_lu_corrections": max(0, action_calls - 1),
                    "maximum_same_lu_corrections": recovery_refinement_max_steps,
                    "step_records": step_records,
                    "passed": recovery_passed,
                    "final_storage_sha256": _task41_v9_array_sha256(final_storage),
                    "final_native_residual_sha256": _task41_v9_array_sha256(final_residual),
                    "final_native_action_sha256": _task41_v9_array_sha256(final_volume_action),
                }
            )
            progress_callback(
                {
                    "phase": "task41_v9_same_lu_recovery",
                    "status": "COMPLETED" if recovery_passed else "GATE_FAILED",
                    "column": column_index,
                    "same_lu_corrections": max(0, action_calls - 1),
                    "forward_error_relative": forward_relative,
                    "native_volume_residual_relative": residual_relative,
                }
            )
            del initial_storage, initial_volume_action, initial_residual
            del final_storage, final_residual, final_volume_action, refined

        recovery_passed = len(column_reports) == 2 and all(item["passed"] for item in column_reports)
        result = {
            "schema": "task41.p0.b0.v9.compact_volume_identity.v1",
            "status": "PASS" if action_passed and recovery_passed else "GATE_FAILED",
            "completed": True,
            "official_result": False,
            "candidate_evaluator_identity": candidate_identity,
            "candidate_evaluator_cache_identity": candidate_cache_identity,
            "donor_manifest_sha256": str(donor["manifest_sha256"]),
            "existing_evidence_bytes": existing_bytes,
            "prior_new_evidence_bytes": prior_new_bytes,
            "internal_rhs_strategy": "same_lu_rhs_solve",
            "geometry_policy": "mesh_actual_exact",
            "active_rows": active_rows,
            "appended_rows": port_rows,
            "full_storage_rows": full_rows,
            "global_volume_matrix_materialized": False,
            "dense_port_matrix_materialized": False,
            "surface_or_carrier_replayed": False,
            "saved_port_rows_unchanged": candidate_action_gate["saved_port_rows_unchanged"],
            "new_evidence_bytes_upper": new_evidence_upper,
            "new_evidence_bytes": persisted_bytes,
            "cumulative_evidence_bytes": existing_bytes + prior_new_bytes + persisted_bytes,
            "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
            "free_space_bytes_before_persist": free_bytes,
            "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
            "persisted_artifacts": artifacts,
            "candidate_full_action_gate": candidate_action_gate,
            "candidate_recovery_gate": {
                "status": "PASS" if recovery_passed else "GATE_FAILED",
                "relative_forward_tolerance": 1.0e-11,
                "native_volume_residual_relative_tolerance": 1.0e-10,
                "maximum_same_lu_corrections_per_column": recovery_refinement_max_steps,
                "recovery_source": "saved native_volume_rhs with the current exact-geometry same-LU owner",
                "native_volume_action_calls": sum(item["native_volume_action_calls"] for item in column_reports),
                "columns": column_reports,
            },
        }
        progress_callback(
            {
                "phase": "task41_v9_compact_volume_identity",
                "status": "COMPLETED" if result["status"] == "PASS" else "GATE_FAILED",
                "new_evidence_bytes": persisted_bytes,
                "cumulative_evidence_bytes": result["cumulative_evidence_bytes"],
            }
        )
        return result
    finally:
        action.destroy()


def audit_task41_v4_volume_identity(
    owner: AssemblyTimeCondensedSystem,
    donor: Mapping[str, Any],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    progress_callback: Callable[[Mapping[str, Any]], Any],
    persist_array: Callable[[str, np.ndarray], Mapping[str, Any]],
    output_directory: str | Path,
    native_volume_apply: Callable[[np.ndarray], np.ndarray] | None = None,
    artifact_prefix: str | None = None,
    candidate_identity: str | None = None,
    candidate_cache_identity: str | None = None,
    compact_evidence: bool = False,
    recovery_refinement_max_steps: int = 0,
    reserved_followup_evidence_bytes: int = 0,
) -> dict[str, Any]:
    """Replay the trace-only production P6 action and RHS identities.

    ``donor`` is the checker's normalized view.  The 64,120 saved port rows are
    compared and carried through unchanged; the fresh action view has zero
    appended rows and borrows the same S/T/LU cache from ``owner``.
    """

    if not all(callable(item) for item in (allocation_gate, progress_callback, persist_array)):
        raise TypeError("Task41 V4 identity replay requires allocation, progress, and persistence callbacks")
    if compact_evidence:
        return _task41_v9_compact_volume_identity(
            owner,
            donor,
            allocation_gate=allocation_gate,
            progress_callback=progress_callback,
            persist_array=persist_array,
            output_directory=output_directory,
            native_volume_apply=native_volume_apply,
            artifact_prefix=artifact_prefix,
            candidate_identity=candidate_identity,
            candidate_cache_identity=candidate_cache_identity,
            recovery_refinement_max_steps=recovery_refinement_max_steps,
            reserved_followup_evidence_bytes=reserved_followup_evidence_bytes,
        )
    if reserved_followup_evidence_bytes:
        raise ValueError("follow-up evidence reservation is only valid for compact V9 evidence")
    columns = tuple(donor["columns"])
    identity = donor["attribution"]
    joint = identity["joint"]
    saved_p6 = np.asarray(joint["p6_result"])
    saved_reduced = np.asarray(joint["reduced_rhs"])
    saved_port_rhs = np.asarray(joint["port_rhs"])
    active_rows = int(owner.active_rows)
    port_rows = int(owner.appended_rows)
    full_rows = int(owner.full_rows)
    exact_candidate = owner.build_audit.get("geometry_policy") == "mesh_actual_exact"
    evaluator_audit = owner.build_audit.get("raw_tensor_evaluator")
    if isinstance(evaluator_audit, Mapping):
        if candidate_identity is None:
            candidate_identity = evaluator_audit.get("implementation")
        if candidate_cache_identity is None:
            candidate_cache_identity = evaluator_audit.get("cache_identity")
    if artifact_prefix is None:
        artifact_prefix = (
            "task41_p0_v6_qmetric_candidate"
            if candidate_identity == "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
            else "task41_p0_v5_candidate"
            if exact_candidate
            else "task41_p0_v4_volume"
        )
    if exact_candidate and not callable(native_volume_apply):
        raise ValueError("V5 candidate recovery requires the independent volume-only native action")
    if (
        len(columns) != 2
        or saved_p6.shape != (active_rows + port_rows, 2)
        or saved_reduced.shape != saved_p6.shape
        or saved_port_rhs.shape != (port_rows, 2)
        or any(value.dtype != np.dtype(np.complex128) for value in (saved_p6, saved_reduced, saved_port_rhs))
        or any(not np.isfinite(value).all() for value in (saved_p6, saved_reduced, saved_port_rhs))
    ):
        raise ValueError("Task41 V4 saved full-action arrays differ from the fresh owner layout")

    active_original = np.asarray(columns[0]["active_original_rows"])
    slave_rows = np.asarray(columns[0]["slave_rows"])
    if (
        active_original.shape != (active_rows,)
        or active_original.dtype.kind not in "iu"
        or slave_rows.dtype.kind not in "iu"
        or any(not np.array_equal(active_original, np.asarray(column["active_original_rows"])) for column in columns[1:])
        or any(not np.array_equal(slave_rows, np.asarray(column["slave_rows"])) for column in columns[1:])
    ):
        raise ValueError("Task41 V4 input columns disagree on active/slave storage rows")
    constraints = owner.trace_constraints
    if len(constraints.owned_active_original_dofs) != active_rows:
        raise ValueError("Task41 V4 active original-row map differs from the fresh owner")
    original_to_active = constraints.original_to_active
    if slave_rows.size > 1 and np.any(slave_rows[1:] < slave_rows[:-1]):
        raise ValueError("Task41 V4 saved slave rows are not sorted for safe identity checks")

    def any_nonzero_at_rows(values: np.ndarray, rows: np.ndarray) -> bool:
        for start in range(0, rows.size, 262_144):
            if np.any(np.asarray(values[rows[start : start + 262_144]]) != 0.0):
                return True
        return False

    expansion_by_original = constraints.expansion_by_original
    max_expansion_terms = max(
        (len(item[0]) for item in expansion_by_original.values()), default=1
    )
    index_size = np.asarray(owner.cell_recovery_maps[0].interior_original_dofs).dtype.itemsize
    local_interior_rows = sum(len(cell.interior_original_dofs) for cell in owner.cell_recovery_maps)
    local_trace_rows = sum(len(cell.trace_original_dofs) for cell in owner.cell_recovery_maps)
    cell_count = len(owner.cell_recovery_maps)
    expansion_nnz_upper = local_trace_rows * max_expansion_terms
    action_payload_upper = (
        index_size
        * (
            local_interior_rows
            + 2 * local_trace_rows
            + cell_count
            + 2 * expansion_nnz_upper
        )
        + np.dtype(np.complex128).itemsize * expansion_nnz_upper
        + 512 * cell_count
    )
    candidate_rows = active_rows + port_rows
    candidate_full_bytes = (
        2 * candidate_rows * 2 * np.dtype(np.complex128).itemsize
        if exact_candidate
        else 0
    )
    attribution_accumulator_bytes = (
        TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT
        * active_rows
        * np.dtype(np.complex128).itemsize
        if exact_candidate
        else 0
    )
    identity_output_arrays = (26 if exact_candidate else 14)
    recovery_evidence_bytes = (
        4 * full_rows * np.dtype(np.complex128).itemsize + 4 * 4096
        if exact_candidate
        else 0
    )
    identity_array_bytes = (
        identity_output_arrays * active_rows * np.dtype(np.complex128).itemsize
        + identity_output_arrays * 4096
        + candidate_full_bytes
        + (2 * 4096 if exact_candidate else 0)
        + recovery_evidence_bytes
    )
    prior_new_bytes = int(donor.get("prior_new_evidence_bytes", 0))
    cumulative_evidence_upper = (
        int(donor["existing_evidence_bytes"]) + prior_new_bytes + identity_array_bytes
    )
    if cumulative_evidence_upper > TASK41_V4_EVIDENCE_CAP_BYTES:
        raise MemoryError("Task41 V4 identity evidence would exceed the cumulative 16 GiB cap")
    output_path = Path(output_directory)
    disk_probe = output_path if output_path.exists() else output_path.parent
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    free_bytes = int(shutil.disk_usage(disk_probe).free)
    if free_bytes - identity_array_bytes < TASK41_V4_FREE_SPACE_FLOOR_BYTES:
        raise OSError("Task41 V4 identity evidence would breach the 2 GiB free-space floor")
    vector_workspace = np.dtype(np.complex128).itemsize * (
        (3 if exact_candidate else 1) * full_rows + 4 * (active_rows + 1)
    ) + candidate_full_bytes
    allocation_gate(
        "task41_v4_production_volume_action_preflight",
        {
            "additional_payload_bytes": int(action_payload_upper),
            "workspace_bytes": int(vector_workspace),
            "already_resident_attribution_accumulator_bytes": int(
                attribution_accumulator_bytes
            ),
            "candidate_full_array_bytes": int(candidate_full_bytes),
            "candidate_array_rows": int(candidate_rows),
            "cell_count": cell_count,
            "max_constraint_expansion_terms": max_expansion_terms,
            "active_rows": active_rows,
            "appended_rows_in_action_view": 0,
            "global_matrix_materialized": False,
            "dense_port_block_materialized": False,
            "new_identity_evidence_bytes_upper": identity_array_bytes,
            "identity_output_array_count": identity_output_arrays,
            "persisted_attribution_accumulator_arrays": (12 if exact_candidate else 0),
            "cumulative_evidence_bytes_upper": cumulative_evidence_upper,
            "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
            "free_space_bytes": free_bytes,
            "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
        },
    )
    progress_callback({"phase": "production_volume_action_view", "status": "STARTED"})
    # The shallow dataclass view keeps every numerical owner/cache shared while
    # making the production action trace-only.  Saved port rows stay external.
    volume_owner = replace(owner, appended_rows=0, owned_appended_rows=0)
    action = P6CellCondensedAction(
        volume_owner,
        H_p=np.zeros((0, 0), dtype=np.complex128),
    )
    candidate_p6 = np.array(saved_p6, dtype=np.complex128, copy=True, order="C") if exact_candidate else None
    candidate_reduced = (
        np.array(saved_reduced, dtype=np.complex128, copy=True, order="C")
        if exact_candidate
        else None
    )
    column_metrics = []
    candidate_recovery_columns: list[dict[str, Any]] = []
    replay_artifacts: list[dict[str, Any]] = []
    persisted_bytes = 0

    def persist(name: str, values: np.ndarray) -> None:
        nonlocal persisted_bytes
        artifact = dict(persist_array(name, np.asarray(values)))
        artifact_bytes = int(artifact.get("bytes", np.asarray(values).nbytes + 4096))
        persisted_bytes += artifact_bytes
        if (
            int(donor["existing_evidence_bytes"])
            + prior_new_bytes
            + reserved_followup_evidence_bytes
            + persisted_bytes
            > TASK41_V4_EVIDENCE_CAP_BYTES
        ):
            raise MemoryError("Task41 V4 persisted identity evidence exceeded the cumulative 16 GiB cap")
        replay_artifacts.append({"name": name, **artifact})
        return artifact
    try:
        for column_index, column in enumerate(columns):
            progress_callback({"phase": "production_volume_column", "status": "STARTED", "column": column_index})
            known = np.asarray(column["known_field"])
            native_rhs = np.asarray(column["native_rhs"])
            volume_rhs = np.asarray(column["native_volume_rhs"])
            b_alpha_rows = np.asarray(column["b_alpha_rows"])
            b_alpha_values = np.asarray(column["b_alpha_values"])
            if (
                known.shape != (full_rows,)
                or native_rhs.shape != (full_rows,)
                or volume_rhs.shape != (full_rows,)
                or any(value.dtype != np.dtype(np.complex128) for value in (known, native_rhs, volume_rhs))
                or b_alpha_rows.ndim != 1
                or b_alpha_rows.dtype.kind not in "iu"
                or b_alpha_values.shape != b_alpha_rows.shape
                or b_alpha_values.dtype != np.dtype(np.complex128)
                or not np.isfinite(b_alpha_values).all()
                or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= full_rows)))
                or any_nonzero_at_rows(known, slave_rows)
                or any_nonzero_at_rows(native_rhs, slave_rows)
                or any_nonzero_at_rows(volume_rhs, slave_rows)
            ):
                raise ValueError(f"Task41 V4 column {column_index} has invalid vectors or slave-row support")
            if exact_candidate:
                assert native_volume_apply is not None
                progress_callback(
                    {
                        "phase": "v5_candidate_recovery",
                        "status": "STARTED",
                        "column": column_index,
                        "native_volume_action_calls_before": len(candidate_recovery_columns),
                    }
                )
                candidate_storage = action.recover_storage(
                    known[active_original],
                    full_rhs=volume_rhs,
                    expand_trace=False,
                )
                recovery_difference = _difference_metrics(candidate_storage, known)
                known_norm = _vector_norm(known)
                forward_relative = recovery_difference["absolute_l2"] / max(
                    known_norm, np.finfo(float).tiny
                )
                active_trace_exact = np.array_equal(
                    candidate_storage[active_original], known[active_original]
                )
                slave_rows_zero = not any_nonzero_at_rows(candidate_storage, slave_rows)

                # The runner callback returns an explicitly owned complex128 copy.
                native_volume_action_values = native_volume_apply(candidate_storage)
                if native_volume_action_values.shape != (full_rows,) or not native_volume_action_values.flags.writeable:
                    raise ValueError("V5 native volume action returned an invalid recovery vector")
                native_volume_action_values *= -1.0
                native_volume_action_values += volume_rhs
                native_volume_residual = native_volume_action_values
                rhs_norm = _vector_norm(volume_rhs)
                native_residual_norm = _vector_norm(native_volume_residual)
                native_residual_relative = native_residual_norm / max(
                    rhs_norm, np.finfo(float).tiny
                )
                residual_slave_rows_zero = not any_nonzero_at_rows(
                    native_volume_residual, slave_rows
                )
                forward_gate_passed = bool(
                    np.isfinite(forward_relative) and forward_relative <= 1.0e-11
                )
                native_residual_gate_passed = bool(
                    np.isfinite(native_residual_relative)
                    and native_residual_relative <= 1.0e-10
                )
                column_recovery_passed = bool(
                    forward_gate_passed
                    and native_residual_gate_passed
                    and active_trace_exact
                    and slave_rows_zero
                    and residual_slave_rows_zero
                )
                recovered_name = f"{artifact_prefix}_recovered_storage_col{column_index}"
                residual_name = f"{artifact_prefix}_native_volume_residual_col{column_index}"
                recovered_artifact = dict(persist(recovered_name, candidate_storage))
                residual_artifact = dict(persist(residual_name, native_volume_residual))
                candidate_recovery_columns.append(
                    {
                        "column": column_index,
                        "forward_error_absolute_l2": recovery_difference["absolute_l2"],
                        "forward_error_relative": forward_relative,
                        "forward_gate_tolerance": 1.0e-11,
                        "forward_gate_passed": forward_gate_passed,
                        "native_volume_residual_absolute_l2": native_residual_norm,
                        "native_volume_residual_relative": native_residual_relative,
                        "native_volume_residual_gate_tolerance": 1.0e-10,
                        "native_volume_residual_gate_passed": native_residual_gate_passed,
                        "active_trace_exact": active_trace_exact,
                        "slave_rows_zero": slave_rows_zero,
                        "residual_slave_rows_zero": residual_slave_rows_zero,
                        "passed": column_recovery_passed,
                        "recovered_storage_artifact": {
                            "name": recovered_name,
                            **recovered_artifact,
                        },
                        "native_volume_residual_artifact": {
                            "name": residual_name,
                            **residual_artifact,
                        },
                    }
                )
                progress_callback(
                    {
                        "phase": "v5_candidate_recovery",
                        "status": "COMPLETED" if column_recovery_passed else "GATE_FAILED",
                        "column": column_index,
                        "forward_error_relative": forward_relative,
                        "native_volume_residual_relative": native_residual_relative,
                        "active_trace_exact": active_trace_exact,
                        "slave_rows_zero": slave_rows_zero,
                    }
                )
                del candidate_storage, native_volume_residual, native_volume_action_values
            slave_positions = np.searchsorted(slave_rows, b_alpha_rows)
            if slave_positions.size and len(slave_rows):
                valid_slave_positions = slave_positions < len(slave_rows)
                if np.any(
                    valid_slave_positions
                    & (slave_rows[np.minimum(slave_positions, len(slave_rows) - 1)] == b_alpha_rows)
                ):
                    raise ValueError("saved B-alpha has nonzero support on an MPC slave row")
            b_active_ids = np.empty(len(b_alpha_rows), dtype=np.int64)
            for index, original in enumerate(b_alpha_rows):
                active_id = original_to_active.get(int(original))
                if active_id is None:
                    raise ValueError("saved B-alpha row is not an independent active trace row")
                b_active_ids[index] = active_id

            source = np.zeros(active_rows, dtype=np.complex128)
            np.take(known, active_original, out=source)
            s_volume = action.apply(source)
            g_volume = action.reduce_rhs(volume_rhs, rhs_is_mpc_dual=True)
            if s_volume.shape != (active_rows,) or g_volume.shape != (active_rows,):
                raise ValueError("Task41 V4 production trace action/reducer returned an invalid shape")
            # Reuse g_volume storage for the pure-volume defect d_vol = S t - g_vol.
            g_volume *= -1.0
            g_volume += s_volume
            d_volume = g_volume

            s_full = s_volume
            np.add.at(s_full, b_active_ids, b_alpha_values)
            g_full = action.reduce_rhs(native_rhs, rhs_is_mpc_dual=True)
            if g_full.shape != (active_rows,):
                raise ValueError("Task41 V4 production full-RHS reducer returned an invalid trace shape")
            persist(f"task41_v4_s_full_trace_col{column_index}", s_full)
            persist(f"task41_v4_g_full_trace_col{column_index}", g_full)
            persist(f"task41_v4_d_volume_trace_col{column_index}", d_volume)
            if exact_candidate:
                assert candidate_p6 is not None and candidate_reduced is not None
                candidate_p6[:active_rows, column_index] = s_full
                candidate_reduced[:active_rows, column_index] = g_full
            rhs_decomposition_roundoff = _rhs_decomposition_metrics(
                native_rhs, volume_rhs, b_alpha_rows, b_alpha_values
            )
            saved_denom = max(
                _vector_norm(saved_p6[:, column_index]),
                _vector_norm(saved_reduced[:, column_index]),
                np.finfo(float).tiny,
            )
            saved_d = _difference_metrics(
                saved_p6[:, column_index], saved_reduced[:, column_index]
            )
            saved_d_trace = _difference_metrics(
                saved_p6[:active_rows, column_index], saved_reduced[:active_rows, column_index]
            )
            s_saved = _difference_metrics(
                s_full, saved_p6[:active_rows, column_index]
            )
            g_saved = _difference_metrics(
                g_full, saved_reduced[:active_rows, column_index]
            )
            old_port_action = saved_p6[active_rows:, column_index]
            old_port_reduced = saved_reduced[active_rows:, column_index]
            port_compare = {
                "p6_vs_reduced": _difference_metrics(old_port_action, old_port_reduced),
                "p6_vs_saved_port_rhs": _difference_metrics(old_port_action, saved_port_rhs[:, column_index]),
                "reduced_vs_saved_port_rhs": _difference_metrics(old_port_reduced, saved_port_rhs[:, column_index]),
            }
            s_full -= g_full
            d_full_trace = s_full
            replayed_full_norm = _vector_norm(d_full_trace)
            trace_old_norm = saved_d_trace["absolute_l2"]
            old_port_norm = port_compare["p6_vs_reduced"]["absolute_l2"]
            replayed_full_l2 = float(np.hypot(replayed_full_norm, old_port_norm))
            replayed_full_relative = replayed_full_l2 / saved_denom
            full_trace_gate = {
                "absolute_l2": replayed_full_norm,
                "same_original_denominator_relative": replayed_full_relative,
                "original_denominator": saved_denom,
                "max_abs": float(np.max(np.abs(d_full_trace))) if d_full_trace.size else 0.0,
                "max_row": int(np.argmax(np.abs(d_full_trace))) if d_full_trace.size else None,
                "full_saved_difference_absolute_l2": trace_old_norm,
                "saved_port_difference_absolute_l2": old_port_norm,
                "same_original_1e_11_gate_passed": replayed_full_relative <= 1.0e-11,
            }

            state_metrics = []
            for state in column["states"]:
                state_label = str(state["label"])
                state_storage = np.asarray(state["storage"])
                volume_residual = np.asarray(state["native_volume_residual"])
                volume_action = np.asarray(state["native_volume_action"])
                if (
                    state_storage.shape != (full_rows,)
                    or state_storage.dtype != np.dtype(np.complex128)
                    or any_nonzero_at_rows(state_storage, slave_rows)
                    or volume_residual.shape != (full_rows,)
                    or volume_action.shape != (full_rows,)
                    or volume_residual.dtype != np.dtype(np.complex128)
                    or volume_action.dtype != np.dtype(np.complex128)
                    or any_nonzero_at_rows(volume_residual, slave_rows)
                    or any_nonzero_at_rows(volume_action, slave_rows)
                ):
                    raise ValueError(f"Task41 V4 {state_label} residual/action layout differs")
                for start in range(0, active_rows, 262_144):
                    active_chunk = active_original[start : start + 262_144]
                    if not np.array_equal(
                        state_storage[active_chunk], known[active_chunk]
                    ):
                        raise ValueError(
                            f"Task41 V4 {state_label} state changed the saved active trace"
                        )
                residual_volume_reduced = action.reduce_rhs(
                    volume_residual, rhs_is_mpc_dual=True
                )
                persist(
                    f"task41_v4_reduce_r_volume_{state_label}_col{column_index}",
                    residual_volume_reduced,
                )
                volume_identity = _sum_metrics(d_volume, residual_volume_reduced)
                volume_identity["same_original_denominator_relative"] = (
                    volume_identity["absolute_l2"] / saved_denom
                )

                residual_full = np.empty(full_rows, dtype=np.complex128)
                for start in range(0, full_rows, 262_144):
                    stop = min(full_rows, start + 262_144)
                    residual_full[start:stop] = (
                        native_rhs[start:stop] - volume_action[start:stop]
                    )
                np.add.at(residual_full, b_alpha_rows, -b_alpha_values)
                full_residual_vs_volume_residual = _difference_metrics(
                    residual_full, volume_residual
                )
                residual_full_reduced = action.reduce_rhs(
                    residual_full, rhs_is_mpc_dual=True
                )
                persist(
                    f"task41_v4_reduce_r_full_{state_label}_col{column_index}",
                    residual_full_reduced,
                )
                full_identity = _sum_metrics(d_full_trace, residual_full_reduced)
                full_identity["same_original_denominator_relative"] = (
                    full_identity["absolute_l2"] / saved_denom
                )
                state_metrics.append(
                    {
                        "state": state_label,
                        "volume_identity_dvol_plus_reduce_rvol": volume_identity,
                        "full_identity_dfull_plus_reduce_rfull": full_identity,
                        "rhs_decomposition_roundoff_native_rhs_minus_action_minus_Balpha_vs_saved_volume_residual": {
                            **full_residual_vs_volume_residual,
                            "same_original_denominator_relative": full_residual_vs_volume_residual["absolute_l2"] / saved_denom,
                        },
                        "rhs_split_roundoff_native_rhs_minus_Balpha_minus_volume_rhs": {
                            **rhs_decomposition_roundoff,
                            "same_original_denominator_relative": rhs_decomposition_roundoff["absolute_l2"] / saved_denom,
                        },
                        "volume_residual_norm": _vector_norm(volume_residual),
                        "full_residual_norm": _vector_norm(residual_full),
                    }
                )
                del residual_volume_reduced, residual_full_reduced, residual_full

            column_metrics.append(
                {
                    "column": column_index,
                    "saved_original_denom": saved_denom,
                    "saved_full_d": saved_d,
                    "saved_trace_d": saved_d_trace,
                    "production_s_full_vs_saved_p6_trace": s_saved,
                    "production_g_full_vs_saved_reduced_rhs_trace": g_saved,
                    "saved_port_comparisons": port_compare,
                    "replayed_full_d_trace_and_original_gate": full_trace_gate,
                    "pure_volume_d_trace_norm": _vector_norm(d_volume),
                    "states": state_metrics,
                }
            )
            progress_callback(
                {"phase": "production_volume_column", "status": "COMPLETED", "column": column_index}
            )
        candidate_action_gate = None
        if exact_candidate:
            assert candidate_p6 is not None and candidate_reduced is not None
            full_p6_name = f"{artifact_prefix}_full_p6"
            reduced_rhs_name = f"{artifact_prefix}_full_reduced_rhs"
            persist(full_p6_name, candidate_p6)
            persist(reduced_rhs_name, candidate_reduced)
            candidate_columns = []
            for column_index, frozen_denominator in enumerate(TASK41_V5_FROZEN_DENOMINATORS):
                difference = _difference_metrics(
                    candidate_p6[:, column_index], candidate_reduced[:, column_index]
                )
                dynamic_denominator = max(
                    _vector_norm(candidate_p6[:, column_index]),
                    _vector_norm(candidate_reduced[:, column_index]),
                    np.finfo(float).tiny,
                )
                dynamic_relative = difference["absolute_l2"] / dynamic_denominator
                frozen_relative = difference["absolute_l2"] / frozen_denominator
                candidate_columns.append(
                    {
                        "column": column_index,
                        "difference": difference,
                        "dynamic_denominator": dynamic_denominator,
                        "dynamic_denominator_relative": dynamic_relative,
                        "frozen_denominator": frozen_denominator,
                        "frozen_denominator_relative": frozen_relative,
                        "dynamic_gate_passed": dynamic_relative
                        <= TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE,
                        "frozen_gate_passed": frozen_relative
                        <= TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE,
                    }
                )
            candidate_action_gate = {
                "status": "PASS"
                if all(
                    item["dynamic_gate_passed"] and item["frozen_gate_passed"]
                    for item in candidate_columns
                )
                else "ACTUAL_COORDINATES_INSUFFICIENT",
                "relative_tolerance": TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE,
                "columns": candidate_columns,
                "full_action_artifact": full_p6_name,
                "full_reduced_rhs_artifact": reduced_rhs_name,
                "port_rows_inherited_after_validation": True,
                "frozen_denominators_source": (
                    "review_report_v6.md"
                    if candidate_identity is not None
                    else "review_report_v5.md"
                ),
            }
        candidate_recovery_status = (
            "PASS"
            if exact_candidate
            and len(candidate_recovery_columns) == 2
            and all(item["passed"] for item in candidate_recovery_columns)
            else "ACTUAL_COORDINATES_INSUFFICIENT"
            if exact_candidate
            else None
        )
        return {
            "schema": (
                "task41.p0.v6.actual_qmetric_attribution.v1"
                if exact_candidate and candidate_identity is not None
                else "task41.p0.v5.mesh_actual_exact_attribution.v1"
                if exact_candidate
                else "task41.p0.v4.volume_only_attribution.v1"
            ),
            "candidate_evaluator_identity": candidate_identity,
            "candidate_evaluator_cache_identity": candidate_cache_identity,
            "completed": True,
            "production_action": "P6CellCondensedAction_active_only_shared_owner_caches",
            "rhs_reducer": "P6CellCondensedAction.reduce_rhs(rhs_is_mpc_dual=True)",
            "active_rows": active_rows,
            "saved_port_rows": port_rows,
            "saved_port_rows_reused": True,
            "global_volume_matrix_materialized": False,
            "dense_port_matrix_materialized": False,
            "carrier_or_surface_constructed": False,
            "local_class_identities": list(identity.get("local_class_identities", ())),
            "replay_artifacts": replay_artifacts,
            "new_identity_evidence_bytes": persisted_bytes,
            "cumulative_evidence_bytes": int(donor["existing_evidence_bytes"]) + prior_new_bytes + persisted_bytes,
            "columns": column_metrics,
            "candidate_full_action_gate": candidate_action_gate,
            "candidate_recovery_gate": (
                {
                    "status": candidate_recovery_status,
                    "relative_forward_tolerance": 1.0e-11,
                    "native_volume_residual_relative_tolerance": 1.0e-10,
                    "native_volume_action_count": len(candidate_recovery_columns),
                    "recovery_source": "saved native_volume_rhs with the current exact-geometry owner",
                    "columns": candidate_recovery_columns,
                }
                if exact_candidate
                else None
            ),
        }
    finally:
        action.destroy()
