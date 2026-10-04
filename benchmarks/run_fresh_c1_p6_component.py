"""Supervised fresh-C1 same80 p6 component worker; no CLI/watchdog of its own.

The external supervisor owns cold-JIT admission, process-tree RSS/termination,
disk reserve, durable callbacks, and the native-library preflight.  This runner
builds one p6 same-mesh physical action, obtains the required literal532
same-live qualification, and only then calls the component worker.
"""
from __future__ import annotations

import hashlib
import json
import os
import argparse
import importlib
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

from benchmarks.task40_runtime_profile import (
    LOCAL_WSL2_PROFILE,
    NATIVE_LINUX_PROFILE,
    validate_runtime_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
INPUT_SHA256 = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
BUDGET_PATH = Path(__file__).with_name("fresh_c1_p6_w0_budget.json")
W0_ARCHIVE_PAYLOAD_LIMIT_BYTES = 8 * 1024**3
W0_EXPECTED_DERIVED_UPPER_BYTES = 6_900_030_936
W0_BUDGET_MANIFEST_SHA256 = "533930676db07f7a145e0e6b71eacd198288bea92717bf7a8ba91fe9d16a9b81"
SAME80_AXES = {
    "x": (0.0, 16.5, 25.0, 33.5, 50.0),
    "y": (0.0, 6.25, 12.5, 18.75, 25.0),
    "z": (-10.0, 0.0, 40.0, 80.0, 120.0, 130.0),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_budget_identity() -> dict[str, Any]:
    packet = json.loads(BUDGET_PATH.read_text())
    manifest_sha = _sha256(BUDGET_PATH)
    if (manifest_sha != W0_BUDGET_MANIFEST_SHA256
            or packet.get("schema") != "task40extra.fresh-c1-p6-w0-raw-member-budget.v1"
            or packet.get("frozen_raw_member_payload_limit_bytes") != W0_ARCHIVE_PAYLOAD_LIMIT_BYTES
            or packet.get("derived_worst_case_member_upper_bytes") != W0_EXPECTED_DERIVED_UPPER_BYTES
            or packet.get("remaining_limit_margin_bytes")
            != W0_ARCHIVE_PAYLOAD_LIMIT_BYTES - W0_EXPECTED_DERIVED_UPPER_BYTES):
        raise ValueError("frozen W0 raw-member budget manifest differs from source constants")
    return {"path": str(BUDGET_PATH), "sha256": manifest_sha,
            "schema": packet["schema"],
            "frozen_raw_member_payload_limit_bytes": W0_ARCHIVE_PAYLOAD_LIMIT_BYTES,
            "derived_worst_case_member_upper_bytes": W0_EXPECTED_DERIVED_UPPER_BYTES,
            "remaining_limit_margin_bytes": packet["remaining_limit_margin_bytes"],
            "scope": packet["scope"], "status": packet["status"]}


def source_identity() -> dict[str, Any]:
    paths = (
        "benchmarks/run_fresh_c1_p6_component.py",
        "benchmarks/check_fresh_c1_p6_component.py",
        "benchmarks/fresh_c1_p6_w0_budget.json",
        "benchmarks/fresh_c1_p6_w0_dependencies.json",
        "benchmarks/subreaper_watchdog.py",
        "scripts/run_fresh_c1_p6_local_wsl.sh",
        "scripts/run_fresh_c1_p6_native.sh",
        "scripts/task40_fresh_c1/activate_local_wsl_complex.sh",
        "scripts/task40_fresh_c1/activate_native_complex.sh",
        "scripts/task40_fresh_c1/native_service_entry.sh",
        "scripts/task40_fresh_c1/qualify_imports_only.py",
        "benchmarks/task40_runtime_profile.py",
        "src/solvers/fresh_c1_p6_component.py",
        "src/solvers/fresh_c1_live_contract.py",
        "src/solvers/dtn_boundary_plane_qualification.py",
        "src/solvers/dtn_boundary_phase_gauge.py",
        "src/solvers/dtn_port_3d.py",
        "src/solvers/fullspace_dtn_action.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py",
        "src/solvers/p6_cell_condensed_action.py",
        "src/solvers/hcurl_assembly_time_condensation.py",
        "src/solvers/original_port_blocks.py",
        "src/solvers/retained_port_block_layout.py",
        "src/solvers/solve_vector_maxwell.py",
    )
    records = {name: _sha256(ROOT / name) for name in paths}
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("ascii")
    return {"schema": "task40extra.fresh-c1-p6-source-identity.v1",
            "files": records, "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
            "source_status": "NEW_UNQUALIFIED"}


def pilot_config(input_path: str | Path = INPUT):
    """Resolve the fixed original model and set its exact regular same80 fixture."""
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized

    source = Path(input_path).resolve()
    raw_sha = _sha256(source)
    if raw_sha != INPUT_SHA256:
        raise ValueError("fresh C1 p6 runner requires the frozen review-v1 input SHA256")
    specification = load_and_resolve(source)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    scale = 7.0 / 135.0
    cfg.case_name = "fresh_c1_p6_component_regular"
    cfg.lambda0 = 0.7
    cfg.incident_phi_deg = 5.0
    cfg.geometry_model_variant = "original"
    cfg.geometry_identity = "task40extra_nonseparable_0p7nm_v1.regular"
    cfg.air_void_box_nm = None
    cfg.cell_notch = None
    cfg.mesh_cell_type = "hexahedron"
    cfg.mesh_spacing_mode = "boundary_fitted"
    cfg.mesh_axis_cell_counts = (4, 4, 5)
    cfg.mesh_axis_x_values = tuple(value * scale for value in SAME80_AXES["x"])
    cfg.mesh_axis_y_values = tuple(value * scale for value in SAME80_AXES["y"])
    cfg.mesh_axis_z_values = tuple(value * scale for value in SAME80_AXES["z"])
    cfg.mesh_axis_z_profile = "task40extra.fresh-C1-same80-z.v1"
    cfg.mesh_plan_id = "task40extra.fresh-C1-same80-regular.v1"
    cfg.mesh_plan_sha256 = None
    cfg.nedelec_degree = 6
    cfg.visualization_degree = 6
    cfg.nedelec_trace_degree = None
    cfg.nedelec_interior_degree = None
    cfg.diffraction_zero_order_only = False
    cfg.stage4_dtn_order_policy = "manual"
    cfg.diffraction_order_max_m = 9
    cfg.diffraction_order_max_n = 3
    cfg.stage4_boundary_model = "dtn_port"
    cfg.stage4_dtn_assembly = "auxiliary"
    cfg.use_pml = False
    cfg.pml_top_thickness = 0.0
    cfg.pml_bottom_thickness = 0.0
    cfg.divergence_penalty = 0.0
    return cfg, {
        "path": str(source), "input_sha256": raw_sha,
        "physical_model_sha256": specification.physical_model_sha256,
        "axes_nm": {name: list(values) for name, values in SAME80_AXES.items()},
        "scale": scale, "cell_count": 80, "geometry_identity": cfg.geometry_identity,
        "air_void_box_nm": None, "model_variant": cfg.geometry_model_variant,
    }


def integer_admission(index_dtype: Any) -> dict[str, Any]:
    """Range-check dimensions and a dense local-nnz upper before mesh setup."""
    import numpy as np

    dtype = np.dtype(index_dtype)
    if dtype.kind not in "iu":
        raise TypeError("native PETSc index type must be integer")
    limit = int(np.iinfo(dtype).max)
    rows = (55_950, 55_950)
    local_nnz_upper = 80 * 882 * 882
    if max(*rows, local_nnz_upper) > limit:
        raise OverflowError("fresh p6 exact dimensions/nnz upper exceed native PETSc.IntType")
    return {"status": "admitted_before_mesh_allocation", "index_dtype": str(dtype),
            "maximum_index": limit, "matrix_dimensions_if_required": list(rows),
            "local_nnz_upper_if_required": local_nnz_upper,
            "matrix_allocated": False, "global_p6_matrix_created": False}


def _qualified_runtime(abi_receipt_path: str | Path):
    """Fail before setup unless modules match this run's explicit local profile receipt."""
    receipt_path = Path(abi_receipt_path).resolve()
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    runtime_profile = receipt.get("runtime_profile", NATIVE_LINUX_PROFILE)
    if (os.environ.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1"
            or Path(os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST", "")).resolve() != receipt_path
            or os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256") != receipt_sha
            or os.environ.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != runtime_profile):
        raise RuntimeError("use the tracked Task40 profile activation with this fresh local ABI receipt")
    runtime_host = validate_runtime_receipt(receipt, requested_profile=runtime_profile)
    if (sys.platform != "linux"
            or receipt.get("schema") != "fresh-runtime-imports-only.v1"
            or receipt.get("status") != "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"
            or receipt.get("FE_action") != "NOT_RUN"):
        raise RuntimeError("fresh Task40 imports-only ABI receipt is missing or failed")
    prefix = Path(sys.prefix).resolve()
    if (Path(sys.executable).resolve() != Path(receipt.get("executable", "")).resolve()
            or prefix != Path(receipt.get("prefix", "")).resolve()
            or sys.version_info[:2] != (3, 12)):
        raise RuntimeError("live interpreter differs from the qualified independent prefix")
    from mpi4py import MPI
    from petsc4py import PETSc
    import dolfinx
    import basix
    from importlib.metadata import version
    import numpy as np

    modules = receipt.get("modules", {})
    live_modules = {name: importlib.import_module(name) for name in (
        "numpy", "scipy", "mpi4py", "petsc4py", "basix", "ufl", "ffcx",
        "dolfinx", "dolfinx_mpc")}
    for name, module in live_modules.items():
        recorded = modules.get(name, {})
        module_file = Path(getattr(module, "__file__", "")).resolve()
        if (not module_file.is_relative_to(prefix)
                or Path(recorded.get("file", "")).resolve() != module_file):
            raise RuntimeError(f"live {name} module differs from the qualified independent prefix/receipt")
    mpc_version = version("dolfinx_mpc")
    if (MPI.COMM_WORLD.size != 1 or MPI.COMM_WORLD.rank != 0
            or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
            or np.dtype(PETSc.IntType) != np.dtype(np.int32)
            or dolfinx.__version__ != "0.10.0"
            or basix.__version__ != "0.10.0"
            or mpc_version != "0.10.5"
            or receipt.get("MPC_package_version") != mpc_version
            or tuple(PETSc.Sys.getVersion()) != (3, 25, 6)):
        raise RuntimeError("Task40 p6 requires MPI1, complex128/int32, DOLFINx/Basix 0.10.0, MPC 0.10.5 and PETSc 3.25.6")
    mpi = receipt.get("MPI", {})
    if (MPI.Get_library_version() != mpi.get("library_version")
            or "MPICH" not in MPI.Get_library_version()
            or "5.0.1" not in MPI.Get_library_version()
            or mpi.get("size") != 1 or mpi.get("rank") != 0
            or receipt.get("PETSc", {}).get("version") != [3, 25, 6]
            or receipt.get("PETSc", {}).get("scalar_dtype") != "complex128"
            or receipt.get("PETSc", {}).get("int_dtype") != "int32"
            or receipt.get("dolfinx_default_scalar_dtype") != "complex128"):
        raise RuntimeError("live MPICH/PETSc/DOLFINx runtime differs from the local ABI receipt")
    if (os.environ.get("UCX_TLS") != "self"
            or any(os.environ.get(name) != "1" for name in
                   ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"))):
        raise RuntimeError("MPI/BLAS thread profile differs from the admitted one-rank receipt")
    loaded = {Path(line.split()[-1]).resolve() for line in Path("/proc/self/maps").read_text().splitlines()
              if "/" in line and any(token in line for token in
              ("libmpi", "libpetsc", "mumps", "dolfinx", "basix", "openblas"))}
    if any(not path.is_relative_to(prefix) for path in loaded):
        raise RuntimeError("live numerical libraries were loaded outside the qualified prefix")
    return MPI, PETSc, {"path": str(receipt_path), "sha256": receipt_sha,
                        "prefix": str(prefix), "executable": str(Path(sys.executable).resolve()),
                        "runtime_profile": runtime_profile,
                        "runtime_host": runtime_host,
                        "MPI_library_version": MPI.Get_library_version(),
                        "PETSc_version": list(PETSc.Sys.getVersion()),
                        "PETSc_scalar": str(np.dtype(PETSc.ScalarType)),
                        "PETSc_integer": str(np.dtype(PETSc.IntType)),
                        "dolfinx": dolfinx.__version__, "basix": basix.__version__,
                        "dolfinx_mpc": mpc_version,
                        "thread_profile": {name: os.environ.get(name) for name in
                            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}}


def run(*, output_dir: str | Path, allocation_gate: Callable,
        save_array: Callable, checkpoint: Callable,
        archive_payload_limit_bytes: int = W0_ARCHIVE_PAYLOAD_LIMIT_BYTES,
        input_path: str | Path = INPUT,
        abi_receipt_path: str | Path) -> dict[str, Any]:
    """Run the externally supervised component and bind all same-live evidence."""
    for name, callback in (("allocation_gate", allocation_gate), ("save_array", save_array),
                           ("checkpoint", checkpoint)):
        if not callable(callback):
            raise TypeError(f"{name} must be callable")
    if archive_payload_limit_bytes != W0_ARCHIVE_PAYLOAD_LIMIT_BYTES:
        raise ValueError("W0 worker must use the exact frozen 8 GiB raw-member limit")
    budget = frozen_budget_identity()
    sources = source_identity()
    MPI, PETSc, abi_identity = _qualified_runtime(abi_receipt_path)
    integer_identity = integer_admission(PETSc.IntType)
    cfg, input_identity = pilot_config(input_path)
    if (tuple(cfg.mesh_axis_cell_counts) != (4, 4, 5)
            or tuple(cfg.mesh_axis_x_values) != tuple(v * (7.0/135.0) for v in SAME80_AXES["x"])
            or tuple(cfg.mesh_axis_y_values) != tuple(v * (7.0/135.0) for v in SAME80_AXES["y"])
            or tuple(cfg.mesh_axis_z_values) != tuple(v * (7.0/135.0) for v in SAME80_AXES["z"])):
        raise ValueError("resolved fresh same80 exact axes changed")
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    allocation_gate("fresh_p6_cold_setup", {
        "matrix_payload_bytes": 0, "workspace_bytes": 64 << 20,
        "process_tree_memory_cap_bytes": 3 << 30,
        "filesystem_free_reserve_bytes": 2 << 30,
        "wall_time_limit_seconds": 4500,
        "allocation_semantics": "additional objects to current whole-process-tree RSS",
        "cold_JIT_must_be_supervised_before_mesh_setup": True,
        "watchdog_and_process_group_termination_owned_by_caller": True,
        "raw_member_payload_limit_bytes": W0_ARCHIVE_PAYLOAD_LIMIT_BYTES,
    })
    admission_record = {
        "input": input_identity, "integer_admission": integer_identity,
        "w0_budget": budget, "source_identity": sources,
        "MPI_size": int(MPI.COMM_WORLD.size),
        "PETSc_scalar": str(PETSc.ScalarType), "PETSc_integer": str(PETSc.IntType),
        "runtime_profile": abi_identity["runtime_profile"],
        "runtime_abi_identity": abi_identity,
        "PDE_solved": False,
    }
    if abi_identity["runtime_profile"] == NATIVE_LINUX_PROFILE:
        admission_record["native_abi_identity"] = abi_identity
    checkpoint("fresh_p6_admission", admission_record)
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action, destroy_same_mesh_physical_action,
    )
    from src.solvers.dtn_boundary_phase_gauge import BOUNDARY_PLANE
    from src.solvers.fresh_c1_live_contract import (
        qualify_live_identity, require_live_carrier_unchanged,
    )
    from src.solvers.fresh_c1_p6_component import run_fresh_p6_component

    modes, _mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
    if len(modes) != 532 or mode_sha != "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951":
        raise ValueError("fresh C1 requires the independently regenerated ordered literal532 physical inventory")
    levels = bundle = None
    try:
        checkpoint("fresh_p6_cold_setup_begin", {"degrees": [6], "cell_count": 80,
                   "include_positive_coefficients": False, "PDE_solved": False})
        levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False)
        levels["declared_degrees"] = (6,)
        levels["mode_sha256"] = mode_sha
        actual_cells = int(levels["mesh"].topology.index_map(levels["mesh"].topology.dim).size_global)
        if actual_cells != 80 or set(levels["spaces"]) != {6} or set(levels["floquets"]) != {6}:
            raise ValueError("same-mesh setup differs from the single-degree 80-cell p6 fixture")
        checkpoint("fresh_p6_cold_setup_complete", {"cell_count": actual_cells,
                   "degree": 6, "PDE_solved": False})
        bundle = build_same_mesh_physical_action(
            levels, cfg, 6, dtn_phase_gauge=BOUNDARY_PLANE,
            verify_dtn_quadrature=True,
        )
        checkpoint("same_live_boundary_plane_bundle_complete", {
            "assembly_context_sha256": bundle["assembly_context_sha256"],
            "physical_generator_manifest_sha256": bundle["physical_generator_manifest_sha256"],
            "compiled_primary_Gauss_identity_present": bool(bundle["compiled_surface_gauss_identity"]),
            "mode_count": len(bundle["modes"]), "PDE_solved": False,
        })
        live = qualify_live_identity(
            bundle, record_path=root / "same_live_literal532.json",
            allocation_gate=allocation_gate, checkpoint=checkpoint,
        )
        worker = run_fresh_p6_component(
            bundle, allocation_gate=allocation_gate, save_array=save_array,
            checkpoint=checkpoint, archive_payload_limit_bytes=archive_payload_limit_bytes,
        )
        require_live_carrier_unchanged(bundle, live["carrier"], live["identity"], checkpoint)
        result = {
            **worker,
            "same_live_qualification": {
                "schema": live["receipt"]["schema"], "status": live["receipt"]["status"],
                "receipt_path": live["receipt_path"], "receipt_sha256": live["receipt_sha256"],
                "shared_discrete_contract": live["shared_discrete_contract"],
                "live_contract_source_sha256": live["live_contract_source_sha256"],
            },
            "w0_budget": budget,
            "source_identity": sources,
            "PDE_solved": False,
            "official_results": False,
        }
        json.dumps(result, allow_nan=False)
        checkpoint("fresh_c1_p6_bound_worker_receipt", result)
        return result
    finally:
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)
        levels = None


def _native_runtime_admission(identity: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    """Keep the original native admission schema and status for existing callers."""
    return {"schema": "task40extra.fresh-c1-p6-native-admission.v1",
            "status": "NATIVE_ABI_AND_SOURCE_ADMISSION_PASS_NO_FE_ACTION",
            "native_abi_identity": identity, "w0_budget": budget,
            "FE_action": "NOT_RUN", "PDE_solved": False}


def validate_native_runtime(abi_receipt_path: str | Path) -> dict[str, Any]:
    """Native-only public admission check; WSL receipts are rejected."""
    _mpi, _petsc, identity = _qualified_runtime(abi_receipt_path)
    if identity["runtime_profile"] != NATIVE_LINUX_PROFILE:
        raise RuntimeError("validate_native_runtime accepts only the native_linux profile")
    return _native_runtime_admission(identity, frozen_budget_identity())


def validate_fresh_runtime(abi_receipt_path: str | Path) -> dict[str, Any]:
    """No-FE admission check for the selected native or explicitly local WSL2 profile."""
    _mpi, _petsc, identity = _qualified_runtime(abi_receipt_path)
    budget = frozen_budget_identity()
    profile = identity["runtime_profile"]
    if profile == NATIVE_LINUX_PROFILE:
        return {**_native_runtime_admission(identity, budget),
                "runtime_profile": profile, "runtime_abi_identity": identity}
    if profile == LOCAL_WSL2_PROFILE:
        return {"schema": "task40extra.fresh-c1-p6-local-wsl2-admission.v1",
                "status": "LOCAL_WSL2_ABI_AND_SOURCE_ADMISSION_PASS_NO_FE_ACTION",
                "runtime_profile": profile, "runtime_abi_identity": identity,
                "w0_budget": budget, "FE_action": "NOT_RUN", "PDE_solved": False}
    raise RuntimeError(f"unsupported Task40 runtime profile: {profile!r}")


DISK_CAPS = {
    "raw": W0_ARCHIVE_PAYLOAD_LIMIT_BYTES,
    "control": 128 * 1024**2,
    "logs": 128 * 1024**2,
    "jit": 2 * 1024**3,
    "tmp": 1 * 1024**3,
}
FREE_RESERVE_BYTES = 2 * 1024**3
MINIMUM_START_FREE_BYTES = sum(DISK_CAPS.values()) + FREE_RESERVE_BYTES
WHOLE_MACHINE_DECIMAL_MEMORY_CAP_BYTES = 2_000_000_000_000
WORKER_CHECKER_WALL_SECONDS_MAX = 4500.0
W0_SUBREAPER_GRACE_SECONDS = 2.0
W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS = 30.0


def _phase_wall_budget_seconds(total_deadline_epoch: float, now_epoch: float) -> float:
    """Bound one phase and leave room for the watchdog's existing tree cleanup."""
    remaining = total_deadline_epoch - now_epoch - W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS
    return max(0.0, min(WORKER_CHECKER_WALL_SECONDS_MAX, remaining))


def _whole_machine_memory_occupancy_upper(envelope: dict[str, Any]) -> tuple[int, int]:
    total = envelope.get("mem_total_bytes")
    available = envelope.get("mem_available_bytes")
    if not isinstance(total, int) or not isinstance(available, int) or available > total:
        raise RuntimeError("physical MemTotal/MemAvailable admission evidence is unavailable")
    physical_used = total - available
    cgroup_used = max((int(item["current_bytes"]) for item in envelope.get("cgroup_limits", [])
                       if isinstance(item.get("current_bytes"), int)), default=0)
    return max(physical_used, cgroup_used), total


def _size_tree(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except FileNotFoundError:
            continue
    return total


def _disk_facts(root: Path, *, include_stop: bool = True) -> dict[str, Any]:
    categories = {
        "raw": _size_tree(root / "raw"),
        "control": sum(path.stat().st_size for pattern in ("*.json", "*.jsonl")
                        for path in root.glob(pattern) if path.is_file()),
        "logs": _size_tree(root / "logs") + _size_tree(root / "supervision"),
        "jit": _size_tree(root / "jit"),
        "tmp": _size_tree(root / "tmp"),
    }
    free = shutil.disk_usage(root).free
    over = {name: value for name, value in categories.items() if value > DISK_CAPS[name]}
    stop = bool(over or free < FREE_RESERVE_BYTES)
    return {"stop": stop if include_stop else False,
            "reason": "EXTERNAL_RESOURCE_CONTROLLED_STOP" if stop else None,
            "category_bytes": categories, "category_caps_bytes": DISK_CAPS,
            "free_bytes": free, "free_reserve_bytes": FREE_RESERVE_BYTES,
            "over_cap_categories": over,
            "raw_archive_created": False,
            "scope": "one canonical raw-member directory; control/log/JIT/tmp caps are separately monitored"}


def _atomic_json(path: Path, value: Any) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _native_callbacks(root: Path, *, checker: bool = False):
    import numpy as np

    stage = "checker" if checker else "worker"
    events = root / ("checker_events.jsonl" if checker else "worker_events.jsonl")
    raw = root / "raw"
    raw_upper_bytes = [0]
    guard_cache = {"sampled_monotonic": 0.0, "facts": None}

    def guard():
        now = time.monotonic()
        facts = guard_cache["facts"]
        if facts is None or now - guard_cache["sampled_monotonic"] >= 1.0:
            facts = _disk_facts(root)
            guard_cache["facts"] = facts
            guard_cache["sampled_monotonic"] = now
        else:
            free = shutil.disk_usage(root).free
            facts = {**facts, "free_bytes": free,
                     "stop": facts.get("stop") or free < FREE_RESERVE_BYTES,
                     "reason": facts.get("reason") or
                         ("EXTERNAL_RESOURCE_CONTROLLED_STOP" if free < FREE_RESERVE_BYTES else None)}
        return facts

    def write_event(stage_name: str, facts: dict[str, Any]):
        _atomic_append = events.open("a", encoding="utf-8")
        try:
            _atomic_append.write(json.dumps({"time_ns": time.time_ns(), "stage": stage_name,
                                             "facts": facts}, sort_keys=True,
                                            allow_nan=False) + "\n")
            _atomic_append.flush()
        finally:
            _atomic_append.close()
        if events.stat().st_size > DISK_CAPS["control"]:
            raise RuntimeError("bounded control/checkpoint budget exceeded")

    def allocation_gate(stage_name: str, facts: dict[str, Any]):
        disk = guard()
        if disk["stop"]:
            raise RuntimeError("disk category/free-reserve guard rejected allocation: " + json.dumps(disk))
        payload = int(facts.get("matrix_payload_bytes", 0))
        workspace = int(facts.get("workspace_bytes", 0))
        from benchmarks.subreaper_watchdog import memory_envelope
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        try:
            parent_pid = int(os.environ["PHYSICAL_WATCHDOG_PARENT_PID"])
        except (KeyError, ValueError) as error:
            raise RuntimeError("allocation gate requires the live subreaper identity") from error
        tree = process_tree_snapshot(parent_pid, "allocation_gate", None,
                                     pss_sampling_policy="disabled_by_profile")
        envelope = memory_envelope()
        evidence_reserve = 128 * 1024**2
        projected_tree = int(tree["rss_bytes"]) + payload + workspace + evidence_reserve
        projected_capacity = payload + workspace + evidence_reserve
        machine_used, physical_total = _whole_machine_memory_occupancy_upper(envelope)
        projected_machine = machine_used + projected_capacity
        if (min(payload, workspace) < 0 or projected_tree > 3 * 1024**3
                or envelope["launch_cap_bytes"] < projected_capacity
                or projected_machine > WHOLE_MACHINE_DECIMAL_MEMORY_CAP_BYTES):
            raise MemoryError("RSS + declared new allocations + evidence reserve exceed the current process/cgroup envelope")
        write_event(stage_name, {**facts, "disk_guard": disk,
            "allocation_gate": {"process_tree_rss_bytes": int(tree["rss_bytes"]),
                "additional_matrix_payload_bytes": payload,
                "additional_workspace_bytes": workspace,
                "evidence_reserve_bytes": evidence_reserve,
                "projected_tree_with_reserve_bytes": projected_tree,
                "process_tree_cap_bytes": 3 * 1024**3,
                "effective_machine_total_bytes": min(int(envelope["effective_total_bytes"]), 2_000_000_000_000),
                "physical_total_bytes": physical_total,
                "whole_machine_current_occupancy_upper_bytes": machine_used,
                "whole_machine_projected_occupancy_upper_bytes": projected_machine,
                "machine_ceiling_decimal_bytes": WHOLE_MACHINE_DECIMAL_MEMORY_CAP_BYTES,
                "effective_available_bytes": int(envelope["effective_available_bytes"]),
                "cgroup_limits": envelope["cgroup_limits"],
                "launch_cap_bytes": int(envelope["launch_cap_bytes"]),
                "pss_sampling_policy": "disabled_by_profile"}})

    def save_array(role: str, array: Any):
        raw.mkdir(parents=True, exist_ok=True)
        safe_name = hashlib.sha256(role.encode("utf-8")).hexdigest() + ".npy"
        path = raw / safe_name
        if path.exists():
            raise FileExistsError("array role attempted to overwrite a raw member")
        upper = int(np.asarray(array).nbytes) + 4096
        if raw_upper_bytes[0] + upper > DISK_CAPS["raw"]:
            raise RuntimeError("raw .npy member upper would exceed the frozen 8 GiB cap")
        if shutil.disk_usage(root).free - upper < FREE_RESERVE_BYTES:
            raise RuntimeError("raw .npy export would consume the 2 GiB filesystem reserve")
        with path.open("xb") as stream:
            np.save(stream, np.asarray(array), allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        raw_upper_bytes[0] += upper
        return str(path)

    def checkpoint(stage_name: str, facts: dict[str, Any]):
        write_event(stage_name, facts)

    return allocation_gate, save_array, checkpoint, guard


def _worker_cli(root: Path, abi_receipt: Path) -> int:
    allocation_gate, save_array, checkpoint, _guard = _native_callbacks(root)
    result = run(output_dir=root, allocation_gate=allocation_gate, save_array=save_array,
                 checkpoint=checkpoint, abi_receipt_path=abi_receipt)
    _atomic_json(root / "worker_report.json", result)
    return 0


def _checker_cli(root: Path, abi_receipt: Path) -> int:
    _qualified_runtime(abi_receipt)
    report = json.loads((root / "worker_report.json").read_text())
    allocation_gate, _save_array, checkpoint, _guard = _native_callbacks(root, checker=True)
    import numpy as np
    from benchmarks.check_fresh_c1_p6_component import check_component

    def load_array(reference: dict[str, Any]):
        name = reference.get("name")
        location = reference.get("callback_reference")
        if not isinstance(name, str) or not isinstance(location, str):
            raise ValueError("raw member reference lacks its worker-exported path")
        expected = (root / "raw" / (hashlib.sha256(name.encode("utf-8")).hexdigest()+".npy")).resolve()
        if Path(location).resolve() != expected or not expected.is_file():
            raise ValueError("worker raw member path is outside the canonical artifact directory")
        value = np.load(expected, mmap_mode="r", allow_pickle=False)
        if list(value.shape) != reference.get("shape") or str(value.dtype) != reference.get("dtype"):
            raise ValueError("raw member shape/dtype differs from worker descriptor")
        return value

    result = check_component(report, load_array, allocation_gate=allocation_gate, checkpoint=checkpoint)
    _atomic_json(root / "checker_report.json", result)
    return 0


def _control_smoke_leaf(root: Path, abi_receipt: Path, phase: str) -> int:
    """No-FE sentinel leaf used only to exercise the native user-service controls."""
    if phase not in {"worker", "checker"}:
        raise ValueError("control-smoke leaf phase must be worker or checker")
    _qualified_runtime(abi_receipt)
    root = root.resolve()
    contract = json.loads((root / "control_smoke_contract.json").read_text())
    token = contract.get("token")
    expected_parent = contract.get("service_pid")
    actual_parent = os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID")
    if (not isinstance(token, str) or len(token) != 32
            or not isinstance(expected_parent, int)
            or actual_parent != str(expected_parent)
            or os.getppid() != expected_parent):
        raise RuntimeError("control-smoke sentinel is outside its live supervised service parent")
    if phase == "worker":
        report = {"status": "CONTROL_SMOKE_WORKER_SENTINEL_PASS", "token": token,
                  "pid": os.getpid(), "parent_pid": os.getppid(),
                  "PDE_solved": False, "official_results": False, "FE_or_JIT": "NOT_RUN"}
        _atomic_json(root / "worker_report.json", report)
        return 0
    worker = json.loads((root / "worker_report.json").read_text())
    if (worker.get("status") != "CONTROL_SMOKE_WORKER_SENTINEL_PASS"
            or worker.get("token") != token or worker.get("PDE_solved") is not False
            or worker.get("official_results") is not False
            or worker.get("parent_pid") != expected_parent
            or not isinstance(worker.get("pid"), int) or worker["pid"] <= 0):
        raise RuntimeError("control-smoke checker did not receive the supervised worker sentinel")
    report = {"status": "CONTROL_SMOKE_CHECKER_SENTINEL_PASS", "token": token,
              "pid": os.getpid(), "parent_pid": os.getppid(), "worker_pid": worker["pid"],
              "PDE_solved": False, "official_results": False, "FE_or_JIT": "NOT_RUN"}
    _atomic_json(root / "checker_report.json", report)
    return 0


def _control_smoke_passes(contract: dict[str, Any], worker: dict[str, Any],
                          checker: dict[str, Any], worker_supervisor: dict[str, Any],
                          checker_supervisor: dict[str, Any]) -> bool:
    """Require actual phase reports, distinct child PIDs and watchdog cleanup."""
    def cleared(summary: dict[str, Any]) -> bool:
        return (summary.get("classification") == "COMPLETED"
                and summary.get("descendants_cleared") is True
                and summary.get("remaining_child_pids") == [])

    worker_pid, checker_pid = worker.get("pid"), checker.get("pid")
    service_pid = contract.get("service_pid")
    return (
        contract.get("PDE_solved") is False
        and worker.get("status") == "CONTROL_SMOKE_WORKER_SENTINEL_PASS"
        and checker.get("status") == "CONTROL_SMOKE_CHECKER_SENTINEL_PASS"
        and worker.get("token") == checker.get("token") == contract.get("token")
        and isinstance(service_pid, int) and service_pid > 0
        and isinstance(worker_pid, int) and worker_pid > 0
        and isinstance(checker_pid, int) and checker_pid > 0
        and worker_pid != checker_pid
        and worker.get("parent_pid") == checker.get("parent_pid") == service_pid
        and checker.get("worker_pid") == worker_pid
        and worker.get("PDE_solved") is False and checker.get("PDE_solved") is False
        and worker.get("official_results") is False and checker.get("official_results") is False
        and cleared(worker_supervisor) and cleared(checker_supervisor)
    )


def _supervise_phase(root: Path, phase: str, abi_receipt: Path,
                     total_deadline_epoch: float, *, control_smoke: bool = False) -> dict[str, Any]:
    from benchmarks.subreaper_watchdog import supervise

    remaining = _phase_wall_budget_seconds(total_deadline_epoch, time.time())
    if remaining <= 1:
        raise TimeoutError("fixed UTC deadline is inside the W0 settlement/cleanup reserve")
    directory = root / "supervision" / phase
    env = {**os.environ, "XDG_CACHE_HOME": str(root / "jit"), "TMPDIR": str(root / "tmp"),
           "TMP": str(root / "tmp"), "TEMP": str(root / "tmp"),
           "PHYSICAL_WATCHDOG_PARENT_PID": str(os.getpid())}
    leaf_mode = (["--control-smoke-leaf", phase] if control_smoke else
                 ["--worker" if phase == "worker" else "--checker-worker"])
    command = [sys.executable, "-m", "benchmarks.run_fresh_c1_p6_component",
               *leaf_mode, "--output-dir", str(root), "--abi-receipt", str(abi_receipt)]
    deadline_guard_last_scan = [0.0]
    deadline_guard_cached = [{}]

    def deadline_guard():
        now = time.time()
        monotonic_now = time.monotonic()
        if monotonic_now - deadline_guard_last_scan[0] >= 1.0:
            deadline_guard_cached[0] = _disk_facts(root)
            deadline_guard_last_scan[0] = monotonic_now
        facts = {**deadline_guard_cached[0],
                 "total_deadline_utc_epoch": total_deadline_epoch,
                 "utc_now_epoch": now,
                 "remaining_total_seconds": max(0.0, total_deadline_epoch-now),
                 "settlement_cleanup_reserve_seconds": W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS,
                 "remaining_before_settlement_cleanup_reserve": _phase_wall_budget_seconds(
                     total_deadline_epoch, now)}
        if now >= total_deadline_epoch - W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS:
            facts.update({"stop": True, "reason": "TOTAL_UTC_DEADLINE_SETTLEMENT_RESERVE"})
        return facts

    summary = supervise(command, directory, wall_seconds=remaining, interval=.25,
                        grace_seconds=W0_SUBREAPER_GRACE_SECONDS,
                        tree_cap_bytes=3 * 1024**3, stop_on_global_swap=True,
                        worker_environment=env, cache_path=root / "jit",
                        external_guard=deadline_guard,
                        pss_sampling_policy="disabled_by_profile")
    _atomic_json(root / f"{phase}_supervisor_summary.json", summary)
    return summary


def _supervised_cli(root: Path, abi_receipt: Path, total_deadline_utc: str,
                    *, control_smoke: bool = False) -> int:
    _qualified_runtime(abi_receipt)
    root = root.resolve()
    if not root.is_dir() or not abi_receipt.is_file():
        raise FileNotFoundError("Task40 service requires the new run directory and local ABI receipt")
    for name in ("raw", "logs", "jit", "tmp", "supervision"):
        (root / name).mkdir(exist_ok=True)
    initial_free = shutil.disk_usage(root).free
    admission = validate_fresh_runtime(abi_receipt)
    from benchmarks.subreaper_watchdog import memory_envelope
    initial_memory = memory_envelope()
    initial_machine_used, physical_total = _whole_machine_memory_occupancy_upper(initial_memory)
    sources = source_identity()
    input_identity = {"path": str(INPUT.resolve()), "sha256": _sha256(INPUT)}
    if input_identity["sha256"] != INPUT_SHA256:
        raise ValueError("frozen original review-v1 input bytes changed before worker admission")
    disk_caps_and_reserve = MINIMUM_START_FREE_BYTES
    if initial_free < disk_caps_and_reserve:
        _atomic_json(root / "admission.json", {**admission, "source_identity": sources,
            "input_identity": input_identity,
            "status": "CONTROLLED_STOP_STORAGE_ADMISSION",
            "initial_free_bytes": initial_free,
            "minimum_start_free_bytes_for_all_separate_caps_and_reserve": disk_caps_and_reserve})
        return 2
    if (initial_memory["launch_cap_bytes"] <= 0
            or initial_machine_used + 128 * 1024**2 > WHOLE_MACHINE_DECIMAL_MEMORY_CAP_BYTES):
        _atomic_json(root / "admission.json", {**admission, "source_identity": sources,
            "input_identity": input_identity, "status": "CONTROLLED_STOP_PHYSICAL_MEMORY_ADMISSION",
            "memory_envelope": initial_memory,
            "whole_machine_current_occupancy_upper_bytes": initial_machine_used,
            "physical_total_bytes": physical_total,
            "machine_ceiling_decimal_bytes": WHOLE_MACHINE_DECIMAL_MEMORY_CAP_BYTES})
        return 7
    _atomic_json(root / "admission.json", {**admission, "source_identity": sources,
        "input_identity": input_identity,
            "status": ("NATIVE_ABI_AND_DISK_ADMISSION_PASS_NO_FE_ACTION"
                       if admission["runtime_profile"] == NATIVE_LINUX_PROFILE else
                       "LOCAL_WSL2_ABI_AND_DISK_ADMISSION_PASS_NO_FE_ACTION"),
        "initial_free_bytes": initial_free,
        "minimum_start_free_bytes_for_all_separate_caps_and_reserve": disk_caps_and_reserve,
        "disk_category_caps_bytes": DISK_CAPS,
        "filesystem_free_reserve_bytes": FREE_RESERVE_BYTES,
        "memory_envelope": initial_memory,
        "whole_machine_current_occupancy_upper_bytes": initial_machine_used,
        "physical_total_bytes": physical_total,
        "machine_ceiling_decimal_bytes": WHOLE_MACHINE_DECIMAL_MEMORY_CAP_BYTES,
        "raw_archive_created": False})
    from datetime import datetime, timezone
    if not total_deadline_utc.endswith("Z"):
        raise ValueError("frozen total deadline must be an explicit UTC Z timestamp")
    total_deadline_epoch = datetime.strptime(total_deadline_utc,
        "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    if _phase_wall_budget_seconds(total_deadline_epoch, time.time()) <= 1:
        _atomic_json(root / "run_summary.json", {"status": "TOTAL_UTC_DEADLINE_SETTLEMENT_RESERVE_BEFORE_WORKER",
            "total_deadline_utc": total_deadline_utc,
            "settlement_cleanup_reserve_seconds": W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS,
            "PDE_solved": False, "official_results": False})
        return 6
    contract = None
    if control_smoke:
        contract = {"schema": "task40extra.w0-no-fe-control-smoke.v1",
                    "token": os.urandom(16).hex(), "service_pid": os.getpid(),
                    "total_deadline_utc": total_deadline_utc,
                    "PDE_solved": False, "official_results": False}
        _atomic_json(root / "control_smoke_contract.json", contract)
    worker_summary = _supervise_phase(root, "worker", abi_receipt, total_deadline_epoch,
                                      control_smoke=control_smoke)
    worker_path = root / "worker_report.json"
    if (worker_summary.get("classification") != "COMPLETED"
            or not worker_path.is_file()
            or (control_smoke and (worker_summary.get("descendants_cleared") is not True
                                   or worker_summary.get("remaining_child_pids") != []))):
        status = "CONTROL_SMOKE_WORKER_FAILED" if control_smoke else "WORKER_NOT_COMPLETED"
        _atomic_json(root / "run_summary.json", {"status": status,
            "worker_supervisor": worker_summary, "PDE_solved": False, "official_results": False})
        return 3
    worker = json.loads(worker_path.read_text())
    if control_smoke and (worker.get("status") != "CONTROL_SMOKE_WORKER_SENTINEL_PASS"
            or worker.get("token") != contract["token"]
            or worker.get("parent_pid") != contract["service_pid"]
            or worker.get("PDE_solved") is not False):
        _atomic_json(root / "run_summary.json", {"status": "CONTROL_SMOKE_WORKER_FAILED",
            "worker_supervisor": worker_summary, "worker_report": worker,
            "PDE_solved": False, "official_results": False})
        return 3
    if _phase_wall_budget_seconds(total_deadline_epoch, time.time()) <= 1:
        _atomic_json(root / "run_summary.json", {"status": "TOTAL_UTC_DEADLINE_SETTLEMENT_RESERVE_BEFORE_CHECKER",
            "worker_supervisor": worker_summary,
            "total_deadline_utc": total_deadline_utc,
            "settlement_cleanup_reserve_seconds": W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS,
            "PDE_solved": False, "official_results": False})
        return 6
    checker_summary = _supervise_phase(root, "checker", abi_receipt, total_deadline_epoch,
                                        control_smoke=control_smoke)
    checker_path = root / "checker_report.json"
    if checker_summary.get("classification") != "COMPLETED" or not checker_path.is_file():
        status = "CONTROL_SMOKE_CHECKER_FAILED" if control_smoke else "CHECKER_NOT_COMPLETED"
        _atomic_json(root / "run_summary.json", {"status": status,
            "worker_supervisor": worker_summary, "checker_supervisor": checker_summary,
            "PDE_solved": False, "official_results": False})
        return 4
    checker = json.loads(checker_path.read_text())
    if control_smoke:
        status = ("CONTROL_SMOKE_PASS_NO_FE"
                  if _control_smoke_passes(contract, worker, checker, worker_summary, checker_summary)
                  else "CONTROL_SMOKE_FAILED")
    else:
        status = "PASS_COMPONENT_ONLY" if checker.get("independent_component_pass") is True else "CHECKER_FAILED"
    run_summary = {"status": status,
        "source_identity_manifest_sha256": sources["manifest_sha256"],
        "input_identity": input_identity,
        "runtime_profile": admission["runtime_profile"],
        "runtime_abi_identity": admission["runtime_abi_identity"],
        "worker_supervisor": worker_summary, "checker_supervisor": checker_summary,
        "PDE_solved": False, "official_results": False, "raw_archive_created": False}
    if admission["runtime_profile"] == NATIVE_LINUX_PROFILE:
        run_summary["native_abi_identity"] = admission["native_abi_identity"]
    if control_smoke:
        run_summary.update({"total_deadline_utc": total_deadline_utc,
            "settlement_cleanup_reserve_seconds": W0_SETTLEMENT_CLEANUP_RESERVE_SECONDS,
            "worker_report": worker, "checker_report": checker})
    else:
        run_summary.update({"worker_report_sha256": _sha256(worker_path),
            "checker_report_sha256": _sha256(checker_path),
            "raw_member_directory": str(root / "raw")})
    _atomic_json(root / "run_summary.json", run_summary)
    return 0 if status in {"PASS_COMPONENT_ONLY", "CONTROL_SMOKE_PASS_NO_FE"} else 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--abi-receipt", required=True)
    parser.add_argument("--total-deadline-utc")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--admission-only", action="store_true")
    mode.add_argument("--supervised", action="store_true")
    mode.add_argument("--worker", action="store_true")
    mode.add_argument("--checker-worker", action="store_true")
    mode.add_argument("--control-smoke-leaf", choices=("worker", "checker"), help=argparse.SUPPRESS)
    parser.add_argument("--control-smoke", action="store_true",
                        help="run the selected runtime-profile admission/supervision with non-numerical worker/checker sentinels")
    args = parser.parse_args(argv)
    root, receipt = Path(args.output_dir).resolve(), Path(args.abi_receipt).resolve()
    if args.control_smoke and not args.supervised:
        parser.error("--control-smoke requires --supervised")
    if args.admission_only:
        print(json.dumps(validate_fresh_runtime(receipt), indent=2, sort_keys=True))
        return 0
    if args.worker:
        return _worker_cli(root, receipt)
    if args.checker_worker:
        return _checker_cli(root, receipt)
    if args.control_smoke_leaf:
        return _control_smoke_leaf(root, receipt, args.control_smoke_leaf)
    if not args.total_deadline_utc:
        parser.error("--supervised and --control-smoke require the frozen --total-deadline-utc")
    return _supervised_cli(root, receipt, args.total_deadline_utc,
                           control_smoke=args.control_smoke)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ("INPUT", "INPUT_SHA256", "W0_ARCHIVE_PAYLOAD_LIMIT_BYTES",
           "W0_EXPECTED_DERIVED_UPPER_BYTES", "pilot_config", "integer_admission",
           "frozen_budget_identity", "source_identity", "run", "validate_fresh_runtime",
           "validate_native_runtime", "main")
