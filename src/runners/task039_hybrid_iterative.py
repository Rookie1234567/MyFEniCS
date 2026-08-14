"""Finite Task39 Hybrid-iterative adapter over the accepted Task37c chain."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from copy import deepcopy
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from benchmarks.task037c_robustness import Task37cProfile, profile_record
from src.io.input_validation import (
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
    task039_profile_errors,
)
from src.runners.task038_hybrid_iterative import _argv_for_payload


TASK039_HYBRID_ITERATIVE_MODES = (120, 240, 480, 960)
TASK039_HYBRID_ITERATIVE_MPI = (1, 8)
_TASK039_MODEL_ID = re.compile(
    r"^task039_5nm_hybrid_iterative_m(120|240|480|960)_candidate$"
)
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_RESIDUAL_KEYS = (
    "reported_relative_residual",
    "global_true_relative_residual",
    "bottom_true_relative_residual",
    "top_true_relative_residual",
    "modal_true_relative_residual",
)


@dataclass(frozen=True)
class Task39HybridIterativeProfile(Task37cProfile):
    """One numeric Task39 profile; no M_robust or campaign value is accepted."""

    profile_id: str = "task039.hybrid_iterative.p6-h10.v1"
    record_schema: str = "task039.hybrid-iterative-online.v1"
    qualification_schema: str = "task039.hybrid-iterative-qualification.v1"
    wavelength_nm: float = 5.0
    incident_grazing_deg: float = 10.0
    incident_phi_deg: float = 0.0
    requested_modes: int = 120
    candidate_modes: int = 240
    internal_traction_model: str = "full3d_one_cell_exact_schur"
    preconditioner_identity: str = (
        "fixed_whole_endcap_ilu0_plus_dynamic_dtn_woodbury_two_pass_residual_correction"
    )
    max_it: int = 6000
    mpi_size: int = 8
    side_residual_correction_steps: int = 2


TASK039_HYBRID_ITERATIVE_PROFILE = Task39HybridIterativeProfile()


def make_task039_hybrid_iterative_profile(
    requested_modes: int,
    mpi_size: int,
    *,
    mesh_target_nm: float = 10.0,
) -> Task39HybridIterativeProfile:
    """Build only the finite numeric M/MPI choices accepted by Task39."""

    modes = int(requested_modes)
    mpi = int(mpi_size)
    mesh = float(mesh_target_nm)
    if modes not in TASK039_HYBRID_ITERATIVE_MODES:
        raise ValueError(
            "Task39 Hybrid iterative modes must be one of "
            f"{TASK039_HYBRID_ITERATIVE_MODES}"
        )
    if mpi not in TASK039_HYBRID_ITERATIVE_MPI:
        raise ValueError(
            f"Task39 Hybrid iterative MPI must be one of {TASK039_HYBRID_ITERATIVE_MPI}"
        )
    if mesh not in (10.0, 5.0):
        raise ValueError("Task39 Hybrid iterative mesh must be 10.0 or 5.0 nm")
    if mesh == 5.0 and (modes != 480 or mpi != 8):
        raise ValueError("Task39 h5 Hybrid iterative requires M480 and MPI8")
    profile_id = (
        "task039.hybrid_iterative.p6-h5.v1"
        if mesh == 5.0
        else "task039.hybrid_iterative.p6-h10.v1"
    )
    return replace(
        TASK039_HYBRID_ITERATIVE_PROFILE,
        profile_id=profile_id,
        requested_modes=modes,
        candidate_modes=2 * modes,
        mpi_size=mpi,
        h_nm=mesh,
        modal_h_nm=mesh,
    )


Task039HybridIterativeRunner = Callable[
    [list[str], Any, Any, Task39HybridIterativeProfile, Mapping[str, Any]],
    int | Mapping[str, Any],
]


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _inventory_keys(inventory: Mapping[str, Any]) -> set[tuple[str, int, int, str]]:
    keys = inventory.get("keys")
    if not isinstance(keys, list):
        return set()
    result: set[tuple[str, int, int, str]] = set()
    for item in keys:
        if not isinstance(item, Mapping):
            continue
        try:
            result.add(
                (
                    str(item["side"]),
                    int(item["m"]),
                    int(item["n"]),
                    str(item["polarization"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _record_order_keys(
    orders: Any,
) -> tuple[set[tuple[str, int, int, str]], bool]:
    if not isinstance(orders, list):
        return set(), False
    keys: list[tuple[str, int, int, str]] = []
    for item in orders:
        if not isinstance(item, Mapping):
            return set(), False
        try:
            keys.append(
                (
                    str(item["side"]),
                    int(item["m"]),
                    int(item["n"]),
                    str(item["polarization"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return set(), False
    return set(keys), len(keys) == len(set(keys))


def task039_hybrid_iterative_authority_errors(
    record: Mapping[str, Any],
    *,
    source_sha: str,
    profile: Task39HybridIterativeProfile,
    inventory: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if record.get("record_schema") != profile.record_schema:
        errors.append("Task39 Hybrid iterative record schema is not accepted")
    if record.get("status") != "online_candidate_pass_awaiting_offline_checker":
        errors.append("Task39 Hybrid iterative record status is not a passed candidate")
    if record.get("online_pass") is not True:
        errors.append("Task39 Hybrid iterative online_pass is not true")
    if record.get("ordinary_default_changed") is not False:
        errors.append("ordinary_default_changed is not false")
    if record.get("explicit_opt_in") is not True:
        errors.append("explicit_opt_in is not true")

    source = record.get("source")
    before = source.get("before") if isinstance(source, Mapping) else None
    after = source.get("after") if isinstance(source, Mapping) else None
    if (
        not isinstance(before, Mapping)
        or before.get("commit_sha") != source_sha
        or before.get("tracked_source_dirty") is not False
        or before.get("stable_and_clean_before") is not True
    ):
        errors.append("source before does not match verified source SHA")
    if not isinstance(after, Mapping) or after.get("head") != source_sha:
        errors.append("source after head does not match verified source SHA")
    elif (
        after.get("clean") is not True
        or after.get("matches_verified_clean_sha") is not True
    ):
        errors.append("source after is not clean at the verified source SHA")

    if record.get("profile") != profile_record(profile):
        errors.append("Task39 Hybrid iterative profile is not exact")
    bindings = record.get("authority_bindings")
    binding = (
        bindings.get("explicit_profile") if isinstance(bindings, Mapping) else None
    )
    if not isinstance(binding, Mapping):
        errors.append("explicit Task39 profile binding is missing")
    elif any(
        binding.get(key) != getattr(profile, profile_key)
        for key, profile_key in (
            ("profile_id", "profile_id"),
            ("requested_modes", "requested_modes"),
            ("mpi_size", "mpi_size"),
        )
    ):
        errors.append("explicit Task39 profile binding is not exact")

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
            "integration_performance_pass",
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
            and reason > 0
            and isinstance(iterations, int)
            and not isinstance(iterations, bool)
            and 0 < iterations <= profile.max_it
        ):
            errors.append("linear reason/iterations are invalid")
        residuals = linear.get("postsolve_residuals")
        if not isinstance(residuals, Mapping):
            errors.append("five postsolve residuals are missing")
        else:
            for key in _RESIDUAL_KEYS:
                value = residuals.get(key)
                if not _finite(value) or not 0.0 <= float(value) <= 5.0e-9:
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
        if not isinstance(port_power, Mapping) or not all(
            _finite(port_power.get(key)) for key in ("R_total", "T_total")
        ):
            errors.append("finite R/T authority is missing")
        if not isinstance(absorption, Mapping) or not _finite(
            absorption.get("A_volume_total")
        ):
            errors.append("finite A_volume authority is missing")
        closure = energy.get("closure") if isinstance(energy, Mapping) else None
        if not _finite(closure) or abs(float(closure)) > 1.0e-5:
            errors.append("energy closure exceeds 1e-5")
        traction = physics.get("traction")
        if not isinstance(traction, Mapping):
            errors.append("exact traction authority is missing")
        else:
            for side in ("bottom", "top"):
                side_traction = traction.get(side)
                value = (
                    side_traction.get("relative_dual")
                    if isinstance(side_traction, Mapping)
                    else None
                )
                if not _finite(value) or abs(float(value)) > 1.0e-8:
                    errors.append(f"physics.traction.{side} exceeds 1e-8")
        for key in ("own_physics_pass", "canonical_pass", "physics_pass"):
            if physics.get(key) is not True:
                errors.append(f"physics.{key} is not true")
        expected_keys = _inventory_keys(inventory)
        observed_keys, unique = _record_order_keys(physics.get("external_orders"))
        if not unique or observed_keys != expected_keys:
            errors.append("physics external order keys do not match inventory")

    mode_identity = record.get("mode_identity")
    expected_keys = _inventory_keys(inventory)
    if not isinstance(mode_identity, Mapping):
        errors.append("bottom/top mode identity is missing")
    else:
        for side in ("bottom", "top"):
            side_report = mode_identity.get(side)
            if not isinstance(side_report, Mapping):
                errors.append(f"{side} mode identity is missing")
                continue
            raw_keys = side_report.get("keys")
            observed: set[tuple[str, int, int, str]] = set()
            if isinstance(raw_keys, list):
                for item in raw_keys:
                    try:
                        observed.add(
                            (
                                str(item[0]),
                                int(item[1]),
                                int(item[2]),
                                str(item[3]),
                            )
                        )
                        if str(item[0]) != side:
                            observed.clear()
                            break
                    except (IndexError, TypeError, ValueError):
                        observed.clear()
                        break
            expected_side = {key for key in expected_keys if key[0] == side}
            if (
                side_report.get("pass") is not True
                or side_report.get("keys_unique") is not True
                or side_report.get("beta_finite") is not True
                or observed != expected_side
            ):
                errors.append(f"{side} mode identity is not finite and exact")

    final_release = record.get("final_release")
    if not isinstance(final_release, Mapping) or final_release.get("pass") is not True:
        errors.append("final release authority is not passed")
    if record.get("external_mode_inventory") != dict(inventory):
        errors.append("external mode inventory is not exact")
    return errors


def _default_runner(
    argv: list[str],
    cfg: Any,
    modal_cfg: Any,
    profile: Task39HybridIterativeProfile,
    inventory: Mapping[str, Any],
) -> Mapping[str, Any]:
    from benchmarks.run_task037b_hybrid_iterative import (
        run_explicit_hybrid_iterative_profile,
    )

    return_code = run_explicit_hybrid_iterative_profile(
        argv,
        profile=profile,
        cfg_override=cfg,
        modal_cfg_override=modal_cfg,
        external_mode_inventory=inventory,
    )
    output = Path(argv[argv.index("--output") + 1])
    try:
        record = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "return_code": int(return_code),
            "record": None,
            "record_error": str(exc),
        }
    return {"return_code": int(return_code), "record": record}


def run_task039_hybrid_iterative(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    runner: Task039HybridIterativeRunner | None = None,
    source_sha: str | None = None,
) -> dict[str, Any]:
    """Run one numeric Task39 Hybrid-iterative profile without nested MPI."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("Task39 Hybrid iterative requires dimension=3")
    model_id = str(resolved_payload.get("model_id", ""))
    model_match = _TASK039_MODEL_ID.fullmatch(model_id)
    if model_match is None:
        raise ValueError("Task39 Hybrid iterative requires a finite Task39 model_id")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") != "hybrid_iterative":
        raise ValueError(
            "Task39 Hybrid iterative requires method.kind=hybrid_iterative"
        )
    if int(model_match.group(1)) != int(
        method.get("requested_modes_per_direction", -1)
    ):
        raise ValueError("Task39 Hybrid iterative model M does not match method M")
    if source_sha is None or not _SOURCE_SHA.fullmatch(source_sha):
        raise ValueError(
            "Task39 Hybrid iterative requires a 40-character lowercase source SHA"
        )
    profile_errors = task039_profile_errors(resolved_payload)
    if profile_errors:
        path, message = profile_errors[0]
        raise ValueError(f"{path}: {message}")

    cfg = simulation_config_3d_from_normalized(resolved_payload)
    modal_cfg = deepcopy(cfg)
    profile = make_task039_hybrid_iterative_profile(
        int(method["requested_modes_per_direction"]),
        int(resolved_payload["execution"]["mpi_size"]),
        mesh_target_nm=float(resolved_payload["discretization"]["mesh_target_nm"]),
    )
    inventory = task039_dynamic_external_mode_inventory(resolved_payload)
    expected_inventory = deepcopy(inventory)
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    if numerical_output.exists():
        raise ValueError(
            f"Task39 Hybrid iterative numerical output collision: {numerical_output}"
        )
    argv = _argv_for_payload(resolved_payload, numerical_output, source_sha)
    result = (runner or _default_runner)(
        argv,
        cfg,
        modal_cfg,
        profile,
        inventory,
    )
    return_code = 0
    record: Mapping[str, Any] | None = None
    runner_error = None
    if isinstance(result, Mapping) and "record" in result:
        record = result.get("record")
        return_code = int(result.get("return_code", 0))
        runner_error = result.get("record_error")
    elif isinstance(result, Mapping):
        record = result
    else:
        return_code = int(result)
    errors: list[str] = []
    if return_code != 0:
        errors.append(f"Task39 Hybrid iterative runner returned {return_code}")
    if runner_error:
        errors.append(f"online record is unreadable: {runner_error}")
    if not isinstance(record, Mapping):
        errors.append("Task39 Hybrid iterative runner did not return a record")
    else:
        errors.extend(
            task039_hybrid_iterative_authority_errors(
                record,
                source_sha=source_sha,
                profile=profile,
                inventory=expected_inventory,
            )
        )
    return {
        "passed": not errors,
        "errors": errors,
        "record": record,
        "summary": record,
        "profile": profile_record(profile),
        "argv": argv,
        "external_mode_inventory": expected_inventory,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = [
    "TASK039_HYBRID_ITERATIVE_MPI",
    "TASK039_HYBRID_ITERATIVE_MODES",
    "Task39HybridIterativeProfile",
    "task039_hybrid_iterative_authority_errors",
    "make_task039_hybrid_iterative_profile",
    "run_task039_hybrid_iterative",
]
