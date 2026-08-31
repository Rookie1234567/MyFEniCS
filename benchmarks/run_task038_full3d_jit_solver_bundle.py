"""Build one physical p6 bundle and observe its cache-hit FFCx calls.

This child deliberately stops after bundle audit and destruction.  It does not
construct a physical RHS, KSP, restart reserve, solve, or recovery field.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import sys
from typing import Any


MODULE = "benchmarks.run_task038_full3d_jit_solver_bundle"
RECORD_SCHEMA = "task038.v14.j3.split-cold-staged.solver-record.v1"
MARKER_SCHEMA = "task038.v14.j3.marker.v1"
MARKER_ORDER = (
    "parent_started",
    "fresh_cache_created",
    "precompile_positive_p6_started",
    "precompile_positive_p6_complete",
    "precompile_positive_p3_started",
    "precompile_positive_p3_complete",
    "precompile_positive_p1_started",
    "precompile_positive_p1_complete",
    "precompile_dtn_surface_started",
    "precompile_dtn_surface_complete",
    "precompile_incident_rhs_started",
    "precompile_incident_rhs_complete",
    "precompile_physical_volume_started",
    "precompile_physical_volume_curl_started",
    "precompile_physical_volume_curl_complete",
    "precompile_physical_volume_mass_started",
    "precompile_physical_volume_mass_complete",
    "precompile_physical_volume_complete",
    "all_precompile_children_gone",
    "solver_child_started",
    "positive_setup_started",
    "positive_setup_complete",
    "mode_inventory_started",
    "mode_inventory_complete",
    "surface_assemblers_started",
    "surface_assemblers_complete",
    "dtn_carrier_started",
    "dtn_carrier_complete",
    "dtn_action_complete",
    "physical_volume_action_started",
    "physical_volume_action_complete",
    "bundle_built",
    "source_built",
    "one_action_complete",
    "one_pc_complete",
    "solve_started",
    "solve_complete",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "recovery_started",
    "recovery_complete",
    "parent_complete",
)
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
EXPECTED_MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
EXPECTED_PROFILE = {
    "model_id": "euv_grazing1_phi0",
    "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
    "comparison_group": "euv_grazing1_phi0",
    "wavelength_nm": 13.5,
    "grazing_angle_deg": 1.0,
    "incident_theta_deg": 89.0,
    "incident_phi_deg": 0.0,
    "polarization": "s",
    "nedelec_degree": 6,
    "mesh_target_size_nm": 10.0,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
    "boundary_model": "dtn_port",
    "dtn_order_policy": "auto_propagating",
    "dtn_assembly": "auxiliary",
}


def _split_physical_audit(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("physical bundle audit is missing")
    volume = value.get("volume_action")
    if (
        value.get("physical_form")
        != "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn"
        or value.get("volume_component_count") != 2
        or value.get("volume_components") != ["curl_curl", "complex_material_mass"]
        or not isinstance(volume, dict)
        or volume.get("schema") != "task038.fullspace-split-volume-action.v1"
        or volume.get("operator") != "A_curl_curl_plus_A_complex_material_mass"
        or volume.get("component_count") != 2
        or set(volume.get("components", {}))
        != {"curl_curl", "complex_material_mass"}
        or volume.get("constraint_identity_rows_exactly_once") is not True
        or volume.get("third_persistent_sum_vector") is not False
    ):
        raise RuntimeError("physical bundle audit is not the exact split volume audit")
    components = volume["components"]
    for name, slave_identity in (("curl_curl", True), ("complex_material_mass", False)):
        component = components.get(name)
        if (
            not isinstance(component, dict)
            or component.get("schema") != "task038.fullspace-mpc-form-action.v1"
            or component.get("operator") != "uncondensed_fullspace_curl_mass_form"
            or component.get("slave_row_identity") is not slave_identity
            or any(
                component.get(key) is not False
                for key in (
                    "global_matrix_materialized",
                    "global_constraint_matrix_materialized",
                    "global_condensed_schur_materialized",
                    "cell_schur_matrix_materialized",
                    "slab_matrix_materialized",
                )
            )
        ):
            raise RuntimeError(f"physical bundle audit component is invalid: {name}")
    return value


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _write_json(path: Path, value: Any) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        return _jsonable(item())
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _jsonable(tolist())
    return str(value)


def _read_markers(marker_dir: Path) -> list[Path]:
    paths = sorted(marker_dir.glob("*.json"), key=lambda path: int(path.name.split("_", 1)[0]))
    names = []
    for path in paths:
        names.append(path.name.split("_", 1)[1].rsplit(".", 1)[0])
    if any(name not in MARKER_ORDER for name in names):
        raise ValueError("unknown marker written by solver child")
    if [MARKER_ORDER.index(name) for name in names] != sorted(
        MARKER_ORDER.index(name) for name in names
    ):
        raise ValueError("solver markers are not ordered")
    return paths


def _install_ffcx_observer(jit_module: Any) -> tuple[list[dict[str, Any]], Any]:
    original = jit_module.ffcx_jit
    calls: list[dict[str, Any]] = []

    def observed(*args: Any, **kwargs: Any) -> Any:
        compiled_object, module, returned_code = original(*args, **kwargs)
        if not isinstance(returned_code, tuple) or len(returned_code) != 2:
            raise RuntimeError("dolfinx.jit.ffcx_jit returned an invalid code tuple")
        code = [None if item is None else "<non_none>" for item in returned_code]
        module_file = getattr(module, "__file__", None)
        calls.append(
            {
                "index": len(calls),
                "module_name": getattr(module, "__name__", None),
                "module_file": None if module_file is None else str(Path(module_file).absolute()),
                "code": code,
                "cache_hit": code == [None, None],
            }
        )
        return compiled_object, module, returned_code

    jit_module.ffcx_jit = observed
    return calls, original


def _restore_ffcx_observer(jit_module: Any, original: Any) -> None:
    jit_module.ffcx_jit = original


def _callback(marker_dir: Path, cache_dir: Path, raw_dir: Path, source_sha: str, comm: Any):
    from benchmarks.task038_full3d_jit_staging import write_marker

    def emit(name: str, facts: dict[str, Any]) -> None:
        merged = {
            "stage": "j3-split-cold-staged-solver",
            "artifact_root": str(cache_dir.parent),
            "cache_dir": str(cache_dir),
            "source_sha": source_sha,
            "worker_pid": int(os.getpid()),
            "mpi_size": int(comm.size),
            "raw_dir": str(raw_dir),
        }
        merged.update(facts)
        write_marker(marker_dir, name, merged)

    return emit


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--marker-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cache_dir = _absolute(args.cache_dir)
    record_path = _absolute(args.record)
    marker_dir = _absolute(args.marker_dir)
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"parent-created cache is missing: {cache_dir}")
    if not marker_dir.is_dir():
        raise FileNotFoundError(f"parent-created marker directory is missing: {marker_dir}")
    if record_path.exists() or not record_path.parent.is_dir():
        raise FileExistsError(f"solver record is not fresh: {record_path}")
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)

    from mpi4py import MPI
    from petsc4py import PETSc
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        audit_p6_same_mesh_physical_bundle,
        build_p6_same_mesh_physical_bundle,
        destroy_p6_same_mesh_physical_bundle,
    )
    import dolfinx.jit as dolfinx_jit
    from benchmarks.run_task038_full3d_jit_precompile import (
        BRANCH,
        _mode_identity,
        _profile,
        _runtime_facts,
    )

    if args.expected_mpi_size != 1 or MPI.COMM_WORLD.size != 1:
        raise ValueError("J3 solver child is MPI1-only")
    root = Path(__file__).resolve().parents[1]
    runtime = _runtime_facts(root, args.expected_source_sha, MPI.COMM_WORLD, PETSc)
    input_path = _absolute(args.input)
    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    profile = _profile(specification, cfg)
    if (
        specification.input_sha256 != EXPECTED_INPUT_SHA256
        or specification.physical_model_sha256 != EXPECTED_PHYSICAL_MODEL_SHA256
        or profile != EXPECTED_PROFILE
    ):
        raise RuntimeError("solver child input is not the frozen exact p6/h10 profile")
    mode_count, mode_sha, qdegree = _mode_identity(cfg)
    if mode_sha != EXPECTED_MODE_MANIFEST_SHA256:
        raise RuntimeError("solver child mode inventory is not the frozen manifest")
    calls, observer_original = _install_ffcx_observer(dolfinx_jit)
    bundle: dict[str, Any] = {}
    try:
        bundle = build_p6_same_mesh_physical_bundle(
            cfg,
            MPI.COMM_WORLD,
            stage_callback=_callback(
                marker_dir,
                cache_dir,
                record_path.parent,
                args.expected_source_sha,
                MPI.COMM_WORLD,
            ),
        )
        audit = audit_p6_same_mesh_physical_bundle(bundle)
        physical_audit = _split_physical_audit(
            _jsonable(audit["physical_action"])
        )
    finally:
        if bundle:
            destroy_p6_same_mesh_physical_bundle(bundle)
        _restore_ffcx_observer(dolfinx_jit, observer_original)
        gc.collect()
        PETSc.garbage_cleanup(MPI.COMM_WORLD)
        gc.collect()
    markers = _read_markers(marker_dir)
    record = {
        "schema": RECORD_SCHEMA,
        "stage": "j3-split-cold-staged-solver",
        "source_sha": args.expected_source_sha,
        "branch": BRANCH,
        "command": [str(Path(sys.executable)), "-m", MODULE, *sys.argv[1:]],
        "identity": {
            "input_path": str(input_path),
            "input_sha256": specification.input_sha256,
            "physical_model_sha256": specification.physical_model_sha256,
            "mode_manifest_sha256": mode_sha,
            "profile": profile,
        },
        "paths": {
            "artifact_root": str(cache_dir.parent),
            "cache_dir": str(cache_dir),
            "marker_dir": str(marker_dir),
            "record": str(record_path),
        },
        "runtime": runtime,
        "mode": {
            "count": mode_count,
            "manifest_sha256": mode_sha,
            "dtn_quadrature_degree": qdegree,
        },
        "ffcx_calls": calls,
        "expected_ffcx_call_count": 10,
        "setup_audit": _jsonable(audit["setup_audit"]),
        "physical_audit": physical_audit,
        "architecture": {
            "p6_matrix_free": True,
            "p6_global_aij": False,
            "high_order_global_aij": False,
            "global_dense_transfer": False,
            "numeric_allgather": False,
            "p3_sparse_matrix_built": True,
            "p1_sparse_matrix_built": True,
            "p1_direct_factor_built": True,
            "same_mesh_pmg_built": True,
            "streaming_dtn_action_built": True,
            "dtn_carrier_built": True,
            "dtn_carrier_lifetime": "transient_released",
            "physical_volume_action_built": bool(
                physical_audit["volume_action"]["component_count"] == 2
            ),
            "volume_component_count": physical_audit["volume_component_count"],
            "volume_components": list(physical_audit["volume_components"]),
            "monolithic_physical_volume": not (
                physical_audit["physical_form"]
                == "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn"
                and physical_audit["volume_action"]["schema"]
                == "task038.fullspace-split-volume-action.v1"
            ),
            "rhs_built": False,
            "outer_ksp_built": False,
            "solve_run": False,
            "recovery_run": False,
            "bundle_destroyed_before_record": True,
        },
        "marker_names": [
            path.name.split("_", 1)[1].rsplit(".", 1)[0] for path in markers
        ],
        "raw_facts_only": True,
    }
    if len(calls) != 10:
        record["ffcx_call_count_mismatch"] = True
    _write_json(record_path, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ("MODULE", "RECORD_SCHEMA", "main")
