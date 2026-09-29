"""Two explicit material-independent checks through the existing shared runner."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.io.neural_fe_interface import DESIGN_PATH, load_interface
from src.runners.task042_shared import ARTIFACTS, write_json


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometry_stage(design, artifact):
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.neural_micro_pilot import air_orders, hexa_inventory
    from src.runners.task042_experiment import thread_qualification
    from src.solvers.neural_trace_dolfinx import (
        build_packet,
        interpolation_checks,
        pilot_space,
    )

    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
    ):
        raise RuntimeError("qualified MPI1 complex128/int64 required")
    budget = {
        "status": "INTERFACE_ONLY_CAPACITY_PASS",
        "numerical_payload_upper_bytes": 512 * 2**20,
        "library_compiler_workspace_allowance_bytes": 2 * 2**30,
        "total_interface_prediction_bytes": int(2.5 * 2**30),
        "tree_hard_bytes": 16 * 2**30,
        "scope": "384-cell p3 mesh/MPC plus q15/q30 moments; no S, FE factors or physical ports",
        "physical_operator_capacity": "UNKNOWN_MATERIAL_PORT_INVENTORY_BLOCKED",
        "candidate_reference_inventory": [hexa_inventory((8, 6, 8), p) for p in (3, 4)],
        "upper_objects": [
            "two moment packets <=64MiB",
            "orientation matrices <=32MiB",
            "custom element build/temporary <=128MiB",
            "mesh/MPC/field buffers <=128MiB",
            "coordinate/geometry evidence <=16MiB",
            "remaining packet copies <=144MiB",
        ],
    }
    write_json(artifact / "capacity_before_allocation.json", budget)
    began = time.perf_counter()
    cfg, data, space, centers, tags, notch, axes = pilot_space(design)
    mesh_seconds = time.perf_counter() - began
    began = time.perf_counter()
    floquet = build_double_floquet_mpc(space, data, cfg)
    mpc_seconds = time.perf_counter() - began
    packets, checks, packet_times = {}, {}, {}
    for quadrature in (15, 30):
        began = time.perf_counter()
        packet, witness = build_packet(space, floquet.mpc, quadrature)
        checks[quadrature] = interpolation_checks(packet, witness, floquet.mpc)
        if checks[quadrature]["status"] != "PASS":
            raise RuntimeError(
                f"independent interpolation/MPC q{quadrature} failed: {checks[quadrature]}"
            )
        path = artifact / f"packet_q{quadrature}.npz"
        np.savez(path, **packet)
        packets[str(quadrature)] = dict(
            path=str(path),
            sha256=file_hash(path),
            payload_bytes=sum(a.nbytes for a in packet.values()),
            file_bytes=path.stat().st_size,
        )
        packet_times[str(quadrature)] = time.perf_counter() - began
    canonical = sorted(
        [
            dict(center=np.round(center, 13).tolist(), tag=int(tag), notch=bool(edited))
            for center, tag, edited in zip(centers, tags, notch, strict=True)
        ],
        key=lambda row: row["center"],
    )
    vertices = sorted(np.round(data.mesh.geometry.x, 13).tolist())

    def varies(axis):
        groups = {}
        for center, tag in zip(centers, tags, strict=True):
            groups.setdefault(tuple(np.round(np.delete(center, axis), 13)), set()).add(
                int(tag)
            )
        return any(len(values) > 1 for values in groups.values())

    geometry = dict(
        status="GEOMETRY_ONLY_MEASURED",
        optical_material_status="MATERIAL_0P7NM_BLOCKED",
        cells=len(centers),
        full_fe_rows=space.dofmap.index_map.size_global,
        trace_inventory=hexa_inventory((8, 6, 8), 3),
        reference_p4_inventory="derived only, not constructed",
        axes=[axis.tolist() for axis in axes],
        tag_counts={
            str(tag): int(np.count_nonzero(tags == tag)) for tag in np.unique(tags)
        },
        notch_cells=int(np.count_nonzero(notch)),
        y_nonseparable=varies(1),
        z_nonseparable=varies(2),
        facet_counts={
            str(tag): int(np.count_nonzero(data.facet_tags.values == tag))
            for tag in np.unique(data.facet_tags.values)
        },
        canonical_mesh_sha256=hashlib.sha256(
            json.dumps(vertices, sort_keys=True).encode()
        ).hexdigest(),
        canonical_geometry_tags_sha256=hashlib.sha256(
            json.dumps(canonical, sort_keys=True).encode()
        ).hexdigest(),
        physical_operator_sha256=None,
        full_channel_inventory=air_orders(design),
        mpc=dict(
            slaves=floquet.num_constraints,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        ),
        finite_element_operator_constructed=False,
    )
    if (
        len(centers) != 384
        or geometry["full_fe_rows"] != 34050
        or not all(
            [
                geometry["y_nonseparable"],
                geometry["z_nonseparable"],
                geometry["notch_cells"] == 8,
            ]
        )
    ):
        raise RuntimeError(f"actual geometry inventory mismatch: {geometry}")
    write_json(artifact / "canonical_cells.json", canonical)
    write_json(artifact / "geometry.json", geometry)
    return dict(
        status="INTERFACE_CHECK_COMPLETE",
        material_status="MATERIAL_0P7NM_BLOCKED",
        geometry=geometry,
        interpolation_checks=checks,
        packets=packets,
        actual_blas_pools=thread_qualification(),
        preallocation=budget,
        costs_exclusive_seconds=dict(
            mesh_and_space=mesh_seconds,
            floquet_mpc=mpc_seconds,
            packets_interpolation_io=packet_times,
        ),
        real_S_constructed=False,
        global_factor_constructed=False,
        local_FE_factors_constructed=False,
        private_audit_CSR=False,
        reference_loaded=False,
        old_artifacts_loaded=False,
        hidden_fallback=False,
    )


def ml_stage(design, artifact, source):
    import torch

    from src.solvers.neural_trace_checks import check_neural_interface
    from src.solvers.neural_trace_torch import qualify_threads

    threads = qualify_threads()
    parent = ARTIFACTS / "v6" / "V6-FE-INTERFACE"
    index = json.loads((parent / "interface_result.json").read_text())
    if index["source_sha"] != source or index["design_sha256"] != file_hash(
        DESIGN_PATH
    ):
        raise ValueError("FE/ML source or design identity mismatch")
    packets = {}
    for quadrature, record in index["packets"].items():
        path = Path(record["path"]).resolve()
        if not path.is_relative_to(parent) or file_hash(path) != record["sha256"]:
            raise ValueError("packet path/hash mismatch")
        with np.load(path, allow_pickle=False) as contents:
            packets[int(quadrature)] = {
                key: np.array(contents[key]) for key in contents.files
            }
    began = time.perf_counter()
    checks, initial, witness = check_neural_interface(design, packets)
    elapsed = time.perf_counter() - began
    torch.save(initial, artifact / "untrained_zero_initial.pt")
    torch.save(witness, artifact / "nonzero_interface_witness.pt")
    libraries = sorted(
        {
            line.split()[-1]
            for line in Path("/proc/self/maps").read_text().splitlines()
            if "/" in line
            and any(
                name in line.lower()
                for name in ("petsc", "mpi", "openblas", "libtorch", "libgomp")
            )
        }
    )
    if any("petsc" in path.lower() or "libmpi" in path.lower() for path in libraries):
        raise RuntimeError("FE ABI libraries appeared in isolated ML process")
    if checks["status"] != "PASS":
        write_json(artifact / "failed_checks.json", checks)
        raise RuntimeError("bounded nonphysical gradient/interface Gate failed")
    return dict(
        status="INTERFACE_CHECK_COMPLETE",
        material_status="MATERIAL_0P7NM_BLOCKED",
        checks=checks,
        threads=threads,
        loaded_library_paths=libraries,
        checking_wall_seconds=elapsed,
        initialization=dict(
            path=str(artifact / "untrained_zero_initial.pt"),
            sha256=file_hash(artifact / "untrained_zero_initial.pt"),
        ),
        nonzero_witness=dict(
            path=str(artifact / "nonzero_interface_witness.pt"),
            sha256=file_hash(artifact / "nonzero_interface_witness.pt"),
        ),
        real_S_constructed=False,
        global_factor_constructed=False,
        reference_loaded=False,
        candidate_training_started=False,
        optimizer_updates=0,
        hidden_fallback=False,
    )


def main():
    specification = load_interface(sys.argv[1])
    directory = Path(sys.argv[2]).resolve()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = json.loads((directory / "run_manifest.json").read_text())
    if source != manifest["source_sha"] or manifest["physical_model_complete"]:
        raise RuntimeError("clean source/unresolved material identity mismatch")
    stage = specification.derived["stage"]
    artifact = ARTIFACTS / "v6" / stage
    artifact.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    design = json.loads(DESIGN_PATH.read_text())
    result = (
        geometry_stage(design, artifact)
        if stage == "V6-FE-INTERFACE"
        else ml_stage(design, artifact, source)
    )
    result.update(
        stage=stage,
        source_sha=source,
        design_sha256=file_hash(DESIGN_PATH),
        input_sha256=specification.input_sha256,
        input_path=str(specification.source_path),
        worker_wall_seconds=time.perf_counter() - began,
        affinity=sorted(os.sched_getaffinity(0)),
        math_threads=1,
        mpi_size=1,
        shared_workstation=True,
        artifact_directory=str(artifact),
    )
    write_json(artifact / "interface_result.json", result)
    write_json(directory / "interface_result.json", result)
    print(
        json.dumps(
            dict(
                stage=stage,
                status=result["status"],
                source_sha=source,
                artifact=str(artifact),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
