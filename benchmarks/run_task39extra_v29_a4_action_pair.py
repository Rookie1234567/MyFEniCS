"""Qualify one complete p4 A4 action against preserved V28 solve vectors."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


EXPECTED_INPUT_SHA256 = "447519b48c87360eb5b6c69d56f61196e91a2e14e0a368522dddec48c5c50ebc"
EXPECTED_PHYSICAL_MODEL_SHA256 = "0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6"
EXPECTED_MODE_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
PACKET_NAME = re.compile(
    r"^v28q4_p4_repair_pc(?P<pc>\d+)_logical(?P<logical>\d+)_(?P<phase>raw|correction_1)\.json$"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def _json_default(value):
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return {"shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _memory_snapshot() -> dict[str, int | None]:
    status: dict[str, int | None] = {"rss_bytes": None, "hwm_bytes": None, "pss_bytes": None}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"VmRSS", "VmHWM"}:
            status[{"VmRSS": "rss_bytes", "VmHWM": "hwm_bytes"}[key]] = int(value.split()[0]) * 1024
    try:
        for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
            key, _, value = line.partition(":")
            if key == "Pss":
                status["pss_bytes"] = int(value.split()[0]) * 1024
                break
    except OSError:
        pass
    return status


def _load_packets(packet_root: Path) -> list[dict]:
    grouped: dict[tuple[int, int], dict[str, Path]] = {}
    for path in packet_root.glob("v28q4_p4_repair_pc*_logical*_*.json"):
        match = PACKET_NAME.fullmatch(path.name)
        if match is None:
            continue
        key = (int(match.group("pc")), int(match.group("logical")))
        grouped.setdefault(key, {})[match.group("phase")] = path
    selected = [
        (key, pair)
        for key, pair in sorted(grouped.items())
        if {"raw", "correction_1"}.issubset(pair)
    ]
    if len(selected) != 6:
        raise ValueError(f"expected the six saved V28 raw/correction pairs, found {len(selected)}")

    packets = []
    for (pc, logical), pair in selected:
        for phase in ("raw", "correction_1"):
            record_path = pair[phase]
            record = json.loads(record_path.read_text())
            if record.get("schema") != "task039extra.v24.p4-repair-vector.v1":
                raise ValueError(f"unexpected p4 vector packet schema: {record_path.name}")
            if record.get("phase") != phase or int(record.get("pc_apply_sequence", -1)) != pc:
                raise ValueError(f"packet identity mismatch: {record_path.name}")
            if int(record.get("logical_call_sequence", -1)) != logical:
                raise ValueError(f"logical call identity mismatch: {record_path.name}")
            array_record = record.get("arrays", {})
            archive_path = record_path.with_suffix(".npz")
            if Path(array_record.get("path", "")).resolve() != archive_path.resolve():
                raise ValueError(f"archive path mismatch: {record_path.name}")
            archive_sha = _file_sha256(archive_path)
            if archive_sha != array_record.get("sha256"):
                raise ValueError(f"archive SHA256 mismatch: {record_path.name}")
            for key in ("g", "correction", "native_applied", "native_A4_residual"):
                item = record.get(key, {})
                name = item.get("array_key")
                if not isinstance(name, str) or item.get("shape") != [201520]:
                    raise ValueError(f"missing or malformed {key} manifest in {record_path.name}")
            packets.append({
                "packet_id": record_path.stem,
                "phase": phase,
                "pc_apply_sequence": pc,
                "logical_call": int(record["logical_call"]),
                "record_sha256": _file_sha256(record_path),
                "archive_sha256": archive_sha,
                "record_path": str(record_path),
                "archive_path": str(archive_path),
                "record": record,
            })
    return packets


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny))


def _load_packet_arrays(packet: dict) -> dict[str, np.ndarray]:
    record = packet["record"]
    with np.load(packet["archive_path"], allow_pickle=False) as archive:
        arrays = {
            key: np.asarray(archive[record[key]["array_key"]], dtype=np.complex128).copy()
            for key in ("g", "correction", "native_applied", "native_A4_residual")
        }
    for key, values in arrays.items():
        if values.shape != (201520,) or not np.isfinite(values).all():
            raise ValueError(f"malformed or non-finite {key} in {packet['packet_id']}")
    return arrays


def _apply(action, source, target) -> tuple[np.ndarray, float, float]:
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    action.apply(source, target)
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    return np.asarray(target.array, dtype=np.complex128).copy(), wall, cpu


def run(args: argparse.Namespace) -> dict:
    from mpi4py import MPI
    from petsc4py import PETSc
    import basix
    import dolfinx
    import importlib.metadata

    if (
        os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1"
        or not os.path.samefile(sys.executable, ".venv/bin/python")
        or PETSc.ScalarType is not np.complex128
        or PETSc.IntType is not np.int32
        or MPI.COMM_WORLD.size != 1
    ):
        raise RuntimeError("V29 A4 pair requires the qualified MPI1 complex128 ABI")
    thread_env = {
        key: os.environ.get(key)
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    }
    if set(thread_env.values()) != {"1"}:
        raise RuntimeError(f"V29 A4 pair requires one thread in every library: {thread_env}")

    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.physical_macro_controls import _mapping_identity_sha256
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.physical_equivalent_fast import build_packed_physical_action

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {args.output}")
    baseline_record = json.loads(args.baseline_record.read_text())
    baseline_run = baseline_record["run"]
    if baseline_record.get("profile") != "physical_p6_trace_fused_kernel_v28":
        raise ValueError("baseline record is not the reviewed V28 profile")
    if baseline_run.get("physical_model_sha256") != EXPECTED_PHYSICAL_MODEL_SHA256:
        raise ValueError("baseline physical-model identity changed")

    specification = load_and_resolve(args.input)
    if specification.input_sha256 != EXPECTED_INPUT_SHA256:
        raise ValueError("V28 input SHA256 differs from the preserved baseline")
    if specification.physical_model_sha256 != EXPECTED_PHYSICAL_MODEL_SHA256:
        raise ValueError("V28 input physical-model identity differs from the preserved baseline")
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    packets = _load_packets(args.packet_root)

    result = {
        "schema": "task039extra.v29.p2-a4-action-pair.v1",
        "classification": "A4_ACTION_PAIR_ONLY_NO_SOLVE_NO_GLOBAL_P4_MATRIX_NO_P4_FACTOR",
        "source_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "source_files": {},
        "baseline": {
            "run_id": baseline_run["run_id"],
            "source_sha": baseline_run["source_sha"],
            "input_sha256": baseline_run["input_sha256"],
            "physical_model_sha256": baseline_run["physical_model_sha256"],
            "ordered_modes_sha256": baseline_run["ordered_modes_sha256"],
            "record_sha256": _file_sha256(args.baseline_record),
        },
        "input": {"path": str(args.input.resolve()), "sha256": specification.input_sha256,
                  "physical_model_sha256": specification.physical_model_sha256},
        "runtime": {
            "python": sys.executable,
            "petsc_scalar_type": str(PETSc.ScalarType),
            "petsc_int_type": str(PETSc.IntType),
            "dolfinx": dolfinx.__version__,
            "basix": basix.__version__,
            "ffcx": importlib.metadata.version("fenics-ffcx"),
            "mpi_library": MPI.Get_library_version().strip(),
            "mpi_ranks": int(MPI.COMM_WORLD.size),
            "threads": thread_env,
        },
        "qualification": {
            "complete_action_relative_limit": 1.0e-10,
            "residual_difference_over_original_g_limit": 1.0e-11,
            "repeats_per_saved_state": int(args.repeats),
            "packet_count": len(packets),
            "global_p4_matrix_built": False,
            "p4_factor_built": False,
        },
        "memory_scope": "single MPI1 process VmRSS/PSS and process VmHWM; not process-tree peak",
        "memory_snapshots": {"before_setup": _memory_snapshot()},
        "packets": [],
    }

    for relative_path in (
        "benchmarks/run_task39extra_v29_a4_action_pair.py",
        "src/solvers/physical_equivalent_fast.py",
        "src/solvers/fullspace_partial_assembly.py",
        "src/solvers/fullspace_fused_split_volume.py",
        "src/solvers/fullspace_physical_action.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
    ):
        result["source_files"][relative_path] = _file_sha256(Path(relative_path))

    setup_started, setup_cpu = time.perf_counter(), time.process_time()
    levels = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6, 4), include_positive_coefficients=False)
    cell_count = int(levels["mesh"].topology.index_map(levels["mesh"].topology.dim).size_global)
    if cell_count != 990:
        raise ValueError(f"expected the preserved 990-cell mesh, got {cell_count}")
    quadrature, integral_records = fine_volume_quadrature_metadata(levels, cfg)
    modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
    if mode_sha != EXPECTED_MODE_SHA256 or len(modes) != 80:
        raise ValueError("ordered p4 DtN mode identity differs from the V28 baseline")
    mode_inventory = (modes, mode_rows, mode_sha)
    p4 = candidate = None
    try:
        p4 = build_same_mesh_physical_action(
            levels,
            cfg,
            4,
            mode_inventory=mode_inventory,
            volume_quadrature_metadata=quadrature,
        )
        local_rows = int(levels["spaces"][4].dofmap.index_map.size_local)
        global_rows = int(levels["spaces"][4].dofmap.index_map.size_global)
        if local_rows != 201520 or global_rows != 201520:
            raise ValueError(f"expected 201520 p4 rows on MPI1, got local/global {local_rows}/{global_rows}")
        map_identity = native_map_arrays(levels["spaces"][4], levels["floquets"][4])
        p4_map_sha = _mapping_identity_sha256(map_identity)
        result["setup"] = {
            "wall_seconds": time.perf_counter() - setup_started,
            "cpu_seconds": time.process_time() - setup_cpu,
            "cell_count": cell_count,
            "p4_rows": global_rows,
            "mode_sha256": mode_sha,
            "mode_count": len(modes),
            "p4_map_sha256": p4_map_sha,
            "fine_volume_quadrature_metadata": quadrature,
            "integral_records": integral_records,
            "native_p4_action_audit": dict(p4["physical_action"].audit),
        }
        result["memory_snapshots"]["after_native_p4_setup"] = _memory_snapshot()

        candidate_started, candidate_cpu = time.perf_counter(), time.process_time()
        candidate = build_packed_physical_action(
            {"levels": levels, "p4": p4},
            cfg,
            degree=4,
            contiguous_work=True,
            preallocated_work=False,
            sum_factorized_work=True,
            fuse_components=True,
        )
        result["candidate_setup"] = {
            "wall_seconds": time.perf_counter() - candidate_started,
            "cpu_seconds": time.process_time() - candidate_cpu,
            "facts": candidate["facts"],
        }
        result["memory_snapshots"]["after_candidate_setup"] = _memory_snapshot()

        native_component = p4["volume_action"].component_actions["curl"]
        source = native_component.matrix.createVecRight()
        target = source.duplicate()
        action_timing: dict[str, list[float]] = {"native_wall": [], "candidate_wall": [],
                                                  "native_cpu": [], "candidate_cpu": []}
        max_action_relative = 0.0
        max_residual_delta = 0.0
        max_native_saved_action_relative = 0.0
        max_native_saved_residual_delta = 0.0
        all_inputs_unchanged = True
        try:
            warm_arrays = _load_packet_arrays(packets[0])
            source.array[:] = warm_arrays["correction"]
            warm_source_before = source.array.copy()
            warm_native, warm_native_wall, warm_native_cpu = _apply(
                p4["physical_action"], source, target
            )
            warm_candidate, warm_candidate_wall, warm_candidate_cpu = _apply(
                candidate["physical_action"], source, target
            )
            result["warmup"] = {
                "packet_id": packets[0]["packet_id"],
                "native_wall_seconds": warm_native_wall,
                "candidate_wall_seconds": warm_candidate_wall,
                "native_cpu_seconds": warm_native_cpu,
                "candidate_cpu_seconds": warm_candidate_cpu,
                "action_relative_difference": _relative(warm_candidate, warm_native),
                "input_unchanged": bool(np.array_equal(source.array, warm_source_before)),
                "included_in_pair_medians": False,
            }
            del warm_arrays, warm_source_before, warm_native, warm_candidate

            for packet_index, packet in enumerate(packets, start=1):
                record = packet["record"]
                arrays = _load_packet_arrays(packet)
                g = arrays["g"]
                correction = arrays["correction"]
                saved_native = arrays["native_applied"]
                saved_residual = arrays["native_A4_residual"]
                slaves = np.asarray(levels["floquets"][4].mpc.slaves, dtype=np.int64)
                if slaves.size and (np.count_nonzero(g[slaves]) or np.count_nonzero(correction[slaves])):
                    raise ValueError(f"saved packet is not strict slave-zero: {packet['packet_id']}")
                g_norm = float(np.linalg.norm(g))
                if g_norm == 0.0:
                    raise ValueError(f"saved original A4 right-hand side is zero: {packet['packet_id']}")
                source.array[:] = correction
                source_before = source.array.copy()

                native_values, native_wall, native_cpu = _apply(p4["physical_action"], source, target)
                candidate_values, candidate_wall, candidate_cpu = _apply(
                    candidate["physical_action"], source, target
                )
                action_relative = _relative(candidate_values, native_values)
                residual_delta = float(np.linalg.norm((g - candidate_values) - (g - native_values)) / g_norm)
                native_saved_action_relative = _relative(native_values, saved_native)
                native_saved_residual_delta = float(
                    np.linalg.norm((g - native_values) - saved_residual) / g_norm
                )
                max_action_relative = max(max_action_relative, action_relative)
                max_residual_delta = max(max_residual_delta, residual_delta)
                max_native_saved_action_relative = max(max_native_saved_action_relative, native_saved_action_relative)
                max_native_saved_residual_delta = max(max_native_saved_residual_delta, native_saved_residual_delta)
                repeats = []
                for repeat in range(args.repeats):
                    order = (("native", p4["physical_action"]), ("candidate", candidate["physical_action"]))
                    if repeat % 2:
                        order = tuple(reversed(order))
                    observed = {}
                    for name, action in order:
                        values, wall, cpu = _apply(action, source, target)
                        observed[name] = {"values": values, "wall": wall, "cpu": cpu}
                        action_timing[f"{name}_wall"].append(wall)
                        action_timing[f"{name}_cpu"].append(cpu)
                    repeat_action_relative = _relative(observed["candidate"]["values"], observed["native"]["values"])
                    repeat_residual_delta = float(
                        np.linalg.norm(observed["candidate"]["values"] - observed["native"]["values"]) / g_norm
                    )
                    max_action_relative = max(max_action_relative, repeat_action_relative)
                    max_residual_delta = max(max_residual_delta, repeat_residual_delta)
                    repeats.append({
                        "repeat": repeat + 1,
                        "order": [name for name, _ in order],
                        "native_wall_seconds": observed["native"]["wall"],
                        "candidate_wall_seconds": observed["candidate"]["wall"],
                        "native_cpu_seconds": observed["native"]["cpu"],
                        "candidate_cpu_seconds": observed["candidate"]["cpu"],
                        "action_relative_difference": repeat_action_relative,
                        "residual_difference_over_original_g": repeat_residual_delta,
                    })
                    del observed
                all_inputs_unchanged &= bool(np.array_equal(source.array, source_before))
                packet["qualification"] = {
                    "original_g_norm": g_norm,
                    "qualification_native_wall_seconds": native_wall,
                    "qualification_candidate_wall_seconds": candidate_wall,
                    "saved_native_relative_residual": float(record["native_A4_relative_residual"]),
                    "native_vs_saved_action_relative": native_saved_action_relative,
                    "native_vs_saved_residual_difference_over_original_g": native_saved_residual_delta,
                    "candidate_vs_native_action_relative": action_relative,
                    "candidate_vs_native_residual_difference_over_original_g": residual_delta,
                    "native_residual_norm": float(np.linalg.norm(g - native_values)),
                    "candidate_residual_norm": float(np.linalg.norm(g - candidate_values)),
                    "native_output_sha256": _array_sha256(native_values),
                    "candidate_output_sha256": _array_sha256(candidate_values),
                    "repeats": repeats,
                }
                result["packets"].append({key: packet[key] for key in (
                    "packet_id", "phase", "pc_apply_sequence", "logical_call",
                    "record_sha256", "archive_sha256", "qualification",
                )})
                print(
                    f"A4_PAIR {packet_index}/{len(packets)} {packet['packet_id']} "
                    f"native={native_wall:.3f}s candidate={candidate_wall:.3f}s "
                    f"action_rel={action_relative:.3e} residual_delta/g={residual_delta:.3e}",
                    flush=True,
                )
                del arrays, g, correction, saved_native, saved_residual, native_values, candidate_values
        finally:
            target.destroy()
            source.destroy()

        result["qualification"].update({
            "max_complete_action_relative_difference": max_action_relative,
            "max_residual_difference_over_original_g": max_residual_delta,
            "max_native_vs_saved_action_relative_difference": max_native_saved_action_relative,
            "max_native_vs_saved_residual_difference_over_original_g": max_native_saved_residual_delta,
            "all_inputs_unchanged": all_inputs_unchanged,
            "complete_action_pass": max_action_relative <= 1.0e-10,
            "residual_accuracy_pass": max_residual_delta <= 1.0e-11,
            "saved_native_identity_pass": max_native_saved_action_relative <= 1.0e-10
            and max_native_saved_residual_delta <= 1.0e-11,
        })
        native_times = action_timing["native_wall"]
        candidate_times = action_timing["candidate_wall"]
        result["timing"] = {
            "native_action_median_wall_seconds": float(np.median(native_times)),
            "candidate_action_median_wall_seconds": float(np.median(candidate_times)),
            "candidate_over_native_median_wall": float(np.median(candidate_times) / np.median(native_times)),
            "native_action_median_cpu_seconds": float(np.median(action_timing["native_cpu"])),
            "candidate_action_median_cpu_seconds": float(np.median(action_timing["candidate_cpu"])),
            "candidate_over_native_median_cpu": float(
                np.median(action_timing["candidate_cpu"]) / np.median(action_timing["native_cpu"])
            ),
            "samples_per_implementation": len(native_times),
        }
        result["qualification"]["candidate_speedup_observed"] = bool(
            result["timing"]["candidate_over_native_median_wall"] < 1.0
        )
        result["qualification"]["adopt_candidate"] = bool(
            result["qualification"]["complete_action_pass"]
            and result["qualification"]["residual_accuracy_pass"]
            and result["qualification"]["saved_native_identity_pass"]
            and all_inputs_unchanged
            and result["qualification"]["candidate_speedup_observed"]
        )
        result["memory_snapshots"]["after_all_action_pairs"] = _memory_snapshot()
    finally:
        if candidate is not None:
            candidate["physical_action"].destroy()
        if p4 is not None:
            destroy_same_mesh_physical_action(p4)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, default=_json_default) + "\n")
    temporary.replace(args.output)
    print(f"A4_PAIR_RESULT {args.output} adopt_candidate={result['qualification']['adopt_candidate']}", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--baseline-record", type=Path, required=True)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats not in (2, 3):
        parser.error("--repeats must be 2 or 3; the reviewed batch uses 3")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
