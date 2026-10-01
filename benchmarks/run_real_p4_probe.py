"""Thin, separately supervised named-G0 p4 assembly/export entrypoint.

Numerical work is delegated to src.solvers.real_p4_probe. The default action
prints the frozen plan. --assemble-export is intentionally separate from any
future factor experiment; there is no factor command in this entrypoint.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from src.solvers.real_p4_probe import file_sha256, validate_named_input, write_json


ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
MAX_TREE_BYTES = 6 * GIB
RESERVE_BYTES = 128 * 1024**2
BRANCH = "task40extra_dot_parallel_cloud"
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"


def source_facts(expected_head: str) -> dict:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    branch, head, dirty = git("branch", "--show-current"), git("rev-parse", "HEAD"), git("status", "--porcelain", "--untracked-files=all")
    if branch != BRANCH or head != expected_head or dirty:
        raise RuntimeError("named cloud probe requires the exact own branch and clean committed source")
    paths = git("ls-files", "src", "benchmarks", "input/task40extra_0p7nm_engineering").splitlines()
    files = {path: file_sha256(ROOT / path) for path in paths if (ROOT / path).is_file()}
    return {"head": head, "branch": branch, "dirty": dirty, "files_sha256": files}


def environment_facts() -> dict:
    if os.environ.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("source the separately qualified cloud-complex activation first")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise RuntimeError(f"thread contract failed: {name}")
    path = Path(os.environ["_MYFENICS_CLOUD_ABI_MANIFEST"])
    digest = os.environ["_MYFENICS_CLOUD_ABI_MANIFEST_SHA256"]
    if file_sha256(path) != digest:
        raise RuntimeError("cloud ABI receipt content/hash mismatch")
    import numpy as np
    from petsc4py import PETSc
    from mpi4py import MPI
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128) or MPI.COMM_WORLD.size != 1:
        raise RuntimeError("requires fresh MPI1 complex128 scalar proof")
    modules = {}
    prefix = Path(sys.prefix).resolve()
    for name in ("dolfinx", "dolfinx_mpc", "petsc4py", "mpi4py", "basix", "ufl", "ffcx", "scipy"):
        module = importlib.import_module(name)
        module_path = Path(module.__file__).resolve()
        if not module_path.is_relative_to(prefix):
            raise RuntimeError(f"module escapes the qualified isolated prefix: {name}")
        modules[name] = {"version": getattr(module, "__version__", None), "path": str(module_path)}
    return {"python": sys.executable, "prefix": str(prefix), "modules": modules,
            "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)), "petsc_int_type": str(np.dtype(PETSc.IntType)),
            "petsc_version": list(PETSc.Sys.getVersion()), "mpi_library": MPI.Get_library_version(),
            "qualification_manifest": str(path), "qualification_manifest_sha256": digest,
            "qualification_scope": "separate_serial_cloud_ABI_not_historical_WSL_equivalence"}


def validate_source_receipt(path: Path, expected_hash: str, expected_head: str) -> dict:
    if file_sha256(path) != expected_hash:
        raise RuntimeError("source qualification receipt hash mismatch")
    receipt = json.loads(path.read_text())
    if receipt.get("source_sha") != expected_head or receipt.get("all_required_checks_passed") is not True:
        raise RuntimeError("required actual source fixtures have not passed at this HEAD")
    return receipt


def projected_allocation_bytes(name: str, facts: dict) -> int:
    if name == "condensed_matrix":
        return int(facts["matrix_payload_bytes"]) + int(facts.get("workspace_bytes", 0))
    if name == "cell_tensor_working_set":
        return int(facts["retained_numeric_bytes_upper"]) + int(facts["workspace_bytes"])
    raise ValueError(f"unknown existing assembly allocation boundary: {name}")


def _worker(args) -> int:
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    if parent != os.getppid() or parent <= 0:
        raise RuntimeError("assembly worker must be a direct child of its dedicated watchdog")
    cap = int(os.environ["PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES"])
    if not 0 < cap <= MAX_TREE_BYTES:
        raise RuntimeError("watchdog cap exceeds named research scope")
    source = source_facts(args.expected_head)
    environment = environment_facts()
    receipt = validate_source_receipt(args.source_receipt, args.source_receipt_sha256, args.expected_head)
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.solvers.real_p4_probe import assemble_export_named_g0
    events = args.run_directory / "probe_events.jsonl"

    def event(name, facts):
        payload = {"name": name, "monotonic": time.monotonic(), "facts": facts}
        with events.open("a") as stream:
            stream.write(json.dumps(payload, allow_nan=False) + "\n")
        print(name, flush=True)

    def allocation_gate(name, facts):
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        if sample.get("all_status_readable") is not True or sample.get("swap_bytes") != 0:
            raise RuntimeError("allocation gate requires a fully readable zero-swap tree")
        requested = projected_allocation_bytes(name, facts)
        projected = int(sample["rss_bytes"]) + requested + RESERVE_BYTES
        event("allocation_gate", {"boundary": name, "current_tree_rss_bytes": sample["rss_bytes"],
                                  "requested_additional_bytes": requested, "projected_tree_bytes": projected,
                                  "effective_cap_bytes": cap, "reserve_bytes": RESERVE_BYTES, "facts": facts})
        if projected >= cap:
            raise MemoryError("assembly projected allocation exceeds actual watchdog tree allowance")

    provenance = {"source": source, "environment": environment,
                  "source_qualification_receipt": receipt, "command": sys.argv,
                  "tree_cap_bytes": cap, "matrix_lifecycle": "no_global_factor_assembly_export_only"}
    assemble_export_named_g0(INPUT, args.run_directory / "operator", provenance=provenance,
                             event=event, allocation_gate=allocation_gate)
    if source_facts(args.expected_head) != source:
        raise RuntimeError("source identity changed during assembly/export")
    event("worker_complete", {"global_factor_created": False, "official_result": False})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assemble-export", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-head")
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--source-receipt-sha256")
    parser.add_argument("--run-directory", type=Path)
    args = parser.parse_args(argv)
    if not args.assemble_export:
        print(json.dumps({"status": "NOT_RUN_PLAN_ONLY", "branch": BRANCH, "input": str(INPUT),
                          "expected": {"cells": 336, "p4_trace_port_rows": 29072, "nnz": 10912592, "modes": 80},
                          "tree_cap_bytes": MAX_TREE_BYTES, "assembly_workflow_seconds": 900,
                          "global_factor_created": False, "p6_space_constructed": False,
                          "requirements": ["clean committed exact HEAD", "qualified isolated complex ABI",
                                           "passed actual source fixture receipt", "parent approval of exact command"]}, indent=2))
        return 0
    if not all((args.expected_head, args.source_receipt, args.source_receipt_sha256, args.run_directory)):
        parser.error("assembly requires expected HEAD, hash-bound source fixture receipt and new ignored run directory")
    validate_named_input(INPUT)
    run_directory = args.run_directory.resolve()
    if not run_directory.is_relative_to(ROOT / "benchmarks/artifacts/task40extra_dot_parallel_cloud"):
        parser.error("artifact directory must remain in the own ignored benchmark subtree")
    args.run_directory = run_directory
    if args.worker:
        return _worker(args)
    source = source_facts(args.expected_head)
    environment_facts()
    validate_source_receipt(args.source_receipt, args.source_receipt_sha256, args.expected_head)
    if shutil.disk_usage(ROOT).free < 5 * GIB:
        raise RuntimeError("fewer than 5 GiB free for the bounded uncompressed export")
    from benchmarks.subreaper_watchdog import supervise
    command = [sys.executable, "-m", "benchmarks.run_real_p4_probe", "--assemble-export", "--worker",
               "--expected-head", args.expected_head, "--source-receipt", str(args.source_receipt.resolve()),
               "--source-receipt-sha256", args.source_receipt_sha256, "--run-directory", str(run_directory)]
    summary = supervise(command, run_directory, wall_seconds=900, interval=.25, grace_seconds=2,
                        source_state=source, phase_path=run_directory / "phase.json", tree_cap_bytes=MAX_TREE_BYTES,
                        hard_stop_immediate=True, timebase_guard=True, stop_on_global_swap=True,
                        pss_sampling_policy="disabled_by_profile")
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    manifest = run_directory / "operator/export_manifest.json"
    passed = (summary.get("classification") == "COMPLETED" and manifest.exists()
              and json.loads(manifest.read_text()).get("status") == "ASSEMBLY_EXPORT_COMPLETE")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
