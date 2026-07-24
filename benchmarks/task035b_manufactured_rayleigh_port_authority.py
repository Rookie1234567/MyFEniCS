"""Write the lightweight manufactured Rayleigh-port physics authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d
from src.solvers.dtn_port_3d import (
    _mode_assembly_projection_denominator,
    _mode_auxiliary_coordinate_scale,
    _mode_boundary_phase,
    _mode_projection_denominator,
    _mode_uses_boundary_referenced_auxiliary,
)
from src.solvers.manufactured_rayleigh_port_authority import (
    build_manufactured_rayleigh_port_physics,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/manufactured_rayleigh_port_authority_v1.json"
)
SOURCE_FILES = (
    "benchmarks/task035b_manufactured_rayleigh_port_authority.py",
    "src/solvers/manufactured_rayleigh_port_authority.py",
    "src/common/modes_3d.py",
    "src/solvers/dtn_port_3d.py",
)
DEFAULT_MODE_IDENTITY_SHA256 = (
    "f039dd14264f7bc2987e75e311ef338682388b1f17a4ea194702ff888f4c7a21"
)
BUFFER1_MODE_IDENTITY_SHA256 = (
    "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).strip().lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": (
            len(verified) == 40
            and all(
                character in "0123456789abcdef"
                for character in verified
            )
        ),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "manufactured Rayleigh authority source gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "checks": checks,
    }


def _stable_source_identity(
    repo_root: Path,
    source_before: Mapping[str, Any],
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "head_stable_after_build": (
            head == source_before.get("commit_sha")
        ),
        "branch_stable_after_build": (
            branch == source_before.get("branch") == EXPECTED_BRANCH
        ),
        "worktree_still_clean_before_exclusive_write": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "manufactured Rayleigh authority source changed during build: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "head_after_sha": head,
        "branch_after": branch,
        "status_after_before_record_write": status,
        "stable_and_clean_after": True,
        "checks": checks,
    }


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "working_directory_is_repo_root": (
            Path.cwd().resolve() == repo_root
        ),
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": (
            np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
        ),
        "int32_petsc": (
            np.dtype(PETSc.IntType) == np.dtype(np.int32)
        ),
        "serial_lightweight_authority": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "manufactured Rayleigh authority environment gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "pass": True,
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git_executable": shutil.which("git"),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION")
        ),
    }


def _relative_error(
    actual: complex | float,
    expected: complex | float,
) -> float:
    return float(
        abs(complex(actual) - complex(expected))
        / max(abs(complex(expected)), 1.0e-300)
    )


def _mode_identity_sha256(modes: Sequence[Any]) -> str:
    ordered = [
        (
            mode.side,
            int(mode.m),
            int(mode.n),
            mode.polarization,
        )
        for mode in modes
    ]
    return hashlib.sha256(
        json.dumps(ordered, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _production_mode_physics_bridge(
    mode: Any,
    config: Any,
    *,
    area: float,
) -> dict[str, Any]:
    """Recompute one production mode's Maxwell and power identities."""

    wavevector = np.asarray(mode.k_vector, dtype=np.complex128)
    electric = np.asarray(mode.e_vector, dtype=np.complex128)
    magnetic = np.asarray(mode.h_vector, dtype=np.complex128)
    expected_kz = (
        (1 if mode.side == "top" else -1) * complex(mode.beta)
    )
    dispersion_expected = (
        config.k0 * complex(mode.refractive_index)
    ) ** 2
    dispersion_scale = max(
        abs(dispersion_expected),
        float(np.linalg.norm(wavevector)) ** 2,
        1.0e-300,
    )
    transversality_scale = max(
        float(np.linalg.norm(wavevector))
        * float(np.linalg.norm(electric)),
        1.0e-300,
    )
    expected_magnetic = np.cross(wavevector, electric) / (
        config.k0 * complex(config.mu_r)
    )
    magnetic_scale = max(
        float(np.linalg.norm(expected_magnetic)),
        1.0e-300,
    )
    outward_normal = np.asarray(
        (0.0, 0.0, 1.0 if mode.side == "top" else -1.0),
        dtype=np.float64,
    )
    poynting = 0.5 * np.real(
        np.cross(electric, np.conj(expected_magnetic))
    )
    expected_power = max(
        float(np.dot(poynting, outward_normal)),
        0.0,
    ) * area
    errors = {
        "kz_relative": _relative_error(
            complex(wavevector[2]),
            expected_kz,
        ),
        "dispersion_relative": float(
            abs(np.dot(wavevector, wavevector) - dispersion_expected)
            / dispersion_scale
        ),
        "electric_transversality_relative": float(
            abs(np.dot(wavevector, electric))
            / transversality_scale
        ),
        "magnetic_definition_relative": float(
            np.linalg.norm(magnetic - expected_magnetic)
            / magnetic_scale
        ),
        "power_per_unit_amplitude_relative": _relative_error(
            mode.power_per_unit_amplitude,
            expected_power,
        ),
    }
    maximum = max(errors.values())
    expected_sign = 1 if mode.side == "top" else -1
    checks = {
        "outgoing_vertical_sign_matches_port": (
            mode.vertical_sign == expected_sign
        ),
        "kz_matches_vertical_sign_times_beta": (
            errors["kz_relative"] <= 5.0e-12
        ),
        "production_dispersion_identity": (
            errors["dispersion_relative"] <= 5.0e-12
        ),
        "production_electric_transversality": (
            errors["electric_transversality_relative"] <= 5.0e-12
        ),
        "production_magnetic_definition": (
            errors["magnetic_definition_relative"] <= 5.0e-12
        ),
        "production_power_matches_independent_poynting_magnitude": (
            errors["power_per_unit_amplitude_relative"] <= 5.0e-12
        ),
    }
    return {
        "errors": errors,
        "maximum_relative_error": maximum,
        "expected_power_per_unit_amplitude": expected_power,
        "checks": checks,
        "pass": all(checks.values()),
    }


def _production_contract_bridge() -> dict[str, Any]:
    """Compare actual Stage-4 coordinates with independent formulas."""

    default_config = target_stage4_config(degree=6, h_nm=15.0)
    default_modes = outgoing_port_modes_3d(default_config)
    area = float(
        (default_config.x_max - default_config.x_min)
        * (default_config.y_max - default_config.y_min)
    )
    default_errors: list[float] = []
    default_checks: list[bool] = []
    outward_power_checks: list[bool] = []
    production_physics_errors: list[float] = []
    for mode in default_modes:
        port_z = float(
            default_config.physical_z_max
            if mode.side == "top"
            else default_config.physical_z_min
        )
        expected_sign = 1 if mode.side == "top" else -1
        expected_phase = complex(
            np.exp(1j * complex(mode.k_vector[2]) * port_z)
        )
        expected_denominator = float(
            area
            * mode.electric_tangential_norm_sq
            * abs(expected_phase) ** 2
        )
        default_errors.extend(
            (
                _relative_error(
                    _mode_boundary_phase(mode, default_config),
                    expected_phase,
                ),
                _relative_error(
                    _mode_projection_denominator(
                        mode,
                        default_config,
                    ),
                    expected_denominator,
                ),
            )
        )
        physics_bridge = _production_mode_physics_bridge(
            mode,
            default_config,
            area=area,
        )
        production_physics_errors.append(
            physics_bridge["maximum_relative_error"]
        )
        default_checks.append(
            mode.vertical_sign == expected_sign
            and complex(mode.k_vector[2])
            == expected_sign * complex(mode.beta)
            and not _mode_uses_boundary_referenced_auxiliary(
                mode,
                default_config,
            )
            and _mode_auxiliary_coordinate_scale(
                mode,
                default_config,
            )
            == 1.0 + 0.0j
            and _mode_assembly_projection_denominator(
                mode,
                default_config,
            )
            == _mode_projection_denominator(
                mode,
                default_config,
            )
            and physics_bridge["pass"] is True
        )
        if mode.propagating:
            outward_power_checks.append(
                mode.power_per_unit_amplitude > 0.0
            )

    buffer_config = target_stage4_config(degree=6, h_nm=15.0)
    buffer_config.stage4_dtn_evanescent_buffer = 1
    buffer_modes = outgoing_port_modes_3d(buffer_config)
    scaled_modes = [
        mode
        for mode in buffer_modes
        if _mode_uses_boundary_referenced_auxiliary(
            mode,
            buffer_config,
        )
    ]
    buffer_errors: list[float] = []
    buffer_checks: list[bool] = []
    for index, mode in enumerate(scaled_modes):
        port_z = float(
            buffer_config.physical_z_max
            if mode.side == "top"
            else buffer_config.physical_z_min
        )
        expected_scale = complex(
            np.exp(1j * complex(mode.k_vector[2]) * port_z)
        )
        scale = _mode_auxiliary_coordinate_scale(
            mode,
            buffer_config,
        )
        boundary_denominator = (
            _mode_assembly_projection_denominator(
                mode,
                buffer_config,
            )
        )
        global_denominator = _mode_projection_denominator(
            mode,
            buffer_config,
        )
        expected_boundary_denominator = float(
            area * mode.electric_tangential_norm_sq
        )
        traction_boundary = complex(
            0.13 + 0.001 * index,
            -0.17 + 0.0003 * index,
        )
        projection_boundary = complex(
            -0.23 + 0.0002 * index,
            0.29 - 0.0001 * index,
        )
        eliminated_global = (
            (scale * traction_boundary)
            * np.conj(scale * projection_boundary)
            / global_denominator
        )
        eliminated_boundary = (
            traction_boundary
            * np.conj(projection_boundary)
            / boundary_denominator
        )
        buffer_errors.extend(
            (
                _relative_error(scale, expected_scale),
                _relative_error(
                    boundary_denominator,
                    expected_boundary_denominator,
                ),
                _relative_error(
                    global_denominator,
                    abs(scale) ** 2 * boundary_denominator,
                ),
                _relative_error(
                    eliminated_global,
                    eliminated_boundary,
                ),
            )
        )
        physics_bridge = _production_mode_physics_bridge(
            mode,
            buffer_config,
            area=area,
        )
        production_physics_errors.append(
            physics_bridge["maximum_relative_error"]
        )
        buffer_checks.append(
            not mode.propagating
            and np.isfinite(abs(scale))
            and abs(scale) > 0.0
            and physics_bridge["pass"] is True
        )

    maximum_error = max(
        [
            *default_errors,
            *buffer_errors,
            *production_physics_errors,
        ]
    )
    default_identity = _mode_identity_sha256(default_modes)
    buffer_identity = _mode_identity_sha256(buffer_modes)
    checks = {
        "ordinary_default_buffer_is_zero": (
            default_config.stage4_dtn_evanescent_buffer == 0
        ),
        "default_mode_count_is_80": len(default_modes) == 80,
        "default_ordered_mode_identity_is_frozen": (
            default_identity == DEFAULT_MODE_IDENTITY_SHA256
        ),
        "default_top_bottom_sign_and_global_z_coordinate_match": (
            bool(default_checks) and all(default_checks)
        ),
        "default_propagating_modes_carry_positive_outward_power": (
            bool(outward_power_checks) and all(outward_power_checks)
        ),
        "buffer1_mode_count_is_340": len(buffer_modes) == 340,
        "buffer1_ordered_mode_identity_is_frozen": (
            buffer_identity == BUFFER1_MODE_IDENTITY_SHA256
        ),
        "buffer1_scaled_evanescent_mode_count_is_260": (
            len(scaled_modes) == 260
        ),
        "buffer1_scaled_modes_are_finite_evanescent": (
            bool(buffer_checks) and all(buffer_checks)
        ),
        "all_default_and_buffer_modes_pass_production_maxwell_bridge": (
            len(production_physics_errors)
            == len(default_modes) + len(scaled_modes)
            and max(production_physics_errors) <= 5.0e-12
        ),
        "buffer1_top_bottom_sign_kz_and_power_magnitude_verified": (
            bool(buffer_checks) and all(buffer_checks)
        ),
        "production_formulas_match_independent_coordinate_algebra": (
            maximum_error <= 5.0e-12
        ),
    }
    return {
        "schema_version": (
            "task035b.manufactured-rayleigh-production-bridge.v1"
        ),
        "default_mode_identity_sha256": default_identity,
        "buffer1_mode_identity_sha256": buffer_identity,
        "default_mode_count": len(default_modes),
        "default_propagating_mode_count": sum(
            mode.propagating for mode in default_modes
        ),
        "buffer1_mode_count": len(buffer_modes),
        "buffer1_scaled_evanescent_mode_count": len(scaled_modes),
        "maximum_formula_relative_error": maximum_error,
        "maximum_production_mode_physics_relative_error": max(
            production_physics_errors
        ),
        "checks": checks,
        "pass": all(checks.values()),
    }


def build_manufactured_rayleigh_port_authority_record(
    repo_root: Path,
    *,
    source: Mapping[str, Any],
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """Build independent finite-plane convention evidence without a PDE."""

    physics = build_manufactured_rayleigh_port_physics()
    production_bridge = _production_contract_bridge()
    source_checks = source.get("checks") or {}
    environment_checks = environment.get("checks") or {}
    source_identity_pass = bool(
        source.get("branch") == EXPECTED_BRANCH
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and isinstance(source.get("commit_sha"), str)
        and len(source["commit_sha"]) == 40
        and all(
            character in "0123456789abcdef"
            for character in source["commit_sha"].lower()
        )
        and source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_before") is True
        and bool(source_checks)
        and all(value is True for value in source_checks.values())
    )
    qualification_checks = {
        "clean_source_identity_hash_bound": source_identity_pass,
        "qualified_environment": (
            environment.get("pass") is True
            and bool(environment_checks)
            and all(
                value is True
                for value in environment_checks.values()
            )
        ),
        "independent_manufactured_physics_pass": physics["pass"] is True,
        "source_free_maxwell_identities_proved": all(
            case["source_free_maxwell_identities"]["pass"]
            for case in (
                *physics["propagating_cases"],
                *physics["evanescent_cases"],
            )
        ),
        "production_contract_bridge_pass": (
            production_bridge["pass"] is True
        ),
        "top_bottom_outgoing_sign_proved": all(
            case["checks"][
                "outgoing_vertical_sign_matches_port"
            ]
            and case["checks"]["outgoing_power_is_positive"]
            and case["checks"]["incoming_power_is_negative"]
            for case in physics["propagating_cases"]
        ),
        "two_plane_phase_propagation_proved": all(
            case["checks"][
                "two_plane_phase_propagation_matches_exp_i_kz_dz"
            ]
            for case in physics["propagating_cases"]
        ),
        "projection_normalization_proved": all(
            case["checks"][
                "global_projection_recovers_plane_independent_amplitude"
            ]
            and case["checks"][
                "projection_normalization_matches_analytic_area_norm"
            ]
            for case in physics["propagating_cases"]
        ),
        "propagating_power_invariance_proved": all(
            case["checks"]["power_is_reference_plane_invariant"]
            and case["checks"][
                "power_normalization_matches_analytic_poynting_flux"
            ]
            for case in physics["propagating_cases"]
        ),
        "evanescent_coordinate_algebra_proved": all(
            case["checks"][
                "boundary_projection_equals_s_times_global_amplitude"
            ]
            and case["checks"][
                "global_denominator_equals_abs_s_sq_times_boundary_denominator"
            ]
            and case["checks"][
                "eliminated_operator_is_coordinate_invariant"
            ]
            for case in physics["evanescent_cases"]
        ),
        "ordinary_default_unchanged": True,
        "pde_not_run": True,
    }
    passed = all(qualification_checks.values())
    return {
        "schema_version": (
            "task035b.manufactured-rayleigh-port-authority.v1"
        ),
        "benchmark_id": (
            "task035b_manufactured_rayleigh_port_authority"
        ),
        "status": (
            "manufactured_rayleigh_port_authority_pass"
            if passed
            else "manufactured_rayleigh_port_authority_fail"
        ),
        "pass": passed,
        "classification": (
            "independent_manufactured_physics_authority"
        ),
        "source": dict(source),
        "source_file_sha256": {
            path: _sha256(repo_root / path) for path in SOURCE_FILES
        },
        "environment": dict(environment),
        "scope": {
            "geometry": "manufactured homogeneous periodic cell",
            "purpose": (
                "independent authority for the Task035b finite-port "
                "Rayleigh convention"
            ),
            "ordinary_default_changed": False,
            "scientific_gate_relaxed": False,
        },
        "pde": {
            "status": "not_run",
            "heavy_case_started": False,
            "mesh_built": False,
            "form_compiled": False,
            "global_matrix_assembled": False,
            "factorization_started": False,
            "solver_started": False,
        },
        "physics": physics,
        "production_contract_bridge": production_bridge,
        "qualification": {
            "pass": passed,
            "checks": qualification_checks,
        },
        "decision": {
            "ordinary_default_changed": False,
            "formal_pde_result_claimed": False,
            "interpretation": (
                "The manufactured authority independently proves the "
                "outgoing sign, finite-plane phase, projection, power, "
                "and evanescent coordinate algebra. It does not establish "
                "a Task035b same-error candidate or replace full residual "
                "and 12-channel gates."
            ),
        },
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a clean-SHA-bound manufactured Rayleigh-port authority "
            "without running a PDE."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    source = _verified_source_identity(
        repo_root,
        args.verified_clean_sha,
    )
    environment = _environment_identity(repo_root)
    output = (
        args.output
        if args.output.is_absolute()
        else repo_root / args.output
    ).resolve()
    if not output.is_relative_to(repo_root):
        raise SystemExit(
            "manufactured Rayleigh authority output must remain in the repo"
        )
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing authority record: {output}"
        )
    record = build_manufactured_rayleigh_port_authority_record(
        repo_root,
        source=source,
        environment=environment,
    )
    source_after = _stable_source_identity(repo_root, source)
    record["source"].update(
        {
            key: value
            for key, value in source_after.items()
            if key != "checks"
        }
    )
    record["source"]["checks"].update(source_after["checks"])
    current_hashes = {
        path: _sha256(repo_root / path) for path in SOURCE_FILES
    }
    if current_hashes != record["source_file_sha256"]:
        raise SystemExit(
            "manufactured Rayleigh source files changed before evidence write"
        )
    record["qualification"]["checks"][
        "source_stable_and_clean_after_build"
    ] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return 0 if record["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
