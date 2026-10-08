"""Tiny contracts for explicit PETSc/MUMPS LU stages.

Both matrices are 8x8 complex AIJ systems (at most three entries per row).
These checks establish API-stage separation and ownership, not large-factor
memory prediction or production ordering equivalence.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from petsc4py import PETSc
from petsc_lu_stage_bridge import create_lu_stage, numeric_event_count_raw


@pytest.fixture(scope="module", autouse=True)
def _begin_petsc_log_once() -> None:
    PETSc.Log.begin()


def _own(owned: list[Any], obj: Any) -> Any:
    owned.append(obj)
    return obj


def _tiny_complex_matrix(owned: list[Any]) -> PETSc.Mat:
    size = 8
    matrix = _own(
        owned,
        PETSc.Mat().createAIJ(
            size=(size, size), nnz=3, comm=PETSc.COMM_WORLD
        ),
    )
    row_start, row_end = matrix.getOwnershipRange()
    for row in range(row_start, row_end):
        matrix.setValue(row, row, PETSc.ScalarType(5.0 + 0.25j))
        if row > 0:
            matrix.setValue(row, row - 1, PETSc.ScalarType(-0.5 + 0.2j))
        if row + 1 < size:
            matrix.setValue(row, row + 1, PETSc.ScalarType(0.25 - 0.1j))
    matrix.assemblyBegin()
    matrix.assemblyEnd()
    return matrix


def _count(event_snapshot: dict[str, Any]) -> int | None:
    if event_snapshot.get("query_error_code") != 0:
        return None
    value = event_snapshot.get("count")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _destroy_owned(owned: list[Any]) -> list[dict[str, Any]]:
    cleanup: list[dict[str, Any]] = []
    while owned:
        obj = owned.pop()
        item: dict[str, Any] = {"python_type": type(obj).__name__}
        try:
            result = obj.destroy()
            if isinstance(result, dict):
                item["bridge_lifecycle"] = result
                item["released"] = result.get("factor_released") is True
                item["error_code"] = result.get("destroy_error_code")
            else:
                item["release_call_completed"] = True
                item["released"] = True
                if result is not None:
                    item["destroy_return_type"] = type(result).__name__
        except Exception as exc:  # noqa: BLE001 - record cleanup failure and continue releasing
            item["released"] = False
            item["exception"] = f"{type(exc).__name__}: {exc}"
        cleanup.append(item)
    return cleanup


def _remove_owned(owned: list[Any], target: Any) -> None:
    for index, item in enumerate(owned):
        if item is target:
            del owned[index]
            return


def _emit_rank_records(prefix: str, local: dict[str, Any]) -> list[dict[str, Any]]:
    comm = PETSc.COMM_WORLD.tompi4py()
    gathered = comm.allgather(local)
    if comm.rank == 0:
        print(
            prefix
            + json.dumps(
                {"rank_records": gathered},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            flush=True,
        )
    return gathered


def test_lu_stage_symbolic_only_keeps_raw_info_and_releases_in_call_order() -> None:
    """The call-graph order is one-cell ICNTL14=100, then both sides at 40."""
    owned: list[Any] = []
    local: dict[str, Any] = {
        "rank": PETSc.COMM_WORLD.tompi4py().rank,
        "matrix_shape": [8, 8],
        "matrix_max_nnz_per_row": 3,
        "decision": "stop_after_symbolic_by_policy",
        "stages": [],
        "cleanup": [],
        "local_pass": True,
    }
    try:
        matrix = _tiny_complex_matrix(owned)
        for stage_name, icntl14 in (
            ("one_cell_before_sides", 100),
            ("bottom_side", 40),
            ("top_side", 40),
        ):
            factor = _own(owned, create_lu_stage(matrix, icntl14=icntl14))
            event_before = numeric_event_count_raw()
            factor.symbolic()
            analysis = factor.analysis_info_raw()
            event_after = numeric_event_count_raw()
            lifecycle_before_destroy = factor.lifecycle()
            before_count = _count(event_before)
            after_count = _count(event_after)
            delta = (
                after_count - before_count
                if before_count is not None and after_count is not None
                else None
            )
            stage_record = {
                "stage": stage_name,
                "icntl14_requested": icntl14,
                "numeric_event_before": event_before,
                "numeric_event_after_symbolic": event_after,
                "numeric_event_delta": delta,
                "analysis_info_raw": analysis,
                "analysis_only_decision": "do_not_call_numeric",
                "lifecycle_before_destroy": lifecycle_before_destroy,
            }
            local["stages"].append(stage_record)
            info_entries = (
                analysis.get("INFO_api_raw_by_rank", [])
                + analysis.get("INFOG_api_raw_by_rank", [])
            )
            stage_ok = (
                analysis.get("stage") == "after_MatLUFactorSymbolic_before_numeric"
                and analysis.get("icntl14_actual") == icntl14
                and analysis.get("numeric_attempts") == 0
                and lifecycle_before_destroy.get("numeric_attempts") == 0
                and len(analysis.get("INFO_api_raw_by_rank", [])) == 2
                and len(analysis.get("INFOG_api_raw_by_rank", [])) == 7
                and all(
                    item.get("query_error_code") == 0
                    and item.get("unit") == "unknown; raw integer only, no byte conversion"
                    and item.get("meaning_status")
                    == "unknown_for_installed_MUMPS_version"
                    and "raw_value" in item
                    for item in info_entries
                )
                and event_before.get("compiled_with_logging") is True
                and event_before.get("query_error_code") == 0
                and event_after.get("query_error_code") == 0
                and delta == 0
            )
            local["local_pass"] = bool(local["local_pass"] and stage_ok)

            cleanup = factor.destroy()
            local["cleanup"].append(
                {
                    "python_type": "LUStageFactor",
                    "stage": stage_name,
                    "status": cleanup,
                    "released": cleanup.get("factor_released") is True,
                    "error_code": cleanup.get("destroy_error_code"),
                }
            )
            _remove_owned(owned, factor)
            local["local_pass"] = bool(
                local["local_pass"]
                and cleanup.get("destroy_attempts") == 1
                and cleanup.get("destroy_error_code") == 0
                and cleanup.get("factor_released") is True
            )

    except Exception as exc:  # noqa: BLE001 - serialize the failure before asserting on all ranks
        local["local_pass"] = False
        local["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        local["cleanup"].extend(_destroy_owned(owned))

    ranks = _emit_rank_records("PETSC_LU_SYMBOLIC_ONLY_JSON=", local)
    assert all(record.get("local_pass") is True for record in ranks), ranks
    assert all(len(record.get("stages", [])) == 3 for record in ranks), ranks
    assert all(
        cleanup.get("status", {}).get("factor_released") is True
        and cleanup.get("status", {}).get("destroy_error_code") == 0
        for record in ranks
        for cleanup in record.get("cleanup", [])
        if "status" in cleanup
    ), ranks
    assert all(
        all(item.get("released") is True for item in record.get("cleanup", []))
        for record in ranks
    ), ranks


def test_lu_stage_numeric_is_explicit_and_checks_original_matrix_residual() -> None:
    """A separate 8x8 case proves the PETSc numeric event advances on request."""
    owned: list[Any] = []
    local: dict[str, Any] = {
        "rank": PETSc.COMM_WORLD.tompi4py().rank,
        "matrix_shape": [8, 8],
        "matrix_max_nnz_per_row": 3,
        "local_pass": True,
        "analysis_info_raw": None,
        "numeric_event": {},
        "original_A_residual": {},
        "cleanup": [],
    }
    try:
        matrix = _tiny_complex_matrix(owned)
        exact = _own(owned, matrix.createVecRight())
        rhs = _own(owned, matrix.createVecLeft())
        solution = _own(owned, matrix.createVecRight())
        residual = _own(owned, matrix.createVecLeft())
        factor = _own(owned, create_lu_stage(matrix, icntl14=40))

        row_start, row_end = exact.getOwnershipRange()
        for index in range(row_start, row_end):
            exact.setValue(
                index,
                PETSc.ScalarType(0.25 * (index + 1) + 0.125j * (index + 2)),
            )
        exact.assemblyBegin()
        exact.assemblyEnd()
        matrix.mult(exact, rhs)

        event_before = numeric_event_count_raw()
        factor.symbolic()
        symbolic_analysis = factor.analysis_info_raw()
        event_after_symbolic = numeric_event_count_raw()
        factor.numeric()
        event_after_numeric = numeric_event_count_raw()
        before_count = _count(event_before)
        symbolic_count = _count(event_after_symbolic)
        after_count = _count(event_after_numeric)
        symbolic_delta = (
            symbolic_count - before_count
            if before_count is not None and symbolic_count is not None
            else None
        )
        numeric_delta = (
            after_count - symbolic_count
            if symbolic_count is not None and after_count is not None
            else None
        )
        try:
            factor.analysis_info_raw()
            analysis_rejected_after_numeric = False
        except RuntimeError:
            analysis_rejected_after_numeric = True

        factor.solve(rhs, solution)
        matrix.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        rhs_norm = float(rhs.norm())
        residual_norm = float(residual.norm())
        relative_residual = residual_norm / rhs_norm if rhs_norm > 0.0 else None
        finite_residual = math.isfinite(rhs_norm) and math.isfinite(residual_norm)
        lifecycle = factor.lifecycle()
        local["analysis_info_raw"] = symbolic_analysis
        local["numeric_event"] = {
            "before": event_before,
            "after_symbolic": event_after_symbolic,
            "after_numeric": event_after_numeric,
            "symbolic_delta": symbolic_delta,
            "numeric_delta": numeric_delta,
            "analysis_rejected_after_numeric": analysis_rejected_after_numeric,
            "lifecycle": lifecycle,
        }
        local["original_A_residual"] = {
            "rhs_norm": rhs_norm if math.isfinite(rhs_norm) else None,
            "residual_norm": residual_norm if math.isfinite(residual_norm) else None,
            "relative_residual": (
                relative_residual
                if relative_residual is not None and math.isfinite(relative_residual)
                else None
            ),
            "zero_rhs_branch": rhs_norm == 0.0,
            "finite": finite_residual,
            "limit": 5.0e-9,
        }
        local["local_pass"] = bool(
            event_before.get("compiled_with_logging") is True
            and event_before.get("query_error_code") == 0
            and event_after_symbolic.get("query_error_code") == 0
            and event_after_numeric.get("query_error_code") == 0
            and symbolic_delta == 0
            and numeric_delta is not None
            and numeric_delta > 0
            and analysis_rejected_after_numeric
            and lifecycle.get("numeric_attempts") == 1
            and lifecycle.get("numeric_completed") is True
            and finite_residual
            and rhs_norm > 0.0
            and relative_residual is not None
            and relative_residual <= 5.0e-9
        )
    except Exception as exc:  # noqa: BLE001 - serialize the failure before asserting on all ranks
        local["local_pass"] = False
        local["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        local["cleanup"].extend(_destroy_owned(owned))

    ranks = _emit_rank_records("PETSC_LU_NUMERIC_EXPLICIT_JSON=", local)
    assert all(record.get("local_pass") is True for record in ranks), ranks
    assert all(
        any(
            entry.get("python_type") == "LUStageFactor"
            and entry.get("released") is True
            and entry.get("error_code") == 0
            for entry in record.get("cleanup", [])
        )
        for record in ranks
    ), ranks
    assert all(
        all(item.get("released") is True for item in record.get("cleanup", []))
        for record in ranks
    ), ranks
