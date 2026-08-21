"""Thin T5 authority runner.

The authority lane is intentionally action-only.  It binds the old W5
artifacts to the current T1 input, emits a concrete owner-local row-layout
witness, and uses the current dual canonical API before any residual is
converted.  The small fixture helpers are pure enough for contract tests; no
T5 sweep, KSP, PDE solve, or T4 transmission is started here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping

import numpy as np

T5_SCHEMA = "task038.full3d.iterative.t5.authority-record.v1"
T5_PROFILE = "full3d_scalable_v1"
T5_ROW_WITNESS_SCHEMA = "task038.t5.row-layout-manifest.v1"
T5_ROW_SHARD_SCHEMA = "task038.t5.row-layout-shard.v1"
OLD_SOURCE_SHA = "41cbbd454eb8336d9ea5378ed618447acfc60aac"
OLD_ARRAY_FACTS = {
    "rhs": {
        "file_sha256": "caf87001775247cb6967d6ebb244c8eb646bcd0d71c6e77410cd091488b1b87f",
        "array_sha256": "31384363d498673ab5e30a26d47042581756ecabfc0efe3dba7a956b3600c20f",
    },
    "outer_action": {
        "file_sha256": "f2605312bf172f91ad13d3a9855ed006b87419be9392f6dbef24c17b51b41de2",
        "array_sha256": "8adcfe14349403a5233a18b982e0490721d5ecbb4364757db2b7265c38e56108",
    },
    "solution": {
        "file_sha256": "d2a5a7e7b94a73d5212bc693d43282cace2883aadd0bb66780a3f8ae7b9e535e",
        "array_sha256": "620b5e496536d69c0bc471731b09a15424c29044e6836881ccd85340cbee0c39",
    },
    "residual": {
        "file_sha256": "4166665f2e3c302f0645d9581856ec1bc433de4679540e45f98eb1e161093cc6",
        "array_sha256": "35de8f03a1fdf4c410cff33ceee44a31831df418443c7534650308505114de98",
    },
}

T5_PHYSICAL_IDENTITY_SCHEMA = "task038.full3d.iterative.t5.physical-identity.v2"
T5_PHYSICAL_IDENTITY_RECORD_SCHEMA = (
    "task038.full3d.iterative.t5.physical-identity-record.v2"
)
T5_PHYSICAL_IDENTITY_FIELDS = (
    "wavelength",
    "geometry",
    "materials",
    "incidence",
    "floquet",
    "finite_element",
    "facet_normal",
    "ordered_modes",
    "incident_amplitudes",
    "rhs_composition",
    "mpc",
    "raw_config",
    "source_provenance",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(root: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git identity probe failed")
        return result.stdout.strip()

    return {
        "commit_sha": git("rev-parse", "HEAD"),
        "tracked_status": git("status", "--short", "--untracked-files=all"),
    }


def _git_blob_sha(root: Path, commit: str, relative_path: str) -> str:
    result = subprocess.run(
        [
            "git",
            "--git-dir=.git-codex",
            "--work-tree=.",
            "show",
            f"{commit}:{relative_path}",
        ],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return hashlib.sha256(result.stdout).hexdigest()


def _identity_available(value: Any, source: str) -> dict[str, Any]:
    return {"status": "available", "value": _jsonable(value), "source_evidence": source}


def _identity_unavailable(reason: str, source: str, known: Any | None = None) -> dict[str, Any]:
    result = {"status": "unavailable", "reason": reason, "source_evidence": source}
    if known is not None:
        result["known"] = _jsonable(known)
    return result


def _identity_file(path: Path) -> dict[str, Any]:
    path = path.resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256_path(path)}


def _mesh_identity_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("cell_type", "cells_global", "vertices_global", "geometry_shape",
            "canonical_connectivity_sha256", "canonical_geometry_sha256",
            "axis_counts", "digest_algorithm")
    return {key: value[key] for key in keys if key in value}


def _mode_identity(modes: Iterable[Any], cfg: Any) -> tuple[list[Mapping[str, Any]], list[complex], bytes, str]:
    from src.solvers.dtn_port_3d import _incident_projection_onto_top_mode
    from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest

    mode_rows, manifest_bytes, manifest_sha = build_ordered_mode_manifest(
        tuple(modes), cfg
    )
    amplitudes = [
        _incident_projection_onto_top_mode(mode, cfg) for mode in modes
    ]
    return list(mode_rows), amplitudes, manifest_bytes, manifest_sha


def _missing_identity_fields(reason: str, source: str) -> dict[str, Any]:
    return {name: _identity_unavailable(reason, source) for name in T5_PHYSICAL_IDENTITY_FIELDS}


def _old_identity_manifest(root: Path, old_dir: Path, summary: Mapping[str, Any], authority: Mapping[str, Any]) -> dict[str, Any]:
    scope = summary.get("scope", {})
    screen = summary.get("measurements", {}).get("screen", {})
    audit = screen.get("dtn_action_audit", {})
    old_mesh = authority.get("mesh_witnesses", {}).get("old_exact")
    if not isinstance(old_mesh, Mapping):
        raise RuntimeError("old exact mesh witness is missing")
    source_files = {
        name: {"commit_sha": OLD_SOURCE_SHA, "path": path, "sha256": _git_blob_sha(root, OLD_SOURCE_SHA, path)}
        for name, path in (("runner", "benchmarks/run_task037_extra_m6b.py"), ("dtn_port", "src/solvers/dtn_port_3d.py"))
    }
    raw_paths = {"mesh_h5": old_dir / "m6b_w5_mesh/mesh_3d.h5",
                 "mesh_xdmf": old_dir / "m6b_w5_mesh/mesh_3d.xdmf",
                 "dual_manifest": old_dir / "mpi1_candidate_physical_rhs_dual_manifest.json",
                 "dual_shard": old_dir / "mpi1_candidate_physical_rhs_dual_rank0.jsonl",
                 "summary": old_dir / "m6b_w5_summary.json"}
    raw_paths.update({name: old_dir / f"m6b_iter200_{name}.npy" for name in OLD_ARRAY_FACTS})
    fields = _missing_identity_fields("old field was not emitted as structured evidence", "old W5 summary/source")
    fields.update({
        "geometry": _identity_unavailable("physical dimensions are absent", "prior exact old mesh witness", _mesh_identity_fields(old_mesh)),
        "materials": _identity_unavailable("epsilon/loss values are absent", "old W5 material tag coverage", screen.get("material_tag_coverage")),
        "finite_element": _identity_unavailable("quadrature identity is absent", "old W5 scope/JIT audit", {"degree": scope.get("degree"), "h_nm": scope.get("h_nm")}),
        "facet_normal": _identity_unavailable("facet tag/normal was not structured", "old incident top traction source", {"side": "top", "normal": [0.0, 0.0, 1.0]}),
        "ordered_modes": _identity_unavailable("ordered mode rows were not preserved", "old W5 DTN audit", {"count": audit.get("mode_count"), "sha256": audit.get("mode_manifest_sha256")}),
        "rhs_composition": _identity_unavailable("component sign/H rows were not emitted", "old W5 rhs_binding", screen.get("rhs_binding")),
        "mpc": _identity_unavailable("MPC relation digest was not emitted", "old W5 scope", {"global_rows": scope.get("global_rows"), "constraint_count": scope.get("constraint_count")}),
        "source_provenance": _identity_available({"source_sha": OLD_SOURCE_SHA, "source_files": source_files, "abi": summary.get("runtime_identity")}, "old W5 summary"),
    })
    return {"schema": T5_PHYSICAL_IDENTITY_SCHEMA, "role": "historical_w5",
            "source": {"commit_sha": OLD_SOURCE_SHA, "source_files": source_files, "raw_root": str(old_dir.resolve())},
            "raw_artifacts": {name: _identity_file(path) for name, path in raw_paths.items()},
            "physical_identity": fields}


def _current_identity_manifest(
    root: Path,
    resolved: Mapping[str, Any],
    cfg: Any,
    modes: Iterable[Any],
    mode_path: Path,
    config_path: Path,
    authority_path: Path,
    authority: Mapping[str, Any],
    source: Mapping[str, Any],
    input_path: Path,
    physical_model_sha: str,
    quadrature_degree: int,
) -> dict[str, Any]:
    raw = Path(str(authority["raw_dir"])).resolve()
    mesh = authority["mesh_witnesses"]["current_generated"]
    rebuild = authority["mesh_witnesses"]["current_rebuild"]
    mpc = authority["mpc"]
    ordered, amplitudes, mode_manifest_bytes, mode_manifest_sha = _mode_identity(
        modes, cfg
    )
    geo, mat, inc, der = resolved["geometry"], resolved["materials"], resolved["incidence"], resolved["derived"]
    source_files = {
        name: {
            "commit_sha": source["commit_sha"],
            "path": path,
            "sha256": _git_blob_sha(root, source["commit_sha"], path),
        }
        for name, path in (
            ("input_validation", "src/io/input_validation.py"),
            ("dtn_port_3d", "src/solvers/dtn_port_3d.py"),
            ("fullspace_dtn_action", "src/solvers/fullspace_dtn_action.py"),
            ("fullspace_physical_action", "src/solvers/fullspace_physical_action.py"),
        )
    }
    fields = {
        "wavelength": _identity_available({"wavelength_nm": inc["wavelength_nm"]}, "T1 resolved config"),
        "geometry": _identity_available({"dimensions_nm": geo, "mesh_witness": _mesh_identity_fields(mesh), "rebuild": _mesh_identity_fields(rebuild)}, "T1 config and current mesh witnesses"),
        "materials": _identity_available({"names": [mat["grating_name"], mat["substrate_name"]], "n": [mat["n_air"], mat["n_grating"], mat["n_substrate"]], "epsilon": der["config_properties"], "mu_r": mat["mu_r"]}, "T1 materials/derived config"),
        "incidence": _identity_available({"wavelength_nm": inc["wavelength_nm"], "grazing_angle_deg": inc["grazing_angle_deg"], "theta_deg": der["internal"]["incident_theta_deg"], "azimuth_deg": inc["azimuth_deg"], "phi_deg": der["internal"]["incident_phi_deg"], "polarization": inc["polarization"], "vector": der["polarization"], "amplitude": inc["electric_amplitude"], "wavevector": der["wavevector"]}, "T1 incidence/derived fields"),
        "floquet": _identity_available({"kx": der["wavevector"][0], "ky": der["wavevector"][1], "phase_x": der["floquet_phase_x"], "phase_y": der["floquet_phase_y"], "constraint_mode": der["floquet_constraint_mode_requested"]}, "T1 Floquet fields"),
        "finite_element": _identity_available({"family": "N1E", "map": "covariantPiola", "degree": resolved["discretization"]["nedelec_degree"], "cell_type": resolved["discretization"]["mesh_cell_type"], "quadrature_degree": int(quadrature_degree)}, "T1 discretization/current production DtN policy"),
        "facet_normal": _identity_available({"side": "top", "tag": "z_max", "normal": [0.0, 0.0, 1.0], "z_nm": geo["z_max_nm"]}, "current incident top traction contract"),
        "ordered_modes": _identity_available(ordered, "current dynamic mode manifest"),
        "incident_amplitudes": _identity_available(amplitudes, "current incident projection definition"),
        "rhs_composition": _identity_available({"base": "incident_top_traction", "coupling": "negative_mode_traction", "normalization": "H", "composition": "base + modal coupling", "phase": "finalized MPC once"}, "current compose_physical_rhs/DtN carrier contract"),
        "mpc": _identity_available({"global_rows": mpc["global_rows"], "local_owned_rows": mpc["local_owned_rows"], "constraint_count": mpc["constraint_count"], "constraint_mode": mpc["constraint_mode"], "relation_digest": mpc["relation_digest"], "row_witness_sha256": authority["row_layout_witness"]["manifest_sha256"]}, "current finalized MPC/row witness"),
        "raw_config": _identity_available({"template": _identity_file(input_path), "resolved": _identity_file(config_path), "physical_model_sha256": physical_model_sha}, "T1 load_and_resolve/resolved_config_bytes"),
        "source_provenance": _identity_available({"head_sha": source["commit_sha"], "tracked_status": source["tracked_status"], "dynamic_mode_manifest_sha256": mode_manifest_sha, "dynamic_mode_manifest_bytes": len(mode_manifest_bytes), "source_files": source_files}, "current production mode/projection/quadrature helpers and T1 adapter"),
    }
    paths = {"input_template": input_path, "resolved_config": config_path, "mode_manifest": mode_path,
             "authority_record": authority_path, "current_rhs_manifest": raw / "canonical/current_rhs.manifest.json",
             "mesh_h5": raw / "mesh/mesh_3d.h5", "mesh_xdmf": raw / "mesh/mesh_3d.xdmf",
             "row_layout_manifest": raw / "row_witness/row_layout.manifest.json"}
    return {"schema": T5_PHYSICAL_IDENTITY_SCHEMA, "role": "current_task038_extra",
            "source": {"commit_sha": source["commit_sha"], "tracked_status": source["tracked_status"], "raw_root": str(raw)},
            "raw_artifacts": {name: _identity_file(path) for name, path in paths.items()}, "physical_identity": fields}


def _identity_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate T5 physical identity manifests")
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--input", type=Path, default=Path("input/templates/full3d_iterative_example.dat"))
    parser.add_argument("--old-w5-dir", type=Path)
    parser.add_argument("--current-mode-manifest", type=Path)
    parser.add_argument("--current-authority-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    return parser


def _identity_main(argv: list[str]) -> int:
    args = _identity_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    source = _source_identity(root)
    if source["commit_sha"] != args.expected_source_sha:
        raise RuntimeError("identity source HEAD does not match expected SHA")
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        raise FileExistsError(f"identity output root already exists: {output}")
    output.mkdir(parents=True)
    def path_or_default(value: Path | None, default: str) -> Path:
        path = value or Path(default)
        return path if path.is_absolute() else root / path
    old_dir = path_or_default(args.old_w5_dir, "benchmarks/artifacts/task037_extra_development/m6b_w5_disk_fgmres_41cbbd4_screen_run1")
    mode_path = path_or_default(args.current_mode_manifest, "benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi1/raw/mode_manifest.json")
    authority_path = path_or_default(args.current_authority_record, "benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v1/mpi1/record.json")
    input_path = path_or_default(args.input, "input/templates/full3d_iterative_example.dat")
    from src.io import load_and_resolve
    from src.io.resolved_config import resolved_config_bytes
    specification = load_and_resolve(input_path)
    payload = resolved_config_bytes(specification)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    config_path = Path(str(authority["raw_dir"])) / "benchmark_input/resolved_config.json"
    if config_path.read_bytes() != payload:
        raise RuntimeError("current authority resolved config is not byte-equal to T1 adapter output")
    summary = json.loads((old_dir / "m6b_w5_summary.json").read_text(encoding="utf-8"))
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_ordered_mode_manifest,
    )

    cfg = simulation_config_3d_from_normalized(json.loads(payload))
    modes, inventory_rows, inventory_sha = build_dynamic_mode_inventory(cfg)
    mode_rows, mode_bytes, mode_sha = build_ordered_mode_manifest(modes, cfg)
    if tuple(inventory_rows) != tuple(mode_rows) or inventory_sha != mode_sha:
        raise RuntimeError("dynamic mode inventory is not production-manifest closed")
    if mode_bytes != mode_path.read_bytes():
        raise RuntimeError("dynamic mode manifest differs from frozen T3 manifest")
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    old = _old_identity_manifest(root, old_dir, summary, authority)
    current = _current_identity_manifest(root, json.loads(payload), cfg, modes, mode_path, config_path, authority_path, authority, source, input_path, specification.physical_model_sha256, quadrature_degree)
    old_path, current_path = output / "old_w5_physical_identity.json", output / "current_task038_physical_identity.json"
    old_path.write_bytes(_canonical_json(old) + b"\n")
    current_path.write_bytes(_canonical_json(current) + b"\n")
    old_rhs = old_dir / "mpi1_candidate_physical_rhs_dual_manifest.json"
    current_rhs = Path(str(authority["raw_dir"])) / "canonical/current_rhs.manifest.json"
    record = {"schema": T5_PHYSICAL_IDENTITY_RECORD_SCHEMA, "raw_root": str(output.resolve()),
              "source": {"expected_sha": args.expected_source_sha, "head_sha": source["commit_sha"], "tracked_status": source["tracked_status"]},
              "manifests": {"old": _identity_file(old_path), "current": _identity_file(current_path)},
              "rhs_observation": {"old_manifest": _identity_file(old_rhs), "current_manifest": _identity_file(current_rhs), "relative_tolerance": 1.0e-12, "comparison_purpose": "diagnosis only; no residual conversion"},
              "input": {"template": _identity_file(input_path), "resolved_config_sha256": hashlib.sha256(payload).hexdigest(), "resolved_config_bytes": len(payload)}}
    record_path = output / "r1_record.json"
    record_path.write_bytes(_canonical_json(record) + b"\n")
    print(json.dumps({"record": str(record_path), "mode_count": len(modes), "mode_manifest_sha256": mode_sha}, sort_keys=True))
    return 0


def _rss_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("current process VmRSS is unavailable")


def _swap_used_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("current process VmSwap is unavailable")


def _prepare_raw_dir(raw_dir: Path, record_path: Path, comm: Any) -> None:
    error: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("T5 raw directory or record already exists")
            raw_dir.mkdir(parents=True)
        except FileExistsError as exc:
            error = ("FileExistsError", str(exc))
        except OSError as exc:
            error = ("OSError", str(exc))
    error = comm.bcast(error, root=0)
    if error is not None:
        if error[0] == "FileExistsError":
            raise FileExistsError(error[1])
        raise OSError(error[1])
    comm.barrier()


def _old_w5_facts(old_dir: Path) -> tuple[dict[str, Any], np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    facts: dict[str, Any] = {
        "directory": str(old_dir.resolve()),
        "files": {},
    }
    for name, expected in OLD_ARRAY_FACTS.items():
        path = old_dir / f"m6b_iter200_{name}.npy"
        array = np.load(path, allow_pickle=False)
        file_sha = _sha256_path(path)
        array_sha = hashlib.sha256(
            np.ascontiguousarray(array).view(np.uint8)
        ).hexdigest()
        if file_sha != expected["file_sha256"] or array_sha != expected["array_sha256"]:
            raise RuntimeError(f"old W5 {name} artifact identity mismatch")
        if list(array.shape) != [173802] or str(array.dtype) != "complex128":
            raise RuntimeError(f"old W5 {name} shape/dtype mismatch")
        arrays[name] = array
        facts["files"][name] = {
            "relative_path": path.name,
            "file_sha256": file_sha,
            "array_sha256": array_sha,
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "bytes": int(path.stat().st_size),
            "finite": bool(np.all(np.isfinite(array))),
        }
    delta = arrays["residual"] - arrays["rhs"] + arrays["outer_action"]
    facts["residual_closure"] = {
        "max_abs": float(np.max(np.abs(delta))),
        "relative_l2": float(
            np.linalg.norm(delta) / max(float(np.linalg.norm(arrays["rhs"])), 1.0e-300)
        ),
    }
    residual = arrays["residual"]
    manifest_path = old_dir / "mpi1_candidate_physical_rhs_dual_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shard = manifest["per_rank_shards"][0]
    shard_path = old_dir / shard["filename"]
    facts["manifest"] = {
        "relative_path": manifest_path.name,
        "sha256": _sha256_path(manifest_path),
        "role": manifest.get("role"),
        "schema_version": manifest.get("schema_version"),
        "packet_count": manifest.get("global_summed_packet_count"),
        "shard_sha256": shard.get("file_sha256"),
        "shard_bytes": int(shard_path.stat().st_size),
        "ownership_range": shard.get("ownership_range"),
    }
    if manifest.get("role") != "candidate_physical_rhs_dual":
        raise RuntimeError("old W5 dual manifest role mismatch")
    return facts, np.asarray(residual, dtype=np.complex128)


def _old_facts_for_case(
    old_dir: Path, mpi1_record: Path | None, comm: Any
) -> tuple[dict[str, Any], np.ndarray | None]:
    if comm.size == 1:
        return _old_w5_facts(old_dir)
    if mpi1_record is None:
        raise RuntimeError("MPI2 requires --mpi1-record and physical residual input")
    payload = json.loads(mpi1_record.read_text(encoding="utf-8"))
    facts = payload.get("old_w5")
    if not isinstance(facts, Mapping):
        raise RuntimeError("MPI1 record does not contain old W5 facts")
    return dict(facts), None


def _runtime_identity() -> dict[str, Any]:
    import basix
    import dolfinx
    from petsc4py import PETSc

    return {
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "python": sys.executable,
        "dolfinx": dolfinx.__version__,
        "basix": basix.__version__,
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
    }


def _runtime_preflight(root: Path) -> dict[str, Any]:
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified WSL activation marker is not 1")
    runtime = _runtime_identity()
    executable = runtime.get("python")
    repo_venv = (root / ".venv").resolve()
    executable_ok = (
        isinstance(executable, str)
        and Path(executable).is_absolute()
        and Path(executable).is_relative_to(repo_venv)
    )
    if not executable_ok:
        raise RuntimeError("qualified Python executable is outside the repository .venv")
    if runtime.get("petsc_scalar_type") != str(np.dtype(np.complex128)):
        raise RuntimeError("PETSc.ScalarType is not complex128")
    return runtime


def _relation_digest(function_space: Any, mpc: Any) -> str:
    index_map = function_space.dofmap.index_map
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    relation_lines = []
    for slave in np.asarray(mpc.slaves, dtype=np.int32):
        row = int(slave)
        masters = np.asarray(mpc.masters.links(row), dtype=np.int32)
        global_slave = int(index_map.local_to_global(np.asarray([row]))[0])
        global_masters = index_map.local_to_global(masters).tolist()
        values = coefficients[int(offsets[row]) : int(offsets[row + 1])]
        relation_lines.append(
            {
                "slave": global_slave,
                "masters": [int(item) for item in global_masters],
                "coefficients": [[float(v.real), float(v.imag)] for v in values],
            }
        )
    local = hashlib.sha256(_canonical_json(sorted(relation_lines, key=lambda x: x["slave"]))).hexdigest()
    comm = function_space.mesh.comm
    gathered = comm.allgather({"rank": int(comm.rank), "count": len(relation_lines), "sha256": local})
    return hashlib.sha256(_canonical_json(sorted(gathered, key=lambda x: x["rank"]))).hexdigest()


def _row_layout_records(function_space: Any, mpc: Any) -> Iterable[dict[str, Any]]:
    from src.solvers.hcurl_canonical_vector import canonical_key
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        _entity_coordinates,
        _global_dofs,
        _mpc_slave_mask,
        _owned_entity_incidents,
        _physical_entity_transform,
        _space_data,
        _topology_data,
    )
    from src.geometry.tetra_mesh_audit import canonical_entity_key, mesh_coordinate_tolerance

    degree, _trace_positions, interior_positions = _space_data(function_space)
    topology, cell_info, owned_cells = _topology_data(function_space)
    tolerance = mesh_coordinate_tolerance(function_space.mesh)
    layout = function_space.dofmap.dof_layout
    relation_digest = _relation_digest(function_space, mpc)
    for dimension in (1, 2):
        cell_to_entity = topology.connectivity(topology.dim, dimension)
        for entity, cell in _owned_entity_incidents(function_space, dimension):
            local_entities = np.asarray(cell_to_entity.links(cell), dtype=np.int32)
            matches = np.flatnonzero(local_entities == int(entity))
            if matches.size != 1:
                raise RuntimeError("row witness entity incidence is not unique")
            positions = np.asarray(
                layout.entity_dofs(dimension, int(matches[0])), dtype=np.int32
            )
            local_dofs = np.asarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int32
            )[positions]
            global_dofs = _global_dofs(function_space, local_dofs)
            slave_mask = _mpc_slave_mask(mpc, local_dofs)
            if np.any(slave_mask) and not np.all(slave_mask):
                raise RuntimeError("row witness found a partly constrained entity block")
            coordinates = _entity_coordinates(function_space, dimension, entity)
            transform, state = _physical_entity_transform(
                coordinates, dimension, degree, tolerance
            )
            physical_key = canonical_key(
                role="full_fe_dual",
                entity_dimension=dimension,
                physical_entity=canonical_entity_key(coordinates, tolerance),
                entity_local_basis_index=0,
                orientation_state=state,
            )[2]
            yield {
                "block_kind": "entity",
                "entity_dimension": dimension,
                "owner_rank": int(function_space.mesh.comm.rank),
                "physical_key": _jsonable(physical_key),
                "ordered_global_row_ids": [int(item) for item in global_dofs],
                "active_global_row_ids": [
                    int(item) for item, excluded in zip(global_dofs, slave_mask) if not excluded
                ],
                "slave_global_row_ids": [
                    int(item) for item, excluded in zip(global_dofs, slave_mask) if excluded
                ],
                "slave_exclusion": True,
                "orientation_state": list(state),
                "orientation_transform_sha256": hashlib.sha256(
                    np.ascontiguousarray(transform).view(np.uint8)
                ).hexdigest(),
                "mpc_relation_digest": relation_digest,
            }
    for cell in range(int(owned_cells[0])):
        local_dofs = np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
        interior_local = local_dofs[interior_positions]
        global_dofs = _global_dofs(function_space, interior_local)
        slave_mask = _mpc_slave_mask(mpc, interior_local)
        physical_key = canonical_entity_key(
            _entity_coordinates(function_space, 3, cell), tolerance
        )
        yield {
            "block_kind": "cell",
            "entity_dimension": 3,
            "owner_rank": int(function_space.mesh.comm.rank),
            "physical_key": _jsonable(physical_key),
            "ordered_global_row_ids": [int(item) for item in global_dofs],
            "active_global_row_ids": [
                int(item) for item, excluded in zip(global_dofs, slave_mask) if not excluded
            ],
            "slave_global_row_ids": [
                int(item) for item, excluded in zip(global_dofs, slave_mask) if excluded
            ],
            "slave_exclusion": True,
            "orientation_state": ["canonical_cell", "Tt_apply"],
            "orientation_transform_sha256": hashlib.sha256(
                np.asarray([cell_info[cell]], dtype=np.uint32).tobytes()
            ).hexdigest(),
            "mpc_relation_digest": relation_digest,
        }


def _write_row_witness(raw_dir: Path, function_space: Any, mpc: Any) -> dict[str, Any]:
    comm = function_space.mesh.comm
    witness_dir = raw_dir / "row_witness"
    if comm.rank == 0:
        witness_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    path = witness_dir / f"row_layout.rank{comm.rank:04d}.jsonl"
    digest = hashlib.sha256()
    block_count = 0
    row_id_count = 0
    relation_digests: set[str] = set()
    with path.open("wb") as stream:
        for record in _row_layout_records(function_space, mpc):
            relation_digests.add(record["mpc_relation_digest"])
            row = {"schema": T5_ROW_SHARD_SCHEMA, **record}
            payload = _canonical_json(row) + b"\n"
            stream.write(payload)
            digest.update(payload)
            block_count += 1
            row_id_count += len(record["ordered_global_row_ids"])
    local = {
        "rank": int(comm.rank),
        "filename": path.name,
        "sha256": digest.hexdigest(),
        "bytes": int(path.stat().st_size),
        "block_count": block_count,
        "row_id_count": row_id_count,
        "relation_digests": sorted(relation_digests),
    }
    shards = comm.gather(local, root=0)
    descriptor = None
    if comm.rank == 0:
        shards = sorted(shards, key=lambda item: item["rank"])
        global_digest = hashlib.sha256(
            _canonical_json(
                [
                    {
                        "rank": item["rank"],
                        "sha256": item["sha256"],
                        "block_count": item["block_count"],
                        "row_id_count": item["row_id_count"],
                    }
                    for item in shards
                ]
            )
        ).hexdigest()
        manifest = {
            "schema": T5_ROW_WITNESS_SCHEMA,
            "shards": shards,
            "global_digest": global_digest,
            "global_block_count": sum(item["block_count"] for item in shards),
            "global_row_id_count": sum(item["row_id_count"] for item in shards),
            "relation_digests": sorted(
                {digest for item in shards for digest in item["relation_digests"]}
            ),
        }
        manifest_path = witness_dir / "row_layout.manifest.json"
        manifest_path.write_bytes(_canonical_json(manifest) + b"\n")
        descriptor = {
            "manifest_relative_path": "row_witness/row_layout.manifest.json",
            "manifest_sha256": _sha256_path(manifest_path),
            "manifest_bytes": int(manifest_path.stat().st_size),
            "global_digest": global_digest,
            "global_block_count": manifest["global_block_count"],
            "global_row_id_count": manifest["global_row_id_count"],
            "numeric_fe_allgather": False,
        }
    return comm.bcast(descriptor, root=0)


def _write_dual_packets(
    raw_dir: Path, vector: Any, function_space: Any, mpc: Any, name: str
) -> dict[str, Any]:
    from mpi4py import MPI

    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
    )

    comm = function_space.mesh.comm
    packets, audit = extract_canonical_full_fe_dual_packets(
        function_space, mpc, vector
    )
    directory = raw_dir / "canonical"
    if comm.rank == 0:
        directory.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = directory / f"{name}.rank{comm.rank:04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shards = comm.gather(shard, root=0)
    descriptor = None
    if comm.rank == 0:
        manifest = canonical_shard_manifest(
            role="full_fe_dual",
            mpi_size=comm.size,
            shard_metadata=shards,
            extractor_audit=_jsonable(dict(audit)),
        )
        manifest_path = directory / f"{name}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "manifest_relative_path": f"canonical/{name}.manifest.json",
            "manifest_sha256": manifest_sha,
            "manifest_bytes": int(manifest_path.stat().st_size),
            "packet_count": int(manifest["global_summed_packet_count"]),
            "role": "full_fe_dual",
        }
    return comm.bcast(descriptor, root=0)


def _read_physical_packets(manifest_path: Path) -> tuple[tuple[Any, complex], ...]:
    from benchmarks.canonical_vector_artifacts import (
        read_canonical_manifest,
        read_canonical_packet_shard,
    )

    manifest = read_canonical_manifest(manifest_path)
    if manifest.get("role") != "full_fe_dual":
        raise RuntimeError("MPI1 residual input is not a full-FE dual manifest")
    packets = []
    for shard in manifest["per_rank_shards"]:
        packets.extend(
            read_canonical_packet_shard(
                manifest_path.parent / shard["filename"], shard["file_sha256"]
            )
        )
    if len(packets) != int(manifest["global_summed_packet_count"]):
        raise RuntimeError("MPI1 residual packet count does not close")
    return tuple(packets)


def _rhs_bridge_preflight(
    old_dir: Path, raw_dir: Path, current_rhs: Mapping[str, Any]
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import compare_canonical_manifests

    old_path = old_dir / "mpi1_candidate_physical_rhs_dual_manifest.json"
    current_path = raw_dir / current_rhs["manifest_relative_path"]
    try:
        comparison = compare_canonical_manifests(
            old_path,
            current_path,
            relative_tolerance=1.0e-12,
        )
        passed = bool(
            comparison.get("pass") is True
            and comparison.get("duplicate_left_count") == 0
            and comparison.get("duplicate_right_count") == 0
            and comparison.get("missing_key_count") == 0
            and comparison.get("extra_key_count") == 0
            and float(comparison.get("relative_coefficient_l2", np.inf)) <= 1.0e-12
        )
        return {
            "pass": passed,
            "relative_tolerance": 1.0e-12,
            "old_manifest_sha256": _sha256_path(old_path),
            "current_manifest_sha256": _sha256_path(current_path),
            "comparison": comparison,
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "pass": False,
            "relative_tolerance": 1.0e-12,
            "error": str(exc),
        }


def _mesh_identity(mesh: Any) -> dict[str, Any]:
    """Hash geometry/cells by sorted physical metadata, independent of MPI."""

    topology = mesh.topology
    topology.create_connectivity(3, 0)
    cell_to_vertex = topology.connectivity(3, 0)
    coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    owned_cells = int(topology.index_map(3).size_local)
    local_cells = []
    local_vertices: set[tuple[float, float, float]] = set()
    for cell in range(owned_cells):
        points = tuple(
            tuple(float(value) for value in coordinates[int(vertex)])
            for vertex in cell_to_vertex.links(cell)
        )
        local_cells.append(tuple(sorted(points)))
        local_vertices.update(points)
    parts = mesh.comm.gather(
        {"cells": local_cells, "vertices": sorted(local_vertices)}, root=0
    )
    if mesh.comm.rank == 0:
        cells = sorted(
            cell for part in parts for cell in part["cells"]
        )
        vertices = sorted(
            set(tuple(point) for part in parts for point in part["vertices"])
        )
        identity = {
            "cell_type": str(topology.cell_type),
            "cells_global": int(topology.index_map(3).size_global),
            "vertices_global": int(topology.index_map(0).size_global),
            "geometry_shape": [len(vertices), 3],
            "canonical_connectivity_sha256": hashlib.sha256(
                _canonical_json(cells)
            ).hexdigest(),
            "canonical_geometry_sha256": hashlib.sha256(
                _canonical_json(vertices)
            ).hexdigest(),
            "axis_counts": [
                len({point[axis] for point in vertices}) for axis in range(3)
            ],
            "digest_algorithm": "sorted-cell-coordinate-metadata-v1",
        }
    else:
        identity = None
    return mesh.comm.bcast(identity, root=0)


def _old_mesh_witness(old_dir: Path) -> dict[str, Any]:
    from dolfinx.io import XDMFFile
    from mpi4py import MPI

    xdmf_path = old_dir / "m6b_w5_mesh" / "mesh_3d.xdmf"
    h5_path = xdmf_path.with_suffix(".h5")
    with XDMFFile(MPI.COMM_SELF, str(xdmf_path), "r") as handle:
        mesh = handle.read_mesh(name="target_stage4_block_grating_p6_h10")
        identity = _mesh_identity(mesh)
    identity.update(
        {
            "source": "old_exact_xdmf",
            "xdmf_sha256": _sha256_path(xdmf_path),
            "h5_sha256": _sha256_path(h5_path),
        }
    )
    return identity


def _mesh_witnesses(
    cfg: Any, mesh_data: Any, raw_dir: Path, old_dir: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = _mesh_identity(mesh_data.mesh)
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d

    repeat_data = build_airbox_mesh_3d(cfg, raw_dir / "mesh_repeat")
    try:
        rebuilt = _mesh_identity(repeat_data.mesh)
    finally:
        del repeat_data
    old = _old_mesh_witness(old_dir)
    identity_fields = (
        "cell_type",
        "cells_global",
        "vertices_global",
        "geometry_shape",
        "canonical_connectivity_sha256",
        "canonical_geometry_sha256",
        "axis_counts",
        "digest_algorithm",
    )
    if not (
        all(old[field] == current[field] for field in identity_fields)
        and all(current[field] == rebuilt[field] for field in identity_fields)
    ):
        raise RuntimeError("old/current/rebuild mesh witness identity differs")
    return {
        "old_exact": old,
        "current_generated": {"source": "current_generated", **current},
        "current_rebuild": {"source": "current_rebuild", **rebuilt},
        "identity_fields": list(identity_fields),
    }, current


def _build_authority_case(
    *,
    root: Path,
    raw_dir: Path,
    input_path: Path,
    old_dir: Path,
    mpi1_record: Path | None,
    mpi1_residual_manifest: Path | None,
    comm: Any,
) -> dict[str, Any]:
    from mpi4py import MPI

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.io import load_and_resolve
    from src.io.resolved_config import resolved_config_bytes
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_vector,
        _dtn_surface_quadrature_degree,
        _incident_projection_onto_top_mode,
        _incident_top_traction_form,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction
    from src.solvers.mpc_form_action import MpcFormActionContext
    from benchmarks.run_task038_full3d_t3 import (
        _independent_modal_sum,
        _make_surface_assemblers,
    )

    specification = load_and_resolve(input_path)
    payload = resolved_config_bytes(specification)
    cfg = simulation_config_3d_from_normalized(json.loads(payload))
    if cfg.stage4_boundary_model != "dtn_port":
        raise RuntimeError("T5 authority requires the current dynamic DtN boundary")
    config_path = raw_dir / "benchmark_input" / "resolved_config.json"
    if comm.rank == 0:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(payload)
    comm.barrier()

    mesh_data = build_airbox_mesh_3d(cfg, raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    modes, _mode_manifest, mode_sha = build_dynamic_mode_inventory(cfg)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    surface_assemblers = _make_surface_assemblers(
        raw_space, mesh_data, cfg, modes, quadrature_degree
    )
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, surface_assemblers, floquet_data.mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    bilinear_form, _rhs = _build_variational_forms(
        mesh_data.mesh,
        mesh_data,
        cfg,
        raw_space,
        field_formulation="total_field",
    )
    volume_action = build_fullspace_mpc_form_action(
        bilinear_form, raw_space, mpc=floquet_data.mpc
    )
    physical_action = FullspacePhysicalAction(volume_action, dtn_action)
    base_incident = _assemble_mpc_vector(
        _incident_top_traction_form(raw_space, mesh_data, cfg),
        floquet_data.mpc,
        quadrature_degree=quadrature_degree,
    )
    incident_projections = tuple(
        _incident_projection_onto_top_mode(mode, cfg) for mode in modes
    )
    source = base_incident.duplicate()
    physical_action.compose_physical_rhs(base_incident, incident_projections, source)
    witness = _write_row_witness(raw_dir, space, floquet_data.mpc)
    current_rhs = _write_dual_packets(raw_dir, source, space, floquet_data.mpc, "current_rhs")
    old_facts, old_residual = _old_facts_for_case(old_dir, mpi1_record, comm)
    if comm.size == 1:
        rhs_preflight = _rhs_bridge_preflight(old_dir, raw_dir, current_rhs)
    else:
        mpi1_payload = json.loads(mpi1_record.read_text(encoding="utf-8"))
        saved_preflight = mpi1_payload.get("bridge", {}).get(
            "rhs_canonical_preflight"
        )
        rhs_preflight = (
            dict(saved_preflight)
            if isinstance(saved_preflight, Mapping)
            else {"pass": False, "error": "MPI1 RHS bridge preflight is missing"}
        )
    mesh_witness, current_mesh = _mesh_witnesses(
        cfg, mesh_data, raw_dir, old_dir
    )
    residual_artifacts: dict[str, Any] = {
        "status": "not_run",
        "reason": "residual conversion was not reached",
        "source": None,
        "action": None,
        "repeat": None,
        "reference": None,
    }
    residual_telemetry: dict[str, Any] = {"status": "not_run"}
    residual_bridge: dict[str, Any] = {
        "rhs_canonical_preflight": rhs_preflight,
    }
    residual = None
    reference_context = None
    residual_reference_volume = None
    residual_action = None
    residual_repeat = None
    residual_reference = None
    try:
        if rhs_preflight.get("pass") is not True:
            residual_bridge.update(
                {
                    "conversion_status": "not_run",
                    "qualified_for_mpi2": False,
                    "reason": "RHS canonical bridge failed before residual conversion",
                }
            )
        elif comm.size == 1:
            if old_residual is None:
                residual_bridge.update(
                    {
                        "conversion_status": "not_run",
                        "qualified_for_mpi2": False,
                        "reason": "MPI1 old residual values are unavailable",
                    }
                )
            else:
                residual = source.duplicate()
                residual.getArray()[:] = old_residual
                residual_bridge["conversion_input"] = "old residual row array (MPI1 only)"
        elif mpi1_residual_manifest is None:
            residual_bridge.update(
                {
                    "conversion_status": "not_run",
                    "qualified_for_mpi2": False,
                    "reason": "MPI2 residual manifest input is missing",
                }
            )
        else:
            from src.solvers.hcurl_canonical_vector_dolfinx import (
                reconstruct_canonical_full_fe_dual_vector,
            )

            residual_packets = _read_physical_packets(mpi1_residual_manifest)
            residual = reconstruct_canonical_full_fe_dual_vector(
                space, floquet_data.mpc, residual_packets
            )
            residual_bridge.update(
                {
                    "mpi1_manifest_path": str(mpi1_residual_manifest.resolve()),
                    "mpi1_manifest_sha256": _sha256_path(mpi1_residual_manifest),
                    "conversion_input": "physical MPI1 residual packets only",
                }
            )
        if residual is not None:
            residual_source_desc = _write_dual_packets(
                raw_dir,
                residual,
                space,
                floquet_data.mpc,
                "residual_source" if comm.size == 1 else "residual_source_reextract",
            )
            residual_bridge.update(
                {
                    "conversion_status": "source_ready",
                    "qualified_for_mpi2": True,
                    "mpi1_manifest_relative_path": (
                        residual_source_desc["manifest_relative_path"]
                        if comm.size == 1
                        else residual_bridge["mpi1_manifest_path"]
                    ),
                    "mpi1_manifest_sha256": (
                        residual_source_desc["manifest_sha256"]
                        if comm.size == 1
                        else residual_bridge["mpi1_manifest_sha256"]
                    ),
                    "mpi2_reextract_manifest_relative_path": (
                        None
                        if comm.size == 1
                        else residual_source_desc["manifest_relative_path"]
                    ),
                }
            )
            residual_action = residual.duplicate()
            residual_repeat = residual.duplicate()
            reference_context = MpcFormActionContext(bilinear_form, floquet_data.mpc)
            residual_reference_volume = residual.duplicate()
            residual_reference_volume.set(0.0)
            reference_context.mult(None, residual, residual_reference_volume)
            reference_assemblers = _make_surface_assemblers(
                raw_space, mesh_data, cfg, modes, quadrature_degree
            )
            residual_direct_dtn, _residual_amplitudes = _independent_modal_sum(
                modes, cfg, reference_assemblers, floquet_data.mpc, residual
            )
            residual_reference = residual_direct_dtn
            residual_reference.axpy(1.0, residual_reference_volume)
            telemetry = []
            for target in (residual_action, residual_repeat):
                started = time.perf_counter()
                physical_action.apply(residual, target)
                telemetry.append(
                    {
                        "elapsed_seconds": float(
                            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
                        ),
                        "rank_max_current_rss_bytes": int(
                            comm.allreduce(_rss_bytes(), op=MPI.MAX)
                        ),
                        "rank_max_current_swap_bytes": int(
                            comm.allreduce(_swap_used_bytes(), op=MPI.MAX)
                        ),
                    }
                )
            residual_artifacts = {
                "status": "pass",
                "source": residual_source_desc,
                "action": _write_dual_packets(
                    raw_dir, residual_action, space, floquet_data.mpc, "residual_action"
                ),
                "repeat": _write_dual_packets(
                    raw_dir, residual_repeat, space, floquet_data.mpc, "residual_repeat"
                ),
                "reference": _write_dual_packets(
                    raw_dir,
                    residual_reference,
                    space,
                    floquet_data.mpc,
                    "residual_reference",
                ),
            }
            residual_bridge["conversion_status"] = "pass"
            residual_telemetry = {
                "status": "pass",
                "telemetry": telemetry,
            }
        return {
            "schema": T5_SCHEMA,
            "resolved_config": {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "template_relative_path": str(input_path.relative_to(root)),
                "template_bytes": len(specification.raw_input_bytes),
                "template_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
            },
            "old_w5": old_facts,
            "extractor_provenance": {
                "old_source_sha": OLD_SOURCE_SHA,
                "old_source_blob_sha256": _git_blob_sha(
                    root, OLD_SOURCE_SHA, "src/solvers/hcurl_canonical_vector_dolfinx.py"
                ),
                "old_api": "iter_canonical_full_fe_dual_packets",
                "current_api": "extract_canonical_full_fe_dual_packets",
                "entity_transform": "transform.conj().T",
                "cell_transform": "Tt_apply",
                "slave_exclusion": True,
                "runtime": _runtime_identity(),
            },
            "mesh": current_mesh,
            "mesh_witnesses": mesh_witness,
            "mpc": {
                "global_rows": int(space.dofmap.index_map.size_global),
                "local_owned_rows": int(space.dofmap.index_map.size_local),
                "element_space_dimension": int(space.element.space_dimension),
                "constraint_count": int(floquet_data.num_constraints),
                "constraint_mode": floquet_data.constraint_mode_resolved,
                "relation_digest": _relation_digest(space, floquet_data.mpc),
            },
            "row_layout_witness": witness,
            "bridge": {
                "old_manifest_path": str(
                    Path(old_facts["directory"])
                    / "mpi1_candidate_physical_rhs_dual_manifest.json"
                ),
                "old_role": old_facts["manifest"]["role"],
                "current_rhs_manifest_relative_path": current_rhs["manifest_relative_path"],
                "current_rhs_packet_count": current_rhs["packet_count"],
                "old_packet_count": old_facts["manifest"]["packet_count"],
                "rhs_canonical_preflight": rhs_preflight,
                "mpi1_residual_conversion_input": "old residual row array",
                "mpi2_residual_conversion_input": "physical MPI1 residual packets only",
            },
            "artifacts": {
                "current_rhs": current_rhs,
                "residual": residual_artifacts,
            },
            "residual_bridge": residual_bridge,
            "residual_telemetry": residual_telemetry,
            "operator": {
                "volume_plus_dynamic_dtn": True,
                "t4_transmission_included": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "pde_run": False,
                "mode_count": len(modes),
                "mode_manifest_sha256": mode_sha,
                "physical_action_audit": _jsonable(dict(physical_action.audit)),
            },
            "case": "p6-h10",
            "profile": T5_PROFILE,
            "mpi": {"size": int(comm.size)},
        }
    finally:
        if residual_reference_volume is not None:
            residual_reference_volume.destroy()
        if residual_reference is not None:
            residual_reference.destroy()
        if residual_repeat is not None:
            residual_repeat.destroy()
        if residual_action is not None:
            residual_action.destroy()
        if residual is not None:
            residual.destroy()
        if reference_context is not None:
            reference_context.destroy()
        base_incident.destroy()
        source.destroy()
        physical_action.destroy()


def _write_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(record) + b"\n")


def _watchdog_main(argv: list[str]) -> int:
    """Run the worker under the repository's external process-tree authority."""

    from benchmarks.task034_wsl_resources import resource_authority_sample
    from benchmarks.watchdog_process_control import (
        terminate_process_tree,
        worker_process_group_popen_kwargs,
    )

    parser = argparse.ArgumentParser(description="External T5 process-tree watchdog")
    parser.add_argument("--watchdog", action="store_true")
    parser.add_argument("--watchdog-record", type=Path, required=True)
    parser.add_argument("--watchdog-raw", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--watchdog-log", type=Path, required=True)
    parser.add_argument("--watchdog-poll-seconds", type=float, default=1.0)
    parser.add_argument("--watchdog-timeout-seconds", type=float, default=7200.0)
    parser.add_argument("--watchdog-command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args([item for item in argv if item != "--watchdog"])
    command = [item for item in args.watchdog_command if item != "--"]
    if not command or args.watchdog_poll_seconds < 0.05 or args.watchdog_timeout_seconds <= 0:
        raise SystemExit("watchdog command, poll, and timeout are invalid")
    raw_path = args.watchdog_raw.resolve()
    compact_path = args.watchdog_compact.resolve()
    log_path = args.watchdog_log.resolve()
    # The worker deliberately rejects a pre-existing raw directory.  Keep
    # only the external log outside it until the worker has created raw_dir.
    log_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    stop_reason = None
    cleanup = None
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[1],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        while process.poll() is None:
            elapsed = time.perf_counter() - started
            sample = resource_authority_sample(process.pid)
            rows.append({"elapsed_seconds": elapsed, **sample})
            process_tree = sample["process_tree"]
            authority = int(sample["memory_authority_bytes"])
            if not process_tree["all_status_readable"]:
                stop_reason = "resource_authority_unreadable"
            elif not sample["job_no_swap"]:
                stop_reason = "swap_nonzero"
            elif authority >= 12 * 1024**3:
                stop_reason = "hard_stop_12_gib"
            elif elapsed >= args.watchdog_timeout_seconds:
                stop_reason = "watchdog_timeout"
            if stop_reason is not None:
                cleanup = terminate_process_tree(process)
                break
            time.sleep(args.watchdog_poll_seconds)
        if cleanup is None:
            cleanup = terminate_process_tree(process)
        returncode = process.returncode

    process_tree_rss = [int(row["process_tree"]["rss_bytes"]) for row in rows]
    process_tree_swap = [int(row["process_tree"]["swap_bytes"]) for row in rows]
    cgroup_swap = [
        int(row["job_cgroup"]["swap_current_bytes"])
        for row in rows
        if row["job_cgroup"].get("dedicated_job_cgroup") is True
        if row["job_cgroup"].get("swap_current_bytes") is not None
    ]
    all_readable = bool(rows) and all(
        bool(row["process_tree"]["all_status_readable"]) for row in rows
    )
    peak_rss = max(process_tree_rss, default=0)
    peak_swap = max(process_tree_swap, default=0)
    peak_cgroup_swap = max(cgroup_swap, default=0)
    pass_status = bool(
        returncode == 0
        and stop_reason is None
        and all_readable
        and peak_rss < 6 * 1024**3
        and max((int(row["memory_authority_bytes"]) for row in rows), default=0)
        < 12 * 1024**3
        and peak_swap == 0
        and peak_cgroup_swap == 0
        and cleanup["process_group_exited"]
    )
    raw_payload = {
        "schema": "task038.t5.external-process-tree-raw.v1",
        "command": command,
        "samples": rows,
        "returncode": returncode,
        "stop_reason": stop_reason,
        "termination": cleanup,
    }
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(_canonical_json(raw_payload) + b"\n")
    raw_sha = _sha256_path(raw_path)
    compact = {
        "schema": "task038.t5.external-process-tree-compact.v1",
        "status": "measured_pass" if pass_status else "measured_fail",
        "process_tree_peak_rss_bytes": peak_rss,
        "process_tree_peak_swap_bytes": peak_swap,
        "dedicated_cgroup_peak_swap_bytes": peak_cgroup_swap,
        "memory_authority_peak_bytes": max(
            (int(row["memory_authority_bytes"]) for row in rows), default=0
        ),
        "process_tree_memory_ceiling_bytes": 6 * 1024**3,
        "hard_stop_memory_bytes": 12 * 1024**3,
        "swap_required_bytes": 0,
        "sample_count": len(rows),
        "all_status_readable": all_readable,
        "stop_reason": stop_reason,
        "returncode": returncode,
        "termination": cleanup,
        "raw_report_sha256": raw_sha,
    }
    compact_path.write_bytes(_canonical_json(compact) + b"\n")
    compact_sha = _sha256_path(compact_path)
    record_path = args.watchdog_record.resolve()
    record_update_error = None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        raw_root = Path(str(record["raw_dir"])).resolve()
        raw_relative = raw_path.relative_to(raw_root).as_posix()
        compact_relative = compact_path.relative_to(raw_root).as_posix()
        record["resource_contract"] = {
            **compact,
            "watchdog": "external_process_tree",
            "status": "measured_pass" if pass_status else "measured_fail",
            "raw_report_relative_path": raw_relative,
            "compact_report_relative_path": compact_relative,
            "compact_report_sha256": compact_sha,
        }
        _write_record(record_path, record)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        record_update_error = str(exc)
    return 0 if pass_status and record_update_error is None else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task038 T5 authority runner")
    parser.add_argument("--input", type=Path, default=Path("input/templates/full3d_iterative_example.dat"))
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--old-w5-dir", type=Path)
    parser.add_argument("--mpi1-record", type=Path)
    parser.add_argument("--mpi1-residual-manifest", type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument(
        "--watchdog-mode",
        choices=("external_process_tree",),
        default="external_process_tree",
    )
    parser.add_argument(
        "--process-tree-memory-ceiling-bytes",
        type=int,
        default=6 * 1024**3,
    )
    parser.add_argument(
        "--hard-stop-memory-bytes",
        type=int,
        default=12 * 1024**3,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    selected_argv = list(sys.argv[1:] if argv is None else argv)
    if "--watchdog" in selected_argv:
        return _watchdog_main(selected_argv)
    if "--identity" in selected_argv:
        return _identity_main(selected_argv)
    args = _parser().parse_args(selected_argv)
    root = Path(__file__).resolve().parents[1]
    identity = _source_identity(root)
    if identity["commit_sha"] != args.expected_source_sha or identity["tracked_status"]:
        raise RuntimeError("T5 source preflight is not clean at start")
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    if comm.size != args.expected_mpi_size or comm.size not in {1, 2}:
        raise RuntimeError("T5 authority requires declared MPI size 1 or 2")
    _runtime_preflight(root)
    old_dir = (
        args.old_w5_dir
        if args.old_w5_dir is not None
        else root
        / "benchmarks/artifacts/task037_extra_development/m6b_w5_disk_fgmres_41cbbd4_screen_run1"
    )
    mpi1_record = (
        None
        if args.mpi1_record is None
        else (args.mpi1_record if args.mpi1_record.is_absolute() else root / args.mpi1_record)
    )
    mpi1_residual_manifest = (
        None
        if args.mpi1_residual_manifest is None
        else (
            args.mpi1_residual_manifest
            if args.mpi1_residual_manifest.is_absolute()
            else root / args.mpi1_residual_manifest
        )
    )
    _prepare_raw_dir(args.raw_dir, args.record, comm)
    record = _build_authority_case(
        root=root,
        raw_dir=args.raw_dir,
        input_path=(args.input if args.input.is_absolute() else root / args.input),
        old_dir=(old_dir if old_dir.is_absolute() else root / old_dir),
        mpi1_record=mpi1_record,
        mpi1_residual_manifest=mpi1_residual_manifest,
        comm=comm,
    )
    record["raw_dir"] = str(args.raw_dir.resolve())
    record["source"] = {
        "expected_sha": args.expected_source_sha,
        "commit_sha_start": identity["commit_sha"],
        "commit_sha_end": _source_identity(root)["commit_sha"],
        "tracked_status_start": identity["tracked_status"],
        "tracked_status_end": _source_identity(root)["tracked_status"],
    }
    record["resource_contract"] = {
        "watchdog": args.watchdog_mode,
        "process_tree_memory_ceiling_bytes": args.process_tree_memory_ceiling_bytes,
        "hard_stop_memory_bytes": args.hard_stop_memory_bytes,
        "swap_required_bytes": 0,
        "status": "not_run",
    }
    if comm.rank == 0:
        _write_record(args.record, record)
    comm.barrier()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
