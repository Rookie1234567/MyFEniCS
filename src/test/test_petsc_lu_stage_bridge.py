"""Tiny contracts for explicit PETSc/MUMPS LU stages.

Both matrices are 8x8 complex AIJ systems (at most three entries per row).
These checks establish API-stage separation and ownership, not large-factor
memory prediction or production ordering equivalence.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import petsc_lu_stage_bridge
import pytest
from petsc4py import PETSc
from petsc_lu_stage_bridge import create_lu_stage, numeric_event_count_raw

from benchmarks.task041_exact_side_workflow import (
    _task041_w0p7_amd_control_errors,
    _task041_w0p7_analysis_ordering_errors,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from src.solvers.petsc_lu_stage import (
    StagedFactorRejected,
    StagedMumpsLUFactory,
    load_lu_stage_bridge,
)


@pytest.fixture(scope="module", autouse=True)
def _begin_petsc_log_once() -> None:
    PETSc.Log.begin()


def _own(owned: list[Any], obj: Any) -> Any:
    owned.append(obj)
    return obj


def _distributed_dense_columns(
    matrix: PETSc.Mat, global_values: np.ndarray, owned: list[Any]
) -> tuple[PETSc.Mat, tuple[int, int], bool]:
    """Build a small dense matrix from only the rows owned by ``matrix`` columns."""

    values = np.asarray(global_values, dtype=np.complex128)
    _, global_columns = map(int, matrix.getSize())
    if values.ndim != 2 or values.shape[0] != global_columns:
        raise ValueError("dense column fixture must match the matrix column count")
    first, last = map(int, matrix.getOwnershipRangeColumn())
    dense = _own(
        owned,
        PETSc.Mat().createDense(
            size=((last - first, global_columns), values.shape[1]),
            comm=matrix.getComm(),
        ),
    )
    dense.getDenseArray()[:, :] = values[first:last, :]
    dense.assemble()
    ownership = tuple(map(int, dense.getOwnershipRange()))
    return dense, ownership, ownership == (first, last)


def _dense_original_residual(
    matrix: PETSc.Mat,
    rhs: PETSc.Mat,
    solution: PETSc.Mat,
    owned: list[Any],
) -> dict[str, Any]:
    residual = _own(owned, matrix.matMult(solution))
    residual.axpy(PETSc.ScalarType(-1.0), rhs)
    rhs_norm = float(rhs.norm(PETSc.NormType.FROBENIUS))
    residual_norm = float(residual.norm(PETSc.NormType.FROBENIUS))
    relative = residual_norm / rhs_norm if rhs_norm > 0.0 else None
    return {
        "rhs_frobenius_norm": rhs_norm if math.isfinite(rhs_norm) else None,
        "residual_frobenius_norm": (
            residual_norm if math.isfinite(residual_norm) else None
        ),
        "relative_frobenius_residual": (
            relative if relative is not None and math.isfinite(relative) else None
        ),
        "finite": math.isfinite(rhs_norm) and math.isfinite(residual_norm),
        "rhs_row_ownership": list(map(int, rhs.getOwnershipRange())),
        "solution_row_ownership": list(map(int, solution.getOwnershipRange())),
        "residual_row_ownership": list(map(int, residual.getOwnershipRange())),
        "limit": 5.0e-9,
    }


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


def _w0p7_amd_context_check(
    context: dict[str, Any], *, after_symbolic: bool
) -> tuple[bool, str | None]:
    """Check the registered side controls and, after analysis, its strategy."""
    comm_size = int(PETSc.COMM_WORLD.getSize())
    analysis = context.get("analysis_info_raw")
    readback = context.get("public_mumps_control_readback")
    if readback is None and isinstance(analysis, dict):
        readback = analysis.get("public_mumps_control_readback")
    errors = _task041_w0p7_amd_control_errors(
        readback,
        expected_comm_size=comm_size,
        expected_comm_rank=int(PETSc.COMM_WORLD.tompi4py().rank),
    )
    if context.get("icntl14_requested") != 40:
        errors.append("context ICNTL(14) does not match the tiny deferred P4 case")
    if after_symbolic:
        if (
            context.get("stage") != "after_symbolic_before_numeric"
            or not isinstance(analysis, dict)
            or analysis.get("stage") != "after_MatLUFactorSymbolic_before_numeric"
            or analysis.get("numeric_attempts") != 0
        ):
            errors.append("analysis record is not the pending numeric stage")
        errors.extend(
            _task041_w0p7_analysis_ordering_errors(
                analysis,
                expected_comm_size=comm_size,
                expected_comm_rank=int(PETSc.COMM_WORLD.tompi4py().rank),
            )
        )
    elif context.get("stage") != "before_symbolic":
        errors.append("pre-symbolic record has the wrong lifecycle stage")
    if errors or not isinstance(readback, dict):
        return False, None
    signature_record = dict(readback)
    profile = signature_record.get("factor_profile")
    if isinstance(profile, dict):
        profile = {key: value for key, value in profile.items() if key != "comm_rank"}
        signature_record["factor_profile"] = profile
    if after_symbolic and isinstance(analysis, dict):
        signature_record["post_symbolic_mumps_control_readback"] = analysis.get(
            "post_symbolic_mumps_control_readback"
        )
    try:
        signature = json.dumps(
            signature_record,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return False, None
    return True, signature


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
            ordinary_controls = {
                "ICNTL7": factor.get_mumps_icntl(7),
                "ICNTL28": factor.get_mumps_icntl(28),
            }
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
                "ordinary_default_controls": ordinary_controls,
                "analysis_info_raw": analysis,
                "analysis_only_decision": "do_not_call_numeric",
                "lifecycle_before_destroy": lifecycle_before_destroy,
            }
            local["stages"].append(stage_record)
            info_entries = (
                analysis.get("INFO_api_raw_by_rank", [])
                + analysis.get("INFOG_api_raw_by_rank", [])
            )
            info_by_index = {
                item.get("index"): item
                for item in analysis.get("INFO_api_raw_by_rank", [])
            }
            infog_by_index = {
                item.get("index"): item
                for item in analysis.get("INFOG_api_raw_by_rank", [])
            }
            layout = factor.layout_raw()
            stage_ok = (
                analysis.get("stage") == "after_MatLUFactorSymbolic_before_numeric"
                and analysis.get("icntl14_actual") == icntl14
                and analysis.get("numeric_attempts") == 0
                and lifecycle_before_destroy.get("numeric_attempts") == 0
                and len(analysis.get("INFO_api_raw_by_rank", [])) == 3
                and len(analysis.get("INFOG_api_raw_by_rank", [])) == 8
                and all(
                    item.get("query_error_code") == 0
                    and "raw_value" in item
                    for item in info_entries
                )
                and info_by_index[15].get("unit")
                == "million_bytes_10^6_bytes; raw integer retained"
                and info_by_index[15].get("meaning_status")
                == "verified_against_MUMPS_5.6.2_user_guide"
                and info_by_index[4].get("unit") == "raw_integer_entry_count"
                and info_by_index[4].get("meaning_status")
                == "verified_against_MUMPS_5.6.2_user_guide"
                and infog_by_index[16].get("unit")
                == "million_bytes_10^6_bytes; raw integer retained"
                and infog_by_index[17].get("unit")
                == "million_bytes_10^6_bytes; raw integer retained"
                and infog_by_index[32].get("unit")
                == "enum; 1=sequential,2=parallel; raw integer retained"
                and infog_by_index[32].get("meaning_status")
                == "verified_against_MUMPS_5.6.2_user_guide"
                and 18 not in infog_by_index
                and 19 not in infog_by_index
                and ordinary_controls == {"ICNTL7": 7, "ICNTL28": 1}
                and analysis.get("byte_estimate") is None
                and tuple(layout.get("source", {}).get("global_size", ()))
                == (8, 8)
                and tuple(layout.get("factor", {}).get("global_size", ()))
                == (8, 8)
                and factor.get_mumps_icntl(14) == icntl14
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


def test_lu_stage_factory_gates_one_factor_and_research_factor_uses_direct_api() -> None:
    owned: list[Any] = []
    comm = PETSc.COMM_WORLD.tompi4py()
    local: dict[str, Any] = {
        "rank": comm.rank,
        "local_pass": True,
        "callback_order": [],
        "solve_residuals": {},
        "cleanup": [],
    }
    research_factor = None
    staged_factor = None
    loaded_bridge = None

    def unanimous(local_value: bool) -> bool:
        return all(bool(value) for value in comm.allgather(local_value))

    def pre_symbolic(context: Any) -> bool:
        local["callback_order"].append("pre_symbolic")
        return unanimous(
            context.get("stage") == "before_symbolic"
            and context.get("layout_raw", {}).get("source") is not None
            and context.get("layout_raw", {}).get("factor") is None
            and context.get("lifecycle", {}).get("symbolic_attempts") == 0
            and context.get("lifecycle", {}).get("numeric_attempts") == 0
        )

    def pre_numeric(context: Any) -> bool:
        local["callback_order"].append("pre_numeric_budget_consensus")
        return unanimous(
            context.get("stage") == "after_symbolic_before_numeric"
            and context.get("layout_raw", {}).get("factor", {}).get(
                "global_size"
            ) == (8, 8)
            and context.get("analysis_info_raw", {}).get("numeric_attempts") == 0
            and context.get("lifecycle", {}).get("symbolic_completed") is True
            and context.get("lifecycle", {}).get("numeric_attempts") == 0
        )

    try:
        bridge_path = Path(petsc_lu_stage_bridge.__file__).resolve(strict=True)
        loaded_bridge = load_lu_stage_bridge(bridge_path)
        explicit_loader = {
            "requested_path": str(bridge_path),
            "loaded_path": str(Path(loaded_bridge.__file__).resolve(strict=True)),
            "same_module": loaded_bridge is petsc_lu_stage_bridge,
            "native_activation_marker": os.environ.get(
                "MYFENICS_NATIVE_COMPLEX_ENV"
            ),
            "scalar_type": str(np.dtype(PETSc.ScalarType)),
            "scalar_sizeof": np.dtype(PETSc.ScalarType).itemsize,
            "bridge_scalar_sizeof": getattr(
                loaded_bridge, "petsc_scalar_sizeof", None
            ),
            "int_type": str(np.dtype(PETSc.IntType)),
            "int_sizeof": np.dtype(PETSc.IntType).itemsize,
            "bridge_int_sizeof": getattr(loaded_bridge, "petsc_int_sizeof", None),
            "complex_scalar": getattr(loaded_bridge, "petsc_complex_scalar", None),
        }
        local["explicit_loader"] = explicit_loader
        explicit_loader_ok = bool(
            loaded_bridge is petsc_lu_stage_bridge
            and Path(loaded_bridge.__file__).resolve(strict=True) == bridge_path
            and explicit_loader["native_activation_marker"] == "1"
            and np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
            and explicit_loader["complex_scalar"] == 1
            and explicit_loader["bridge_scalar_sizeof"]
            == explicit_loader["scalar_sizeof"]
            and explicit_loader["bridge_int_sizeof"] == explicit_loader["int_sizeof"]
        )
        matrix = _tiny_complex_matrix(owned)
        stage_factory = StagedMumpsLUFactory(
            loaded_bridge,
            pre_symbolic_gate=pre_symbolic,
            pre_numeric_gate=pre_numeric,
        )
        research_factor = ResearchExactFactorInverse(
            matrix,
            factor_only_storage=True,
            stage_factory=stage_factory,
        )
        staged_factor = research_factor._staged_factor
        if staged_factor is None:
            raise RuntimeError("Research factor did not retain staged direct handle")

        exact = _own(owned, matrix.createVecRight())
        rhs = _own(owned, matrix.createVecLeft())
        solution = _own(owned, matrix.createVecRight())
        residual = _own(owned, matrix.createVecLeft())
        transpose_rhs = _own(owned, matrix.createVecLeft())
        transpose_solution = _own(owned, matrix.createVecRight())
        transpose_residual = _own(owned, matrix.createVecLeft())
        first, last = map(int, exact.getOwnershipRange())
        for index in range(first, last):
            exact.setValue(index, PETSc.ScalarType(0.5 + index + 0.125j * (index + 1)))
        exact.assemble()
        matrix.mult(exact, rhs)
        matrix.multTranspose(exact, transpose_rhs)
        research_factor.release_borrowed_matrix()
        research_factor.solve(rhs, solution)
        staged_factor.solveTranspose(transpose_rhs, transpose_solution)
        matrix.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        matrix.multTranspose(transpose_solution, transpose_residual)
        transpose_residual.axpy(PETSc.ScalarType(-1.0), transpose_rhs)
        rhs_norm = float(rhs.norm())
        residual_norm = float(residual.norm())
        transpose_rhs_norm = float(transpose_rhs.norm())
        transpose_residual_norm = float(transpose_residual.norm())
        local["solve_residuals"] = {
            "MatSolve_relative": residual_norm / rhs_norm,
            "MatSolveTranspose_relative": (
                transpose_residual_norm / transpose_rhs_norm
            ),
            "source_borrow_released": research_factor.matrix is None,
        }

        exact_columns = np.column_stack(
            (np.arange(1, 9) + 0.25j, np.arange(2, 10) - 0.5j)
        ).astype(np.complex128)
        dense_exact, exact_ownership, exact_layout_ok = _distributed_dense_columns(
            matrix, exact_columns, owned
        )
        exact_layout_ok = all(comm.allgather(exact_layout_ok))
        if not exact_layout_ok:
            raise RuntimeError("distributed dense input rows do not match A columns")
        dense_rhs = _own(owned, matrix.matMult(dense_exact))
        dense_solution = _own(owned, dense_rhs.duplicate(copy=False))
        factor_row_ownership = tuple(
            map(int, staged_factor.factor_layout["row_ownership"])
        )
        solve_many_ownership_ok = (
            tuple(map(int, dense_rhs.getOwnershipRange())) == factor_row_ownership
            and tuple(map(int, dense_solution.getOwnershipRange()))
            == factor_row_ownership
        )
        solve_many_ownership_ok = all(comm.allgather(solve_many_ownership_ok))
        if not solve_many_ownership_ok:
            raise RuntimeError("distributed RHS rows do not match factor ownership")
        research_factor.solve_many(dense_rhs, dense_solution)
        batch_residual = _dense_original_residual(
            matrix, dense_rhs, dense_solution, owned
        )

        diagnostics = research_factor.diagnostics
        local["solve_residuals"]["distributed_two_column_solve_many"] = {
            **batch_residual,
            "exact_column_ownership": list(exact_ownership),
            "factor_row_ownership": list(factor_row_ownership),
            "ownership_matches_factor": solve_many_ownership_ok,
            "api": "ResearchExactFactorInverse.solve_many->MatMatSolve",
        }
        local["factor_diagnostics_before_destroy"] = diagnostics
        local["local_pass"] = bool(
            local["callback_order"]
            == ["pre_symbolic", "pre_numeric_budget_consensus"]
            and explicit_loader_ok
            and solve_many_ownership_ok
            and diagnostics.get("ksp_created") is False
            and diagnostics.get("ksp_destroyed") is None
            and diagnostics.get("factor_execution_mode")
            == "staged_direct_MatSolve_no_KSP_reason"
            and not hasattr(staged_factor, "getConvergedReason")
            and rhs_norm > 0.0
            and transpose_rhs_norm > 0.0
            and residual_norm / rhs_norm <= 5.0e-9
            and transpose_residual_norm / transpose_rhs_norm <= 5.0e-9
            and batch_residual["finite"] is True
            and batch_residual["rhs_frobenius_norm"] is not None
            and batch_residual["rhs_frobenius_norm"] > 0.0
            and batch_residual["relative_frobenius_residual"] is not None
            and batch_residual["relative_frobenius_residual"] <= 5.0e-9
        )
    except Exception as exc:  # noqa: BLE001 - all ranks record before assertions
        local["local_pass"] = False
        local["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        if research_factor is not None:
            try:
                research_factor.destroy()
                local["cleanup"].append(
                    {
                        "factor_execution_mode": research_factor.diagnostics.get(
                            "factor_execution_mode"
                        ),
                        "factor_destroyed": research_factor.diagnostics.get(
                            "factor_destroyed"
                        ),
                        "staged_lifecycle": (
                            None if staged_factor is None else dict(staged_factor.lifecycle)
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - preserve cleanup evidence
                local["local_pass"] = False
                local["cleanup"].append(
                    {"exception": f"{type(exc).__name__}: {exc}"}
                )
        local["cleanup"].extend(_destroy_owned(owned))

    ranks = _emit_rank_records("PETSC_LU_FACTORY_DIRECT_JSON=", local)
    assert all(record.get("local_pass") is True for record in ranks), ranks
    assert all(
        record.get("cleanup", [{}])[0].get("staged_lifecycle", {}).get(
            "factor_released"
        )
        is True
        for record in ranks
    ), ranks


def test_lu_stage_factory_rejects_unknown_pre_numeric_budget_and_cleans_factor() -> None:
    comm = PETSc.COMM_WORLD.tompi4py()
    local: dict[str, Any] = {
        "rank": comm.rank,
        "local_pass": True,
        "callback_order": [],
        "numeric_event_delta": None,
        "cleanup_status": None,
    }

    def pre_symbolic(context: Any) -> bool:
        local["callback_order"].append("pre_symbolic")
        return all(comm.allgather(context.get("stage") == "before_symbolic"))

    def reject_unknown_budget(context: Any) -> bool:
        local["callback_order"].append("pre_numeric_budget")
        unknown = context.get("analysis_info_raw", {}).get("byte_estimate") is None
        return all(comm.allgather(not unknown))

    owned: list[Any] = []
    try:
        matrix = _tiny_complex_matrix(owned)
        event_before = numeric_event_count_raw()
        factory = StagedMumpsLUFactory(
            petsc_lu_stage_bridge,
            pre_symbolic_gate=pre_symbolic,
            pre_numeric_gate=reject_unknown_budget,
        )
        try:
            factory(matrix, icntl14=40)
            local["local_pass"] = False
            local["exception"] = "unknown analysis budget unexpectedly passed"
        except StagedFactorRejected as exc:
            local["cleanup_status"] = exc.cleanup_status
        event_after = numeric_event_count_raw()
        before_count = _count(event_before)
        after_count = _count(event_after)
        local["numeric_event_delta"] = (
            None
            if before_count is None or after_count is None
            else after_count - before_count
        )
        local["local_pass"] = bool(
            local["local_pass"]
            and local["callback_order"]
            == ["pre_symbolic", "pre_numeric_budget"]
            and isinstance(local["cleanup_status"], dict)
            and local["cleanup_status"].get("numeric_attempts") == 0
            and local["cleanup_status"].get("factor_released") is True
            and local["cleanup_status"].get("destroy_error_code") == 0
            and local["numeric_event_delta"] == 0
        )
    except Exception as exc:  # noqa: BLE001 - serialize before all-rank assertion
        local["local_pass"] = False
        local["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        local["cleanup"] = _destroy_owned(owned)

    ranks = _emit_rank_records("PETSC_LU_REJECT_UNKNOWN_BUDGET_JSON=", local)
    assert all(record.get("local_pass") is True for record in ranks), ranks


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
        transpose_rhs = _own(owned, matrix.createVecLeft())
        transpose_solution = _own(owned, matrix.createVecRight())
        transpose_residual = _own(owned, matrix.createVecLeft())
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
        numeric_info = factor.numeric_info_raw()
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
        matrix.multTranspose(exact, transpose_rhs)
        factor.solve_transpose(transpose_rhs, transpose_solution)
        matrix.multTranspose(transpose_solution, transpose_residual)
        transpose_residual.axpy(PETSc.ScalarType(-1.0), transpose_rhs)
        transpose_rhs_norm = float(transpose_rhs.norm())
        transpose_residual_norm = float(transpose_residual.norm())
        transpose_relative = (
            transpose_residual_norm / transpose_rhs_norm
            if transpose_rhs_norm > 0.0
            else None
        )
        exact_columns = np.column_stack(
            (np.arange(1, 9) + 0.25j, np.arange(2, 10) - 0.5j)
        ).astype(np.complex128)
        exact_dense, exact_ownership, exact_layout_ok = _distributed_dense_columns(
            matrix, exact_columns, owned
        )
        comm = PETSc.COMM_WORLD.tompi4py()
        exact_layout_ok = all(comm.allgather(exact_layout_ok))
        if not exact_layout_ok:
            raise RuntimeError("distributed dense input rows do not match A columns")
        batch_rhs = _own(owned, matrix.matMult(exact_dense))
        batch_solution = _own(owned, batch_rhs.duplicate(copy=False))
        factor_row_ownership = tuple(
            map(int, factor.layout_raw()["factor"]["row_ownership"])
        )
        batch_ownership_ok = (
            tuple(map(int, batch_rhs.getOwnershipRange())) == factor_row_ownership
            and tuple(map(int, batch_solution.getOwnershipRange()))
            == factor_row_ownership
        )
        batch_ownership_ok = all(comm.allgather(batch_ownership_ok))
        if not batch_ownership_ok:
            raise RuntimeError("distributed RHS rows do not match factor ownership")
        factor.mat_solve(batch_rhs, batch_solution)
        batch_residual = _dense_original_residual(
            matrix, batch_rhs, batch_solution, owned
        )
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
            "numeric_info_raw": numeric_info,
            "layout_raw": factor.layout_raw(),
            "two_column_MatMatSolve": {
                **batch_residual,
                "exact_column_ownership": list(exact_ownership),
                "factor_row_ownership": list(factor_row_ownership),
                "ownership_matches_factor": batch_ownership_ok,
                "api": "MatMatSolve",
            },
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
        local["solve_api_modes"] = {
            "single_vector_MatSolve_relative_residual": relative_residual,
            "single_vector_MatSolveTranspose_relative_residual": transpose_relative,
            "two_column_MatMatSolve_relative_frobenius_residual": batch_residual[
                "relative_frobenius_residual"
            ],
            "two_column_MatMatSolve_status": "measured_on_active_comm",
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
            and numeric_info.get("numeric_completed") is True
            and numeric_info.get("numeric_attempts") == 1
            and {
                item.get("index")
                for item in numeric_info.get("INFOG_api_raw_by_rank", [])
            }
            == {1, 2, 18, 19}
            and all(
                item.get("query_error_code") == 0
                and "raw_value" in item
                for item in numeric_info.get("INFOG_api_raw_by_rank", [])
            )
            and {
                item.get("index"): item
                for item in numeric_info.get("INFOG_api_raw_by_rank", [])
            }[18].get("label")
            == "global_numeric_max_rank_allocated_memory"
            and {
                item.get("index"): item
                for item in numeric_info.get("INFOG_api_raw_by_rank", [])
            }[19].get("label")
            == "global_numeric_sum_ranks_allocated_memory"
            and all(
                item.get("unit")
                == "million_bytes_10^6_bytes; raw integer retained"
                and item.get("meaning_status")
                == "verified_against_MUMPS_5.6.2_user_guide"
                for item in numeric_info.get("INFOG_api_raw_by_rank", [])
                if item.get("index") in (18, 19)
            )
            and "must not be summed again across ranks"
            in numeric_info.get("interpretation_note", "")
            and finite_residual
            and rhs_norm > 0.0
            and relative_residual is not None
            and relative_residual <= 5.0e-9
            and math.isfinite(transpose_rhs_norm)
            and math.isfinite(transpose_residual_norm)
            and transpose_rhs_norm > 0.0
            and transpose_relative is not None
            and transpose_relative <= 5.0e-9
            and batch_ownership_ok
            and batch_residual["finite"] is True
            and batch_residual["rhs_frobenius_norm"] is not None
            and batch_residual["rhs_frobenius_norm"] > 0.0
            and batch_residual["relative_frobenius_residual"] is not None
            and batch_residual["relative_frobenius_residual"] <= 5.0e-9
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



def test_w0p7_pending_p4_handles_reject_solves_until_same_handle_numeric() -> None:
    """Exercise pending side handles on the existing distributed 8x8 matrix."""
    comm = PETSc.COMM_WORLD.tompi4py()
    owned: list[Any] = []
    factors: dict[str, ResearchExactFactorInverse] = {}
    local: dict[str, Any] = {"rank": comm.rank, "local_pass": True, "cleanup": []}
    event_deltas: dict[str, int | None] = {}
    matrix = None

    def consensus(value: bool) -> bool:
        return all(comm.allgather(bool(value)))

    def gate(context: Any) -> bool:
        identity = context.get("stage_identity")
        after_symbolic = context.get("stage") == "after_symbolic_before_numeric"
        amd_ok, signature = _w0p7_amd_context_check(
            context, after_symbolic=after_symbolic
        )
        live = {
            row.get("stage_identity"): row.get("factor_state")
            for row in context.get("live_factor_inventory", [])
            if isinstance(row, dict)
        }
        if context.get("stage") == "before_symbolic":
            expected = (
                {}
                if identity.endswith("bottom")
                else {"task041.w0p7.p4.bottom": "symbolic_live_pending_numeric"}
            )
            valid = (
                context.get("icntl14_requested") == 40
                and live == expected
                and amd_ok
            )
        else:
            expected = (
                {
                    "task041.w0p7.p4.bottom": "symbolic_live_pending_numeric",
                    "task041.w0p7.p4.top": "symbolic_live_pending_numeric",
                }
                if identity.endswith("bottom")
                else {
                    "task041.w0p7.p4.bottom": "numeric_ready",
                    "task041.w0p7.p4.top": "symbolic_live_pending_numeric",
                }
            )
            valid = (
                context.get("stage") == "after_symbolic_before_numeric"
                and context.get("lifecycle", {}).get("numeric_attempts") == 0
                and live == expected
                and amd_ok
            )
        rank_checks = comm.allgather((bool(valid), signature))
        return bool(
            all(row[0] for row in rank_checks)
            and all(row[1] is not None for row in rank_checks)
            and len({row[1] for row in rank_checks}) == 1
        )

    try:
        matrix = _tiny_complex_matrix(owned)
        factory = StagedMumpsLUFactory(
            petsc_lu_stage_bridge,
            pre_symbolic_gate=gate,
            pre_numeric_gate=gate,
            deferred_numeric_stage_identities=(
                "task041.w0p7.p4.bottom",
                "task041.w0p7.p4.top",
            ),
            sequential_amd_stage_identities=(
                "task041.w0p7.p4.bottom",
                "task041.w0p7.p4.top",
            ),
        )
        event_before = numeric_event_count_raw()

        for side in ("bottom", "top"):
            identity = f"task041.w0p7.p4.{side}"

            def make_stage(source, *, icntl14, defer_numeric=False, _id=identity):
                return factory(
                    source,
                    icntl14=icntl14,
                    stage_identity=_id,
                    defer_numeric=defer_numeric,
                )

            factors[side] = ResearchExactFactorInverse(
                matrix,
                factor_only_storage=True,
                stage_factory=make_stage,
                allow_pending_numeric=True,
            )

        handles = {side: factor._staged_factor for side, factor in factors.items()}
        event_symbolic = numeric_event_count_raw()
        before_count, symbolic_count = _count(event_before), _count(event_symbolic)
        event_deltas["both_symbolic"] = (
            None if before_count is None or symbolic_count is None
            else symbolic_count - before_count
        )

        exact = _own(owned, matrix.createVecRight())
        rhs = _own(owned, matrix.createVecLeft())
        solution = _own(owned, matrix.createVecRight())
        residual = _own(owned, matrix.createVecLeft())
        first, last = map(int, exact.getOwnershipRange())
        for row in range(first, last):
            exact.setValue(row, PETSc.ScalarType(0.75 + 0.2 * row + 0.125j))
        exact.assemble()
        matrix.mult(exact, rhs)

        dense, _, ownership_ok = _distributed_dense_columns(
            matrix,
            np.column_stack(
                (np.arange(1, 9) + 0.125j, np.arange(3, 11) - 0.25j)
            ).astype(np.complex128),
            owned,
        )
        batch_rhs = _own(owned, matrix.matMult(dense))
        batch_solution = _own(owned, batch_rhs.duplicate(copy=False))
        if not consensus(ownership_ok):
            raise RuntimeError("dense RHS ownership does not match the 8x8 matrix")

        rejections: dict[str, list[bool]] = {}
        for side, factor in factors.items():
            staged = handles[side]
            outcomes = []
            for method, args in (
                (factor.solve, (rhs, solution)),
                (factor.solve_many, (batch_rhs, batch_solution)),
                (staged.solve, (rhs, solution)),
                (staged.solveTranspose, (rhs, solution)),
                (staged.matSolve, (batch_rhs, batch_solution)),
                (staged.matSolveTranspose, (batch_rhs, batch_solution)),
                (factor.release_borrowed_matrix, ()),
            ):
                try:
                    method(*args)
                except RuntimeError:
                    outcomes.append(True)
                else:
                    outcomes.append(False)
            rejections[side] = outcomes
            local["local_pass"] &= (
                all(outcomes)
                and factor.matrix is matrix
                and factor.diagnostics["factor_state"]
                == "symbolic_live_pending_numeric"
            )

        for side in ("bottom", "top"):
            before = _count(numeric_event_count_raw())
            factors[side].complete_numeric()
            after = _count(numeric_event_count_raw())
            event_deltas[side] = (
                None if before is None or after is None else after - before
            )
            local.setdefault("same_handles", {})[side] = (
                factors[side]._staged_factor is handles[side]
                and handles[side].numeric_ready is True
            )
            if side == "bottom":
                local["top_still_pending"] = (
                    factors["top"].diagnostics["factor_state"]
                    == "symbolic_live_pending_numeric"
                )

        rhs_norm = float(rhs.norm())
        for side, factor in factors.items():
            factor.solve(rhs, solution)
            matrix.mult(solution, residual)
            residual.axpy(PETSc.ScalarType(-1), rhs)
            residual_norm = float(residual.norm())
            relative = residual_norm / rhs_norm if rhs_norm > 0 else None
            local.setdefault("relative_residuals", {})[side] = relative
            factor_row_ownership = tuple(
                map(
                    int,
                    factor._staged_factor.factor_layout[
                        "row_ownership"
                    ],
                )
            )
            batch_ownership_ok = (
                tuple(map(int, batch_rhs.getOwnershipRange()))
                == factor_row_ownership
                and tuple(map(int, batch_solution.getOwnershipRange()))
                == factor_row_ownership
            )
            batch_ownership_ok = consensus(batch_ownership_ok)
            if not batch_ownership_ok:
                raise RuntimeError(
                    f"{side} distributed batch rows do not match factor ownership"
                )
            factor.solve_many(batch_rhs, batch_solution)
            batch_residual = _dense_original_residual(
                matrix, batch_rhs, batch_solution, owned
            )
            batch_residual["factor_row_ownership"] = list(
                factor_row_ownership
            )
            batch_residual["ownership_matches_factor"] = batch_ownership_ok
            local.setdefault("batch_relative_frobenius_residuals", {})[
                side
            ] = batch_residual
            factor.release_borrowed_matrix()
            local["local_pass"] &= (
                math.isfinite(rhs_norm)
                and rhs_norm > 0
                and math.isfinite(residual_norm)
                and relative is not None
                and math.isfinite(relative)
                and relative <= 5.0e-9
                and batch_residual["finite"] is True
                and batch_residual["rhs_frobenius_norm"] is not None
                and batch_residual["rhs_frobenius_norm"] > 0.0
                and batch_residual["relative_frobenius_residual"] is not None
                and batch_residual["relative_frobenius_residual"] <= 5.0e-9
                and batch_residual["ownership_matches_factor"] is True
                and factor.matrix is None
            )

        local["numeric_event_deltas"] = event_deltas
        local["pending_operation_rejections"] = rejections
        local["local_pass"] &= (
            event_deltas["both_symbolic"] == 0
            and event_deltas["bottom"] == 1
            and event_deltas["top"] == 1
            and all(all(values) for values in rejections.values())
            and all(local["same_handles"].values())
            and local["top_still_pending"] is True
        )
    except Exception as exc:  # noqa: BLE001 - persist each rank result after cleanup
        local["local_pass"] = False
        local["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        for factor in reversed(tuple(factors.values())):
            staged = factor._staged_factor
            try:
                factor.destroy()
                status = dict(staged.lifecycle)
                local["cleanup"].append(status)
                local["local_pass"] &= (
                    status.get("factor_released") is True
                    and status.get("destroy_error_code") == 0
                )
            except Exception as exc:  # noqa: BLE001 - preserve cleanup evidence
                local["local_pass"] = False
                local["cleanup"].append({"exception": f"{type(exc).__name__}: {exc}"})
        local["cleanup"].extend(_destroy_owned(owned))

    ranks = _emit_rank_records("W0P7_PENDING_P4_LIFECYCLE_JSON=", local)
    assert all(record.get("local_pass") is True for record in ranks), ranks


def test_w0p7_pending_p4_numeric_budget_rejection_destroys_without_numeric() -> None:
    """An unknown pre-numeric budget rejects and destroys the pending handle."""
    comm = PETSc.COMM_WORLD.tompi4py()
    owned: list[Any] = []
    local: dict[str, Any] = {"rank": comm.rank, "local_pass": True}
    factor = None
    pending_destroy = None

    def gate(context: Any) -> bool:
        amd_ok, signature = _w0p7_amd_context_check(
            context, after_symbolic=False
        )
        valid = (
            context.get("stage") == "before_symbolic"
            and context.get("stage_identity") == "task041.w0p7.p4.bottom"
            and amd_ok
        )
        rank_checks = comm.allgather((bool(valid), signature))
        return bool(
            all(row[0] for row in rank_checks)
            and all(row[1] is not None for row in rank_checks)
            and len({row[1] for row in rank_checks}) == 1
        )

    def reject_unknown(context: Any) -> bool:
        amd_ok, signature = _w0p7_amd_context_check(
            context, after_symbolic=True
        )
        lifecycle = context.get("lifecycle", {})
        rank_checks = comm.allgather((amd_ok, signature))
        controls_consistent = bool(
            all(row[0] for row in rank_checks)
            and all(row[1] is not None for row in rank_checks)
            and len({row[1] for row in rank_checks}) == 1
        )
        local["unknown_budget"] = (
            context.get("stage") == "after_symbolic_before_numeric"
            and context.get("analysis_info_raw", {}).get("byte_estimate") is None
            and lifecycle.get("numeric_attempts") == 0
            and controls_consistent
        )
        return False

    try:
        matrix = _tiny_complex_matrix(owned)
        before = _count(numeric_event_count_raw())
        factory = StagedMumpsLUFactory(
            petsc_lu_stage_bridge,
            pre_symbolic_gate=gate,
            pre_numeric_gate=reject_unknown,
            deferred_numeric_stage_identities=("task041.w0p7.p4.bottom",),
            sequential_amd_stage_identities=("task041.w0p7.p4.bottom",),
        )
        # Explicit user destruction of a pending handle must stay symbolic-only.
        pending_destroy = factory(
            matrix,
            icntl14=40,
            stage_identity="task041.w0p7.p4.bottom",
            defer_numeric=True,
        )
        destroy_status = dict(pending_destroy.destroy())
        after_pending_destroy = _count(numeric_event_count_raw())
        local["pending_destroy"] = destroy_status
        local["pending_destroy_numeric_delta"] = (
            None
            if before is None or after_pending_destroy is None
            else after_pending_destroy - before
        )
        factor = _own(
            owned,
            factory(
                matrix,
                icntl14=40,
                stage_identity="task041.w0p7.p4.bottom",
                defer_numeric=True,
            ),
        )
        symbolic = _count(numeric_event_count_raw())
        try:
            factor.complete_numeric()
            local["rejected"] = False
        except StagedFactorRejected as exc:
            local["rejected"] = True
            local["cleanup_status"] = dict(exc.cleanup_status)
        after = _count(numeric_event_count_raw())
        local["symbolic_event_delta"] = (
            None if before is None or symbolic is None else symbolic - before
        )
        local["rejected_event_delta"] = (
            None if before is None or after is None else after - before
        )
        status = local.get("cleanup_status", {})
        local["local_pass"] = bool(
            local["rejected"] is True
            and local.get("unknown_budget") is True
            and local["symbolic_event_delta"] == 0
            and local["rejected_event_delta"] == 0
            and local["pending_destroy_numeric_delta"] == 0
            and destroy_status.get("factor_released") is True
            and destroy_status.get("destroy_error_code") == 0
            and destroy_status.get("numeric_attempts") == 0
            and status.get("numeric_attempts") == 0
            and status.get("factor_released") is True
            and status.get("destroy_error_code") == 0
            and factor.destroyed is True
        )
    except Exception as exc:  # noqa: BLE001 - persist each rank result after cleanup
        local["local_pass"] = False
        local["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        local["cleanup"] = _destroy_owned(owned)

    ranks = _emit_rank_records("W0P7_PENDING_BUDGET_REJECT_JSON=", local)
    assert all(record.get("local_pass") is True for record in ranks), ranks
