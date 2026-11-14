"""Thin orchestration for the fixed-geometry workstation wavelength pilot."""
from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "pstddm_stationary_workstation_pilot"
WORKFLOW = "source_transfer_initial_then_original_system_fgmres"
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
TREE_LIMIT_BYTES = 8_000_000_000
STAGING_RESERVE_BYTES = 512 << 20


def _plain(value: Any) -> Any:
    import numpy as np
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    return value


def _validate_case(document: dict[str, Any]) -> dict[str, Any]:
    required = {
        "model", "case_id", "mode", "wavelength_nm", "degree", "partitions",
        "reference_case_id", "workflow", "restart", "max_iterations",
        "true_residual_tolerance", "reference_tolerance", "field_E_tolerance",
        "field_H_tolerance", "theta_deg", "phi_deg", "polarization",
    }
    if set(document) != required:
        raise ValueError(f"case keys differ from the frozen schema: {sorted(set(document)^required)}")
    if document["model"] != MODEL_NAME or document["workflow"] != WORKFLOW:
        raise ValueError("workstation pilot model/workflow identity mismatch")
    if document["mode"] not in {"direct", "candidate"}:
        raise ValueError("workstation pilot mode must be direct or candidate")
    if document["degree"] != 2 or document["theta_deg"] != 89.0 or document["phi_deg"] != 90.0:
        raise ValueError("workstation pilot requires the frozen p2, theta=89, phi=90 profile")
    if document["polarization"] != "s":
        raise ValueError("workstation pilot preserves s polarization")
    if document["mode"] == "direct":
        if document["partitions"] != 0 or document["reference_case_id"] != "":
            raise ValueError("direct cases have no partition count or reference case")
    elif document["partitions"] not in {2, 4} or not document["reference_case_id"]:
        raise ValueError("formal candidates are N=2/N=4 and must name their direct reference")
    controls = {
        "restart": 30, "max_iterations": 100, "true_residual_tolerance": 1e-8,
        "reference_tolerance": 1e-10, "field_E_tolerance": 1e-4, "field_H_tolerance": 1e-3,
    }
    if any(document[key] != value for key, value in controls.items()):
        raise ValueError("workstation solver controls differ from the reviewed pilot contract")
    if not document["case_id"] or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in document["case_id"]):
        raise ValueError("case_id must be a nonempty filesystem-safe identifier")
    wavelength = float(document["wavelength_nm"])
    if wavelength not in {13.5, 5.0, 0.7}:
        raise ValueError("only the reviewed 13.5 -> 5 -> conditional 0.7 nm wavelengths are allowed")
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_workstation_cgroup(
    active_path: str,
    active_facts: dict[str, int],
    preparation_path: str,
    *,
    reserve_bytes: int = STAGING_RESERVE_BYTES,
    future_bytes: int = 0,
) -> None:
    """Validate the live case unit independently of the imports-only unit."""
    if active_path == preparation_path:
        raise ValueError("case cgroup must be separate from the ABI-preflight cgroup")
    if active_facts.get("memory_max_bytes") != TREE_LIMIT_BYTES:
        raise ValueError("case cgroup memory.max must equal 8,000,000,000 B")
    if active_facts.get("swap_max_bytes") != 0 or active_facts.get("swap_current_bytes") != 0:
        raise ValueError("case cgroup swap must remain zero")
    current = active_facts.get("memory_current_bytes", TREE_LIMIT_BYTES)
    if current + future_bytes + reserve_bytes > TREE_LIMIT_BYTES:
        raise MemoryError("case cgroup current plus staging reserve exceeds memory.max")


def _source_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def validate_supervisor_handoff(
    case_path: Path,
    case_id: str,
    input_sha256: str,
    scope_root: Path,
    output: Path,
    *,
    parent_pid: int,
) -> dict[str, Any]:
    """Check the supervisor's precreated directory before any FE work begins."""
    if os.environ.get("PSTDDM_WORKSTATION_SUPERVISOR_PID") != str(parent_pid):
        raise RuntimeError("case process is not the direct child of its declared supervisor")
    if output.parent.name != "runs" or output.name != case_id:
        raise ValueError("case output path does not match the frozen runs/case_id layout")
    if not case_path.is_relative_to(scope_root) or not output.is_relative_to(scope_root):
        raise ValueError("case input/output are outside the assigned task root")
    identity_path = output / "supervisor_identity.json"
    runtime_path = output / "runtime_receipt.json"
    if not identity_path.is_file() or not runtime_path.is_file():
        raise RuntimeError("supervisor did not initialize its runtime and source identity records")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    expected = {
        "case_id": case_id, "input_path": str(case_path), "input_sha256": input_sha256,
        "scope_root": str(scope_root), "runs_root": str(output.parent),
        "source_sha": _source_sha(), "supervisor_pid": parent_pid,
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise RuntimeError("supervisor handoff identity differs from this case, source, or output")
    if identity.get("runtime_receipt_sha256") != _sha256(runtime_path):
        raise RuntimeError("supervisor runtime receipt hash differs")
    allowed = {"tmp", "cache", "runtime_receipt.json", "supervisor_identity.json", "stdout.log", "stderr.log"}
    present = {item.name for item in output.iterdir()}
    if not allowed.issuperset(present) or not {"tmp", "cache", "runtime_receipt.json", "supervisor_identity.json"}.issubset(present):
        raise RuntimeError("case output contains unexpected artifacts or is missing supervisor initialization")
    if not (output / "tmp").is_dir() or not (output / "cache").is_dir():
        raise RuntimeError("supervisor temporary/cache locations are invalid")
    return identity


def qualified_native_runtime_receipt(scope_root: Path) -> dict[str, Any]:
    """Verify the main-provided, hash-bound native activation and ABI receipt."""
    import importlib
    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc

    if sys.platform != "linux" or "microsoft" in platform.release().lower() or os.environ.get("WSL_DISTRO_NAME"):
        raise RuntimeError("workstation profile requires the native Linux fenics-ws runtime")
    prep_path = scope_root / "preparation/abi_imports_20261114.json"
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    if prep.get("scope") != "IMPORTS_ONLY_NO_FE_NO_PDE" or prep.get("hostname") != __import__("socket").gethostname():
        raise RuntimeError("workstation preparation receipt has the wrong scope or host")
    if prep.get("boot_id") != Path("/proc/sys/kernel/random/boot_id").read_text().strip():
        raise RuntimeError("workstation preparation receipt belongs to a different host boot")
    if os.environ.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("native qualified activation marker is missing")
    if os.environ.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != "native_linux":
        raise RuntimeError("native activation runtime profile must equal native_linux")
    env_record = prep.get("environment", {})
    if env_record.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != "native_linux":
        raise RuntimeError("preparation receipt does not bind runtime_profile=native_linux")
    for name in THREAD_VARIABLES:
        if os.environ.get(name) != "1" or env_record.get(name) != "1":
            raise RuntimeError(f"native activation thread contract failed: {name}")
    dependencies = {str(item.get("path")): item for item in prep.get("dependencies", [])}
    if len(dependencies) != 2:
        raise RuntimeError("preparation receipt must bind the activation script and native ABI receipt")
    for path_text, item in dependencies.items():
        path = Path(path_text)
        if not path.is_file() or path.is_symlink() or _sha256(path) != item.get("sha256"):
            raise RuntimeError(f"preparation dependency is missing or changed: {path}")
        if path.stat().st_size != item.get("bytes"):
            raise RuntimeError(f"preparation dependency length changed: {path}")
    dependency_names = {Path(path).name for path in dependencies}
    if (not any(name.startswith("activate_native_complex") for name in dependency_names)
            or not any(name.startswith("abi_receipt_") for name in dependency_names)):
        raise RuntimeError("preparation receipt dependencies do not name the supplied activation and ABI receipt")
    active_manifest = os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST")
    active_manifest_sha = os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
    if (not active_manifest or active_manifest not in dependencies
            or not active_manifest_sha or dependencies[active_manifest].get("sha256") != active_manifest_sha):
        raise RuntimeError("active ABI manifest path/hash differ from the supplied native receipt")
    python = Path(sys.executable).resolve()
    if str(python) != str(Path(prep.get("python", "")).resolve()):
        raise RuntimeError("active Python does not match the preparation receipt")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128) or np.dtype(PETSc.IntType).name != "int32":
        raise RuntimeError("active PETSc must be complex128/int32")
    if MPI.COMM_WORLD.size != 1 or PETSc.COMM_WORLD.size != 1:
        raise RuntimeError("workstation pilot requires MPI1")
    modules = {}
    expected_modules = prep.get("modules", {})
    for name in ("numpy", "petsc4py", "dolfinx", "basix", "ffcx", "mpi4py"):
        module = importlib.import_module(name)
        path = str(Path(module.__file__).resolve())
        expected = expected_modules.get(name, {}).get("file")
        if expected is None or path != str(Path(expected).resolve()):
            raise RuntimeError(f"loaded module differs from the preparation receipt: {name}")
        modules[name] = {"version": getattr(module, "__version__", None), "path": path}
    cg = prep.get("cgroup", {})
    if cg.get("memory.max") != "8000000000" or cg.get("memory.swap.max") != "0":
        raise RuntimeError("preparation receipt does not bind memory.max=8e9 and swap.max=0")
    current_cgroup = next(line.split(":", 2)[2] for line in Path("/proc/self/cgroup").read_text().splitlines()
                          if line.startswith("0::"))
    current_cgroup_path = Path("/sys/fs/cgroup") / current_cgroup.lstrip("/")
    if str(current_cgroup_path) == cg.get("path"):
        raise RuntimeError("formal workstation case must run in its separately admitted cgroup, not the ABI-preflight unit")
    return {
        "runtime_profile": "native_linux", "preparation_receipt": str(prep_path),
        "preparation_receipt_sha256": _sha256(prep_path), "hostname": prep["hostname"],
        "boot_id": prep["boot_id"], "python_executable": str(python),
        "preparation_cgroup": cg,
        "active_cgroup_path": str(current_cgroup_path),
        "activation_and_abi_dependencies": [item for item in dependencies.values()],
        "PETSc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "PETSc_integer_type": str(np.dtype(PETSc.IntType)),
        "PETSc_version": list(PETSc.Sys.getVersion()), "MPI_library": MPI.Get_library_version(),
        "mpi_size": int(MPI.COMM_WORLD.size), "modules": modules,
        "qualification_scope": "imports_only_no_FE_no_PDE; fresh source fixture checks remain separate",
    }


def _write_sparse_identity(system: Any, out: Path) -> dict[str, Any]:
    from scipy import sparse

    matrices = [
        ("A", system.A), ("C", system.C), ("D", system.D), ("mass", system.M),
        ("curl_gram", system.K), ("T", system.T), ("full", system.full),
        ("raw_A", system.raw_A), ("raw_C", system.dtn.C), ("raw_D", system.dtn.D),
    ]
    result = {}
    for name, matrix in matrices:
        path = out / f"{name}.npz"
        sparse.save_npz(path, matrix)
        result[name] = {"shape": list(matrix.shape), "nnz": int(matrix.nnz), "sha256": _sha256(path)}
    np = __import__("numpy")
    np.save(out / "rhs.npy", system.rhs)
    np.save(out / "physical_rhs.npy", system.rhs)
    np.save(out / "raw_f.npy", system.raw_f)
    np.save(out / "raw_aux_rhs.npy", system.rhs[system.A.shape[0]:])
    mpc = system.p.floquet.mpc
    coefficients, offsets = mpc.coefficients()
    np.savez(out / "raw_mpc.npz", slaves=mpc.slaves[:mpc.num_local_slaves],
             masters=mpc.masters.array, master_offsets=mpc.masters.offsets,
             coefficients=coefficients, coefficient_offsets=offsets)
    return result


def _verify_reference(reference_dir: Path, system: Any, identity: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from scipy import sparse

    manifest_path = reference_dir / "run_manifest.json"
    summary_path = reference_dir / "run_summary.json"
    if not manifest_path.is_file() or not summary_path.is_file():
        raise ValueError("direct reference is missing its manifest or summary")
    manifest, summary = json.loads(manifest_path.read_text()), json.loads(summary_path.read_text())
    if manifest.get("status") != "DIRECT_REFERENCE_PASS":
        raise ValueError("named reference does not have a passing direct residual")
    for key in ("wavelength_nm", "geometry_identity", "material_identity_sha256", "physical_sha256",
                "ordered_modes_sha256", "C_sha256", "D_sha256"):
        if manifest.get(key) != identity.get(key):
            raise ValueError(f"reference {key} identity differs from the candidate")
    n = system.A.shape[0]
    for name, matrix in (("A", system.A), ("C", system.C), ("D", system.D), ("T", system.T),
                         ("mass", system.M), ("curl_gram", system.K)):
        previous = sparse.load_npz(reference_dir / f"{name}.npz")
        difference = previous - matrix
        if difference.nnz and np.max(np.abs(difference.data)) != 0.0:
            raise ValueError(f"reference {name} matrix is not exactly identical")
    if not np.array_equal(np.load(reference_dir / "rhs.npy"), system.rhs):
        raise ValueError("reference right-hand side differs")
    artifacts = json.loads((reference_dir / "artifact_hashes.json").read_text())
    for filename, item in artifacts.items():
        artifact = reference_dir / filename
        if (not artifact.is_file() or artifact.stat().st_size != item["bytes"]
                or _sha256(artifact) != item["sha256"]):
            raise ValueError(f"direct reference artifact hash/size mismatch: {filename}")
    z = np.load(reference_dir / "reference_solution.npz", allow_pickle=False)["z"]
    recomputed = float(np.linalg.norm(system.rhs - system.full @ z)
                       / max(float(np.linalg.norm(system.rhs)), np.finfo(float).tiny))
    result = summary["result"]
    if not np.isfinite(recomputed) or recomputed > 1e-10:
        raise ValueError(f"recomputed direct true residual exceeds 1e-10: {recomputed}")
    if not np.isclose(recomputed, float(result["true_residual"]), rtol=1e-10, atol=1e-15):
        raise ValueError("summary reference residual differs from the original full-system matvec")
    return {"z": z, "true_residual": recomputed,
            "diagnostics": json.loads((reference_dir / "reference_diagnostics.json").read_text()),
            "reference_case_id": manifest["case_id"]}


def run_workstation_case(input_path: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Execute one case only when invoked under the existing supervisor."""
    if not __debug__ or os.environ.get("PYTHONOPTIMIZE"):
        raise RuntimeError("optimization mode is forbidden for assertion-based admission")
    from src.io.input_loader import load_dat_input
    loaded = load_dat_input(input_path)
    case_path = loaded.source_path
    document = _validate_case(dict(loaded.document))

    from src.solvers.pstddm_material import derive_si_optical_identity
    from src.solvers.pstddm_model import model_preflight, workstation_spec_from_material_identity

    material = derive_si_optical_identity(float(document["wavelength_nm"]))
    model = workstation_spec_from_material_identity(material)
    plan = model_preflight(model, int(document["degree"]))
    preflight = {"material_identity": material, "model": _plain(model.__dict__), "model_preflight": plan}
    if dry_run:
        return {"status": "VALID_CONFIGURATION_NOT_RUN", "config": document,
                "preflight": preflight, "execution_command": "python scripts/run_case.py <input.dat>"}
    if os.environ.get("PSTDDM_WORKSTATION_SUPERVISOR_PID") != str(os.getppid()):
        raise RuntimeError("formal workstation cases require supervise.py --profile workstation")
    scope_root = Path(os.environ["PSTDDM_WORKSTATION_SCOPE_ROOT"]).resolve(strict=True)
    output = Path(os.environ["PSTDDM_WORKSTATION_OUTPUT"]).resolve(strict=True)
    validate_supervisor_handoff(
        case_path, str(document["case_id"]), loaded.input_sha256, scope_root, output,
        parent_pid=os.getppid(),
    )
    runtime = qualified_native_runtime_receipt(scope_root)
    if any(os.environ.get(name) != "1" for name in THREAD_VARIABLES):
        raise RuntimeError("all mathematical thread variables must equal one")

    from src.solvers.pstddm_native import global_system, build_partition
    from src.solvers.pstddm_comparison import direct_reference, candidate

    start = time.monotonic()
    events: list[dict[str, Any]] = []

    def gate(stage: str, future_bytes: int = 0) -> None:
        status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
        meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        available = int(meminfo["MemAvailable"].split()[0]) * 1024
        total = int(meminfo["MemTotal"].split()[0]) * 1024
        rss = int(status["VmRSS"].split()[0]) * 1024
        event = {"stage": stage, "elapsed_seconds": time.monotonic() - start,
                 "process_rss_bytes": rss, "planned_extra_bytes": int(future_bytes),
                 "staging_reserve_bytes": 512 << 20,
                 "host_available_bytes": available, "host_total_bytes": total}
        events.append(event)
        (output / "phase_gates.json").write_text(json.dumps(events, indent=2) + "\n")
        print(json.dumps(event, separators=(",", ":")), flush=True)
        if rss + int(future_bytes) + (512 << 20) > 8_000_000_000:
            raise RuntimeError("task phase RSS plus staging reserve exceeds 8,000,000,000 B")
        if available - int(future_bytes) - (512 << 20) < 400 * (1 << 30):
            raise RuntimeError("predicted host MemAvailable would cross the 400 GiB reserve")
        if int(status.get("VmSwap", "0 kB").split()[0]) != 0:
            raise RuntimeError("workstation task process has nonzero swap")
        cgroup_path = Path("/sys/fs/cgroup")
        try:
            cg_rel = next(line.split(":", 2)[2] for line in Path("/proc/self/cgroup").read_text().splitlines()
                          if line.startswith("0::"))
            cgroup = (cgroup_path / cg_rel.lstrip("/")).resolve(strict=True)
            current = int((cgroup / "memory.current").read_text().strip())
            maximum = int((cgroup / "memory.max").read_text().strip())
            swap_max = int((cgroup / "memory.swap.max").read_text().strip())
            swap_current = int((cgroup / "memory.swap.current").read_text().strip())
        except (StopIteration, OSError, ValueError) as exc:
            raise RuntimeError("cannot read the workstation task's cgroup v2 memory gates") from exc
        event.update({"cgroup_memory_current_bytes": current, "cgroup_memory_max_bytes": maximum,
                      "cgroup_swap_current_bytes": swap_current, "cgroup_swap_max_bytes": swap_max})
        (output / "phase_gates.json").write_text(json.dumps(events, indent=2) + "\n")
        validate_workstation_cgroup(
            str(cgroup), {"memory_current_bytes": current, "memory_max_bytes": maximum,
                          "swap_current_bytes": swap_current, "swap_max_bytes": swap_max},
            str(runtime["preparation_cgroup"]["path"]), future_bytes=int(future_bytes),
        )

    free = __import__("shutil").disk_usage(scope_root).free
    if free < 400_000_000_000:
        raise RuntimeError("task filesystem has less than the 400 GB free-space floor")

    (output / "input_original.dat").write_bytes(loaded.raw_input_bytes)
    (output / "preflight.json").write_text(json.dumps(preflight, indent=2, allow_nan=False) + "\n")
    (output / "runtime_receipt.json").write_text(json.dumps(runtime, indent=2, allow_nan=False) + "\n")
    gate("direct_factor_planning_admission", int(plan["direct_factor_planning_allowance_bytes"]))
    gate("before_global_assembly", 256 << 20)
    system = global_system(output, int(document["degree"]), gate, model_spec=model)
    config_json = _plain(system.p.cfg.as_jsonable())
    physical_bytes = json.dumps(config_json, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    physical_sha = hashlib.sha256(physical_bytes).hexdigest()
    identity = {
        "case_id": document["case_id"], "wavelength_nm": float(document["wavelength_nm"]),
        "geometry_identity": model.geometry_identity,
        "material_identity_sha256": material["identity_sha256"],
        "physical_sha256": physical_sha,
        "ordered_modes_sha256": system.dtn.metadata["ordered_modes_sha256"],
        "C_sha256": system.dtn.metadata["C_sha256"], "D_sha256": system.dtn.metadata["D_sha256"],
        "model": document["model"], "mode": document["mode"],
    }
    matrix_identity = _write_sparse_identity(system, output)
    (output / "material_identity.json").write_text(json.dumps(material, indent=2, allow_nan=False) + "\n")
    (output / "global_config.json").write_text(json.dumps(config_json, indent=2, allow_nan=False) + "\n")
    (output / "mode_manifest.json").write_text(json.dumps(_plain(system.dtn.metadata), indent=2, allow_nan=False) + "\n")
    manifest = {
        **identity, "input_sha256": loaded.input_sha256,
        "source_sha": _source_sha(), "degree": int(document["degree"]),
        "axis_cell_counts": plan["axis_cell_counts"], "cell_count": plan["cells"],
        "raw_FE_rows": system.T.shape[0], "independent_FE_rows": system.A.shape[0],
        "auxiliary_rows": system.C.shape[1], "full_augmented_rows": system.full.shape[0],
        "direct_factor_planning_allowance_bytes": plan["direct_factor_planning_allowance_bytes"],
        "matrices": matrix_identity, "mpi": 1,
        "thread_environment": {name: os.environ[name] for name in THREAD_VARIABLES},
        "runtime_profile": runtime["runtime_profile"],
        "runtime_receipt_sha256": _sha256(output / "runtime_receipt.json"),
        "global_pml_disabled": bool(not system.p.cfg.use_pml),
        "local_pml_only": True,
        "scope": "fixed-geometry same-discrete algorithm and resource pilot; not physical convergence",
    }
    reference_dir: Path | None = None
    if document["mode"] == "direct":
        result = direct_reference(system, gate, output)
        status = "DIRECT_REFERENCE_PASS" if result["true_residual"] <= 1e-10 else "DIRECT_REFERENCE_FAIL"
        manifest["status"] = status
        diagnostic_qualification = result["diagnostics"].get("qualification", "missing")
        manifest["postprocessing_qualification"] = diagnostic_qualification
        manifest["observable_qualification"] = {
            name: diagnostic_qualification for name in
            ("R_total", "T_total", "A_flux", "A_volume", "mode_power", "E_total_l2", "H_total_l2")
        }
    else:
        runs_root = output.parent
        reference_dir = (runs_root / str(document["reference_case_id"])).resolve(strict=True)
        if reference_dir.parent != runs_root.resolve():
            raise ValueError("reference case must be a sibling in this task's runs directory")
        reference = _verify_reference(reference_dir, system, identity)
        core, pairs, partition = build_partition(system, int(document["partitions"]), gate)
        from scipy import sparse

        for index, pair in enumerate(pairs):
            for name, matrix in (("map", pair.S), ("commutator_plus", pair.plus),
                                 ("commutator_minus", pair.minus), ("L", pair.L)):
                sparse.save_npz(output / f"pair{index}_{name}.npz", matrix)
        (output / "partition_audit.json").write_text(json.dumps(_plain(partition), indent=2, allow_nan=False) + "\n")
        result = candidate(system, core, reference, output)
        partition["actual_solve_counts"] = [pair.solve_count for pair in pairs]
        partition["actual_solve_seconds"] = [pair.solve_seconds for pair in pairs]
        (output / "partition_audit.json").write_text(json.dumps(_plain(partition), indent=2, allow_nan=False) + "\n")
        manifest["reference_case_id"] = document["reference_case_id"]
        manifest["reference_source_sha"] = json.loads((reference_dir / "run_manifest.json").read_text())["source_sha"]
        manifest["partition_count"] = int(document["partitions"])
        manifest["status"] = "CANDIDATE_SAME_DISCRETE_PASS" if result["same_discrete_solver_pass"] else "CANDIDATE_NUMERICAL_FAIL"
        diagnostics = result["diagnostics"]
        diagnostic_qualification = diagnostics.get("qualification", "missing")
        manifest["postprocessing_qualification"] = diagnostic_qualification
        manifest["observable_qualification"] = {
            name: diagnostic_qualification for name in
            ("R_total", "T_total", "A_flux", "A_volume", "mode_power", "E_total_l2", "H_total_l2")
        }
        manifest["qualified_total_power_gate"] = {
            "status": "not_applicable_unqualified_postprocessing",
            "qualification": diagnostic_qualification,
            "diagnostic_absolute_differences": result["diagnostic_absolute_differences"],
        }
        if diagnostic_qualification == "qualified":
            power_names = ("R_total", "T_total", "A_flux", "A_volume")
            power_gate = {name: result["diagnostic_absolute_differences"][name] for name in power_names}
            power_passed = max(power_gate.values(), default=0.0) <= 1e-4
            manifest["qualified_total_power_gate"] = {
                "status": "pass" if power_passed else "fail",
                "qualification": diagnostic_qualification,
                "absolute_tolerance": 1e-4, "absolute_differences": power_gate,
            }
            if not power_passed:
                manifest["status"] = "CANDIDATE_QUALIFIED_POWER_FAIL"
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    summary = {
        "status": manifest["status"], "result": _plain({key: value for key, value in result.items() if key != "z"}),
        "setup_wall_seconds": system.setup_seconds, "case_wall_seconds": time.monotonic() - start,
        "source_sha": manifest["source_sha"], "physical_sha256": physical_sha,
        "material_identity_sha256": material["identity_sha256"],
        "postprocessing_qualification": manifest.get("postprocessing_qualification", "diagnostic_unqualified"),
        "reference_case_id": document["reference_case_id"] or None,
    }
    (output / "run_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary
