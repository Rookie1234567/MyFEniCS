"""Explicit loader and callback-gated adapter for the PETSc LU-stage bridge.

The extension is deliberately not imported, compiled, or installed by this
module. Call :func:`load_lu_stage_bridge` with the exact extension path built
for the active native PETSc ABI, then pass the returned module to
:class:`StagedMumpsLUFactory`.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from petsc4py import PETSc

GateCallback = Callable[[Mapping[str, Any]], bool]
ConfigureCallback = Callable[[Any], None]


def _require_active_petsc_abi(module: ModuleType) -> None:
    if (
        getattr(module, "petsc_complex_scalar", None) != 1
        or getattr(module, "petsc_scalar_sizeof", None)
        != np.dtype(PETSc.ScalarType).itemsize
        or getattr(module, "petsc_int_sizeof", None)
        != np.dtype(PETSc.IntType).itemsize
    ):
        raise ImportError(
            "bridge compile-time PETSc scalar/index ABI does not match active petsc4py"
        )


class StagedFactorRejected(RuntimeError):
    """A unanimous explicit stage gate declined the next factor stage."""

    def __init__(self, message: str, *, cleanup_status: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.cleanup_status = None if cleanup_status is None else dict(cleanup_status)


def load_lu_stage_bridge(extension_path: str | Path) -> ModuleType:
    """Load one explicitly named extension built for the current native ABI.

    There is no import-path search, implicit build, KSP fallback, or automatic
    installation. The caller must activate the repository's native complex
    environment before calling this function.
    """

    if os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") != "1":
        raise RuntimeError("native complex activation marker is absent")
    repository_root = Path(__file__).resolve().parents[2]
    if Path(os.path.abspath(sys.executable)).parent != repository_root / ".venv/bin":
        raise RuntimeError("loader requires the repository's active .venv interpreter")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError(
            f"loader requires complex128 PETSc, got {np.dtype(PETSc.ScalarType)}"
        )
    path = Path(extension_path).expanduser().resolve(strict=True)
    if not path.is_file() or not any(
        path.name.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    ):
        raise ImportError(f"not a Python extension module path: {path}")

    module_name = "petsc_lu_stage_bridge"
    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_path = Path(getattr(existing, "__file__", "")).resolve()
        if existing_path != path:
            raise ImportError(
                "a different petsc_lu_stage_bridge is already loaded: "
                f"{existing_path} != {path}"
            )
        _require_active_petsc_abi(existing)
        return existing

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create an extension loader for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    if not callable(getattr(module, "create_lu_stage", None)):
        sys.modules.pop(module_name, None)
        raise TypeError(
            f"{path} does not expose create_lu_stage"
        )
    try:
        _require_active_petsc_abi(module)
    except ImportError:
        sys.modules.pop(module_name, None)
        raise
    return module


class StagedMumpsFactor:
    """Direct MatSolve adapter; it intentionally has no KSP convergence reason."""

    factor_solve_semantics = "direct_MatSolve_no_KSP_reason"
    explicit_staged_direct_factor = True

    def __init__(
        self,
        raw_factor: Any,
        *,
        comm: Any,
        layout_raw: Mapping[str, Any],
        analysis_info_raw: Mapping[str, Any],
        numeric_info_raw: Mapping[str, Any],
    ) -> None:
        self._raw_factor = raw_factor
        self._comm = comm
        self.layout_raw = dict(layout_raw)
        self.analysis_info_raw = dict(analysis_info_raw)
        self.numeric_info_raw = dict(numeric_info_raw)
        self._destroyed = False

    @property
    def factor_layout(self) -> Mapping[str, Any]:
        return self.layout_raw["factor"]

    @property
    def source_layout(self) -> Mapping[str, Any]:
        return self.layout_raw["source"]

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def getSize(self) -> tuple[int, int]:
        """PETSc-Mat-compatible size needed by existing factor consumers."""

        return tuple(map(int, self.factor_layout["global_size"]))

    def getLocalSize(self) -> tuple[int, int]:
        return tuple(map(int, self.factor_layout["local_size"]))

    def getOwnershipRange(self) -> tuple[int, int]:
        return tuple(map(int, self.factor_layout["row_ownership"]))

    def getOwnershipRangeColumn(self) -> tuple[int, int]:
        return tuple(map(int, self.factor_layout["column_ownership"]))

    def getComm(self) -> Any:
        return self._comm

    def get_mumps_icntl(self, index: int) -> int:
        return int(self._raw_factor.get_mumps_icntl(index))

    @property
    def lifecycle(self) -> Mapping[str, Any]:
        return self._raw_factor.lifecycle()

    def solve(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._raw_factor.solve(rhs, solution)

    def solveTranspose(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._raw_factor.solve_transpose(rhs, solution)

    def matSolve(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._raw_factor.mat_solve(rhs, solution)

    def matSolveTranspose(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._raw_factor.mat_solve_transpose(rhs, solution)

    def release_source_keepalive(self) -> Mapping[str, Any]:
        """Drop the bridge's source reference after numeric factorization."""

        self._require_live()
        return self._raw_factor.release_source_keepalive()

    def destroy(self) -> Mapping[str, Any]:
        if self._destroyed:
            return self._raw_factor.lifecycle()
        status = self._raw_factor.destroy()
        self._destroyed = status.get("factor_released") is True
        return status

    def _require_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("staged MUMPS factor has been destroyed")


class StagedMumpsLUFactory:
    """Create one factor and run callback-gated stages on that same handle.

    The two gate callbacks are invoked once per factor, never per RHS. Each
    callback must perform any required all-rank consensus itself and return
    the same exact ``bool`` on every rank. Unknown estimates must return
    ``False``. This class performs no MPI collective and makes no claim that
    arbitrary rank-local Python or PETSc errors are synchronized.
    """

    def __init__(
        self,
        bridge: ModuleType,
        *,
        pre_symbolic_gate: GateCallback,
        pre_numeric_gate: GateCallback,
        configure_factor: ConfigureCallback | None = None,
    ) -> None:
        if not callable(getattr(bridge, "create_lu_stage", None)):
            raise TypeError("bridge must expose create_lu_stage")
        for name, callback in (
            ("pre_symbolic_gate", pre_symbolic_gate),
            ("pre_numeric_gate", pre_numeric_gate),
        ):
            if not callable(callback):
                raise TypeError(f"{name} must be callable")
        if configure_factor is not None and not callable(configure_factor):
            raise TypeError("configure_factor must be callable or None")
        self._bridge = bridge
        self._pre_symbolic_gate = pre_symbolic_gate
        self._pre_numeric_gate = pre_numeric_gate
        self._configure_factor = configure_factor

    def __call__(self, matrix: Any, *, icntl14: int) -> StagedMumpsFactor:
        if isinstance(icntl14, bool) or not isinstance(icntl14, int) or icntl14 < 0:
            raise TypeError("icntl14 must be a non-negative non-bool integer")
        raw_factor = self._bridge.create_lu_stage(matrix, icntl14=icntl14)
        try:
            if self._configure_factor is not None:
                self._configure_factor(raw_factor)

            pre_symbolic_layout = raw_factor.layout_raw()
            self._require_gate(
                self._pre_symbolic_gate,
                {
                    "stage": "before_symbolic",
                    "icntl14_requested": icntl14,
                    "layout_raw": pre_symbolic_layout,
                    "lifecycle": raw_factor.lifecycle(),
                },
                "pre-symbolic",
            )

            raw_factor.symbolic()
            analysis = raw_factor.analysis_info_raw()
            layout = raw_factor.layout_raw()
            self._require_gate(
                self._pre_numeric_gate,
                {
                    "stage": "after_symbolic_before_numeric",
                    "icntl14_requested": icntl14,
                    "layout_raw": layout,
                    "analysis_info_raw": analysis,
                    "lifecycle": raw_factor.lifecycle(),
                },
                "pre-numeric budget",
            )

            raw_factor.numeric()
            numeric = raw_factor.numeric_info_raw()
            numeric_entries = numeric.get("INFOG_api_raw_by_rank")
            if not isinstance(numeric_entries, list):
                raise TypeError(
                    "numeric INFOG snapshot is unavailable"
                )
            error_status = next(
                (
                    entry
                    for entry in numeric_entries
                    if isinstance(entry, Mapping) and entry.get("index") == 1
                ),
                None,
            )
            if (
                not isinstance(error_status, Mapping)
                or error_status.get("query_error_code") != 0
                or isinstance(error_status.get("raw_value"), bool)
                or not isinstance(error_status.get("raw_value"), int)
                or error_status["raw_value"] < 0
            ):
                raise RuntimeError(
                    "MUMPS INFOG(1) is unknown or reports a numeric factor error"
                )
            release_status = raw_factor.release_source_keepalive()
            if release_status.get("source_keepalive_released") is not True:
                raise RuntimeError("PETSc source wrapper release was not confirmed")
            return StagedMumpsFactor(
                raw_factor,
                comm=matrix.getComm(),
                layout_raw=layout,
                analysis_info_raw=analysis,
                numeric_info_raw=numeric,
            )
        except BaseException as primary:
            try:
                lifecycle = raw_factor.lifecycle()
            except BaseException as lifecycle_error:  # noqa: BLE001 - still attempt factor cleanup
                lifecycle = {}
                primary.add_note(
                    "staged factor lifecycle snapshot failed before cleanup: "
                    f"{type(lifecycle_error).__name__}: {lifecycle_error}"
                )
            if lifecycle.get("numeric_attempts", 0) > 0:
                try:
                    primary.numeric_info_raw = raw_factor.numeric_info_raw()
                except BaseException as info_error:  # noqa: BLE001 - preserve the primary failure
                    primary.add_note(
                        "numeric INFO snapshot unavailable after failure: "
                        f"{type(info_error).__name__}: {info_error}"
                    )
            try:
                cleanup = raw_factor.destroy()
                if isinstance(primary, StagedFactorRejected):
                    primary.cleanup_status = dict(cleanup)
                if (
                    cleanup.get("factor_released") is not True
                    or cleanup.get("destroy_error_code") != 0
                ):
                    primary.add_note(
                        "staged factor cleanup did not confirm release: "
                        f"{cleanup!r}"
                    )
            except BaseException as cleanup_error:  # noqa: BLE001 - preserve the primary failure
                primary.add_note(
                    "staged factor cleanup raised: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            raise

    @staticmethod
    def _require_gate(
        callback: GateCallback,
        context: Mapping[str, Any],
        name: str,
    ) -> None:
        decision = callback(context)
        if type(decision) is not bool:
            raise TypeError(f"{name} gate must return an exact bool")
        if not decision:
            raise StagedFactorRejected(f"{name} gate rejected the next LU stage")
