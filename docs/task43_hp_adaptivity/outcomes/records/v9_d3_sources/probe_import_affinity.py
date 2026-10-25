#!/usr/bin/env python3
"""One-shot traced ABI import and bounded S2 fixture run."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
import time
from pathlib import Path


ROOT = Path(os.environ["TASK43_V6_D2_ROOT"])
TRACE_PREFIX = Path(os.environ["TASK43_V6_D2_TRACE_PREFIX"])
STAGE_LOG = ROOT / "probe_stages.jsonl"
TERMINAL = ROOT / "probe_terminal.json"
REPO = Path("/home/fenics/Projects/NN-Lab-V2")
ENVIRONMENT_RECORD = REPO / "docs/task43_hp_adaptivity/outcomes/records/workspace_environment_v1.json"
NODE_CAP_BYTES = 8_589_934_592
TARGETED_NODEIDS = (
    "src/test/test_task43_v3_failure_safe_order.py::test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle",
    "src/test/test_task43_v3_failure_safe_order.py::test_synthetic_joint_authority_fixture_rejects_common_missing_identity",
    "src/test/test_task43_v3_failure_safe_order.py::test_synthetic_joint_authority_fixture_rejects_each_failure_independently",
    "src/test/test_task43_v3_failure_safe_order.py::test_a2_postprocess_writer_failures_keep_original_error_and_primary",
)


def _proc_identity() -> dict[str, object]:
    raw = Path(f"/proc/{os.getpid()}/stat").read_text(encoding="utf-8")
    tail = raw[raw.rfind(")") + 2 :].split()
    return {
        "pid": os.getpid(),
        "ppid": int(tail[1]),
        "start_ticks": int(tail[19]),
    }


def _trace_files() -> list[Path]:
    return sorted(Path(TRACE_PREFIX.parent).glob(TRACE_PREFIX.name + ".*"))


def _read_trace() -> tuple[list[tuple[Path, str]], list[str]]:
    lines: list[tuple[Path, str]] = []
    errors: list[str] = []
    files = _trace_files()
    if not files:
        errors.append("strace produced no per-process trace files")
    for path in files:
        try:
            lines.extend((path, line) for line in path.read_text(encoding="utf-8").splitlines())
        except OSError as exc:
            errors.append(f"cannot read {path}: {type(exc).__name__}: {exc}")
    return lines, errors


def _successful_setters(lines: list[tuple[Path, str]]) -> tuple[list[dict[str, str]], list[str]]:
    found: list[dict[str, str]] = []
    unknown: list[str] = []
    for path, line in lines:
        if "sched_setaffinity" not in line or line.lstrip().startswith(">"):
            continue
        # D3 is conservative: any incomplete, resumed, failed or unknown setter
        # record stops continuation; unwind-stack symbol mentions are not calls.
        match = re.fullmatch(
            r"\s*\d+\.\d+\s+sched_setaffinity\(-?\d+,\s*\d+,\s*"
            r"\[(\d+(?:\s+\d+)*)\]\)\s+=\s+0\s*",
            line,
        )
        if match is None:
            unknown.append(f"{path.name}: {line}")
            continue
        cpus = [int(item) for item in match.group(1).split()]
        found.append({"trace_file": path.name, "cpus": json.dumps(cpus), "line": line})
    return found, unknown


def _append(record: dict[str, object]) -> None:
    with STAGE_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _snapshot(stage: str, module: str | None = None) -> tuple[bool, str]:
    tids: list[int] = []
    affinity_by_tid: dict[str, list[int]] = {}
    unreadable_tids: dict[str, str] = {}
    try:
        tids = sorted(int(value) for value in os.listdir("/proc/self/task"))
    except OSError as exc:
        unreadable_tids["/proc/self/task"] = f"{type(exc).__name__}: {exc}"

    own_trace = Path(f"{TRACE_PREFIX}.{os.getpid()}")
    try:
        prior_getaffinity_count = own_trace.read_text(encoding="utf-8").count(
            "sched_getaffinity("
        )
    except OSError:
        prior_getaffinity_count = 0
    for tid in tids:
        try:
            affinity_by_tid[str(tid)] = sorted(os.sched_getaffinity(tid))
        except OSError as exc:
            unreadable_tids[str(tid)] = f"{type(exc).__name__}: {exc}"

    deadline = time.monotonic() + 1.5
    trace_sync = False
    while time.monotonic() < deadline:
        try:
            content = own_trace.read_text(encoding="utf-8")
        except OSError:
            content = ""
        if content.count("sched_getaffinity(") >= prior_getaffinity_count + len(tids):
            trace_sync = True
            break
        time.sleep(0.01)

    lines, trace_errors = _read_trace()
    setters, unknown_setters = _successful_setters(lines)
    record: dict[str, object] = {
        "stage": stage,
        "module": module,
        "hwloc_components": os.environ.get("HWLOC_COMPONENTS"),
        "ompi_mca_pml": os.environ.get("OMPI_MCA_pml"),
        **_proc_identity(),
        "tids": tids,
        "affinity_by_tid": affinity_by_tid,
        "unreadable_tids": unreadable_tids,
        "trace_sync": trace_sync,
        "trace_files": [path.name for path in _trace_files()],
        "trace_errors": trace_errors,
        "successful_sched_setaffinity_events": setters,
        "unclassified_setter_records": unknown_setters,
    }
    _append(record)

    if not trace_sync:
        return False, "trace output did not synchronously expose the getaffinity barrier"
    if os.environ.get("HWLOC_COMPONENTS") != "-x86":
        return False, "HWLOC_COMPONENTS was not set to the reviewed scoped value -x86"
    if os.environ.get("OMPI_MCA_pml") != "ob1":
        return False, "OMPI_MCA_pml was not set to the reviewed scoped value ob1"
    if trace_errors or unreadable_tids or not tids:
        return False, "stage process/thread identity or trace was unreadable"
    if unknown_setters:
        return False, "affinity setter record was failed, incomplete or outside the reviewed grammar"
    if any(json.loads(event["cpus"]) != [1] for event in setters):
        return False, "successful sched_setaffinity event selected a mask other than [1]"
    if any(mask != [1] for mask in affinity_by_tid.values()):
        return False, "a readable stage TID did not have affinity [1]"
    return True, "ok"


def _finish(status: str, reason: str, exit_code: int) -> int:
    payload = {
        "schema": "task43.v6.affinity_import_probe.v1",
        "status": status,
        "reason": reason,
        "exit_code": exit_code,
        "pytest_mode": (
            "targeted S2 fixture cases; no mesh/solver/PDE"
            if status in {
                "FIXTURE_TESTS_PASSED",
                "FIXTURE_TESTS_FAILED",
                "FIXTURE_TESTS_AFFINITY_LIMITED",
            }
            else "not_run"
        ),
    }
    TERMINAL.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return exit_code


def _native_abi_check() -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    record = json.loads(ENVIRONMENT_RECORD.read_text(encoding="utf-8"))
    import dolfinx
    import mpi4py
    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc
    import petsc4py
    from benchmarks.subreaper_watchdog import memory_envelope

    modules = {
        "dolfinx": Path(dolfinx.__file__).absolute(),
        "mpi4py": Path(mpi4py.__file__).absolute(),
        "numpy": Path(np.__file__).absolute(),
        "petsc4py": Path(petsc4py.__file__).absolute(),
    }
    raw_mpi_library = MPI.Get_library_version()
    normalized_mpi_library = raw_mpi_library.strip().rstrip("\x00")
    expected_mpi_library = record["mpi_library"].strip().rstrip("\x00")
    envelope = memory_envelope()
    actual = {
        "executable": str(Path(sys.executable).absolute()),
        "activation_marker": os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION"),
        "petsc_scalar": np.dtype(PETSc.ScalarType).name,
        "petsc_integer": np.dtype(PETSc.IntType).name,
        "numpy_version": np.__version__,
        "petsc_version": list(PETSc.Sys.getVersion()),
        "mpi_size": MPI.COMM_WORLD.size,
        "mpi_library_raw": raw_mpi_library,
        "mpi_library_normalized": normalized_mpi_library,
        "hwloc_components": os.environ.get("HWLOC_COMPONENTS"),
        "module_paths": {name: str(path) for name, path in modules.items()},
        "affinity": sorted(os.sched_getaffinity(0)),
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
            )
        },
        "capacity_identity": os.environ.get("PHYSICAL_NATIVE_CAPACITY"),
        "node_cap_bytes": os.environ.get("PHYSICAL_NATIVE_NODE_CAP_BYTES"),
        "memory_envelope": envelope,
    }

    if actual["executable"] != str(Path(record["executable"]).absolute()):
        failures.append("python executable differs from the frozen environment record")
    if actual["activation_marker"] != "1":
        failures.append("qualified native activation marker is missing")
    if actual["petsc_scalar"] != "complex128":
        failures.append("PETSc scalar type is not complex128")
    if actual["petsc_integer"] != "int64":
        failures.append("PETSc integer type is not int64")
    if actual["petsc_version"] != record["petsc_version"]:
        failures.append("PETSc version differs from the frozen environment record")
    if str(modules["numpy"]) != str(Path(record["modules"]["numpy"])):
        failures.append("numpy module path differs from the frozen environment record")
    if actual["mpi_size"] != 1:
        failures.append("MPI world size is not one")
    if normalized_mpi_library != expected_mpi_library:
        failures.append("MPI library differs from the frozen environment record")
    for name, path in modules.items():
        if path != Path(record["modules"][name]):
            failures.append(f"{name} module path differs from the frozen environment record")
    if actual["affinity"] != [1]:
        failures.append("ABI preflight affinity is not exactly CPU1")
    if actual["hwloc_components"] != "-x86":
        failures.append("HWLOC_COMPONENTS is not the reviewed scoped value -x86")
    if any(value != "1" for value in actual["thread_environment"].values()):
        failures.append("one or more numerical thread limits are not one")
    if actual["capacity_identity"] != "task43_hp_adaptivity_resource_v1":
        failures.append("native capacity profile identity differs")
    if actual["node_cap_bytes"] != str(NODE_CAP_BYTES):
        failures.append("native per-node cap differs from 8 GiB")
    if envelope.get("resource_profile_identity") != "task43_hp_adaptivity_resource_v1":
        failures.append("memory envelope profile identity differs")
    launch_cap = int(envelope.get("launch_cap_bytes") or 0)
    planning_cap = int(envelope.get("planning_cap_bytes") or 0)
    if not (0 < planning_cap <= launch_cap <= NODE_CAP_BYTES):
        failures.append("memory envelope planning/launch cap is invalid")
    return actual, failures


def main() -> int:
    if Path.cwd() != REPO:
        return _finish("FAILED", "probe was not launched from repository root", 20)
    native_modules = ("dolfinx", "mpi4py", "numpy", "petsc4py")
    preloaded = [name for name in native_modules if name in sys.modules]
    ok, reason = _snapshot("python_startup_before_explicit_native_imports")
    _append(
        {
            "stage": "native_module_preload_check",
            **_proc_identity(),
            "already_loaded_native_modules": preloaded,
        }
    )
    if preloaded:
        return _finish(
            "STOPPED_BEFORE_IMPORT",
            f"native modules loaded before the traced explicit import sequence: {preloaded}",
            19,
        )
    if not ok:
        return _finish("STOPPED_BEFORE_IMPORT", reason, 21)

    imports = (
        "dolfinx",
        "mpi4py",
        "numpy",
        "mpi4py.MPI",
        "petsc4py.PETSc",
        "petsc4py",
    )
    for module_name in imports:
        try:
            importlib.import_module(module_name)
        except BaseException as exc:  # Preserve exact native import failure as a probe result.
            _append(
                {
                    "stage": "native_import_failed",
                    "module": module_name,
                    **_proc_identity(),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                }
            )
            return _finish("IMPORT_FAILED", f"{module_name}: {type(exc).__name__}: {exc}", 22)
        ok, reason = _snapshot("native_import_complete", module_name)
        if not ok:
            return _finish("STOPPED_AFTER_IMPORT", f"{module_name}: {reason}", 23)

    try:
        abi, failures = _native_abi_check()
    except BaseException as exc:  # Preserve ABI probe failures and keep collection closed.
        _append(
            {
                "stage": "abi_preflight_failed",
                **_proc_identity(),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            }
        )
        return _finish("ABI_FAILED_BEFORE_PYTEST", f"{type(exc).__name__}: {exc}", 28)
    _append({"stage": "abi_preflight", **_proc_identity(), "facts": abi, "failures": failures})
    if failures:
        return _finish("ABI_FAILED_BEFORE_PYTEST", "; ".join(failures), 29)

    ok, reason = _snapshot("before_targeted_fixture_tests")
    if not ok:
        return _finish("STOPPED_BEFORE_PYTEST", reason, 24)

    try:
        pytest = importlib.import_module("pytest")
        ok, reason = _snapshot("pytest_import_complete", "pytest")
        if not ok:
            return _finish("STOPPED_BEFORE_PYTEST", reason, 25)
        exit_code = int(
            pytest.main(
                [
                    "-q",
                    "--basetemp",
                    str(ROOT / "pytest"),
                    *TARGETED_NODEIDS,
                ]
            )
        )
    except BaseException as exc:  # Preserve pytest failures as a bounded fixture result.
        _append(
            {
                "stage": "targeted_fixture_tests_failed",
                **_proc_identity(),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            }
        )
        return _finish("FIXTURE_TESTS_FAILED", f"{type(exc).__name__}: {exc}", 26)

    ok, reason = _snapshot("targeted_fixture_tests_complete", "pytest")
    if not ok:
        return _finish("FIXTURE_TESTS_AFFINITY_LIMITED", reason, 27)
    if exit_code != 0:
        return _finish("FIXTURE_TESTS_FAILED", f"targeted pytest exit={exit_code}", exit_code)
    return _finish(
        "FIXTURE_TESTS_PASSED",
        "imports, ABI gates, affinity trace, and targeted S2 fixtures passed; no mesh/solver/PDE",
        0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
