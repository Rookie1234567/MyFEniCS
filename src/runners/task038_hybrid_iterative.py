"""Task38 adapter for the finite, explicit Task37c iterative profile."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from src.io.input_validation import (
    simulation_config_3d_from_normalized,
    task038_hybrid_iterative_profile_errors,
)


LegacyIterativeRunner = Callable[[list[str]], int | Mapping[str, Any]]
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_RESIDUAL_KEYS = (
    "reported_relative_residual",
    "global_true_relative_residual",
    "bottom_true_relative_residual",
    "top_true_relative_residual",
    "modal_true_relative_residual",
)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _profile_errors(
    record: Mapping[str, Any], *, source_sha: str, mpi_size: int, phi: float
) -> list[str]:
    errors: list[str] = []
    if record.get("record_schema") != "task037c.hybrid-iterative-online.v1":
        errors.append("online record schema is not the Task37c iterative schema")
    if record.get("status") != "online_candidate_pass_awaiting_offline_checker":
        errors.append("online record status is not a passed candidate")
    if record.get("online_pass") is not True:
        errors.append("online_pass is not true")
    if record.get("ordinary_default_changed") is not False:
        errors.append("ordinary_default_changed is not false")
    if record.get("explicit_opt_in") is not True:
        errors.append("explicit_opt_in is not true")
    source = record.get("source")
    if not isinstance(source, Mapping):
        errors.append("source provenance is missing")
    else:
        before = source.get("before")
        after = source.get("after")
        if not isinstance(before, Mapping) or before.get("commit_sha") != source_sha:
            errors.append("source before does not match verified source SHA")
        if not isinstance(after, Mapping) or after.get("head") != source_sha:
            errors.append("source after does not match verified source SHA")
        elif not (
            after.get("clean") is True
            and after.get("matches_verified_clean_sha") is True
        ):
            errors.append("source after is not clean at the verified source SHA")

    profile = record.get("profile")
    expected_profile = {
        "profile_id": "task037c.robustness.grazing1.v1",
        "target": "hybrid",
        "degree": 6,
        "h_nm": 10.0,
        "modal_degree": 6,
        "modal_h_nm": 10.0,
        "wavelength_nm": 13.5,
        "polarization_kind": "s",
        "incident_grazing_deg": 1.0,
        "incident_phi_deg": phi,
        "bottom_interface_nm": 10.0,
        "top_interface_nm": 110.0,
        "requested_modes": 120,
        "candidate_modes": 240,
        "internal_propagation_model": "full3d_uniform_cg",
        "internal_traction_model": "full3d_one_cell_exact_schur",
        "operator_identity": "exact_monolithic_hybrid_operator",
        "solver_path": "block-ldu-action-full-solve",
        "preconditioner_identity": (
            "fixed_whole_endcap_ilu0_plus_dynamic_dtn_woodbury_"
            "two_pass_residual_correction"
        ),
        "subdomain_count": 1,
        "overlap": 0.0,
        "ilu_level": 0,
        "shift": 0.1,
        "restart": 90,
        "max_it": 4500,
        "rtol": 5.0e-9,
        "initial_guess": "zero",
        "mpi_size": mpi_size,
        "assembly_backend": "assembly_time_static_condensed",
        "side_residual_correction_steps": 2,
    }
    if not isinstance(profile, Mapping):
        errors.append("online record profile is missing")
    else:
        for key, expected in expected_profile.items():
            if profile.get(key) != expected:
                errors.append(f"profile.{key} does not match the accepted profile")

    qualification = record.get("qualification")
    if not isinstance(qualification, Mapping):
        errors.append("qualification is missing")
    else:
        for key in (
            "numerical_pass",
            "release_pass",
            "recovery_pass",
            "physics_pass",
            "lifecycle_pass",
            "source_after_pass",
            "final_release_pass",
            "cfg_audit_pass",
            "mode_identity_pass",
            "error_free",
        ):
            if qualification.get(key) is not True:
                errors.append(f"qualification.{key} is not true")

    linear = record.get("linear")
    if not isinstance(linear, Mapping):
        errors.append("linear authority is missing")
    else:
        reason = linear.get("reason")
        iterations = linear.get("iterations")
        if not (
            isinstance(reason, int)
            and not isinstance(reason, bool)
            and math.isfinite(float(reason))
            and reason > 0
            and isinstance(iterations, int)
            and not isinstance(iterations, bool)
            and 0 < iterations <= 4500
        ):
            errors.append("linear iteration/reason authority is invalid")
        residuals = linear.get("postsolve_residuals")
        if not isinstance(residuals, Mapping):
            errors.append("five postsolve residuals are missing")
        else:
            for key in _RESIDUAL_KEYS:
                if not _finite(residuals.get(key)) or float(residuals[key]) > 5.0e-9:
                    errors.append(f"linear.{key} exceeds 5e-9")
        release = linear.get("release")
        if not isinstance(release, Mapping) or release.get("pass") is not True:
            errors.append("linear release is not passed")

    physics = record.get("physics")
    if not isinstance(physics, Mapping):
        errors.append("physics authority is missing")
    else:
        port_power = physics.get("port_power")
        absorption = physics.get("absorption")
        energy = physics.get("energy")
        traction = physics.get("traction")
        for key, value in (
            (
                "R_total",
                port_power.get("R_total") if isinstance(port_power, Mapping) else None,
            ),
            (
                "T_total",
                port_power.get("T_total") if isinstance(port_power, Mapping) else None,
            ),
            (
                "A_volume_total",
                absorption.get("A_volume_total")
                if isinstance(absorption, Mapping)
                else None,
            ),
            ("closure", energy.get("closure") if isinstance(energy, Mapping) else None),
        ):
            if not _finite(value):
                errors.append(f"physics.{key} is not finite")
        if not isinstance(traction, Mapping):
            errors.append("exact traction authority is missing")
        else:
            for side in ("bottom", "top"):
                value = traction.get(side, {})
                dual = (
                    value.get("relative_dual") if isinstance(value, Mapping) else None
                )
                if not _finite(dual) or abs(float(dual)) > 1.0e-8:
                    errors.append(f"physics.traction.{side} exceeds 1e-8")
        orders = physics.get("external_orders")
        order_audit = physics.get("order_audit")
        if not isinstance(orders, list) or not orders:
            errors.append("external diffraction orders are missing")
        if not isinstance(order_audit, Mapping) or order_audit.get("pass") is not True:
            errors.append("external diffraction-order audit is not passed")
        if physics.get("own_physics_pass") is not True:
            errors.append("own physics authority is not passed")
        if physics.get("canonical_pass") is not True:
            errors.append("canonical/final field authority is not passed")

    final_release = record.get("final_release")
    if not isinstance(final_release, Mapping) or final_release.get("pass") is not True:
        errors.append("final release authority is not passed")
    return errors


def _default_runner(argv: list[str]) -> int:
    from benchmarks.run_task037b_hybrid_iterative import main

    return int(main(argv))


def _argv_for_payload(
    payload: Mapping[str, Any], numerical_output: Path, source_sha: str
) -> list[str]:
    incidence = payload["incidence"]
    method = payload["method"]
    execution = payload["execution"]
    return [
        "--task037c-robustness-gate",
        "--case-label",
        str(payload["run_id"]),
        "--run-dir",
        str(numerical_output),
        "--memory-stages",
        str(numerical_output / "memory_stages.jsonl"),
        "--output",
        str(numerical_output / "online_record.json"),
        "--verified-clean-sha",
        source_sha,
        "--incident-phi-deg",
        str(incidence["azimuth_deg"]),
        "--requested-modes",
        str(method["requested_modes_per_direction"]),
        "--mpi-size",
        str(execution["mpi_size"]),
        "--internal-traction-model",
        str(method["traction_model"]),
        "--task037c-two-pass-side-correction",
    ]


def run_hybrid_iterative(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    runner: LegacyIterativeRunner | None = None,
    source_sha: str | None = None,
) -> dict[str, Any]:
    """Run the existing Task37c iterative profile without nested MPI."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("hybrid_iterative requires dimension=3")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") != "hybrid_iterative":
        raise ValueError("hybrid_iterative requires method.kind=hybrid_iterative")
    if source_sha is None or not _SOURCE_SHA.fullmatch(source_sha):
        raise ValueError(
            "hybrid_iterative requires a 40-character lowercase source SHA"
        )
    profile_errors = task038_hybrid_iterative_profile_errors(resolved_payload)
    if profile_errors:
        raise ValueError(
            "; ".join(f"{path}: {message}" for path, message in profile_errors)
        )
    # Construct the same normalized mapping used by T2; the legacy runner is
    # intentionally still the only numerical implementation invoked here.
    simulation_config_3d_from_normalized(resolved_payload)
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    if numerical_output.exists():
        raise ValueError(f"iterative numerical output collision: {numerical_output}")
    output_record = numerical_output / "online_record.json"
    argv = _argv_for_payload(resolved_payload, numerical_output, source_sha)
    runner_result = (runner or _default_runner)(argv)
    if isinstance(runner_result, Mapping):
        record: Mapping[str, Any] | None = runner_result
        return_code = 0
    else:
        return_code = int(runner_result)
        try:
            record = json.loads(output_record.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            record = None
            read_error = f"online record is unreadable: {exc}"
        else:
            read_error = None
    errors: list[str] = []
    if return_code != 0:
        errors.append(f"iterative runner returned {return_code}")
    if record is None or not isinstance(record, Mapping):
        errors.append(read_error or "iterative runner did not return a record")
    else:
        errors.extend(
            _profile_errors(
                record,
                source_sha=source_sha,
                mpi_size=int(resolved_payload["execution"]["mpi_size"]),
                phi=float(resolved_payload["incidence"]["azimuth_deg"]),
            )
        )
    return {
        "passed": not errors,
        "errors": errors,
        "record": record,
        "argv": argv,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = ["run_hybrid_iterative"]
