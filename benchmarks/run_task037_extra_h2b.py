"""Task037 H2B Phase 2: isolated B0 action staging and online smoother probe.

The controller is intentionally standard-library only.  DOLFINx, PETSc, the
R2 loader, and the H2A helpers are imported only by the two worker entry
points (or by the read-only checker).  This keeps the watchdog's own process
tree out of the online memory measurement and keeps H2B explicitly opt-in.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
H2B_SCHEMA = "task037.extra.h2b.phase2"
H2B_WORKER_SCHEMA = f"{H2B_SCHEMA}.worker.v1"
H2B_WATCHDOG_SCHEMA = f"{H2B_SCHEMA}.watchdog.v1"
H2B_CHECK_SCHEMA = f"{H2B_SCHEMA}.check.v1"
H2B_PROGRESS_SCHEMA = f"{H2B_SCHEMA}.progress.v1"
H2B_S0_SCHEMA = f"{H2B_SCHEMA}.s0"
H2B_S0_WORKER_SCHEMA = f"{H2B_S0_SCHEMA}.worker.v1"
H2B_S0_WATCHDOG_SCHEMA = f"{H2B_S0_SCHEMA}.watchdog.v1"
H2B_S0_CHECK_SCHEMA = f"{H2B_S0_SCHEMA}.check.v1"
H2B_STAGE_TIMEOUT_SECONDS = 3600.0
H2B_ONLINE_TIMEOUT_SECONDS = 1800.0
H2B_STAGE_RSS_LIMIT_BYTES = 1_800_000_000
H2B_ONLINE_RSS_LIMIT_BYTES = 1_450_000_000
H2B_SWAP_LIMIT_BYTES = 0
H2B_S0_RSS_LIMIT_BYTES = 1_000_000_000
H2B_S0_TIMEOUT_SECONDS = 3_600.0
H2B_PROCESS_DRAIN_TIMEOUT_SECONDS = 5.0
H2B_PROCESS_DRAIN_POLL_SECONDS = 0.05
H2B_S0_STRATEGIES = ("additive", "forward", "symmetric")
H2B_S0_OPERATIONAL_ACTION_COUNTS = {"additive": 1, "forward": 8, "symmetric": 16}
H2B_S0_RHO_LIMITS = {
    "gradient-dominated": 0.95,
    "curl-dominated": 0.95,
    "mixed": 0.85,
    "checkerboard/high-frequency": 0.70,
    "physical-RHS-like": 0.95,
}
H2B_FACTOR_WORK_LIMIT_BYTES = 500_000_000
H2B_R2_RECORD_PATH = (
    ROOT
    / "benchmarks/cases/101_task37_extra_development/records"
    / "h2a_staged_factor_cache.json"
)
H2B_R2_RECORD_SHA256 = (
    "2af81d454b89d63e1a5d03916286b527112dd76da34259712e73557918516c9c"
)
H2B_R2_RECORD_EVIDENCE_SHA256 = (
    "c288b8c4d5b0e2587b26c7404fb73685095bacff82ca70fcea6373356442c405"
)
H2B_R2_MANIFEST = (
    ROOT
    / "benchmarks/artifacts/task037_extra_development"
    / "h2a_r2_da8ddbb_run1/factor_store/manifest.json"
)
H2B_R2_MANIFEST_SHA256 = (
    "1bac2dab37ac19dfa6ab81834327b96e251b1178e0ff652a03347bdd0fa48f98"
)
H2B_R2_PRODUCER_SOURCE_SHA = (
    "da8ddbb257b0d9d510e9d711d23144f50dabd0e4"
)
H2B_FIXED_ROWS = 173_802
H2B_FIXED_CONSTRAINTS = 9_210
H2B_FIXED_CELLS = 252
H2B_FIXED_NLOC = 882
H2B_FIXED_CLASSES = 24
H2B_FIXED_FACTORS = 16
H2B_PRIMARY_BUDGET = 3
H2B_FORM_JIT_ARGS = ("-O0", "-g0")
H2B_SOURCE_LABELS = (
    "gradient-dominated",
    "curl-dominated",
    "mixed",
    "checkerboard/high-frequency",
    "physical-RHS-like",
)
H2B_RHO_LIMITS = {
    "gradient-dominated": 1.0,
    "curl-dominated": 1.0,
    "mixed": 0.85,
    "checkerboard/high-frequency": 0.70,
    "physical-RHS-like": 1.0,
}
H2B_SOURCE_DEFINITIONS = {
    "gradient-dominated": (
        "phase-matched analytic gradient primal with fixed dimensionless zeta "
        "envelope; "
        "B0 action supplies the residual"
    ),
    "curl-dominated": (
        "phase-matched transverse oscillatory primal with fixed nonzero z "
        "frequency; B0 action supplies the residual"
    ),
    "mixed": (
        "normalize(gradient_residual) + (0.37+0.11j)*"
        "normalize(curl_residual), then normalize the sum; coefficient is "
        "fixed before measurement"
    ),
    "checkerboard/high-frequency": (
        "fixed global-DoF parity alternating vector with Floquet identity "
        "rows explicitly zeroed for the B0 source"
    ),
    "physical-RHS-like": (
        "cfg.incident_amplitude*cfg.polarization_vector*"
        "exp(1j*dot(cfg.wavevector,x)); "
        "B0 action supplies the residual"
    ),
}
H2B_STAGE_EVENTS = (
    "mesh_build_started",
    "mesh_build_ready",
    "function_space_started",
    "function_space_ready",
    "b0_form_started",
    "compiler_probe_ready",
    "b0_compile_started",
    "b0_compile_ready",
    "summary_started",
    "summary_ready",
)
H2B_ONLINE_EVENTS = (
    "authority_validate_started",
    "authority_validate_ready",
    "mesh_build_started",
    "mesh_build_ready",
    "function_space_started",
    "function_space_ready",
    "floquet_mpc_started",
    "floquet_mpc_ready",
    "b0_cache_load_started",
    "b0_cache_load_ready",
    "factor_load_started",
    "factor_load_ready",
    "source_setup_ready",
    "smoother_ready",
    "summary_started",
    "summary_ready",
)
_S0_SMOOTHER_EVENT = H2B_ONLINE_EVENTS.index("smoother_ready")
H2B_S0_EVENTS = (
    H2B_ONLINE_EVENTS[:_S0_SMOOTHER_EVENT]
    + ("s0_measurement_started", "s0_measurement_ready")
    + H2B_ONLINE_EVENTS[_S0_SMOOTHER_EVENT + 1 :]
)
H2B_S0_ARTIFACT_NAMES = (
    "stage_progress.jsonl",
    "stage_stdout.txt",
    "stage_summary.json",
    "stage_timeline.jsonl",
    "s0_progress.jsonl",
    "s0_stdout.txt",
    "s0_summary.json",
    "s0_timeline.jsonl",
    "stage_root_pid.json",
    "s0_root_pid.json",
)
_HEX = set("0123456789abcdef")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _attach_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("evidence_sha256", None)
    result["evidence_sha256"] = hashlib.sha256(_canonical_json(result)).hexdigest()
    return result


def _evidence_valid(value: Mapping[str, Any]) -> bool:
    observed = value.get("evidence_sha256")
    if not isinstance(observed, str) or len(observed) != 64:
        return False
    if observed.lower() != observed or any(char not in _HEX for char in observed):
        return False
    return observed == _attach_evidence(value)["evidence_sha256"]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _artifact(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {"path": relative, "present": False}
    return {
        "path": relative,
        "present": True,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
    }


def _fixed_scope() -> dict[str, Any]:
    return {
        "mode": "h2b_phase2_primary",
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "global_cells": H2B_FIXED_CELLS,
        "local_nloc": H2B_FIXED_NLOC,
        "global_rows": H2B_FIXED_ROWS,
        "constraint_count": H2B_FIXED_CONSTRAINTS,
        "stage_timeout_seconds": H2B_STAGE_TIMEOUT_SECONDS,
        "online_timeout_seconds": H2B_ONLINE_TIMEOUT_SECONDS,
        "stage_rss_limit_bytes": H2B_STAGE_RSS_LIMIT_BYTES,
        "online_rss_limit_bytes": H2B_ONLINE_RSS_LIMIT_BYTES,
        "swap_limit_bytes": H2B_SWAP_LIMIT_BYTES,
        "factor_work_limit_bytes": H2B_FACTOR_WORK_LIMIT_BYTES,
        "operator": "(1/mu_r)*K_curl+k0^2*M_abs_epsilon",
        "timing_protocol": "one warm action, five volume actions median; two applies/source median",
        "formal_budget_runs": H2B_PRIMARY_BUDGET,
        "fallback": "not_implemented",
    }


def _s0_scope() -> dict[str, Any]:
    return {
        "mode": "h2b_s0_scale_invariant_direction",
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "global_cells": H2B_FIXED_CELLS,
        "local_nloc": H2B_FIXED_NLOC,
        "global_rows": H2B_FIXED_ROWS,
        "constraint_count": H2B_FIXED_CONSTRAINTS,
        "strategies": list(H2B_S0_STRATEGIES),
        "operator": "K_curl+k0^2*M_abs_epsilon; code uses (1/mu_r) with mu_r=1",
        "online_timeout_seconds": H2B_S0_TIMEOUT_SECONDS,
        "online_rss_limit_bytes": H2B_S0_RSS_LIMIT_BYTES,
        "swap_limit_bytes": H2B_SWAP_LIMIT_BYTES,
    }


def _fixed_identity() -> dict[str, Any]:
    return {
        "fine_space": "uncondensed_fullspace",
        "fullspace_global_rows_h10": H2B_FIXED_ROWS,
        "condensation": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "slab_factor_count": 0,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "B2_B4_local_krylov_used": False,
        "fullspace_patch_pc_used": True,
        "interior_recovery_required": False,
        "ksp_created": False,
        "dtn_used": False,
        "pde_solve_called": False,
        "ordinary_default_changed": False,
    }


def _phase_identity(*, jit_api: bool, compile_called: bool, compiler_probe: bool) -> dict[str, Any]:
    return {
        "jit_api_called": bool(jit_api),
        "compile_called": bool(compile_called),
        "compiler_probe_called": bool(compiler_probe),
        "tensor_tabulation_called": False,
        "factorization_called": False,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "ordinary_default_changed": False,
    }


def _source_definition_sha(label: str) -> str:
    return hashlib.sha256(H2B_SOURCE_DEFINITIONS[label].encode("utf-8")).hexdigest()


def _source_records_from_arrays(arrays: Mapping[str, Any], slave_rows: Any) -> list[dict[str, Any]]:
    """Return fixed source metadata; NumPy is imported only inside workers."""

    import numpy as np

    rows = np.asarray(slave_rows, dtype=np.int64)
    records: list[dict[str, Any]] = []
    for label in H2B_SOURCE_LABELS:
        value = np.ascontiguousarray(np.asarray(arrays[label], dtype=np.complex128))
        sanitized = np.array(value, copy=True)
        sanitized[rows] = 0.0
        vector_sha = hashlib.sha256(memoryview(sanitized).cast("B")).hexdigest()
        norm = float(np.linalg.norm(sanitized))
        records.append(
            {
                "label": label,
                "definition": H2B_SOURCE_DEFINITIONS[label],
                "definition_sha256": _source_definition_sha(label),
                "vector_sha256": vector_sha,
                "full_space_norm": norm,
                "slave_semantics": "slave identity rows are explicitly zero in B0 source; smoother copies rhs identity correction",
                "rho_norm_scope": "all_fullspace_rows",
                "external_slave_mask": False,
            }
        )
        del sanitized
    return records


def _source_arrays(
    function_space: Any,
    cfg: Any,
    slave_rows: Any,
    mpc: Any | None = None,
) -> dict[str, Any]:
    """Build the five fixed deterministic source vectors for the online worker."""

    import numpy as np
    from dolfinx import fem
    from dolfinx.la.petsc import create_vector
    from petsc4py import PETSc

    owned = int(function_space.dofmap.index_map.size_local)
    field = fem.Function(function_space)
    kx, ky = complex(cfg.kx), complex(cfg.ky)
    z_span = float(cfg.domain_z_max - cfg.domain_z_min)
    if not math.isfinite(z_span) or z_span <= 0.0:
        raise ValueError("H2B z domain span must be positive")

    def phase(x: Any) -> Any:
        return np.exp(1j * (kx * x[0] + ky * x[1]))

    def gradient(x: Any) -> Any:
        zeta = (x[2] - float(cfg.domain_z_min)) / z_span
        phi = phase(x) * (1.0 + 0.17 * zeta)
        return np.vstack(
            (
                1j * kx * phi,
                1j * ky * phi,
                (0.17 / z_span) * phase(x),
            )
        ).astype(np.complex128)
    omega = 2.0 * np.pi / z_span
    curl = lambda x: np.vstack(
        (
            phase(x) * np.sin(omega * (x[2] - cfg.domain_z_min)),
            phase(x) * np.cos(omega * (x[2] - cfg.domain_z_min)),
            0.25 * phase(x) * np.sin(omega * (x[2] - cfg.domain_z_min)),
        )
    ).astype(np.complex128)
    wavevector = np.asarray(cfg.wavevector, dtype=np.complex128)
    polarization = np.asarray(cfg.polarization_vector, dtype=np.complex128)
    amplitude = complex(cfg.incident_amplitude)

    def physical(x: Any) -> Any:
        full_phase = np.exp(1j * np.dot(wavevector, x))
        return (amplitude * full_phase * polarization[:, None]).astype(np.complex128)

    def owned_values(interpolant: Any) -> Any:
        field.interpolate(interpolant)
        field.x.scatter_forward()
        values = np.array(field.x.array[:owned], dtype=np.complex128, copy=True)
        if mpc is None:
            return values
        vector = create_vector(
            [(function_space.dofmap.index_map, function_space.dofmap.index_map_bs)]
        )
        try:
            with vector.localForm() as local:
                local.set(0.0)
                local.array_w[:owned] = values
            vector.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            mpc.backsubstitution(vector)
            vector.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            return np.array(vector.getArray(readonly=True), dtype=np.complex128, copy=True)
        finally:
            vector.destroy()

    gradient_values = owned_values(gradient)
    curl_values = owned_values(curl)
    physical_values = owned_values(physical)
    index = np.arange(owned, dtype=np.int64)
    checker = np.where(index % 2 == 0, 1.0 + 0.0j, -1.0 + 0.0j)
    gradient_values = np.ascontiguousarray(gradient_values)
    curl_values = np.ascontiguousarray(curl_values)
    physical_values = np.ascontiguousarray(physical_values)
    return {
        "gradient-dominated": gradient_values,
        "curl-dominated": curl_values,
        "mixed": np.zeros_like(gradient_values),
        "checkerboard/high-frequency": np.ascontiguousarray(checker),
        "physical-RHS-like": physical_values,
    }


def _residual_source_arrays(
    primal_arrays: Mapping[str, Any],
    exact_action: Any,
    slave_rows: Any,
) -> dict[str, Any]:
    """Map frozen primal probes through B0 before forming residual sources."""

    import numpy as np

    rows = np.asarray(slave_rows, dtype=np.int64)

    def mapped(label: str) -> np.ndarray:
        source = np.array(primal_arrays[label], dtype=np.complex128, copy=True)
        source[rows] = 0.0
        target = np.empty_like(source)
        exact_action(source, target)
        if not np.all(np.isfinite(target)):
            raise ValueError(f"H2B {label} residual is nonfinite")
        target[rows] = 0.0
        return np.ascontiguousarray(target)

    gradient = mapped("gradient-dominated")
    curl = mapped("curl-dominated")
    physical = mapped("physical-RHS-like")

    def normalized(value: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(value))
        if not math.isfinite(norm) or norm <= 0.0:
            raise ValueError("H2B source residual has no finite norm")
        return value / norm

    mixed = normalized(gradient) + (0.37 + 0.11j) * normalized(curl)
    mixed = np.ascontiguousarray(normalized(mixed))
    checker = np.array(
        primal_arrays["checkerboard/high-frequency"], dtype=np.complex128, copy=True
    )
    checker[rows] = 0.0
    return {
        "gradient-dominated": gradient,
        "curl-dominated": curl,
        "mixed": mixed,
        "checkerboard/high-frequency": np.ascontiguousarray(checker),
        "physical-RHS-like": physical,
    }


def _s0_array_sha(value: Any) -> str:
    import numpy as np

    array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _s0_oracle_metrics(
    rhs: Any,
    correction: Any,
    operational_residual: Any,
    diagnostic_action: Any,
    *,
    repeat_correction: Any,
    repeat_residual: Any,
    repeat_diagnostic_action: Any,
    operational_action_count: int,
    diagnostic_action_count: int,
) -> dict[str, Any]:
    """Compute the scale-invariant S0 direction oracle from full vectors."""

    import numpy as np

    values = tuple(
        np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
        for value in (
            rhs,
            correction,
            operational_residual,
            diagnostic_action,
            repeat_correction,
            repeat_residual,
            repeat_diagnostic_action,
        )
    )
    r, z, r_final, q, z_repeat, r_repeat, q_repeat = values
    if any(value.ndim != 1 or not np.all(np.isfinite(value)) for value in values):
        raise ValueError("H2B-S0 oracle vectors must be finite one-dimensional arrays")
    if not (r.shape == z.shape == r_final.shape == q.shape == z_repeat.shape == r_repeat.shape == q_repeat.shape):
        raise ValueError("H2B-S0 oracle vector shapes must match")
    r_norm = float(np.linalg.norm(r))
    q_norm = float(np.linalg.norm(q))
    if not math.isfinite(r_norm) or r_norm <= 0.0:
        raise ValueError("H2B-S0 RHS norm must be positive and finite")
    if not math.isfinite(q_norm) or q_norm <= 0.0:
        raise ValueError("H2B-S0 diagnostic action norm must be positive and finite")
    qh_r = np.vdot(q, r)
    omega = complex(qh_r / (q_norm * q_norm))
    unit_residual = r - q
    scaled_residual = r - omega * q
    q_over_r = q_norm / r_norm
    z_norm = float(np.linalg.norm(z))
    z_over_r = z_norm / r_norm
    return {
        "r_norm": r_norm,
        "z_norm": z_norm,
        "q_norm": q_norm,
        "unit_residual_norm": float(np.linalg.norm(unit_residual)),
        "scaled_residual_norm": float(np.linalg.norm(scaled_residual)),
        "q_h_r_real": float(qh_r.real),
        "q_h_r_imag": float(qh_r.imag),
        "omega_real": float(omega.real),
        "omega_imag": float(omega.imag),
        "omega_abs": float(abs(omega)),
        "rho_unit": float(np.linalg.norm(unit_residual) / r_norm),
        "rho_star": float(np.linalg.norm(scaled_residual) / r_norm),
        "eta": float(abs(qh_r) / (q_norm * r_norm)),
        "q_over_r_amplification": float(q_over_r),
        "z_over_r_amplification": float(z_over_r),
        "action_closure_relative_error": float(
            np.linalg.norm((r - r_final) - q) / max(q_norm, np.finfo(float).tiny)
        ),
        "repeat_action_closure_relative_error": float(
            np.linalg.norm((r - r_repeat) - q_repeat)
            / max(float(np.linalg.norm(q_repeat)), np.finfo(float).tiny)
        ),
        "correction_sha256": _s0_array_sha(z),
        "repeat_correction_sha256": _s0_array_sha(z_repeat),
        "operational_residual_sha256": _s0_array_sha(r_final),
        "repeat_operational_residual_sha256": _s0_array_sha(r_repeat),
        "diagnostic_action_sha256": _s0_array_sha(q),
        "repeat_diagnostic_action_sha256": _s0_array_sha(q_repeat),
        "finite": True,
        "deterministic": bool(
            np.array_equal(z, z_repeat)
            and np.array_equal(r_final, r_repeat)
            and np.array_equal(q, q_repeat)
        ),
        "operational_action_count": int(operational_action_count),
        "diagnostic_action_count": int(diagnostic_action_count),
    }


def _s0_positive_times(value: Any, count: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == count
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            and float(item) > 0.0
            for item in value
        )
    )


def _s0_source_valid(label: Any, record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    if label not in H2B_SOURCE_LABELS:
        return False
    if record.get("definition") != H2B_SOURCE_DEFINITIONS[label] or record.get("definition_sha256") != _source_definition_sha(label):
        return False
    if not _valid_hash(record.get("vector_sha256")):
        return False
    if record.get("rho_norm_scope") != "all_fullspace_rows" or record.get("external_slave_mask") is not False:
        return False
    required = (
        "r_norm",
        "z_norm",
        "q_norm",
        "unit_residual_norm",
        "scaled_residual_norm",
        "q_h_r_real",
        "q_h_r_imag",
        "rho_unit",
        "rho_star",
        "eta",
        "action_closure_relative_error",
        "repeat_action_closure_relative_error",
    )
    numeric = []
    for key in required:
        value = record.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not math.isfinite(float(value)):
            return False
        if key not in {"q_h_r_real", "q_h_r_imag"} and float(value) < 0.0:
            return False
        numeric.append(float(value))
    r_norm, z_norm, q_norm, unit_norm, scaled_norm = numeric[:5]
    qh_real, qh_imag = numeric[5:7]
    if r_norm <= 0.0 or q_norm <= 0.0:
        return False
    omega_abs = record.get("omega_abs")
    omega_real = record.get("omega_real")
    omega_imag = record.get("omega_imag")
    q_over_r = record.get("q_over_r_amplification")
    z_over_r = record.get("z_over_r_amplification")
    for key, value in (
        ("omega_abs", omega_abs),
        ("omega_real", omega_real),
        ("omega_imag", omega_imag),
        ("q_over_r_amplification", q_over_r),
        ("z_over_r_amplification", z_over_r),
    ):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or (key not in {"omega_real", "omega_imag"} and float(value) < 0.0)
        ):
            return False
    qh_abs = math.hypot(qh_real, qh_imag)
    qh_expected = qh_abs / (q_norm * q_norm)
    rho_unit = unit_norm / r_norm
    rho_star = scaled_norm / r_norm
    eta = qh_abs / (q_norm * r_norm)
    if not (
        math.isclose(float(omega_real), qh_real / (q_norm * q_norm), rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(float(omega_imag), qh_imag / (q_norm * q_norm), rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(float(omega_abs), qh_expected, rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(record.get("rho_unit"), rho_unit, rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(record.get("rho_star"), rho_star, rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(record.get("eta"), eta, rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(float(record["q_over_r_amplification"]), q_norm / r_norm, rel_tol=1e-12, abs_tol=1e-15)
        and math.isclose(float(record["z_over_r_amplification"]), z_norm / r_norm, rel_tol=1e-12, abs_tol=1e-15)
        and rho_star <= 1.0 + 1.0e-12
        and eta <= 1.0 + 1.0e-12
        and rho_star <= rho_unit + 1.0e-12
        and float(record["action_closure_relative_error"]) <= 1.0e-11
        and float(record["repeat_action_closure_relative_error"]) <= 1.0e-11
    ):
        return False
    apply_seconds = record.get("apply_seconds")
    diagnostic_seconds = record.get("diagnostic_action_seconds")
    wall_seconds = record.get("wall_seconds")
    if (
        not _s0_positive_times(apply_seconds, 2)
        or not _s0_positive_times(diagnostic_seconds, 2)
        or not isinstance(wall_seconds, (int, float))
        or isinstance(wall_seconds, bool)
        or not math.isfinite(float(wall_seconds))
        or float(wall_seconds) <= 0.0
        or not math.isclose(
            float(wall_seconds),
            sum(float(item) for item in apply_seconds + diagnostic_seconds),
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
    ):
        return False
    hashes = (
        "correction_sha256",
        "repeat_correction_sha256",
        "operational_residual_sha256",
        "repeat_operational_residual_sha256",
        "diagnostic_action_sha256",
        "repeat_diagnostic_action_sha256",
    )
    if not all(_valid_hash(record.get(key)) for key in hashes):
        return False
    return bool(
        record.get("finite") is True
        and record.get("deterministic") is True
        and record.get("correction_sha256") == record.get("repeat_correction_sha256")
        and record.get("operational_residual_sha256") == record.get("repeat_operational_residual_sha256")
        and record.get("diagnostic_action_sha256") == record.get("repeat_diagnostic_action_sha256")
    )


def _s0_combination_valid(strategy: Any, combination: Any) -> bool:
    if not isinstance(combination, Mapping) or strategy not in H2B_S0_STRATEGIES:
        return False
    wall_seconds = combination.get("wall_seconds")
    if (
        not isinstance(wall_seconds, (int, float))
        or isinstance(wall_seconds, bool)
        or not math.isfinite(float(wall_seconds))
        or float(wall_seconds) <= 0.0
    ):
        return False
    sources = combination.get("sources")
    if not isinstance(sources, list) or [item.get("label") for item in sources if isinstance(item, Mapping)] != list(H2B_SOURCE_LABELS):
        return False
    expected_actions = H2B_S0_OPERATIONAL_ACTION_COUNTS[strategy]
    for source in sources:
        if not isinstance(source, Mapping) or not _s0_source_valid(source.get("label"), source):
            return False
        if (
            type(source.get("operational_action_count")) is not int
            or source.get("operational_action_count") != expected_actions
            or type(source.get("diagnostic_action_count")) is not int
            or source.get("diagnostic_action_count") != 2
        ):
            return False
    return True


def _s0_resource_valid(resource: Any) -> bool:
    if not isinstance(resource, Mapping):
        return False
    peak = resource.get("process_tree_peak_rss_bytes")
    swap = resource.get("process_tree_swap_bytes")
    return (
        type(peak) is int
        and peak >= 0
        and type(swap) is int
        and swap == 0
        and peak < H2B_S0_RSS_LIMIT_BYTES
    )


def _s0_select_route(combinations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Recompute the fixed S0 route without trusting a worker status field."""

    passing: list[dict[str, Any]] = []
    valid: list[str] = []
    for combination in combinations:
        strategy = combination.get("strategy")
        source_records = combination.get("sources")
        if not isinstance(strategy, str) or not _s0_combination_valid(strategy, combination):
            continue
        valid.append(strategy)
        if not all(
            float(source["rho_star"]) <= H2B_S0_RHO_LIMITS[source["label"]]
            for source in source_records
        ):
            continue
        worst = max(float(record["rho_star"]) for record in source_records)
        passing.append(
            {
                "strategy": strategy,
                "operational_action_count": H2B_S0_OPERATIONAL_ACTION_COUNTS[strategy],
                "worst_rho_star": worst,
                "wall_seconds": float(combination["wall_seconds"]),
            }
        )
    passing.sort(key=lambda item: (item["operational_action_count"], item["worst_rho_star"], item["wall_seconds"]))
    selected = passing[0] if passing else None
    return {
        "route": "H2B-K" if selected is not None else "H2B-P",
        "selected_strategy": None if selected is None else selected["strategy"],
        "valid_strategies": valid,
        "passing_strategies": [item["strategy"] for item in passing],
        "selection": selected,
    }


def _s0_check_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute S0 validity, resource stop, and direction qualification."""

    checks: dict[str, bool] = {}
    problems: list[str] = []
    checks["scope"] = raw.get("scope") == _s0_scope()
    checks["identity"] = raw.get("identity") == _fixed_identity()
    p6 = raw.get("p6")
    checks["p6"] = isinstance(p6, Mapping) and all(
        type(p6.get(key)) is int and p6.get(key) == value
        for key, value in {
            "global_cells": H2B_FIXED_CELLS,
            "local_cells": H2B_FIXED_CELLS,
            "local_nloc": H2B_FIXED_NLOC,
            "global_rows": H2B_FIXED_ROWS,
            "constraint_count": H2B_FIXED_CONSTRAINTS,
        }.items()
    )
    factor = raw.get("factor")
    checks["factor_authority"] = isinstance(factor, Mapping) and all(
        type(factor.get(key)) is int and factor.get(key) == value
        for key, value in {
            "class_count": H2B_FIXED_CLASSES,
            "cell_count": H2B_FIXED_CELLS,
            "unique_factor_count": H2B_FIXED_FACTORS,
            "factor_plus_metadata_bytes": 201_933_812,
        }.items()
    ) and factor.get("finite") is True and factor.get("deterministic") is True
    combinations = raw.get("combinations")
    checks["strategy_order"] = isinstance(combinations, list) and [
        item.get("strategy") for item in combinations if isinstance(item, Mapping)
    ] == list(H2B_S0_STRATEGIES)
    if not isinstance(combinations, list):
        combinations = []
    checks["combinations_valid"] = len(combinations) == len(H2B_S0_STRATEGIES) and all(
        isinstance(item, Mapping) and _s0_combination_valid(item.get("strategy"), item)
        for item in combinations
    )
    resource = raw.get("resource")
    checks["resource"] = _s0_resource_valid(resource)
    problems.extend(name for name, passed in checks.items() if passed is not True)
    failure_measurements = {
        "p6": p6,
        "factor": factor,
        "combinations": combinations,
        "resource": resource,
    }
    if problems:
        nonresource_problems = [name for name in problems if name != "resource"]
        status = "STOP_ANOMALY" if nonresource_problems else "STOP_RESOURCE"
        return {
            "schema": H2B_S0_CHECK_SCHEMA,
            "status": status,
            "pass": False,
            "route": status,
            "s0_direction_gate_pass": False,
            "problems": sorted(problems),
            "checks": checks,
            "measurements": None,
            "failure_measurements": failure_measurements,
        }
    selection = _s0_select_route(combinations)
    return {
        "schema": H2B_S0_CHECK_SCHEMA,
        "status": "pass",
        "pass": True,
        "route": selection["route"],
        "s0_direction_gate_pass": selection["route"] == "H2B-K",
        "problems": [],
        "checks": checks,
        "measurements": {
            "p6": p6,
            "factor": factor,
            "combinations": combinations,
            "resource": resource,
            "selection": selection,
        },
        "failure_measurements": None,
    }


def _s0_project_campaign_sources(combinations: Any, resource: Mapping[str, Any]) -> list[dict[str, Any]]:
    peak = int(resource["process_tree_peak_rss_bytes"])
    swap = int(resource["process_tree_swap_bytes"])
    return [
        {
            **combination,
            "sources": [
                {
                    **source,
                    "process_tree_peak_rss_bytes": peak,
                    "process_tree_swap_bytes": swap,
                    "process_tree_peak_scope": "whole_s0_online_campaign",
                }
                for source in combination["sources"]
            ],
        }
        for combination in combinations
    ]


def _s0_measure_source(
    label: str,
    rhs: Any,
    smoother: Any,
    exact_action: Any,
    strategy: str,
    slave_rows: Any,
) -> dict[str, Any]:
    """Run two fixed applications and one diagnostic action per result."""

    import numpy as np

    value = np.ascontiguousarray(np.asarray(rhs, dtype=np.complex128))
    first_tick = time.perf_counter()
    first_correction = smoother.apply_s0(value, strategy)
    first_seconds = float(time.perf_counter() - first_tick)
    first_residual = smoother.last_residual
    second_tick = time.perf_counter()
    second_correction = smoother.apply_s0(value, strategy)
    second_seconds = float(time.perf_counter() - second_tick)
    second_residual = smoother.last_residual
    diagnostic = []
    diagnostic_seconds: list[float] = []
    rows = np.asarray(slave_rows, dtype=np.int64)
    for correction in (first_correction, second_correction):
        source = np.ascontiguousarray(correction, dtype=np.complex128).copy()
        source[rows] = 0.0
        target = np.empty_like(source)
        diagnostic_tick = time.perf_counter()
        exact_action(source, target)
        diagnostic_seconds.append(float(time.perf_counter() - diagnostic_tick))
        diagnostic.append(np.ascontiguousarray(target))
    metrics = _s0_oracle_metrics(
        value,
        first_correction,
        first_residual,
        diagnostic[0],
        repeat_correction=second_correction,
        repeat_residual=second_residual,
        repeat_diagnostic_action=diagnostic[1],
        operational_action_count=int(smoother.audit["action_count"]),
        diagnostic_action_count=2,
    )
    metrics.update(
        {
            "label": label,
            "apply_seconds": [first_seconds, second_seconds],
            "diagnostic_action_seconds": diagnostic_seconds,
            "wall_seconds": float(
                first_seconds
                + second_seconds
                + sum(diagnostic_seconds)
            ),
            "rho_norm_scope": "all_fullspace_rows",
            "external_slave_mask": False,
        }
    )
    return metrics


def _cache_snapshot(cache_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not cache_dir.is_dir():
        raise FileNotFoundError(cache_dir)
    for path in sorted(cache_dir.iterdir(), key=lambda value: value.name):
        if not path.is_file():
            raise ValueError(f"cache entry is not a file: {path.name}")
        entries.append(
            {
                "path": path.name,
                "bytes": int(path.stat().st_size),
                "mtime_ns": int(path.stat().st_mtime_ns),
                "sha256": _sha256_file(path),
            }
        )
    return entries


def _form_code_state(code: Any) -> tuple[str, str | None]:
    if not isinstance(code, (tuple, list)) or len(code) != 2:
        return "invalid", None
    if code[0] is None and code[1] is None:
        return "hit_no_new_decl_impl", None
    if not all(isinstance(part, str) and part for part in code):
        return "invalid", None
    return "cold_decl_impl_generated", hashlib.sha256(
        (code[0] + "\0" + code[1]).encode("utf-8")
    ).hexdigest()


def _form_record(form: Any, ufl_form: Any, cache_dir: Path, cfg: Any, function_space: Any, role: str) -> dict[str, Any]:
    import numpy as np
    from benchmarks.run_task037_extra_h2 import _canonical_basis_signature, _jsonable, _proxy_identity

    module_name = str(form.module.__name__)
    prefix = "libffcx_forms_"
    if not module_name.startswith(prefix):
        raise ValueError("B0 form has an unexpected FFCx module")
    code_state, code_sha = _form_code_state(form.code)
    cache = _cache_snapshot(cache_dir)
    files = [item for item in cache if item["path"].startswith(module_name + ".")]
    suffixes = (".c", ".o", ".so", ".c.cached")
    if not all(any(item["path"].endswith(suffix) for item in files) for suffix in suffixes):
        raise ValueError(f"B0 module artifacts are incomplete: {module_name}")
    return {
        "role": role,
        "ufl_signature": str(ufl_form.signature()),
        "ufcx_signature": form.module.ffi.string(form.ufcx_form.signature).decode("ascii"),
        "module_name": module_name,
        "ffcx_signature_stem": module_name[len(prefix) :],
        "code_state": code_state,
        "code_sha256": code_sha,
        "jit_options": {
            "cache_dir": str(cache_dir.resolve()),
            "cffi_extra_compile_args": list(H2B_FORM_JIT_ARGS),
        },
        "form_compiler_options": {"scalar_type": str(np.dtype(np.complex128))},
        "proxy_identity": {
            "operator": "(1/mu_r)*K_curl+k0^2*M_abs_epsilon",
            "k0": float(cfg.k0),
            "mu_r": [float(complex(cfg.mu_r).real), float(complex(cfg.mu_r).imag)],
            "unit_mass_before_abs_epsilon": True,
            "production_proxy_identity": _jsonable(_proxy_identity(cfg)),
        },
        "element_signature": list(_canonical_basis_signature(function_space)),
        "cache_files": files,
    }


def _lazy_h2a() -> Any:
    """Import the existing heavy runner only inside a worker/checker."""

    import benchmarks.run_task037_extra_h2 as h2a

    return h2a


def _build_b0_form(function_space: Any, mesh_data: Any, cfg: Any) -> tuple[Any, Any]:
    import numpy as np
    import ufl
    from petsc4py import PETSc
    from src.common.materials import relative_permittivity

    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_data.mesh)
    epsilon = relative_permittivity(mesh_data, cfg)
    epsilon.x.array[:] = np.abs(epsilon.x.array)
    epsilon.x.scatter_forward()
    b0 = (
        PETSc.ScalarType(1.0 / cfg.mu_r) * ufl.inner(ufl.curl(u), ufl.curl(v))
        + PETSc.ScalarType(float(cfg.k0) ** 2) * epsilon * ufl.inner(u, v)
    ) * dx
    return b0, epsilon


def _runtime_identity(h2a: Any, *, compiler_probe: bool, compiler: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return h2a._r1_runtime_identity(compiler_probe=compiler_probe, compiler=compiler)


def _source_pair(h2a: Any) -> dict[str, Any]:
    return h2a._r1_inspect_source(h2a.ROOT).as_jsonable()


def _light_source() -> dict[str, Any]:
    command = [
        "git",
        "--git-dir",
        str(ROOT / ".git-codex"),
        "--work-tree",
        str(ROOT),
        "rev-parse",
        "HEAD",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    status = subprocess.run(
        [
            "git",
            "--git-dir",
            str(ROOT / ".git-codex"),
            "--work-tree",
            str(ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in status.stdout.splitlines() if line.strip()]
    untracked = [line[3:] for line in lines if line.startswith("?? ") and len(line) > 3]
    return {
        "source_commit_full_sha": result.stdout.strip(),
        "tracked_source_dirty": bool(lines),
        "source_worktree_dirty": bool(lines),
        "cleanliness_semantics": (
            "all tracked changes plus every nonignored untracked path"
        ),
        "nonignored_untracked_paths": untracked,
        "worktree_status_porcelain": lines,
        "git_error": None,
    }


def _expected_jit_options(cache_dir: Path) -> dict[str, Any]:
    return {
        "cache_dir": str(cache_dir.resolve()),
        "cffi_extra_compile_args": list(H2B_FORM_JIT_ARGS),
    }


def _form_files_valid(run_dir: Path, form: Any) -> bool:
    if not isinstance(form, Mapping) or not isinstance(form.get("cache_files"), list):
        return False
    module = form.get("module_name")
    if not isinstance(module, str) or not module:
        return False
    required = {".c": False, ".o": False, ".so": False, ".c.cached": False}
    paths: set[str] = set()
    for item in form["cache_files"]:
        if not isinstance(item, Mapping):
            return False
        relative = item.get("path")
        if not isinstance(relative, str) or not relative.startswith(module + ".") or relative in paths:
            return False
        paths.add(relative)
        if not isinstance(item.get("bytes"), int) or isinstance(item["bytes"], bool) or item["bytes"] <= 0:
            return False
        if not isinstance(item.get("mtime_ns"), int) or isinstance(item["mtime_ns"], bool) or item["mtime_ns"] <= 0:
            return False
        if not _valid_hash(item.get("sha256")):
            return False
        for suffix in required:
            if relative.endswith(suffix):
                required[suffix] = True
        path = run_dir / "jit_cache" / relative
        if not path.is_file() or path.stat().st_size != item["bytes"] or _sha256_file(path) != item["sha256"]:
            return False
    return bool(paths) and all(required.values())


def _forms_match(stage: Any, online: Any, run_dir: Path) -> bool:
    required = {
        "role",
        "ufl_signature",
        "ufcx_signature",
        "module_name",
        "ffcx_signature_stem",
        "jit_options",
        "form_compiler_options",
        "proxy_identity",
        "element_signature",
        "cache_files",
        "code_state",
    }
    if not isinstance(stage, Mapping) or not isinstance(online, Mapping):
        return False
    if not required.issubset(stage) or not required.issubset(online):
        return False
    if stage.get("role") != "b0" or online.get("role") != "b0":
        return False
    if stage.get("code_state") != "cold_decl_impl_generated" or online.get("code_state") != "hit_no_new_decl_impl":
        return False
    if stage.get("module_name") != "libffcx_forms_" + str(stage.get("ffcx_signature_stem")):
        return False
    if online.get("module_name") != "libffcx_forms_" + str(online.get("ffcx_signature_stem")):
        return False
    for key in ("ufl_signature", "ufcx_signature", "module_name", "ffcx_signature_stem"):
        if not isinstance(stage.get(key), str) or not stage[key] or stage.get(key) != online.get(key):
            return False
    expected_options = _expected_jit_options(run_dir / "jit_cache")
    if stage.get("jit_options") != expected_options or online.get("jit_options") != expected_options:
        return False
    if stage.get("form_compiler_options") != {"scalar_type": "complex128"} or online.get("form_compiler_options") != {"scalar_type": "complex128"}:
        return False
    for key in ("proxy_identity", "element_signature"):
        if not stage.get(key) or stage.get(key) != online.get(key):
            return False
    if stage.get("cache_files") != online.get("cache_files"):
        return False
    return _form_files_valid(run_dir, stage) and _form_files_valid(run_dir, online)


def _emit_marker(stream: Any, *, event: str, phase: str, started: float, **extra: Any) -> None:
    marker = {
        "schema": H2B_PROGRESS_SCHEMA,
        "phase": phase,
        "event": event,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
        **extra,
    }
    stream.write(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()
    print(json.dumps(marker, sort_keys=True), flush=True)


def _worker_error_types() -> tuple[type[BaseException], ...]:
    return (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    )


def _run_jit_worker(run_dir: Path) -> int:
    import gc

    h2a = _lazy_h2a()
    from src.common.config_3d import target_stage4_config
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space

    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    progress = run_dir / "stage_progress.jsonl"
    summary_path = run_dir / "stage_summary.json"
    cache_dir = run_dir / "jit_cache"
    started = time.perf_counter()
    source_start = _source_pair(h2a)
    runtime: dict[str, Any] | None = None
    form_record: dict[str, Any] | None = None
    measurement: dict[str, Any] | None = None
    error: str | None = None
    try:
        with progress.open("w", encoding="utf-8") as markers:
            _emit_marker(markers, event="mesh_build_started", phase="stage", started=started)
            if cache_dir.exists() and any(cache_dir.iterdir()):
                raise ValueError("dedicated H2B cache is not initially empty")
            cache_dir.mkdir(parents=True, exist_ok=True)
            cfg = target_stage4_config(degree=6, h_nm=10.0)
            mesh_data = build_airbox_mesh_3d(cfg, run_dir / "stage_mesh")
            _emit_marker(markers, event="mesh_build_ready", phase="stage", started=started)
            _emit_marker(markers, event="function_space_started", phase="stage", started=started)
            function_space = _create_nedelec_space(mesh_data.mesh, cfg)
            index_map = function_space.dofmap.index_map
            measurement = {
                "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
                "local_cells": int(mesh_data.mesh.topology.index_map(3).size_local),
                "local_nloc": int(function_space.element.space_dimension),
                "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
            }
            _emit_marker(markers, event="function_space_ready", phase="stage", started=started, **measurement)
            _emit_marker(markers, event="b0_form_started", phase="stage", started=started)
            _b0, _epsilon = _build_b0_form(function_space, mesh_data, cfg)
            runtime = _runtime_identity(h2a, compiler_probe=True)
            _emit_marker(markers, event="compiler_probe_ready", phase="stage", started=started)
            from dolfinx import fem
            import ufl

            _coefficient = fem.Function(function_space)
            action_ufl = ufl.action(_b0, _coefficient)

            _emit_marker(markers, event="b0_compile_started", phase="stage", started=started)
            form = fem.form(action_ufl, jit_options={
                "cache_dir": str(cache_dir.resolve()),
                "cffi_extra_compile_args": list(H2B_FORM_JIT_ARGS),
            })
            form_record = _form_record(form, action_ufl, cache_dir, cfg, function_space, "b0")
            if form_record["code_state"] != "cold_decl_impl_generated":
                raise ValueError("stage B0 form did not report cold code generation")
            _emit_marker(markers, event="b0_compile_ready", phase="stage", started=started)
            _emit_marker(markers, event="summary_started", phase="stage", started=started)
            _emit_marker(markers, event="summary_ready", phase="stage", started=started)
            del form, action_ufl, _coefficient, _epsilon, _b0, function_space, mesh_data
    except _worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            h2a.clear_floquet_topology_cache()
        finally:
            gc.collect()
    source_end = _source_pair(h2a)
    payload = _attach_evidence(
        {
            "schema": H2B_WORKER_SCHEMA,
            "phase": "stage",
            "status": "measurement_complete" if error is None else "gate_failed",
            "scope": _fixed_scope(),
            "identity": _fixed_identity(),
            "phase_identity": _phase_identity(jit_api=True, compile_called=True, compiler_probe=True),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "runtime_identity": runtime,
            "measurement": measurement,
            "form": form_record,
            "cache_inventory": _cache_snapshot(cache_dir) if cache_dir.is_dir() else None,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if error is None else 1


def _run_legacy_measurement(smoother: Any, source_arrays: Mapping[str, Any], sources: list[dict[str, Any]], exact_action: Any, slaves: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np

    warm = np.zeros(H2B_FIXED_ROWS, dtype=np.complex128)
    warm_target = np.zeros_like(warm)
    warm_tick = time.perf_counter()
    exact_action(warm, warm_target)
    warm_seconds = float(time.perf_counter() - warm_tick)
    volume_probe = np.asarray(source_arrays["physical-RHS-like"], dtype=np.complex128)
    volume_probe[slaves] = 0.0
    action_times: list[float] = []
    for _ in range(5):
        out = np.empty_like(volume_probe)
        tick = time.perf_counter()
        exact_action(volume_probe, out)
        action_times.append(float(time.perf_counter() - tick))
    smoother_times: list[float] = []
    for record in sources:
        rhs = np.ascontiguousarray(source_arrays[record["label"]], dtype=np.complex128)
        rhs[slaves] = 0.0
        first_tick = time.perf_counter()
        first_correction = smoother.apply(rhs)
        first_seconds = float(time.perf_counter() - first_tick)
        smoother_times.append(first_seconds)
        first_residual = smoother.last_residual
        second_tick = time.perf_counter()
        second_correction = smoother.apply(rhs)
        second_seconds = float(time.perf_counter() - second_tick)
        smoother_times.append(second_seconds)
        second_residual = smoother.last_residual
        independent_target = np.empty_like(rhs)
        correction_for_action = np.ascontiguousarray(first_correction, dtype=np.complex128)
        correction_for_action[slaves] = 0.0
        exact_action(correction_for_action, independent_target)
        independent_residual = rhs - independent_target
        denominator = float(np.linalg.norm(rhs))
        numerator = float(np.linalg.norm(independent_residual))
        record.update(
            {
                "correction_sha256": _s0_array_sha(first_correction),
                "repeat_correction_sha256": _s0_array_sha(second_correction),
                "residual_sha256": _s0_array_sha(first_residual),
                "repeat_residual_sha256": _s0_array_sha(second_residual),
                "finite": bool(np.all(np.isfinite(first_correction)) and np.all(np.isfinite(first_residual))),
                "independent_residual_numerator": numerator,
                "independent_residual_denominator": denominator,
                "rho": numerator / max(denominator, np.finfo(float).tiny),
                "independent_action_relative_error": float(
                    np.linalg.norm(first_residual - independent_residual)
                    / max(denominator, np.finfo(float).tiny)
                ),
                "apply_seconds": [first_seconds, second_seconds],
            }
        )
    action_median = float(statistics.median(action_times))
    smoother_median = float(statistics.median(smoother_times))
    return smoother.audit, {
        "timing": {
            "warm_action_seconds": warm_seconds,
            "volume_action_seconds": action_times,
            "action_median_seconds": action_median,
            "smoother_apply_seconds": smoother_times,
            "smoother_median_seconds": smoother_median,
            "smoother_action_ratio": smoother_median / max(action_median, 1.0e-30),
        },
    }


def _run_s0_measurement(
    store: Any,
    source_arrays: Mapping[str, Any],
    base_sources: list[dict[str, Any]],
    exact_action: Any,
    slaves: Any,
) -> dict[str, Any]:
    import numpy as np
    from src.solvers.hcurl_h2b_block_smoother import (
        build_h2b_constrained_block_smoother,
    )

    combinations: list[dict[str, Any]] = []
    for strategy in H2B_S0_STRATEGIES:
        strategy_started = time.perf_counter()
        smoother = build_h2b_constrained_block_smoother(
            store,
            global_row_count=H2B_FIXED_ROWS,
            owned_slave_identity_rows=slaves,
            action=exact_action,
            task037_extra_h2b=True,
        )
        records = []
        for base in base_sources:
            label = str(base["label"])
            rhs = np.ascontiguousarray(source_arrays[label], dtype=np.complex128)
            rhs[slaves] = 0.0
            record = dict(base)
            record.update(_s0_measure_source(label, rhs, smoother, exact_action, strategy, slaves))
            records.append(record)
        combinations.append(
            {
                "strategy": strategy,
                "sources": records,
                "wall_seconds": float(time.perf_counter() - strategy_started),
            }
        )
        del smoother
    return {"combinations": combinations}


def _run_online_worker(run_dir: Path, *, s0: bool = False) -> int:
    import gc

    import numpy as np
    from petsc4py import PETSc

    h2a = _lazy_h2a()
    from src.common.config_3d import target_stage4_config
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.hcurl_h2b_block_smoother import build_h2b_constrained_block_smoother
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    run_dir = run_dir.resolve()
    phase = "s0" if s0 else "online"
    worker_schema = H2B_S0_WORKER_SCHEMA if s0 else H2B_WORKER_SCHEMA
    progress = run_dir / ("s0_progress.jsonl" if s0 else "online_progress.jsonl")
    summary_path = run_dir / ("s0_summary.json" if s0 else "online_summary.json")
    stage_path = run_dir / "stage_summary.json"
    started = time.perf_counter()
    source_start = _source_pair(h2a)
    runtime: dict[str, Any] | None = None
    measurement: dict[str, Any] | None = None
    error: str | None = None
    factor_audit: dict[str, Any] | None = None
    smoother_audit: dict[str, Any] | None = None
    producer_authority: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = []
    try:
        with progress.open("w", encoding="utf-8") as markers:
            _emit_marker(markers, event="authority_validate_started", phase=phase, started=started)
            stage = _read_json(stage_path)
            if stage.get("schema") != H2B_WORKER_SCHEMA or not _evidence_valid(stage):
                raise ValueError("stage summary authority is invalid")
            authority = _authority()
            producer_authority = authority["producer_authority"]
            r0 = authority["r0"]
            if r0["global_rows"] != H2B_FIXED_ROWS or r0["constraint_count"] != H2B_FIXED_CONSTRAINTS:
                raise ValueError("R0 authority identity mismatch")
            _emit_marker(markers, event="authority_validate_ready", phase=phase, started=started)
            cfg = target_stage4_config(degree=6, h_nm=10.0)
            _emit_marker(markers, event="mesh_build_started", phase=phase, started=started)
            mesh_data = build_airbox_mesh_3d(cfg, run_dir / "online_mesh")
            _emit_marker(markers, event="mesh_build_ready", phase=phase, started=started)
            _emit_marker(markers, event="function_space_started", phase=phase, started=started)
            function_space = _create_nedelec_space(mesh_data.mesh, cfg)
            _emit_marker(markers, event="function_space_ready", phase=phase, started=started)
            _emit_marker(markers, event="floquet_mpc_started", phase=phase, started=started)
            floquet = h2a.build_double_floquet_mpc(function_space, mesh_data, cfg)
            index_map = function_space.dofmap.index_map
            measurement = {
                "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
                "local_cells": int(mesh_data.mesh.topology.index_map(3).size_local),
                "local_nloc": int(function_space.element.space_dimension),
                "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
                "constraint_count": int(floquet.num_constraints),
            }
            if measurement != {
                "global_cells": H2B_FIXED_CELLS,
                "local_cells": H2B_FIXED_CELLS,
                "local_nloc": H2B_FIXED_NLOC,
                "global_rows": H2B_FIXED_ROWS,
                "constraint_count": H2B_FIXED_CONSTRAINTS,
            }:
                raise ValueError("H2B p6 identity mismatch")
            _emit_marker(markers, event="floquet_mpc_ready", phase=phase, started=started)
            cache_dir = run_dir / "jit_cache"
            before = _cache_snapshot(cache_dir)
            _b0, _epsilon = _build_b0_form(function_space, mesh_data, cfg)
            _emit_marker(markers, event="b0_cache_load_started", phase=phase, started=started)
            runtime = _runtime_identity(
                h2a,
                compiler_probe=False,
                compiler=stage["runtime_identity"]["compiler"],
            )
            action = build_task037_extra_h1r2_mpc_action(
                _b0,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options={
                    "cache_dir": str(cache_dir.resolve()),
                    "cffi_extra_compile_args": list(H2B_FORM_JIT_ARGS),
                },
            )
            form_record = _form_record(action._action_form, action._action_ufl, cache_dir, cfg, function_space, "b0")
            after = _cache_snapshot(cache_dir)
            if form_record["code_state"] != "hit_no_new_decl_impl" or before != after:
                raise ValueError("online B0 form did not hit the staged cache")
            _emit_marker(markers, event="b0_cache_load_ready", phase=phase, started=started)
            _emit_marker(markers, event="factor_load_started", phase=phase, started=started)
            store = h2a.load_h2a_r2_factor_store(H2B_R2_MANIFEST, task037_extra_h2a_r2=True)
            factor_audit = dict(store.audit)
            if _sha256_file(H2B_R2_MANIFEST) != H2B_R2_MANIFEST_SHA256:
                raise ValueError("R2 factor manifest changed")
            _emit_marker(markers, event="factor_load_ready", phase=phase, started=started)
            slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
            primal_arrays = _source_arrays(function_space, cfg, slaves, floquet.mpc)
            source_vec = action.output_vector.duplicate()

            def exact_action(source: np.ndarray, target: np.ndarray) -> None:
                if np.any(source[slaves] != 0.0):
                    raise ValueError("H2B action source has nonzero identity rows")
                with source_vec.localForm() as local:
                    local.set(0.0)
                    local.array_w[: source.size] = source
                source_vec.ghostUpdate(
                    addv=PETSc.InsertMode.INSERT_VALUES,
                    mode=PETSc.ScatterMode.FORWARD,
                )
                result = action.mult(source_vec)
                target[:] = np.asarray(result.getArray(readonly=True), dtype=np.complex128)

            source_arrays = _residual_source_arrays(primal_arrays, exact_action, slaves)
            del primal_arrays
            sources = _source_records_from_arrays(source_arrays, slaves)
            _emit_marker(markers, event="source_setup_ready", phase=phase, started=started)

            smoother = None
            if s0:
                _emit_marker(markers, event="s0_measurement_started", phase=phase, started=started)
                s0_measurement = _run_s0_measurement(
                    store, source_arrays, sources, exact_action, slaves
                )
                payload_measurement = {
                    "p6": measurement,
                    "factor": {
                        "class_count": int(factor_audit["class_count"]),
                        "cell_count": int(factor_audit["cell_count"]),
                        "unique_factor_count": int(factor_audit["unique_factor_count"]),
                        "factor_plus_metadata_bytes": int(factor_audit["factor_plus_metadata_bytes"]),
                        "finite": factor_audit["finite"],
                        "deterministic": factor_audit["deterministic"],
                    },
                    **s0_measurement,
                    "cache": {
                        "before": before,
                        "after": after,
                        "unchanged": before == after,
                        "form_jit_cache_hit": True,
                        "c_source_regeneration": False,
                        "compiler_descendant_pids": [],
                    },
                    "stage_manifest_sha256": _sha256_file(stage_path),
                    "r2_manifest_sha256": H2B_R2_MANIFEST_SHA256,
                }
                _emit_marker(markers, event="s0_measurement_ready", phase=phase, started=started)
            else:
                smoother = build_h2b_constrained_block_smoother(
                    store,
                    global_row_count=H2B_FIXED_ROWS,
                    owned_slave_identity_rows=slaves,
                    action=exact_action,
                    task037_extra_h2b=True,
                )
                _emit_marker(markers, event="smoother_ready", phase=phase, started=started)
                smoother_audit, legacy_measurement = _run_legacy_measurement(
                    smoother, source_arrays, sources, exact_action, slaves
                )
                payload_measurement = {
                    "p6": measurement,
                    **legacy_measurement,
                    "cache": {
                        "before": before,
                        "after": after,
                        "unchanged": before == after,
                        "form_jit_cache_hit": True,
                        "c_source_regeneration": False,
                        "compiler_descendant_pids": [],
                    },
                    "stage_manifest_sha256": _sha256_file(stage_path),
                    "r2_manifest_sha256": H2B_R2_MANIFEST_SHA256,
                }
            _emit_marker(markers, event="summary_started", phase=phase, started=started)
            _emit_marker(markers, event="summary_ready", phase=phase, started=started)
            source_vec.destroy()
            action.destroy()
            del smoother, store, _epsilon, _b0, function_space, mesh_data, floquet
    except _worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
        payload_measurement = locals().get("payload_measurement")
        form_record = locals().get("form_record")
        before = locals().get("before")
        after = locals().get("after")
    finally:
        h2a.clear_floquet_topology_cache()
        gc.collect()
    source_end = _source_pair(h2a)
    payload = _attach_evidence(
        {
            "schema": worker_schema,
            "phase": phase,
            "status": "measurement_complete" if error is None else "gate_failed",
            "scope": _s0_scope() if s0 else _fixed_scope(),
            "identity": _fixed_identity(),
            "phase_identity": _phase_identity(jit_api=True, compile_called=False, compiler_probe=False),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "runtime_identity": runtime,
            "producer_authority": producer_authority,
            "current_online_source": source_start,
            "measurement": locals().get("payload_measurement"),
            "form": locals().get("form_record"),
            "cache_before": locals().get("before"),
            "cache_after": locals().get("after"),
            "cache_unchanged": locals().get("before") is not None and locals().get("before") == locals().get("after"),
            "factor_manifest": str(H2B_R2_MANIFEST),
            "factor_manifest_sha256": H2B_R2_MANIFEST_SHA256,
            "factor_audit": factor_audit,
            **({"smoother_audit": smoother_audit} if not s0 else {}),
            "sources": [] if s0 else sources,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if error is None else 1


def _run_s0_worker(run_dir: Path) -> int:
    return _run_online_worker(run_dir, s0=True)


def _compiler_descendant_pids(pids: Sequence[int]) -> list[int]:
    found: list[int] = []
    for pid in pids:
        try:
            command = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
        except OSError:
            continue
        if any(token in command for token in ("/cc ", "/cc\n", "gcc", "g++", "clang")):
            found.append(int(pid))
    return sorted(set(found))


def _monitor_phase(
    run_dir: Path,
    phase: str,
    command: list[str],
    timeout: float,
    rss_limit: int,
) -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import process_tree_sample
    from benchmarks.run_task033_case090_watchdog import terminate_process_tree

    stdout_path = run_dir / f"{phase}_stdout.txt"
    timeline_path = run_dir / f"{phase}_timeline.jsonl"
    root_path = run_dir / f"{phase}_root_pid.json"
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, timeline_path.open("w", encoding="utf-8") as timeline:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=stdout,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        _write_json(root_path, {"schema": f"{H2B_SCHEMA}.root.v1", "phase": phase, "root_pid": process.pid})
        peak = 0
        swap = 0
        sampled_pids: set[int] = set()
        termination: dict[str, Any] | None = None
        while process.poll() is None:
            sample = process_tree_sample(process.pid)
            pids = list(sample.pids)
            compiler = _compiler_descendant_pids(pids)
            item = {
                "schema": H2B_PROGRESS_SCHEMA,
                "phase": phase,
                "sample_kind": "worker",
                "elapsed_wall_seconds": float(time.perf_counter() - started),
                "root_pid": int(sample.root_pid),
                "pids": pids,
                "process_count": len(pids),
                "rss_bytes": int(sample.rss_bytes),
                "swap_bytes": int(sample.swap_bytes),
                "all_status_readable": bool(sample.all_status_readable),
                "compiler_descendant_pids": compiler,
            }
            if not sample.all_status_readable:
                terminal_return_code = process.poll()
                if terminal_return_code is not None:
                    item.update(
                        {
                            "sample_kind": "terminal_exit_unreadable",
                            "formal_sample": False,
                            "terminal_exit": True,
                            "return_code": int(terminal_return_code),
                        }
                    )
            timeline.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
            timeline.flush()
            if item["sample_kind"] == "worker" and sample.all_status_readable:
                peak = max(peak, int(sample.rss_bytes))
                swap = max(swap, int(sample.swap_bytes))
            sampled_pids.update(pids)
            elapsed = time.perf_counter() - started
            if item["sample_kind"] == "terminal_exit_unreadable":
                break
            if not sample.all_status_readable:
                termination = {"reason": "process_tree_unreadable"}
                break
            if sample.swap_bytes > H2B_SWAP_LIMIT_BYTES:
                termination = {"reason": "swap_over_limit"}
                break
            if sample.rss_bytes >= rss_limit:
                termination = {"reason": "process_tree_rss_at_or_over_limit"}
                break
            if elapsed > timeout:
                termination = {"reason": "timeout"}
                break
            time.sleep(0.05)
        if termination is not None and process.poll() is None:
            termination["termination"] = terminate_process_tree(process)
        return_code = process.wait()
    return {
        "phase": phase,
        "command": command,
        "root_pid": int(process.pid),
        "return_code": int(return_code),
        "termination": termination,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
        "peak_rss_bytes": peak,
        "swap_bytes": swap,
        "observed_process_tree_pids": sorted(sampled_pids),
    }


def _processes_gone(process_info: Mapping[str, Any]) -> bool:
    pids = [process_info.get("root_pid"), *process_info.get("observed_process_tree_pids", [])]
    return all(isinstance(pid, int) and not (Path("/proc") / str(pid)).exists() for pid in pids)


def _s0_stage_lifecycle_valid(stage_process: Any) -> bool:
    return bool(
        isinstance(stage_process, Mapping)
        and type(stage_process.get("return_code")) is int
        and stage_process.get("return_code") == 0
        and stage_process.get("termination") is None
        and stage_process.get("processes_gone_before_s0") is True
    )


def _bounded_process_drain(process_info: Mapping[str, Any]) -> dict[str, Any]:
    """Check post-wait PID teardown for at most the fixed five-second window."""

    started = time.perf_counter()
    polls = 0
    while True:
        gone = _processes_gone(process_info)
        elapsed = float(time.perf_counter() - started)
        if gone or elapsed >= H2B_PROCESS_DRAIN_TIMEOUT_SECONDS:
            return {
                "gone": bool(gone),
                "elapsed_wall_seconds": elapsed,
                "poll_count": polls,
            }
        polls += 1
        time.sleep(H2B_PROCESS_DRAIN_POLL_SECONDS)


def _stage_gate_allows_online(
    stage_process: Mapping[str, Any],
    stage_summary: Mapping[str, Any],
    processes_gone: bool,
    run_dir: Path | None = None,
) -> bool:
    basic = bool(
        stage_process.get("return_code") == 0
        and stage_process.get("termination") is None
        and stage_summary.get("status") == "measurement_complete"
        and _evidence_valid(stage_summary)
        and processes_gone
    )
    if not basic or run_dir is None:
        return basic
    try:
        measurement = stage_summary.get("measurement")
        form = stage_summary.get("form")
        return bool(
            stage_summary.get("scope") == _fixed_scope()
            and stage_summary.get("identity") == _fixed_identity()
            and stage_summary.get("phase_identity")
            == _phase_identity(jit_api=True, compile_called=True, compiler_probe=True)
            and _source_pair_valid(
                stage_summary.get("source_at_start"), stage_summary.get("source_at_end")
            )
            and _runtime_valid(stage_summary.get("runtime_identity"))
            and measurement
            == {
                "global_cells": H2B_FIXED_CELLS,
                "local_cells": H2B_FIXED_CELLS,
                "local_nloc": H2B_FIXED_NLOC,
                "global_rows": H2B_FIXED_ROWS,
            }
            and _progress_events(run_dir / "stage_progress.jsonl", "stage")
            == list(H2B_STAGE_EVENTS)
            and _timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")["peak_rss_bytes"]
            < H2B_STAGE_RSS_LIMIT_BYTES
            and _timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")["swap_bytes"]
            == 0
            and isinstance(stage_summary.get("cache_inventory"), list)
            and stage_summary["cache_inventory"] == _cache_snapshot(run_dir / "jit_cache")
            and isinstance(form, Mapping)
            and form.get("role") == "b0"
            and form.get("code_state") == "cold_decl_impl_generated"
            and isinstance(form.get("ufl_signature"), str)
            and bool(form["ufl_signature"])
            and isinstance(form.get("ufcx_signature"), str)
            and bool(form["ufcx_signature"])
            and form.get("module_name") == "libffcx_forms_" + str(form.get("ffcx_signature_stem"))
            and form.get("jit_options") == _expected_jit_options(run_dir / "jit_cache")
            and form.get("form_compiler_options") == {"scalar_type": "complex128"}
            and _form_files_valid(run_dir, form)
        )
    except _worker_error_types():
        return False


def _worker_command(executable: str, phase: str, run_dir: Path) -> list[str]:
    if phase not in {"jit-worker", "online-worker", "s0-worker"}:
        raise ValueError("H2B worker phase is fixed")
    return [
        str(executable),
        "-m",
        "benchmarks.run_task037_extra_h2b",
        phase,
        "--run-dir",
        str(Path(run_dir).resolve()),
    ]


def _worker_executable() -> str:
    return os.path.abspath(sys.executable)


def _run_watchdog(run_dir: Path) -> int:
    run_dir = run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(f"H2B run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    started = time.perf_counter()
    source_start: dict[str, Any] | None = None
    stage: dict[str, Any] | None = None
    online: dict[str, Any] | None = None
    error: str | None = None
    executable = _worker_executable()
    try:
        source_start = _light_source()
        command = _worker_command(executable, "jit-worker", run_dir)
        stage = _monitor_phase(run_dir, "stage", command, H2B_STAGE_TIMEOUT_SECONDS, H2B_STAGE_RSS_LIMIT_BYTES)
        stage_summary = _read_json(run_dir / "stage_summary.json")
        drain = _bounded_process_drain(stage)
        processes_gone = drain["gone"]
        stage["processes_gone_before_online"] = bool(processes_gone)
        stage["processes_gone_before_online_drain"] = drain
        stage_ok = _stage_gate_allows_online(stage, stage_summary, processes_gone, run_dir)
        if not stage_ok:
            error = "stage_gate_failed_before_online"
        else:
            online_command = _worker_command(executable, "online-worker", run_dir)
            online = _monitor_phase(run_dir, "online", online_command, H2B_ONLINE_TIMEOUT_SECONDS, H2B_ONLINE_RSS_LIMIT_BYTES)
    except _worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_end = _light_source() if source_start is not None else None
    payload = _attach_evidence(
        {
            "schema": H2B_WATCHDOG_SCHEMA,
            "status": "pass" if error is None and stage and online and stage["return_code"] == 0 and online["return_code"] == 0 else "gate_failed",
            "run_dir": str(run_dir),
            "scope": _fixed_scope(),
            "identity": _fixed_identity(),
            "command_identity": {
                "python": executable,
                "launch_mode": "direct_singleton",
                "stage_command": None if stage is None else stage["command"],
                "online_command": None if online is None else online["command"],
            },
            "source_at_start": source_start,
            "source_at_end": source_end,
            "stage": stage,
            "online": online,
            "error": error,
            "completion_elapsed_seconds": float(time.perf_counter() - started),
            "raw_artifacts": {
                name: _artifact(run_dir, name)
                for name in (
                    "stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json", "stage_timeline.jsonl",
                    "online_progress.jsonl", "online_stdout.txt", "online_summary.json", "online_timeline.jsonl",
                    "stage_root_pid.json", "online_root_pid.json",
                )
            },
        }
    )
    _write_json(run_dir / "h2b_watchdog_summary.json", payload)
    return 0 if payload["status"] == "pass" else 1


def _run_s0_watchdog(run_dir: Path) -> int:
    """Run the existing cache stage, then the single S0 worker sequentially."""

    run_dir = run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(f"H2B-S0 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    started = time.perf_counter()
    source_start: dict[str, Any] | None = None
    source_end: dict[str, Any] | None = None
    executable: str | None = None
    stage: dict[str, Any] | None = None
    error: str | None = None
    s0: dict[str, Any] | None = None
    try:
        source_start = _light_source()
        executable = _worker_executable()
        stage = _monitor_phase(
            run_dir,
            "stage",
            _worker_command(executable, "jit-worker", run_dir),
            H2B_STAGE_TIMEOUT_SECONDS,
            H2B_STAGE_RSS_LIMIT_BYTES,
        )
        stage_summary = _read_json(run_dir / "stage_summary.json")
        drain = _bounded_process_drain(stage)
        processes_gone = drain["gone"]
        stage["processes_gone_before_s0"] = bool(processes_gone)
        stage["processes_gone_before_s0_drain"] = drain
        if not _stage_gate_allows_online(stage, stage_summary, processes_gone, run_dir):
            error = "stage_gate_failed_before_s0"
        else:
            s0 = _monitor_phase(
                run_dir,
                "s0",
                _worker_command(executable, "s0-worker", run_dir),
                H2B_S0_TIMEOUT_SECONDS,
                H2B_S0_RSS_LIMIT_BYTES,
            )
            drain = _bounded_process_drain(s0)
            s0["processes_gone_after_s0"] = bool(drain["gone"])
            s0["processes_gone_after_s0_drain"] = drain
    except _worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    if source_start is not None:
        try:
            source_end = _light_source()
        except _worker_error_types() as exc:
            error = f"{type(exc).__name__}: {exc}"
    stage_ok = (
        stage is not None
        and stage.get("return_code") == 0
        and stage.get("termination") is None
        and stage.get("processes_gone_before_s0") is True
    )
    s0_ok = (
        s0 is not None
        and s0.get("return_code") == 0
        and s0.get("termination") is None
        and s0.get("processes_gone_after_s0") is True
    )
    payload = _attach_evidence(
        {
            "schema": H2B_S0_WATCHDOG_SCHEMA,
            "status": "pass" if error is None and stage_ok and s0_ok else "gate_failed",
            "run_dir": str(run_dir),
            "scope": _s0_scope(),
            "identity": _fixed_identity(),
            "command_identity": {
                "python": executable,
                "launch_mode": "direct_singleton",
                "stage_command": None if stage is None else stage["command"],
                "s0_command": None if s0 is None else s0["command"],
            },
            "source_at_start": source_start,
            "source_at_end": source_end,
            "stage": stage,
            "s0": s0,
            "error": error,
            "completion_elapsed_seconds": float(time.perf_counter() - started),
            "raw_artifacts": {
                name: _artifact(run_dir, name) for name in H2B_S0_ARTIFACT_NAMES
            },
        }
    )
    _write_json(run_dir / "h2b_s0_watchdog_summary.json", payload)
    return 0 if payload["status"] == "pass" else 1


def _s0_artifacts_match(run_dir: Path, recorded: Any) -> bool:
    if not isinstance(recorded, Mapping) or set(recorded) != set(H2B_S0_ARTIFACT_NAMES):
        return False
    for name in H2B_S0_ARTIFACT_NAMES:
        actual = _artifact(run_dir, name)
        if actual.get("present") is not True or recorded.get(name) != actual:
            return False
    return True


def _s0_controlled_missing_summary(run_dir: Path, watchdog: Mapping[str, Any]) -> dict[str, Any] | None:
    if (
        watchdog.get("schema") != H2B_S0_WATCHDOG_SCHEMA
        or not _evidence_valid(watchdog)
        or (run_dir / "s0_summary.json").is_file()
    ):
        return None
    s0 = watchdog.get("s0")
    termination = s0.get("termination") if isinstance(s0, Mapping) else None
    if not isinstance(termination, Mapping):
        return None
    try:
        timeline = _timeline_metrics(run_dir / "s0_timeline.jsonl", "s0")
    except _worker_error_types():
        return None
    peak = int(timeline["peak_rss_bytes"])
    swap = int(timeline["swap_bytes"])
    reason = termination.get("reason")
    resource_stop = peak >= H2B_S0_RSS_LIMIT_BYTES or swap > H2B_SWAP_LIMIT_BYTES
    status = "STOP_RESOURCE" if resource_stop else "STOP_ANOMALY"
    return {
        "schema": H2B_S0_CHECK_SCHEMA,
        "status": status,
        "pass": False,
        "route": status,
        "s0_direction_gate_pass": False,
        "problems": [
            "s0_summary_missing",
            "s0_resource_termination" if resource_stop else "s0_timeout_or_termination",
        ],
        "checks": {
            "watchdog_evidence": True,
            "s0_termination": True,
            "timeline": True,
            "resource": resource_stop,
            "online_measurement_formed": False,
        },
        "measurements": None,
        "failure_measurements": {
            "resource": {
                "process_tree_peak_rss_bytes": peak,
                "process_tree_swap_bytes": swap,
                "process_tree_peak_scope": "whole_s0_online_campaign",
                "live_sample_count": timeline["live_sample_count"],
            },
            "termination": termination,
            "termination_reason": reason,
            "s0_process": s0,
            "online_measurement_formed": False,
            "raw_artifacts": watchdog.get("raw_artifacts"),
            "watchdog_summary_sha256": _sha256_file(run_dir / "h2b_s0_watchdog_summary.json"),
        },
    }


def _s0_terminal_exit_race_adjudication(
    run_dir: Path,
    watchdog: Mapping[str, Any],
    stage: Mapping[str, Any],
    worker: Mapping[str, Any],
    checks: Mapping[str, Any],
    timeline: Mapping[str, Any],
    checker_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Adjudicate only the already-recorded S0 terminal-exit race."""

    required_checks = (
        "watchdog_evidence",
        "worker_evidence",
        "worker_status",
        "source",
        "runtime",
        "phase_identity",
        "stage_identity",
        "watchdog_identity",
        "authority",
        "forms",
        "commands",
        "cache_hit",
        "stage_manifest",
        "run_dir",
        "progress",
        "watchdog_artifacts",
        "stage_resource",
        "stage_lifecycle",
        "resource",
        "p6",
        "factor_authority",
        "strategy_order",
        "combinations_valid",
    )
    failed = [name for name in required_checks if checks.get(name) is not True]
    s0 = watchdog.get("s0")
    termination = s0.get("termination") if isinstance(s0, Mapping) else None
    nested = termination.get("termination") if isinstance(termination, Mapping) else None
    termination_ok = bool(
        isinstance(termination, Mapping)
        and termination.get("reason") == "process_tree_unreadable"
        and isinstance(nested, Mapping)
        and nested.get("requested") is True
        and nested.get("worker_exited") is True
        and nested.get("sigkill_required") is False
    )
    source_ok = bool(
        _source_pair_valid(worker.get("source_at_start"), worker.get("source_at_end"))
        and _source_pair_valid(stage.get("source_at_start"), stage.get("source_at_end"))
        and _source_pair_valid(watchdog.get("source_at_start"), watchdog.get("source_at_end"))
        and watchdog.get("source_at_start") == worker.get("source_at_start")
        and stage.get("source_at_start") == worker.get("source_at_start")
    )
    if not source_ok:
        failed.append("source_pair")
    if watchdog.get("status") != "gate_failed":
        failed.append("raw_watchdog_status")
    if watchdog.get("error") is not None:
        failed.append("watchdog_error")
    worker_elapsed = worker.get("elapsed_wall_seconds")
    terminal_elapsed = timeline.get("terminal_elapsed_seconds") if isinstance(timeline, Mapping) else None
    time_closed = bool(
        isinstance(worker_elapsed, (int, float))
        and not isinstance(worker_elapsed, bool)
        and math.isfinite(float(worker_elapsed))
        and float(worker_elapsed) > 0.0
        and isinstance(terminal_elapsed, (int, float))
        and not isinstance(terminal_elapsed, bool)
        and math.isfinite(float(terminal_elapsed))
        and float(terminal_elapsed) >= float(worker_elapsed)
    )
    if not time_closed:
        failed.append("terminal_time_after_worker_summary")
    if not (
        isinstance(stage, Mapping)
        and stage.get("status") == "measurement_complete"
        and _evidence_valid(stage)
    ):
        failed.append("stage_complete")
    if not _s0_stage_lifecycle_valid(watchdog.get("stage")):
        failed.append("stage_lifecycle")
    if not (
        watchdog.get("schema") == H2B_S0_WATCHDOG_SCHEMA
        and _evidence_valid(watchdog)
    ):
        failed.append("watchdog_complete")
    if not (
        isinstance(worker, Mapping)
        and worker.get("status") == "measurement_complete"
        and worker.get("error") is None
        and _evidence_valid(worker)
    ):
        failed.append("worker_complete")
    processes_gone = bool(isinstance(s0, Mapping) and _processes_gone(s0))
    if not (
        isinstance(s0, Mapping)
        and type(s0.get("return_code")) is int
        and s0.get("return_code") == 0
        and termination_ok
        and processes_gone
    ):
        failed.append("worker_processes_gone")
    if not (
        isinstance(timeline, Mapping)
        and timeline.get("legacy_terminal_exit") is True
        and isinstance(timeline.get("live_sample_count"), int)
        and timeline["live_sample_count"] > 0
    ):
        failed.append("timeline_terminal_exit")
    terminal_pids = timeline.get("terminal_pids") if isinstance(timeline, Mapping) else None
    observed_pids = s0.get("observed_process_tree_pids") if isinstance(s0, Mapping) else None
    root_pid = timeline.get("root_pid") if isinstance(timeline, Mapping) else None
    terminal_pid_binding = bool(
        isinstance(terminal_pids, list)
        and terminal_pids
        and all(type(pid) is int and pid > 0 for pid in terminal_pids)
        and isinstance(observed_pids, list)
        and all(type(pid) is int and pid > 0 for pid in observed_pids)
        and type(root_pid) is int
        and root_pid > 0
        and isinstance(s0, Mapping)
        and type(s0.get("root_pid")) is int
        and root_pid == s0.get("root_pid")
        and root_pid in terminal_pids
        and set(terminal_pids).issubset(observed_pids)
    )
    if not terminal_pid_binding:
        failed.append("terminal_pid_binding")
    if not _s0_artifacts_match(run_dir, watchdog.get("raw_artifacts")):
        failed.append("raw_artifacts")
    if not _checker_source_valid(checker_source):
        failed.append("checker_source")
    failed = sorted(set(failed))
    return {
        "value": not failed,
        "reason": "legacy_terminal_exit_race_recovered" if not failed else "legacy_terminal_exit_race_rejected",
        "failed_requirements": failed,
        "raw_watchdog_status": watchdog.get("status"),
        "termination_reason": (
            termination.get("reason") if isinstance(termination, Mapping) else None
        ),
        "live_sample_count": timeline.get("live_sample_count"),
        "terminal_elapsed_seconds": terminal_elapsed,
        "terminal_pids": timeline.get("terminal_pids"),
        "worker_elapsed_seconds": worker_elapsed,
        "processes_gone": processes_gone,
        "worker_return_code": s0.get("return_code") if isinstance(s0, Mapping) else None,
    }


def _s0_check_problems(
    checks: Mapping[str, Any], adjudication: Mapping[str, Any]
) -> list[str]:
    return sorted(
        name
        for name, passed in checks.items()
        if passed is not True
        and not (
            adjudication.get("value") is True
            and name == "watchdog_status"
        )
    )


def _run_s0_check(run_dir: Path, output: Path) -> int:
    try:
        run_dir = run_dir.resolve()
        watchdog = _read_json(run_dir / "h2b_s0_watchdog_summary.json")
        if not (run_dir / "s0_summary.json").is_file():
            controlled = _s0_controlled_missing_summary(run_dir, watchdog)
            if controlled is not None:
                _write_json(output.resolve(), _attach_evidence(controlled))
                print(f"H2B-S0 check status={controlled['status']} output={output.resolve()}", flush=True)
                return 1
        stage = _read_json(run_dir / "stage_summary.json")
        worker = _read_json(run_dir / "s0_summary.json")
        stage_timeline = _timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")
        terminal_exit_race = False
        try:
            timeline = _timeline_metrics(run_dir / "s0_timeline.jsonl", "s0")
        except ValueError:
            timeline = _s0_legacy_terminal_exit_timeline(run_dir / "s0_timeline.jsonl")
            terminal_exit_race = True
        measurement = worker.get("measurement")
        raw = {
            "scope": worker.get("scope"),
            "identity": worker.get("identity"),
            "p6": None if not isinstance(measurement, Mapping) else measurement.get("p6"),
            "factor": None if not isinstance(measurement, Mapping) else measurement.get("factor"),
            "combinations": None if not isinstance(measurement, Mapping) else measurement.get("combinations"),
            "resource": {
                "process_tree_peak_rss_bytes": timeline["peak_rss_bytes"],
                "process_tree_swap_bytes": timeline["swap_bytes"],
                "scope": "whole_s0_online_campaign",
            },
        }
        result = _s0_check_payload(raw)
        checks = result["checks"]
        authority_error: str | None = None
        try:
            authority = _authority()
        except _worker_error_types() as exc:
            authority = {}
            authority_error = f"{type(exc).__name__}: {exc}"
        stage_process = watchdog.get("stage")
        s0_process = watchdog.get("s0")
        worker_source = worker.get("source_at_start")
        try:
            checker_source = _light_source()
        except _worker_error_types():
            checker_source = None
        command_identity = watchdog.get("command_identity")
        executable = command_identity.get("python") if isinstance(command_identity, Mapping) else None
        compact_authority = {
            "source_commit_full_sha": (
                worker_source.get("source_commit_full_sha")
                if isinstance(worker_source, Mapping)
                else None
            ),
            "producer_source_commit_full_sha": (
                worker_source.get("source_commit_full_sha")
                if isinstance(worker_source, Mapping)
                else None
            ),
            "checker_source_commit_full_sha": (
                checker_source.get("source_commit_full_sha")
                if isinstance(checker_source, Mapping)
                else None
            ),
            "checker_source": checker_source,
            "factor_manifest_sha256": authority.get("factor_manifest_sha256"),
            "r2_record_sha256": authority.get("r2_record_sha256"),
            "r2_record_evidence_sha256": authority.get("r2_evidence_sha256"),
            "producer_authority": worker.get("producer_authority"),
            "b0_form": worker.get("form"),
            "raw_artifacts": watchdog.get("raw_artifacts"),
            "watchdog_summary_sha256": _sha256_file(run_dir / "h2b_s0_watchdog_summary.json"),
        }
        adjudication = {
            "value": False,
            "reason": "not_applicable",
            "failed_requirements": [],
            "raw_watchdog_status": watchdog.get("status"),
        }
        checks.update(
            {
                "watchdog_evidence": watchdog.get("schema") == H2B_S0_WATCHDOG_SCHEMA and _evidence_valid(watchdog),
                "worker_evidence": worker.get("schema") == H2B_S0_WORKER_SCHEMA and worker.get("phase") == "s0" and _evidence_valid(worker),
                "worker_status": worker.get("status") == "measurement_complete" and worker.get("error") is None,
                "watchdog_status": watchdog.get("status") == "pass",
                "source": (
                    _source_pair_valid(worker.get("source_at_start"), worker.get("source_at_end"))
                    and _source_pair_valid(stage.get("source_at_start"), stage.get("source_at_end"))
                    and _source_pair_valid(watchdog.get("source_at_start"), watchdog.get("source_at_end"))
                    and watchdog.get("source_at_start") == worker.get("source_at_start")
                    and stage.get("source_at_start") == worker.get("source_at_start")
                ),
                "runtime": (
                    _runtime_valid(stage.get("runtime_identity"))
                    and _runtime_valid(worker.get("runtime_identity"))
                    and stage.get("runtime_identity") == worker.get("runtime_identity")
                ),
                "phase_identity": worker.get("phase_identity")
                == _phase_identity(jit_api=True, compile_called=False, compiler_probe=False),
                "stage_identity": (
                    stage.get("scope") == _fixed_scope()
                    and stage.get("identity") == _fixed_identity()
                    and stage.get("phase_identity")
                    == _phase_identity(jit_api=True, compile_called=True, compiler_probe=True)
                ),
                "watchdog_identity": (
                    watchdog.get("scope") == _s0_scope()
                    and watchdog.get("identity") == _fixed_identity()
                ),
                "authority": (
                    authority_error is None
                    and worker.get("producer_authority") == authority.get("producer_authority")
                    and worker.get("factor_manifest_sha256") == authority.get("factor_manifest_sha256")
                    and worker.get("factor_manifest") == str(H2B_R2_MANIFEST)
                ),
                "forms": _forms_match(stage.get("form"), worker.get("form"), run_dir),
                "commands": (
                    isinstance(command_identity, Mapping)
                    and isinstance(executable, str)
                    and command_identity.get("launch_mode") == "direct_singleton"
                    and command_identity.get("stage_command")
                    == _worker_command(executable, "jit-worker", run_dir)
                    and command_identity.get("s0_command")
                    == _worker_command(executable, "s0-worker", run_dir)
                ),
                "cache_hit": (
                    isinstance(measurement, Mapping)
                    and isinstance(measurement.get("cache"), Mapping)
                    and measurement["cache"].get("unchanged") is True
                    and measurement["cache"].get("form_jit_cache_hit") is True
                    and measurement["cache"].get("c_source_regeneration") is False
                    and measurement["cache"].get("compiler_descendant_pids") == []
                    and isinstance(worker.get("form"), Mapping)
                    and worker["form"].get("code_state") == "hit_no_new_decl_impl"
                ),
                "stage_manifest": (
                    isinstance(measurement, Mapping)
                    and measurement.get("stage_manifest_sha256") == _sha256_file(run_dir / "stage_summary.json")
                    and measurement.get("r2_manifest_sha256") == authority.get("factor_manifest_sha256")
                ),
                "run_dir": watchdog.get("run_dir") == str(run_dir),
                "progress": _progress_events(run_dir / "s0_progress.jsonl", "s0") == list(H2B_S0_EVENTS),
                "watchdog_artifacts": _s0_artifacts_match(run_dir, watchdog.get("raw_artifacts")),
                "stage_resource": stage_timeline["peak_rss_bytes"] < H2B_STAGE_RSS_LIMIT_BYTES and stage_timeline["swap_bytes"] == 0,
                "stage_lifecycle": _s0_stage_lifecycle_valid(stage_process),
                "s0_lifecycle": (
                    isinstance(s0_process, Mapping)
                    and type(s0_process.get("return_code")) is int
                    and s0_process.get("return_code") == 0
                    and s0_process.get("termination") is None
                    and s0_process.get("processes_gone_after_s0") is True
                ),
                "checker_source": (
                    _checker_source_valid(checker_source)
                ),
            }
        )
        if terminal_exit_race:
            adjudication = _s0_terminal_exit_race_adjudication(
                run_dir,
                watchdog,
                stage,
                worker,
                checks,
                timeline,
                checker_source,
            )
            checks["terminal_exit_race_adjudication"] = adjudication["value"]
            if adjudication["value"] is True:
                checks["s0_lifecycle"] = True
        checks["lifecycle"] = checks["stage_lifecycle"] and checks["s0_lifecycle"]
        if not terminal_exit_race:
            checks["terminal_exit_race_adjudication"] = True
        compact_authority["adjudication"] = adjudication
        problems = _s0_check_problems(checks, adjudication)
        result["problems"] = problems
        if problems:
            result["pass"] = False
            nonresource_problems = [name for name in problems if name not in {"resource", "stage_resource"}]
            if nonresource_problems:
                result["status"] = "STOP_ANOMALY"
                result["route"] = "STOP_ANOMALY"
                result["s0_direction_gate_pass"] = False
            elif not checks["resource"] or not checks["stage_resource"]:
                result["status"] = "STOP_RESOURCE"
                result["route"] = "STOP_RESOURCE"
                result["s0_direction_gate_pass"] = False
            elif result["status"] == "pass":
                result["status"] = "STOP_ANOMALY"
                result["route"] = "STOP_ANOMALY"
                result["s0_direction_gate_pass"] = False
            result["failure_measurements"] = result.get("failure_measurements") or {
                "p6": raw["p6"],
                "factor": raw["factor"],
                "combinations": raw["combinations"],
                "resource": raw["resource"],
            }
            result["failure_measurements"]["authority"] = compact_authority
        else:
            result["measurements"]["combinations"] = _s0_project_campaign_sources(
                result["measurements"]["combinations"], raw["resource"]
            )
            result["measurements"]["source_identity"] = worker.get("source_at_start")
            result["measurements"]["authority"] = compact_authority
            result["measurements"]["resource"]["scope"] = "whole_s0_online_campaign"
            result["pass"] = True
            result["status"] = "pass"
    except _worker_error_types() as exc:
        result = {
            "schema": H2B_S0_CHECK_SCHEMA,
            "status": "gate_failed",
            "pass": False,
            "problems": [f"raw_unreadable:{type(exc).__name__}"],
        }
    _write_json(output.resolve(), _attach_evidence(result))
    print(f"H2B-S0 check status={result['status']} output={output.resolve()}", flush=True)
    return 0 if result["pass"] else 1


def _source_pair_valid(start: Any, end: Any) -> bool:
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        return False
    if start.get("source_commit_full_sha") != end.get("source_commit_full_sha"):
        return False
    return (
        start.get("tracked_source_dirty") is False
        and end.get("tracked_source_dirty") is False
        and start.get("source_worktree_dirty") is False
        and end.get("source_worktree_dirty") is False
        and start.get("nonignored_untracked_paths") == []
        and end.get("nonignored_untracked_paths") == []
    )


def _checker_source_valid(source: Any) -> bool:
    if not isinstance(source, Mapping):
        return False
    commit = source.get("source_commit_full_sha")
    return bool(
        isinstance(commit, str)
        and len(commit) == 40
        and commit.lower() == commit
        and all(char in _HEX for char in commit)
        and source.get("tracked_source_dirty") is False
        and source.get("source_worktree_dirty") is False
        and source.get("nonignored_untracked_paths") == []
        and source.get("worktree_status_porcelain") == []
        and source.get("git_error") is None
    )


def _runtime_valid(identity: Any) -> bool:
    if not isinstance(identity, Mapping):
        return False
    executable = identity.get("sys_executable")
    threads = identity.get("threads")
    return (
        identity.get("qualified_activation") == "1"
        and isinstance(executable, str)
        and Path(executable).is_absolute()
        and Path(executable).parent.name == "bin"
        and Path(executable).parent.parent.name == ".venv"
        and identity.get("petsc_scalar_type") in {"complex128", "<c16"}
        and identity.get("petsc_int_type") in {"int32", "<i4"}
        and isinstance(threads, Mapping)
        and all(threads.get(name) == "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"))
    )


def _progress_events(path: Path, phase: str) -> list[str]:
    events: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get("schema") != H2B_PROGRESS_SCHEMA or item.get("phase") != phase:
                raise ValueError(f"{phase} progress schema mismatch")
            events.append(str(item.get("event")))
    return events


def _timeline_sample_valid(item: Mapping[str, Any], readable: bool) -> bool:
    pids = item.get("pids")
    return bool(
        isinstance(item.get("root_pid"), int)
        and not isinstance(item["root_pid"], bool)
        and item["root_pid"] > 0
        and isinstance(pids, list)
        and all(isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 for pid in pids)
        and item["root_pid"] in pids
        and item.get("process_count") == len(pids)
        and isinstance(item.get("rss_bytes"), int)
        and not isinstance(item["rss_bytes"], bool)
        and item["rss_bytes"] >= 0
        and isinstance(item.get("swap_bytes"), int)
        and not isinstance(item["swap_bytes"], bool)
        and item["swap_bytes"] >= 0
        and item.get("all_status_readable") is readable
        and isinstance(item.get("compiler_descendant_pids"), list)
        and all(
            isinstance(pid, int)
            and not isinstance(pid, bool)
            and pid > 0
            for pid in item["compiler_descendant_pids"]
        )
    )


def _timeline_metrics(path: Path, phase: str) -> dict[str, Any]:
    live: list[dict[str, Any]] = []
    compiler: set[int] = set()
    terminal_seen = False
    terminal_sample: Mapping[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("schema") != H2B_PROGRESS_SCHEMA or item.get("phase") != phase:
            raise ValueError(f"{phase} timeline schema mismatch")
        if terminal_seen:
            raise ValueError(f"{phase} timeline has samples after terminal exit")
        if item.get("sample_kind") == "terminal_exit_unreadable":
            if (
                not _timeline_sample_valid(item, readable=False)
                or item.get("terminal_exit") is not True
                or item.get("formal_sample") is not False
                or not isinstance(item.get("return_code"), int)
                or isinstance(item.get("return_code"), bool)
                or not isinstance(item.get("elapsed_wall_seconds"), (int, float))
                or isinstance(item.get("elapsed_wall_seconds"), bool)
                or not math.isfinite(float(item["elapsed_wall_seconds"]))
                or float(item["elapsed_wall_seconds"]) <= 0.0
            ):
                raise ValueError(f"{phase} terminal timeline sample is invalid")
            terminal_seen = True
            terminal_sample = item
        elif item.get("sample_kind") == "worker":
            if not _timeline_sample_valid(item, readable=True):
                raise ValueError(f"{phase} timeline sample is unreadable")
            live.append(item)
            compiler.update(int(pid) for pid in item["compiler_descendant_pids"])
        else:
            raise ValueError(f"{phase} timeline sample kind is invalid")
    if not live:
        raise ValueError(f"{phase} timeline has no live sample")
    roots = {int(item["root_pid"]) for item in live}
    if len(roots) != 1:
        raise ValueError(f"{phase} timeline has multiple roots")
    root_pid = next(iter(roots))
    if terminal_sample is not None and terminal_sample["root_pid"] != root_pid:
        raise ValueError(f"{phase} terminal timeline root mismatch")
    metrics = {
        "live_sample_count": len(live),
        "peak_rss_bytes": max(int(item["rss_bytes"]) for item in live),
        "swap_bytes": max(int(item["swap_bytes"]) for item in live),
        "root_pid": root_pid,
        "compiler_descendant_pids": sorted(compiler),
    }
    if terminal_sample is not None:
        metrics.update(
            {
                "terminal_elapsed_seconds": float(terminal_sample["elapsed_wall_seconds"]),
                "terminal_pids": list(terminal_sample["pids"]),
            }
        )
    return metrics


def _s0_legacy_terminal_exit_timeline(path: Path) -> dict[str, Any]:
    """Read only the recorded S0 teardown-race shape from the first campaign."""

    items = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(items) < 2:
        raise ValueError("s0 legacy terminal-exit timeline is incomplete")
    for item in items:
        if item.get("schema") != H2B_PROGRESS_SCHEMA or item.get("phase") != "s0":
            raise ValueError("s0 legacy terminal-exit timeline schema mismatch")
    final = items[-1]
    legacy_terminal = (
        final.get("sample_kind") == "worker"
        and _timeline_sample_valid(final, readable=False)
    )
    if not legacy_terminal:
        raise ValueError("s0 legacy terminal-exit sample is missing or misplaced")
    terminal_elapsed = final.get("elapsed_wall_seconds")
    if (
        not isinstance(terminal_elapsed, (int, float))
        or isinstance(terminal_elapsed, bool)
        or not math.isfinite(float(terminal_elapsed))
        or float(terminal_elapsed) <= 0.0
    ):
        raise ValueError("s0 legacy terminal-exit time is invalid")
    live = items[:-1]
    if not all(
        item.get("sample_kind") == "worker"
        and _timeline_sample_valid(item, readable=True)
        for item in live
    ):
        raise ValueError("s0 legacy timeline has an earlier unreadable sample")
    roots = {int(item["root_pid"]) for item in live}
    if len(roots) != 1 or int(final["root_pid"]) not in roots:
        raise ValueError("s0 legacy terminal-exit timeline root mismatch")
    compiler = sorted(
        {
            int(pid)
            for item in live
            for pid in item["compiler_descendant_pids"]
        }
    )
    return {
        "live_sample_count": len(live),
        "peak_rss_bytes": max(int(item["rss_bytes"]) for item in live),
        "swap_bytes": max(int(item["swap_bytes"]) for item in live),
        "root_pid": roots.pop(),
        "compiler_descendant_pids": compiler,
        "legacy_terminal_exit": True,
        "terminal_sample_kind": final.get("sample_kind"),
        "terminal_elapsed_seconds": float(terminal_elapsed),
        "terminal_pids": list(final["pids"]),
    }


def _authority() -> dict[str, Any]:
    """Read and validate the frozen R0/R1/R2 authority in a lazy path."""

    h2a = _lazy_h2a()
    r0 = h2a._r2_read_r0_authority()
    r1 = h2a._r2_read_r1_authority()
    if not H2B_R2_RECORD_PATH.is_file():
        raise ValueError("frozen H2A-R2 compact authority is missing or changed")
    record_sha256 = _sha256_file(H2B_R2_RECORD_PATH)
    if record_sha256 != H2B_R2_RECORD_SHA256:
        raise ValueError("frozen H2A-R2 compact authority is missing or changed")
    record = _read_json(H2B_R2_RECORD_PATH)
    if record.get("evidence_sha256") != H2B_R2_RECORD_EVIDENCE_SHA256 or not _evidence_valid(record):
        raise ValueError("frozen H2A-R2 compact evidence is invalid")
    if not H2B_R2_MANIFEST.is_file():
        raise ValueError("frozen H2A-R2 factor manifest is missing or changed")
    manifest_sha256 = _sha256_file(H2B_R2_MANIFEST)
    if manifest_sha256 != H2B_R2_MANIFEST_SHA256:
        raise ValueError("frozen H2A-R2 factor manifest is missing or changed")
    manifest = _read_json(H2B_R2_MANIFEST)
    record_source = record.get("measurements", {}).get("source_commit_full_sha")
    manifest_source = manifest.get("metadata", {}).get("source_identity", {}).get(
        "source_commit_full_sha"
    )
    if record_source != H2B_R2_PRODUCER_SOURCE_SHA or manifest_source != record_source:
        raise ValueError("R2 producer source identity is not closed")
    factor = record.get("measurements", {}).get("factor")
    if not isinstance(factor, Mapping) or factor.get("cell_count") != H2B_FIXED_CELLS or factor.get("class_count") != H2B_FIXED_CLASSES or factor.get("unique_factor_count") != H2B_FIXED_FACTORS or factor.get("retained_payload_bytes") != 201_933_812:
        raise ValueError("frozen H2A-R2 factor authority is incomplete")
    return {
        "r0": r0,
        "r1": r1,
        "r2_record_sha256": record_sha256,
        "r2_evidence_sha256": H2B_R2_RECORD_EVIDENCE_SHA256,
        "factor_manifest_sha256": manifest_sha256,
        "producer_authority": {
            "r0_source": "b7eef17f10655be99f5bba072f9a547ae05f17ac",
            "r1_source": "107a3ac1ea01ab0cfdd450a268789890ef76e030",
            "r2_producer_source_full_sha": record_source,
            "r2_record_sha256": record_sha256,
            "r2_record_evidence_sha256": H2B_R2_RECORD_EVIDENCE_SHA256,
            "r2_factor_manifest_sha256": manifest_sha256,
        },
        "factor": dict(factor),
    }


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and value.lower() == value and all(char in _HEX for char in value)


def _check_sources(sources: Any) -> dict[str, bool]:
    checks = {label: False for label in H2B_SOURCE_LABELS}
    if not isinstance(sources, list) or [item.get("label") for item in sources if isinstance(item, Mapping)] != list(H2B_SOURCE_LABELS):
        return checks
    for item in sources:
        label = item["label"]
        definition = item.get("definition")
        num = item.get("independent_residual_numerator")
        den = item.get("independent_residual_denominator")
        rho = item.get("rho")
        timings = item.get("apply_seconds")
        full_norm = item.get("full_space_norm")
        hashes = (
            item.get("vector_sha256"),
            item.get("correction_sha256"),
            item.get("repeat_correction_sha256"),
            item.get("residual_sha256"),
            item.get("repeat_residual_sha256"),
        )
        checks[label] = (
            definition == H2B_SOURCE_DEFINITIONS[label]
            and item.get("definition_sha256") == _source_definition_sha(label)
            and all(_valid_hash(value) for value in hashes)
            and isinstance(full_norm, (int, float))
            and not isinstance(full_norm, bool)
            and math.isfinite(float(full_norm))
            and float(full_norm) > 0.0
            and item.get("finite") is True
            and item.get("rho_norm_scope") == "all_fullspace_rows"
            and item.get("external_slave_mask") is False
            and item.get("correction_sha256") == item.get("repeat_correction_sha256")
            and item.get("residual_sha256") == item.get("repeat_residual_sha256")
            and isinstance(num, (int, float)) and not isinstance(num, bool) and math.isfinite(float(num)) and float(num) >= 0.0
            and isinstance(den, (int, float)) and not isinstance(den, bool) and math.isfinite(float(den)) and float(den) > 0.0
            and float(full_norm) == float(den)
            and isinstance(rho, (int, float)) and not isinstance(rho, bool) and math.isfinite(float(rho))
            and float(rho) >= 0.0
            and math.isclose(float(rho), float(num) / float(den), rel_tol=1.0e-12, abs_tol=1.0e-15)
            and float(rho) <= H2B_RHO_LIMITS[label]
            and isinstance(item.get("independent_action_relative_error"), (int, float))
            and not isinstance(item.get("independent_action_relative_error"), bool)
            and math.isfinite(float(item["independent_action_relative_error"]))
            and 0.0 <= float(item["independent_action_relative_error"]) <= 1.0e-11
            and isinstance(timings, list)
            and len(timings) == 2
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0.0
                for value in timings
            )
        )
    return checks


def _core_identity_closed(smoother: Mapping[str, Any]) -> bool:
    core_identity = smoother.get("identity")
    expected = {
        "fine_space": "uncondensed_fullspace",
        "condensation": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "B2_B4_local_krylov_used": False,
        "fullspace_patch_pc_used": True,
        "interior_recovery_required": False,
        "ordinary_default_changed": False,
    }
    return isinstance(core_identity, Mapping) and all(
        core_identity.get(key) == value for key, value in expected.items()
    )


def _factor_work_closed(factor: Any, smoother: Any) -> bool:
    if not isinstance(factor, Mapping) or not isinstance(smoother, Mapping):
        return False
    integer_fields = (
        (factor.get("class_count"), H2B_FIXED_CLASSES),
        (factor.get("cell_count"), H2B_FIXED_CELLS),
        (factor.get("unique_factor_count"), H2B_FIXED_FACTORS),
        (factor.get("factor_plus_metadata_bytes"), 201_933_812),
        (smoother.get("factor_payload_bytes"), 201_933_812),
        (smoother.get("apply_count"), 10),
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value != expected
        for value, expected in integer_fields
    ):
        return False
    for value in (smoother.get("factor_plus_work_bytes"),):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
    if smoother.get("factor_plus_work_bytes") > H2B_FACTOR_WORK_LIMIT_BYTES:
        return False
    for key in ("factorization_residual_max", "solve_residual_max"):
        value = factor.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not math.isfinite(float(value)) or float(value) < 0.0 or float(value) > 1.0e-10:
            return False
    if factor.get("finite") is not True or factor.get("deterministic") is not True:
        return False
    expected_actions = smoother.get("expected_action_count")
    return (
        isinstance(expected_actions, int)
        and not isinstance(expected_actions, bool)
        and expected_actions > 0
        and smoother.get("action_count") == expected_actions
        and smoother.get("total_action_count") == 10 * expected_actions
    )


def _materialization_closed(smoother: Any) -> bool:
    if not isinstance(smoother, Mapping) or not _core_identity_closed(smoother):
        return False
    if smoother.get("global_row_count") != H2B_FIXED_ROWS:
        return False
    materialization = smoother.get("materialization_identity")
    forbidden = (
        "global_matrix_materialized",
        "global_constraint_matrix_materialized",
        "cell_schur_matrix_materialized",
        "slab_matrix_materialized",
        "schur_materialized",
        "per_cell_factor",
        "per_cell_dense_c",
        "ksp_created",
        "dtn_used",
        "pde_solve_called",
    )
    return isinstance(materialization, Mapping) and all(
        materialization.get(key) is False for key in forbidden
    )


def _check_raw(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    watchdog = _read_json(run_dir / "h2b_watchdog_summary.json")
    stage = _read_json(run_dir / "stage_summary.json")
    online = _read_json(run_dir / "online_summary.json")
    authority = _authority()
    problems: list[str] = []
    checks: dict[str, bool] = {}
    checks["watchdog_evidence"] = watchdog.get("schema") == H2B_WATCHDOG_SCHEMA and _evidence_valid(watchdog)
    checks["stage_evidence"] = stage.get("schema") == H2B_WORKER_SCHEMA and stage.get("phase") == "stage" and _evidence_valid(stage)
    checks["online_evidence"] = online.get("schema") == H2B_WORKER_SCHEMA and online.get("phase") == "online" and _evidence_valid(online)
    checks["status"] = watchdog.get("status") == "pass" and stage.get("status") == "measurement_complete" and online.get("status") == "measurement_complete"
    checks["scope"] = watchdog.get("scope") == _fixed_scope() and stage.get("scope") == _fixed_scope() and online.get("scope") == _fixed_scope()
    checks["identity"] = watchdog.get("identity") == _fixed_identity() and stage.get("identity") == _fixed_identity() and online.get("identity") == _fixed_identity()
    checks["phase_identity"] = stage.get("phase_identity") == _phase_identity(jit_api=True, compile_called=True, compiler_probe=True) and online.get("phase_identity") == _phase_identity(jit_api=True, compile_called=False, compiler_probe=False)
    checks["runtime"] = _runtime_valid(stage.get("runtime_identity")) and _runtime_valid(online.get("runtime_identity")) and stage.get("runtime_identity") == online.get("runtime_identity")
    checks["source"] = _source_pair_valid(stage.get("source_at_start"), stage.get("source_at_end")) and _source_pair_valid(online.get("source_at_start"), online.get("source_at_end")) and stage.get("source_at_start") == online.get("source_at_start")
    checks["watchdog_source"] = _source_pair_valid(watchdog.get("source_at_start"), watchdog.get("source_at_end")) and watchdog.get("source_at_start") == stage.get("source_at_start")
    checks["run_dir"] = watchdog.get("run_dir") == str(run_dir)
    command_identity = watchdog.get("command_identity")
    checks["commands"] = (
        isinstance(command_identity, Mapping)
        and command_identity.get("launch_mode") == "direct_singleton"
        and command_identity.get("python") == stage.get("runtime_identity", {}).get("sys_executable")
        and command_identity.get("stage_command") == _worker_command(command_identity.get("python"), "jit-worker", run_dir)
        and command_identity.get("online_command") == _worker_command(command_identity.get("python"), "online-worker", run_dir)
    ) if isinstance(command_identity, Mapping) and isinstance(command_identity.get("python"), str) else False
    checks["authority"] = (
        online.get("producer_authority") == authority.get("producer_authority")
        and online.get("factor_manifest_sha256") == authority.get("factor_manifest_sha256")
        and online.get("factor_manifest") == str(H2B_R2_MANIFEST)
    )
    checks["current_online_source"] = (
        online.get("current_online_source") == online.get("source_at_start")
    )
    checks["stage_events"] = _progress_events(run_dir / "stage_progress.jsonl", "stage") == list(H2B_STAGE_EVENTS)
    checks["online_events"] = _progress_events(run_dir / "online_progress.jsonl", "online") == list(H2B_ONLINE_EVENTS)
    stage_timeline = _timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")
    online_timeline = _timeline_metrics(run_dir / "online_timeline.jsonl", "online")
    checks["stage_resource"] = stage_timeline["peak_rss_bytes"] < H2B_STAGE_RSS_LIMIT_BYTES and stage_timeline["swap_bytes"] == 0
    checks["online_resource"] = online_timeline["peak_rss_bytes"] < H2B_ONLINE_RSS_LIMIT_BYTES and online_timeline["swap_bytes"] == 0 and online_timeline["compiler_descendant_pids"] == []
    checks["serial_lifecycle"] = watchdog.get("stage", {}).get("return_code") == 0 and watchdog.get("online", {}).get("return_code") == 0 and watchdog.get("stage", {}).get("processes_gone_before_online") is True and watchdog.get("online", {}).get("termination") is None
    p6 = online.get("measurement", {}).get("p6")
    expected_p6 = {
        "global_cells": H2B_FIXED_CELLS,
        "local_cells": H2B_FIXED_CELLS,
        "local_nloc": H2B_FIXED_NLOC,
        "global_rows": H2B_FIXED_ROWS,
        "constraint_count": H2B_FIXED_CONSTRAINTS,
    }
    checks["p6_measurement"] = isinstance(p6, Mapping) and all(
        type(p6.get(key)) is int and p6.get(key) == value
        for key, value in expected_p6.items()
    )
    measurement = online.get("measurement")
    if isinstance(measurement, Mapping):
        cache = measurement.get("cache")
        checks["cache_hit"] = isinstance(cache, Mapping) and cache.get("unchanged") is True and cache.get("form_jit_cache_hit") is True and cache.get("c_source_regeneration") is False and cache.get("compiler_descendant_pids") == [] and isinstance(online.get("form"), Mapping) and online["form"].get("code_state") == "hit_no_new_decl_impl"
    else:
        checks["cache_hit"] = False
    checks["manifest_binding"] = (
        isinstance(measurement, Mapping)
        and measurement.get("stage_manifest_sha256") == _sha256_file(run_dir / "stage_summary.json")
        and measurement.get("r2_manifest_sha256") == authority.get("factor_manifest_sha256")
    )
    checks["forms"] = _forms_match(stage.get("form"), online.get("form"), run_dir)
    factor = online.get("factor_audit")
    smoother = online.get("smoother_audit")
    checks["factor_work"] = _factor_work_closed(factor, smoother)
    checks["materialization"] = _materialization_closed(smoother)
    source_checks = _check_sources(online.get("sources"))
    checks["sources"] = all(source_checks.values())
    timing = measurement.get("timing") if isinstance(measurement, Mapping) else None
    if isinstance(timing, Mapping):
        warm = timing.get("warm_action_seconds")
        actions = timing.get("volume_action_seconds")
        applies = timing.get("smoother_apply_seconds")
        finite_positive = lambda values: (
            isinstance(values, list)
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0.0
                for value in values
            )
        )
        action_median = statistics.median(actions) if finite_positive(actions) and len(actions) == 5 else None
        smoother_median = statistics.median(applies) if finite_positive(applies) and len(applies) == 10 else None
        source_timings = online.get("sources")
        flattened = (
            [value for item in source_timings for value in item.get("apply_seconds", [])]
            if isinstance(source_timings, list)
            and len(source_timings) == len(H2B_SOURCE_LABELS)
            and all(isinstance(item, Mapping) for item in source_timings)
            else None
        )
        ratio = timing.get("smoother_action_ratio")
        checks["timing"] = (
            isinstance(warm, (int, float))
            and not isinstance(warm, bool)
            and math.isfinite(float(warm))
            and float(warm) > 0.0
            and action_median is not None
            and smoother_median is not None
            and timing.get("action_median_seconds") == action_median
            and timing.get("smoother_median_seconds") == smoother_median
            and isinstance(ratio, (int, float))
            and not isinstance(ratio, bool)
            and math.isfinite(float(ratio))
            and float(ratio) == float(smoother_median / action_median)
            and float(ratio) <= 30.0
            and flattened == applies
        )
    else:
        checks["timing"] = False
    artifact_names = ("stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json", "stage_timeline.jsonl", "online_progress.jsonl", "online_stdout.txt", "online_summary.json", "online_timeline.jsonl", "stage_root_pid.json", "online_root_pid.json")
    actual_artifacts = {name: _artifact(run_dir, name) for name in artifact_names}
    checks["raw_hashes"] = all(actual_artifacts[name].get("present") is True for name in artifact_names)
    recorded_artifacts = watchdog.get("raw_artifacts")
    checks["raw_artifact_binding"] = isinstance(recorded_artifacts, Mapping) and all(recorded_artifacts.get(name) == actual_artifacts[name] for name in artifact_names)
    problems.extend(name for name, passed in checks.items() if passed is not True)
    status = not problems
    artifacts = {name: _artifact(run_dir, name) for name in (*artifact_names, "h2b_watchdog_summary.json")}
    measurements = None
    if status:
        measurements = {
            "source_identity": online.get("source_at_start"),
            "producer_authority": online.get("producer_authority"),
            "p6": measurement.get("p6"),
            "sources": online.get("sources"),
            "factor": factor,
            "smoother": smoother,
            "timing": timing,
            "stage_process_tree_peak_rss_bytes": stage_timeline["peak_rss_bytes"],
            "online_process_tree_peak_rss_bytes": online_timeline["peak_rss_bytes"],
            "stage_swap_bytes": stage_timeline["swap_bytes"],
            "online_swap_bytes": online_timeline["swap_bytes"],
            "online_compiler_descendant_pids": online_timeline["compiler_descendant_pids"],
        }
    return {
        "schema": H2B_CHECK_SCHEMA,
        "status": "pass" if status else "gate_failed",
        "pass": status,
        "problems": sorted(problems),
        "checks": checks,
        "measurements": measurements,
        "raw_artifacts": artifacts,
        "authority": {
            "r2_record_sha256": authority.get("r2_record_sha256"),
            "r2_evidence_sha256": authority.get("r2_evidence_sha256"),
            "factor_manifest_sha256": authority.get("factor_manifest_sha256"),
        },
    }


def _controlled_stage_failure(run_dir: Path, cause: BaseException) -> dict[str, Any] | None:
    """Preserve a readable stage boundary when online was never launched."""

    run_dir = run_dir.resolve()
    stage_path = run_dir / "stage_summary.json"
    watchdog_path = run_dir / "h2b_watchdog_summary.json"
    if (run_dir / "online_summary.json").exists() or not stage_path.is_file() or not watchdog_path.is_file():
        return None
    try:
        stage = _read_json(stage_path)
        watchdog = _read_json(watchdog_path)
        stage_timeline = _timeline_metrics(run_dir / "stage_timeline.jsonl", "stage")
    except _worker_error_types():
        return None
    stage_evidence = (
        stage.get("schema") == H2B_WORKER_SCHEMA
        and stage.get("phase") == "stage"
        and _evidence_valid(stage)
    )
    watchdog_evidence = (
        watchdog.get("schema") == H2B_WATCHDOG_SCHEMA
        and _evidence_valid(watchdog)
    )
    if not stage_evidence or not watchdog_evidence:
        return None
    stage_error = stage.get("error")
    problems = ["stage_gate_failed_before_online", "online_not_run"]
    if isinstance(stage_error, str) and stage_error:
        problems.append(f"stage_error:{stage_error}")
    artifacts = {
        name: _artifact(run_dir, name)
        for name in (
            "stage_progress.jsonl",
            "stage_stdout.txt",
            "stage_summary.json",
            "stage_timeline.jsonl",
            "stage_root_pid.json",
            "online_progress.jsonl",
            "online_stdout.txt",
            "online_summary.json",
            "online_timeline.jsonl",
            "online_root_pid.json",
            "h2b_watchdog_summary.json",
        )
    }
    return {
        "schema": H2B_CHECK_SCHEMA,
        "status": "gate_failed",
        "pass": False,
        "problems": sorted(problems),
        "checks": {
            "stage_evidence": stage_evidence,
            "watchdog_evidence": watchdog_evidence,
            "stage_resource": (
                stage_timeline["peak_rss_bytes"] < H2B_STAGE_RSS_LIMIT_BYTES
                and stage_timeline["swap_bytes"] == 0
            ),
            "stage_source": _source_pair_valid(
                stage.get("source_at_start"), stage.get("source_at_end")
            ),
            "stage_runtime": _runtime_valid(stage.get("runtime_identity")),
            "online_not_run": True,
        },
        "measurements": None,
        "failure_measurements": {
            "stage": {
                "completion_elapsed_seconds": stage.get("elapsed_wall_seconds"),
                "process_tree_peak_rss_bytes": stage_timeline["peak_rss_bytes"],
                "process_tree_swap_bytes": stage_timeline["swap_bytes"],
                "live_sample_count": stage_timeline["live_sample_count"],
                "return_code": watchdog.get("stage", {}).get("return_code"),
                "termination": watchdog.get("stage", {}).get("termination"),
                "error": stage_error,
                "source_at_start": stage.get("source_at_start"),
                "source_at_end": stage.get("source_at_end"),
                "runtime_identity": stage.get("runtime_identity"),
            },
            "online_not_run": True,
            "checker_cause": f"{type(cause).__name__}: {cause}",
        },
        "raw_artifacts": artifacts,
        "authority": None,
    }


def _run_check(run_dir: Path, output: Path) -> int:
    try:
        result = _check_raw(run_dir)
    except _worker_error_types() as exc:
        result = _controlled_stage_failure(run_dir, exc)
        if result is None:
            result = {
                "schema": H2B_CHECK_SCHEMA,
                "status": "gate_failed",
                "pass": False,
                "problems": [f"raw_unreadable:{type(exc).__name__}"],
            }
    _write_json(output.resolve(), _attach_evidence(result))
    print(f"H2B check status={result['status']} output={output.resolve()}", flush=True)
    return 0 if result["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_task037_extra_h2b")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("jit-worker", _run_jit_worker),
        ("online-worker", _run_online_worker),
        ("s0-worker", _run_s0_worker),
    ):
        item = sub.add_parser(name)
        item.add_argument("--run-dir", required=True)
        item.set_defaults(handler=handler)
    watchdog = sub.add_parser("watchdog")
    watchdog.add_argument("--run-dir", required=True)
    watchdog.set_defaults(handler=_run_watchdog)
    s0_watchdog = sub.add_parser("s0-watchdog")
    s0_watchdog.add_argument("--run-dir", required=True)
    s0_watchdog.set_defaults(handler=_run_s0_watchdog)
    checker = sub.add_parser("check")
    checker.add_argument("--run-dir", required=True)
    checker.add_argument("--output", required=True)
    checker.set_defaults(handler=lambda args: _run_check(Path(args.run_dir), Path(args.output)))
    s0_checker = sub.add_parser("s0-check")
    s0_checker.add_argument("--run-dir", required=True)
    s0_checker.add_argument("--output", required=True)
    s0_checker.set_defaults(
        handler=lambda args: _run_s0_check(Path(args.run_dir), Path(args.output))
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"jit-worker", "online-worker", "s0-worker", "watchdog", "s0-watchdog"}:
        return int(args.handler(Path(args.run_dir)))
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
