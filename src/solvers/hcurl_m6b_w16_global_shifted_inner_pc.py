"""Research-only fixed beta=1 shifted inner cycles for W16A/W16R/W16B.

The auxiliary operator is the existing shifted volume-only beta=1 operator.
The physical beta=0 volume-plus-DtN measurement belongs to the later worker;
this module only wraps the existing disk-backed flexible-GMRES implementation
and evaluates its small scalar/hash contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import numpy as np

from .disk_backed_flexible_gmres import (
    DiskBackedFlexibleGMRES,
    DiskBackedFlexibleGMRESResult,
)


__all__ = (
    "W16A_AUXILIARY_BETA",
    "W16A_AUXILIARY_OPERATOR",
    "W16A_AUXILIARY_PC",
    "W16A_CHECKPOINTS",
    "W16A_CLOSURE_LIMIT",
    "W16A_INNER_SCHEMA",
    "W16A_INNER_TRUE_RESIDUAL_LIMIT",
    "W16A_MAX_STEPS",
    "W16A_PREDICTED_LIVE_SET_BYTES",
    "W16A_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W16A_RELATIVE_IDENTITY_LIMIT",
    "W16A_RHO_LIMIT",
    "W16A_SCHEMA",
    "W16A_SCRATCH_PER_RUN_BYTES",
    "W16A_SCRATCH_TWO_RUN_TOTAL_BYTES",
    "W16A_SCRATCH_IS_DISK_NOT_RSS",
    "W16A_WATCHDOG_LIMIT_BYTES",
    "W16R_ADDITIONAL_STEPS",
    "W16R_GLOBAL_ACTION_COUNT_PER_RUN",
    "W16R_GLOBAL_ACTION_COUNT_TOTAL",
    "W16R_INNER_SCHEMA",
    "W16R_LOCAL_PC_COUNT_TOTAL",
    "W16R_PREDICTED_LIVE_SET_BYTES",
    "W16R_SCHEMA",
    "W16B_SCHEMA",
    "W16B_INNER_SCHEMA",
    "W16B_MAX_STEPS",
    "W16B_CHECKPOINTS",
    "W16B_RHO1_ANCHOR",
    "W16B_RHO2_LIMIT",
    "W16B_PREDICTED_LIVE_SET_BYTES",
    "W16B_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "W16B_WATCHDOG_LIMIT_BYTES",
    "W16B_SCRATCH_PER_APPLY_BYTES",
    "W16B_INNER_SCRATCH_PER_SCREEN_BYTES",
    "W16B_OUTER_SCRATCH_PER_SCREEN_BYTES",
    "W16B_SCRATCH_PER_SCREEN_BYTES",
    "W16B_SCRATCH_TWO_RUN_TOTAL_BYTES",
    "W16B_FIXED40_GLOBAL_ACTION_COUNT",
    "W16B_FIXED40_PC_COUNT",
    "W16B_FIXED40_SHIFTED_ACTION_COUNT",
    "W16B_OUTER_ACTION_COUNT",
    "W16B_OUTER_PC_COUNT",
    "W16B_TOTAL_GLOBAL_ACTION_COUNT",
    "W16B_TOTAL_PC_COUNT",
    "W16B_TOTAL_SHIFTED_ACTION_COUNT",
    "W16B_TOTAL_PHYSICAL_ACTION_COUNT",
    "W16B_TOTAL_OUTER_PC_COUNT",
    "W16B_TOTAL_LOCAL_EXACT_SHIFTED_ACTION_COUNT",
    "W16BFixed40Result",
    "W16BFixed40ComposedPC",
    "run_w16b_fixed40",
    "run_w16b_outer2",
    "evaluate_w16b_outer2_gate",
    "evaluate_w16r_restart20_gate",
    "evaluate_w16a_global_shifted_gate",
    "run_w16r_fixed20",
    "run_w16a_fixed20",
)


W16A_SCHEMA = "task037.extra.h2b.w16a.global-shifted-inner.v1"
W16A_INNER_SCHEMA = "task037.extra.h2b.w16a.inner-fixed20.v1"
W16A_AUXILIARY_OPERATOR = "shifted_volume_only"
W16A_AUXILIARY_PC = "direct_beta1_shifted_row_complete_local_patch"
W16A_AUXILIARY_BETA = 1.0
W16A_MAX_STEPS = 20
W16A_CHECKPOINTS = (20,)
W16A_INNER_TRUE_RESIDUAL_LIMIT = 1.0e-2
W16A_RELATIVE_IDENTITY_LIMIT = 1.0e-13
W16A_RHO_LIMIT = 0.90
W16A_CLOSURE_LIMIT = 1.0e-11
W16A_VECTOR_BYTES = 173_802 * np.dtype(np.complex128).itemsize
W16A_SCRATCH_PER_RUN_BYTES = (
    W16A_MAX_STEPS + 1 + W16A_MAX_STEPS
) * W16A_VECTOR_BYTES
W16A_SCRATCH_TWO_RUN_TOTAL_BYTES = 2 * W16A_SCRATCH_PER_RUN_BYTES
W16A_SCRATCH_IS_DISK_NOT_RSS = True
W16A_BASE_LIVE_SET_BYTES = 1_698_273_595
W16A_AUXILIARY_VECTOR_BYTES = 15 * W16A_VECTOR_BYTES
W16A_PREDICTED_LIVE_SET_BYTES = (
    W16A_BASE_LIVE_SET_BYTES + W16A_AUXILIARY_VECTOR_BYTES
)
W16A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
W16A_WATCHDOG_LIMIT_BYTES = 1_950_000_000

W16R_SCHEMA = "task037.extra.h2b.w16r.restart20.v1"
W16R_INNER_SCHEMA = "task037.extra.h2b.w16r.inner-restart20.v1"
W16R_ADDITIONAL_STEPS = 20
W16R_GLOBAL_ACTION_COUNT_PER_RUN = 22
W16R_GLOBAL_ACTION_COUNT_TOTAL = 44
W16R_LOCAL_PC_COUNT_TOTAL = 40
W16R_PREDICTED_LIVE_SET_BYTES = W16A_PREDICTED_LIVE_SET_BYTES + W16A_VECTOR_BYTES

W16B_SCHEMA = "task037.extra.h2b.w16b.outer2-composed.v1"
W16B_INNER_SCHEMA = "task037.extra.h2b.w16b.inner-composed-fixed40.v1"
W16B_MAX_STEPS = 2
W16B_CHECKPOINTS = (1, 2)
W16B_RHO1_ANCHOR = 0.8814092210776835
W16B_RHO1_LIMIT = 1.0e-11
W16B_RHO2_LIMIT = math.sqrt(0.75)
W16B_OUTER_RELATIVE_LIMIT = 1.0e-13
W16B_OUTER_CLOSURE_LIMIT = 1.0e-12
W16B_PREDICTED_LIVE_SET_BYTES = 1_734_993_014
W16B_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
W16B_WATCHDOG_LIMIT_BYTES = 1_950_000_000
W16B_SCRATCH_PER_APPLY_BYTES = 228_028_224
W16B_INNER_SCRATCH_PER_SCREEN_BYTES = 456_056_448
W16B_OUTER_SCRATCH_PER_SCREEN_BYTES = (3 + 2) * W16A_VECTOR_BYTES
W16B_SCRATCH_PER_SCREEN_BYTES = (
    W16B_INNER_SCRATCH_PER_SCREEN_BYTES + W16B_OUTER_SCRATCH_PER_SCREEN_BYTES
)
W16B_SCRATCH_TWO_RUN_TOTAL_BYTES = 2 * W16B_SCRATCH_PER_SCREEN_BYTES
W16B_FIXED40_GLOBAL_ACTION_COUNT = 43
W16B_FIXED40_PC_COUNT = 40
W16B_FIXED40_SHIFTED_ACTION_COUNT = 83
W16B_OUTER_ACTION_COUNT = 4
W16B_OUTER_PC_COUNT = 2
W16B_TOTAL_GLOBAL_ACTION_COUNT = 172
W16B_TOTAL_PC_COUNT = 160
W16B_TOTAL_SHIFTED_ACTION_COUNT = 332
W16B_TOTAL_PHYSICAL_ACTION_COUNT = 8
W16B_TOTAL_OUTER_PC_COUNT = 4
W16B_TOTAL_LOCAL_EXACT_SHIFTED_ACTION_COUNT = 160
W16B_W16R_COMPACT_FILE_SHA256 = (
    "9c1c53961db80d33b95e266fd3569a8fd366b19004ae3df0aa0d9c847703b77e"
)
W16B_W16R_COMPACT_EVIDENCE_SHA256 = (
    "87aae95d856a9761a63be6c7b834559d76c382c4b3b2eae6454ab4e12c05ccd4"
)
W16B_W16R_MEASURED_PEAK_BYTES = 1_398_456_320
W16B_PHYSICAL_RETAINED_PAYLOAD_BYTES = 6_151_120
W16B_PHYSICAL_PER_APPLY_TEMP_BYTES = 3_564_288
W16B_DTN_RETAINED_WORK_BYTES = 16_673_350
W16B_OUTER_BOUNDED_VECTOR_BYTES = 33_369_984


def _w16b_array_sha256(values: np.ndarray) -> str:
    import hashlib

    array = np.ascontiguousarray(values, dtype=np.complex128)
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _w16b_write_solution_artifact(
    path: Path, values: np.ndarray
) -> dict[str, Any]:
    import hashlib

    array = np.ascontiguousarray(values, dtype=np.complex128)
    with Path(path).open("wb") as stream:
        np.save(stream, array, allow_pickle=False)
    file_hash = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            file_hash.update(block)
    return {
        "path": str(Path(path).resolve()),
        "bytes": int(Path(path).stat().st_size),
        "dtype": str(array.dtype),
        "shape": [int(value) for value in array.shape],
        "array_sha256": _w16b_array_sha256(array),
        "file_sha256": file_hash.hexdigest(),
    }


def run_w16a_fixed20(
    action: Callable[[np.ndarray], np.ndarray],
    pc: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> DiskBackedFlexibleGMRESResult:
    """Run exactly one zero-start right-FGMRES W16A auxiliary cycle.

    ``DiskBackedFlexibleGMRES`` remains the sole implementation of Arnoldi,
    two-pass MGS, checkpoint reconstruction, and disk-backed basis storage.
    This wrapper intentionally exposes no iteration, restart, beta, or
    tolerance controls.
    """

    solver = DiskBackedFlexibleGMRES(
        action,
        pc,
        max_steps=W16A_MAX_STEPS,
        checkpoints=W16A_CHECKPOINTS,
    )
    return solver.solve(rhs, scratch_dir=scratch_dir, observer=observer)


def run_w16r_fixed20(
    action: Callable[[np.ndarray], np.ndarray],
    pc: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    initial_solution: np.ndarray,
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> DiskBackedFlexibleGMRESResult:
    """Run W16R's fixed additional-20-step restart from a frozen solution.

    The initial solution is deliberately not configurable through solver
    settings: W16R always performs one fresh initial action/residual followed
    by exactly twenty right-FGMRES steps.  The shared solver remains the sole
    implementation of Arnoldi, MGS, checkpoint reconstruction, and scratch
    storage.
    """

    solver = DiskBackedFlexibleGMRES(
        action,
        pc,
        max_steps=W16R_ADDITIONAL_STEPS,
        checkpoints=(W16R_ADDITIONAL_STEPS,),
    )
    return solver.solve(
        rhs,
        scratch_dir=scratch_dir,
        initial_solution=initial_solution,
        observer=observer,
    )


@dataclass(frozen=True)
class W16BFixed40Result:
    """One composed zero-start 20+20 auxiliary correction."""

    solution: np.ndarray
    cycle20_audit: Mapping[str, Any]
    cycle40_audit: Mapping[str, Any]
    final_relative_residual: float
    audit: Mapping[str, Any]


def run_w16b_fixed40(
    action: Callable[[np.ndarray], np.ndarray],
    pc: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> W16BFixed40Result:
    """Compose the fixed zero-start W16A and W16R cycles.

    The first cycle is never replaced by a frozen W16A/W16R result.  Its
    solution is passed only as the initial solution of the second fixed cycle;
    both Arnoldi/MGS implementations and their disk stores remain owned by
    ``DiskBackedFlexibleGMRES``.
    """

    root = Path(scratch_dir)
    first = run_w16a_fixed20(
        action,
        pc,
        rhs,
        root / "cycle20",
    )
    z20 = np.array(first.solution, dtype=np.complex128, order="C", copy=True)
    second = run_w16r_fixed20(
        action,
        pc,
        rhs,
        z20,
        root / "cycle40",
        observer=observer,
    )
    cycle20_audit = dict(first.audit)
    cycle40_audit = dict(second.audit)
    solution = np.array(second.solution, dtype=np.complex128, order="C", copy=True)
    audit = {
        "schema": W16B_INNER_SCHEMA,
        "algorithm": "fgmres_right_shifted_beta1_composed_fixed20_plus20",
        "initial_solution_provided": False,
        "initial_action_count": 0,
        "cycle20": cycle20_audit,
        "cycle40": cycle40_audit,
        "cycle20_relative_residual": float(first.final_relative_residual),
        "cycle40_relative_residual": float(second.final_relative_residual),
        "solution_sha256": _w16b_array_sha256(solution),
        "global_action_count": int(
            cycle20_audit["action_count"] + cycle40_audit["action_count"]
        ),
        "pc_apply_count": int(cycle20_audit["pc_count"] + cycle40_audit["pc_count"]),
        "shifted_action_count": W16B_FIXED40_SHIFTED_ACTION_COUNT,
        "final_relative_residual": float(second.final_relative_residual),
        "finite": bool(
            np.all(np.isfinite(solution))
            and np.isfinite(first.final_relative_residual)
            and np.isfinite(second.final_relative_residual)
        ),
        "scratch_paths": {
            "cycle20": cycle20_audit["scratch_paths"],
            "cycle40": cycle40_audit["scratch_paths"],
        },
    }
    del first, second, z20
    return W16BFixed40Result(
        solution=solution,
        cycle20_audit=cycle20_audit,
        cycle40_audit=cycle40_audit,
        final_relative_residual=float(audit["final_relative_residual"]),
        audit=audit,
    )


class W16BFixed40ComposedPC:
    """Borrowed-action/PC wrapper with one fresh scratch root per apply."""

    def __init__(
        self,
        action: Callable[[np.ndarray], np.ndarray],
        pc: Callable[[np.ndarray], np.ndarray],
        scratch_root: str | Path,
    ) -> None:
        self._action = action
        self._pc = pc
        self._scratch_root = Path(scratch_root)
        self._apply_index = 0
        self._records: list[Mapping[str, Any]] = []

    def apply(self, values: np.ndarray) -> np.ndarray:
        self._apply_index += 1
        apply_root = self._scratch_root / f"apply_{self._apply_index:02d}"
        apply_root.mkdir(parents=True, exist_ok=False)
        result = run_w16b_fixed40(
            self._action,
            self._pc,
            np.asarray(values),
            apply_root,
        )
        solution = result.solution
        record = dict(result.audit)
        record["solution_sha256"] = _w16b_array_sha256(solution)
        record["solution_artifact"] = _w16b_write_solution_artifact(
            apply_root / "solution.npy", solution
        )
        self._records.append(record)
        del result
        return solution

    @property
    def apply_count(self) -> int:
        return self._apply_index

    @property
    def records(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._records)


def run_w16b_outer2(
    physical_action: Callable[[np.ndarray], np.ndarray],
    auxiliary_action: Callable[[np.ndarray], np.ndarray],
    local_pc: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    scratch_dir: str | Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[DiskBackedFlexibleGMRESResult, W16BFixed40ComposedPC]:
    """Run the fixed two-step outer physical screen with a composed PC."""

    outer_scratch = Path(scratch_dir)
    if not outer_scratch.parent.is_dir():
        outer_scratch.parent.mkdir(parents=True)
    if outer_scratch.exists():
        raise FileExistsError(f"W16B outer scratch already exists: {outer_scratch}")
    composed_pc = W16BFixed40ComposedPC(
        auxiliary_action,
        local_pc,
        outer_scratch / "inner",
    )
    solver = DiskBackedFlexibleGMRES(
        physical_action,
        composed_pc.apply,
        max_steps=W16B_MAX_STEPS,
        checkpoints=W16B_CHECKPOINTS,
    )
    result = solver.solve(
        rhs,
        scratch_dir=outer_scratch,
        observer=observer,
    )
    return result, composed_pc


def _w16b_outer_audit_valid(audit: Any) -> bool:
    if not isinstance(audit, Mapping):
        return False
    try:
        return bool(
            audit["algorithm"] == "right_flexible_gmres"
            and audit["rows"] == W16A_VECTOR_BYTES // 16
            and audit["dtype"] == "complex128"
            and audit["max_steps"] == 2
            and audit["iterations"] == 2
            and audit["checkpoint_iterations"] == [1, 2]
            and audit["checkpoint_count"] == 2
            and audit["observer_count"] == 2
            and audit["action_count"] == W16B_OUTER_ACTION_COUNT
            and audit["pc_count"] == W16B_OUTER_PC_COUNT
            and audit["initial_action_count"] == 0
            and audit["orthogonalization_passes"] == 2
            and audit["mmap"] is False
            and audit["basis_in_memory"] is False
            and audit["bounded_full_vector_gate"] is True
            and audit["checkpoint_set_complete"] is True
            and audit["scratch_bytes"] == 13_904_160
            and audit["scratch_mmap"] is False
            and audit["scratch_basis_in_memory"] is False
            and audit["bounded_full_vector_buffer_count"] == 12
            and audit["bounded_full_vector_bytes"] == W16B_OUTER_BOUNDED_VECTOR_BYTES
            and audit["v_basis"]["capacity"] == 3
            and audit["v_basis"]["written_count"] == 3
            and audit["v_basis"]["allocated_bytes"] == 3 * W16A_VECTOR_BYTES
            and audit["z_basis"]["capacity"] == 2
            and audit["z_basis"]["written_count"] == 2
            and audit["z_basis"]["allocated_bytes"] == 2 * W16A_VECTOR_BYTES
            and isinstance(audit["scratch_paths"], Mapping)
            and isinstance(audit["scratch_paths"]["v_basis"], str)
            and isinstance(audit["scratch_paths"]["z_basis"], str)
        )
    except (KeyError, TypeError, ValueError):
        return False


def _w16b_fixed40_audit_valid(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    try:
        cycle20 = record["cycle20"]
        cycle40 = record["cycle40"]
        return bool(
            record["schema"] == W16B_INNER_SCHEMA
            and record["algorithm"]
            == "fgmres_right_shifted_beta1_composed_fixed20_plus20"
            and record["initial_solution_provided"] is False
            and record["initial_action_count"] == 0
            and _fixed20_inner_audit(cycle20)
            and _fixed20_inner_audit(cycle40, initial_solution_provided=True)
            and record["global_action_count"] == W16B_FIXED40_GLOBAL_ACTION_COUNT
            and record["pc_apply_count"] == W16B_FIXED40_PC_COUNT
            and record["shifted_action_count"] == W16B_FIXED40_SHIFTED_ACTION_COUNT
            and isinstance(record["solution_sha256"], str)
            and bool(record["solution_sha256"])
            and isinstance(record["solution_artifact"], Mapping)
            and record["solution_artifact"]["array_sha256"]
            == record["solution_sha256"]
            and record["finite"] is True
            and _finite_bounded(record["cycle20_relative_residual"])
            and _finite_bounded(record["cycle40_relative_residual"])
            and _finite_bounded(
                record["final_relative_residual"], W16A_INNER_TRUE_RESIDUAL_LIMIT
            )
            and isinstance(record["scratch_paths"], Mapping)
        )
    except (KeyError, TypeError, ValueError):
        return False


def evaluate_w16b_outer2_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the fixed W16B two-screen scalar/hash contract."""

    names = (
        "schema",
        "fixed_identity",
        "screen_runs",
        "inner_residual",
        "inner_identity",
        "outer_audit",
        "checkpoint_identity",
        "rho",
        "action_counts",
        "architecture",
        "lifecycle",
        "prediction",
    )
    checks = {name: False for name in names}
    if not isinstance(summary, Mapping):
        return {"pass": False, "checks": checks, "problems": list(names)}
    try:
        checks["schema"] = summary["schema"] == W16B_SCHEMA
        identity = summary["fixed_identity"]
        checks["fixed_identity"] = bool(
            isinstance(identity, Mapping)
            and identity["operator"] == "shifted_volume_only"
            and type(identity["beta"]) is float
            and identity["beta"] == 1.0
            and identity["right_pc"]
            == "direct_beta1_shifted_row_complete_local_patch"
            and identity["auxiliary_dtn_used"] is False
            and identity["projected_range_used"] is False
            and identity["b0_used"] is False
            and identity["m3y_used"] is False
            and identity["range_store_used"] is False
        )
        runs = summary["screen_runs"]
        checks["screen_runs"] = bool(
            isinstance(runs, Sequence)
            and not isinstance(runs, (str, bytes))
            and len(runs) == 2
            and [item["run_index"] for item in runs] == [1, 2]
            and all(
                item["finite"] is True
                and isinstance(item["inner_records"], Sequence)
                and len(item["inner_records"]) == 2
                and [record["apply_index"] for record in item["inner_records"]]
                == [1, 2]
                and all(_w16b_fixed40_audit_valid(value) for value in item["inner_records"])
                for item in runs
            )
        )
        checks["inner_residual"] = bool(
            checks["screen_runs"]
            and all(
                _finite_bounded(value["final_relative_residual"], W16A_INNER_TRUE_RESIDUAL_LIMIT)
                and _finite_bounded(value["cycle20_relative_residual"])
                for item in runs
                for value in item["inner_records"]
            )
        )
        checks["outer_audit"] = bool(
            checks["screen_runs"]
            and all(_w16b_outer_audit_valid(item["outer_audit"]) for item in runs)
            and runs[0]["outer_audit"]["scratch_paths"]
            != runs[1]["outer_audit"]["scratch_paths"]
        )
        inner_identity = summary["inner_identity"]
        checks["inner_identity"] = bool(
            isinstance(inner_identity, Sequence)
            and not isinstance(inner_identity, (str, bytes))
            and len(inner_identity) == 2
            and all(
                isinstance(value, Mapping)
                and value["first_sha256"]
                == runs[0]["inner_records"][index]["solution_sha256"]
                and value["second_sha256"]
                == runs[1]["inner_records"][index]["solution_sha256"]
                and value["first_sha256"] == value["second_sha256"]
                and value["sha256_equal"] is True
                and _finite_bounded(
                    value["relative_difference"], W16B_OUTER_RELATIVE_LIMIT
                )
                for index, value in enumerate(inner_identity)
            )
        )
        checkpoints = [item["checkpoints"] for item in runs]
        checks["checkpoint_identity"] = bool(
            all(isinstance(value, Sequence) and len(value) == 2 for value in checkpoints)
            and all(
                value[0]["iteration"] == 1 and value[1]["iteration"] == 2
                for value in checkpoints
            )
            and all(
                all(
                    isinstance(value["artifacts"][name], Mapping)
                    and isinstance(value["artifacts"][name]["array_sha256"], str)
                    and value["artifacts"][name]["array_sha256"]
                    for name in ("solution", "outer_action", "residual", "rhs")
                )
                for run in checkpoints
                for value in run
            )
            and all(
                checkpoints[0][index]["artifacts"][name]["array_sha256"]
                == checkpoints[1][index]["artifacts"][name]["array_sha256"]
                for index in (0, 1)
                for name in ("solution", "outer_action", "residual", "rhs")
            )
            and all(
                _finite_bounded(
                    value["residual_closure"], W16B_OUTER_CLOSURE_LIMIT
                )
                and abs(
                    value["true_relative_residual"]
                    - runs[run_index]["rho1" if checkpoint_index == 0 else "rho2"]
                )
                <= W16B_OUTER_CLOSURE_LIMIT
                for run_index, run in enumerate(runs)
                for checkpoint_index, value in enumerate(run["checkpoints"])
            )
        )
        checks["rho"] = bool(
            all(
                _finite_bounded(item["rho1"])
                and _finite_bounded(item["rho2"])
                and abs(item["rho1"] - W16B_RHO1_ANCHOR) <= W16B_RHO1_LIMIT
                and item["rho2"] <= item["rho1"] + 1.0e-13
                and item["rho2"] <= W16B_RHO2_LIMIT
                for item in runs
            )
            and abs(runs[0]["rho1"] - runs[1]["rho1"])
            <= W16B_OUTER_RELATIVE_LIMIT
            and abs(runs[0]["rho2"] - runs[1]["rho2"])
            <= W16B_OUTER_RELATIVE_LIMIT
        )
        action = summary["action_audit"]
        checks["action_counts"] = bool(
            isinstance(action, Mapping)
            and action["outer_pc_apply_count"] == W16B_TOTAL_OUTER_PC_COUNT
            and action["physical_action_count"] == W16B_TOTAL_PHYSICAL_ACTION_COUNT
            and action["global_shifted_action_count"] == W16B_TOTAL_GLOBAL_ACTION_COUNT
            and action["local_pc_apply_count"] == W16B_TOTAL_PC_COUNT
            and action["local_exact_shifted_volume_action_count"]
            == W16B_TOTAL_LOCAL_EXACT_SHIFTED_ACTION_COUNT
            and action["shifted_action_total_count"] == W16B_TOTAL_SHIFTED_ACTION_COUNT
        )
        architecture = summary["architecture"]
        checks["architecture"] = bool(
            isinstance(architecture, Mapping)
            and architecture["fine_space"] == "uncondensed_fullspace"
            and architecture["physical_operator"]
            == "beta0_volume_plus_matrix_free_dtn80"
            and architecture["auxiliary_operator"] == "shifted_volume_only"
            and architecture["auxiliary_dtn_used"] is False
            and architecture["global_matrix_materialized"] is False
            and architecture["augmented_matrix_materialized"] is False
            and architecture["condensation"] is False
            and architecture["static_condensation"] is False
            and architecture["trace_slab"] is False
            and architecture["slab_factors"] == 0
            and architecture["physical_ksp_used"] is False
            and architecture["pde_used"] is False
            and architecture["official_rta"] is False
        )
        lifecycle = summary["lifecycle"]
        checks["lifecycle"] = bool(
            isinstance(lifecycle, Mapping)
            and lifecycle["auxiliary_physical_overlap"] is True
            and lifecycle["release_between_screen_runs"] is False
            and lifecycle["heavy_objects_reused_between_screens"] is True
            and lifecycle["events"] == [
                "auxiliary_constructed",
                "physical_constructed",
                "screen_run_1",
                "screen_run_2",
                "physical_released",
                "auxiliary_released",
            ]
        )
        prediction = summary["prediction"]
        checks["prediction"] = bool(
            isinstance(prediction, Mapping)
            and prediction["bytes"] == W16B_PREDICTED_LIVE_SET_BYTES
            and prediction["limit_bytes"] == W16B_PREDICTED_LIVE_SET_LIMIT_BYTES
            and prediction["watchdog_limit_bytes"] == W16B_WATCHDOG_LIMIT_BYTES
            and prediction["derived_not_measured"] is True
            and prediction["scratch_is_disk_not_rss"] is True
            and prediction["w16r_compact_file_sha256"]
            == W16B_W16R_COMPACT_FILE_SHA256
            and prediction["w16r_compact_evidence_sha256"]
            == W16B_W16R_COMPACT_EVIDENCE_SHA256
            and prediction["w16r_measured_peak_bytes"]
            == W16B_W16R_MEASURED_PEAK_BYTES
            and prediction["components"] == {
                "calibrated_w16r_measured_process_tree_peak_bytes": 1_398_456_320,
                "physical_retained_numeric_payload_bytes": 6_151_120,
                "physical_per_apply_temporary_bytes": 3_564_288,
                "dtn_retained_and_work_bytes": 16_673_350,
                "outer_bridge_fixed_vectors_bytes": 5_561_664,
                "outer_petsc_template_vector_bytes": 2_780_832,
                "outer_solver_bounded_vectors_bytes": 33_369_984,
                "coexistence_uncertainty_margin_bytes": 268_435_456,
            }
            and sum(prediction["components"].values()) == prediction["bytes"]
            and summary["w16r_authority"]["compact_file_sha256"]
            == W16B_W16R_COMPACT_FILE_SHA256
            and summary["w16r_authority"]["compact_evidence_sha256"]
            == W16B_W16R_COMPACT_EVIDENCE_SHA256
            and summary["w16r_authority"]["measured_peak_rss_bytes"]
            == W16B_W16R_MEASURED_PEAK_BYTES
            and summary["w16r_authority"]["measured_swap_bytes"] == 0
            and summary["memory_audit"] == {
                "physical_retained_numeric_payload_bytes": W16B_PHYSICAL_RETAINED_PAYLOAD_BYTES,
                "physical_per_apply_temporary_bytes": W16B_PHYSICAL_PER_APPLY_TEMP_BYTES,
                "dtn_retained_and_work_bytes": W16B_DTN_RETAINED_WORK_BYTES,
                "outer_bridge_fixed_vectors": 2,
                "outer_petsc_template_vector_bytes": W16A_VECTOR_BYTES,
                "outer_solver_bounded_vector_bytes": W16B_OUTER_BOUNDED_VECTOR_BYTES,
            }
        )
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(name for name, passed in checks.items() if not passed),
    }


def _finite_bounded(value: Any, limit: float | None = None) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0.0 and (
        limit is None or number <= limit
    )


def _fixed20_inner_audit(
    audit: Mapping[str, Any], *, initial_solution_provided: bool = False
) -> bool:
    if not isinstance(audit, Mapping):
        return False
    try:
        v_basis = audit["v_basis"]
        z_basis = audit["z_basis"]
        expected_action_count = 22 if initial_solution_provided else 21
        expected_initial_action_count = 1 if initial_solution_provided else 0
        initial_identity = (
            audit["initial_solution_provided"] is True
            if initial_solution_provided
            else (
                "initial_solution_provided" not in audit
                or audit["initial_solution_provided"] is False
            )
        )
        return (
            audit["algorithm"] == "right_flexible_gmres"
            and audit["rows"] == W16A_VECTOR_BYTES // 16
            and audit["dtype"] == "complex128"
            and audit["max_steps"] == W16A_MAX_STEPS
            and audit["iterations"] == W16A_MAX_STEPS
            and audit["checkpoint_iterations"] == [20]
            and audit["checkpoint_count"] == 1
            and audit["observer_count"] == 1
            and audit["action_count"] == expected_action_count
            and audit["pc_count"] == 20
            and audit["initial_action_count"] == expected_initial_action_count
            and initial_identity
            and audit["orthogonalization_passes"] == 2
            and audit["mmap"] is False
            and audit["basis_in_memory"] is False
            and audit["scratch_bytes"] == W16A_SCRATCH_PER_RUN_BYTES
            and audit["scratch_mmap"] is False
            and audit["scratch_basis_in_memory"] is False
            and audit["checkpoint_set_complete"] is True
            and audit["bounded_full_vector_gate"] is True
            and isinstance(audit["scratch_paths"], Mapping)
            and isinstance(audit["scratch_paths"]["v_basis"], str)
            and bool(audit["scratch_paths"]["v_basis"])
            and isinstance(audit["scratch_paths"]["z_basis"], str)
            and bool(audit["scratch_paths"]["z_basis"])
            and v_basis["capacity"] == 21
            and v_basis["written_count"] == 21
            and v_basis["write_count"] == 21
            and v_basis["allocated_bytes"] == 21 * W16A_VECTOR_BYTES
            and v_basis["mmap"] is False
            and z_basis["capacity"] == 20
            and z_basis["written_count"] == 20
            and z_basis["write_count"] == 20
            and z_basis["allocated_bytes"] == 20 * W16A_VECTOR_BYTES
            and z_basis["mmap"] is False
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def _fixed20_record(
    record: Mapping[str, Any], *, initial_solution_provided: bool = False
) -> bool:
    if not isinstance(record, Mapping):
        return False
    try:
        expected_action_count = 22 if initial_solution_provided else 21
        expected_initial_action_count = 1 if initial_solution_provided else 0
        initial_identity = (
            record["initial_solution_provided"] is True
            if initial_solution_provided
            else (
                "initial_solution_provided" not in record
                or record["initial_solution_provided"] is False
            )
        )
        return (
            record["schema"] == (
                W16R_INNER_SCHEMA if initial_solution_provided else W16A_INNER_SCHEMA
            )
            and record["algorithm"]
            == (
                "fgmres_right_shifted_beta1_restart20"
                if initial_solution_provided
                else "fgmres_right_shifted_beta1_fixed20"
            )
            and record["iterations"] == 20
            and record["checkpoint_iteration"] == 20
            and record["action_count"] == expected_action_count
            and record["pc_apply_count_delta"] == 20
            and record["observer_count"] == 1
            and record["initial_action_count"] == expected_initial_action_count
            and initial_identity
            and type(record["run_index"]) is int
            and record["run_index"] in (1, 2)
            and record["finite"] is True
            and isinstance(record["solution_sha256"], str)
            and bool(record["solution_sha256"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _identity_gate(identity: Mapping[str, Any]) -> bool:
    if not isinstance(identity, Mapping):
        return False
    try:
        return (
            identity["finite"] is True
            and identity["dtype"] == "complex128"
            and identity["shape_equal"] is True
            and identity["sha256_equal"] is True
            and _finite_bounded(
                identity["relative_difference"], W16A_RELATIVE_IDENTITY_LIMIT
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _measurement_gate(
    measurement: Mapping[str, Any], *, expected_schema: str = W16A_SCHEMA
) -> bool:
    if not isinstance(measurement, Mapping):
        return False
    try:
        return (
            measurement["schema"] == expected_schema
            and measurement["finite"] is True
            and measurement["repeat_exact"] is True
            and _finite_bounded(measurement["rho"], W16A_RHO_LIMIT)
            and _finite_bounded(
                measurement["normal_closure"], W16A_CLOSURE_LIMIT
            )
            and _finite_bounded(
                measurement["projection_orthogonality"], W16A_CLOSURE_LIMIT
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def evaluate_w16a_global_shifted_gate(
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the narrow W16A scalar/hash Gate from recorded evidence.

    The evaluator accepts only the fixed beta=1 shifted-volume/direct-local-PC
    identity.  It does not infer missing fields or trust a producer ``pass``
    flag.  Physical action measurements are included as the later worker's
    two rank-one records; no action or solver is executed here.
    """

    check_names = (
        "schema",
        "fixed_identity",
        "inner_audits",
        "inner_records",
        "inner_residual",
        "z_identity",
        "p_identity",
        "measurements",
        "action_counts",
        "architecture",
        "lifecycle",
        "prediction",
    )
    checks = {name: False for name in check_names}
    if not isinstance(summary, Mapping):
        return {
            "pass": False,
            "checks": checks,
            "problems": list(check_names),
        }

    try:
        checks["schema"] = summary["schema"] == W16A_SCHEMA

        identity = summary["fixed_identity"]
        checks["fixed_identity"] = (
            isinstance(identity, Mapping)
            and identity["operator"] == W16A_AUXILIARY_OPERATOR
            and type(identity["beta"]) is float
            and identity["beta"] == W16A_AUXILIARY_BETA
            and identity["right_pc"] == W16A_AUXILIARY_PC
            and identity["auxiliary_dtn_used"] is False
            and identity["projected_range_used"] is False
            and identity["b0_used"] is False
            and identity["m3y_used"] is False
            and identity["range_store_used"] is False
        )

        inner_audits = summary["inner_audits"]
        checks["inner_audits"] = (
            isinstance(inner_audits, Sequence)
            and not isinstance(inner_audits, (str, bytes))
            and len(inner_audits) == 2
            and all(_fixed20_inner_audit(audit) for audit in inner_audits)
            and inner_audits[0]["scratch_paths"]["v_basis"]
            != inner_audits[1]["scratch_paths"]["v_basis"]
            and inner_audits[0]["scratch_paths"]["z_basis"]
            != inner_audits[1]["scratch_paths"]["z_basis"]
        )
        records = summary["inner_records"]
        checks["inner_records"] = (
            isinstance(records, Sequence)
            and not isinstance(records, (str, bytes))
            and len(records) == 2
            and all(_fixed20_record(record) for record in records)
            and [record["run_index"] for record in records] == [1, 2]
            and records[0]["rhs_sha256"] == records[1]["rhs_sha256"]
        )
        checks["inner_residual"] = (
            checks["inner_records"]
            and all(
                _finite_bounded(
                    record["true_residual"], W16A_INNER_TRUE_RESIDUAL_LIMIT
                )
                for record in records
            )
        )
        checks["z_identity"] = _identity_gate(summary["z_identity"])
        checks["p_identity"] = _identity_gate(summary["p_identity"])

        measurements = summary["measurements"]
        checks["measurements"] = (
            isinstance(measurements, Sequence)
            and not isinstance(measurements, (str, bytes))
            and len(measurements) == 2
            and all(
                _measurement_gate(measurement, expected_schema=W16A_SCHEMA)
                for measurement in measurements
            )
        )
        action_audit = summary["action_audit"]
        checks["action_counts"] = (
            isinstance(action_audit, Mapping)
            and action_audit["global_shifted_action_count"] == 42
            and action_audit["local_pc_apply_count"] == 40
            and action_audit["local_exact_shifted_volume_action_count"] == 40
            and action_audit["shifted_action_total_count"] == 82
            and action_audit["physical_action_count"] == 2
            and action_audit["physical_dtn_action_count"] == 2
        )

        architecture = summary["architecture"]
        checks["architecture"] = (
            isinstance(architecture, Mapping)
            and architecture["fine_space"] == "uncondensed_fullspace"
            and architecture["physical_operator"]
            == "beta0_volume_plus_matrix_free_dtn80"
            and architecture["auxiliary_dtn_used"] is False
            and architecture["global_matrix_materialized"] is False
            and architecture["augmented_matrix_materialized"] is False
            and architecture["condensation"] is False
            and architecture["static_condensation"] is False
            and architecture["trace_slab"] is False
            and architecture["slab_factors"] == 0
            and architecture["physical_ksp_used"] is False
            and architecture["pde_used"] is False
            and architecture["official_rta"] is False
        )

        lifecycle = summary["lifecycle"]
        checks["lifecycle"] = (
            isinstance(lifecycle, Mapping)
            and lifecycle["events"] == [
                "auxiliary_constructed",
                "inner_apply_1",
                "inner_apply_2",
                "auxiliary_released",
                "physical_constructed",
                "physical_apply_1",
                "physical_apply_2",
                "physical_released",
            ]
            and lifecycle["auxiliary_physical_overlap"] is False
            and lifecycle["release_between_inner_runs"] is False
        )

        prediction = summary["prediction"]
        checks["prediction"] = (
            isinstance(prediction, Mapping)
            and prediction["bytes"] == W16A_PREDICTED_LIVE_SET_BYTES
            and prediction["limit_bytes"] == W16A_PREDICTED_LIVE_SET_LIMIT_BYTES
            and prediction["watchdog_limit_bytes"] == W16A_WATCHDOG_LIMIT_BYTES
            and prediction["bytes"] <= prediction["limit_bytes"]
            and prediction["derived_not_measured"] is True
            and prediction["per_run_scratch_bytes"] == W16A_SCRATCH_PER_RUN_BYTES
            and prediction["two_run_scratch_bytes"]
            == W16A_SCRATCH_TWO_RUN_TOTAL_BYTES
            and prediction["scratch_is_disk_not_rss"] is True
            and prediction["swap_bytes"] == 0
        )
    except (KeyError, IndexError, TypeError, ValueError):
        pass

    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(name for name, passed in checks.items() if not passed),
    }


def evaluate_w16r_restart20_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute W16R's fixed additional-20-step numeric contract."""

    checks = {
        name: False
        for name in (
            "schema",
            "restart_authority",
            "inner_audits",
            "inner_records",
            "inner_residual",
            "z_identity",
            "p_identity",
            "measurements",
            "action_counts",
            "architecture",
            "lifecycle",
            "prediction",
        )
    }
    if not isinstance(summary, Mapping):
        return {
            "pass": False,
            "checks": checks,
            "problems": sorted(checks),
        }
    try:
        checks["schema"] = summary["schema"] == W16R_SCHEMA
        authority = summary["restart_authority"]
        checks["restart_authority"] = (
            isinstance(authority, Mapping)
            and authority["initial_solution_provided"] is True
            and authority["initial_solution_role"] == "W16A_run1_run2_z20"
            and isinstance(authority["z20_sha256"], str)
            and len(authority["z20_sha256"]) == 64
            and authority["w16a_numeric_fail_only_worker_action_gate"] is True
        )
        audits = summary["inner_audits"]
        checks["inner_audits"] = (
            isinstance(audits, Sequence)
            and not isinstance(audits, (str, bytes))
            and len(audits) == 2
            and all(
                _fixed20_inner_audit(audit, initial_solution_provided=True)
                for audit in audits
            )
            and audits[0]["scratch_paths"]["v_basis"]
            != audits[1]["scratch_paths"]["v_basis"]
            and audits[0]["scratch_paths"]["z_basis"]
            != audits[1]["scratch_paths"]["z_basis"]
        )
        records = summary["inner_records"]
        checks["inner_records"] = (
            isinstance(records, Sequence)
            and not isinstance(records, (str, bytes))
            and len(records) == 2
            and all(
                _fixed20_record(record, initial_solution_provided=True)
                for record in records
            )
            and [record["run_index"] for record in records] == [1, 2]
            and records[0]["rhs_sha256"] == records[1]["rhs_sha256"]
            and all(
                record["initial_solution_sha256"] == authority["z20_sha256"]
                for record in records
            )
            and all(
                record["initial_cumulative_iteration"] == 20
                and record["additional_iterations"] == 20
                and record["cumulative_iteration"] == 40
                for record in records
            )
        )
        checks["inner_residual"] = (
            checks["inner_records"]
            and all(
                _finite_bounded(
                    record["true_residual"], W16A_INNER_TRUE_RESIDUAL_LIMIT
                )
                for record in records
            )
        )
        checks["z_identity"] = _identity_gate(summary["z40_identity"])
        checks["p_identity"] = _identity_gate(summary["p_identity"])
        measurements = summary["measurements"]
        checks["measurements"] = (
            isinstance(measurements, Sequence)
            and not isinstance(measurements, (str, bytes))
            and len(measurements) == 2
            and all(
                _measurement_gate(item, expected_schema=W16R_SCHEMA)
                for item in measurements
            )
        )
        action_audit = summary["action_audit"]
        checks["action_counts"] = (
            isinstance(action_audit, Mapping)
            and action_audit["global_shifted_action_count"] == W16R_GLOBAL_ACTION_COUNT_TOTAL
            and action_audit["local_pc_apply_count"] == W16R_LOCAL_PC_COUNT_TOTAL
            and action_audit["local_exact_shifted_volume_action_count"] == W16R_LOCAL_PC_COUNT_TOTAL
            and action_audit["shifted_action_total_count"] == 84
            and action_audit["physical_action_count"] == 2
            and action_audit["physical_dtn_action_count"] == 2
        )
        architecture = summary["architecture"]
        checks["architecture"] = (
            isinstance(architecture, Mapping)
            and architecture["fine_space"] == "uncondensed_fullspace"
            and architecture["physical_operator"] == "beta0_volume_plus_matrix_free_dtn80"
            and architecture["auxiliary_dtn_used"] is False
            and architecture["global_matrix_materialized"] is False
            and architecture["augmented_matrix_materialized"] is False
            and architecture["condensation"] is False
            and architecture["static_condensation"] is False
            and architecture["trace_slab"] is False
            and architecture["slab_factors"] == 0
            and architecture["physical_ksp_used"] is False
            and architecture["pde_used"] is False
            and architecture["official_rta"] is False
        )
        lifecycle = summary["lifecycle"]
        checks["lifecycle"] = (
            isinstance(lifecycle, Mapping)
            and lifecycle["events"] == [
                "auxiliary_constructed",
                "inner_apply_1",
                "inner_apply_2",
                "auxiliary_released",
                "physical_constructed",
                "physical_apply_1",
                "physical_apply_2",
                "physical_released",
            ]
            and lifecycle["auxiliary_physical_overlap"] is False
            and lifecycle["release_between_inner_runs"] is False
        )
        prediction = summary["prediction"]
        checks["prediction"] = (
            isinstance(prediction, Mapping)
            and prediction["bytes"] == W16R_PREDICTED_LIVE_SET_BYTES
            and prediction["limit_bytes"] == W16A_PREDICTED_LIVE_SET_LIMIT_BYTES
            and prediction["watchdog_limit_bytes"] == W16A_WATCHDOG_LIMIT_BYTES
            and prediction["bytes"] <= prediction["limit_bytes"]
            and prediction["derived_not_measured"] is True
            and prediction["frozen_z20_vector_bytes"] == W16A_VECTOR_BYTES
            and prediction["scratch_is_disk_not_rss"] is True
            and prediction["per_run_scratch_bytes"] == W16A_SCRATCH_PER_RUN_BYTES
            and prediction["two_run_scratch_bytes"]
            == W16A_SCRATCH_TWO_RUN_TOTAL_BYTES
            and prediction["swap_bytes"] == 0
            and prediction["assumptions"]
            == {
                "reuses_w16a_calibrated_bound": True,
                "one_frozen_z20_vector": True,
                "auxiliary_physical_sequential": True,
                "warm_cache_compiler_process_count": 0,
                "disk_scratch_not_rss": True,
            }
            and prediction["components"]
            == {
                "w16a_calibrated_bound_bytes": W16A_PREDICTED_LIVE_SET_BYTES,
                "frozen_z20_vector_bytes": W16A_VECTOR_BYTES,
                "disk_scratch_bytes_not_rss": W16A_SCRATCH_TWO_RUN_TOTAL_BYTES,
            }
            and prediction["bytes"]
            == prediction["components"]["w16a_calibrated_bound_bytes"]
            + prediction["components"]["frozen_z20_vector_bytes"]
            and prediction["basis"]
            == (
                "W16R derived bound = W16A calibrated bound + one frozen z20 "
                "vector; auxiliary and physical lifetimes are sequential; warm "
                "cache assumes zero compiler processes; disk scratch is not RSS "
                "and bytes are not measured."
            )
        )
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": sorted(name for name, passed in checks.items() if not passed),
    }
