"""Action-only physical-dual component evidence worker.

The candidate is the current dynamic DtN carrier.  The oracle creates fresh
UFL facet forms for every recorded component and never reads carrier entries.
Only compact descriptors are written to the record; local vectors and dual
canonical shards belong below the ignored raw directory.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

SCHEMA = "fullspace.full3d.dual-component-record.v1"
PROFILE = "full3d_scalable_v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
CASES = {
    "p2-h50": {"degree": 2, "mesh_target_nm": 50.0},
    "p3-h50": {"degree": 3, "mesh_target_nm": 50.0},
    "p6-h10": {"degree": 6, "mesh_target_nm": 10.0},
}
COMPONENT_LIMIT_SMALL = 1.0e-12
COMPONENT_LIMIT_FROZEN = 1.0e-11
RECOMPOSE_LIMIT = 1.0e-12


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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Git identity probe failed")
        return result.stdout.strip()

    status = git("status", "--short", "--untracked-files=all")
    return {
        "branch": git("branch", "--show-current"),
        "commit_sha": git("rev-parse", "HEAD"),
        "tracked_status": status,
        "clean": status == "",
    }


def _prepare_raw_dir(raw_dir: Path, record_path: Path, comm: Any) -> None:
    error: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            raw_dir.parent.mkdir(parents=True, exist_ok=True)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("component raw directory or record exists")
            raw_dir.mkdir()
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


def _rss_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("VmRSS telemetry is unavailable")


def _swap_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("VmSwap telemetry is unavailable")


def _telemetry(comm: Any, mpi: Any) -> dict[str, int | str]:
    return {
        "rss_semantics": "mpi_rank_max_current_self_rss",
        "swap_semantics": "current_process_VmSwap",
        "rank_max_current_rss_bytes": int(comm.allreduce(_rss_bytes(), op=mpi.MAX)),
        "rank_max_swap_used_bytes": int(comm.allreduce(_swap_bytes(), op=mpi.MAX)),
    }


def _assemble_compiled(form: Any, *, mpc: Any, fem_petsc: Any, dolfinx_mpc: Any) -> Any:
    from petsc4py import PETSc

    vector = (
        dolfinx_mpc.assemble_vector(form, mpc)
        if mpc is not None
        else fem_petsc.assemble_vector(form)
    )
    vector.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return vector


def _direct_phase(ufl: Any, PETSc: Any, x: Any, wavevector: Sequence[complex]) -> Any:
    return ufl.exp(
        sum(
            PETSc.ScalarType(1j * complex(wavevector[index])) * x[index]
            for index in range(3)
        )
    )


def _direct_vector_form(
    *,
    fem: Any,
    ufl: Any,
    PETSc: Any,
    function_space: Any,
    mesh_data: Any,
    tag: int,
    component: int,
    scalar: complex,
    wavevector: Sequence[complex],
    quadrature_degree: int,
) -> Any:
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    phase = _direct_phase(ufl, PETSc, x, wavevector)
    values = [PETSc.ScalarType(0.0)] * 3
    values[component] = PETSc.ScalarType(scalar) * phase
    test = ufl.TestFunction(function_space)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    return fem.form(
        ufl.inner(ufl.as_vector(tuple(values)), test) * ds(tag),
        form_compiler_options={"quadrature_degree": int(quadrature_degree)},
    )


def _direct_scalar(
    *, fem: Any, ufl: Any, mesh_data: Any, expression: Any, tag: int, quadrature_degree: int
) -> complex:
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    local = fem.assemble_scalar(
        fem.form(
            expression * ds(tag),
            form_compiler_options={"quadrature_degree": int(quadrature_degree)},
        )
    )
    return complex(mesh_data.mesh.comm.allreduce(local))


def _direct_base_data(cfg: Any) -> tuple[np.ndarray, np.ndarray]:
    normal = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    wavevector = np.asarray(cfg.wavevector, dtype=np.complex128)
    electric = complex(cfg.incident_amplitude) * np.asarray(
        cfg.polarization_vector, dtype=np.complex128
    )
    traction = np.cross(1j * np.cross(wavevector, electric), normal)
    return traction, wavevector


def _direct_mode_data(
    *,
    fem: Any,
    ufl: Any,
    PETSc: Any,
    mesh_data: Any,
    cfg: Any,
    mode: Any,
    quadrature_degree: int,
) -> tuple[float, complex, np.ndarray]:
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    mode_phase = _direct_phase(ufl, PETSc, x, mode.k_vector)
    incident_phase = _direct_phase(ufl, PETSc, x, cfg.wavevector)
    mode_values = [
        PETSc.ScalarType(mode.e_vector[index]) * mode_phase for index in range(2)
    ] + [PETSc.ScalarType(0.0)]
    incident_values = [
        PETSc.ScalarType(complex(cfg.incident_amplitude) * cfg.polarization_vector[index])
        * incident_phase
        for index in range(2)
    ] + [PETSc.ScalarType(0.0)]
    mode_field = ufl.as_vector(tuple(mode_values))
    incident_field = ufl.as_vector(tuple(incident_values))
    tag = int(cfg.tags.z_max)
    denominator = _direct_scalar(
        fem=fem,
        ufl=ufl,
        mesh_data=mesh_data,
        expression=ufl.inner(mode_field, mode_field),
        tag=tag,
        quadrature_degree=quadrature_degree,
    ).real
    numerator = _direct_scalar(
        fem=fem,
        ufl=ufl,
        mesh_data=mesh_data,
        expression=ufl.inner(incident_field, mode_field),
        tag=tag,
        quadrature_degree=quadrature_degree,
    )
    if not math.isfinite(float(denominator)) or denominator <= 0.0:
        raise RuntimeError("direct mode H is not finite and positive")
    normal = np.asarray(
        (0.0, 0.0, 1.0) if mode.side == "top" else (0.0, 0.0, -1.0),
        dtype=np.float64,
    )
    traction = np.cross(1j * np.cross(mode.k_vector, mode.e_vector), normal)
    return float(denominator), complex(numerator / denominator), traction


def _direct_component(
    *,
    fem: Any,
    fem_petsc: Any,
    dolfinx_mpc: Any,
    ufl: Any,
    PETSc: Any,
    function_space: Any,
    mesh_data: Any,
    mpc: Any,
    tag: int,
    component: int,
    scalar: complex,
    wavevector: Sequence[complex],
    quadrature_degree: int,
) -> Any:
    form = _direct_vector_form(
        fem=fem,
        ufl=ufl,
        PETSc=PETSc,
        function_space=function_space,
        mesh_data=mesh_data,
        tag=tag,
        component=component,
        scalar=scalar,
        wavevector=wavevector,
        quadrature_degree=quadrature_degree,
    )
    return _assemble_compiled(
        form, mpc=mpc, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc
    )


def _add_in_place(target: Any, value: Any) -> None:
    target.axpy(1.0, value)


def _write_local_vector(raw_dir: Path, label: str, vector: Any, comm: Any) -> dict[str, Any]:
    directory = raw_dir / "local"
    directory.mkdir(parents=True, exist_ok=True)
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    path = directory / f"{label}.rank{comm.rank:04d}.npy"
    np.save(path, values)
    start, end = map(int, vector.getOwnershipRange())
    shard = {
        "relative_path": str(path.relative_to(raw_dir)),
        "sha256": _sha256_path(path),
        "bytes": int(path.stat().st_size),
        "row_start": start,
        "row_end": end,
        "count": int(values.size),
        "finite": bool(np.all(np.isfinite(values))),
        "norm_sq": float(np.vdot(values, values).real),
    }
    shards = comm.gather(shard, root=0)
    descriptor = None
    if comm.rank == 0:
        manifest = {
            "schema": "fullspace.dual-component-local-v1",
            "label": label,
            "shards": shards,
            "owned_count": int(sum(item["count"] for item in shards)),
            "finite": bool(all(item["finite"] for item in shards)),
            "norm_sq": float(sum(item["norm_sq"] for item in shards)),
        }
        manifest_path = directory / f"{label}.json"
        manifest_path.write_bytes(_canonical_json(manifest) + b"\n")
        descriptor = {
            "kind": "owner_local_vector",
            "manifest_relative_path": str(manifest_path.relative_to(raw_dir)),
            "manifest_sha256": _sha256_path(manifest_path),
            "owned_count": manifest["owned_count"],
            "finite": manifest["finite"],
            "norm": float(math.sqrt(manifest["norm_sq"])),
        }
    return comm.bcast(descriptor, root=0)


def _write_dual_canonical(
    raw_dir: Path, label: str, function_space: Any, mpc: Any, vector: Any, comm: Any
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
    )

    directory = raw_dir / "canonical"
    directory.mkdir(parents=True, exist_ok=True)
    packets, audit = extract_canonical_full_fe_dual_packets(function_space, mpc, vector)
    shard_path = directory / f"{label}.rank{comm.rank:04d}.jsonl"
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
        manifest_path = directory / f"{label}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "kind": "full_fe_dual_canonical_manifest",
            "manifest_relative_path": str(manifest_path.relative_to(raw_dir)),
            "manifest_sha256": manifest_sha,
            "packet_count": int(manifest["global_summed_packet_count"]),
            "duplicate_count": int(manifest["summed_local_duplicate_count"]),
            "finite": bool(all(item.get("packet_finite", True) for item in shards)),
        }
    return comm.bcast(descriptor, root=0)


def _state(
    *, raw_dir: Path, label: str, pre: Any, owner: Any, space: Any, mpc: Any, comm: Any
) -> dict[str, Any]:
    pre_local = _write_local_vector(raw_dir, f"{label}_pre_mpc", pre, comm)
    owner_local = _write_local_vector(raw_dir, f"{label}_owner_local", owner, comm)
    canonical = _write_dual_canonical(raw_dir, label, space, mpc, owner, comm)
    return {
        "pre_mpc": pre_local,
        "owner_local": owner_local,
        "canonical": canonical,
    }


def _sum_vectors(vectors: Sequence[Any], template: Any) -> Any:
    result = template.duplicate()
    result.set(0.0)
    for vector in vectors:
        _add_in_place(result, vector)
    return result


def _case_config(root: Path, case: str, input_path: Path | None) -> tuple[Any, bytes, str | None]:
    from src.common.config_3d import target_stage4_config
    from src.io import load_and_resolve
    from src.io.resolved_config import resolved_config_bytes
    from src.io.input_validation import simulation_config_3d_from_normalized

    if case in {"p2-h50", "p3-h50"}:
        spec = CASES[case]
        cfg = replace(
            target_stage4_config(
                degree=int(spec["degree"]), h_nm=float(spec["mesh_target_nm"])
            ),
            incident_theta_deg=21.131,
            incident_phi_deg=33.690,
        )
        return cfg, _canonical_json({"case": case, "degree": spec["degree"], "mesh_target_nm": spec["mesh_target_nm"]}), None
    path = (input_path or root / "input/templates/full3d_iterative_example.dat").resolve()
    specification = load_and_resolve(path)
    payload = resolved_config_bytes(specification)
    return (
        simulation_config_3d_from_normalized(json.loads(payload)),
        payload,
        specification.physical_model_sha256,
    )


def _component_record(
    *,
    mode: Any,
    mode_index: int,
    candidate_amp: complex,
    direct_amp: complex,
    candidate_h: float,
    direct_h: float,
    candidate_traction: np.ndarray,
    direct_traction: np.ndarray,
    components: dict[str, Any],
    candidate_total: dict[str, Any],
    direct_total: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mode_index": int(mode_index),
        "side": str(mode.side),
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization),
        "alpha": complex(mode.alpha),
        "gamma": complex(mode.gamma),
        "kz": complex(mode.k_vector[2]),
        "e_vector": tuple(complex(value) for value in mode.e_vector),
        "candidate_traction": tuple(complex(value) for value in candidate_traction),
        "direct_traction": tuple(complex(value) for value in direct_traction),
        "candidate_H": float(candidate_h),
        "direct_H": float(direct_h),
        "candidate_amplitude": complex(candidate_amp),
        "direct_amplitude": complex(direct_amp),
        "components": components,
        "candidate_total": candidate_total,
        "direct_total": direct_total,
    }


def _mode_grouping(
    modes: Sequence[Any],
    amplitudes: np.ndarray,
) -> dict[str, Any]:
    """Describe side/polarization groups by exact inventory indices."""

    nonzero = {
        index for index, value in enumerate(amplitudes) if complex(value) != 0.0j
    }

    def group(indices: list[int]) -> dict[str, Any]:
        selected_nonzero = [index for index in indices if index in nonzero]
        selected_zero = [index for index in indices if index not in nonzero]
        return {
            "inventory_mode_count": len(indices),
            "nonzero_mode_indices": selected_nonzero,
            "exact_zero_mode_indices": selected_zero,
            "zero_incident_semantics": (
                "no modes in this group"
                if not indices
                else "incident amplitude is exactly 0j; no modal RHS contribution"
            ),
            "total": {
                "source": "sum of mode total states listed by index; no duplicate vector is written",
                "mode_indices": selected_nonzero,
            },
        }

    side_groups = {
        side: group(
            [index for index, mode in enumerate(modes) if str(mode.side) == side]
        )
        for side in ("top", "bottom")
    }
    polarizations = {str(mode.polarization) for mode in modes} | {"s", "p"}
    polarization_groups = {
        polarization: group(
            [
                index
                for index, mode in enumerate(modes)
                if str(mode.polarization) == polarization
            ]
        )
        for polarization in sorted(polarizations)
    }
    return {"side": side_groups, "polarization": polarization_groups}


def _run_case(args: argparse.Namespace) -> int:
    from mpi4py import MPI
    from dolfinx import fem
    from dolfinx.fem import petsc as fem_petsc
    import dolfinx_mpc
    import ufl
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_vector,
        _assemble_unconstrained_vector,
        _dtn_surface_quadrature_degree,
        _incident_projection_onto_top_mode,
        _incident_top_traction_form,
        _mode_projection_denominator,
        _traction_vector,
        _ReusableSurfaceComponentAssembler,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )

    comm = MPI.COMM_WORLD
    root = Path(__file__).resolve().parents[1]
    source_start = _source_identity(root)
    if source_start["branch"] != BRANCH:
        raise RuntimeError("component worker is on the wrong branch")
    if source_start["commit_sha"] != args.expected_source_sha:
        raise RuntimeError("component source SHA does not match expectation")
    if source_start["tracked_status"] and not args.allow_dirty:
        raise RuntimeError("component formal worker requires a clean source")
    if args.expected_mpi_size is not None and comm.size != args.expected_mpi_size:
        raise RuntimeError("component MPI size does not match expectation")
    raw_dir = Path(args.raw_dir).resolve()
    record_path = Path(args.record).resolve()
    _prepare_raw_dir(raw_dir, record_path, comm)
    cfg, config_bytes, physical_model_sha = _case_config(root, args.case, args.input)
    if cfg.stage4_boundary_model != "dtn_port":
        raise RuntimeError("component oracle requires the dynamic DtN boundary")
    mesh_data = build_airbox_mesh_3d(cfg, raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    modes, _manifest, _manifest_sha = build_dynamic_mode_inventory(cfg)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = {
        (side, component): _ReusableSurfaceComponentAssembler(
            raw_space,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=quadrature_degree,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, floquet_data.mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    direct_base_traction, direct_wavevector = _direct_base_data(cfg)
    candidate_base_pre = _assemble_unconstrained_vector(
        _incident_top_traction_form(raw_space, mesh_data, cfg),
        quadrature_degree=quadrature_degree,
    )
    candidate_base = _assemble_mpc_vector(
        _incident_top_traction_form(raw_space, mesh_data, cfg),
        floquet_data.mpc,
        quadrature_degree=quadrature_degree,
    )
    direct_base_pre = _direct_component(
        fem=fem, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc, ufl=ufl, PETSc=PETSc,
        function_space=raw_space, mesh_data=mesh_data, mpc=None, tag=int(cfg.tags.z_max),
        component=0, scalar=direct_base_traction[0], wavevector=direct_wavevector,
        quadrature_degree=quadrature_degree,
    )
    direct_base_pre_1 = _direct_component(
        fem=fem, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc, ufl=ufl, PETSc=PETSc,
        function_space=raw_space, mesh_data=mesh_data, mpc=None, tag=int(cfg.tags.z_max),
        component=1, scalar=direct_base_traction[1], wavevector=direct_wavevector,
        quadrature_degree=quadrature_degree,
    )
    direct_base_0 = _direct_component(
        fem=fem, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc, ufl=ufl, PETSc=PETSc,
        function_space=raw_space, mesh_data=mesh_data, mpc=floquet_data.mpc, tag=int(cfg.tags.z_max),
        component=0, scalar=direct_base_traction[0], wavevector=direct_wavevector,
        quadrature_degree=quadrature_degree,
    )
    direct_base_1 = _direct_component(
        fem=fem, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc, ufl=ufl, PETSc=PETSc,
        function_space=raw_space, mesh_data=mesh_data, mpc=floquet_data.mpc, tag=int(cfg.tags.z_max),
        component=1, scalar=direct_base_traction[1], wavevector=direct_wavevector,
        quadrature_degree=quadrature_degree,
    )
    base_component_states = {}
    for component, pre_vector, owner_vector in (
        (0, direct_base_pre, direct_base_0),
        (1, direct_base_pre_1, direct_base_1),
    ):
        base_component_states[str(component)] = _state(
            raw_dir=raw_dir,
            label=f"base_component{component}_oracle",
            pre=pre_vector,
            owner=owner_vector,
            space=space,
            mpc=floquet_data.mpc,
            comm=comm,
        )
    direct_base_pre_sum = _sum_vectors(
        (direct_base_pre, direct_base_pre_1), direct_base_pre
    )
    direct_base = _sum_vectors((direct_base_0, direct_base_1), direct_base_0)
    direct_base_pre.destroy()
    direct_base_pre_1.destroy()
    direct_base_0.destroy()
    direct_base_1.destroy()
    direct_base_pre = direct_base_pre_sum
    base_state = {
        "candidate": _state(raw_dir=raw_dir, label="base_candidate", pre=candidate_base_pre, owner=candidate_base, space=space, mpc=floquet_data.mpc, comm=comm),
        "oracle": _state(raw_dir=raw_dir, label="base_oracle", pre=direct_base_pre, owner=direct_base, space=space, mpc=floquet_data.mpc, comm=comm),
        "direct_components": base_component_states,
        "component_sum": {
            "source": "independent direct component assembly",
            "components": ["0", "1"],
            "whole": "oracle",
            "candidate_whole": "candidate",
            "candidate_component_api": False,
        },
    }

    candidate_amplitudes = np.asarray(
        [_incident_projection_onto_top_mode(mode, cfg) for mode in modes],
        dtype=np.complex128,
    )
    nonzero_indices = [
        index for index, amplitude in enumerate(candidate_amplitudes)
        if complex(amplitude) != 0.0j
    ]
    mode_records: list[dict[str, Any]] = []
    candidate_mode_vectors: list[Any] = []
    direct_mode_vectors: list[Any] = []
    candidate_modal_pre_vectors: list[Any] = []
    direct_modal_pre_vectors: list[Any] = []
    for mode_index in nonzero_indices:
        mode = modes[mode_index]
        candidate_amp = complex(candidate_amplitudes[mode_index])
        candidate_h = _mode_projection_denominator(mode, cfg)
        candidate_traction = np.asarray(_traction_vector(mode, cfg), dtype=np.complex128)
        direct_h, direct_amp, direct_traction = _direct_mode_data(
            fem=fem, ufl=ufl, PETSc=PETSc, mesh_data=mesh_data, cfg=cfg, mode=mode,
            quadrature_degree=quadrature_degree,
        )
        component_records: dict[str, Any] = {}
        candidate_components: list[Any] = []
        direct_components: list[Any] = []
        candidate_components_pre: list[Any] = []
        direct_components_pre: list[Any] = []
        for component in (0, 1):
            candidate_pre = assemblers[(mode.side, component)].assemble_unconstrained_vector(mode)
            candidate_pre.scale(-candidate_traction[component] * candidate_amp)
            rows, values = assemblers[(mode.side, component)].assemble_entries(mode, floquet_data.mpc)
            candidate_owner = direct_base.duplicate()
            candidate_owner.set(0.0)
            start, _end = candidate_owner.getOwnershipRange()
            owner_values = candidate_owner.getArray()
            owner_values[rows - start] += (-candidate_traction[component] * candidate_amp) * values
            direct_pre = _direct_component(
                fem=fem, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc, ufl=ufl, PETSc=PETSc,
                function_space=raw_space, mesh_data=mesh_data, mpc=None, tag=int(cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min),
                component=component, scalar=-direct_traction[component] * direct_amp,
                wavevector=mode.k_vector, quadrature_degree=quadrature_degree,
            )
            direct_owner = _direct_component(
                fem=fem, fem_petsc=fem_petsc, dolfinx_mpc=dolfinx_mpc, ufl=ufl, PETSc=PETSc,
                function_space=raw_space, mesh_data=mesh_data, mpc=floquet_data.mpc, tag=int(cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min),
                component=component, scalar=-direct_traction[component] * direct_amp,
                wavevector=mode.k_vector, quadrature_degree=quadrature_degree,
            )
            candidate_components_pre.append(candidate_pre)
            candidate_components.append(candidate_owner)
            direct_components_pre.append(direct_pre)
            direct_components.append(direct_owner)
            component_records[str(component)] = {
                "candidate": _state(raw_dir=raw_dir, label=f"mode{mode_index:03d}_component{component}_candidate", pre=candidate_pre, owner=candidate_owner, space=space, mpc=floquet_data.mpc, comm=comm),
                "oracle": _state(raw_dir=raw_dir, label=f"mode{mode_index:03d}_component{component}_oracle", pre=direct_pre, owner=direct_owner, space=space, mpc=floquet_data.mpc, comm=comm),
                "component": component,
            }
        candidate_mode = direct_base.duplicate()
        dtn_action.apply_modal_rhs(
            tuple(candidate_amp if index == mode_index else 0.0j for index in range(len(modes))),
            candidate_mode,
        )
        direct_mode = _sum_vectors(direct_components, direct_components[0])
        candidate_mode_pre = _sum_vectors(candidate_components_pre, candidate_components_pre[0])
        direct_mode_pre = _sum_vectors(direct_components_pre, direct_components_pre[0])
        candidate_mode_vectors.append(candidate_mode)
        direct_mode_vectors.append(direct_mode)
        candidate_modal_pre_vectors.append(candidate_mode_pre)
        direct_modal_pre_vectors.append(direct_mode_pre)
        mode_total_state = {
            "candidate": _state(raw_dir=raw_dir, label=f"mode{mode_index:03d}_total_candidate", pre=candidate_mode_pre, owner=candidate_mode, space=space, mpc=floquet_data.mpc, comm=comm),
            "oracle": _state(raw_dir=raw_dir, label=f"mode{mode_index:03d}_total_oracle", pre=direct_mode_pre, owner=direct_mode, space=space, mpc=floquet_data.mpc, comm=comm),
        }
        mode_records.append(
            _component_record(
                mode=mode, mode_index=mode_index, candidate_amp=candidate_amp,
                direct_amp=direct_amp, candidate_h=candidate_h, direct_h=direct_h,
                candidate_traction=candidate_traction, direct_traction=direct_traction,
                components=component_records,
                candidate_total=mode_total_state["candidate"],
                direct_total=mode_total_state["oracle"],
            )
        )
        for vector in (*candidate_components, *direct_components):
            vector.destroy()
        for vector in (*candidate_components_pre, *direct_components_pre):
            vector.destroy()
    candidate_modal_pre = _sum_vectors(candidate_modal_pre_vectors, candidate_base_pre)
    direct_modal_pre = _sum_vectors(direct_modal_pre_vectors, direct_base_pre)
    candidate_modal = direct_base.duplicate()
    dtn_action.apply_modal_rhs(tuple(candidate_amplitudes), candidate_modal)
    direct_modal = _sum_vectors(direct_mode_vectors, direct_base)
    modal_state = {
        "candidate": _state(raw_dir=raw_dir, label="modal_total_candidate", pre=candidate_modal_pre, owner=candidate_modal, space=space, mpc=floquet_data.mpc, comm=comm),
        "oracle": _state(raw_dir=raw_dir, label="modal_total_oracle", pre=direct_modal_pre, owner=direct_modal, space=space, mpc=floquet_data.mpc, comm=comm),
    }
    candidate_rhs = direct_base.duplicate()
    dtn_action.compose_physical_rhs(candidate_base, tuple(candidate_amplitudes), candidate_rhs)
    direct_rhs = _sum_vectors((direct_base, direct_modal), direct_base)
    candidate_rhs_repeat = direct_base.duplicate()
    dtn_action.compose_physical_rhs(candidate_base, tuple(candidate_amplitudes), candidate_rhs_repeat)
    candidate_rhs_pre = _sum_vectors(
        (candidate_base_pre, candidate_modal_pre), candidate_base_pre
    )
    direct_rhs_pre = _sum_vectors(
        (direct_base_pre, direct_modal_pre), direct_base_pre
    )
    rhs_state = {
        "candidate": _state(raw_dir=raw_dir, label="rhs_candidate", pre=candidate_rhs_pre, owner=candidate_rhs, space=space, mpc=floquet_data.mpc, comm=comm),
        "oracle": _state(raw_dir=raw_dir, label="rhs_oracle", pre=direct_rhs_pre, owner=direct_rhs, space=space, mpc=floquet_data.mpc, comm=comm),
        "candidate_repeat": _write_dual_canonical(raw_dir, "rhs_candidate_repeat", space, floquet_data.mpc, candidate_rhs_repeat, comm),
    }
    rhs_state["oracle_repeat"] = dict(rhs_state["oracle"]["canonical"])
    rhs_state["oracle_repeat_alias_of"] = "oracle"
    grouping = _mode_grouping(modes, candidate_amplitudes)

    audit = {
        "surface_side": "top",
        "facet_tag": int(cfg.tags.z_max),
        "outward_normal": [0.0, 0.0, 1.0],
        "traction_definition": "cross(1j*cross(k,e), outward_normal)",
        "coupling_sign": "negative traction",
        "conjugation": "UFL inner(vector, test); dual entity transform T^H",
        "e_vector_components": "mode.e_vector[0:2]",
        "projection_denominator": "H = direct surface inner(mode_t, mode_t)",
        "mpc": {
            "finalized": True,
            "slave_rows_excluded": True,
            "slave_count": int(len(floquet_data.mpc.slaves)),
            "phase_application": "finalized Floquet MPC once",
            "manual_phase_application": False,
        },
        "numeric_allgather": False,
        "global_aij_materialized": False,
        "dense_interface_schur_materialized": False,
        "ksp_created": False,
        "pde_run": False,
        "official_physics": "not_run",
    }
    telemetry = _telemetry(comm, MPI)
    record = {
        "schema": SCHEMA,
        "profile": PROFILE,
        "case": args.case,
        "degree": int(cfg.nedelec_degree),
        "mesh_target_nm": float(cfg.mesh_target_size),
        "mpi_size": int(comm.size),
        "raw_dir": str(raw_dir),
        "source": {
            "branch": source_start["branch"],
            "expected_sha": args.expected_source_sha,
            "commit_sha_start": source_start["commit_sha"],
            "commit_sha_end": _source_identity(root)["commit_sha"],
            "tracked_status_start": source_start["tracked_status"],
            "tracked_status_end": _source_identity(root)["tracked_status"],
        },
        "config": {
            "bytes": len(config_bytes),
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
            "physical_model_sha256": physical_model_sha,
        },
        "modes": {
            "inventory_count": len(modes),
            "nonzero_incident_count": len(mode_records),
            "inventory": [
                {
                    "mode_index": int(index),
                    "side": str(mode.side),
                    "polarization": str(mode.polarization),
                    "incident_amplitude": complex(candidate_amplitudes[index]),
                }
                for index, mode in enumerate(modes)
            ],
            "records": mode_records,
            "grouping": grouping,
        },
        "components": {
            "incident_base": base_state,
            "modal_total": modal_state,
            "rhs": rhs_state,
        },
        "audit": audit,
        "telemetry": telemetry,
        "authority_classification": "OLD_W5_PHYSICAL_DUAL_NOT_CURRENT_AUTHORITY",
    }
    if comm.rank == 0:
        record_path.write_bytes(_canonical_json(record) + b"\n")
    comm.barrier()
    for vector in (
        direct_base_pre,
        candidate_base,
        candidate_base_pre,
        direct_base,
        direct_modal,
        candidate_modal,
        candidate_rhs_pre,
        direct_rhs_pre,
        candidate_rhs,
        candidate_rhs_repeat,
        direct_rhs,
    ):
        vector.destroy()
    for vector in (*candidate_mode_vectors, *direct_mode_vectors, *candidate_modal_pre_vectors, *direct_modal_pre_vectors):
        vector.destroy()
    dtn_action.destroy()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Full-space physical-dual component evidence")
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return _run_case(args)


if __name__ == "__main__":
    raise SystemExit(main())
