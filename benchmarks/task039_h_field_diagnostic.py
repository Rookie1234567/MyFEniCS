"""Offline Task39 Full3D H-field replay and three-path comparison.

The replay reconstructs an existing canonical Full3D field only.  It does not
enter a solver, assemble a matrix, or call a Full3D runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.task039_review_v1_contracts import diagnose_h_paths
from src.io.resolved_config import canonical_json_bytes


REPLAY_SCHEMA = "task039.full3d-h-diagnostic-replay.v1"
PAYLOAD_SCHEMA = "task039.full3d-h-diagnostic-payload.v1"
CANONICAL_MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
FROZEN_PLANES = (10.0, 30.0, 60.0, 90.0, 110.0)
T3_RUN_ID = "task039_5nm_full3d_direct_p6h10_mpi8"
T3_SOURCE_SHA = "76b6d6c08769496b60139797b2b9ab7849810964"
T3_INPUT_SHA256 = "e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6"
T3_PHYSICAL_MODEL_SHA256 = (
    "db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a"
)
H_PLANE_ROLES = (
    "interface_bottom",
    "bottom_element_safe_offset",
    "lower_reference",
    "middle_reference",
    "upper_reference",
    "top_element_safe_offset",
    "interface_top",
)
DIAGNOSTIC_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "normal_poynting_flux_W_per_m2",
    "vacuum_weighted_sampled_energy_J_per_m3",
)
HYBRID_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "native_E_V_per_m",
    "native_H_A_per_m",
    "curlE_E_V_per_m",
    "curlE_H_A_per_m",
    "native_flux",
    "curlE_flux",
    "native_energy",
    "curlE_energy",
)


class ReplayIdentityError(ValueError):
    """A frozen T3 artifact is missing or is internally inconsistent."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayIdentityError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ReplayIdentityError(f"JSON artifact is not an object: {path}")
    return value


def _require(value: bool, message: str) -> None:
    if not value:
        raise ReplayIdentityError(message)


def _require_mpi8(comm: Any) -> None:
    _require(
        getattr(comm, "size", None) == 8, "Full3D canonical replay requires MPI size 8"
    )


def _artifact(path: Path, label: str) -> dict[str, Any]:
    _require(path.is_file(), f"missing {label}: {path}")
    return {
        "label": label,
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _resolve(root: Path, value: Any) -> Path:
    _require(isinstance(value, str) and bool(value), "artifact path is missing")
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    local = root / candidate
    if local.is_file():
        return local
    repo = Path(__file__).resolve().parents[1] / candidate
    return repo


def _load_old_reference(numeric_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata_path = numeric_dir / "full3d_reference_samples.json"
    metadata = _json(metadata_path)
    archive_path = _resolve(numeric_dir, metadata.get("archive"))
    _require(
        _sha256(archive_path) == metadata.get("archive_sha256"),
        "old reference archive SHA mismatch",
    )
    _require(
        archive_path.stat().st_size == metadata.get("archive_bytes"),
        "old reference archive byte count mismatch",
    )
    try:
        with np.load(archive_path, allow_pickle=False) as archive:
            arrays = {key: np.asarray(archive[key]).copy() for key in archive.files}
    except (OSError, ValueError) as exc:
        raise ReplayIdentityError(
            "cannot load old five-plane reference archive"
        ) from exc
    for key, shape in {"x_nm": (40,), "y_nm": (20,), "z_nm": (5,)}.items():
        value = arrays.get(key)
        _require(
            value is not None and value.shape == shape and value.dtype == np.float64,
            f"old reference {key} shape/dtype mismatch",
        )
        _require(bool(np.isfinite(value).all()), f"old reference {key} is non-finite")
    for key in ("E_V_per_m", "H_A_per_m"):
        value = arrays.get(key)
        _require(
            value is not None
            and value.shape == (5, 20, 40, 3)
            and value.dtype == np.complex128,
            f"old reference {key} shape/dtype mismatch",
        )
        _require(bool(np.isfinite(value).all()), f"old reference {key} is non-finite")
    _require(
        tuple(float(value) for value in arrays["z_nm"]) == FROZEN_PLANES,
        "old reference planes are not the frozen five planes",
    )
    return (
        {
            "metadata": _artifact(metadata_path, "full3d_reference_samples.json"),
            "archive": _artifact(archive_path, "full3d_reference_samples.npz"),
        },
        arrays,
    )


def _canonical_rank_shard(
    root: Path, numeric: Mapping[str, Any], rank: int
) -> tuple[dict[str, Any], Path, str]:
    export = numeric.get("full3d_direct_canonical_export")
    _require(
        isinstance(export, Mapping) and export.get("status") == "completed",
        "Full3D canonical export is incomplete",
    )
    roles = export.get("roles")
    _require(
        isinstance(roles, Mapping) and set(roles) == {"active_trace", "full_fe"},
        "Full3D canonical roles are not active_trace/full_fe",
    )
    full_fe = roles["full_fe"]
    _require(isinstance(full_fe, Mapping), "full_fe canonical descriptor is missing")
    manifest_path = _resolve(root / "numerical_output", full_fe.get("manifest"))
    manifest_sha = full_fe.get("manifest_sha256")
    _require(
        isinstance(manifest_sha, str) and len(manifest_sha) == 64,
        "full_fe manifest SHA is invalid",
    )
    _require(_sha256(manifest_path) == manifest_sha, "full_fe manifest SHA mismatch")
    manifest = _json(manifest_path)
    _require(
        manifest.get("schema_version") == CANONICAL_MANIFEST_SCHEMA,
        "full_fe manifest schema mismatch",
    )
    _require(manifest.get("role") == "full_fe", "full_fe manifest role mismatch")
    _require(
        manifest.get("mpi_size") == 8 and manifest.get("dtype") == "complex128",
        "full_fe manifest MPI/dtype mismatch",
    )
    _require(
        manifest.get("summed_local_duplicate_count") == 0,
        "full_fe manifest reports duplicate keys",
    )
    shards = manifest.get("per_rank_shards")
    _require(
        isinstance(shards, list) and len(shards) == 8,
        "full_fe manifest must contain eight shards",
    )
    ranks = [item.get("rank") for item in shards if isinstance(item, Mapping)]
    filenames = [item.get("filename") for item in shards if isinstance(item, Mapping)]
    _require(
        ranks == list(range(8)) and len(set(filenames)) == 8,
        "full_fe shard ranks or filenames are not unique",
    )
    shard_summary: list[dict[str, Any]] = []
    for item in shards:
        _require(
            isinstance(item.get("file_sha256"), str) and len(item["file_sha256"]) == 64,
            "full_fe shard SHA is invalid",
        )
        _require(
            isinstance(item.get("packet_count"), int)
            and item["packet_count"] > 0
            and item.get("local_duplicate_count", 0) == 0,
            "full_fe shard packet/duplicate metadata is invalid",
        )
        shard_summary.append(
            {
                "rank": int(item["rank"]),
                "filename": str(item["filename"]),
                "file_sha256": item["file_sha256"],
                "packet_count": int(item["packet_count"]),
                "local_duplicate_count": int(item.get("local_duplicate_count", 0)),
            }
        )
    _require(
        sum(item["packet_count"] for item in shard_summary)
        == manifest.get("global_summed_packet_count"),
        "full_fe shard packet counts do not sum to manifest global count",
    )
    shard = shards[rank]
    shard_path = manifest_path.parent / str(shard["filename"])
    return (
        {
            "manifest_artifact": _artifact(manifest_path, "full_fe canonical manifest"),
            "manifest_sha256": manifest_sha,
            "manifest_payload": manifest,
            "shards": shard_summary,
        },
        shard_path,
        str(shard["file_sha256"]),
    )


def _load_replay_authority(root: Path, rank: int) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "run_manifest.json"
    outer_path = root / "run_summary.json"
    numeric_path = root / "numerical_output" / "run_summary.json"
    resolved_path = root / "resolved_config.json"
    input_path = root / "input_original.dat"
    manifest, outer, numeric, resolved = (
        _json(manifest_path),
        _json(outer_path),
        _json(numeric_path),
        _json(resolved_path),
    )
    _require(
        manifest.get("status") == "finished" and manifest.get("exit_status") == 0,
        "T3 run manifest is not finished/exit0",
    )
    _require(
        outer.get("status") == "finished" and outer.get("exit_status") == 0,
        "T3 outer summary is not finished/exit0",
    )
    _require(
        manifest.get("method") == "full3d_direct"
        and manifest.get("resolved_method_adapter") == "task038.full3d_direct",
        "run is not the frozen Full3D direct adapter",
    )
    _require(
        manifest.get("run_id") == T3_RUN_ID, "run_id is not the frozen T3 authority"
    )
    _require(
        manifest.get("mpi_size") == 8 and numeric.get("mpi_size") == 8,
        "T3 Full3D replay requires MPI8",
    )
    for key in ("input_sha256", "resolved_config_sha256", "physical_model_sha256"):
        _require(
            isinstance(manifest.get(key), str) and len(manifest[key]) == 64,
            f"manifest.{key} is invalid",
        )
    _require(
        manifest.get("input_sha256") == T3_INPUT_SHA256,
        "input SHA is not the frozen T3 authority",
    )
    _require(
        manifest.get("physical_model_sha256") == T3_PHYSICAL_MODEL_SHA256,
        "physical model SHA is not the frozen T3 authority",
    )
    _require(
        isinstance(manifest.get("source_sha"), str)
        and len(manifest["source_sha"]) == 40,
        "manifest.source_sha is invalid",
    )
    _require(
        manifest.get("source_sha") == T3_SOURCE_SHA,
        "source SHA is not the frozen T3 authority",
    )
    _require(
        input_path.is_file() and _sha256(input_path) == manifest["input_sha256"],
        "input_original.dat identity mismatch",
    )
    _require(
        resolved_path.is_file()
        and _sha256(resolved_path) == manifest["resolved_config_sha256"],
        "resolved_config.json identity mismatch",
    )
    source_path = root / "source_sha.txt"
    if source_path.is_file():
        _require(
            source_path.read_text(encoding="utf-8").strip() == manifest["source_sha"],
            "source_sha.txt identity mismatch",
        )

    from src.io.input_validation import load_and_resolve

    specification = load_and_resolve(input_path)
    _require(
        specification.input_sha256 == manifest["input_sha256"],
        "resolved input SHA differs from manifest",
    )
    _require(
        specification.physical_model_sha256 == manifest["physical_model_sha256"],
        "resolved physical SHA differs from manifest",
    )
    _require(
        specification.method.get("kind") == "full3d_direct",
        "input method is not full3d_direct",
    )
    _require(
        specification.execution.get("mpi_size") == 8,
        "input execution MPI size is not 8",
    )
    resolved_bytes = canonical_json_bytes(specification.as_jsonable()) + b"\n"
    _require(
        hashlib.sha256(resolved_bytes).hexdigest()
        == manifest["resolved_config_sha256"],
        "input resolution does not reproduce resolved_config.json",
    )
    _require(
        resolved.get("provenance", {}).get("physical_model_sha256")
        == manifest["physical_model_sha256"],
        "resolved config physical provenance mismatch",
    )
    _require(
        numeric.get("case_status") == "completed"
        and numeric.get("official_result") is True,
        "T3 numerical summary is not completed/official",
    )
    _require(
        numeric.get("full3d_direct_canonical_export", {}).get("status") == "completed",
        "T3 numerical canonical summary is incomplete",
    )
    reference, reference_arrays = _load_old_reference(root / "numerical_output")
    canonical, shard_path, shard_sha = _canonical_rank_shard(root, numeric, rank)
    return {
        "root": root,
        "manifest": manifest,
        "outer": outer,
        "numeric": numeric,
        "resolved": resolved,
        "specification": specification,
        "reference": reference,
        "reference_arrays": reference_arrays,
        "canonical": canonical,
        "shard_path": shard_path,
        "shard_sha256": shard_sha,
        "artifacts": {
            "run_manifest": _artifact(manifest_path, "run_manifest.json"),
            "outer_run_summary": _artifact(outer_path, "run_summary.json"),
            "numerical_run_summary": _artifact(
                numeric_path, "numerical_output/run_summary.json"
            ),
            "resolved_config": _artifact(resolved_path, "resolved_config.json"),
            "input_original": _artifact(input_path, "input_original.dat"),
            "full_fe_canonical_manifest": canonical["manifest_artifact"],
            "full_fe_canonical_shards": canonical["shards"],
            **reference,
        },
    }


def _relative_l2(left: np.ndarray, right: np.ndarray) -> float:
    denominator = max(
        float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-30
    )
    return float(np.linalg.norm(left - right) / denominator)


def old_five_plane_identity(
    reconstructed_electric: np.ndarray,
    reconstructed_magnetic: np.ndarray,
    reference_arrays: Mapping[str, np.ndarray],
    reconstructed_coordinates: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> dict[str, Any]:
    """Check the replay against the authoritative five-plane archive."""

    expected_e = np.asarray(reference_arrays["E_V_per_m"])
    expected_h = np.asarray(reference_arrays["H_A_per_m"])
    actual_e = np.asarray(reconstructed_electric)
    actual_h = np.asarray(reconstructed_magnetic)
    actual_coordinates = tuple(np.asarray(value) for value in reconstructed_coordinates)
    coordinates_exact = all(
        np.array_equal(actual_coordinates[index], np.asarray(reference_arrays[name]))
        for index, name in enumerate(("x_nm", "y_nm", "z_nm"))
    )
    e_relative = _relative_l2(actual_e, expected_e)
    h_relative = _relative_l2(actual_h, expected_h)
    result = {
        "coordinates_exact": coordinates_exact,
        "electric_global_relative_l2": e_relative,
        "magnetic_global_relative_l2": h_relative,
        "limit": 1.0e-10,
        "pass": coordinates_exact and e_relative <= 1.0e-10 and h_relative <= 1.0e-10,
    }
    return result


def _diagnostic_grid(
    cfg: Any, z_values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_nm = (
        float(cfg.x_min)
        + (np.arange(40, dtype=np.float64) + 0.5) * float(cfg.period_x) / 40.0
    )
    y_nm = (
        float(cfg.y_min)
        + (np.arange(20, dtype=np.float64) + 0.5) * float(cfg.period_y) / 20.0
    )
    return x_nm, y_nm, np.asarray(z_values, dtype=np.float64)


def _sample_reconstructed_fields(
    cfg: Any, mesh_data: Any, field: Any, z_values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    from dolfinx import fem
    import ufl
    from src.postprocessing.full3d_reference import (
        _sample_distributed_function,
        reference_plane_sides,
    )
    from src.postprocessing.hybrid_field_reconstruction import (
        sampled_plane_flux_and_vacuum_energy,
    )
    from src.postprocessing.postprocess_3d import _interpolation_points

    x_nm, y_nm, z_nm = _diagnostic_grid(cfg, z_values)
    zz, yy, xx = np.meshgrid(z_nm, y_nm, x_nm, indexing="ij")
    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    points_per_plane = len(x_nm) * len(y_nm)
    sides = reference_plane_sides(len(z_nm), points_per_plane)
    dg = fem.functionspace(mesh_data.mesh, ("DG", cfg.visualization_degree, (3,)))
    e_code = fem.Function(dg)
    e_code.interpolate(field)
    e_physical = fem.Function(dg)
    e_physical.x.array[:] = cfg.electric_field_scale_V_per_m * e_code.x.array[:]
    e_physical.x.scatter_forward()
    h_expr = (cfg.magnetic_field_scale_A_per_m / (1j * cfg.k0 * cfg.mu_r)) * ufl.curl(
        field
    )
    h_dg = fem.Function(dg)
    h_dg.interpolate(fem.Expression(h_expr, _interpolation_points(dg)))
    electric = _sample_distributed_function(e_physical, points, sides).reshape(
        (len(z_nm), 20, 40, 3)
    )
    magnetic = _sample_distributed_function(h_dg, points, sides).reshape(
        (len(z_nm), 20, 40, 3)
    )
    flux, energy = sampled_plane_flux_and_vacuum_energy(electric, magnetic)
    return electric, magnetic, flux, energy


def _write_full3d_payload(
    output_dir: Path,
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_path = output_dir / "task039_full3d_h_diagnostic_payload.npz"
    metadata_path = output_dir / "task039_full3d_h_diagnostic_payload.json"
    np.savez(payload_path, **arrays)
    descriptor = {
        "schema": PAYLOAD_SCHEMA,
        "path": payload_path.name,
        "metadata_path": metadata_path.name,
        "keys": list(DIAGNOSTIC_KEYS),
        "archive_sha256": _sha256(payload_path),
        "archive_bytes": payload_path.stat().st_size,
        "arrays": {
            key: {
                "shape": list(np.asarray(value).shape),
                "dtype": str(np.asarray(value).dtype),
                "bytes": int(np.asarray(value).nbytes),
                "sha256": _array_sha256(np.asarray(value)),
                "finite": bool(np.isfinite(value).all()),
            }
            for key, value in arrays.items()
        },
        **dict(metadata),
    }
    metadata_path.write_text(
        json.dumps(descriptor, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    descriptor["metadata_sha256"] = _sha256(metadata_path)
    descriptor["metadata_bytes"] = metadata_path.stat().st_size
    return descriptor


def replay_full3d(
    run_root: str | Path, output_dir: str | Path, comm: Any = None
) -> dict[str, Any]:
    """Rebuild and sample the frozen T3 field on MPI8 without numerical solve."""

    from mpi4py import MPI

    comm = MPI.COMM_WORLD if comm is None else comm
    _require_mpi8(comm)
    authority = _load_replay_authority(Path(run_root), comm.rank)
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d, stage4_axis_plan
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        reconstruct_canonical_full_fe_function,
    )
    from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard
    from src.postprocessing.hybrid_field_reconstruction import (
        element_safe_middle_offsets,
    )

    cfg = simulation_config_3d_from_normalized(authority["specification"].as_jsonable())
    mesh_output = Path(output_dir).resolve() / "mesh_replay"
    mesh_data = build_airbox_mesh_3d(cfg, mesh_output)
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(function_space, mesh_data, cfg)
    try:
        packets = read_canonical_packet_shard(
            authority["shard_path"], authority["shard_sha256"]
        )
        keys = [packet[0] for packet in packets]
        local_verification = {
            "rank": comm.rank,
            "filename": authority["canonical"]["shards"][comm.rank]["filename"],
            "file_sha256": _sha256(authority["shard_path"]),
            "packet_count": len(packets),
            "local_duplicate_count": len(keys) - len(set(keys)),
            "verified": True,
        }
    except (OSError, ValueError, KeyError) as exc:
        packets = ()
        local_verification = {
            "rank": comm.rank,
            "verified": False,
            "error": str(exc),
        }
    shard_verifications = comm.allgather(local_verification)
    _require(
        all(item.get("verified") is True for item in shard_verifications),
        "at least one manifest-declared full_fe shard failed local verification",
    )
    for item in shard_verifications:
        declared = authority["canonical"]["shards"][int(item["rank"])]
        _require(
            item["filename"] == declared["filename"]
            and item["file_sha256"] == declared["file_sha256"]
            and item["packet_count"] == declared["packet_count"]
            and item["local_duplicate_count"] == 0,
            "local full_fe shard verification does not match manifest",
        )
    gathered_shards = shard_verifications
    try:
        field = reconstruct_canonical_full_fe_function(
            function_space, packets, floquet_data
        )
        reconstruction_verification = {
            "rank": comm.rank,
            "verified": True,
        }
    except (KeyError, RuntimeError, ValueError) as exc:
        field = None
        reconstruction_verification = {
            "rank": comm.rank,
            "verified": False,
            "error": str(exc),
        }
    reconstruction_status = comm.allgather(reconstruction_verification)
    _require(
        all(item.get("verified") is True for item in reconstruction_status),
        "at least one rank failed canonical full-FE reconstruction",
    )
    axis_plan = stage4_axis_plan(cfg, comm.size)
    offsets = element_safe_middle_offsets(axis_plan, bottom_z_nm=10.0, top_z_nm=110.0)
    diagnostic_z = np.asarray(
        [10.0, offsets[0]["z_nm"], 30.0, 60.0, 90.0, offsets[1]["z_nm"], 110.0],
        dtype=np.float64,
    )
    old_e, old_h, _, _ = _sample_reconstructed_fields(
        cfg, mesh_data, field, np.asarray(FROZEN_PLANES, dtype=np.float64)
    )
    old_coordinates = _diagnostic_grid(cfg, np.asarray(FROZEN_PLANES, dtype=np.float64))
    old_identity = old_five_plane_identity(
        old_e,
        old_h,
        authority["reference_arrays"],
        old_coordinates,
    )
    old_identity = comm.bcast(old_identity, root=0)
    if not old_identity["pass"]:
        result = {
            "schema": REPLAY_SCHEMA,
            "status": "replay_identity_fail",
            "old_five_plane_identity": old_identity,
            "canonical_shard_verification": gathered_shards,
            "canonical_reconstruction_verification": reconstruction_status,
            "artifacts": authority["artifacts"],
        }
        if comm.rank == 0:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / "replay_identity_fail.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
        return result
    electric, magnetic, flux, energy = _sample_reconstructed_fields(
        cfg, mesh_data, field, diagnostic_z
    )
    if comm.rank != 0:
        return comm.bcast(None, root=0)
    arrays = {
        "x_nm": _diagnostic_grid(cfg, diagnostic_z)[0],
        "y_nm": _diagnostic_grid(cfg, diagnostic_z)[1],
        "z_nm": diagnostic_z,
        "E_V_per_m": electric,
        "H_A_per_m": magnetic,
        "normal_poynting_flux_W_per_m2": flux,
        "vacuum_weighted_sampled_energy_J_per_m3": energy,
    }
    descriptor = _write_full3d_payload(
        Path(output_dir),
        arrays,
        {
            "source": "canonical_full_fe_offline_replay",
            "no_matrix_assembly": True,
            "no_linear_solve": True,
            "mpi_size": 8,
            "plane_roles": [
                "interface_bottom",
                "bottom_element_safe_offset",
                "lower_reference",
                "middle_reference",
                "upper_reference",
                "top_element_safe_offset",
                "interface_top",
            ],
            "offset_provenance": {
                "source": "mesh_element_interior",
                "bottom": offsets[0],
                "top": offsets[1],
            },
            "old_five_plane_identity": old_identity,
            "canonical_shard_verification": gathered_shards,
            "canonical_reconstruction_verification": reconstruction_status,
            "t3_artifacts": authority["artifacts"],
        },
    )
    result = {
        "schema": REPLAY_SCHEMA,
        "status": "qualified",
        "payload": descriptor,
        "old_five_plane_identity": old_identity,
        "t3_artifacts": authority["artifacts"],
    }
    (Path(output_dir) / "replay_summary.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return comm.bcast(result, root=0)


def _load_payload(
    payload_path: Path, metadata_path: Path, hybrid: bool
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    metadata = _json(metadata_path)
    expected_keys = HYBRID_KEYS if hybrid else DIAGNOSTIC_KEYS
    _require(
        metadata.get("keys") == list(expected_keys),
        "diagnostic metadata keys are not the frozen contract",
    )
    _require(
        set(metadata.get("arrays", {})) == set(expected_keys),
        "diagnostic metadata array descriptors are incomplete",
    )
    archive_sha = metadata.get("archive_sha256", metadata.get("sha256"))
    archive_bytes = metadata.get("archive_bytes", metadata.get("bytes"))
    _require(
        _sha256(payload_path) == archive_sha
        and payload_path.stat().st_size == archive_bytes,
        "diagnostic payload archive binding failed",
    )
    try:
        with np.load(payload_path, allow_pickle=False) as archive:
            arrays = {key: np.asarray(archive[key]).copy() for key in archive.files}
    except (OSError, ValueError) as exc:
        raise ReplayIdentityError("cannot load diagnostic payload") from exc
    _require(
        tuple(arrays) == expected_keys, "diagnostic payload keys do not match metadata"
    )
    for key, info in metadata.get("arrays", {}).items():
        value = arrays.get(key)
        _require(
            value is not None
            and list(value.shape) == info.get("shape")
            and str(value.dtype) == info.get("dtype"),
            f"diagnostic array {key} shape/dtype binding failed",
        )
        _require(
            _array_sha256(value) == info.get("sha256")
            and bool(np.isfinite(value).all()) == bool(info.get("finite")),
            f"diagnostic array {key} hash/finite binding failed",
        )
    if hybrid:
        _require(
            metadata.get("schema") == "task039.hybrid-h-diagnostic.v1",
            "Hybrid H diagnostic metadata schema is invalid",
        )
        _require(
            metadata.get("curl_source")
            == "complete_reconstructed_field_analytic_or_fe",
            "Hybrid H diagnostic curl source is invalid",
        )
    else:
        _require(
            metadata.get("schema") == PAYLOAD_SCHEMA,
            "Full3D H diagnostic metadata schema is invalid",
        )
        _require(
            metadata.get("source") == "canonical_full_fe_offline_replay",
            "Full3D H diagnostic source is invalid",
        )
        _require(
            metadata.get("no_matrix_assembly") is True
            and metadata.get("no_linear_solve") is True,
            "Full3D replay safety flags are invalid",
        )
    _validate_plane_payload(metadata, arrays, hybrid)
    return metadata, arrays


def _validate_plane_payload(
    metadata: Mapping[str, Any], arrays: Mapping[str, np.ndarray], hybrid: bool
) -> None:
    _require(
        metadata.get("plane_roles") == list(H_PLANE_ROLES),
        "diagnostic plane roles are not the frozen seven-plane contract",
    )
    provenance = metadata.get("offset_provenance")
    _require(
        isinstance(provenance, Mapping)
        and provenance.get("source") == "mesh_element_interior",
        "diagnostic offset provenance source is invalid",
    )
    for side, role in (
        ("bottom", "bottom_element_safe_offset"),
        ("top", "top_element_safe_offset"),
    ):
        evidence = provenance.get(side)
        _require(
            isinstance(evidence, Mapping),
            f"diagnostic {side} offset provenance is missing",
        )
        _require(
            evidence.get("role") == role
            and evidence.get("source") == "mesh_element_interior_midpoint",
            f"diagnostic {side} offset role/source is invalid",
        )
        _require(
            isinstance(evidence.get("element_id"), (str, int)),
            f"diagnostic {side} element identity is missing",
        )
        distance = evidence.get("distance_from_interface_nm")
        _require(
            isinstance(distance, (int, float))
            and not isinstance(distance, bool)
            and np.isfinite(distance)
            and distance > 0.0,
            f"diagnostic {side} offset distance is invalid",
        )
    for key, shape, dtype in (
        ("x_nm", (40,), np.float64),
        ("y_nm", (20,), np.float64),
        ("z_nm", (7,), np.float64),
    ):
        value = arrays[key]
        _require(
            value.shape == shape
            and value.dtype == dtype
            and bool(np.isfinite(value).all()),
            f"diagnostic coordinate {key} shape/dtype/finite contract failed",
        )
    z = arrays["z_nm"]
    _require(
        np.isclose(z[0], 10.0)
        and np.isclose(z[-1], 110.0)
        and bool(np.all(np.diff(z) > 0.0)),
        "diagnostic z planes are not ordered 10/offset/30/60/90/offset/110",
    )
    _require(
        np.isclose(z[1], provenance["bottom"]["z_nm"])
        and np.isclose(z[5], provenance["top"]["z_nm"]),
        "diagnostic z planes do not match offset provenance",
    )
    field_names = (
        ("native_E_V_per_m", "native_H_A_per_m", "curlE_E_V_per_m", "curlE_H_A_per_m")
        if hybrid
        else ("E_V_per_m", "H_A_per_m")
    )
    for key in field_names:
        value = arrays[key]
        _require(
            value.shape == (7, 20, 40, 3)
            and value.dtype == np.complex128
            and bool(np.isfinite(value).all()),
            f"diagnostic field {key} shape/dtype/finite contract failed",
        )
    scalar_names = (
        ("native_flux", "curlE_flux", "native_energy", "curlE_energy")
        if hybrid
        else (
            "normal_poynting_flux_W_per_m2",
            "vacuum_weighted_sampled_energy_J_per_m3",
        )
    )
    for key in scalar_names:
        value = arrays[key]
        _require(
            value.shape == (7,)
            and value.dtype == np.float64
            and bool(np.isfinite(value).all()),
            f"diagnostic scalar {key} shape/dtype/finite contract failed",
        )


def _path_mapping(
    metadata: Mapping[str, Any], arrays: Mapping[str, np.ndarray], path: str
) -> dict[str, Any]:
    coordinates = {key: arrays[key] for key in ("x_nm", "y_nm", "z_nm")}
    if path == "hybrid":
        return {
            "coordinates": coordinates,
            "plane_roles": metadata["plane_roles"],
            "offset_provenance": metadata["offset_provenance"],
            "fields": {
                "E_V_per_m": arrays["native_E_V_per_m"],
                "H_A_per_m": arrays["native_H_A_per_m"],
            },
            "flux": arrays["native_flux"],
            "energy": arrays["native_energy"],
        }
    return {
        "coordinates": coordinates,
        "plane_roles": metadata["plane_roles"],
        "offset_provenance": metadata["offset_provenance"],
        "fields": {"E_V_per_m": arrays["E_V_per_m"], "H_A_per_m": arrays["H_A_per_m"]},
        "flux": arrays["normal_poynting_flux_W_per_m2"],
        "energy": arrays["vacuum_weighted_sampled_energy_J_per_m3"],
    }


def compare_payloads(
    hybrid_payload: str | Path,
    full3d_payload: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Compare native/curl-E Hybrid paths with the replayed Full3D path."""

    hybrid_path = Path(hybrid_payload).resolve()
    full_path = Path(full3d_payload).resolve()
    hybrid_meta, hybrid_arrays = _load_payload(
        hybrid_path, hybrid_path.with_suffix(".json"), True
    )
    full_meta, full_arrays = _load_payload(
        full_path, full_path.with_suffix(".json"), False
    )
    _require(
        hybrid_meta["plane_roles"] == full_meta["plane_roles"]
        and hybrid_meta["offset_provenance"] == full_meta["offset_provenance"],
        "Hybrid and Full3D plane roles/provenance differ",
    )
    for key in ("x_nm", "y_nm", "z_nm"):
        _require(
            np.array_equal(hybrid_arrays[key], full_arrays[key]),
            f"Hybrid and Full3D {key} coordinates differ",
        )
    comparison = diagnose_h_paths(
        _path_mapping(hybrid_meta, hybrid_arrays, "hybrid"),
        {
            **_path_mapping(hybrid_meta, hybrid_arrays, "hybrid"),
            "fields": {
                "E_V_per_m": hybrid_arrays["curlE_E_V_per_m"],
                "H_A_per_m": hybrid_arrays["curlE_H_A_per_m"],
            },
            "flux": hybrid_arrays["curlE_flux"],
            "energy": hybrid_arrays["curlE_energy"],
            "curl_source": hybrid_meta.get("curl_source"),
        },
        _path_mapping(full_meta, full_arrays, "full3d"),
    )
    result = {
        "schema": "task039.h-diagnostic-comparison.v1",
        "source": "diagnose_h_paths",
        "hybrid_artifacts": {
            "payload": _artifact(hybrid_path, "Hybrid H diagnostic payload"),
            "metadata": _artifact(
                hybrid_path.with_suffix(".json"), "Hybrid H diagnostic metadata"
            ),
        },
        "full3d_artifacts": {
            "payload": _artifact(full_path, "Full3D H diagnostic payload"),
            "metadata": _artifact(
                full_path.with_suffix(".json"), "Full3D H diagnostic metadata"
            ),
        },
        "comparison": comparison,
        "classification": comparison["classification"],
        "diagnostic_complete": comparison["diagnostic_complete"],
        "pass": comparison["pass"],
    }
    if output is not None:
        output_path = Path(output)
        output_path.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        result["output"] = {
            "path": str(output_path),
            "sha256": _sha256(output_path),
            "bytes": output_path.stat().st_size,
        }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task39 offline Full3D H diagnostic")
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay-full3d")
    replay.add_argument("--run-root", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--hybrid-payload", type=Path, required=True)
    compare.add_argument("--full3d-payload", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "replay-full3d":
            replay_full3d(args.run_root, args.output)
        else:
            compare_payloads(args.hybrid_payload, args.full3d_payload, args.output)
    except (ReplayIdentityError, ValueError, OSError) as exc:
        print(f"task039_h_field_diagnostic: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
