#!/usr/bin/env python3
"""Build one immutable Task035e blind-trial identity from qualified inputs.

The caller supplies files, not trusted identity values.  This producer
independently replays the deterministic Path A/B initial space, checks the
qualified full-solve configuration against the fixed block grating, and
derives every mesh, degree, state, and physical-configuration digest used by
the blind controller.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence

from benchmarks.task034_case093 import (
    PHYSICAL_KEYS,
    _physical_identity as _case093_physical_identity,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    target_stage4_config,
)


ROOT = Path(__file__).resolve().parents[1]
TRIAL_METADATA_SCHEMA = "task035e.blind-trial-metadata.v2"
QUALIFIED_SOLVER_CONFIG_SCHEMA = (
    "task035e.blind-qualified-solver-config.v1"
)
TRIAL_METADATA_RECEIPT_SCHEMA = (
    "task035e.blind-trial-metadata-write-receipt.v1"
)
TRIAL_ALGORITHM_ID = "reference-blind-multilevel-hp-v1"
TRIAL_MAXIMUM_CYCLES = 6
FORMAL_MPI_SIZE = 8

_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PATH_H_NM = {"A": 20.0, "B": 15.0}
_TRIAL_ID = {
    "A": "task035e-blind-path-a",
    "B": "task035e-blind-path-b",
}
_INITIAL_PATH_ID = {
    "A": "path-A-h20",
    "B": "path-B-h15",
}
_FULL_SOLVE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
_FORBIDDEN_PATH_PARTS = frozenset(
    {
        "ref" + "erence",
        "hid" + "den",
        "ref" + "erence_certifier",
        "hid" + "den_auditor",
        "sealed_" + "reference",
        "sealed-" + "reference",
        "golden_" + "reference",
        "golden-" + "reference",
    }
)

_QUALIFIED_CONFIG_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "source_sha",
        "formal_mpi_size",
        "run_kind",
        "output_role",
        "cycle_index",
        "assembly_backend",
        "initial_plan_file_sha256",
        "source_clean_verified",
        "source_stable_during_run",
        "qualified_activation",
        "petsc_scalar_type",
        "petsc_int_type",
        "ordinary_default_changed",
        "config",
        "config_payload_sha256",
        "authority_payload_sha256",
    }
)
_TRIAL_METADATA_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "trial_id",
        "algorithm_id",
        "source_sha",
        "initial_path_id",
        "initial_mesh_forest_sha256",
        "initial_degree_map_sha256",
        "initial_state_sha256",
        "initial_plan_file_sha256",
        "initial_plan_payload_sha256",
        "initial_space_authority_file_sha256",
        "initial_space_authority_payload_sha256",
        "qualified_solver_config_file_sha256",
        "qualified_solver_config_payload_sha256",
        "geometry_sha256",
        "material_sha256",
        "incident_sha256",
        "dtn_definition_sha256",
        "postprocessing_sha256",
        "physical_identity_sha256",
        "formal_mpi_size",
        "maximum_cycles",
        "ordinary_default_changed",
        "metadata_payload_sha256",
    }
)

_GEOMETRY_CONFIG_KEYS = (
    "geometry_kind",
    "stage_case",
    "period_x",
    "period_y",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    "physical_z_min",
    "physical_z_max",
    "air_height",
    "substrate_thickness",
    "grating_height",
    "grating_width_x",
    "grating_width_y",
    "grating_bounds",
    "interface_z",
    "use_pml",
    "pml_top_thickness",
    "pml_bottom_thickness",
)
_MATERIAL_CONFIG_KEYS = (
    "lambda0",
    "n_air",
    "n_grating",
    "n_substrate",
    "eps_air",
    "eps_grating",
    "eps_substrate",
    "mu_r",
    "grating_material_label",
    "substrate_material_label",
)
_INCIDENT_CONFIG_KEYS = (
    "lambda0",
    "incident_theta_deg",
    "incident_phi_deg",
    "polarization_kind",
    "incident_amplitude",
    "incident_e0_v_per_m",
    "propagation_direction",
    "wavevector",
    "scattering_background",
)
_DTN_CONFIG_KEYS = (
    "stage4_boundary_model",
    "stage4_dtn_order_policy",
    "stage4_dtn_assembly",
    "stage4_pml_outer_bc",
    "use_floquet_xy",
    "period_x",
    "period_y",
    "floquet_phase_x",
    "floquet_phase_y",
    "physical_z_min",
    "physical_z_max",
    "n_air",
    "n_substrate",
    "diffraction_zero_order_only",
    "diffraction_order_max_m",
    "diffraction_order_max_n",
    "diffraction_rayleigh_tol",
)
_POSTPROCESS_CONFIG_KEYS = (
    "full3d_reference_export",
    "full3d_reference_plane_z",
    "full3d_reference_sample_count_x",
    "full3d_reference_sample_count_y",
    "diffraction_sample_count_x",
    "diffraction_sample_count_y",
    "diffraction_probe_fraction",
    "electric_field_unit",
    "magnetic_field_unit",
)
_NORMALIZATION_CONTRACT = {
    "schema_version": "task035e.fixed-order-normalization.v1",
    "amplitude_plane": "physical_boundary",
    "co_polarization_for_incident_S": "s",
    "cross_polarization_for_incident_S": "p",
    "total_power": "s_plus_p_power_ratio",
    "admittance": "s_beta_over_k0_mu_r",
    "far_field_power_applicability": "positive_outward_real_poynting",
}


class TrialMetadataError(ValueError):
    """Raised when blind-trial metadata cannot be derived fail-closed."""


@dataclass(frozen=True, slots=True)
class TrialMetadataWriteReceipt:
    """Identity of one immutable blind-trial metadata artifact."""

    path: Path
    file_sha256: str
    metadata_payload_sha256: str
    trial_id: str
    algorithm_id: str
    source_sha: str
    initial_path_id: str
    physical_identity_sha256: str


@dataclass(frozen=True, slots=True)
class QualifiedSolverConfigWriteReceipt:
    """Identity of one immutable qualified cycle-0 solver configuration."""

    path: Path
    file_sha256: str
    authority_payload_sha256: str
    config_payload_sha256: str
    source_sha: str
    initial_path_id: str
    initial_plan_file_sha256: str


def _reject_nonfinite(value: str) -> None:
    raise TrialMetadataError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrialMetadataError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _canonical(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _canonical_file_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _canonical(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_sha(value: Any) -> str:
    source = str(value)
    if _SOURCE_SHA_RE.fullmatch(source) is None:
        raise TrialMetadataError(
            "source_sha must be one lowercase full Git SHA"
        )
    return source


def _sha256(value: Any, *, label: str) -> str:
    digest = str(value)
    if _SHA256_RE.fullmatch(digest) is None:
        raise TrialMetadataError(f"{label} must be a lowercase SHA-256")
    return digest


def _exact(
    value: Any,
    keys: frozenset[str] | set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrialMetadataError(f"{label} must be one JSON object")
    if set(value) != set(keys):
        raise TrialMetadataError(
            f"{label} does not use its closed schema; "
            f"missing={sorted(set(keys) - set(value))}, "
            f"extra={sorted(set(value) - set(keys))}"
        )
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise TrialMetadataError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    lowered = {part.lower() for part in resolved.parts}
    if lowered.intersection(_FORBIDDEN_PATH_PARTS):
        raise TrialMetadataError(
            f"{label} crosses a protected evaluator layer"
        )
    return resolved


def _private_regular_file(path: Path, *, label: str) -> Path:
    resolved = _safe_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise TrialMetadataError(f"{label} is absent: {resolved}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise TrialMetadataError(f"{label} is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise TrialMetadataError(f"{label} must use mode 0600")
    return resolved


def _strict_private_json(
    path: Path,
    *,
    label: str,
) -> tuple[Path, Mapping[str, Any], str]:
    resolved = _private_regular_file(path, label=label)
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrialMetadataError(
            f"cannot read strict {label} JSON: {resolved}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise TrialMetadataError(f"{label} must be one JSON object")
    return resolved, payload, _file_sha256(resolved)


def _selected_config(
    config: Mapping[str, Any],
    keys: Sequence[str],
    *,
    label: str,
) -> dict[str, Any]:
    missing = [key for key in keys if key not in config]
    if missing:
        raise TrialMetadataError(
            f"{label} config is missing keys: {sorted(missing)}"
        )
    return {key: _canonical(config[key]) for key in keys}


def _expected_full_solve_config(*, path_id: str) -> Mapping[str, Any]:
    h_nm = _PATH_H_NM[path_id]
    cfg = replace(
        target_stage4_config(degree=6, h_nm=h_nm),
        polarization_kind="s",
        custom_polarization=None,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=True,
        full3d_reference_plane_z=_FULL_SOLVE_PLANES_NM,
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    )
    return cfg.as_jsonable()


_ABI_PREFLIGHT_KEYS = frozenset(
    {
        "schema_version",
        "pass",
        "activation_marker",
        "python_executable",
        "repo_venv_python",
        "sys_platform",
        "os_name",
        "petsc_scalar_type",
        "petsc_int_type",
        "dolfinx_scalar_type",
        "mpi4py_module_path",
        "petsc4py_module_path",
        "dolfinx_module_path",
        "mpi_comm_relation",
    }
)


def _linux_module_path(module: Any, *, label: str) -> str:
    raw = getattr(module, "__file__", None)
    if not isinstance(raw, str) or not raw:
        raise TrialMetadataError(f"{label} has no importable module path")
    resolved = Path(raw).resolve()
    rendered = resolved.as_posix()
    if (
        not resolved.is_absolute()
        or rendered == "/mnt"
        or rendered.startswith("/mnt/")
        or "\\" in raw
        or re.match(r"^[A-Za-z]:", raw) is not None
    ):
        raise TrialMetadataError(
            f"{label} is not loaded from the Linux ABI stack"
        )
    return rendered


def _qualified_abi_preflight() -> Mapping[str, Any]:
    """Inspect the live lightweight Python/MPI/PETSc/DOLFINx ABI stack."""

    try:
        import dolfinx
        import mpi4py
        import numpy as np
        import petsc4py
        from mpi4py import MPI
        from petsc4py import PETSc
    except ImportError as exc:
        raise TrialMetadataError(
            "qualified solver-config ABI imports failed"
        ) from exc

    try:
        relation = MPI.Comm.Compare(
            PETSc.COMM_WORLD.tompi4py(),
            MPI.COMM_WORLD,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise TrialMetadataError(
            "petsc4py and mpi4py communicators are not interoperable"
        ) from exc
    relation_name = {
        int(MPI.IDENT): "IDENT",
        int(MPI.CONGRUENT): "CONGRUENT",
    }.get(int(relation), f"OTHER:{int(relation)}")
    return {
        "schema_version": "task035e.qualified-linux-abi-preflight.v1",
        "pass": True,
        "activation_marker": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "python_executable": str(Path(sys.executable).resolve()),
        "repo_venv_python": str(
            (ROOT / ".venv" / "bin" / "python").resolve()
        ),
        "sys_platform": sys.platform,
        "os_name": os.name,
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "dolfinx_scalar_type": np.dtype(
            dolfinx.default_scalar_type
        ).name,
        "mpi4py_module_path": _linux_module_path(
            mpi4py,
            label="mpi4py",
        ),
        "petsc4py_module_path": _linux_module_path(
            petsc4py,
            label="petsc4py",
        ),
        "dolfinx_module_path": _linux_module_path(
            dolfinx,
            label="dolfinx",
        ),
        "mpi_comm_relation": relation_name,
    }


def _validated_abi_preflight(
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    row = _exact(
        payload,
        _ABI_PREFLIGHT_KEYS,
        label="qualified solver-config ABI preflight",
    )
    expected_python = str(
        (ROOT / ".venv" / "bin" / "python").resolve()
    )
    module_paths = tuple(
        str(row[name])
        for name in (
            "mpi4py_module_path",
            "petsc4py_module_path",
            "dolfinx_module_path",
        )
    )
    if (
        row["schema_version"]
        != "task035e.qualified-linux-abi-preflight.v1"
        or row["pass"] is not True
        or row["activation_marker"] != "1"
        or row["python_executable"] != expected_python
        or row["repo_venv_python"] != expected_python
        or row["sys_platform"] != "linux"
        or row["os_name"] != "posix"
        or row["petsc_scalar_type"] != "complex128"
        or row["petsc_int_type"] != "int32"
        or row["dolfinx_scalar_type"] != "complex128"
        or row["mpi_comm_relation"] not in {"IDENT", "CONGRUENT"}
        or any(
            not path.startswith("/")
            or path == "/mnt"
            or path.startswith("/mnt/")
            or "\\" in path
            or re.match(r"^[A-Za-z]:", path) is not None
            for path in module_paths
        )
    ):
        raise TrialMetadataError(
            "qualified activation/Linux complex128-int32 ABI gate failed"
        )
    return row


_GIT_SOURCE_STATE_KEYS = frozenset(
    {"repo_root", "head_sha", "status_lines"}
)


def _git_source_state() -> Mapping[str, Any]:
    """Read the source identity without acquiring an optional Git lock."""

    environment = dict(os.environ)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"

    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise TrialMetadataError(
                "read-only Git source probe failed"
                + (f": {detail}" if detail else "")
            )
        return completed.stdout

    root = run("rev-parse", "--show-toplevel").strip()
    head = run("rev-parse", "HEAD").strip()
    status = tuple(
        line
        for line in run(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).splitlines()
        if line
    )
    return {
        "repo_root": root,
        "head_sha": head,
        "status_lines": status,
    }


def _validated_git_source_state(
    payload: Mapping[str, Any],
    *,
    expected_source_sha: str,
    label: str,
) -> Mapping[str, Any]:
    row = _exact(
        payload,
        _GIT_SOURCE_STATE_KEYS,
        label=label,
    )
    status = row["status_lines"]
    if (
        Path(str(row["repo_root"])).resolve() != ROOT.resolve()
        or row["head_sha"] != expected_source_sha
        or not isinstance(status, (list, tuple))
        or any(not isinstance(item, str) for item in status)
        or len(status) != 0
    ):
        raise TrialMetadataError(
            f"{label} is not the requested clean source identity"
        )
    return {
        "repo_root": str(ROOT.resolve()),
        "head_sha": expected_source_sha,
        "status_lines": (),
    }


def _replay_initial_plan_for_config(
    *,
    initial_plan_path: Path,
    source_sha: str,
    path_id: str,
) -> tuple[Path, Mapping[str, Any], str]:
    resolved, plan, plan_file_sha = _strict_private_json(
        initial_plan_path,
        label="initial solver plan",
    )
    canonical = build_task035e_initial_space_plan(
        target_stage4_config(
            degree=6,
            h_nm=_PATH_H_NM[path_id],
        ),
        path_id=path_id,
        source_sha=source_sha,
        comm_size=FORMAL_MPI_SIZE,
    )
    expected = canonical.plan_payload()
    if dict(plan) != expected:
        raise TrialMetadataError(
            "initial solver plan does not replay for the requested "
            f"source/Path {path_id}"
        )
    if _json_sha256(plan) != canonical.audit["plan_payload_sha256"]:
        raise TrialMetadataError(
            "initial solver plan payload SHA-256 does not replay"
        )
    return resolved, plan, plan_file_sha


def _qualified_cycle0_config(
    *,
    path_id: str,
    initial_plan_path: Path,
) -> Mapping[str, Any]:
    cfg = replace(
        target_stage4_config(
            degree=6,
            h_nm=_PATH_H_NM[path_id],
        ),
        polarization_kind="s",
        custom_polarization=None,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        stage4_variable_p_cell_degree_plan=None,
        stage4_local_h_refinement_plan=str(
            initial_plan_path.resolve()
        ),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=True,
        full3d_reference_plane_z=_FULL_SOLVE_PLANES_NM,
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    )
    # This scope validator is pure: it proves that the selected backend has
    # exactly one real local-h/variable-p plan and a complete recovery solve.
    from src.common.config_3d import (
        qualify_stage4_full3d_assembly_backend,
    )

    backend = qualify_stage4_full3d_assembly_backend(cfg)
    if (
        backend.get("qualified_scope") is not True
        or backend.get("actual")
        != ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    ):
        raise TrialMetadataError(
            "cycle-0 variable-p backend scope did not qualify"
        )
    return cfg.as_jsonable()


def _component_identity(
    config: Mapping[str, Any],
    *,
    source_sha: str,
) -> dict[str, str]:
    geometry = _json_sha256(
        {
            "schema_version": "task035e.geometry-identity.v1",
            "config": _selected_config(
                config,
                _GEOMETRY_CONFIG_KEYS,
                label="geometry",
            ),
        }
    )
    material = _json_sha256(
        {
            "schema_version": "task035e.material-identity.v1",
            "config": _selected_config(
                config,
                _MATERIAL_CONFIG_KEYS,
                label="material",
            ),
        }
    )
    incident = _json_sha256(
        {
            "schema_version": "task035e.incident-identity.v1",
            "config": _selected_config(
                config,
                _INCIDENT_CONFIG_KEYS,
                label="incident",
            ),
        }
    )
    dtn = _json_sha256(
        {
            "schema_version": "task035e.dtn-identity.v1",
            "config": _selected_config(
                config,
                _DTN_CONFIG_KEYS,
                label="DtN",
            ),
            "normalization": _NORMALIZATION_CONTRACT,
        }
    )
    postprocess = _json_sha256(
        {
            "schema_version": "task035e.postprocessing-identity.v1",
            "config": _selected_config(
                config,
                _POSTPROCESS_CONFIG_KEYS,
                label="postprocess",
            ),
            "field_observations": {
                "interface": [
                    "E_t_interface_V_per_m",
                    "H_t_interface_A_per_m",
                ],
                "volume": ["E_V_per_m", "H_A_per_m"],
                "volume_plane_selection": "middle_plane_indices",
                "storage": "pointwise_complex_observations",
            },
        }
    )
    return {
        "geometry_sha256": geometry,
        "material_sha256": material,
        "incident_sha256": incident,
        "dtn_definition_sha256": dtn,
        "postprocessing_sha256": postprocess,
        "source_sha": source_sha,
    }


def _resolve_config_plan_path(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise TrialMetadataError(
            "qualified solver config has no local-h plan path"
        )
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def _validate_qualified_config(
    payload: Mapping[str, Any],
    *,
    expected_source_sha: str,
    expected_path_id: str,
    expected_plan_path: Path,
    expected_plan_file_sha256: str,
) -> tuple[Mapping[str, Any], str, dict[str, str]]:
    row = _exact(
        payload,
        _QUALIFIED_CONFIG_KEYS,
        label="qualified solver config authority",
    )
    unsigned = dict(row)
    observed_authority_sha = _sha256(
        unsigned.pop("authority_payload_sha256"),
        label="qualified solver config authority payload SHA-256",
    )
    if _json_sha256(unsigned) != observed_authority_sha:
        raise TrialMetadataError(
            "qualified solver config authority self-hash differs"
        )
    checks = (
        row["schema_version"] == QUALIFIED_SOLVER_CONFIG_SCHEMA,
        row["status"] == "qualified",
        row["pass"] is True,
        row["source_sha"] == expected_source_sha,
        row["formal_mpi_size"] == FORMAL_MPI_SIZE,
        row["run_kind"] == "full-solve",
        row["output_role"] == "blind_current_solve",
        row["cycle_index"] == 0,
        row["assembly_backend"]
        == ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
        row["initial_plan_file_sha256"] == expected_plan_file_sha256,
        row["source_clean_verified"] is True,
        row["source_stable_during_run"] is True,
        row["qualified_activation"] is True,
        row["petsc_scalar_type"] == "complex128",
        row["petsc_int_type"] == "int32",
        row["ordinary_default_changed"] is False,
    )
    if not all(checks):
        raise TrialMetadataError(
            "qualified solver config authority gate differs"
        )
    config = row["config"]
    if not isinstance(config, Mapping):
        raise TrialMetadataError(
            "qualified solver config payload must be one object"
        )
    config_sha = _json_sha256(config)
    if row["config_payload_sha256"] != config_sha:
        raise TrialMetadataError(
            "qualified solver config payload SHA-256 differs"
        )

    expected_config = _expected_full_solve_config(
        path_id=expected_path_id,
    )
    expected_case093 = _canonical(
        _case093_physical_identity(expected_config)
    )
    observed_case093 = _canonical(_case093_physical_identity(config))
    if set(PHYSICAL_KEYS) != set(expected_case093):
        raise AssertionError("Task034 physical-key contract drifted")
    if observed_case093 != expected_case093:
        raise TrialMetadataError(
            "solver physical configuration differs from the fixed grating"
        )
    for label, keys in (
        ("geometry", _GEOMETRY_CONFIG_KEYS),
        ("material", _MATERIAL_CONFIG_KEYS),
        ("incident", _INCIDENT_CONFIG_KEYS),
        ("DtN", _DTN_CONFIG_KEYS),
        ("postprocess", _POSTPROCESS_CONFIG_KEYS),
    ):
        if _selected_config(
            config,
            keys,
            label=label,
        ) != _selected_config(
            expected_config,
            keys,
            label=f"expected {label}",
        ):
            raise TrialMetadataError(
                f"solver {label} configuration is not the qualified target"
            )

    h_nm = config.get("mesh_target_size")
    if (
        isinstance(h_nm, bool)
        or not isinstance(h_nm, (int, float))
        or abs(float(h_nm) - _PATH_H_NM[expected_path_id]) > 1.0e-12
        or config.get("nedelec_degree") != 6
        or config.get("stage4_full3d_assembly_backend")
        != ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        or config.get("stage4_variable_p_cell_degree_plan") is not None
        or config.get("matrix_diagnostics_assemble_only") is not False
        or config.get("matrix_diagnostics_factorization_only") is not False
        or config.get("full3d_reference_export") is not True
        or config.get("ordinary_default_changed") is not None
    ):
        raise TrialMetadataError(
            "solver discretization/lifecycle configuration is not qualified"
        )
    if (
        _resolve_config_plan_path(
            config.get("stage4_local_h_refinement_plan")
        )
        != expected_plan_path
    ):
        raise TrialMetadataError(
            "solver config is not bound to the immutable initial plan"
        )
    expected_complete_config = _qualified_cycle0_config(
        path_id=expected_path_id,
        initial_plan_path=expected_plan_path,
    )
    if _canonical(config) != _canonical(expected_complete_config):
        raise TrialMetadataError(
            "solver complete cycle-0 configuration differs from the "
            "qualified deterministic target"
        )

    identity = _component_identity(
        config,
        source_sha=expected_source_sha,
    )
    return config, config_sha, identity


def _load_initial_bundle(
    *,
    plan_path: Path,
    authority_path: Path,
) -> tuple[
    Path,
    Mapping[str, Any],
    str,
    Mapping[str, Any],
    str,
    str,
    str,
]:
    resolved_plan, plan, plan_file_sha = _strict_private_json(
        plan_path,
        label="initial solver plan",
    )
    resolved_authority, authority, authority_file_sha = (
        _strict_private_json(
            authority_path,
            label="initial-space authority",
        )
    )
    if resolved_plan == resolved_authority:
        raise TrialMetadataError(
            "initial plan and initial-space authority must differ"
        )
    path_id = str(authority.get("path_id"))
    if path_id not in _PATH_H_NM:
        raise TrialMetadataError(
            "initial-space authority does not identify Path A or B"
        )
    source_sha = _source_sha(authority.get("source_sha"))
    canonical = build_task035e_initial_space_plan(
        target_stage4_config(
            degree=6,
            h_nm=_PATH_H_NM[path_id],
        ),
        path_id=path_id,
        source_sha=source_sha,
        comm_size=FORMAL_MPI_SIZE,
    )
    expected_plan = canonical.plan_payload()
    if dict(plan) != expected_plan:
        raise TrialMetadataError(
            "initial solver plan does not replay from the deterministic path"
        )
    plan_payload_sha = _json_sha256(plan)
    if plan_payload_sha != canonical.audit["plan_payload_sha256"]:
        raise TrialMetadataError(
            "initial solver plan content identity differs"
        )
    expected_authority = {
        **dict(canonical.audit),
        "plan_file_sha256": plan_file_sha,
        "plan_content_sha256": plan_payload_sha,
        "formal_mpi_size": FORMAL_MPI_SIZE,
        "nominal_h_nm": _PATH_H_NM[path_id],
    }
    if dict(authority) != expected_authority:
        raise TrialMetadataError(
            "initial-space authority does not replay from the plan"
        )
    return (
        resolved_plan,
        plan,
        plan_file_sha,
        authority,
        authority_file_sha,
        path_id,
        source_sha,
    )


def _validate_metadata_payload(
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    row = _exact(
        payload,
        _TRIAL_METADATA_KEYS,
        label="blind trial metadata",
    )
    unsigned = dict(row)
    observed_payload_sha = _sha256(
        unsigned.pop("metadata_payload_sha256"),
        label="trial metadata payload SHA-256",
    )
    if _json_sha256(unsigned) != observed_payload_sha:
        raise TrialMetadataError("trial metadata self-hash differs")
    path_id = next(
        (
            path
            for path, initial_path in _INITIAL_PATH_ID.items()
            if row["initial_path_id"] == initial_path
        ),
        None,
    )
    if (
        path_id is None
        or row["schema_version"] != TRIAL_METADATA_SCHEMA
        or row["status"] != "qualified"
        or row["pass"] is not True
        or row["trial_id"] != _TRIAL_ID[path_id]
        or row["algorithm_id"] != TRIAL_ALGORITHM_ID
        or _SOURCE_SHA_RE.fullmatch(str(row["source_sha"])) is None
        or row["formal_mpi_size"] != FORMAL_MPI_SIZE
        or row["maximum_cycles"] != TRIAL_MAXIMUM_CYCLES
        or row["ordinary_default_changed"] is not False
    ):
        raise TrialMetadataError("trial metadata fixed contract differs")
    for name in _TRIAL_METADATA_KEYS:
        if name.endswith("_sha256"):
            _sha256(row[name], label=name)
    identity = {
        name: row[name]
        for name in (
            "geometry_sha256",
            "material_sha256",
            "incident_sha256",
            "dtn_definition_sha256",
            "postprocessing_sha256",
            "source_sha",
        )
    }
    if _json_sha256(identity) != row["physical_identity_sha256"]:
        raise TrialMetadataError(
            "trial metadata physical identity SHA-256 differs"
        )
    return row


def load_trial_metadata(path: Path) -> Mapping[str, Any]:
    """Load and validate one private v2 trial-metadata artifact."""

    _resolved, payload, _file_sha = _strict_private_json(
        path,
        label="blind trial metadata",
    )
    return dict(_validate_metadata_payload(payload))


def _atomic_private_json(
    output_path: Path,
    payload: Mapping[str, Any],
    *,
    label: str = "blind trial metadata",
    loader: Callable[[Path], Mapping[str, Any]] = load_trial_metadata,
) -> tuple[Path, str]:
    if output_path.is_symlink() or output_path.exists():
        raise FileExistsError(
            f"refusing to overwrite immutable output: {output_path}"
        )
    destination = _safe_path(
        output_path,
        label=f"{label} output",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = _canonical_file_bytes(payload)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        temporary.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    loaded = loader(destination)
    if dict(loaded) != dict(payload):
        raise TrialMetadataError(
            f"{label} changed during immutable publication"
        )
    return destination, hashlib.sha256(body).hexdigest()


def load_qualified_solver_config(
    path: Path,
    *,
    initial_plan_path: Path,
    verified_clean_source_sha: str,
    path_id: str,
) -> Mapping[str, Any]:
    """Load one immutable cycle-0 authority and replay all public inputs."""

    source_sha = _source_sha(verified_clean_source_sha)
    normalized_path = str(path_id).upper()
    if normalized_path not in _PATH_H_NM:
        raise TrialMetadataError("path_id must be A or B")
    plan_path, _plan, plan_file_sha = (
        _replay_initial_plan_for_config(
            initial_plan_path=initial_plan_path,
            source_sha=source_sha,
            path_id=normalized_path,
        )
    )
    _resolved, payload, _file_sha = _strict_private_json(
        path,
        label="qualified solver config authority",
    )
    _validate_qualified_config(
        payload,
        expected_source_sha=source_sha,
        expected_path_id=normalized_path,
        expected_plan_path=plan_path,
        expected_plan_file_sha256=plan_file_sha,
    )
    return dict(payload)


def write_qualified_solver_config(
    output_path: Path,
    *,
    initial_plan_path: Path,
    verified_clean_source_sha: str,
    path_id: str,
) -> QualifiedSolverConfigWriteReceipt:
    """Publish the sole qualified Path-A/B cycle-0 solver configuration.

    The caller can select only the immutable initial plan, its clean source
    SHA, and Path A or B.  Physical parameters, lifecycle options, MPI width,
    backend, and observable export settings are rebuilt here rather than
    accepted from an open caller-provided configuration.
    """

    if output_path.is_symlink() or output_path.exists():
        raise FileExistsError(
            f"refusing to overwrite immutable output: {output_path}"
        )
    source_sha = _source_sha(verified_clean_source_sha)
    normalized_path = str(path_id).upper()
    if normalized_path not in _PATH_H_NM:
        raise TrialMetadataError("path_id must be A or B")

    source_before = _validated_git_source_state(
        _git_source_state(),
        expected_source_sha=source_sha,
        label="source identity before solver-config production",
    )
    abi = _validated_abi_preflight(_qualified_abi_preflight())
    plan_path, _plan, plan_file_sha = (
        _replay_initial_plan_for_config(
            initial_plan_path=initial_plan_path,
            source_sha=source_sha,
            path_id=normalized_path,
        )
    )
    config = _canonical(
        _qualified_cycle0_config(
            path_id=normalized_path,
            initial_plan_path=plan_path,
        )
    )
    config_sha = _json_sha256(config)
    unsigned: dict[str, Any] = {
        "schema_version": QUALIFIED_SOLVER_CONFIG_SCHEMA,
        "status": "qualified",
        "pass": True,
        "source_sha": source_sha,
        "formal_mpi_size": FORMAL_MPI_SIZE,
        "run_kind": "full-solve",
        "output_role": "blind_current_solve",
        "cycle_index": 0,
        "assembly_backend": (
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        "initial_plan_file_sha256": plan_file_sha,
        "source_clean_verified": True,
        "source_stable_during_run": True,
        "qualified_activation": (
            abi["activation_marker"] == "1"
        ),
        "petsc_scalar_type": abi["petsc_scalar_type"],
        "petsc_int_type": abi["petsc_int_type"],
        "ordinary_default_changed": False,
        "config": config,
        "config_payload_sha256": config_sha,
    }
    payload = {
        **unsigned,
        "authority_payload_sha256": _json_sha256(unsigned),
    }
    _validate_qualified_config(
        payload,
        expected_source_sha=source_sha,
        expected_path_id=normalized_path,
        expected_plan_path=plan_path,
        expected_plan_file_sha256=plan_file_sha,
    )

    source_after = _validated_git_source_state(
        _git_source_state(),
        expected_source_sha=source_sha,
        label="source identity after solver-config production",
    )
    if source_after != source_before:
        raise TrialMetadataError(
            "source identity changed during solver-config production"
        )

    def reload(destination: Path) -> Mapping[str, Any]:
        return load_qualified_solver_config(
            destination,
            initial_plan_path=plan_path,
            verified_clean_source_sha=source_sha,
            path_id=normalized_path,
        )

    destination, file_sha = _atomic_private_json(
        output_path,
        payload,
        label="qualified solver config authority",
        loader=reload,
    )
    return QualifiedSolverConfigWriteReceipt(
        path=destination,
        file_sha256=file_sha,
        authority_payload_sha256=payload[
            "authority_payload_sha256"
        ],
        config_payload_sha256=config_sha,
        source_sha=source_sha,
        initial_path_id=_INITIAL_PATH_ID[normalized_path],
        initial_plan_file_sha256=plan_file_sha,
    )


def write_trial_metadata(
    output_path: Path,
    *,
    initial_plan_path: Path,
    initial_space_authority_path: Path,
    qualified_solver_config_path: Path,
) -> TrialMetadataWriteReceipt:
    """Replay all authorities and publish one deterministic trial identity."""

    (
        plan_path,
        plan,
        plan_file_sha,
        initial_authority,
        initial_authority_file_sha,
        path_id,
        source_sha,
    ) = _load_initial_bundle(
        plan_path=initial_plan_path,
        authority_path=initial_space_authority_path,
    )
    _config_path, config_authority, config_file_sha = (
        _strict_private_json(
            qualified_solver_config_path,
            label="qualified solver config authority",
        )
    )
    _config, config_payload_sha, identity = _validate_qualified_config(
        config_authority,
        expected_source_sha=source_sha,
        expected_path_id=path_id,
        expected_plan_path=plan_path,
        expected_plan_file_sha256=plan_file_sha,
    )
    physical_identity_sha = _json_sha256(identity)
    unsigned: dict[str, Any] = {
        "schema_version": TRIAL_METADATA_SCHEMA,
        "status": "qualified",
        "pass": True,
        "trial_id": _TRIAL_ID[path_id],
        "algorithm_id": TRIAL_ALGORITHM_ID,
        "source_sha": source_sha,
        "initial_path_id": _INITIAL_PATH_ID[path_id],
        "initial_mesh_forest_sha256": initial_authority[
            "leaf_catalog_sha256"
        ],
        "initial_degree_map_sha256": initial_authority[
            "cell_degree_plan_sha256"
        ],
        "initial_state_sha256": initial_authority[
            "initial_state_sha256"
        ],
        "initial_plan_file_sha256": plan_file_sha,
        "initial_plan_payload_sha256": _json_sha256(plan),
        "initial_space_authority_file_sha256": (
            initial_authority_file_sha
        ),
        "initial_space_authority_payload_sha256": _json_sha256(
            initial_authority
        ),
        "qualified_solver_config_file_sha256": config_file_sha,
        "qualified_solver_config_payload_sha256": config_payload_sha,
        "geometry_sha256": identity["geometry_sha256"],
        "material_sha256": identity["material_sha256"],
        "incident_sha256": identity["incident_sha256"],
        "dtn_definition_sha256": identity["dtn_definition_sha256"],
        "postprocessing_sha256": identity["postprocessing_sha256"],
        "physical_identity_sha256": physical_identity_sha,
        "formal_mpi_size": FORMAL_MPI_SIZE,
        "maximum_cycles": TRIAL_MAXIMUM_CYCLES,
        "ordinary_default_changed": False,
    }
    payload = {
        **unsigned,
        "metadata_payload_sha256": _json_sha256(unsigned),
    }
    _validate_metadata_payload(payload)
    destination, file_sha = _atomic_private_json(output_path, payload)
    return TrialMetadataWriteReceipt(
        path=destination,
        file_sha256=file_sha,
        metadata_payload_sha256=payload["metadata_payload_sha256"],
        trial_id=payload["trial_id"],
        algorithm_id=payload["algorithm_id"],
        source_sha=source_sha,
        initial_path_id=payload["initial_path_id"],
        physical_identity_sha256=physical_identity_sha,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-plan", type=Path, required=True)
    parser.add_argument(
        "--initial-space-authority",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--qualified-solver-config",
        type=Path,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = write_trial_metadata(
            args.output,
            initial_plan_path=args.initial_plan,
            initial_space_authority_path=args.initial_space_authority,
            qualified_solver_config_path=args.qualified_solver_config,
        )
    except (FileExistsError, OSError, TrialMetadataError) as error:
        print(
            json.dumps(
                {
                    "schema_version": TRIAL_METADATA_RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": TRIAL_METADATA_RECEIPT_SCHEMA,
                "status": "completed",
                "path": str(receipt.path),
                "file_sha256": receipt.file_sha256,
                "metadata_payload_sha256": (
                    receipt.metadata_payload_sha256
                ),
                "trial_id": receipt.trial_id,
                "algorithm_id": receipt.algorithm_id,
                "source_sha": receipt.source_sha,
                "initial_path_id": receipt.initial_path_id,
                "physical_identity_sha256": (
                    receipt.physical_identity_sha256
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FORMAL_MPI_SIZE",
    "QUALIFIED_SOLVER_CONFIG_SCHEMA",
    "TRIAL_ALGORITHM_ID",
    "TRIAL_MAXIMUM_CYCLES",
    "TRIAL_METADATA_SCHEMA",
    "QualifiedSolverConfigWriteReceipt",
    "TrialMetadataError",
    "TrialMetadataWriteReceipt",
    "load_qualified_solver_config",
    "load_trial_metadata",
    "write_qualified_solver_config",
    "write_trial_metadata",
]
