"""V41 finite native bridge, target low-order topology and owner packets.

No forms, new factors, target p6 spaces or full target volume vectors exist
in this opt-in interface study. The actual native MPC is the small oracle.
"""

import json
import os
import zipfile
from pathlib import Path
from time import perf_counter
from types import MappingProxyType, SimpleNamespace

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from src.runners.task042_shared import write_json
from src.solvers.native_entity_adapter import (
    CompleteEntityAdapter,
    boundary_rows,
    entity_transform,
)
from src.solvers.native_entity_dependencies import (
    publish_envelope,
    semantic_hashes,
    validate_envelope,
)
from src.solvers.native_entity_protocol import canonical_values, structured_counts
from src.solvers.native_entity_scope import (
    ARTIFACT,
    ROOT,
    mesh_reservation,
    plan_record,
    stage,
    window,
)
from src.solvers.native_entity_topology import (
    basis_axis_transform,
    create_structured_mesh,
    raw_classes,
    topology_packet,
)
from src.solvers.native_recovery_packets import sha
from src.solvers.port_component_study import array_file
from src.solvers.target_port_preparation import geometry_contract, target_config


def parent(label):
    ptr = json.loads(Path(plan_record()["parents"][label]["path"]).read_text())
    if sha(ptr["path"]) != ptr["sha256"]:
        raise ValueError("immutable upstream result")
    return json.loads(Path(ptr["path"]).read_text()), Path(ptr["path"])


def environment():
    import sys

    import basix
    import dolfinx
    import dolfinx_mpc
    import petsc4py
    import slepc4py
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.runners.actual_loss_block_descent import _pure_blas_threads

    pools = _pure_blas_threads()
    if (
        os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION") != "1"
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
        or any(p["threads"] != 1 for p in pools)
        or Path(sys.executable).parent.parent != ROOT / ".venv"
    ):
        raise RuntimeError("V41 qualified ABI/threads")
    return {
        "executable": sys.executable,
        "scalar": "complex128",
        "IntType": "int64",
        "MPI_size": MPI.COMM_WORLD.size,
        "rank": MPI.COMM_WORLD.rank,
        "affinity": sorted(os.sched_getaffinity(0)),
        "math_pools": pools,
        "module_paths": {
            m.__name__: m.__file__
            for m in (basix, dolfinx, dolfinx_mpc, petsc4py, slepc4py)
        },
        "GPU_used": False,
        "DataLoader_workers": 0,
        "shared_workstation": True,
    }


def save_rank(folder, arrays, metadata, *, name="packet"):
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    path = folder / (name + f"_rank{comm.rank}.npz")
    receipt = array_file(path, compressed=True, **arrays)
    row = {
        "numeric": receipt,
        "metadata": metadata,
        "source_sha": os.environ["TASK042_RUN_SOURCE"],
        "rank": comm.rank,
        "MPI_size": comm.size,
        "environment": environment(),
        "commit": True,
    }
    write_json(path.with_suffix(".json"), row)
    # Only small receipts/metadata collective, never the trace/entity arrays.
    return comm.allgather(row)


def frozen_axes():
    r, _ = parent("V40_CAPACITY")
    return [np.array(r["capacity"]["axes_nm"][a], np.float64) for a in ("x", "y", "z")]


def envelope(folder):
    cfg, material = target_config()
    contract = geometry_contract(cfg, material)
    checkpoint = ROOT / "benchmarks/artifacts/task042/v40/checkpoints"
    groups = {}
    for group, file in (
        ("geometry", "geometry"),
        ("classes", "system"),
        ("quadrature", "quadrature"),
        ("recovery", "recovery"),
    ):
        row = json.loads((checkpoint / (file + ".json")).read_text())
        old = semantic_hashes(group, row["source_sha"])
        if old != semantic_hashes(group):
            raise ValueError("changed numerical stage dependency " + group)
        groups[group] = {
            "producer_source": row["source_sha"],
            "semantic_hashes": old,
            "packet_manifest": {
                "path": str(checkpoint / (file + ".json")),
                "sha256": sha(checkpoint / (file + ".json")),
            },
        }
    expected = {
        "physical": contract["physical_contract_sha256"],
        "material": sha(ROOT / "input/materials/si_optical_constants_v1.json"),
        "phase": [
            [cfg.floquet_phase_x.real, cfg.floquet_phase_x.imag],
            [cfg.floquet_phase_y.real, cfg.floquet_phase_y.imag],
        ],
        "basis": "N1E p6 Legendre complete 6/60/450 moments",
        "owner_protocol": "native_complete_entity.v1",
        "index_dtype": "int64",
        "scalar_dtype": "complex128",
        "axes": [a.tolist() for a in frozen_axes()],
        "modes": parent("V36_INVENTORY")[0]["ports"]["mode_inventory_sha256"]
        if "ports" in parent("V36_INVENTORY")[0]
        else sha(parent("V36_INVENTORY")[1]),
        "slave_semantics": "computation slave=0; physical expansion original phase; dual conjugate phase",
        "stage_dependencies": groups,
        "tags": contract["regular_geometry"]["tags"],
        "q": {"volume": 15, "boundary": 30, "audit": 17},
    }
    parents = []
    logical = actual = aliases = 0
    for p in sorted(checkpoint.glob("*.json")):
        row = json.loads(p.read_text())
        parents.append({"path": str(p), "sha256": sha(p)})
        a = row["arrays"]
        with zipfile.ZipFile(a["path"]) as z:
            count = len(z.namelist())
        if count != len(a["members"]) - len(a["aliases"]):
            raise ValueError("logical/actual/alias inventory")
        parents.append({"path": a["path"], "sha256": a["sha256"]})
        logical += len(a["members"])
        actual += count
        aliases += len(a["aliases"])
    # Bind full boundary layout and complete 32060-mode identity without
    # decoding V40 factors or making aliases into fresh array copies.
    for label in ("V38_LAYOUT", "V38_COMPONENT", "V36_INVENTORY"):
        r, path = parent(label)
        parents.append({"path": str(path), "sha256": sha(path)})
        for field in ("layout", "inputs", "outputs"):
            if field in r:
                parents.append({"path": r[field]["path"], "sha256": r[field]["sha256"]})
    sys = checkpoint / "system.json"
    binding = {
        "system_path": str(sys),
        "classes": json.loads(sys.read_text())["metadata"]["classes"],
    }
    record = publish_envelope(
        folder / "consumption_envelope.json",
        expected,
        parents=parents,
        class_bindings=[binding],
    )
    if (logical, actual, aliases) != (129, 120, 9):
        raise ValueError("V40 corrected inventory differs")
    return {
        "status": "IMMUTABLE_STAGE_CONSUMPTION_ENVELOPE_QUALIFIED",
        "envelope_path": str(folder / "consumption_envelope.json"),
        "envelope_sha256": sha(folder / "consumption_envelope.json"),
        "identity": expected,
        "inventory": {"logical": logical, "actual": actual, "aliases": aliases},
        "class_bindings": record["class_bindings"],
        "old_packets_modified": False,
    }


def require_envelope():
    e, _ = stage("ENVELOPE")
    if sha(e["envelope_path"]) != e["envelope_sha256"]:
        raise ValueError("envelope hash")
    validate_envelope(json.loads(Path(e["envelope_path"]).read_text()), e["identity"])
    return e


def fixture_bridge(folder, ranks):
    import basix.ufl
    from dolfinx import fem, la
    from mpi4py import MPI

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.constraints.floquet_3d_high_order import _build_entity_dof_map
    from src.geometry.mesh_builder_3d import _mark_boundary_facets, _mark_cells

    comm = MPI.COMM_WORLD
    require_envelope()
    if comm.size != ranks:
        raise ValueError("actual requested native MPI identity")
    resume = plan_record().get("resume_bridge_packets", {}).get("BRIDGE" + str(ranks))
    if resume is not None:
        from dolfinx.fem.element import finiteelement
        from dolfinx.mesh import CellType

        from benchmarks.check_native_entities import check_packets

        # A failed last direction step cannot invalidate the already atomic
        # native MPC packet. Validate it independently and repeat only the
        # affected direction API; no new mesh/dofmap/form/factor.
        records = []
        for item in resume:
            if sha(item["path"]) != item["sha256"]:
                raise ValueError("bridge resume source/hash")
            records.append(json.loads(Path(item["path"]).read_text()))
        audited = check_packets(records, fixture=True)
        if not audited["passed"] or any(r["MPI_size"] != ranks for r in records):
            raise ValueError("bridge resume literal numeric identity")
        results = [{"relabel": False, "packets": records}]
        native_element = finiteelement(
            CellType.hexahedron,
            basix.ufl.element("N1curl", "hexahedron", 6),
            np.float64,
        )
        directions = (
            direction_witness(folder, results, native_element)
            if comm.rank == 0
            else None
        )
        directions = comm.bcast(directions, root=0)
        return {
            "status": "DISTRIBUTED_NATIVE_ENTITY_BRIDGE_QUALIFIED_ON_FIXTURE"
            if directions["passed"]
            else "NATIVE_ENTITY_BRIDGE_NOT_QUALIFIED",
            "results": results,
            "direction_witness": directions,
            "fixture_hex": 64,
            "MPI_size": ranks,
            "resume": resume,
            "new_mesh": 0,
            "independent_checkpoint_checks": audited,
            "environment": environment(),
            "qualified_solver_MPI": "NOT_QUALIFIED",
        }
    cfg, _ = target_config()
    axes = [np.array(a, np.float64) for a in plan_record()["fixture_axes_nm"]]
    results = []
    # Use the one legal relabel only if natural numbering lacks a required
    # direction. MPI2 may already supply all three direction kinds.
    prior_directions = stage("BRIDGE2")[0]["direction_witness"] if ranks == 4 else None
    need_copy = ranks == 4 and not all(
        prior_directions[k]
        for k in ("edge_reverse", "face_rotation", "face_reflection")
    )
    for relabel in (False, True) if need_copy else (False,):
        if comm.rank == 0:
            mesh_reservation(64)
        comm.barrier()
        began = perf_counter()
        msh, costs = create_structured_mesh(
            axes, comm, keep_partition=True, relabel=relabel
        )
        literal, meta = topology_packet(
            msh, axes, (cfg.floquet_phase_x, cfg.floquet_phase_y)
        )
        tags = _mark_cells(msh, cfg)
        facet_tags, exterior = _mark_boundary_facets(msh, cfg)
        raw, oriented = raw_classes(msh, literal, tags.values)
        mesh_data = SimpleNamespace(
            mesh=msh, facet_tags=facet_tags, boundary_facets=exterior
        )
        V = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 6))
        floquet = build_double_floquet_mpc(V, mesh_data, cfg)
        mpc = floquet.mpc
        im = V.dofmap.index_map
        n = im.size_local + im.num_ghosts
        extended = mpc.function_space.dofmap.index_map
        ne = extended.size_local + extended.num_ghosts
        stored = np.zeros(ne, np.complex128)
        physical = np.zeros(n, np.complex128)
        full_dual = np.zeros(ne, np.complex128)
        coverage = np.zeros(n, np.int8)
        checks = []
        for d, moments in ((1, 6), (2, 60)):
            em = msh.topology.index_map(d)
            records = _build_entity_dof_map(V, d, moments)
            dofs = np.array(
                [
                    records[i]["local_dofs"]
                    for i in range(em.size_local + em.num_ghosts)
                ],
                np.int32,
            )
            owned = literal[f"entity{d}_native_ids"][: em.size_local]
            values = canonical_values(
                literal[f"entity{d}_keys"][: em.size_local], moments, 424101
            )
            adapter = CompleteEntityAdapter(
                comm,
                owned,
                literal[f"entity{d}_master_ids"],
                literal[f"entity{d}_master_owners"],
                literal[f"entity{d}_phase"],
                literal[f"entity{d}_vertex_permutations"],
                d,
            )
            expanded = adapter.extract(values)
            physical[dofs] = expanded
            coverage[dofs] += 1
            # A different complex dual on every physical, owned mesh entity.
            dual = canonical_values(literal[f"entity{d}_keys"], moments, 424109)
            dual[em.size_local :] = 0
            target = np.zeros_like(values)
            adapter.scatter_into(dual, target)
            left = comm.allreduce(np.vdot(dual, expanded))
            right = comm.allreduce(np.vdot(target, values))
            checks.append(
                {
                    "kind": f"complete_entity{d}_duality",
                    **metric(np.array([left]), np.array([right])),
                }
            )
            full_dual[dofs[: em.size_local]] = dual[: em.size_local]
            literal.update(
                {
                    f"entity{d}_native_dofs": dofs,
                    f"entity{d}_owned_canonical": values,
                    f"entity{d}_physical": expanded,
                    f"entity{d}_dual": dual,
                    f"entity{d}_scattered_dual": target,
                }
            )
        interior = np.array(V.element.basix_element.entity_dofs[3][0], np.int32)
        nc = msh.topology.index_map(3).size_local + msh.topology.index_map(3).num_ghosts
        cell_dofs = np.array([V.dofmap.cell_dofs(i) for i in range(nc)], np.int32)
        for c in range(nc):
            xyz = literal["coordinates"][literal["cell_vertices"][c]]
            lo = xyz.min(axis=0)
            key = np.array(
                [[3, 3, *[np.searchsorted(axes[a], lo[a]) for a in range(3)]]], np.int64
            )
            value = canonical_values(key, 450, 424101)[0]
            physical[cell_dofs[c, interior]] = value
            coverage[cell_dofs[c, interior]] += 1
        slaves = np.asarray(mpc.slaves, np.int32)
        stored[:n] = physical
        stored[slaves] = 0
        # Actual native MPC communication and substitution is an independent
        # oracle, not the new adapter calling itself.
        fun = fem.Function(mpc.function_space)
        fun.x.array[:] = stored
        fun.x.scatter_forward()
        computation = fun.x.array.copy()
        computation[slaves] = 0
        mpc.backsubstitution(fun)
        fun.x.scatter_forward()
        expanded_native = fun.x.array.copy()
        checks.append(
            {
                "kind": "actual_p6_MPC_full_vector",
                **metric(expanded_native[:n], physical),
            }
        )
        checks.append(
            {
                "kind": "actual_p6_MPC_ghost_sync",
                **metric(
                    computation[:n][np.setdiff1d(np.arange(n), slaves)],
                    physical[np.setdiff1d(np.arange(n), slaves)],
                ),
            }
        )
        scale = 0.37 - 0.91j
        fun.x.array[:] = scale * computation
        mpc.backsubstitution(fun)
        fun.x.scatter_forward()
        scaled_expanded = fun.x.array.copy()
        checks.append(
            {
                "kind": "actual_native_MPC_complex_scale",
                **metric(scaled_expanded, scale * expanded_native),
            }
        )
        fun.x.array[:] = 0
        mpc.backsubstitution(fun)
        fun.x.scatter_forward()
        zero_expanded = fun.x.array.copy()
        checks.append(
            {
                "kind": "actual_native_MPC_zero",
                **metric(zero_expanded, np.zeros_like(zero_expanded)),
            }
        )
        if np.any(computation[slaves]) or not np.all(coverage == 1):
            raise ValueError("slave-zero or complete actual-native dofmap inventory")
        coefficients, offsets = mpc.coefficients()
        master_array = np.asarray(mpc.masters.array, np.int32)
        # Literal conjugate pullback, then the library's reverse scatter.
        pulled = np.array(full_dual, copy=True)
        for slave in slaves:
            if slave >= im.size_local:
                continue
            lo, hi = offsets[slave : slave + 2]
            np.add.at(
                pulled,
                master_array[lo:hi],
                np.asarray(coefficients[lo:hi]).conjugate() * full_dual[slave],
            )
            pulled[slave] = 0
        dual_fun = fem.Function(mpc.function_space)
        dual_fun.x.array[:] = pulled
        dual_fun.x.scatter_reverse(la.InsertMode.add)
        # Whole-native dot is independent of the complete-entity protocol.
        inner1 = comm.allreduce(
            np.vdot(full_dual[: im.size_local], expanded_native[: im.size_local])
        )
        inner2 = comm.allreduce(
            np.vdot(dual_fun.x.array[: im.size_local], computation[: im.size_local])
        )
        checks.append(
            {
                "kind": "literal_MPC_conjugate_duality",
                **metric(np.array([inner1]), np.array([inner2])),
            }
        )
        literal.update(
            cell_native_dofs=cell_dofs,
            actual_dof_global_ids=extended.local_to_global(
                np.arange(ne, dtype=np.int32)
            ).astype(np.int64),
            actual_dof_owners=np.r_[
                np.full(extended.size_local, comm.rank, np.int32), extended.owners
            ],
            computation=computation,
            expanded_native=expanded_native,
            independent_physical=physical,
            scaled_expanded=scaled_expanded,
            zero_expanded=zero_expanded,
            native_dual=full_dual,
            literal_dual_scatter=dual_fun.x.array.copy(),
            slave_local_dofs=slaves,
            MPC_offsets=np.asarray(offsets, np.int64),
            MPC_masters=master_array,
            MPC_coefficients=np.asarray(coefficients, np.complex128),
            dof_coverage=coverage,
            interval_transform=V.element.basix_element.entity_transformations()[
                "interval"
            ],
            quadrilateral_transform=V.element.basix_element.entity_transformations()[
                "quadrilateral"
            ],
        )
        meta.update(
            costs=costs,
            raw_classes=raw,
            oriented_classes=oriented,
            checks=checks,
            axis_cells=[4, 4, 4],
            axes_nm=[a.tolist() for a in axes],
            phases=[
                [cfg.floquet_phase_x.real, cfg.floquet_phase_x.imag],
                [cfg.floquet_phase_y.real, cfg.floquet_phase_y.imag],
            ],
            actual_p6_global_rows=int(im.size_global),
            owned_dofs=int(im.size_local),
            relabel=relabel,
            original_function_local_rows=n,
            all_trace_allgather=False,
            native_p6_space=True,
            form_JIT=0,
            assembly=0,
            new_LU=0,
            total_seconds=perf_counter() - began,
        )
        packets = save_rank(
            folder, literal, meta, name="relabel" if relabel else "fixture"
        )
        results.append({"relabel": relabel, "packets": packets})
        native_element = V.element
        del fun, dual_fun, V, mpc, floquet, msh, literal
    # Direction oracle uses the old immutable raw class only. No new tensor
    # assembly/factorization. Keep full matrices in one rank's packet.
    directions = (
        direction_witness(folder, results, native_element) if comm.rank == 0 else None
    )
    directions = comm.bcast(directions, root=0)
    passed = all(
        c["passed"]
        for result in results
        for p in result["packets"]
        for c in p["metadata"]["checks"]
    )
    return {
        "status": "DISTRIBUTED_NATIVE_ENTITY_BRIDGE_QUALIFIED_ON_FIXTURE"
        if passed and directions["passed"]
        else "NATIVE_ENTITY_BRIDGE_NOT_QUALIFIED",
        "results": results,
        "direction_witness": directions,
        "fixture_hex": 64,
        "MPI_size": ranks,
        "qualified_solver_MPI": "NOT_QUALIFIED",
        "environment": environment(),
    }


def direction_witness(folder, results, native_element, *, codes=None):
    import basix.ufl

    # The actual FiniteElement from the completed fixture isn't retained.
    # Basix and DOLFINx C++ transformation implementations are paired below
    # using the element exported on its original mesh without constructing a
    # second mesh. The API object is installed by fixture_bridge.
    element = basix.ufl.element("N1curl", "hexahedron", 6).basix_element
    saved = json.loads(
        (
            ROOT / "benchmarks/artifacts/task042/v40/checkpoints/class_attempt_0_0.json"
        ).read_text()
    )
    with np.load(saved["arrays"]["path"], allow_pickle=False) as a:
        raw = a["raw_tensor"].copy()
    codes = (
        sorted(
            {
                int(code)
                for result in results
                for p in result["packets"]
                for code in read_arrays(p["numeric"])["cell_permutations"]
            }
        )
        if codes is None
        else sorted(set(map(int, codes)))
    )
    arrays, checks = (
        {
            "raw": raw,
            "codes": np.array(codes, np.uint32),
            "interval_transform": element.entity_transformations()["interval"],
            "quadrilateral_transform": element.entity_transformations()[
                "quadrilateral"
            ],
        },
        [],
    )
    for i, code in enumerate(codes):
        manual = basis_axis_transform(element, raw, code)
        native = raw.copy()
        # Native transformations accept contiguous real values. Two passes
        # cover both axes, each on real and imaginary channels.
        for part in ("real", "imag"):
            x = np.ascontiguousarray(getattr(native, part))
            native_element.T_apply(x.ravel(), np.array([code], np.uint32), 882)
            x = np.ascontiguousarray(x.T)
            native_element.T_apply(x.ravel(), np.array([code], np.uint32), 882)
            getattr(native, part)[:] = x.T
        checks.append(
            {"kind": "actual_native_p6_two_axis_" + str(code), **metric(manual, native)}
        )
        # Keep every actual native oracle. The checker reconstructs the
        # entity-generator action independently; no scalar pass is trusted.
        arrays["native_" + str(code)] = native
    edge = any(code >> 18 for code in codes)
    rotations = any(
        any(((code >> (3 * i)) & 7) >> 1 for i in range(6)) for code in codes
    )
    reflections = any(any((code >> (3 * i)) & 1 for i in range(6)) for code in codes)
    receipt = array_file(folder / "directions.npz", compressed=True, **arrays)
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "numeric": receipt,
        "codes": codes,
        "edge_reverse": edge,
        "face_rotation": rotations,
        "face_reflection": reflections,
        "raw_parent": {
            "path": saved["arrays"]["path"],
            "sha256": saved["arrays"]["sha256"],
        },
        "new_kernel": 0,
        "new_LU": 0,
    }


def topology_forecast():
    """Conservative simultaneous tree inventory, not a linear fitted slope."""
    shape = tuple(len(a) - 1 for a in frozen_axes())
    counts = structured_counts(shape)
    items = {
        "two_MPI_ABI_and_element_runtime_allowance": 768 * 2**20,
        "native_cells_connectivities_partition_and_ghost_workspaces": counts["cells"]
        * 1024,
        "native_vertices_geometry_and_input_copies": counts["vertices"] * 640,
        "native_edges_and_export_live_arrays": counts["edges"] * 256,
        "native_faces_and_export_live_arrays": counts["faces"] * 320,
        "MPI_graph_partition_and_compression_transient_allowance": 1024 * 2**20,
        "independent_owner_check_and_boundary_buffers_allowance": 512 * 2**20,
    }
    return {
        "counts": counts,
        "shape": list(shape),
        "simultaneous_tree_planned_bytes": sum(items.values()),
        "objects": items,
        "target_p6_space_vector_matrix_bytes": 0,
        "cgroup_kernel_limit_claim": False,
        "planning_limit_bytes": 6 * 2**30,
        "planning_pass": sum(items.values()) <= 6 * 2**30,
        "assumptions": "one MPI2 low-order mesh, preallocated arrays; no per-cell Python tuple mesh or target FE space",
    }


def target_topology(folder):
    from mpi4py import MPI

    from src.geometry.mesh_builder_3d import _mark_cells

    comm = MPI.COMM_WORLD
    require_envelope()
    for name in ("BRIDGE1", "BRIDGE2", "BRIDGE4"):
        r, _ = stage(name)
        if r["status"] != "DISTRIBUTED_NATIVE_ENTITY_BRIDGE_QUALIFIED_ON_FIXTURE":
            raise ValueError("real native distributed fixture gate " + name)
    bridge, _ = stage("BRIDGE4")
    directions = bridge["direction_witness"]
    if not all(
        directions[k] for k in ("edge_reverse", "face_rotation", "face_reflection")
    ):
        raise ValueError(
            "actual p6 nonzero edge/rotation/reflection qualification missing"
        )
    if comm.size != 2:
        raise ValueError("target topology fixed MPI2")
    forecast = topology_forecast()
    if comm.rank == 0:
        write_json(folder / "preallocation_capacity.json", forecast)
    if not forecast["planning_pass"]:
        return {
            "status": "TARGET_TOPOLOGY_CAPACITY_CONTROLLED_STOP",
            "forecast": forecast,
        }
    # The current active run was admitted against the same immutable limits.
    # Retain >1200s of native budget for owner/consumer/checking if setup is slow.
    book = window.ledger()
    used = sum(
        r["elapsed_seconds"]
        for r in book["runs"]
        if r["role"]
        in ("BRIDGE1", "BRIDGE2", "BRIDGE4", "TOPOLOGY", "ROUTING", "DEPLOY")
    )
    if 4800 - used < 1800:
        return {
            "status": "TARGET_TOPOLOGY_BUDGET_CONTROLLED_STOP",
            "remaining_native": 4800 - used,
        }
    cfg, _ = target_config()
    axes = frozen_axes()
    if comm.rank == 0:
        mesh_reservation(530856, target=True)
    comm.barrier()
    began = perf_counter()
    msh, costs = create_structured_mesh(axes, comm)
    literal, meta = topology_packet(
        msh, axes, (cfg.floquet_phase_x, cfg.floquet_phase_y)
    )
    tags = _mark_cells(msh, cfg)
    raw, oriented = raw_classes(msh, literal, tags.values)
    meta.update(
        costs=costs,
        raw_classes=raw,
        oriented_classes=oriented,
        axis_cells=list(forecast["shape"]),
        axes_nm=[a.tolist() for a in axes],
        phases=[
            [cfg.floquet_phase_x.real, cfg.floquet_phase_x.imag],
            [cfg.floquet_phase_y.real, cfg.floquet_phase_y.imag],
        ],
        target_p6_space_created=False,
        form_JIT=0,
        new_LU=0,
        total_seconds=perf_counter() - began,
    )
    packets = save_rank(folder, literal, meta, name="topology")
    classes = comm.allgather({"raw": raw, "oriented": oriented})
    raw_global, oriented_global = {}, {}
    for rank, row in enumerate(classes):
        for r in row["raw"]:
            key = (r["tag"], *r["width_hex"])
            entry = raw_global.setdefault(
                key,
                {
                    "tag": r["tag"],
                    "width_hex": r["width_hex"],
                    "count": 0,
                    "rank_users": [],
                },
            )
            entry["count"] += r["count"]
            entry["rank_users"].append(rank)
        for r in row["oriented"]:
            key = (
                r["tag"],
                *r["width_hex"],
                r["permutation"],
                *r["native_reference_vertex_order"],
            )
            entry = oriented_global.setdefault(key, {**r, "count": 0, "rank_users": []})
            entry["count"] += r["count"]
            entry["rank_users"].append(rank)
    old, _ = parent("V40_CAPACITY")
    expected = {
        (r["material_tag"], *r["raw_float64_width_hex"]): r["cell_count"]
        for r in old["volume_cache"]["raw_width_material_classes"]
    }
    raw_pass = {k: v["count"] for k, v in raw_global.items()} == expected
    actual_codes = {r["permutation"] for r in oriented_global.values()}
    qualified_codes = {
        code
        for name in ("BRIDGE1", "BRIDGE2", "BRIDGE4")
        for code in stage(name)[0]["direction_witness"]["codes"]
    }
    new_codes = sorted(actual_codes - qualified_codes)
    meta_counts = [p["metadata"]["entity_sizes"] for p in packets]
    exact_counts = all(
        sum(m[str(d)]["owned"] for m in meta_counts) == forecast["counts"][name]
        for d, name in ((0, "vertices"), (1, "edges"), (2, "faces"), (3, "cells"))
    )
    return {
        "status": "TARGET_NATIVE_TOPOLOGY_INVENTORY_QUALIFIED"
        if raw_pass and exact_counts
        else "TARGET_NATIVE_TOPOLOGY_NOT_QUALIFIED",
        "packets": packets,
        "raw_classes": list(raw_global.values()),
        "oriented_classes": list(oriented_global.values()),
        "raw_count": len(raw_global),
        "oriented_count": len(oriented_global),
        "raw_inventory_matches_270": raw_pass,
        "exact_global_counts": exact_counts,
        "new_unqualified_direction_codes": new_codes,
        "forecast": forecast,
        "target_cells": 530856,
        "target_p6_native_dofmap": "NOT_CONSTRUCTED",
        "canonical_moment_rows": "PROTOCOL_ONLY_NOT_NATIVE_DOLFINX_IDS",
    }


def saved_boundary_action():
    """Rehydrate saved polynomial, using the existing exact-q30 action."""
    import basix
    import basix.ufl

    from src.solvers.directional_boundary import (
        BoundaryLayout,
        DirectionalBoundaryAction,
        FacetPolynomial,
    )

    inventory, _ = parent("V36_INVENTORY")
    layout, _ = parent("V38_LAYOUT")
    data = read_arrays(layout["layout"])
    modes = inventory["ordered_modes"]
    if len(modes) != 32060:
        raise ValueError("complete frozen ordered modes")
    polynomial = FacetPolynomial.__new__(FacetPolynomial)
    polynomial.element = basix.ufl.element("N1curl", "hexahedron", 6).basix_element
    polynomial.p = 6
    coefficients, active = {}, {}
    topo = basix.cell.topology(basix.CellType.hexahedron)
    for side, face in (("bottom", 0), ("top", 5)):
        coefficients[side] = data[side + "_polynomial"]
        vertices = set(topo[2][face])
        edges = [i for i, edge in enumerate(topo[1]) if set(edge) <= vertices]
        active[side] = np.array(
            [j for edge in edges for j in polynomial.element.entity_dofs[1][edge]]
            + polynomial.element.entity_dofs[2][face],
            np.int64,
        )
    polynomial.coefficients = MappingProxyType(coefficients)
    polynomial.active = MappingProxyType(active)
    polynomial.nbytes = sum(a.nbytes for a in coefficients.values())
    cfg, _ = target_config()
    axes = frozen_axes()
    l = BoundaryLayout(
        axes[0], axes[1], polynomial, (cfg.floquet_phase_x, cfg.floquet_phase_y)
    )
    for side in ("bottom", "top"):
        if not np.array_equal(l.maps[side], data[side + "_rows"]) or not np.array_equal(
            l.weights[side], data[side + "_primal_phases"]
        ):
            raise ValueError("V38 literal full boundary layout identity")
    return DirectionalBoundaryAction(l, modes, 30)


def target_routing(folder):
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    require_envelope()
    topology, _ = stage("TOPOLOGY")
    if topology["status"] != "TARGET_NATIVE_TOPOLOGY_INVENTORY_QUALIFIED":
        raise ValueError("target inventory or nonzero p6 direction gate")
    if topology["new_unqualified_direction_codes"]:
        orientation, _ = stage("ORIENTATION")
        if (
            orientation["status"] != "TARGET_ENCOUNTERED_P6_DIRECTIONS_QUALIFIED"
            or orientation["direction_witness"]["codes"]
            != topology["new_unqualified_direction_codes"]
        ):
            raise ValueError("new target direction qualification still stopped")
    own = topology["packets"][comm.rank]
    a = read_arrays(own["numeric"])
    component, _ = parent("V38_COMPONENT")
    inputs = read_arrays(component["inputs"])
    x, y = inputs["x"], inputs["y"]
    shape = tuple(len(axis) - 1 for axis in frozen_axes())
    numeric, meta = (
        {},
        {
            "rank": comm.rank,
            "MPI_size": comm.size,
            "owner_buffer_bytes": 0,
            "producer": "ACTUAL_NATIVE_MESH_ENTITY_GLOBAL_IDS",
            "consumer": "CANONICAL_BOUNDARY_MOMENT_PROTOCOL",
            "full_target_volume_vector_allocated": False,
            "all_trace_allgather": False,
        },
    )
    reconstructed = np.zeros(378432, np.complex128)
    left = right = 0j
    for d, n in ((1, 6), (2, 60)):
        keys = a[f"entity{d}_keys"]
        total_owned = own["metadata"]["entity_sizes"][str(d)]["owned"]
        ids = np.arange(len(keys))
        boundary = ((keys[:, 4] == 0) | (keys[:, 4] == shape[2])) & (
            keys[:, 1] != 2 if d == 1 else keys[:, 1] == 2
        )
        physical_owned = np.flatnonzero(boundary & (ids < total_owned))
        canonical_owned = np.flatnonzero(
            boundary
            & (ids < total_owned)
            & np.all(keys == a[f"entity{d}_master_keys"], axis=1)
        )
        rows = boundary_rows(keys[canonical_owned], shape, d)
        owned_values = np.ascontiguousarray(x[rows])
        adapter = CompleteEntityAdapter(
            comm,
            a[f"entity{d}_native_ids"][canonical_owned],
            a[f"entity{d}_master_ids"][physical_owned],
            a[f"entity{d}_master_owners"][physical_owned],
            a[f"entity{d}_phase"][physical_owned],
            a[f"entity{d}_vertex_permutations"][physical_owned],
            d,
        )
        extracted = adapter.extract(owned_values)
        master_rows = boundary_rows(
            a[f"entity{d}_master_keys"][physical_owned], shape, d
        )
        expected = np.empty_like(extracted)
        for j, row in enumerate(master_rows):
            expected[j] = a[f"entity{d}_phase"][physical_owned[j]] * (
                entity_transform(
                    d, a[f"entity{d}_vertex_permutations"][physical_owned[j]]
                )
                @ x[row]
            )
        dual = canonical_values(keys[physical_owned], n, 424127)
        scattered = np.zeros_like(owned_values)
        adapter.scatter_into(dual, scattered)
        left += np.vdot(dual, extracted)
        right += np.vdot(scattered, owned_values)
        # Return only canonical master entities to the compact boundary input.
        canonical = adapter.canonical_from_physical(extracted)
        index = {
            int(gid): i
            for i, gid in enumerate(a[f"entity{d}_native_ids"][physical_owned])
        }
        selected = [
            index[int(gid)] for gid in a[f"entity{d}_native_ids"][canonical_owned]
        ]
        reconstructed[rows] = canonical[selected]
        numeric.update(
            {
                f"boundary{d}_canonical_rows": rows,
                f"boundary{d}_owned_keys": keys[canonical_owned],
                f"boundary{d}_physical_keys": keys[physical_owned],
                f"boundary{d}_master_rows": master_rows,
                f"boundary{d}_phase": a[f"entity{d}_phase"][physical_owned],
                f"boundary{d}_permutation": a[f"entity{d}_vertex_permutations"][
                    physical_owned
                ],
                f"boundary{d}_owned_values": owned_values,
                f"boundary{d}_physical_dual": dual,
                f"boundary{d}_scattered_dual": scattered,
                f"boundary{d}_extracted": extracted,
                f"boundary{d}_expected": expected,
                f"boundary{d}_canonical_extracted": canonical,
                f"boundary{d}_physical_native_ids": a[f"entity{d}_native_ids"][
                    physical_owned
                ],
                f"boundary{d}_requested_master_ids": a[f"entity{d}_master_ids"][
                    physical_owned
                ],
                f"boundary{d}_requested_master_owners": a[f"entity{d}_master_owners"][
                    physical_owned
                ],
                f"boundary{d}_owned_native_ids": a[f"entity{d}_native_ids"][
                    canonical_owned
                ],
            }
        )
        meta["owner_buffer_bytes"] += (
            owned_values.nbytes + scattered.nbytes + extracted.nbytes + dual.nbytes
        )
    numeric["global_duality_left"] = np.array([comm.allreduce(left)])
    numeric["global_duality_right"] = np.array([comm.allreduce(right)])
    output = np.empty_like(reconstructed) if comm.rank == 0 else None
    comm.Reduce(reconstructed, output, op=MPI.SUM, root=0)
    packets = save_rank(folder, numeric, meta, name="boundary")
    checks, actions = [], None
    if comm.rank == 0:
        checks.append(
            {"kind": "complete_canonical_378432_extract", **metric(output, x)}
        )
        action = saved_boundary_action()
        old = read_arrays(component["outputs"])
        amplitudes = action.recover(output)
        forward = action.apply(output)
        adjoint = action.apply(output, adjoint=True)
        modal = action.modal_rhs(inputs["alpha"])
        for name, value, frozen in (
            ("amplitudes", amplitudes, "q30_a_amplitudes"),
            ("forward", forward, "q30_a_forward"),
            ("adjoint", adjoint, "q30_a_adjoint"),
            ("modal", modal, "q30_a_modal"),
        ):
            checks.append(
                {"kind": "complete_32060_" + name, **metric(value, old[frozen])}
            )
        actions = array_file(
            folder / "complete_boundary_actions.npz",
            compressed=True,
            routed_input=output,
            frozen_input=x,
            amplitudes=amplitudes,
            frozen_amplitudes=old["q30_a_amplitudes"],
            forward=forward,
            frozen_forward=old["q30_a_forward"],
            adjoint=adjoint,
            frozen_adjoint=old["q30_a_adjoint"],
            modal=modal,
            frozen_modal=old["q30_a_modal"],
            y=y,
            alpha=inputs["alpha"],
        )
    checks, actions = comm.bcast((checks, actions), root=0)
    return {
        "status": "TARGET_BOUNDARY_OWNER_ROUTING_QUALIFIED"
        if all(c["passed"] for c in checks)
        else "TARGET_BOUNDARY_OWNER_ROUTING_NOT_QUALIFIED",
        "packets": packets,
        "checks": checks,
        "complete_actions": actions,
        "rows": 378432,
        "ports": 32060,
        "faces_per_side": 2628,
        "full_target_p6_dofmap": "NOT_CONSTRUCTED",
        "native_full_volume_vector": "NOT_CONSTRUCTED",
        "boundary_calls": {"recover": 1, "forward": 1, "adjoint": 1, "modal": 1},
        "NN_training": 0,
    }


def finish(role, folder):
    from mpi4py import MPI

    from benchmarks.check_native_entities import (
        check_directions,
        check_packets,
        check_routing,
    )

    require_envelope()
    checks = {}
    for name in ("BRIDGE1", "BRIDGE2", "BRIDGE4"):
        if not (ARTIFACT / (name + ".json")).exists():
            checks[name] = {"status": "NOT_RUN"}
            continue
        r, _ = stage(name)
        checks[name] = {
            "fixtures": [
                check_packets(p["packets"], fixture=True) for p in r["results"]
            ],
            "directions": check_directions(r["direction_witness"]["numeric"]),
        }
    if (ARTIFACT / "TOPOLOGY.json").exists():
        t, _ = stage("TOPOLOGY")
        if "packets" in t:
            checks["TOPOLOGY"] = check_packets(t["packets"])
    if (ARTIFACT / "ORIENTATION.json").exists():
        o, _ = stage("ORIENTATION")
        checks["ORIENTATION"] = check_directions(o["direction_witness"]["numeric"])
    if (ARTIFACT / "ROUTING.json").exists():
        r, _ = stage("ROUTING")
        checks["ROUTING"] = check_routing(r["packets"])
        a = read_arrays(r["complete_actions"])
        checks["ACTIONS"] = [
            {"kind": n, **metric(a[n], a["frozen_" + n])}
            for n in ("amplitudes", "forward", "adjoint", "modal")
        ]
    if role == "CAPACITY":
        return capacity_record(folder, checks)
    if role == "DEPLOY":
        r, _ = stage("ROUTING")
        comm = MPI.COMM_WORLD
        p = r["packets"][comm.rank]
        a = read_arrays(p["numeric"])
        errors = []
        for d, moments in ((1, 6), (2, 60)):
            adapter = CompleteEntityAdapter(
                comm,
                a[f"boundary{d}_owned_native_ids"],
                a[f"boundary{d}_requested_master_ids"],
                a[f"boundary{d}_requested_master_owners"],
                a[f"boundary{d}_phase"],
                a[f"boundary{d}_permutation"],
                d,
            )
            actual = adapter.extract(a[f"boundary{d}_owned_values"])
            dual = np.zeros_like(a[f"boundary{d}_owned_values"])
            adapter.scatter_into(a[f"boundary{d}_physical_dual"], dual)
            errors.extend(
                [
                    {
                        "kind": f"consumer_{d}_extract_rank{comm.rank}",
                        **metric(actual, a[f"boundary{d}_extracted"]),
                    },
                    {
                        "kind": f"consumer_{d}_dual_rank{comm.rank}",
                        **metric(dual, a[f"boundary{d}_scattered_dual"]),
                    },
                ]
            )
        errors = [c for row in comm.allgather(errors) for c in row]
        return {
            "status": "OWNER_BOUNDARY_FRESH_PROCESS_CONSUMPTION_QUALIFIED"
            if all(c["passed"] for c in errors)
            else "OWNER_CONSUMPTION_NOT_QUALIFIED",
            "checks": errors,
            "upstream_independent": checks,
            "volume_consumer": "NOT_CONNECTED_MATCHING_DISTRIBUTED_VOLUME_CALLBACK_REQUIRED",
            "required_volume_fields": [
                "native_entity_binding",
                "independent_trace",
                "internal_RHS",
                "nonzero_port_RHS",
                "forward",
                "adjoint",
                "recover",
                "full_explicit_residual",
            ],
            "V40_nonzero_RHS_anchor": plan_record()["parents"]["V40_RECOVER"],
            "target_PDE": "NOT_RUN",
        }
    return {
        "status": "INDEPENDENT_NATIVE_ENTITY_CHECKS_COMPLETE",
        "checks": checks,
        "solver_qualified": False,
    }


def capacity_record(folder, checks):
    result = {
        "status": "MEASURED_TOPOLOGY_OWNER_CAPACITY_CONTRACT",
        "checks": checks,
        "complete_target_PDE": "NOT_RUN",
        "NN20": "NOT_QUALIFIED",
        "full_step_seconds": "unknown",
        "48h_formula": "T_setup+K*(T_volume+T_boundary+T_adapter+T_PC)+T_recovery+T_audit+T_IO<=172800",
        "K_limit": "unknown until full target step and convergence are measured",
        "target_p6_native_dofmap": "NOT_CONSTRUCTED",
        "readiness": {
            "physical": "CANONICAL_USER_MATERIAL_AND_FROZEN_AXES",
            "numbering": "FINITE_NATIVE_BRIDGE_ONLY_AND_TARGET_ENTITY_IDS",
            "full_volume_operator": "MISSING_MATCHING_DISTRIBUTED_ENGINE",
            "PC": "NOT_QUALIFIED_CLOSED_OLD_PCS_UNAVAILABLE",
            "convergence": "NOT_QUALIFIED",
            "distributed_recovery": "MISSING_MPI1_V40_ANCHOR_ONLY",
            "accuracy_and_mode_truncation": "NOT_QUALIFIED",
            "complete_cost": "unknown",
        },
    }
    if (ARTIFACT / "TOPOLOGY.json").exists():
        t, _ = stage("TOPOLOGY")
        raw = t.get("raw_classes", [])
        oriented = t.get("oriented_classes", [])
        one_raw = 882 * 882 * 16
        # Fixed object inventory. These are conditional payloads, not measured
        # resident factors. No factors are loaded/generated by this stage.
        per_cache = 450 * 450 * 16 + 450 * 8 + 450 * 432 * 16 * 2 + 432 * 432 * 16
        result["actual_class_inventory"] = {
            "raw": len(raw),
            "oriented": len(oriented),
            "rank_private_raw_copies": sum(len(r["rank_users"]) for r in raw),
            "rank_private_oriented_copies": sum(len(r["rank_users"]) for r in oriented),
        }
        result["conditional_payload_bytes"] = {
            "node_shared_raw_matrices": len(raw) * one_raw,
            "rank_private_raw_matrices": sum(len(r["rank_users"]) for r in raw)
            * one_raw,
            "node_shared_LU_recovery_Schur_raw_classes": len(raw) * per_cache
            + 450 * 450 * 8,
            "rank_private_LU_recovery_Schur_raw_classes": sum(
                len(r["rank_users"]) for r in raw
            )
            * per_cache
            + 2 * 450 * 450 * 8,
            "additional_oriented_matrices_if_materialized": len(oriented) * one_raw,
            "one_full_complex128_native_vector": 345771066 * 16,
            "target_topology_packet_payload": sum(
                p["metadata"]["packet_array_payload"] for p in t.get("packets", [])
            ),
            "PC_Krylov_audit_lifecycle": "unknown",
            "constraint_after_recovery_class_count": "unknown_not_equal_to_raw_count",
            "alias_decode_workspace": "payload dedup does not guarantee process sharing",
        }
    result["adapter_workspace_objects"] = {
        "old_882_by84_float64_direction_buffer": 882 * 84 * 8,
        "new_largest_face_transform_complex128": 60 * 60 * 16,
        "new_per_entity_primal_and_dual_temporary": 3 * 60 * 16,
        "owner_send_receive_buffers": "actual per-rank packet; may coexist with source/target",
        "old_86880B_claim": "one partial payload; never full RSS upper bound",
    }
    write_json(folder / "target_solver_readiness.json", result)
    return result


def execute(role, folder, state):
    if role == "ENVELOPE":
        return envelope(folder)
    if role.startswith("BRIDGE"):
        return fixture_bridge(folder, int(role[-1]))
    if role == "TOPOLOGY":
        return target_topology(folder)
    if role == "ORIENTATION":
        import basix.ufl
        from dolfinx.fem.element import finiteelement
        from dolfinx.mesh import CellType

        require_envelope()
        t, path = stage("TOPOLOGY")
        if t["status"] != "TARGET_NATIVE_TOPOLOGY_INVENTORY_QUALIFIED":
            raise ValueError(
                "actual topology identity before necessary direction audit"
            )
        codes = t["new_unqualified_direction_codes"]
        if not codes:
            raise ValueError("no new target direction; reuse fixture evidence")
        element = finiteelement(
            CellType.hexahedron,
            basix.ufl.element("N1curl", "hexahedron", 6),
            np.float64,
        )
        d = direction_witness(folder, [], element, codes=codes)
        return {
            "status": "TARGET_ENCOUNTERED_P6_DIRECTIONS_QUALIFIED"
            if d["passed"]
            else "TARGET_NEW_DIRECTION_NOT_QUALIFIED",
            "direction_witness": d,
            "target_parent": {"path": str(path), "sha256": sha(path)},
            "new_mesh": 0,
            "target_p6_function_space": "NOT_CONSTRUCTED",
            "new_kernel": 0,
            "new_LU": 0,
            "scope": "necessary p6 native two-axis audit on actually encountered new directions; qualification paused until pass",
        }
    if role == "ROUTING":
        return target_routing(folder)
    if role in ("CHECK", "DEPLOY", "CAPACITY"):
        return finish(role, folder)
    raise ValueError("V41 explicit stage")
