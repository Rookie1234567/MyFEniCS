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
ReleaseCallback = Callable[[str, Mapping[str, Any]], None]
NumericCompletionCallback = Callable[[Any], Mapping[str, Any]]
_W0P7_P4_STAGE_IDENTITIES = frozenset(
    {"task041.w0p7.p4.bottom", "task041.w0p7.p4.top"}
)
W0P7_PORD_SOURCE_MODEL_ID = "task041.w0p7.p4.pord_preanalysis_source_model.v2"
W0P7_PORD_SOURCE_MODEL_AUDIT_SHA256 = (
    "32dcc5712e7ae306a6ffa24e6dded44a6140d67d2631fce47ee258bac41b2c1a"
)
W0P7_PORD_SOURCE_MODEL_AUDIT_PATH = (
    "results/task041_w0p7_mumps_amd_descriptor_probe_20261008/"
    "pord_gbisect_scratch_correction_20261009.md"
)


def _source_matrix_inventory(matrix: Any) -> dict[str, Any]:
    """Return the assembled sparse source dimensions before factor creation."""

    try:
        info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
        local_nnz = info.get("nz_used") if isinstance(info, Mapping) else None
        if (
            isinstance(local_nnz, bool)
            or not isinstance(local_nnz, (int, float, np.integer, np.floating))
            or not np.isfinite(float(local_nnz))
            or float(local_nnz) < 0.0
            or not float(local_nnz).is_integer()
        ):
            local_nnz = None
        else:
            local_nnz = int(local_nnz)
        row_range = tuple(map(int, matrix.getOwnershipRange()))
        column_range = tuple(map(int, matrix.getOwnershipRangeColumn()))
        return {
            "global_size": list(map(int, matrix.getSize())),
            "local_size": list(map(int, matrix.getLocalSize())),
            "row_ownership": list(row_range),
            "column_ownership": list(column_range),
            "local_nnz_used": local_nnz,
            "nnz_scope": "PETSc MatGetInfo LOCAL nz_used; sum rank records once",
            "matrix_type": str(matrix.getType()),
            "status": "measured" if local_nnz is not None else "partial",
        }
    except Exception as exc:  # noqa: BLE001 - caller records and rejects unknown inventory
        return {
            "global_size": None,
            "local_size": None,
            "row_ownership": None,
            "column_ownership": None,
            "local_nnz_used": None,
            "nnz_scope": "unknown",
            "matrix_type": None,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


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

    def __init__(
        self,
        message: str,
        *,
        cleanup_status: Mapping[str, Any] | None = None,
        gate_context: Mapping[str, Any] | None = None,
    ):
        super().__init__(message)
        self.cleanup_status = None if cleanup_status is None else dict(cleanup_status)
        self.gate_context = None if gate_context is None else dict(gate_context)


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
        stage_identity: str | None,
        source_matrix_inventory: Mapping[str, Any],
        layout_raw: Mapping[str, Any],
        analysis_info_raw: Mapping[str, Any],
        numeric_info_raw: Mapping[str, Any] | None,
        numeric_completion_callback: NumericCompletionCallback | None = None,
        release_callback: ReleaseCallback | None = None,
    ) -> None:
        self._raw_factor = raw_factor
        self._comm = comm
        self.stage_identity = stage_identity
        self.source_matrix_inventory = dict(source_matrix_inventory)
        self.layout_raw = dict(layout_raw)
        self.analysis_info_raw = dict(analysis_info_raw)
        self.numeric_info_raw = (
            None if numeric_info_raw is None else dict(numeric_info_raw)
        )
        self._numeric_ready = numeric_info_raw is not None
        self._numeric_completion_callback = numeric_completion_callback
        self._release_callback = release_callback
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

    @property
    def numeric_ready(self) -> bool:
        return self._numeric_ready

    @property
    def stage_state(self) -> str:
        if self._destroyed:
            return "destroyed"
        return "numeric_ready" if self._numeric_ready else "symbolic_live_pending_numeric"

    def complete_numeric(self) -> Mapping[str, Any]:
        """Run the explicit numeric stage once on this same symbolic handle."""

        self._require_live()
        if self._numeric_ready:
            raise RuntimeError("staged numeric factorization is already complete")
        if self._numeric_completion_callback is None:
            raise RuntimeError("this pending factor cannot complete its numeric stage")
        return self._numeric_completion_callback(self)

    def solve(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._require_numeric()
        self._raw_factor.solve(rhs, solution)

    def solveTranspose(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._require_numeric()
        self._raw_factor.solve_transpose(rhs, solution)

    def matSolve(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._require_numeric()
        self._raw_factor.mat_solve(rhs, solution)

    def matSolveTranspose(self, rhs: Any, solution: Any) -> None:
        self._require_live()
        self._require_numeric()
        self._raw_factor.mat_solve_transpose(rhs, solution)

    def release_source_keepalive(self) -> Mapping[str, Any]:
        """Drop the bridge's source reference after numeric factorization."""

        self._require_live()
        self._require_numeric()
        return self._raw_factor.release_source_keepalive()

    def destroy(self) -> Mapping[str, Any]:
        if self._destroyed:
            return self._raw_factor.lifecycle()
        status = self._raw_factor.destroy()
        self._destroyed = status.get("factor_released") is True
        if self._destroyed and self._release_callback is not None:
            try:
                self._release_callback(str(self.stage_identity), status)
            except BaseException as exc:  # noqa: BLE001 - cleanup status stays authoritative
                status = {
                    **dict(status),
                    "release_record_error": f"{type(exc).__name__}: {exc}",
                }
        return status

    def _require_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("staged MUMPS factor has been destroyed")

    def _require_numeric(self) -> None:
        if not self._numeric_ready:
            raise RuntimeError(
                "staged factor is symbolic only; complete_numeric is required before solve"
            )


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
        factor_released_callback: ReleaseCallback | None = None,
        stage_event_callback: ReleaseCallback | None = None,
        deferred_numeric_stage_identities: tuple[str, ...] = (),
        sequential_amd_stage_identities: tuple[str, ...] = (),
        sequential_pord_stage_identities: tuple[str, ...] = (),
        pord_source_model_identity: str | None = None,
        pord_source_model_audit_sha256: str | None = None,
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
        if factor_released_callback is not None and not callable(
            factor_released_callback
        ):
            raise TypeError("factor_released_callback must be callable or None")
        if stage_event_callback is not None and not callable(stage_event_callback):
            raise TypeError("stage_event_callback must be callable or None")
        allowed_deferred = {
            "task041.w0p7.p4.bottom",
            "task041.w0p7.p4.top",
        }
        if not isinstance(deferred_numeric_stage_identities, tuple) or any(
            not isinstance(identity, str) or identity not in allowed_deferred
            for identity in deferred_numeric_stage_identities
        ) or len(set(deferred_numeric_stage_identities)) != len(
            deferred_numeric_stage_identities
        ):
            raise ValueError(
                "deferred numeric stages are limited to the registered W0.7 P4 sides"
            )
        if not isinstance(sequential_amd_stage_identities, tuple) or any(
            not isinstance(identity, str)
            or identity not in _W0P7_P4_STAGE_IDENTITIES
            or identity not in deferred_numeric_stage_identities
            for identity in sequential_amd_stage_identities
        ) or len(set(sequential_amd_stage_identities)) != len(
            sequential_amd_stage_identities
        ):
            raise ValueError(
                "sequential AMD controls are limited to deferred registered W0.7 P4 sides"
            )
        if not isinstance(sequential_pord_stage_identities, tuple) or any(
            not isinstance(identity, str)
            or identity not in _W0P7_P4_STAGE_IDENTITIES
            or identity not in deferred_numeric_stage_identities
            for identity in sequential_pord_stage_identities
        ) or len(set(sequential_pord_stage_identities)) != len(
            sequential_pord_stage_identities
        ):
            raise ValueError(
                "sequential PORD controls are limited to deferred registered W0.7 P4 sides"
            )
        if set(sequential_amd_stage_identities) & set(sequential_pord_stage_identities):
            raise ValueError("a deferred W0.7 P4 side cannot select AMD and PORD together")
        if sequential_pord_stage_identities:
            if (
                pord_source_model_identity != W0P7_PORD_SOURCE_MODEL_ID
                or pord_source_model_audit_sha256
                != W0P7_PORD_SOURCE_MODEL_AUDIT_SHA256
            ):
                raise ValueError(
                    "PORD stages require the exact registered W0.7 source-model identity and audit SHA"
                )
        elif (
            pord_source_model_identity is not None
            or pord_source_model_audit_sha256 is not None
        ):
            raise ValueError("PORD source-model binding was supplied without PORD stages")
        self._bridge = bridge
        self._pre_symbolic_gate = pre_symbolic_gate
        self._pre_numeric_gate = pre_numeric_gate
        self._configure_factor = configure_factor
        self._factor_released_callback = factor_released_callback
        self._stage_event_callback = stage_event_callback
        self._deferred_numeric_stage_identities = frozenset(
            deferred_numeric_stage_identities
        )
        self._sequential_amd_stage_identities = frozenset(
            sequential_amd_stage_identities
        )
        self._sequential_pord_stage_identities = frozenset(
            sequential_pord_stage_identities
        )
        self._pord_source_model_binding = (
            {
                "identity": W0P7_PORD_SOURCE_MODEL_ID,
                "audit_path": W0P7_PORD_SOURCE_MODEL_AUDIT_PATH,
                "audit_sha256": W0P7_PORD_SOURCE_MODEL_AUDIT_SHA256,
            }
            if sequential_pord_stage_identities
            else None
        )
        self._live_factors: dict[str, StagedMumpsFactor] = {}
        self._released_factors: list[dict[str, Any]] = []

    def _record_factor_release(
        self, stage_identity: str, status: Mapping[str, Any]
    ) -> None:
        self._released_factors.append(
            {"stage_identity": stage_identity, "destroy_status": dict(status)}
        )
        if (
            status.get("factor_released") is True
            and status.get("destroy_error_code") == 0
        ):
            self._live_factors.pop(stage_identity, None)
        if self._factor_released_callback is not None:
            self._factor_released_callback(stage_identity, status)

    @property
    def factor_release_history(self) -> list[dict[str, Any]]:
        """Return local completed destroy records for later all-rank gates."""

        return [dict(event) for event in self._released_factors]

    @property
    def live_factor_inventory(self) -> list[dict[str, Any]]:
        """Return live handles and raw MUMPS fields without converting them to RSS."""

        return [
            {
                "stage_identity": identity,
                "status": "live",
                "factor_state": factor.stage_state,
                "numeric_ready": factor.numeric_ready,
                "source_matrix_inventory": dict(factor.source_matrix_inventory),
                "factor_layout_raw": dict(factor.layout_raw),
                "analysis_info_raw": dict(factor.analysis_info_raw),
                "numeric_info_raw": (
                    None
                    if factor.numeric_info_raw is None
                    else dict(factor.numeric_info_raw)
                ),
                "memory_field_semantics": (
                    "MUMPS INFOG(18)/(19) raw post-numeric allocation fields; "
                    "not process RSS or a future-allocation upper bound"
                ),
            }
            for identity, factor in self._live_factors.items()
            if not factor.destroyed
        ]

    def __call__(
        self,
        matrix: Any,
        *,
        icntl14: int,
        stage_identity: str | None = None,
        defer_numeric: bool = False,
    ) -> StagedMumpsFactor:
        if type(defer_numeric) is not bool:
            raise TypeError("defer_numeric must be an exact bool")
        if isinstance(icntl14, bool) or not isinstance(icntl14, int) or icntl14 < 0:
            raise TypeError("icntl14 must be a non-negative non-bool integer")
        if stage_identity is not None and (
            not isinstance(stage_identity, str) or not stage_identity.strip()
        ):
            raise TypeError("stage_identity must be a non-empty string or None")
        if defer_numeric and stage_identity not in self._deferred_numeric_stage_identities:
            raise ValueError(
                "pending numeric is enabled only for explicitly registered W0.7 P4 sides"
            )
        if (
            stage_identity in self._sequential_amd_stage_identities
            and not defer_numeric
        ):
            raise ValueError(
                "sequential AMD controls are reserved for deferred W0.7 P4 handles"
            )
        if (
            stage_identity in self._sequential_pord_stage_identities
            and not defer_numeric
        ):
            raise ValueError(
                "sequential PORD controls are reserved for deferred W0.7 P4 handles"
            )
        if stage_identity is not None and stage_identity in self._live_factors:
            raise RuntimeError(
                f"staged factor identity is already live: {stage_identity}"
            )
        source_inventory = _source_matrix_inventory(matrix)
        raw_factor = self._bridge.create_lu_stage(matrix, icntl14=icntl14)
        factor: StagedMumpsFactor | None = None
        try:
            if self._configure_factor is not None:
                self._configure_factor(raw_factor)

            public_control_readback = None
            ordering_profile = None
            ordering_icntl7 = None
            if stage_identity in self._sequential_amd_stage_identities:
                ordering_profile = "sequential_amd_deferred_p4"
                ordering_icntl7 = 0
            elif stage_identity in self._sequential_pord_stage_identities:
                ordering_profile = "sequential_pord_deferred_p4"
                ordering_icntl7 = 4
            if ordering_profile is not None:
                set_call_values = {28: 1, 7: ordering_icntl7}
                requested_controls = dict(set_call_values)
                control_errors: list[dict[str, Any]] = []
                for index, value in set_call_values.items():
                    try:
                        raw_factor.set_mumps_icntl(index, value)
                    except Exception as exc:  # noqa: BLE001 - reject at collective gate
                        control_errors.append(
                            {
                                "index": index,
                                "operation": "MatMumpsSetIcntl",
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                cached_readback: dict[str, dict[str, Any]] = {}
                requested_controls = {14: icntl14, **requested_controls}
                for index in (7, 14, 28):
                    try:
                        cached_value = int(raw_factor.get_mumps_icntl(index))
                        query_error = None
                    except Exception as exc:  # noqa: BLE001 - reject at collective gate
                        cached_value = None
                        query_error = f"{type(exc).__name__}: {exc}"
                        control_errors.append(
                            {
                                "index": index,
                                "operation": "MatMumpsGetIcntl",
                                "error": query_error,
                            }
                        )
                    cached_readback[f"ICNTL{index}"] = {
                        "value": cached_value,
                        "query_error": query_error,
                    }

                try:
                    factor_profile = dict(raw_factor.mumps_options_raw())
                    factor_profile.update(
                        {
                            "runtime_petsc_version": list(
                                map(int, PETSc.Sys.getVersion()[:3])
                            ),
                            "runtime_petsc_scalar_dtype": str(
                                np.dtype(PETSc.ScalarType)
                            ),
                            "runtime_petsc_int_dtype": str(np.dtype(PETSc.IntType)),
                            "runtime_petsc_int_sizeof": np.dtype(PETSc.IntType).itemsize,
                            "bridge_compile_petsc_version": [
                                int(self._bridge.petsc_version_major),
                                int(self._bridge.petsc_version_minor),
                                int(self._bridge.petsc_version_subminor),
                            ],
                            "bridge_compile_petsc_int_sizeof": getattr(
                                self._bridge, "petsc_int_sizeof", None
                            ),
                            "bridge_compile_mumps_version": [
                                int(self._bridge.mumps_package_version_major),
                                int(self._bridge.mumps_package_version_minor),
                                int(self._bridge.mumps_package_version_subminor),
                            ],
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - reject at rank consensus
                    factor_profile = {
                        "schema": "task041.w0p7.factor_mumps_options.v1",
                        "status": "query_error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    control_errors.append(
                        {
                            "operation": "public_factor_options_profile",
                            "error": factor_profile["error"],
                        }
                    )
                effective_inputs = {
                    "ICNTL5": 0,
                    "ICNTL6": 7,
                    "ICNTL7": ordering_icntl7,
                    "ICNTL8": 77,
                    "ICNTL14": icntl14,
                    "ICNTL18": 3,
                    "ICNTL19": 0,
                    "ICNTL28": 1,
                    "ICNTL35": 0,
                }
                if ordering_profile == "sequential_amd_deferred_p4":
                    effective_input_basis = (
                        "PETSc 3.19.6 first MUMPS JOB_INIT: MPI>1 supplies "
                        "ICNTL18=3 and its MUMPS constructor initializes "
                        "ICNTL19=0; MUMPS 5.6.2 zini_defaults supplies the "
                        "other listed defaults; ICNTL7/28 and ICNTL14 are "
                        "explicit PETSc API requests"
                    )
                else:
                    effective_input_basis = (
                        "PETSc 3.19.6 assembled distributed MPI>1 route and "
                        "MUMPS 5.6.2 zini_defaults are source-derived; ICNTL7=4, "
                        "ICNTL28=1 and ICNTL14=40 are explicit API requests. "
                        "PORD internal compile options are separately bound to "
                        "the source audit and are not proven by these controls"
                    )
                public_control_readback = {
                    "schema": "task041.w0p7.public_mumps_controls.v2",
                    "profile": ordering_profile,
                    "status": "explicit_requests_and_JOB_NULL_cache_readback",
                    "set_calls": {
                        f"ICNTL{index}": value
                        for index, value in set_call_values.items()
                    },
                    "requested_controls": {
                        f"ICNTL{index}": value
                        for index, value in sorted(requested_controls.items())
                    },
                    "cached_readback": cached_readback,
                    "requested_via_factor_constructor": {
                        "ICNTL14": icntl14,
                        "source": "create_lu_stage(icntl14) public MatMumpsSetIcntl",
                    },
                    "source_derived_effective_inputs": {
                        "status": "source_derived_not_measured",
                        "controls": effective_inputs,
                        "basis": effective_input_basis,
                    },
                    "factor_profile": factor_profile,
                    "errors": control_errors,
                }
                if ordering_profile == "sequential_pord_deferred_p4":
                    public_control_readback["source_model_binding"] = dict(
                        self._pord_source_model_binding or {}
                    )

            pre_symbolic_layout = raw_factor.layout_raw()
            self._require_gate(
                self._pre_symbolic_gate,
                {
                    "stage": "before_symbolic",
                    "stage_identity": stage_identity,
                    "icntl14_requested": icntl14,
                    "source_matrix_inventory": source_inventory,
                    "live_factor_inventory": self.live_factor_inventory,
                    "factor_release_history": self.factor_release_history,
                    "layout_raw": pre_symbolic_layout,
                    "public_mumps_control_readback": public_control_readback,
                    "lifecycle": raw_factor.lifecycle(),
                },
                "pre-symbolic",
            )

            raw_factor.symbolic()
            analysis = raw_factor.analysis_info_raw()
            if public_control_readback is not None:
                post_controls: dict[str, dict[str, Any]] = {}
                post_errors: list[dict[str, Any]] = []
                for index in (5, 6, 7, 8, 14, 18, 19, 28, 35):
                    try:
                        actual = int(raw_factor.get_mumps_icntl(index))
                        query_error = None
                    except Exception as exc:  # noqa: BLE001 - post-init actual readback
                        actual = None
                        query_error = f"{type(exc).__name__}: {exc}"
                        post_errors.append(
                            {
                                "index": index,
                                "operation": "MatMumpsGetIcntl_after_symbolic",
                                "error": query_error,
                            }
                        )
                    post_controls[f"ICNTL{index}"] = {
                        "actual": actual,
                        "query_error": query_error,
                    }
                analysis["public_mumps_control_readback"] = (
                    public_control_readback
                )
                analysis["post_symbolic_mumps_control_readback"] = {
                    "schema": "task041.w0p7.post_symbolic_mumps_controls.v1",
                    "status": "measured_after_symbolic_initialization",
                    "controls": post_controls,
                    "errors": post_errors,
                }
            layout = raw_factor.layout_raw()
            factor = StagedMumpsFactor(
                raw_factor,
                comm=matrix.getComm(),
                stage_identity=stage_identity,
                source_matrix_inventory=source_inventory,
                layout_raw=layout,
                analysis_info_raw=analysis,
                numeric_info_raw=None,
                numeric_completion_callback=self._complete_numeric_factor,
                release_callback=self._record_factor_release,
            )
            if stage_identity is not None:
                self._live_factors[stage_identity] = factor
            if defer_numeric:
                if self._stage_event_callback is not None:
                    self._stage_event_callback(
                        "symbolic_factor_pending_numeric",
                        {
                            "stage_identity": stage_identity,
                            "icntl14_requested": icntl14,
                            "source_matrix_inventory": source_inventory,
                            "factor_layout_raw": layout,
                            "analysis_info_raw": analysis,
                            "public_mumps_control_readback": (
                                public_control_readback
                            ),
                            "numeric_info_raw": None,
                            "lifecycle": raw_factor.lifecycle(),
                        },
                    )
                return factor
            factor.complete_numeric()
            return factor
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
                    numeric_info = raw_factor.numeric_info_raw()
                    primary.numeric_info_raw = numeric_info
                    if factor is not None:
                        factor.numeric_info_raw = dict(numeric_info)
                except BaseException as info_error:  # noqa: BLE001 - preserve the primary failure
                    primary.add_note(
                        "numeric INFO snapshot unavailable after failure: "
                        f"{type(info_error).__name__}: {info_error}"
                    )
            try:
                cleanup = (
                    factor.destroy() if factor is not None else raw_factor.destroy()
                )
                if isinstance(primary, StagedFactorRejected):
                    primary.cleanup_status = dict(cleanup)
                    context = primary.gate_context or {}
                    primary.failure_evidence = {
                        "stage": context.get("stage"),
                        "stage_identity": context.get("stage_identity"),
                        "icntl14_requested": context.get("icntl14_requested"),
                        "source_matrix_inventory": context.get(
                            "source_matrix_inventory"
                        ),
                        "factor_lifecycle_before_destroy": context.get(
                            "lifecycle"
                        ),
                        "cleanup_status": dict(cleanup),
                    }
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

    def _complete_numeric_factor(
        self, factor: StagedMumpsFactor
    ) -> Mapping[str, Any]:
        factor._require_live()
        if factor.numeric_ready:
            raise RuntimeError("staged numeric factorization is already complete")
        raw_factor = factor._raw_factor
        context = {
            "stage": "after_symbolic_before_numeric",
            "stage_identity": factor.stage_identity,
            "icntl14_requested": factor.get_mumps_icntl(14),
            "source_matrix_inventory": factor.source_matrix_inventory,
            "live_factor_inventory": self.live_factor_inventory,
            "factor_release_history": self.factor_release_history,
            "layout_raw": factor.layout_raw,
            "analysis_info_raw": factor.analysis_info_raw,
            "lifecycle": raw_factor.lifecycle(),
        }
        try:
            self._require_gate(
                self._pre_numeric_gate,
                context,
                "pre-numeric budget",
            )
            raw_factor.numeric()
            numeric = raw_factor.numeric_info_raw()
            factor.numeric_info_raw = dict(numeric)
            numeric_entries = numeric.get("INFOG_api_raw_by_rank")
            if not isinstance(numeric_entries, list):
                raise TypeError("numeric INFOG snapshot is unavailable")
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
            factor._numeric_ready = True
            if self._stage_event_callback is not None:
                self._stage_event_callback(
                    "numeric_factor_ready",
                    {
                        "stage_identity": factor.stage_identity,
                        "icntl14_requested": context["icntl14_requested"],
                        "source_matrix_inventory": factor.source_matrix_inventory,
                        "factor_layout_raw": dict(factor.layout_raw),
                        "analysis_info_raw": dict(factor.analysis_info_raw),
                        "numeric_info_raw": dict(factor.numeric_info_raw),
                        "source_keepalive_release": dict(release_status),
                        "lifecycle": raw_factor.lifecycle(),
                    },
                )
            return dict(factor.numeric_info_raw)
        except BaseException as primary:
            try:
                lifecycle = raw_factor.lifecycle()
            except BaseException as lifecycle_error:  # noqa: BLE001 - preserve the primary failure
                lifecycle = {}
                primary.add_note(
                    "staged factor lifecycle snapshot failed before cleanup: "
                    f"{type(lifecycle_error).__name__}: {lifecycle_error}"
                )
            if lifecycle.get("numeric_attempts", 0) > 0:
                try:
                    factor.numeric_info_raw = dict(raw_factor.numeric_info_raw())
                except BaseException as info_error:  # noqa: BLE001 - preserve the primary failure
                    primary.add_note(
                        "numeric INFO snapshot unavailable after failure: "
                        f"{type(info_error).__name__}: {info_error}"
                    )
            try:
                cleanup = factor.destroy()
                if isinstance(primary, StagedFactorRejected):
                    primary.cleanup_status = dict(cleanup)
                    primary.failure_evidence = {
                        "stage": context.get("stage"),
                        "stage_identity": context.get("stage_identity"),
                        "icntl14_requested": context.get("icntl14_requested"),
                        "source_matrix_inventory": context.get(
                            "source_matrix_inventory"
                        ),
                        "factor_lifecycle_before_destroy": context.get(
                            "lifecycle"
                        ),
                        "cleanup_status": dict(cleanup),
                    }
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
            raise StagedFactorRejected(
                f"{name} gate rejected the next LU stage",
                gate_context=context,
            )
