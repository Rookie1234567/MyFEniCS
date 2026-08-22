"""Thin N1 local-spectral worker.

The cell operator, exact-class factors, local modes, and regional algebra live
in ``src.solvers.fullspace_local_spectral_dolfinx``.  This module only builds
the fixed p2/p3 h50 fixture, records owner-local canonical source/action
shards, and writes the serial assembled oracle for MPI1.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np


N1_SCHEMA = "task038.full3d.iterative.local-spectral-record.v1"
N1_PROFILE = "local_spectral_cell_patch_regional_oracle_v1"
N1_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
N1_CASES = {
    "p2-mpi1": {"degree": 2, "mpi_size": 1},
    "p2-mpi2": {"degree": 2, "mpi_size": 2},
    "p3-mpi1": {"degree": 3, "mpi_size": 1},
    "p3-mpi2": {"degree": 3, "mpi_size": 2},
}
N1_MESH_TARGET_NM = 50.0
N1_MODE_CAP = 8
N1_REGIONAL_RANK_CAP = 16
N1_MAX_CLASSES = 32
N1_ALGEBRA_LIMIT = 1.0e-11
N1_MPI_LIMIT = 1.0e-12
N1_REPEAT_LIMIT = 1.0e-13
N1_POU_LIMIT = 1.0e-13
N1_MPI2_UFL_BOUNDARY = (
    "mpi2_distributed_local_cell_action_only; independent assembled UFL "
    "oracle is MPI1-only"
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_json(path: Path, value: Any) -> dict[str, Any]:
    payload = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "relative_path": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _source_identity(root: Path) -> dict[str, Any]:
    status = _git(root, "status", "--short", "--untracked-files=all")
    return {
        "branch": _git(root, "branch", "--show-current"),
        "commit_sha": _git(root, "rev-parse", "HEAD"),
        "tracked_status": status,
        "clean": status == "",
    }


def _runtime_identity(root: Path) -> dict[str, Any]:
    import basix
    import dolfinx
    from mpi4py import MPI
    from petsc4py import PETSc
    import slepc4py

    marker = os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "")
    executable = Path(sys.executable).absolute()
    qualified_bin = (root / ".venv" / "bin").resolve()
    if marker != "1":
        raise RuntimeError("N1 requires qualified activation marker=1")
    if executable.parent.resolve() != qualified_bin:
        raise RuntimeError("N1 requires the repository qualified .venv")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("N1 requires PETSc complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("N1 requires PETSc int32")
    return {
        "qualified_activation": marker,
        "python": sys.version.split()[0],
        "sys_executable": str(executable),
        "qualified_venv_bin_resolved": str(qualified_bin),
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_library": MPI.Get_library_version().splitlines()[0],
        "mpi_thread_level": int(MPI.Query_thread()),
        "petsc4py": str(PETSc.Sys.getVersion()),
        "slepc4py": str(slepc4py.__version__),
        "dolfinx": str(dolfinx.__version__),
        "basix": str(basix.__version__),
        "mpi4py": str(MPI.Get_version()),
        "threads": {
            name: os.environ.get(name, "")
            for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
    }


def _rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("VmRSS is unavailable")


def _swap_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmSwap:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("VmSwap is unavailable")


def _telemetry(comm: Any, mpi: Any) -> dict[str, Any]:
    return {
        "scope": "mpi_rank_max_current_self",
        "rss_bytes": int(comm.allreduce(_rss_bytes(), op=mpi.MAX)),
        "swap_bytes": int(comm.allreduce(_swap_bytes(), op=mpi.MAX)),
        "process_tree_measured": False,
    }


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(left) - np.asarray(right))
        / max(float(np.linalg.norm(np.asarray(right))), 1.0e-300)
    )


def _canonical_key_text(key: Any) -> str:
    from benchmarks.canonical_vector_artifacts import canonical_key_json_bytes

    return canonical_key_json_bytes(key).decode("utf-8")


def _prepare_paths(raw_dir: Path, record_path: Path, comm: Any) -> None:
    error = None
    if comm.rank == 0:
        try:
            raw_dir.parent.mkdir(parents=True, exist_ok=True)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("N1 raw directory or record already exists")
            raw_dir.mkdir()
        except Exception as exc:  # only shared-path setup is handled here
            error = (type(exc).__name__, str(exc))
    error = comm.bcast(error, root=0)
    if error is not None:
        if error[0] == "FileExistsError":
            raise FileExistsError(error[1])
        raise OSError(error[1])
    comm.barrier()


def _fixture(raw_dir: Path, degree: int):
    from dataclasses import replace

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_slab_interface import build_fullspace_slab_interface
    from src.test.stage2_test_utils import stage4_block_config

    cfg = replace(
        stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=N1_MESH_TARGET_NM,
            stage4_dtn_order_policy="zero_order",
            incident_theta_deg=21.131,
            incident_phi_deg=33.690,
        ),
        nedelec_degree=degree,
    )
    mesh_data = build_airbox_mesh_3d(
        cfg, raw_dir / f"mesh-p{degree}-n{mesh_data_comm_size()}"
    )
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    topology = build_fullspace_slab_interface(
        space, mesh_data, floquet_data, cfg
    )
    return cfg, mesh_data, raw_space, space, floquet_data, topology


def mesh_data_comm_size() -> int:
    from mpi4py import MPI

    return int(MPI.COMM_WORLD.size)


def _write_action_shard(
    raw_dir: Path,
    rank: int,
    source: Mapping[Any, complex],
    action: Mapping[Any, complex],
    source_repeat: Mapping[Any, complex],
    action_repeat: Mapping[Any, complex],
) -> dict[str, Any]:
    keys = tuple(sorted(source, key=_canonical_key_text))
    if set(keys) != set(action) or set(keys) != set(source_repeat) or set(keys) != set(action_repeat):
        raise RuntimeError("source/action repeat canonical key sets differ")
    key_json = np.asarray([_canonical_key_text(key) for key in keys], dtype="U")
    arrays = {
        "key_json": key_json,
        "source": np.asarray([source[key] for key in keys], dtype=np.complex128),
        "action": np.asarray([action[key] for key in keys], dtype=np.complex128),
        "source_repeat": np.asarray(
            [source_repeat[key] for key in keys], dtype=np.complex128
        ),
        "action_repeat": np.asarray(
            [action_repeat[key] for key in keys], dtype=np.complex128
        ),
    }
    path = raw_dir / "canonical" / f"rank{rank:04d}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **arrays)
    return {
        "relative_path": str(path.relative_to(raw_dir)),
        "sha256": _sha256(path),
        "bytes": int(path.stat().st_size),
        "packet_count": len(keys),
        "dtype": "complex128",
        "key_encoding": "canonical_key_json_bytes",
    }


def _write_manifest(raw_dir: Path, descriptors: list[dict[str, Any]]) -> dict[str, Any]:
    descriptors = sorted(descriptors, key=lambda item: item["relative_path"])
    count = {int(item["packet_count"]) for item in descriptors}
    if len(count) != 1:
        raise RuntimeError("canonical shard packet counts differ")
    manifest = {
        "schema": "task038.n1.local-spectral-canonical-source-action.v1",
        "role": "full_space_source_action_owner_local_shards",
        "key_encoding": "canonical_key_json_bytes",
        "dtype": "complex128",
        "mpi_size": len(descriptors),
        "global_packet_count": int(next(iter(count))),
        "per_rank_shards": descriptors,
        "numeric_allgather": False,
    }
    path = raw_dir / "canonical" / "manifest.json"
    descriptor = _write_json(path, manifest)
    descriptor["relative_path"] = str(path.relative_to(raw_dir))
    return {**manifest, "file": descriptor}


def _write_ufl_oracle(
    raw_dir: Path,
    raw_space: Any,
    space: Any,
    mesh_data: Any,
    floquet_data: Any,
    cfg: Any,
    oracle: Mapping[str, Any],
) -> dict[str, Any]:
    import ufl

    from benchmarks.run_task038_full3d_adaptive_coarse import _constrained_dense
    from src.solvers.fullspace_local_spectral_dolfinx import _prepare_real_context

    trial = ufl.TrialFunction(raw_space)
    test = ufl.TestFunction(raw_space)
    dx = ufl.Measure("dx", domain=raw_space.mesh, subdomain_data=mesh_data.cell_tags)
    form = (
        (1.0 / complex(cfg.mu_r))
        * ufl.inner(ufl.curl(trial), ufl.curl(test))
        * dx
    )
    for tag, epsilon in (
        (cfg.tags.air, cfg.eps_air),
        (cfg.tags.substrate, cfg.eps_substrate),
        (cfg.tags.grating, cfg.eps_grating),
    ):
        form += (
            cfg.k0**2
            * abs(epsilon)
            * ufl.inner(trial, test)
            * dx(int(tag))
        )
    constrained, free_rows = _constrained_dense(
        form, raw_space, space, floquet_data.mpc
    )
    source = np.asarray(
        [oracle["source_by_raw_row"][int(row)] for row in free_rows],
        dtype=np.complex128,
    )
    assembled_action = constrained @ source
    context = _prepare_real_context(space, mesh_data, floquet_data, cfg)
    action_by_key: dict[Any, complex] = {}
    for row, value in zip(free_rows, assembled_action, strict=True):
        row = int(row)
        key = context["raw_to_key"][row]
        if key in action_by_key:
            raise RuntimeError("assembled UFL action has duplicate canonical key")
        action_by_key[key] = np.conj(context["raw_to_scale"][row]) * value
    keys = tuple(sorted(action_by_key, key=_canonical_key_text))
    expected_keys = tuple(sorted(oracle["local_action_by_key"], key=_canonical_key_text))
    if keys != expected_keys:
        raise RuntimeError("assembled UFL and local action key sets differ")
    values = np.asarray([action_by_key[key] for key in keys], dtype=np.complex128)
    path = raw_dir / "canonical" / "ufl_action.npz"
    np.savez(
        path,
        key_json=np.asarray([_canonical_key_text(key) for key in keys], dtype="U"),
        action=values,
    )
    local_values = np.asarray(
        [oracle["local_action_by_key"][key] for key in keys], dtype=np.complex128
    )
    return {
        "status": "measured",
        "kind": "small_assembled_oracle_only",
        "relative_error": _relative(local_values, values),
        "limit": N1_ALGEBRA_LIMIT,
        "global_numeric_matrix_scope": "serial fixture only; destroyed after action",
        "production_path_references_oracle": False,
        "artifact": {
            "relative_path": str(path.relative_to(raw_dir)),
            "sha256": _sha256(path),
            "bytes": int(path.stat().st_size),
            "packet_count": len(keys),
        },
    }


def _destroy_patches(patches: tuple[Any, ...]) -> None:
    if not patches:
        return
    plan = patches[0].class_plan
    for patch in patches:
        patch.destroy()
    plan.destroy()


def _run_case(root: Path, args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    spec = N1_CASES[args.case]
    if comm.size != int(spec["mpi_size"]):
        raise RuntimeError(f"{args.case} requires MPI size {spec['mpi_size']}")
    raw_dir = Path(args.raw_dir).resolve()
    record_path = Path(args.record).resolve()
    _prepare_paths(raw_dir, record_path, comm)
    source_start = _source_identity(root)
    if source_start["branch"] != N1_BRANCH:
        raise RuntimeError("N1 worker is on the wrong branch")
    if source_start["commit_sha"] != args.expected_source_sha or not source_start["clean"]:
        raise RuntimeError("N1 worker requires the expected clean source SHA")
    runtime = _runtime_identity(root)
    runtime_root = comm.bcast(runtime if comm.rank == 0 else None, root=0)
    if runtime != runtime_root:
        raise RuntimeError("MPI ranks do not share runtime identity")

    cfg, mesh_data, raw_space, space, floquet_data, topology = _fixture(
        raw_dir, int(spec["degree"])
    )
    from src.solvers.fullspace_local_spectral_dolfinx import (
        build_real_local_regional_rayleigh_ritz,
        build_real_local_spectral_patches,
        small_p2p3_local_action_oracle,
    )

    patches, patch_audit = build_real_local_spectral_patches(
        space, mesh_data, floquet_data, cfg
    )
    first_mode_digest = str(patch_audit["mode_digest"])
    local_mode_count = max((int(patch.modes.shape[1]) for patch in patches), default=0)
    regional, regional_audit = build_real_local_regional_rayleigh_ritz(
        patches, space, mesh_data, floquet_data, cfg
    )
    regional_records = {
        repr(region): {
            key: value
            for key, value in dict(record).items()
            if key != "coefficients"
        }
        for region, record in regional.items()
    }
    _destroy_patches(patches)

    repeat_patches, repeat_audit = build_real_local_spectral_patches(
        space, mesh_data, floquet_data, cfg
    )
    repeat_mode_digest = str(repeat_audit["mode_digest"])
    _destroy_patches(repeat_patches)

    oracle = small_p2p3_local_action_oracle(space, mesh_data, floquet_data, cfg)
    repeat_oracle = small_p2p3_local_action_oracle(
        space, mesh_data, floquet_data, cfg
    )
    shard = _write_action_shard(
        raw_dir,
        comm.rank,
        oracle["canonical_source"],
        oracle["local_action_by_key"],
        repeat_oracle["canonical_source"],
        repeat_oracle["local_action_by_key"],
    )
    shard_descriptors = comm.gather(shard, root=0)
    manifest = None
    if comm.rank == 0:
        manifest = _write_manifest(raw_dir, shard_descriptors)
    manifest = comm.bcast(manifest, root=0)

    ufl_oracle = {"status": "not_run", "boundary": N1_MPI2_UFL_BOUNDARY}
    if comm.size == 1:
        ufl_oracle = _write_ufl_oracle(
            raw_dir, raw_space, space, mesh_data, floquet_data, cfg, oracle
        )
    rank_fact = {
        "rank": comm.rank,
        "owned_patch_count": int(patch_audit["patch_count"]),
        "local_mode_count": local_mode_count,
        "mode_digest": first_mode_digest,
        "repeat_mode_digest": repeat_mode_digest,
        "mode_repeat_exact": bool(first_mode_digest == repeat_mode_digest),
        "patch_audit": _jsonable(patch_audit),
        "regional_audit": _jsonable(regional_audit),
        "regional_records": _jsonable(regional_records),
    }
    rank_facts = comm.gather(rank_fact, root=0)
    source_end = _source_identity(root)
    resource = _telemetry(comm, MPI)
    if comm.rank == 0:
        facts = {
            "schema": "task038.n1.local-spectral-raw-facts.v1",
            "rank_facts": rank_facts,
            "mode_cap": N1_MODE_CAP,
            "regional_rank_cap": N1_REGIONAL_RANK_CAP,
            "source_packet_count": len(oracle["canonical_source"]),
            "class_count": int(oracle["class_count"]),
            "source_action_repeat_relative": _relative(
                np.asarray(list(oracle["canonical_source"].values())),
                np.asarray(list(repeat_oracle["canonical_source"].values())),
            ),
            "action_repeat_relative": _relative(
                np.asarray(list(oracle["local_action_by_key"].values())),
                np.asarray(list(repeat_oracle["local_action_by_key"].values())),
            ),
            "action_repeat_exact": bool(
                all(
                    oracle["local_action_by_key"][key]
                    == repeat_oracle["local_action_by_key"][key]
                    for key in oracle["local_action_by_key"]
                )
            ),
            "regional_diagnostic_only": True,
            "regional_projector_cross_mpi_gate": "diagnostic_only_not_hard_gate",
            "regional_packet_cross_mpi_gate": "diagnostic_only_not_hard_gate",
        }
        facts_descriptor = _write_json(raw_dir / "facts.json", facts)
        source = {
            "branch": source_start["branch"],
            "expected_sha": args.expected_source_sha,
            "commit_sha_start": source_start["commit_sha"],
            "commit_sha_end": source_end["commit_sha"],
            "tracked_status_start": source_start["tracked_status"],
            "tracked_status_end": source_end["tracked_status"],
            "clean_start": bool(source_start["clean"]),
            "clean_end": bool(source_end["clean"]),
        }
        record = {
            "schema": N1_SCHEMA,
            "stage": "n1",
            "profile": N1_PROFILE,
            "case": args.case,
            "degree": int(spec["degree"]),
            "mesh_target_nm": N1_MESH_TARGET_NM,
            "mpi_size": int(comm.size),
            "raw_dir": str(raw_dir),
            "input": {
                "path": str(Path(args.input).resolve()),
                "sha256": _sha256(Path(args.input)),
                "bytes": int(Path(args.input).stat().st_size),
            },
            "source": source,
            "runtime": runtime,
            "model": {
                "wavelength_nm": float(cfg.lambda0),
                "incident_theta_deg": float(cfg.incident_theta_deg),
                "incident_phi_deg": float(cfg.incident_phi_deg),
                "source_formula": "current small_p2p3_local_action_oracle stable sha256(repr(canonical key))",
                "source_key_identity": "physical canonical cell/row key; no local row/rank input",
            },
            "topology": {
                "owned_patch_counts_by_rank": [
                    int(item["owned_patch_count"]) for item in rank_facts
                ],
                "global_patch_count": int(
                    sum(item["owned_patch_count"] for item in rank_facts)
                ),
                "class_count": int(facts["class_count"]),
                "class_owner_factor_identity": "one packed factor per exact class at deterministic owner",
            },
            "local_spectral": {
                "mode_cap": N1_MODE_CAP,
                "selected_mode_count_max": int(
                    max(item["local_mode_count"] for item in rank_facts)
                ),
                "mode_repeat_limit": N1_REPEAT_LIMIT,
                "mode_repeat_exact_by_rank": [
                    bool(item["mode_repeat_exact"]) for item in rank_facts
                ],
                "facts_artifact": facts_descriptor,
            },
            "regional": {
                "rank_cap": N1_REGIONAL_RANK_CAP,
                "diagnostic_only": True,
                "projector_cross_mpi": "measured_diagnostic_not_hard_gate",
                "packet_cross_mpi": "measured_diagnostic_not_hard_gate",
            },
            "source_action": {
                "manifest": manifest,
                "role": "full_space_source_action_owner_local_shards",
                "repeat_relative_limit": N1_REPEAT_LIMIT,
                "source_action_raw_shards": True,
                "production_numeric_allgather": False,
            },
            "serial_assembled_oracle": ufl_oracle,
            "resource": resource,
            "forbidden": {
                "global_numeric_allgather": False,
                "global_aij_in_production": False,
                "global_schur": False,
                "global_factor": False,
                "per_rank_full_basis_replication": False,
                "pde_solve": False,
            },
            "worker_facts_only": True,
        }
        record_path.write_bytes(_json_bytes(record))
    comm.barrier()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(N1_CASES), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from mpi4py import MPI

    root = Path(__file__).resolve().parents[1]
    if args.expected_mpi_size not in {1, 2}:
        raise SystemExit("N1 expected MPI size must be 1 or 2")
    if MPI.COMM_WORLD.size != args.expected_mpi_size:
        raise SystemExit("MPI size does not match --expected-mpi-size")
    return _run_case(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
