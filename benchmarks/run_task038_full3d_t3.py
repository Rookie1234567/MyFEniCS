"""Small action-only runner for dynamic Full3D Fourier-DtN qualification.

The resolved JSON is the only physical input.  This runner assembles the
current MPC-aware surface functionals, applies the bounded modal action, and
writes raw vectors plus a compact facts record.  It never creates a KSP or
solves a PDE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

T3_SCHEMA = "task038.full3d.iterative.t3.action-record.v1"
T3_PROFILE = "full3d_scalable_v1"
T3_REPEATS = 12
T3_FORMAL_CASE = "p6-h10"
T3_TEMPLATE_RELATIVE_PATH = "input/templates/full3d_iterative_example.dat"
T3_EXPECTED_MODE_COUNT = 80
T3_EXPECTED_INPUT_BYTES = 2119
T3_EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
T3_EXPECTED_RESOLVED_CONFIG_BYTES = 4076
T3_EXPECTED_RESOLVED_CONFIG_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
T3_EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(root: Path) -> dict[str, str]:
    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *arguments],
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


def _rss_bytes() -> int:
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError) as exc:
        raise RuntimeError("current VmRSS is unavailable") from exc
    raise RuntimeError("current VmRSS is unavailable")


def _swap_used_bytes() -> int:
    values: dict[str, int] = {}
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.partition(":")
                if key in {"SwapTotal", "SwapFree"}:
                    values[key] = int(value.split()[0]) * 1024
    except (OSError, ValueError):
        return -1
    if set(values) != {"SwapTotal", "SwapFree"}:
        return -1
    return max(values["SwapTotal"] - values["SwapFree"], 0)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _load_adapter_resolved_config(
    root: Path, resolved_config: Path
) -> tuple[Any, Path, bytes]:
    """Load the frozen .dat through T1 and require byte-exact resolved JSON."""

    from src.io import load_and_resolve
    from src.io.resolved_config import resolved_config_bytes

    template_path = root / T3_TEMPLATE_RELATIVE_PATH
    specification = load_and_resolve(template_path)
    adapter_bytes = resolved_config_bytes(specification)
    try:
        supplied_bytes = resolved_config.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"T3 resolved config is unreadable: {resolved_config}") from exc
    if supplied_bytes != adapter_bytes:
        raise RuntimeError(
            "T3 resolved config is not the byte-exact T1 adapter output for "
            f"{T3_TEMPLATE_RELATIVE_PATH}"
        )
    if len(specification.raw_input_bytes) != T3_EXPECTED_INPUT_BYTES:
        raise RuntimeError("T3 frozen input byte count changed")
    if specification.input_sha256 != T3_EXPECTED_INPUT_SHA256:
        raise RuntimeError("T3 frozen input SHA changed")
    if len(adapter_bytes) != T3_EXPECTED_RESOLVED_CONFIG_BYTES:
        raise RuntimeError("T3 frozen resolved-config byte count changed")
    if hashlib.sha256(adapter_bytes).hexdigest() != T3_EXPECTED_RESOLVED_CONFIG_SHA256:
        raise RuntimeError("T3 frozen resolved-config SHA changed")
    if specification.physical_model_sha256 != T3_EXPECTED_PHYSICAL_MODEL_SHA256:
        raise RuntimeError("T3 frozen physical-model SHA changed")
    return specification, template_path, adapter_bytes


def _frozen_benchmark_identity(
    specification: Any, cfg: Any, *, case: str, mode_count: int
) -> dict[str, Any]:
    """Return the exact benchmark contract after adapter and mode discovery."""

    identity = specification.identity
    method = specification.method
    boundary = specification.boundary
    solver = specification.solver
    exact = {
        "case": T3_FORMAL_CASE,
        "model_id": "euv_grazing1_phi0",
        "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
        "comparison_group": "euv_grazing1_phi0",
        "method": "full3d_iterative",
        "profile": T3_PROFILE,
        "preconditioner": "full3d_scalable_v1",
        "wavelength_nm": 13.5,
        "nedelec_degree": 6,
        "mesh_target_nm": 10.0,
        "boundary_model": "dtn_port",
        "vertical_boundary": "dtn_port",
        "dtn_order_policy": "auto_propagating",
        "dtn_assembly": "auxiliary",
        "expected_mode_count": T3_EXPECTED_MODE_COUNT,
        "discovered_mode_count": T3_EXPECTED_MODE_COUNT,
        "input_adapter": "src.io.load_and_resolve",
        "resolved_config_encoder": "src.io.resolved_config.resolved_config_bytes",
    }
    actual = {
        "case": case,
        "model_id": identity.get("model_id"),
        "run_id": identity.get("run_id"),
        "comparison_group": identity.get("comparison_group"),
        "method": method.get("kind"),
        "profile": solver.get("preconditioner"),
        "preconditioner": solver.get("preconditioner"),
        "wavelength_nm": float(cfg.lambda0),
        "nedelec_degree": int(cfg.nedelec_degree),
        "mesh_target_nm": float(cfg.mesh_target_size),
        "boundary_model": cfg.stage4_boundary_model,
        "vertical_boundary": boundary.get("vertical_boundary"),
        "dtn_order_policy": cfg.stage4_dtn_order_policy,
        "dtn_assembly": cfg.stage4_dtn_assembly,
        "expected_mode_count": T3_EXPECTED_MODE_COUNT,
        "discovered_mode_count": int(mode_count),
        "input_adapter": "src.io.load_and_resolve",
        "resolved_config_encoder": "src.io.resolved_config.resolved_config_bytes",
    }
    if case != T3_FORMAL_CASE or actual != exact:
        raise RuntimeError("T3 frozen p6/h10 benchmark identity does not match adapter output")
    return exact


def _write_petsc_vector(vector: Any, path: Path, comm: Any) -> dict[str, Any]:
    from mpi4py import MPI

    start, stop = map(int, vector.getOwnershipRange())
    local = np.ascontiguousarray(
        np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    )
    if local.size != stop - start:
        raise RuntimeError("PETSc vector ownership does not close")
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    handle = MPI.File.Open(comm, str(path), MPI.MODE_WRONLY | MPI.MODE_CREATE)
    handle.Set_size(int(vector.getSize()) * np.dtype(np.complex128).itemsize)
    handle.Write_at_all(start * np.dtype(np.complex128).itemsize, local)
    handle.Close()
    comm.barrier()
    payload = None
    if comm.rank == 0:
        payload = {
            "relative_path": path.name,
            "bytes": int(path.stat().st_size),
            "sha256": _sha256_path(path),
            "dtype": "complex128",
            "shape": [int(vector.getSize())],
        }
    return comm.bcast(payload, root=0)


def _write_canonical_vector(
    vector: Any,
    raw_dir: Path,
    relative_path: str,
    *,
    function_space: Any,
    floquet_data: Any,
    canonical_role: str,
    comm: Any,
) -> dict[str, Any]:
    """Write a raw vector plus a physical full-FE canonical packet manifest."""

    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_packets,
    )

    descriptor = _write_petsc_vector(vector, raw_dir / relative_path, comm)
    packets, extractor_audit = extract_canonical_full_fe_packets(
        function_space, vector, floquet_data
    )
    canonical_dir = raw_dir / "canonical"
    if comm.rank == 0:
        canonical_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = canonical_dir / f"{canonical_role}.rank{comm.rank:04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shards = comm.gather(shard, root=0)
    manifest_relative = f"canonical/{canonical_role}.manifest.json"
    if comm.rank == 0:
        manifest = canonical_shard_manifest(
            role=canonical_role,
            mpi_size=comm.size,
            shard_metadata=shards,
            extractor_audit=_jsonable(dict(extractor_audit)),
        )
        manifest_path = raw_dir / manifest_relative
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor.update(
            {
                "canonical_order": "physical_hcurl_packet_key",
                "canonical_manifest_relative_path": manifest_relative,
                "canonical_manifest_bytes": int(manifest_path.stat().st_size),
                "canonical_manifest_sha256": manifest_sha,
                "canonical_packet_count": int(
                    manifest["global_summed_packet_count"]
                ),
            }
        )
    else:
        descriptor = None
    return comm.bcast(descriptor, root=0)


def _write_mode_manifest(raw_dir: Path, manifest_bytes: bytes, comm: Any) -> dict[str, Any]:
    path = raw_dir / "mode_manifest.json"
    if comm.rank == 0:
        path.write_bytes(manifest_bytes)
        descriptor = {
            "kind": "ordered_mode_manifest",
            "relative_path": path.name,
            "bytes": int(path.stat().st_size),
            "sha256": _sha256_path(path),
            "dtype": "json",
        }
    else:
        descriptor = None
    return comm.bcast(descriptor, root=0)


def _write_benchmark_input_artifacts(
    raw_dir: Path, template_bytes: bytes, resolved_bytes: bytes, comm: Any
) -> dict[str, dict[str, Any]]:
    paths = {
        "input_template": (raw_dir / "benchmark_input" / "full3d_iterative_example.dat", template_bytes, "input_template"),
        "resolved_config": (raw_dir / "benchmark_input" / "resolved_config.json", resolved_bytes, "resolved_config"),
    }
    if comm.rank == 0:
        for path, payload, _kind in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    comm.barrier()
    descriptors = None
    if comm.rank == 0:
        descriptors = {
            name: {
                "kind": kind,
                "relative_path": str(path.relative_to(raw_dir)),
                "bytes": int(path.stat().st_size),
                "sha256": _sha256_path(path),
            }
            for name, (path, _payload, kind) in paths.items()
        }
    return comm.bcast(descriptors, root=0)


def _independent_modal_sum(
    modes: Any,
    cfg: Any,
    surface_assemblers: Any,
    mpc: Any,
    source: Any,
) -> tuple[Any, np.ndarray]:
    """Assemble a fresh modal sum without reading the candidate carrier."""

    from mpi4py import MPI

    from src.solvers.dtn_port_3d import (
        _combine_owned_entries,
        _mode_projection_denominator,
        _traction_vector,
    )

    comm = source.getComm().tompi4py()
    start, _stop = map(int, source.getOwnershipRange())
    source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    reference = source.duplicate()
    reference.set(0.0)
    reference_values = reference.getArray()
    amplitudes = np.empty(len(modes), dtype=np.complex128)
    for index, mode in enumerate(modes):
        components = (
            surface_assemblers[(mode.side, 0)].assemble_entries(mode, mpc),
            surface_assemblers[(mode.side, 1)].assemble_entries(mode, mpc),
        )
        projection_rows, projection_values = _combine_owned_entries(
            components,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        traction = _traction_vector(mode, cfg)
        coupling_rows, coupling_values = _combine_owned_entries(
            components,
            (-traction[0], -traction[1]),
            comm=comm,
        )
        local_projection = (
            np.vdot(
                projection_values,
                source_values[projection_rows - start],
            )
            if projection_rows.size
            else 0.0 + 0.0j
        )
        amplitude = complex(comm.allreduce(local_projection, op=MPI.SUM))
        amplitude /= _mode_projection_denominator(mode, cfg)
        amplitudes[index] = amplitude
        if coupling_rows.size:
            reference_values[coupling_rows - start] += amplitude * coupling_values
    return reference, amplitudes


def _make_surface_assemblers(
    V: Any, mesh_data: Any, cfg: Any, modes: Any, quadrature_degree: int
) -> dict[tuple[str, int], Any]:
    from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler

    return {
        (side, component): _ReusableSurfaceComponentAssembler(
            V,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=quadrature_degree,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }


def _relative_error(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    try:
        return float(difference.norm() / max(right.norm(), 1.0e-30))
    finally:
        difference.destroy()


def _run_case(
    *,
    resolved_config: Path,
    raw_dir: Path,
    record_path: Path,
    case: str,
    expected_source_sha: str,
) -> dict[str, Any]:
    from mpi4py import MPI

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_vector,
        _dtn_surface_quadrature_degree,
        _incident_top_traction_form,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )

    comm = MPI.COMM_WORLD
    root = Path(__file__).resolve().parents[1]
    identity = _source_identity(root)
    if identity["commit_sha"] != expected_source_sha or identity["tracked_status"]:
        raise RuntimeError("T3 source preflight is not clean at start")
    specification, template_path, payload_bytes = _load_adapter_resolved_config(
        root, resolved_config
    )
    payload = json.loads(payload_bytes)
    cfg = simulation_config_3d_from_normalized(payload)
    if cfg.stage4_boundary_model != "dtn_port":
        raise RuntimeError("T3 action runner requires the resolved DtN boundary")
    if raw_dir.exists() or record_path.exists():
        raise FileExistsError("T3 raw directory or record already exists")
    if comm.rank == 0:
        raw_dir.mkdir(parents=True)
    comm.barrier()

    modes, manifest, _manifest_sha = build_dynamic_mode_inventory(cfg)
    benchmark = _frozen_benchmark_identity(
        specification, cfg, case=case, mode_count=len(modes)
    )
    input_artifacts = _write_benchmark_input_artifacts(
        raw_dir,
        specification.raw_input_bytes,
        payload_bytes,
        comm,
    )
    mesh_data = build_airbox_mesh_3d(cfg, raw_dir / "mesh")
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, mesh_data, cfg)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    surface_assemblers = _make_surface_assemblers(
        V, mesh_data, cfg, modes, quadrature_degree
    )
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes,
        surface_assemblers,
        floquet_data.mpc,
        cfg,
    )
    reference_assemblers = _make_surface_assemblers(
        V, mesh_data, cfg, modes, quadrature_degree
    )
    action = build_fullspace_dtn_action(carrier, comm=comm)
    source = _assemble_mpc_vector(
        _incident_top_traction_form(V, mesh_data, cfg),
        floquet_data.mpc,
        quadrature_degree=quadrature_degree,
    )
    candidate = source.duplicate()
    direct, direct_amplitudes = _independent_modal_sum(
        modes,
        cfg,
        reference_assemblers,
        floquet_data.mpc,
        source,
    )
    baseline = None
    try:
        elapsed_seconds = []
        rss_bytes = []
        swap_used_bytes = []
        repeat_differences = []
        for apply_index in range(T3_REPEATS):
            started = time.perf_counter()
            action.matrix.mult(source, candidate)
            elapsed_seconds.append(float(time.perf_counter() - started))
            rss_bytes.append(int(comm.allreduce(_rss_bytes(), op=MPI.MAX)))
            swap_used_bytes.append(
                int(comm.allreduce(_swap_used_bytes(), op=MPI.MAX))
            )
            if apply_index == 0:
                baseline = candidate.copy()
            else:
                repeat_differences.append(_relative_error(candidate, baseline))
        action_error = _relative_error(candidate, direct)
        recovered = action.recover_auxiliary(source)
        recovery_error = float(
            np.linalg.norm(recovered - direct_amplitudes)
            / max(np.linalg.norm(direct_amplitudes), 1.0e-30)
        )
        artifacts = {
            "source": _write_canonical_vector(
                source,
                raw_dir,
                "source.bin",
                function_space=V,
                floquet_data=floquet_data,
                canonical_role="source",
                comm=comm,
            ),
            "action": _write_canonical_vector(
                candidate,
                raw_dir,
                "action.bin",
                function_space=V,
                floquet_data=floquet_data,
                canonical_role="action",
                comm=comm,
            ),
            "reference_action": _write_canonical_vector(
                direct,
                raw_dir,
                "reference_action.bin",
                function_space=V,
                floquet_data=floquet_data,
                canonical_role="reference_action",
                comm=comm,
            ),
        }
        artifacts["mode_manifest"] = _write_mode_manifest(
            raw_dir, carrier.mode_manifest_bytes, comm
        )
        artifacts.update(input_artifacts)
        if comm.rank == 0:
            np.asarray(recovered, dtype=np.complex128).tofile(raw_dir / "recovery.bin")
            artifacts["recovery"] = {
                "relative_path": "recovery.bin",
                "bytes": int((raw_dir / "recovery.bin").stat().st_size),
                "sha256": _sha256_path(raw_dir / "recovery.bin"),
                "dtype": "complex128",
                "shape": [len(recovered)],
            }
        artifacts["recovery"] = comm.bcast(artifacts.get("recovery"), root=0)
        observations = {
            "action_relative_error": action_error,
            "recovery_relative_error": recovery_error,
            "repeat_count": T3_REPEATS,
            "repeat_relative_differences": repeat_differences,
            "elapsed_seconds": elapsed_seconds,
            "rss_bytes": rss_bytes,
            "swap_used_bytes": swap_used_bytes,
        }
        audit = dict(action.audit)
        audit["mode_classification_counts"] = {
            name: sum(1 for row in manifest if row["classification"] == name)
            for name in ("propagating", "near-cutoff", "evanescent")
        }
        record = {
            "schema": T3_SCHEMA,
            "profile": T3_PROFILE,
            "case": case,
            "raw_dir": str(raw_dir),
            "resolved_config_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "resolved_config_bytes": len(payload_bytes),
            "benchmark": {
                **benchmark,
                "input_template_relative_path": T3_TEMPLATE_RELATIVE_PATH,
                "input_template_bytes": len(specification.raw_input_bytes),
                "input_template_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "resolved_config_bytes": len(payload_bytes),
                "resolved_config_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            },
            "source": {
                "expected_sha": expected_source_sha,
                "commit_sha_start": identity["commit_sha"],
                "commit_sha_end": _source_identity(root)["commit_sha"],
                "tracked_status_start": identity["tracked_status"],
                "tracked_status_end": _source_identity(root)["tracked_status"],
                "input_template_path": str(template_path),
                "input_template_relative_path": T3_TEMPLATE_RELATIVE_PATH,
                "input_template_bytes": len(specification.raw_input_bytes),
                "input_template_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "resolved_config_bytes": len(payload_bytes),
                "resolved_config_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            },
            "mpi": {"size": comm.size},
            "model": {
                "wavelength_nm": float(cfg.lambda0),
                "mode_count": len(modes),
                "mode_manifest_sha256": carrier.mode_manifest_sha256,
                "mode_classification_counts": audit["mode_classification_counts"],
                "rayleigh_tolerance": float(cfg.diffraction_rayleigh_tol),
            },
            "artifacts": artifacts,
            "observations": observations,
            "carrier_audit": audit,
            "resource": {
                "rss_semantics": "mpi_rank_max_current_self_rss",
                "process_tree_evidence": "not_measured_t3",
            },
        }
        if comm.rank == 0:
            record_path.write_bytes(_canonical_json(record) + b"\n")
        comm.barrier()
        return record
    finally:
        if baseline is not None:
            baseline.destroy()
        candidate.destroy()
        direct.destroy()
        source.destroy()
        action.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="T3 dynamic DtN action runner")
    parser.add_argument("--resolved-config", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    _run_case(
        resolved_config=args.resolved_config,
        raw_dir=args.raw_dir,
        record_path=args.record,
        case=args.case,
        expected_source_sha=args.expected_source_sha,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
