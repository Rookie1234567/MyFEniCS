"""Bounded V42 producer/consumer stages; original kernels remain the oracle."""

import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from src.runners.task042_shared import write_json
from src.solvers.distributed_volume_scope import (
    ARTIFACT,
    ROOT,
    plan_record,
    reserve_mesh,
    stage,
)
from src.solvers.native_entity_study import (
    current_consumption_identity,
    environment,
    save_rank,
)
from src.solvers.native_recovery_packets import PacketStore, sha
from src.solvers.target_port_preparation import target_config


def upstream(label):
    item = plan_record()["parents"][label]
    ptr = json.loads(Path(item["path"]).read_text())
    if sha(ptr["path"]) != ptr["sha256"]:
        raise ValueError("upstream payload hash")
    return json.loads(Path(ptr["path"]).read_text())


def live_identity():
    from src.solvers.native_entity_dependencies import digest

    return dict(
        current_consumption_identity(),
        volume_implementation={
            name: sha(ROOT / name)
            for name in (
                "src/solvers/distributed_entity_volume.py",
                "src/solvers/hcurl_affine_isotropic_tensor.py",
            )
        },
        volume_plan=digest(plan_record()),
    )


def require_live_envelope():
    from src.solvers.native_entity_dependencies import validate_envelope

    row, _ = stage("ENVELOPE")
    validate_envelope(row["envelope"], live_identity())
    return row


def store():
    return PacketStore(ARTIFACT / "checkpoints", live_identity())


def envelope(folder):
    from src.solvers.native_entity_dependencies import publish_envelope

    identity = live_identity()
    ptrs = plan_record()["parents"]
    system_path = ROOT / "benchmarks/artifacts/task042/v40/checkpoints/system.json"
    system = json.loads(system_path.read_text())
    result = publish_envelope(
        folder / "consumption.json",
        identity,
        parents=list(ptrs.values()),
        class_bindings=[
            {"system_path": str(system_path), "classes": system["metadata"]["classes"]}
        ],
    )
    return {
        "status": "LIVE_CONSUMPTION_ENVELOPE_READY",
        "envelope": result,
        "old_packets_modified": False,
        "live_identity": identity,
    }


def element():
    import basix

    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )


def physical_spec(q):
    from src.solvers.hcurl_affine_isotropic_tensor import (
        AffineIsotropicMaxwellTensorSpec,
    )

    cfg, _ = target_config()
    eps = {
        cfg.tags.air: cfg.eps_r,
        cfg.tags.substrate: cfg.substrate_index**2,
        cfg.tags.grating: cfg.grating_index**2,
    }
    return AffineIsotropicMaxwellTensorSpec(
        1 / cfg.mu_r,
        {tag: -(cfg.k0**2) * v for tag, v in eps.items()},
        quadrature_degree=q,
    )


def classes(folder):
    from scipy.linalg import lu_factor

    from src.solvers.hcurl_affine_isotropic_tensor import (
        AffineIsotropicMaxwellTensorFactory,
    )
    from src.solvers.native_integration_study import polynomial_volume
    from src.solvers.native_recovery_study import store as old_store

    require_live_envelope()
    s = store()
    p = upstream("v41_BRIDGE1")["results"][0]["packets"][0]
    lit = read_arrays(p["numeric"])
    rows = p["metadata"]["raw_classes"]
    if len(rows) != 6:
        raise ValueError("exact six-class finite anchor")
    e, cfg = element(), target_config()[0]
    began = perf_counter()
    factory = AffineIsotropicMaxwellTensorFactory(e, physical_spec(15))
    s.save(
        "reference_q15",
        {"mass" + str(i): a for i, a in enumerate(factory.mass_components)}
        | {"curl" + str(i): a for i, a in enumerate(factory.curl_components)},
        {"audit": dict(factory.audit)},
    )
    checks, class_names = [], []
    ip = np.asarray(e.entity_dofs[3][0], np.int64)
    for i, r in enumerate(rows):
        widths = tuple(float.fromhex(v) for v in r["width_hex"])
        a = factory.tensor(tag=r["tag"], widths=widths)
        # Distinct physical-quadrature implementation, not a second factory.
        c = int(np.flatnonzero(lit["cell_raw_class_local"] == r["index"])[0])
        xyz = lit["coordinates"][lit["cell_vertices"][c]]
        eps = {
            cfg.tags.air: cfg.eps_r,
            cfg.tags.substrate: cfg.substrate_index**2,
            cfg.tags.grating: cfg.grating_index**2,
        }[r["tag"]]
        q17 = polynomial_volume(e, xyz, eps, cfg.k0, cfg.mu_r, 17)
        check = dict(
            kind=f"raw_class_{i}_factory_q15_independent_q17", **metric(a, q17)
        )
        checks.append(check)
        name = f"class_{i}"
        # Write the expensive tensor before any LU or derived summary.
        s.save(name + "_tensor", {"raw": a, "q17": q17}, {"key": r, "checks": [check]})
        if not check["passed"]:
            return {
                "status": "VOLUME_NOT_QUALIFIED",
                "checks": checks,
                "failed_class": i,
            }
        counter = ARTIFACT / "local_lu_inventory.json"
        inv = (
            json.loads(counter.read_text())
            if counter.exists()
            else {"attempted": [], "completed": []}
        )
        if len(inv["attempted"]) >= 6:
            raise RuntimeError("six unique local LU attempt cap")
        inv["attempted"].append(name)
        write_json(counter, inv)
        lu, piv = lu_factor(a[np.ix_(ip, ip)])
        if not np.isfinite(lu).all() or np.any(np.diag(lu) == 0):
            raise ArithmeticError("finite internal LU unsafe")
        s.save(name + "_lu", {"lu": lu, "pivots": piv}, {"class": name, "rows": 450})
        inv["completed"].append(name)
        write_json(counter, inv)
        class_names.append(name)
    # Immutable V40 native raw matrices anchor the same reference integral
    # independently of the new large-cell witnesses.
    old = old_store()
    system = old.read("system")[0]["metadata"]
    for i, item in enumerate(system["classes"]):
        name = item["name"]
        m, a = old.read(name)
        import ast

        # The actual_space source key is recorded on each class, not rounded.
        key = ast.literal_eval(m["metadata"]["original_key"])
        tag, widths = key[0], tuple(key[1:4])
        pred = factory.tensor(tag=tag, widths=widths)
        checks.append(dict(kind="V40_raw_" + name, **metric(pred, a["raw_tensor"])))
    return {
        "status": "FINITE_RAW_CLASSES_READY"
        if all(c["passed"] for c in checks)
        else "VOLUME_NOT_QUALIFIED",
        "class_names": class_names,
        "class_keys": rows,
        "checks": checks,
        "seconds": perf_counter() - began,
        "new_local_LU": len(class_names),
        "global_LU": False,
    }


def oracle(folder):
    import basix.ufl
    import ufl
    from dolfinx import fem
    from mpi4py import MPI

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import _mark_boundary_facets, _mark_cells
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        _tabulate_raw_tensor_class,
    )
    from src.solvers.native_entity_topology import create_structured_mesh
    from src.solvers.native_recovery_study import orient_basix_tensor
    from src.solvers.native_witness_csr import assemble_witness_csr

    require_live_envelope()
    row, _ = stage("CLASSES")
    if row["status"] != "FINITE_RAW_CLASSES_READY" or MPI.COMM_WORLD.size != 1:
        raise ValueError("qualified classes / unique MPI1 native oracle")
    cfg, _ = target_config()
    old = upstream("v41_BRIDGE1")["results"][0]["packets"][0]
    lit = read_arrays(old["numeric"])
    axes = [np.asarray(a) for a in old["metadata"]["axes_nm"]]
    reserve_mesh(64)
    began = perf_counter()
    msh, _ = create_structured_mesh(axes, MPI.COMM_WORLD, keep_partition=True)
    tags = _mark_cells(msh, cfg)
    facets, exterior = _mark_boundary_facets(msh, cfg)
    V = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 6))
    mpc = build_double_floquet_mpc(
        V, SimpleNamespace(mesh=msh, facet_tags=facets, boundary_facets=exterior), cfg
    ).mpc
    coefficients, offsets = mpc.coefficients()
    if (
        not np.array_equal(mpc.slaves, lit["slave_local_dofs"])
        or not np.array_equal(offsets, lit["MPC_offsets"])
        or not np.array_equal(mpc.masters.array, lit["MPC_masters"])
        or not metric(np.asarray(coefficients), lit["MPC_coefficients"])["passed"]
    ):
        raise ValueError("live original native MPC differs from immutable bridge")
    if any(
        not np.array_equal(V.dofmap.cell_dofs(c), lit["cell_native_dofs"][c])
        for c in range(64)
    ):
        raise ValueError("native oracle dofmap changed")
    dx = ufl.Measure(
        "dx", domain=msh, subdomain_data=tags, metadata={"quadrature_degree": 15}
    )
    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    curl, mass = _build_physical_volume_terms(cfg, u, v, dx)
    compiled = fem.form(curl + mass)
    write_json(
        folder / "compiled_kernel.json",
        {
            "module": str(compiled.module.__file__),
            "sha256": sha(compiled.module.__file__),
            "seconds": perf_counter() - began,
        },
    )
    kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
    s, checks = store(), []
    for i, key in enumerate(row["class_keys"]):
        if s.has(f"class_{i}_native"):
            cached = s.read(f"class_{i}_native")[1]["raw_native"]
            raw = s.read(f"class_{i}_tensor")[1]["raw"]
            checks.append(
                dict(kind=f"native_q15_class_{i}_cached", **metric(raw, cached))
            )
            continue
        c = int(np.flatnonzero(lit["cell_raw_class_local"] == key["index"])[0])
        xyz = np.ascontiguousarray(
            lit["coordinates"][lit["cell_vertices"][c]], np.float64
        )
        a = _tabulate_raw_tensor_class(
            compiled, kernels, xyz, tag=key["tag"], dimension=882
        )
        raw = s.read(f"class_{i}_tensor")[1]["raw"]
        check = dict(kind=f"native_q15_class_{i}", **metric(raw, a))
        checks.append(check)
        s.save(f"class_{i}_native", {"raw_native": a}, {"checks": [check]})
    if not all(c["passed"] for c in checks):
        return {"status": "VOLUME_NOT_QUALIFIED", "checks": checks}
    from scipy.sparse import csr_matrix

    nr = len(lit["actual_dof_global_ids"])
    rr, cc, vv = [], [], []
    slaves = set(map(int, lit["slave_local_dofs"]))
    for j in range(nr):
        if j in slaves:
            lo, hi = lit["MPC_offsets"][j : j + 2]
            rr.extend([j] * int(hi - lo))
            cc.extend(lit["MPC_masters"][lo:hi])
            vv.extend(lit["MPC_coefficients"][lo:hi])
        else:
            rr.append(j)
            cc.append(j)
            vv.append(1.0 + 0j)
    expansion = csr_matrix((vv, (rr, cc)), shape=(nr, nr), dtype=np.complex128)
    original = [s.read(f"class_{i}_native")[1]["raw_native"] for i in range(6)]

    def matrices():
        for c in range(64):
            i = int(lit["cell_raw_class_local"][c])
            yield orient_basix_tensor(
                V.element.basix_element, original[i], int(lit["cell_permutations"][c])
            )

    matrix = assemble_witness_csr(matrices(), lit["cell_native_dofs"], expansion, nr)
    indptr, indices, data = matrix.indptr, matrix.indices, matrix.data
    s.save(
        "native_csr",
        {
            "indptr": indptr,
            "indices": indices,
            "data": data,
            "shape": np.asarray(matrix.shape, np.int64),
        },
        {
            "classes": checks,
            "source": "ORIGINAL_NATIVE_UFL_q15_BASIX_TRANSFORM_LITERAL_DOLFINx_MPC",
            "assembly": "original class kernels reused; sum E_c^H V_c E_c; no repeated cell integral",
            "factorized": False,
        },
    )
    del matrix
    return {
        "status": "FINITE_NATIVE_ORACLE_READY",
        "checks": checks,
        "seconds": perf_counter() - began,
        "new_native_hex": 64,
        "global_LU": False,
    }


def volume(folder, ranks):
    from mpi4py import MPI

    from src.solvers.distributed_entity_volume import (
        NativeDistributedAction,
        affine_internal_recover,
    )
    from src.solvers.native_entity_adapter import entity_transform
    from src.solvers.native_entity_protocol import canonical_values

    require_live_envelope()
    comm = MPI.COMM_WORLD
    if (
        comm.size != ranks
        or stage("ORACLE")[0]["status"] != "FINITE_NATIVE_ORACLE_READY"
    ):
        raise ValueError("actual ranks / qualified finite original oracle")
    parent = upstream("v41_BRIDGE" + str(ranks))
    if len(parent["results"]) != 1:
        raise ValueError("explicit single native numbering fixture required")
    p = parent["results"][0]["packets"][comm.rank]
    lit = read_arrays(p["numeric"])
    meta = p["metadata"]
    nc, nn = meta["entity_sizes"]["3"]["owned"], meta["owned_dofs"]
    s = store()
    row = stage("CLASSES")[0]
    e = element()
    mats = [s.read(n + "_tensor")[1]["raw"] for n in row["class_names"]]
    table = {(r["tag"], *r["width_hex"]): i for i, r in enumerate(row["class_keys"])}
    ids = np.asarray(
        [
            table[
                (
                    int(lit["cell_tags"][c]),
                    *[
                        float(v).hex()
                        for v in np.ptp(
                            lit["coordinates"][lit["cell_vertices"][c]], axis=0
                        )
                    ],
                )
            ]
            for c in range(nc)
        ]
    )
    action = NativeDistributedAction(comm, lit, mats, ids, e, nn, nc)
    # Independent y generated through the qualified complete entity decoder.
    y = np.zeros(len(lit["actual_dof_global_ids"]), np.complex128)
    for d, nm in ((1, 6), (2, 60)):
        vals = canonical_values(lit[f"entity{d}_master_keys"], nm, 424209)
        for j, perm in enumerate(lit[f"entity{d}_vertex_permutations"]):
            y[lit[f"entity{d}_native_dofs"][j]] = lit[f"entity{d}_phase"][j] * (
                entity_transform(d, perm) @ vals[j]
            )
    ip = np.asarray(e.entity_dofs[3][0], np.int64)
    cell_keys = []
    for c in range(nc):
        xyz = lit["coordinates"][lit["cell_vertices"][c]]
        key = np.array(
            [
                3,
                3,
                *[
                    np.searchsorted(meta["axes_nm"][a], xyz[:, a].min())
                    for a in range(3)
                ],
            ]
        )
        cell_keys.append(key)
        y[lit["cell_native_dofs"][c, ip]] = canonical_values(key[None, :], 450, 424209)[
            0
        ]
    y[lit["slave_local_dofs"]] = 0
    # Same pre-registered canonical input for every actual MPI layout.
    xlocal = np.zeros(len(lit["actual_dof_global_ids"]), np.complex128)
    for d, nm in ((1, 6), (2, 60)):
        vals = canonical_values(lit[f"entity{d}_master_keys"], nm, 424201)
        for j, perm in enumerate(lit[f"entity{d}_vertex_permutations"]):
            xlocal[lit[f"entity{d}_native_dofs"][j]] = lit[f"entity{d}_phase"][j] * (
                entity_transform(d, perm) @ vals[j]
            )
    for c, key in enumerate(cell_keys):
        xlocal[lit["cell_native_dofs"][c, ip]] = canonical_values(
            np.asarray(key)[None, :], 450, 424201
        )[0]
    xlocal[lit["slave_local_dofs"]] = 0
    x = xlocal[:nn].copy()
    y = y[:nn].copy()
    forward = action.apply_original(x)
    adjoint = action.apply_original_adjoint(y)
    left = comm.allreduce(np.vdot(y, forward))
    right = comm.allreduce(np.vdot(adjoint, x))

    def norm2(v):
        return float(comm.allreduce(float(np.vdot(v, v).real)))

    denom = max(
        np.sqrt(norm2(forward) * norm2(y)), np.sqrt(norm2(x) * norm2(adjoint)), 1e-30
    )
    error = float(abs(left - right))
    checks = [
        {
            "kind": "global_dual",
            "numerator": error,
            "denominator": float(denom),
            "relative": error / denom,
            "passed": error / denom <= 1e-10,
            "left": [left.real, left.imag],
            "right": [right.real, right.imag],
        }
    ]
    zero = action.apply_original(np.zeros_like(x))
    scaled = action.apply_original((0.37 - 0.91j) * x)
    checks += [
        dict(kind="zero", **metric(zero, np.zeros_like(zero))),
        dict(kind="complex_linearity", **metric(scaled, (0.37 - 0.91j) * forward)),
    ]
    oracle_check_seconds = 0.0
    if ranks == 1:
        from scipy.sparse import csr_matrix

        began = perf_counter()
        _, a = s.read("native_csr")
        matrix = csr_matrix(
            (a["data"], a["indices"], a["indptr"]), shape=tuple(a["shape"])
        )
        checks.extend(
            [
                dict(kind="original_native_CSR_forward", **metric(forward, matrix @ x)),
                dict(
                    kind="original_native_CSR_adjoint",
                    **metric(adjoint, matrix.conjugate().T @ y),
                ),
            ]
        )
        del matrix, a
        oracle_check_seconds = perf_counter() - began
    arrays = {
        "x": x,
        "y": y,
        "forward": forward,
        "adjoint": adjoint,
        "zero": zero,
        "scaled": scaled,
        "owned_global_ids": lit["actual_dof_global_ids"][:nn],
        "cell_keys": np.asarray(cell_keys),
    }
    for d in (1, 2):
        owned = meta["entity_sizes"][str(d)]["owned"]
        for label, a in (("forward", forward), ("adjoint", adjoint)):
            vals = []
            keys = []
            for j in range(owned):
                if lit[f"entity{d}_native_ids"][j] != lit[f"entity{d}_master_ids"][j]:
                    continue
                dofs = lit[f"entity{d}_native_dofs"][j]
                vals.append(
                    entity_transform(d, lit[f"entity{d}_vertex_permutations"][j])
                    .conjugate()
                    .T
                    @ a[dofs]
                )
                keys.append(lit[f"entity{d}_keys"][j])
            arrays[f"{label}_entity{d}_keys"] = np.asarray(keys, np.int64)
            arrays[f"{label}_entity{d}"] = np.asarray(vals, np.complex128)
    arrays["forward_internal"] = np.asarray(
        [forward[lit["cell_native_dofs"][c, ip]] for c in range(nc)]
    )
    arrays["adjoint_internal"] = np.asarray(
        [adjoint[lit["cell_native_dofs"][c, ip]] for c in range(nc)]
    )
    # Nonzero interior load. All six factors are immutable shared class data.
    recovered = []
    balance = []
    fi = []
    physical = action.expand(x)
    factors = [s.read(name + "_lu")[1] for name in row["class_names"]]
    for c in range(nc):
        i = int(ids[c])
        a = mats[i]
        lu = factors[i]
        f = canonical_values(np.asarray(cell_keys[c])[None, :], 450, 424213)[0]
        t = action.transforms[int(lit["cell_permutations"][c])]
        local = physical[lit["cell_native_dofs"][c]].copy()
        tp = np.setdiff1d(np.arange(882), ip)
        u = affine_internal_recover(a, lu["lu"], lu["pivots"], tp, ip, local, f, t)
        b = (t @ (a @ (t.T @ u)))[ip]
        checks.append(dict(kind=f"internal_balance_cell{c}", **metric(b, f)))
        recovered.append(u)
        balance.append(b)
        fi.append(f)
    arrays.update(
        recovered=np.asarray(recovered),
        internal_balance=np.asarray(balance),
        fi=np.asarray(fi),
    )
    packets = save_rank(
        folder,
        arrays,
        {
            "checks": checks,
            "MPI_size": ranks,
            "owned_rows": nn,
            "owned_cells": nc,
            "parent": p["numeric"],
            "calls": action.calls,
            "seconds": action.seconds,
            "oracle_check_seconds": oracle_check_seconds,
            "class_ids": ids.tolist(),
            "all_trace_allgather": False,
        },
        name="volume",
    )
    passed = comm.allreduce(int(all(c["passed"] for c in checks))) == ranks
    return {
        "status": "FINITE_DISTRIBUTED_VOLUME_SAVED"
        if passed
        else "VOLUME_NOT_QUALIFIED",
        "packets": packets,
        "checks": checks,
        "MPI_size": ranks,
        "new_LU": 0,
        "PDE_solved": False,
    }


def check_volume(folder):
    from scipy.sparse import csr_matrix

    from benchmarks.check_distributed_volume import compare_mpi

    require_live_envelope()
    s = store()
    _, a = s.read("native_csr")
    matrix = csr_matrix((a["data"], a["indices"], a["indptr"]), shape=tuple(a["shape"]))
    checks = []
    rows = []
    for n in (1, 2, 4):
        r, path = stage("VOLUME" + str(n))
        if r.get("MPI_size") != n or len(r.get("packets", [])) != n:
            raise ValueError("required complete finite volume rank inventory")
        checks.extend(c for p in r["packets"] for c in p["metadata"]["checks"])
        rows.append({"path": str(path), "sha256": sha(path), "MPI_size": n})
        if n == 1:
            v = read_arrays(r["packets"][0]["numeric"])
            for label, result in (
                ("forward", matrix @ v["x"]),
                ("adjoint", matrix.conjugate().T @ v["y"]),
            ):
                checks.append(
                    dict(
                        kind="independent_original_native_CSR_" + label,
                        **metric(v[label], result),
                    )
                )
            baseline = r["packets"]
        else:
            for label in ("forward", "adjoint"):
                checks.extend(
                    dict(c, MPI_size=n)
                    for c in compare_mpi(baseline, r["packets"], label)
                )
    return {
        "status": "FINITE_VOLUME_QUALIFIED"
        if all(c["passed"] for c in checks)
        else "VOLUME_NOT_QUALIFIED",
        "checks": checks,
        "parents": rows,
        "PDE_solved": False,
        "passed": all(c["passed"] for c in checks),
    }


def execute(role, folder, state):
    environment()
    if role == "ENVELOPE":
        return envelope(folder)
    if role == "CLASSES":
        return classes(folder)
    if role == "ORACLE":
        return oracle(folder)
    if role.startswith("VOLUME"):
        return volume(folder, int(role[-1]))
    if role.startswith("RECOVERY"):
        from src.solvers.distributed_recovery_study import recover

        return recover(folder, int(role[-1]))
    if role == "CHECK":
        result = check_volume(folder)
        from benchmarks.check_distributed_volume import check_recovery

        recovery = check_recovery()
        from benchmarks.check_frozen_volume_dependencies import (
            audit_internal_recovery,
            check_saved_target_classes,
        )

        literal_inventory = check_saved_target_classes(upstream("v41_TOPOLOGY"))
        internal_audit = audit_internal_recovery()
        result["volume_status"] = result["status"]
        result["recovery"] = recovery
        result["literal_class_inventory"] = literal_inventory
        result["independent_internal_audit"] = internal_audit
        result["volume_action_passed"] = all(
            c["passed"]
            for c in result["checks"]
            if not c["kind"].startswith("internal_balance_cell")
        )
        result["passed"] = (
            result["passed"]
            and recovery["passed"]
            and literal_inventory["passed"]
            and internal_audit["passed"]
        )
        result["status"] = (
            "DISTRIBUTED_VOLUME_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES"
            if result["passed"]
            else "DISTRIBUTED_VOLUME_NOT_QUALIFIED"
        )
        return result
    if role in ("TARGET_GATE", "DEPLOY", "CAPACITY"):
        from src.solvers.distributed_volume_delivery import (
            capacity,
            deploy,
            target_gate,
        )

        if role == "TARGET_GATE":
            return target_gate()
        if role == "DEPLOY":
            return deploy(folder)
        return capacity()
    if role.startswith("TARGET_"):
        gate, _ = stage("TARGET_GATE")
        if not gate["admitted"]:
            raise ValueError(
                "target numerical actor forbidden by recorded finite/resource/backend gate"
            )
    raise NotImplementedError("V42 stage wiring incomplete: " + role)
