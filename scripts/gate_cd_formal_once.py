"""Fail-closed fresh/systemd entry for the finite Gate-CD signed-window route.

The package binds the selected q21 and mapped-geometry cache witnesses; the
route remains a finite signed rectangle and is not full-DtN qualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SERVICE_PROPERTIES = {
    "Type": "exec",
    "Restart": "no",
    "RuntimeMaxSec": "infinity",
    "KillMode": "mixed",
    "TimeoutStopSec": "infinity",
}
_CAPTURE_ENV = {
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
    "TASK39EXTRA_INT64_ACTIVATION",
    "TASK39EXTRA_PORD64_ACTIVATION",
}


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object: {path}")
    return value


def _atomic_json(path: str | Path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _require_systemd_unit_not_loaded(unit: str, *, timeout_seconds: float = 5.0) -> str:
    """Proceed only when the user manager proves the unique unit is absent."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=LoadState"],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "user systemd did not answer the bounded unit-state query; "
            "cannot prove the reviewed unit is absent"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            "user systemd unit-state query failed; cannot prove the reviewed unit is absent"
        )
    states = [
        line.split("=", 1)[1].strip()
        for line in result.stdout.splitlines()
        if line.startswith("LoadState=")
    ]
    if len(states) != 1 or not states[0]:
        raise RuntimeError(
            "user systemd returned no unique LoadState; cannot prove the reviewed unit is absent"
        )
    if states[0] != "not-found":
        raise ValueError(
            "the exact service unit already exists or has an unknown load state; no duplicate"
        )
    return states[0]


def _require_final_package(package: dict) -> None:
    if package.get("schema") != "task40.gate_cd.formal_package.v1":
        raise ValueError("unsupported Gate-CD final package schema")
    if package.get("execution_authorized") is not True:
        raise ValueError("draft package is not executable")
    readiness = package.get("route_readiness")
    if not isinstance(readiness, dict) or readiness.get("launchable") is not True:
        raise ValueError("Gate-CD profile is not launchable")
    quad = package.get("quadrature_contract")
    if not isinstance(quad, dict):
        raise TypeError("final quadrature contract is missing")
    if quad.get("volume_degree") not in (15, 21, 27):
        raise ValueError("selected volume degree is not a reviewed q15/q21/q27 value")
    if quad.get("surface_degree") != 81 or quad.get("surface_rule") != "default":
        raise ValueError("surface rule differs from the reviewed Gate-CD contract")
    if package.get("mapped_geometry_identity") != "mapped_exact":
        raise ValueError("mapped geometry must retain exact physical-coordinate identity")
    cache_policy = package.get("mapped_geometry_cache_policy")
    if not isinstance(cache_policy, dict):
        raise TypeError("package must bind the exact live mapped-geometry cache policy")
    normalized = package.get("translation_normalized_cache")
    if not isinstance(normalized, bool):
        raise TypeError("translation-normalized cache selection must be boolean")
    if (
        cache_policy.get("geometry_identity_policy")
        != package.get("mapped_geometry_identity")
        or cache_policy.get("mapped_geometry_translation_invariant") is not normalized
    ):
        raise ValueError("package cache identity and translation selection differ")
    if normalized and (
        cache_policy.get("translation_normalized_candidate") is not True
        or cache_policy.get("translation_equivalence_status")
        != "PASS_BOUNDED_TRANSLATION_EQUIVALENCE"
        or not isinstance(cache_policy.get("translation_equivalence_witness"), dict)
    ):
        raise ValueError(
            "translation-normalized cache requires the reviewed bounded witness"
        )


def _validate_live_profile_contract(package: dict, facts: dict) -> None:
    options = facts.get("component_options", {})
    route = facts.get("campaign_authorization", {}).get("direct_route", {})
    quadrature = package.get("quadrature_contract", {})
    surface = options.get("surface_quadrature", {})
    volume = options.get("volume_quadrature", {})
    if (
        surface.get("degree") != quadrature.get("surface_degree")
        or surface.get("rule") != quadrature.get("surface_rule")
        or route.get("surface_quadrature_degree") != surface.get("degree")
    ):
        raise ValueError(
            "live component and campaign surface quadrature differ from the package"
        )
    if (
        volume.get("degree") != quadrature.get("volume_degree")
        or volume.get("rule") != quadrature.get("volume_rule")
        or route.get("volume_quadrature") != volume
    ):
        raise ValueError(
            "live component and campaign volume quadrature/witness differ from the package"
        )

    cache = options.get("mapped_geometry_cache_policy")
    condensed = facts.get("condensed_route", {})
    if not isinstance(cache, dict):
        raise TypeError("live profile has no mapped-geometry cache policy")
    if package.get("mapped_geometry_cache_policy") != cache:
        raise ValueError("package cache policy differs from the exact live profile facts")
    if (
        package.get("mapped_geometry_identity")
        != route.get("geometry_identity_policy")
        or route.get("mapped_geometry_cache_identity") != cache.get("identity")
        or route.get("mapped_geometry_translation_invariant")
        is not cache.get("mapped_geometry_translation_invariant")
        or condensed.get("geometry_identity_policy")
        != cache.get("geometry_identity_policy")
        or condensed.get("mapped_geometry_translation_invariant")
        is not cache.get("mapped_geometry_translation_invariant")
        or package.get("translation_normalized_cache")
        is not cache.get("mapped_geometry_translation_invariant")
    ):
        raise ValueError("live route cache identity differs from package/profile")


def _runtime_reservation_path(sidecar: dict) -> tuple[dict, Path, str]:
    scope_path = Path(sidecar["scope_path"]).resolve()
    raw = scope_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sidecar.get("scope_sha256"):
        raise ValueError("runtime scope changed after fresh acceptance")
    scope = json.loads(raw)
    paths = scope.get("runtime_paths")
    if not isinstance(paths, dict):
        raise TypeError("runtime scope lacks its one-shot reservation path")
    lock_directory = Path(sidecar.get("lock_directory", "")).resolve()
    if Path(paths.get("lock_directory", "")).resolve() != lock_directory:
        raise ValueError("runtime scope lock directory differs from the sidecar")
    raw_path = paths.get("one_shot_reservation")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("runtime one-shot reservation path is invalid")
    reservation_path = Path(raw_path).resolve()
    if reservation_path.parent != lock_directory:
        raise ValueError("runtime reservation is outside the reviewed lock directory")
    return scope, reservation_path, digest


def _wait_for_runtime_cpu_reservation(
    sidecar: dict,
    package: dict,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.2,
) -> tuple[dict, str, str]:
    scope, path, scope_sha = _runtime_reservation_path(sidecar)
    expected_identity = scope.get("identity", {})
    if (
        expected_identity.get("profile_identity") != package.get("profile_identity")
        or expected_identity.get("run_id") != package.get("run_id")
    ):
        raise ValueError("runtime scope profile/run differs from the package")
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "runtime CPU reservation was not committed after systemd submission"
                )
            time.sleep(max(0.01, float(poll_seconds)))
            continue
        try:
            reservation = json.loads(raw)
        except json.JSONDecodeError:
            if time.monotonic() >= deadline:
                raise ValueError(
                    "runtime CPU reservation stayed unreadable after bounded wait"
                )
            time.sleep(max(0.01, float(poll_seconds)))
            continue
        if (
            reservation.get("schema")
            != "task40.gate_cd.formal_one_shot_submission.v1"
            or reservation.get("profile_identity") != package.get("profile_identity")
            or reservation.get("run_id") != package.get("run_id")
            or reservation.get("attempt_id") != scope.get("attempt_id")
            or reservation.get("scope_sha256") != scope_sha
            or reservation.get("submission_mode") != "runtime"
        ):
            raise ValueError("runtime one-shot reservation identity mismatch")
        cpu = reservation.get("cpu_reservation")
        if not isinstance(cpu, dict):
            raise TypeError("runtime one-shot reservation has no CPU record")
        worker_cpus = cpu.get("worker_cpus")
        if not isinstance(worker_cpus, list) or not worker_cpus:
            worker = cpu.get("worker_cpu")
            if not isinstance(worker, int):
                raise ValueError("runtime CPU reservation has no worker CPU")
            worker_cpus = [worker]
        if any(not isinstance(value, int) or value < 0 for value in worker_cpus):
            raise ValueError("runtime worker CPU reservation is invalid")
        if len(worker_cpus) != 1:
            raise ValueError("Gate-CD runtime lease must reserve exactly one worker CPU")
        if cpu.get("worker_cpu") != worker_cpus[0]:
            raise ValueError("runtime worker_cpu and worker_cpus disagree")
        supervisor_cpu = cpu.get("supervisor_cpu")
        if not isinstance(supervisor_cpu, int) or supervisor_cpu == worker_cpus[0]:
            raise ValueError("runtime supervisor/worker CPU reservation is invalid")
        return reservation, hashlib.sha256(raw).hexdigest(), scope_sha


def validate_package_sidecar(
    package_path: str | Path, sidecar_path: str | Path
) -> tuple[dict, dict, str, str]:
    package_path = Path(package_path).resolve()
    sidecar_path = Path(sidecar_path).resolve()
    package = _load_json(package_path)
    sidecar = _load_json(sidecar_path)
    package_sha = sha256_file(package_path)
    sidecar_sha = sha256_file(sidecar_path)
    _require_final_package(package)
    if sidecar.get("schema") != "task40.gate_cd.formal_sidecar.v1":
        raise ValueError("unsupported Gate-CD sidecar schema")
    if sidecar.get("package_sha256") != package_sha:
        raise ValueError("sidecar does not bind the exact package bytes")
    if sidecar.get("source_commit") != package.get("source_commit"):
        raise ValueError("package/sidecar source identity mismatch")
    if sidecar.get("input_sha256") != package.get("input_sha256"):
        raise ValueError("package/sidecar input identity mismatch")
    if sidecar.get("physical_model_sha256") != package.get("physical_model_sha256"):
        raise ValueError("package/sidecar physical identity mismatch")
    if sidecar.get("resolved_config_sha256") != package.get("resolved_config_sha256"):
        raise ValueError("package/sidecar resolved identity mismatch")
    return package, sidecar, package_sha, sidecar_sha


def _git_text(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _expected_identity(specification, profile: str, source_commit: str) -> dict:
    from src.io.input_validation import _jsonable
    from src.io.native_capacity_profile import native_profile_facts
    from src.io.resolved_config import resolved_config_sha256

    return {
        "profile_identity": profile,
        "run_id": specification.identity.get("run_id"),
        "input_path": str(Path(specification.source_path).resolve()),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_config_sha256(specification),
        "resolved_output_parent_absolute": str(
            specification.expected_output_parent.resolve()
        ),
        "source_commit": source_commit,
        "direct_route_contract": _jsonable(
            native_profile_facts(profile)["campaign_authorization"]["direct_route"]
        ),
    }


def fresh_acceptance(
    package_path: str | Path, sidecar_path: str | Path, output_path: str | Path
) -> dict:
    package, sidecar, package_sha, sidecar_sha = validate_package_sidecar(
        package_path, sidecar_path
    )
    root = REPO_ROOT.resolve()
    if Path.cwd().resolve() != root:
        raise ValueError("fresh check must run from the exact repository root")
    source_commit = _git_text(root, "rev-parse", "HEAD")
    if source_commit != package.get("source_commit"):
        raise ValueError("source HEAD differs from the frozen package")
    if _git_text(root, "status", "--porcelain"):
        raise ValueError("source worktree is not clean")
    for rel, expected in package.get("source_file_sha256", {}).items():
        if sha256_file(root / rel) != expected:
            raise ValueError(f"bound source file changed: {rel}")
    from src.io import load_and_resolve
    from src.io.native_capacity_profile import (
        native_capacity_profile_identity,
        native_profile_facts,
    )
    from src.runners.native_capacity import native_capacity_guard
    from src.runners.task40_gate_cd_formal_admission import (
        GATE_CD_FORMAL_PROFILE,
        GATE_CD_LOCK_DIRECTORY_ENV,
        GATE_CD_SCOPE_PATH_ENV,
        GATE_CD_SCOPE_SHA_ENV,
        GATE_CD_SUBMISSION_MODE_ENV,
    )

    dat_path = Path(package["input_path"]).resolve()
    if sha256_file(dat_path) != package.get("input_sha256"):
        raise ValueError("input bytes differ from the frozen package")
    specification = load_and_resolve(dat_path)
    profile = native_capacity_profile_identity(
        specification.method.get("kind"), specification.solver
    )
    if profile != GATE_CD_FORMAL_PROFILE or profile != package.get("profile_identity"):
        raise ValueError("resolved input is not the exact Gate-CD formal profile")
    facts = native_profile_facts(profile)
    readiness = facts.get("component_options", {}).get("route_readiness", {})
    if readiness.get("launchable") is not True:
        raise ValueError("live profile readiness is still fail-closed")
    _validate_live_profile_contract(package, facts)
    actual = _expected_identity(specification, profile, source_commit)
    if actual != package.get("identity"):
        raise ValueError("actual standard-loader identity differs from the package")
    if actual["physical_model_sha256"] != package.get("physical_model_sha256"):
        raise ValueError("physical-model hash differs from the package")
    output_parent = Path(sidecar["expected_output_parent"]).resolve()
    if str(output_parent) != actual["resolved_output_parent_absolute"]:
        raise ValueError("sidecar output parent differs from the formal loader")
    if output_parent.exists() and any(output_parent.iterdir()):
        raise ValueError("formal output parent is not empty; refusing a duplicate/overwrite")
    _require_systemd_unit_not_loaded(str(sidecar["service_unit"]))
    scope_path = Path(sidecar["scope_path"]).resolve()
    old_env = {
        key: os.environ.get(key)
        for key in (
            GATE_CD_SCOPE_PATH_ENV,
            GATE_CD_SCOPE_SHA_ENV,
            GATE_CD_LOCK_DIRECTORY_ENV,
            GATE_CD_SUBMISSION_MODE_ENV,
        )
    }
    os.environ[GATE_CD_SCOPE_PATH_ENV] = str(scope_path)
    os.environ[GATE_CD_SCOPE_SHA_ENV] = str(sidecar["scope_sha256"])
    os.environ[GATE_CD_LOCK_DIRECTORY_ENV] = str(sidecar["lock_directory"])
    os.environ[GATE_CD_SUBMISSION_MODE_ENV] = "fresh_check"
    try:
        with native_capacity_guard(
            profile,
            memory_policy=specification.execution.get(
                "native_memory_policy", "none"
            ),
            task_run_id=specification.identity.get("run_id"),
            submission_mode="fresh_check",
            expected_identity=actual,
        ) as (_root, isolation):
            result = {
                "schema": "task40.gate_cd.formal_fresh_receipt.v1",
                "captured_utc": datetime.now(timezone.utc).isoformat(),
                "fresh_pass": True,
                "launch_not_started": True,
                "package_sha256": package_sha,
                "sidecar_sha256": sidecar_sha,
                "source_commit": source_commit,
                "input_sha256": actual["input_sha256"],
                "physical_model_sha256": actual["physical_model_sha256"],
                "resolved_config_sha256": actual["resolved_config_sha256"],
                "run_id": actual["run_id"],
                "profile_identity": profile,
                "host_and_lease_facts": isolation,
                "no_FE_or_factor_started": True,
            }
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    _atomic_json(output_path, result)
    return result


def _validate_systemd_argv(sidecar: dict) -> list[str]:
    argv = sidecar.get("systemd_run_argv")
    unit = sidecar.get("service_unit")
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ValueError("sidecar systemd_run_argv must be an exact string array")
    if not isinstance(unit, str) or not unit.endswith(".service"):
        raise ValueError("sidecar service unit is invalid")
    if argv[:3] != ["systemd-run", "--user", "--no-block"]:
        raise ValueError("only the reviewed one-shot user-systemd mode is accepted")
    if not any(x in argv for x in (f"--unit={unit}",)) and not (
        "--unit" in argv and argv[argv.index("--unit") + 1 : argv.index("--unit") + 2] == [unit]
    ):
        raise ValueError("systemd argv does not bind the unique service unit")
    for key, value in _SERVICE_PROPERTIES.items():
        if f"--property={key}={value}" not in argv:
            raise ValueError(f"systemd service property differs: {key}")
    if len(argv) < 3 or argv[-3:-1] != ["/bin/bash", "-lc"]:
        raise ValueError("systemd argv must end in the reviewed bash -lc command")
    argv_shell_command = argv[-1]
    declared_shell_command = sidecar.get("shell_command")
    if declared_shell_command != argv_shell_command:
        raise ValueError("sidecar shell_command differs from the actual systemd argv")
    if "scripts/run_case.py" not in argv_shell_command:
        raise ValueError("service must call the standard run_case entry")
    if "src.runners.task038_input_worker" in argv_shell_command:
        raise ValueError("sidecar cannot bypass run_case and invoke the worker directly")
    output = sidecar.get("append_log_path")
    if not isinstance(output, str) or not Path(output).is_absolute():
        raise ValueError("systemd append log path must be absolute")
    if f"--property=StandardOutput=append:{output}" not in argv:
        raise ValueError("stdout must append to the reviewed persistent log")
    if f"--property=StandardError=append:{output}" not in argv:
        raise ValueError("stderr must append to the reviewed persistent log")
    environment = sidecar.get("service_environment")
    if not isinstance(environment, dict):
        raise TypeError("sidecar service_environment must be explicit")
    required_env = {
        "HWLOC_COMPONENTS": "-x86",
        "TASK40_GATE_CD_SCOPE_PATH": sidecar.get("scope_path"),
        "TASK40_GATE_CD_SCOPE_SHA256": sidecar.get("scope_sha256"),
        "TASK40_GATE_CD_LOCK_DIRECTORY": sidecar.get("lock_directory"),
        "TASK40_GATE_CD_SUBMISSION_MODE": "runtime",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    for key, expected in required_env.items():
        if not isinstance(expected, str) or environment.get(key) != expected:
            raise ValueError(f"sidecar launch environment differs for {key}")
        if f"--setenv={key}={expected}" not in argv:
            raise ValueError(f"systemd argv does not pass exact environment {key}")
    activation_env = (
        "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
        "TASK39EXTRA_INT64_ACTIVATION",
        "TASK39EXTRA_PORD64_ACTIVATION",
    )
    for key in activation_env:
        if environment.get(key) != "1" or f"--setenv={key}=1" not in argv:
            raise ValueError(f"systemd argv lacks qualified activation marker {key}")
    activation_script = sidecar.get("activation_script")
    shell_command = sidecar.get("shell_command")
    if not isinstance(activation_script, str) or not Path(activation_script).is_absolute():
        raise ValueError("qualified activation script path must be absolute")
    if not isinstance(shell_command, str) or activation_script not in argv_shell_command:
        raise ValueError("service shell must source the exact qualified activation script")
    if "exec python scripts/run_case.py" not in argv_shell_command:
        raise ValueError("service shell must exec the standard run_case entry")
    return argv


def _service_properties(unit: str) -> dict[str, str]:
    names = (
        "LoadState", "ActiveState", "SubState", "MainPID", "InvocationID",
        "ControlGroup", "Result", "ExecMainCode", "ExecMainStatus", "ExecStart",
    )
    result = subprocess.run(
        ["systemctl", "--user", "show", unit, *[f"--property={x}" for x in names]],
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


def _process_identity(pid: int) -> dict | None:
    proc = Path("/proc") / str(pid)
    try:
        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        status = (proc / "status").read_text()
        argv = [
            x.decode(errors="replace")
            for x in (proc / "cmdline").read_bytes().split(b"\0")
            if x
        ]
        env = {}
        for item in (proc / "environ").read_bytes().split(b"\0"):
            if b"=" not in item:
                continue
            raw_key, raw_value = item.split(b"=", 1)
            key = raw_key.decode(errors="replace")
            if key in _CAPTURE_ENV:
                env[key] = raw_value.decode(errors="replace")
        allowed = next(
            (
                x.split(":", 1)[1].strip()
                for x in status.splitlines()
                if x.startswith("Cpus_allowed_list:")
            ),
            None,
        )
        cgroup = (proc / "cgroup").read_text()
        cg_path = next(
            (x.split(":", 2)[2] for x in cgroup.splitlines() if x.count(":") >= 2),
            None,
        )
        petsc = []
        with (proc / "maps").open() as stream:
            for line in stream:
                if "libpetsc" in line and "/" in line:
                    value = line.split()[-1]
                    if value not in petsc:
                        petsc.append(value)
        numa = {"lines": 0, "interleave_0_1_vmas": 0, "default_vmas": 0}
        with (proc / "numa_maps").open() as stream:
            for line in stream:
                numa["lines"] += 1
                tokens = line.split()
                numa["interleave_0_1_vmas"] += int(
                    "interleave:0-1" in tokens
                )
                numa["default_vmas"] += int("default" in tokens)
        threads = []
        task_dir = proc / "task"
        for tid_path in sorted(
            (p for p in task_dir.iterdir() if p.name.isdigit()),
            key=lambda p: int(p.name),
        ):
            tid = int(tid_path.name)
            try:
                task_stat = (tid_path / "stat").read_text().rsplit(")", 1)[1].split()
                task_status = (tid_path / "status").read_text()
                thread_cpus = next(
                    (
                        row.split(":", 1)[1].strip()
                        for row in task_status.splitlines()
                        if row.startswith("Cpus_allowed_list:")
                    ),
                    None,
                )
                threads.append(
                    {
                        "tid": tid,
                        "start_ticks": int(task_stat[19]),
                        "state": task_stat[0],
                        "cpus_allowed_list": thread_cpus,
                    }
                )
            except (OSError, ValueError, IndexError):
                continue
        return {
            "pid": pid,
            "start_ticks": int(fields[19]),
            "state": fields[0],
            "ppid": int(fields[1]),
            "argv": argv,
            "cwd": os.readlink(proc / "cwd"),
            "cpus_allowed_list": allowed,
            "cgroup": cgroup,
            "cgroup_path": cg_path,
            "environment": env,
            "threads": threads,
            "numa_maps_summary": numa,
            "libpetsc_mappings": petsc,
        }
    except (OSError, ValueError, IndexError):
        return None


def capture_unit(unit: str) -> dict:
    props = _service_properties(unit)
    mainpid = int(props.get("MainPID", "0") or 0)
    cgroup = props.get("ControlGroup", "")
    cg_procs = Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "cgroup.procs"
    pids = [int(x) for x in cg_procs.read_text().split()] if cgroup else []
    identities = [
        identity
        for pid in pids
        if (identity := _process_identity(pid)) is not None
    ]
    roles = {"root": [], "mpi": [], "worker": []}
    for identity in identities:
        argv = identity["argv"]
        if any(x.endswith("scripts/run_case.py") for x in argv):
            roles["root"].append(identity)
        elif any(Path(x).name in {"mpiexec", "mpirun", "orted"} for x in argv):
            roles["mpi"].append(identity)
        elif "-m" in argv and "src.runners.task038_input_worker" in argv:
            roles["worker"].append(identity)
    return {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "unit": unit,
        "unit_properties": props,
        "main_pid_identity": _process_identity(mainpid) if mainpid else None,
        "control_group_processes": identities,
        "roles": roles,
    }


def _require_live_capture(
    capture: dict, repo_root: Path, expected_worker_cpus: list[int], math_threads: int
) -> None:
    props = capture["unit_properties"]
    root = capture["roles"]["root"]
    mpi = capture["roles"]["mpi"]
    workers = capture["roles"]["worker"]
    mainpid = int(props.get("MainPID", "0") or 0)
    if not props.get("InvocationID") or not props.get("ControlGroup"):
        raise ValueError("submitted service has no InvocationID/cgroup identity")
    if len(root) != 1 or root[0]["pid"] != mainpid or not mpi or len(workers) != 1:
        raise ValueError("service cgroup does not contain one exact root, MPI, and worker")
    if root[0]["cwd"] != str(repo_root.resolve()):
        raise ValueError("run_case root cwd differs from the frozen worktree")
    mpi_pids = {int(item["pid"]) for item in mpi}
    if root[0]["ppid"] != int(capture["main_pid_identity"]["ppid"]):
        raise ValueError("run_case parent identity differs from the captured systemd MainPID")
    if not any(item["ppid"] == mainpid for item in mpi):
        raise ValueError("MPI launcher is not a child of the run_case root")
    if not any(item["ppid"] in mpi_pids for item in workers):
        raise ValueError("worker is not a child of the observed MPI launcher")
    worker = workers[0]
    expected_cpu_text = ",".join(str(cpu) for cpu in expected_worker_cpus)
    if worker["cpus_allowed_list"] != expected_cpu_text:
        raise ValueError("worker CPU affinity differs from committed runtime CPU lease")
    if not worker["threads"] or any(
        row["cpus_allowed_list"] != expected_cpu_text for row in worker["threads"]
    ):
        raise ValueError("worker thread CPU affinity differs from committed runtime lease")
    if len(worker["threads"]) < math_threads:
        raise ValueError("worker has fewer threads than its math-thread contract")
    if not any("pord64-overlay" in p for p in worker["libpetsc_mappings"]):
        raise ValueError("worker has not mapped the qualified PORD64 PETSc")
    if worker["numa_maps_summary"]["interleave_0_1_vmas"] < 1:
        raise ValueError("worker NUMA interleave:0-1 has not been observed")
    if worker["environment"].get("OMP_NUM_THREADS") != "1":
        raise ValueError("worker math-thread contract has not been read back")
    if any(worker["environment"].get(name) != "1" for name in _CAPTURE_ENV - {
        "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
        "TASK39EXTRA_INT64_ACTIVATION",
        "TASK39EXTRA_PORD64_ACTIVATION",
    }):
        raise ValueError("worker math environment differs from one-thread contract")
    if any(
        worker["environment"].get(name) != "1"
        for name in (
            "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
            "TASK39EXTRA_INT64_ACTIVATION",
            "TASK39EXTRA_PORD64_ACTIVATION",
        )
    ):
        raise ValueError("worker qualified ABI activation markers are incomplete")


def _write_once_marker(marker: Path, data: dict) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def submit_once(
    package_path: str | Path,
    sidecar_path: str | Path,
    fresh_receipt_path: str | Path,
    review_path: str | Path,
    marker_path: str | Path,
    start_receipt_path: str | Path,
    live_receipt_path: str | Path,
    *,
    run_command=subprocess.run,
) -> dict:
    package, sidecar, package_sha, sidecar_sha = validate_package_sidecar(
        package_path, sidecar_path
    )
    review = _load_json(review_path)
    fresh = _load_json(fresh_receipt_path)
    review_bindings = review.get("bindings", review)
    review_status = review.get("decision", review.get("status"))
    if review_status != "PASS_GATE_CD_SYSTEMD_AND_FRESH":
        raise ValueError("main review is not the Gate-CD fresh/systemd PASS")
    if review_bindings.get("package_sha256") != package_sha:
        raise ValueError("main review does not bind this package")
    if review_bindings.get("sidecar_sha256") != sidecar_sha:
        raise ValueError("main review does not bind this sidecar")
    for key in (
        "source_commit",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
    ):
        if review_bindings.get(key) != package.get(key):
            raise ValueError(f"main review does not bind {key}")
    if not fresh.get("fresh_pass") or fresh.get("launch_not_started") is not True:
        raise ValueError("a matching fresh PASS receipt is required")
    if (
        fresh.get("package_sha256") != package_sha
        or fresh.get("sidecar_sha256") != sidecar_sha
        or fresh.get("source_commit") != package.get("source_commit")
        or fresh.get("input_sha256") != package.get("input_sha256")
        or fresh.get("physical_model_sha256") != package.get("physical_model_sha256")
        or fresh.get("resolved_config_sha256")
        != package.get("resolved_config_sha256")
    ):
        raise ValueError("fresh receipt package/source identity mismatch")
    argv = _validate_systemd_argv(sidecar)
    unit = sidecar["service_unit"]
    _require_systemd_unit_not_loaded(unit)
    marker = Path(marker_path)
    _write_once_marker(
        marker,
        {
            "schema": "task40.gate_cd.formal_systemd_submission_once.v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "service_unit": unit,
            "package_sha256": package_sha,
            "sidecar_sha256": sidecar_sha,
            "fresh_receipt_sha256": sha256_file(fresh_receipt_path),
            "main_review_sha256": sha256_file(review_path),
            "systemd_submitted": False,
            "automatic_retry": False,
        },
    )
    completed = run_command(argv, text=True, capture_output=True, timeout=60)
    start = {
        "schema": "task40.gate_cd.formal_systemd_start_receipt.v1",
        "submitted_utc": datetime.now(timezone.utc).isoformat(),
        "service_unit": unit,
        "systemd_run_argv": argv,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "package_sha256": package_sha,
        "sidecar_sha256": sidecar_sha,
        "source_commit": package["source_commit"],
        "automatic_retry": False,
    }
    _atomic_json(start_receipt_path, start)
    if completed.returncode != 0:
        raise RuntimeError(
            "systemd submission failed after consuming one-shot marker; no retry"
        )
    marker_data = _load_json(marker)
    marker_data["systemd_submitted"] = True
    marker_data["systemd_returncode"] = int(completed.returncode)
    _atomic_json(marker, marker_data)
    try:
        runtime_reservation, reservation_sha, scope_sha = (
            _wait_for_runtime_cpu_reservation(sidecar, package)
        )
        runtime_cpu = runtime_reservation["cpu_reservation"]
        runtime_worker_cpus = runtime_cpu.get("worker_cpus")
        if not isinstance(runtime_worker_cpus, list) or not runtime_worker_cpus:
            runtime_worker_cpus = [runtime_cpu["worker_cpu"]]
        worker_cpus = [int(cpu) for cpu in runtime_worker_cpus]
        start["runtime_cpu_reservation"] = runtime_reservation
        start["runtime_cpu_reservation_sha256"] = reservation_sha
        start["runtime_scope_sha256"] = scope_sha
        start["affinity_authority"] = (
            "committed_runtime_one_shot_reservation_not_fresh_sample"
        )
        start["cpu_exclusive_ownership"] = False
        _atomic_json(start_receipt_path, start)
    except (OSError, ValueError, TimeoutError, KeyError) as exc:
        start["live_identity_verified"] = False
        start["live_capture_error"] = str(exc)
        start["passive_capture_required"] = True
        start["submission_was_not_repeated"] = True
        _atomic_json(start_receipt_path, start)
        raise RuntimeError(
            "systemd submitted once but runtime CPU lease is not yet readable; "
            "passively inspect this unit, never resubmit"
        ) from exc
    try:
        capture = capture_unit(unit)
        if not worker_cpus:
            raise ValueError("runtime reservation does not bind selected worker CPUs")
        capture["runtime_cpu_reservation"] = runtime_reservation
        capture["runtime_cpu_reservation_sha256"] = reservation_sha
        capture["fresh_worker_affinity_sample_is_not_authoritative"] = True
        _require_live_capture(
            capture,
            REPO_ROOT,
            worker_cpus,
            int(package.get("math_threads", 1)),
        )
        _atomic_json(live_receipt_path, capture)
        start["live_identity_verified"] = True
        start["live_receipt_sha256"] = sha256_file(live_receipt_path)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        start["live_identity_verified"] = False
        start["live_capture_error"] = str(exc)
        start["passive_capture_required"] = True
        _atomic_json(start_receipt_path, start)
        raise RuntimeError(
            "systemd submitted once but live capture is incomplete; passively recapture same unit, never resubmit"
        ) from exc
    _atomic_json(start_receipt_path, start)
    return start


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fresh = sub.add_parser("fresh")
    fresh.add_argument("--package", required=True)
    fresh.add_argument("--sidecar", required=True)
    fresh.add_argument("--output", required=True)
    launch = sub.add_parser("submit")
    launch.add_argument("--package", required=True)
    launch.add_argument("--sidecar", required=True)
    launch.add_argument("--fresh-receipt", required=True)
    launch.add_argument("--main-review", required=True)
    launch.add_argument("--marker", required=True)
    launch.add_argument("--start-receipt", required=True)
    launch.add_argument("--live-receipt", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--unit", required=True)
    capture.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "fresh":
            result = fresh_acceptance(args.package, args.sidecar, args.output)
        elif args.command == "submit":
            result = submit_once(
                args.package,
                args.sidecar,
                args.fresh_receipt,
                args.main_review,
                args.marker,
                args.start_receipt,
                args.live_receipt,
            )
        else:
            result = capture_unit(args.unit)
            _atomic_json(args.output, result)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Gate-CD execution helper refused/failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
