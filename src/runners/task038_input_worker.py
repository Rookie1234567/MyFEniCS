"""Private Task38 worker contract and resolved-payload dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src.io.execution_plan import CONTRACT_PROBE_ADAPTER, METHOD_ADAPTERS


def _task40_d07c_runtime_cache_evidence(
    manifest: dict[str, Any], *, environment=None, jit_options_resolver=None
) -> dict[str, Any] | None:
    """Verify the exact G5/G6 worker cache and JIT routing before FE work."""
    profile = manifest.get("native_capacity_profile_identity")
    from src.runners.task40_d07c_g5_join import (
        G5_PROFILE,
        G6_SCOPED_PROFILES,
        g6_case_for_profile,
    )

    if profile != G5_PROFILE and profile not in G6_SCOPED_PROFILES:
        return None
    case = "G5" if profile == G5_PROFILE else g6_case_for_profile(profile)
    case_key = case.lower()
    owner = f"{case}_attempt_only"
    scope_key = f"{case_key}_observational_join"

    env = os.environ if environment is None else environment
    runtime = manifest.get("attempt_specific_runtime_cache")
    if not isinstance(runtime, dict) or runtime.get("owner") != owner:
        raise ValueError(f"{case} manifest is missing its attempt-owned cache paths")
    join = manifest.get("native_capacity_isolation", {}).get(scope_key)
    attempt_id = join.get("attempt_id") if isinstance(join, dict) else None
    if not isinstance(attempt_id, str):
        raise TypeError(f"{case} manifest is missing its one-attempt identity")
    expected_root = Path("/tmp") / f"task40_d07c_{case_key}_attempt_{attempt_id}"
    expected_paths = {
        "root": expected_root,
        "tmp": expected_root / "tmp",
        "xdg": expected_root / "xdg",
        "pycache": expected_root / "pycache",
        "mpl": expected_root / "mpl",
    }
    for key, path in expected_paths.items():
        if Path(runtime.get(key, "")).resolve() != path.resolve():
            raise ValueError(f"{case} manifest cache path differs at {key}")
        if path.is_symlink() or (key != "root" and not path.is_dir()):
            raise ValueError(f"{case} attempt cache directory is missing or symlinked: {key}")
    expected_environment = {
        "TMPDIR": str(expected_paths["tmp"]),
        "TMP": str(expected_paths["tmp"]),
        "TEMP": str(expected_paths["tmp"]),
        "XDG_CACHE_HOME": str(expected_paths["xdg"]),
        "PYTHONPYCACHEPREFIX": str(expected_paths["pycache"]),
        "MPLCONFIGDIR": str(expected_paths["mpl"]),
    }
    mismatches = {
        key: {"expected": value, "actual": env.get(key)}
        for key, value in expected_environment.items()
        if env.get(key) != value
    }
    if mismatches:
        raise ValueError(f"{case} worker cache environment differs: {mismatches}")
    if jit_options_resolver is None:
        from dolfinx.jit import get_options

        from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
            SAME_MESH_JIT_OPTIONS,
        )

        def jit_options_resolver():
            return get_options(dict(SAME_MESH_JIT_OPTIONS))
    options = jit_options_resolver()
    actual_jit_cache = Path(options["cache_dir"]).expanduser().resolve()
    expected_jit_cache = (expected_paths["xdg"] / "fenics").resolve()
    if actual_jit_cache != expected_jit_cache:
        raise ValueError(
            f"{case} DOLFINx JIT cache is not inside this attempt's XDG cache: "
            f"{actual_jit_cache} != {expected_jit_cache}"
        )
    return {
        "schema": f"task40.d07c.{case_key}_worker_cache_runtime.v1",
        "attempt_id": attempt_id,
        "owner": owner,
        "environment": expected_environment,
        "dolfinx_jit_cache_dir": str(actual_jit_cache),
        "dolfinx_jit_options_source": "dolfinx.jit.get_options(SAME_MESH_JIT_OPTIONS)",
        "cache_paths_verified_before_FE_dispatch": True,
    }


def _task40_g5_runtime_cache_evidence(
    manifest: dict[str, Any], *, environment=None, jit_options_resolver=None
) -> dict[str, Any] | None:
    if manifest.get("native_capacity_profile_identity") != "task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1":
        return None
    return _task40_d07c_runtime_cache_evidence(
        manifest, environment=environment, jit_options_resolver=jit_options_resolver
    )


def _task40_g6_runtime_cache_evidence(
    manifest: dict[str, Any], *, environment=None, jit_options_resolver=None
) -> dict[str, Any] | None:
    from src.runners.task40_d07c_g5_join import G6_SCOPED_PROFILES

    if manifest.get("native_capacity_profile_identity") not in G6_SCOPED_PROFILES:
        return None
    return _task40_d07c_runtime_cache_evidence(
        manifest, environment=environment, jit_options_resolver=jit_options_resolver
    )


def _write_d07c_runtime_cache_evidence(output_directory: str | Path, evidence: dict) -> Path:
    case = evidence["owner"].split("_", maxsplit=1)[0].lower()
    path = Path(output_directory) / f"{case}_runtime_environment.json"
    payload = (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def _read_json_bytes(
    path: Path, label: str
) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, None, f"{label} is unreadable: {exc}"
    if not isinstance(value, dict):
        return None, payload, f"{label} must contain a JSON object"
    return value, payload, None


def _load_and_validate_worker_payload(
    *,
    resolved_config: str | Path,
    manifest: str | Path,
    expected_input_sha256: str,
    expected_physical_model_sha256: str,
    expected_source_sha: str,
    expected_mpi_size: int,
    expected_method: str,
    expected_adapter: str,
    expected_output_directory: str | Path,
    expected_resolved_config_sha256: str,
    actual_mpi_size: int,
    contract_probe: bool = False,
    setup_only: bool = False,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read each contract JSON once and return the validated resolved payload."""

    resolved_path = Path(resolved_config)
    manifest_path = Path(manifest)
    expected_output_path = Path(expected_output_directory).resolve()
    errors: list[str] = []
    resolved, resolved_bytes, resolved_error = _read_json_bytes(
        resolved_path, "resolved config"
    )
    manifest_value, _manifest_bytes, manifest_error = _read_json_bytes(
        manifest_path, "manifest"
    )
    if resolved_error:
        errors.append(resolved_error)
    if manifest_error:
        errors.append(manifest_error)
    if resolved is None or resolved_bytes is None or manifest_value is None:
        return None, errors

    # Validate the observer opt-in at the worker's real pre-FE payload gate.
    # The runner repeats this check at its own entry as defense in depth; this
    # first check prevents an enabled parent manifest from being silently
    # ignored if the worker environment binding is lost.
    try:
        import os

        from src.io.v7_balanced_diagnostic_contract import (
            V7_DIAGNOSTIC_ENV,
            validate_worker_binding,
        )

        solver_payload = resolved.get("solver")
        from src.io.native_capacity_profile import native_capacity_profile_identity

        profile_name = native_capacity_profile_identity(
            resolved.get("method", {}).get("kind"),
            solver_payload if isinstance(solver_payload, dict) else {},
        )
        observer_binding = validate_worker_binding(
            manifest_value,
            environment_value=os.environ.get(V7_DIAGNOSTIC_ENV),
            profile=str(profile_name or ""),
            source_sha=str(expected_source_sha),
            input_sha256=str(expected_input_sha256),
            resolved_config_sha256=str(expected_resolved_config_sha256),
            physical_model_sha256=str(expected_physical_model_sha256),
            output_directory=expected_output_path,
        )
        if observer_binding is not None:
            observer = manifest_value.get("v7_balanced_failure_diagnostic")
            if not isinstance(observer, dict) or observer != observer_binding:
                errors.append("V7 observer binding differs from the validated parent manifest")
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(f"V7 observer binding failed: {exc}")

    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    if resolved_sha != expected_resolved_config_sha256:
        errors.append("resolved config SHA does not match the launch contract")

    if resolved_path.resolve().parent != expected_output_path:
        errors.append("resolved config output directory mismatch")
    if manifest_path.resolve().parent != expected_output_path:
        errors.append("manifest output directory mismatch")

    provenance = resolved.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("resolved config provenance is missing")
    else:
        if provenance.get("input_sha256") != expected_input_sha256:
            errors.append("resolved config input SHA mismatch")
        if provenance.get("physical_model_sha256") != expected_physical_model_sha256:
            errors.append("resolved config physical model SHA mismatch")

        if provenance.get("source_path") != manifest_value.get("input_path"):
            errors.append("manifest input path mismatch")

    input_copy = expected_output_path / "input_original.dat"
    try:
        input_copy_bytes = input_copy.read_bytes()
    except OSError as exc:
        errors.append(f"input_original.dat is unreadable: {exc}")
    else:
        input_copy_sha = hashlib.sha256(input_copy_bytes).hexdigest()
        if input_copy_sha != expected_input_sha256:
            errors.append("input_original.dat SHA mismatch")
        if input_copy_sha != manifest_value.get("input_sha256"):
            errors.append("input_original.dat manifest SHA mismatch")

    method_payload = resolved.get("method")
    if not isinstance(method_payload, dict):
        errors.append("resolved config method payload is missing")
        method = None
        requested_modes = None
    else:
        method = method_payload.get("kind")
        requested_modes = method_payload.get("requested_modes_per_direction")
    if method != expected_method:
        errors.append("resolved config method mismatch")

    execution_payload = resolved.get("execution")
    if not isinstance(execution_payload, dict):
        errors.append("resolved config execution payload is missing")
    elif execution_payload.get("mpi_size") != expected_mpi_size:
        errors.append("resolved config MPI size mismatch")

    expected_method_adapter = METHOD_ADAPTERS.get(expected_method)
    if contract_probe != (expected_adapter == CONTRACT_PROBE_ADAPTER):
        errors.append("contract-probe mode and adapter identity mismatch")
    if expected_adapter == CONTRACT_PROBE_ADAPTER:
        pass
    elif expected_method_adapter is None or expected_adapter != expected_method_adapter:
        errors.append("adapter identity mismatch with expected method")

    if actual_mpi_size != expected_mpi_size:
        errors.append("MPI.COMM_WORLD size mismatch")
    if manifest_value.get("mpi_size") != expected_mpi_size:
        errors.append("manifest MPI size mismatch")
    if manifest_value.get("method") != expected_method:
        errors.append("manifest method mismatch")
    if manifest_value.get("resolved_method_adapter") != expected_adapter:
        errors.append("manifest adapter identity mismatch")
    if manifest_value.get("input_sha256") != expected_input_sha256:
        errors.append("manifest input SHA mismatch")
    if manifest_value.get("physical_model_sha256") != expected_physical_model_sha256:
        errors.append("manifest physical model SHA mismatch")
    if manifest_value.get("source_sha") != expected_source_sha:
        errors.append("manifest source SHA mismatch")
    if manifest_value.get("resolved_config_sha256") != resolved_sha:
        errors.append("manifest resolved config SHA mismatch")
    if manifest_value.get("output_directory") != str(expected_output_path):
        errors.append("manifest output directory mismatch")
    if manifest_value.get("numerical_output_directory") != str(
        expected_output_path / "numerical_output"
    ):
        errors.append("manifest numerical output directory mismatch")

    for identity_key in ("model_id", "run_id", "comparison_group"):
        if manifest_value.get(identity_key) != resolved.get(identity_key):
            errors.append(f"manifest {identity_key.replace('_', ' ')} mismatch")
    if manifest_value.get("solver") != resolved.get("solver"):
        errors.append("manifest solver payload mismatch")
    if manifest_value.get("requested_modes") != requested_modes:
        errors.append("manifest requested-mode identity mismatch")

    expected_execution_mode = "setup_only" if setup_only else "full_solve"
    if not setup_only:
        from src.io.native_capacity_profile import (
            P6_CONDENSED_DIRECT_PROFILES,
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z7P5_OOC8_PROFILE,
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE,
            TASK40_PHI90_D07C_G6_M8_N14_PROFILE,
            V6_NATIVE_PROFILES,
            native_capacity_profile_identity,
            native_profile_facts,
            numeric_factor_blas_thread_choices,
        )
        profile_name = native_capacity_profile_identity(
            resolved.get('method', {}).get('kind'), resolved.get('solver', {})
        )
        numeric_factor_blas_threads = manifest_value.get("numeric_factor_blas_threads")
        numeric_factor_blas_scope = manifest_value.get("numeric_factor_blas_scope")
        if numeric_factor_blas_threads is not None:
            allowed_thread_counts = numeric_factor_blas_thread_choices(profile_name)
            if (
                type(numeric_factor_blas_threads) is not int
                or numeric_factor_blas_threads not in allowed_thread_counts
                or numeric_factor_blas_scope != "MUMPS_numeric_factorization_only"
            ):
                errors.append(
                    "manifest numeric-factor BLAS control is outside the exact profile-scoped contract"
                )
            isolation = manifest_value.get("native_capacity_isolation")
            worker_affinity = (
                isolation.get("worker_affinity") if isinstance(isolation, dict) else None
            )
            expected_worker_count = (
                8 if profile_name == TASK40_PHI90_D07C_G6_M8_N14_PROFILE
                else numeric_factor_blas_threads
                if type(numeric_factor_blas_threads) is int else -1
            )
            if (
                not isinstance(worker_affinity, list)
                or len(worker_affinity) != expected_worker_count
                or any(type(cpu) is not int or cpu < 0 for cpu in worker_affinity)
                or len(set(worker_affinity)) != expected_worker_count
            ):
                errors.append(
                    "manifest BLAS benchmark lacks its profile-matched physical-core reservation"
                )
            else:
                worker_command = manifest_value["worker_command"]
                try:
                    taskset_index = worker_command.index("/usr/bin/taskset")
                    command_affinity = worker_command[taskset_index + 2]
                except (AttributeError, IndexError, KeyError, TypeError, ValueError):
                    errors.append(
                        "manifest worker command omits its G6 BLAS CPU reservation"
                    )
                else:
                    if command_affinity != ",".join(map(str, worker_affinity)):
                        errors.append(
                            "manifest worker command differs from its numeric-LU CPU reservation"
                        )
        elif numeric_factor_blas_scope is not None:
            errors.append("manifest numeric-factor BLAS scope has no thread-count binding")
        if profile_name in (V6_NATIVE_PROFILES | P6_CONDENSED_DIRECT_PROFILES):
            profile = native_profile_facts(profile_name)
            expected_execution_mode = profile['execution_mode']
            if manifest_value.get('component_options') != profile['component_options']:
                errors.append('manifest native profile component options mismatch')
            if profile_name in P6_CONDENSED_DIRECT_PROFILES:
                resolved_derived = resolved.get('derived')
                resolved_profile = (
                    resolved_derived.get('native_capacity_profile')
                    if isinstance(resolved_derived, dict) else None
                )
                from src.io.resolved_config import canonical_json_bytes

                if (
                    not isinstance(resolved_profile, dict)
                    or canonical_json_bytes(resolved_profile)
                    != canonical_json_bytes(profile)
                ):
                    errors.append(
                        'resolved condensed-direct native-capacity profile facts mismatch'
                    )
                if manifest_value.get('native_capacity_profile_identity') != profile_name:
                    errors.append('manifest condensed-direct profile identity mismatch')
                if manifest_value.get('native_capacity_profile') != resolved_profile:
                    errors.append(
                        'manifest condensed-direct profile facts differ from resolved config'
                    )
                native_contract = manifest_value.get('native_capacity_contract')
                if not isinstance(native_contract, dict):
                    errors.append('manifest condensed-direct native-capacity contract is missing')
                else:
                    expected_route = profile['campaign_authorization']['direct_route']
                    expected_rss_cap = profile['resources']['rss_hard_limit_bytes']
                    expected_minimum_available = profile['resources'].get('minimum_available_bytes')
                    expected_minimum_disk = profile['resources'].get(
                        'minimum_disk_available_bytes'
                    )
                    expected_disk_warning = profile['resources'].get(
                        'disk_warning_bytes'
                    )
                    if native_contract.get('profile') != profile_name:
                        errors.append('manifest condensed-direct resource profile mismatch')
                    if native_contract.get('rss_hard_limit_bytes') != expected_rss_cap:
                        errors.append('manifest condensed-direct RSS hard limit mismatch')
                    if native_contract.get('resource_stop_policy') != profile['resources'].get(
                        'resource_stop_policy', 'legacy'
                    ):
                        errors.append('manifest condensed-direct resource stop policy mismatch')
                    if native_contract.get('minimum_available_bytes') != expected_minimum_available:
                        errors.append('manifest condensed-direct minimum available-memory floor mismatch')
                    if native_contract.get('minimum_disk_available_bytes') != expected_minimum_disk:
                        errors.append('manifest condensed-direct minimum disk floor mismatch')
                    if native_contract.get('disk_warning_bytes') != expected_disk_warning:
                        errors.append('manifest condensed-direct disk warning threshold mismatch')
                    if native_contract.get('direct_route') != expected_route:
                        errors.append('manifest condensed-direct route contract mismatch')
                    if profile_name == SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z7P5_OOC8_PROFILE:
                        expected_ooc_contract = profile['component_options'].get(
                            'mumps_ooc_contract'
                        )
                        if native_contract.get('mumps_ooc_contract') != expected_ooc_contract:
                            errors.append('manifest OOC8 contract differs from the resolved profile')
        if profile_name in (
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE,
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z7P5_OOC8_PROFILE,
        ):
            gate_profile = profile['component_options'].get(
                'pre_lu_port_assembly_gate'
            )
            if not isinstance(gate_profile, dict):
                errors.append('CX9Z10 resolved profile omits its pre-LU gate identity')
            else:
                repository_root = Path(__file__).resolve().parents[2]
                profile_path = (
                    repository_root / gate_profile.get('profile_path', '')
                ).resolve()
                launcher_path = (
                    repository_root / 'src/runners/task038_launcher.py'
                ).resolve()
                worker_path = (
                    repository_root / 'src/runners/p6_condensed_direct.py'
                ).resolve()
                try:
                    profile_document = json.loads(profile_path.read_text())
                    worker_environment = {
                        'MYFENICS_CX9Z10_PRELU_PORT_PROFILE_ID': str(
                            gate_profile['profile_id']
                        ),
                        'MYFENICS_CX9Z10_PRELU_PROFILE_PATH': str(profile_path),
                        'MYFENICS_CX9Z10_PRELU_LAUNCHER_PATH': str(launcher_path),
                        'MYFENICS_CX9Z10_PRELU_WORKER_PATH': str(worker_path),
                    }
                    expected_gate_binding = {
                        'schema': 'cx9z10.prelu_launcher_binding.v1',
                        'profile_id': gate_profile['profile_id'],
                        'profile_path': str(profile_path),
                        'profile_sha256': hashlib.sha256(
                            profile_path.read_bytes()
                        ).hexdigest(),
                        'launcher_path': str(launcher_path),
                        'launcher_sha256': hashlib.sha256(
                            launcher_path.read_bytes()
                        ).hexdigest(),
                        'worker_path': str(worker_path),
                        'worker_sha256': hashlib.sha256(
                            worker_path.read_bytes()
                        ).hexdigest(),
                        'worker_environment': worker_environment,
                        'launch_authority': (
                            'external_main_review_and_fresh_gate_required'
                        ),
                    }
                    if (
                        profile_document.get('profile_id')
                        != gate_profile['profile_id']
                        or profile_document.get('state')
                        != 'EXPLICIT_OPT_IN_PENDING_MAIN_PACKAGE_REVIEW'
                        or profile_document.get('target_performance_status')
                        != 'NOT_MEASURED'
                    ):
                        errors.append('CX9Z10 pre-LU profile document identity/state mismatch')
                    if manifest_value.get('pre_lu_port_assembly_gate') != expected_gate_binding:
                        errors.append('CX9Z10 launcher manifest pre-LU gate binding mismatch')
                    for name, expected in worker_environment.items():
                        if os.environ.get(name) != expected:
                            errors.append(
                                f'CX9Z10 worker environment has an invalid {name} binding'
                            )
                except (KeyError, OSError, json.JSONDecodeError, TypeError) as exc:
                    errors.append(
                        f'CX9Z10 pre-LU gate binding could not be validated: {exc}'
                    )
        elif manifest_value.get('pre_lu_port_assembly_gate') is not None:
            errors.append('pre-LU port gate binding is forbidden outside CX9Z10/CX9Z7P5_OOC8')
        elif any(
            os.environ.get(name) is not None
            for name in (
                'MYFENICS_CX9Z10_PRELU_PORT_PROFILE_ID',
                'MYFENICS_CX9Z10_PRELU_PROFILE_PATH',
                'MYFENICS_CX9Z10_PRELU_LAUNCHER_PATH',
                'MYFENICS_CX9Z10_PRELU_WORKER_PATH',
            )
        ):
            errors.append('CX9Z10 pre-LU environment is forbidden outside its target profile')
    if manifest_value.get("execution_mode", "full_solve") != expected_execution_mode:
        errors.append("worker CLI and manifest execution mode mismatch")
    if setup_only:
        from src.io.native_capacity_profile import (
            SETUP_ONLY_5NM_PROFILE,
            setup_only_5nm_identity_errors,
        )

        if contract_probe:
            errors.append("setup-only cannot be combined with a contract probe")
        solver = resolved.get("solver")
        profile = solver.get("preconditioner") if isinstance(solver, dict) else None
        errors.extend(
            setup_only_5nm_identity_errors(
                profile=str(profile or ""),
                method=str(method or ""),
                input_sha256=expected_input_sha256,
                physical_model_sha256=expected_physical_model_sha256,
            )
        )
        expected_setup_contract = {
            "profile": SETUP_ONLY_5NM_PROFILE,
            "input_sha256": expected_input_sha256,
            "physical_model_sha256": expected_physical_model_sha256,
            "completion_marker": "SETUP_ONLY_COMPLETED",
        }
        if manifest_value.get("setup_only_contract") != expected_setup_contract:
            errors.append("manifest setup-only identity contract mismatch")
    elif "setup_only_contract" in manifest_value:
        errors.append("full-solve worker cannot accept a setup-only manifest contract")
    return resolved, errors


def validate_worker_contract(**kwargs: Any) -> list[str]:
    """Validate worker identity without reading the original .dat."""

    _resolved, errors = _load_and_validate_worker_payload(**kwargs)
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="private Task38 worker contract")
    parser.add_argument("--resolved-config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--expected-physical-model-sha256", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--expected-method", required=True)
    parser.add_argument("--expected-adapter", required=True)
    parser.add_argument("--expected-output-directory", type=Path, required=True)
    parser.add_argument("--resolved-config-sha256", required=True)
    parser.add_argument("--contract-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--setup-only", action="store_true")
    return parser


def _dispatch_resolved_payload(
    resolved_payload: dict[str, Any],
    *,
    expected_method: str,
    output_directory: Path,
    expected_source_sha: str | None = None,
    setup_only: bool = False,
    numeric_factor_blas_threads: int | None = None,
    numeric_factor_worker_affinity: list[int] | None = None,
) -> tuple[int, list[str]]:
    """Dispatch the already validated payload without rereading its input."""

    if setup_only and expected_method != "full3d_iterative":
        return 3, ["setup-only is available only through the full3d_iterative worker"]

    if expected_method in {"2d_scattered", "2d_port"}:
        from src.runners.task038_2d import run_2d

        adapter = run_2d
        label = "2D"
    elif expected_method == "full3d_direct":
        from src.io.native_capacity_profile import (
            P6_CONDENSED_DIRECT_PROFILES,
            native_capacity_profile_identity,
        )

        profile_name = native_capacity_profile_identity(
            expected_method, resolved_payload.get('solver', {})
        )
        if profile_name in P6_CONDENSED_DIRECT_PROFILES:
            from src.runners.p6_condensed_direct import run_p6_condensed_direct

            def adapter(payload, directory):
                runner_options = {"source_sha": expected_source_sha}
                if numeric_factor_blas_threads is not None:
                    runner_options["numeric_factor_blas_threads"] = (
                        numeric_factor_blas_threads
                    )
                if numeric_factor_worker_affinity is not None:
                    runner_options["numeric_factor_worker_affinity"] = (
                        numeric_factor_worker_affinity
                    )
                return run_p6_condensed_direct(
                    payload,
                    directory,
                    **runner_options,
                )

            label = "p6 condensed direct"
        else:
            from src.runners.task038_full3d_direct import run_full3d_direct

            adapter = run_full3d_direct
            label = "Full3D direct"
    elif expected_method == "full3d_iterative":
        from src.runners.task038_full3d_iterative import run_full3d_iterative

        def adapter(payload, directory):
            if setup_only:
                return run_full3d_iterative(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                    setup_only=True,
                )
            return run_full3d_iterative(
                payload,
                directory,
                source_sha=expected_source_sha,
            )
        label = "Full3D iterative"
    elif expected_method == "hybrid_direct":
        from src.runners.task038_hybrid_direct import run_hybrid_direct

        def adapter(payload, directory):
            return run_hybrid_direct(
                payload,
                directory,
                source_sha=expected_source_sha,
            )

        label = "Hybrid direct"
    elif expected_method == "hybrid_iterative":
        from src.runners.task038_hybrid_iterative import run_hybrid_iterative

        def adapter(payload, directory):
            return run_hybrid_iterative(
                payload,
                directory,
                source_sha=expected_source_sha,
            )

        label = "Hybrid iterative"
    else:
        return 3, [f"Task38 {expected_method} numerical adapter is unavailable"]

    try:
        result = adapter(resolved_payload, output_directory)
    except Exception as exc:  # convert one worker boundary failure to a nonzero exit
        return 4, [f"Task38 {label} adapter failed: {exc}"]
    if not result["passed"]:
        return 4, list(result["errors"])
    return 0, []


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        from mpi4py import MPI
    except ImportError as exc:
        raise SystemExit(f"Task38 worker requires mpi4py: {exc}") from exc
    comm = MPI.COMM_WORLD
    resolved_payload, errors = _load_and_validate_worker_payload(
        resolved_config=args.resolved_config,
        manifest=args.manifest,
        expected_input_sha256=args.expected_input_sha256,
        expected_physical_model_sha256=args.expected_physical_model_sha256,
        expected_source_sha=args.expected_source_sha,
        expected_mpi_size=args.expected_mpi_size,
        expected_method=args.expected_method,
        expected_adapter=args.expected_adapter,
        expected_output_directory=args.expected_output_directory,
        expected_resolved_config_sha256=args.resolved_config_sha256,
        actual_mpi_size=comm.size,
        contract_probe=args.contract_probe,
        setup_only=args.setup_only,
    )
    failed = comm.allreduce(bool(errors), op=MPI.LOR)
    if failed:
        if comm.rank == 0:
            for error in errors:
                print(f"Task38 worker contract error: {error}")
        return 2
    runtime_cache_evidence = None
    validated_manifest_value = None
    runtime_cache_errors: list[str] = []
    if not args.contract_probe and resolved_payload is not None:
        profile_name = None
        saxs_numeric_profiles = frozenset()
        try:
            from src.io.native_capacity_profile import (
                SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILES,
                TASK40_PHI90_D07C_G6_4_M2_N2_PROFILE,
                native_capacity_profile_identity,
            )

            saxs_numeric_profiles = SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILES

            profile_name = native_capacity_profile_identity(
                resolved_payload.get("method", {}).get("kind"),
                resolved_payload.get("solver", {}),
            )
            from src.runners.task40_d07c_g5_join import (
                G5_PROFILE,
                G6_SCOPED_PROFILES,
                g6_case_for_profile,
            )

            if profile_name == TASK40_PHI90_D07C_G6_4_M2_N2_PROFILE:
                manifest_value, _manifest_bytes, manifest_error = _read_json_bytes(
                    args.manifest, "manifest for small288 numeric-factor dispatch"
                )
                if manifest_error or manifest_value is None:
                    raise ValueError(
                        manifest_error or "small288 manifest is unavailable"
                    )
                validated_manifest_value = manifest_value
            elif profile_name in saxs_numeric_profiles:
                manifest_value, _manifest_bytes, manifest_error = _read_json_bytes(
                    args.manifest, "manifest for SAXS numeric-factor dispatch"
                )
                if manifest_error or manifest_value is None:
                    raise ValueError(
                        manifest_error or "SAXS numeric-factor manifest is unavailable"
                    )
                validated_manifest_value = manifest_value
            elif profile_name == G5_PROFILE or profile_name in G6_SCOPED_PROFILES:
                case = (
                    "G5"
                    if profile_name == G5_PROFILE
                    else g6_case_for_profile(profile_name)
                )
                manifest_value, _manifest_bytes, manifest_error = _read_json_bytes(
                    args.manifest, f"manifest for {case} runtime cache verification"
                )
                if manifest_error or manifest_value is None:
                    raise ValueError(
                        manifest_error or f"{case} manifest is unavailable"
                    )
                validated_manifest_value = manifest_value
                runtime_cache_evidence = _task40_d07c_runtime_cache_evidence(
                    manifest_value
                )
        except (
            ImportError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            failure_scope = (
                "SAXS numeric-factor manifest verification"
                if profile_name in saxs_numeric_profiles
                else "D07C worker manifest/cache verification"
            )
            runtime_cache_errors.append(f"{failure_scope} failed: {exc}")
    cache_failed = comm.allreduce(bool(runtime_cache_errors), op=MPI.LOR)
    if cache_failed:
        if comm.rank == 0:
            for error in runtime_cache_errors:
                print(f"Task38 worker contract error: {error}")
        return 2
    write_errors: list[str] = []
    if comm.rank == 0 and runtime_cache_evidence is not None:
        try:
            _write_d07c_runtime_cache_evidence(
                args.expected_output_directory, runtime_cache_evidence
            )
        except (OSError, TypeError, ValueError) as exc:
            write_errors.append(
                f"D07C runtime-cache evidence could not be persisted: {exc}"
            )
    if comm.allreduce(bool(write_errors), op=MPI.LOR):
        if comm.rank == 0:
            for error in write_errors:
                print(f"Task38 worker contract error: {error}")
        return 2
    if runtime_cache_evidence is not None:
        comm.Barrier()
    if args.contract_probe:
        comm.Barrier()
        if comm.rank == 0:
            marker = args.expected_output_directory / "worker_contract_probe.json"
            marker.write_bytes(
                json.dumps(
                    {"status": "contract_probe_pass", "mpi_size": comm.size},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
        return 0
    if resolved_payload is None:
        return 2
    exit_status, dispatch_errors = _dispatch_resolved_payload(
        resolved_payload,
        expected_method=args.expected_method,
        output_directory=args.expected_output_directory,
        expected_source_sha=args.expected_source_sha,
        setup_only=args.setup_only,
        numeric_factor_blas_threads=(
            None
            if validated_manifest_value is None
            else validated_manifest_value.get("numeric_factor_blas_threads")
        ),
        numeric_factor_worker_affinity=(
            None
            if validated_manifest_value is None
            else validated_manifest_value.get("native_capacity_isolation", {}).get(
                "worker_affinity"
            )
        ),
    )
    if exit_status != 0:
        if comm.rank == 0:
            for error in dispatch_errors:
                print(f"Task38 {args.expected_method} authority error: {error}")
        return exit_status
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "validate_worker_contract"]
