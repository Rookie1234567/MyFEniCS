"""Finite native integration study, orchestrated by the shared preparation runner.

No physical solve is performed. The existing native cell condensation and an
independently assembled <=8-hex matrix supply recovery and the volume oracle.
"""

import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from benchmarks.check_native_integration import (
    check_adapter_vectors,
    check_coupled_vectors,
    literal_layout_checks,
)
from src.runners.task042_shared import write_json
from src.solvers.boundary_structure_study import make_action, witness_plan
from src.solvers.native_boundary_adapter import (
    CoupledNativeBoundaryAction,
    LocalNativeVolumeAction,
    NativeBoundaryAdapter,
    build_literal_adapter,
)
from src.solvers.native_integration_scope import (
    native_counter,
    parent_stage,
    plan_record,
    read_stage,
    reserve_local_classes,
    settle_local_classes,
    window,
)
from src.solvers.port_component_study import array_file, environment


def random_complex(rng, n):
    return np.asarray(rng.normal(size=n) + 1j * rng.normal(size=n), np.complex128)


def selected_action(description=None):
    from src.solvers.directional_boundary import DirectionalBoundaryAction

    full = make_action(witness_plan()["selected_modes"], 30)
    if description is None:
        return full
    faces = [(c["side"], *c["indices"][:2]) for c in description["cells"]]
    return DirectionalBoundaryAction(full.layout, full.modes, 30, face_inventory=faces)


def require_stage(name, status):
    row, path = read_stage(name)
    if row["status"] != status:
        raise ValueError("V39 prerequisite " + name)
    return row, path


def evidence(folder):
    from benchmarks.check_boundary_structure import check_saved

    began = perf_counter()
    saved = check_saved()
    bridge, _ = parent_stage("BRIDGE")
    layout, _ = parent_stage("LAYOUT")
    action = selected_action()
    conversions = layout["native_patch_adapter"]["arrays"]
    checks = []
    for patch, conversion in zip(bridge["patches"], conversions, strict=True):
        name = patch["description"]["name"]
        if Path(conversion["path"]).name != name + "_row_adapter.npz":
            raise ValueError("literal adapter class/path inventory")
        checks.extend(
            literal_layout_checks(
                action.layout.polynomial.element, action.layout, patch, conversion
            )
        )
    if (
        not all(c["passed"] for c in checks)
        or saved["status"] != "TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q"
    ):
        raise ValueError("saved final-inventory or literal adapter audit failed")
    return {
        "status": "SAVED_BOUNDARY_EVIDENCE_LINKED",
        "independent_checks": checks,
        "saved_checker": saved,
        "seconds": perf_counter() - began,
        "parents": plan_record()["parents"],
        "target_solve": False,
    }


def native_literal(V, mpc, desc):
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        _entity_canonical_order,
        _entity_coordinates,
        _space_data,
        _topology_data,
    )
    from src.solvers.target_boundary_witness import dual_maps

    degree, _, interior_positions = _space_data(V)
    topology, info, owned = _topology_data(V)
    if degree != 6 or int(owned[0]) != len(desc["cells"]):
        raise ValueError("native p6/owner-cell witness identity")
    permutations = info.copy()
    maps = dual_maps(V, mpc)
    e = V.element.basix_element
    dofs = np.array([V.dofmap.cell_dofs(c) for c in range(len(desc["cells"]))])
    interior = np.unique(dofs[:, interior_positions])
    literal = {
        "cell_dofs": dofs,
        "coordinates": V.mesh.geometry.x.copy(),
        "geometry_dofmap": V.mesh.geometry.dofmap.copy(),
        "permutations": permutations,
        "master_offsets": np.r_[0, np.cumsum([len(r) for r, _ in maps])].astype(
            np.int64
        ),
        "master_rows": np.concatenate([r for r, _ in maps]),
        "master_dual_coefficients": np.concatenate([c for _, c in maps]),
        "slaves": np.array(mpc.slaves, np.int64),
        "interiors": interior,
        "interval_transform": e.entity_transformations()["interval"],
        "quadrilateral_transform": e.entity_transformations()["quadrilateral"],
    }
    # Reuse the established physical canonical entity keys. They identify
    # actual native entities; compact boundary IDs still do not claim to be
    # the unconstructed full-volume DOLFINx row IDs.
    for dimension in (1, 2):
        ids = np.arange(topology.index_map(dimension).size_local, dtype=np.int64)
        coords = []
        permutations = []
        for entity in ids:
            raw = _entity_coordinates(V, dimension, int(entity))
            canonical, order = _entity_canonical_order(raw, dimension, 1e-10)
            coords.append(canonical)
            permutations.append(order)
        literal[f"entity_{dimension}_ids"] = ids
        literal[f"entity_{dimension}_canonical_coordinates"] = np.array(coords)
        literal[f"entity_{dimension}_canonical_permutations"] = np.array(
            permutations, np.int64
        )
    return literal


def adapter_columns(adapter, action):
    n, nm = adapter.native_size, len(action.modes)
    C = np.empty((n, nm), np.complex128)
    D = np.empty((nm, n), np.complex128)
    for m in range(nm):
        alpha = np.zeros(nm, np.complex128)
        alpha[m] = 1
        C[:, m] = adapter.scatter(action.modal_rhs(alpha))
        components = np.zeros((nm, 2), np.complex128)
        components[m] = action.e[m] / action.H[m]
        # scatter_components is the conjugate adjoint of the raw Fourier
        # component functional. Taking H gives normalized primal D.
        D[m] = adapter.scatter(action.scatter_components(components)).conjugate()
    return C, D


def adapter_stage(folder):
    from src.solvers.target_boundary_witness import build_patch
    from src.solvers.target_port_preparation import target_config

    require_stage("EVIDENCE", "SAVED_BOUNDARY_EVIDENCE_LINKED")
    cfg, _ = target_config()
    action = selected_action()
    wp = witness_plan()
    bridge, _ = parent_stage("BRIDGE")
    patches = []
    # Completed prefixes can be reused after an ordinary metadata repair;
    # their source and all array receipts stay bound to the original attempt.
    prefix = window.TMP / "adapter_prefix.json"
    if prefix.exists():
        patches = json.loads(prefix.read_text())
        for p in patches:
            for key in ("literal", "adapter", "vectors"):
                read_arrays(p[key])
    for desc in wp["patches"]:
        name = desc["name"]
        if any(p["description"] == desc for p in patches):
            continue
        action = selected_action(desc)
        native_counter(len(desc["cells"]))
        began = perf_counter()
        data, V, floquet = build_patch(desc, cfg)
        lit = native_literal(V, floquet.mpc, desc)
        old = next(p for p in bridge["patches"] if p["description"] == desc)
        old_lit = read_arrays(old["literal"])
        for key in (
            "cell_dofs",
            "coordinates",
            "geometry_dofmap",
            "permutations",
            "master_offsets",
            "master_rows",
            "master_dual_coefficients",
            "slaves",
        ):
            if not np.array_equal(lit[key], old_lit[key]):
                raise ValueError("native witness row/permutation/MPC changed: " + key)
        n = V.dofmap.index_map.size_global
        adapter, ownership = build_literal_adapter(
            action.layout.polynomial.element, lit, desc, action.layout, n, lit["slaves"]
        )
        setup = perf_counter() - began
        native = read_arrays(old["native"])
        nm = len(action.modes)
        C = np.column_stack([native[f"C_{m}"] for m in range(nm)])
        H = np.array([m["projection_denominator"] for m in wp["selected_modes"]])
        D = np.row_stack([native[f"D_{m}"] for m in range(nm)]) / H[:, None]
        Ca, Da = adapter_columns(adapter, action)
        vectors = {
            "C_native": C,
            "D_native": D,
            "C_from_adapter": Ca,
            "D_from_adapter": Da,
            "slaves": lit["slaves"],
            "interiors": lit["interiors"],
        }
        rng = np.random.default_rng(423901)
        x = random_complex(rng, n)
        x[lit["slaves"]] = 0
        rng2 = np.random.default_rng(423903)
        y = random_complex(rng2, n)
        y[lit["slaves"]] = 0
        internal = np.zeros(n, np.complex128)
        internal[lit["interiors"]] = random_complex(rng, len(lit["interiors"]))
        times = {}
        began = perf_counter()
        for label, value in (
            ("a", x),
            ("b", y),
            ("interior", internal),
            ("zero", np.zeros(n, np.complex128)),
            ("scale", (0.37 - 0.91j) * x),
        ):
            t0 = perf_counter()
            trace = adapter.extract(value)
            vectors[label + "_x"] = value
            vectors[label + "_t"] = trace
            vectors[label + "_forward"] = adapter.scatter(action.apply(trace))
            vectors[label + "_adjoint"] = adapter.scatter(
                action.apply(trace, adjoint=True)
            )
            vectors[label + "_amplitudes"] = action.recover(trace)
            vectors[label + "_oracle_forward"] = C @ (D @ value)
            vectors[label + "_oracle_adjoint"] = D.conjugate().T @ (
                C.conjugate().T @ value
            )
            vectors[label + "_oracle_amplitudes"] = D @ value
            times[label] = perf_counter() - t0
        alpha = random_complex(rng, nm)
        dual = random_complex(rng2, adapter.boundary_size)
        vectors.update(
            alpha=alpha,
            modal=adapter.scatter(action.modal_rhs(alpha)),
            oracle_modal=C @ alpha,
            boundary_dual=dual,
            extract_inner=np.array([np.vdot(dual, adapter.extract(x))]),
            scatter_inner=np.array([np.vdot(adapter.scatter(dual), x)]),
        )
        checks = check_adapter_vectors(vectors)
        receipts = {
            "literal": array_file(folder / (name + "_literal.npz"), **lit),
            "adapter": array_file(folder / (name + "_adapter.npz"), **adapter.arrays()),
            "vectors": array_file(
                folder / (name + "_vectors.npz"), deduplicate=True, **vectors
            ),
        }
        record = dict(
            description=desc,
            record_source_sha=os.environ["TASK042_RUN_SOURCE"],
            storage_rows=n,
            ownership=ownership,
            checks=checks,
            setup_seconds=setup,
            action_seconds=perf_counter() - began,
            per_input_seconds=times,
            adapter_cost=dict(adapter.stats),
            **receipts,
        )
        patches.append(record)
        write_json(prefix, patches)
        if not all(c["passed"] for c in checks):
            return {"status": "NATIVE_ADAPTER_NOT_QUALIFIED", "patches": patches}
        del V, data, floquet, adapter, vectors
    return {
        "status": "NATIVE_BOUNDARY_ADAPTER_QUALIFIED_ON_WITNESSES",
        "patches": patches,
        "mode_count": len(action.modes),
        "environment": environment(fe=True),
        "MPI": 1,
        "target_volume_rows": "UNKNOWN_NOT_CONSTRUCTED",
        "target_solve": False,
    }


def polynomial_volume(element, coordinates, eps, k0, mu, q):
    """Independent Basix quadrature, all 882 fields, affine covariant Piola.

    N1curl p6 components have per-axis degrees at most six. Products in the
    mass and curl terms have degree <=12 per axis. q15 (8-point Gauss in each
    axis, exact through degree15) therefore suffices on these affine cells.
    q17 checks the numerical tensor, not the Fourier boundary quadrature.
    """
    import basix

    points, weights = basix.make_quadrature(basix.CellType.hexahedron, q)
    tab = element.tabulate(1, points)
    widths = np.ptp(coordinates, axis=0)
    jac = np.prod(widths)
    fields = tab[0] / widths
    derivative = [
        tab[basix.index(*(int(j == a) for j in range(3)))] / widths / widths[a]
        for a in range(3)
    ]
    curls = np.stack(
        (
            derivative[1][:, :, 2] - derivative[2][:, :, 1],
            derivative[2][:, :, 0] - derivative[0][:, :, 2],
            derivative[0][:, :, 1] - derivative[1][:, :, 0],
        ),
        axis=2,
    )
    out = np.zeros((element.dim, element.dim), np.complex128)
    for a in range(3):
        out += (curls[:, :, a].T @ (weights[:, None] * curls[:, :, a])) * (jac / mu)
        out -= (fields[:, :, a].T @ (weights[:, None] * fields[:, :, a])) * (
            jac * k0**2 * eps
        )
    return out


def coupled_stage(folder):
    import dolfinx_mpc
    import ufl
    from dolfinx import fem
    from scipy.sparse import csr_matrix

    from src.runners.port_preparation import storage
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.hcurl_assembly_time_condensation import (
        _orient_cell_tensor,
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.p6_cell_condensed_action import (
        P6CellCondensedAction,
        P6DirectTracePortTerms,
    )
    from src.solvers.target_boundary_witness import build_patch
    from src.solvers.target_port_preparation import target_config

    adapter_record, _ = require_stage(
        "ADAPTER", "NATIVE_BOUNDARY_ADAPTER_QUALIFIED_ON_WITNESSES"
    )
    patch = next(
        p for p in adapter_record["patches"] if p["description"]["name"] == "xy_corner"
    )
    desc = patch["description"]
    native_counter(len(desc["cells"]))
    cfg, _ = target_config()
    costs = {}
    began = perf_counter()
    data, V, floquet = build_patch(desc, cfg)
    lit = native_literal(V, floquet.mpc, desc)
    old_lit = read_arrays(patch["literal"])
    for key in old_lit:
        if not np.array_equal(lit[key], old_lit[key]):
            raise ValueError("coupled native literal identity " + key)
    adapter = NativeBoundaryAdapter.from_arrays(
        read_arrays(patch["adapter"]), identity="xy_corner"
    )
    action = selected_action(desc)
    native = read_arrays(patch["vectors"])
    n, nm = adapter.native_size, len(action.modes)
    # Conservative simultaneous upper plan: JIT<=1.5GiB, evidence>=256MiB;
    # 8 raw/oriented tensors, internal caches, sparse copies and quadrature
    # fit below 2GiB RAM. No target-sized volume object is constructed.
    reserve = storage(1536 * 2**20 + 256 * 2**20, namespace="v39")
    write_json(
        folder / "capacity_plan.json",
        {
            "storage": reserve,
            "hex": 8,
            "max_cell_tensor_rows": 882,
            "max_local_classes": 16,
            "local_cache_limit_bytes": 256 * 2**20,
            "planned_peak_bytes": 2 * 2**30,
            "jit_limit_bytes": 1536 * 2**20,
            "evidence_reserved_bytes": 256 * 2**20,
            "oracle_max_nnz_upper": 8 * 882**2,
            "global_target_matrix": False,
        },
    )
    costs["mesh_literal_setup"] = perf_counter() - began
    began = perf_counter()
    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    dx = ufl.Measure(
        "dx",
        domain=V.mesh,
        subdomain_data=data.cell_tags,
        metadata={"quadrature_degree": 15},
    )
    curl, mass = _build_physical_volume_terms(cfg, u, v, dx)
    compiled = fem.form(curl + mass)
    costs["native_volume_compile"] = perf_counter() - began
    began = perf_counter()
    # Eight cells can create at most eight raw+orientation classes. All four
    # dense internal caches plus identity and pivots fit the 256MiB limit
    # even before any identity sharing is assumed.
    prior_cache_upper = 8 * (
        16 * (450**2 + 2 * 450 * 432 + 432**2) + 8 * 450**2 + 4 * 450
    )
    if prior_cache_upper > 256 * 2**20:
        raise MemoryError("prior local cache bound")
    class_attempt = reserve_local_classes(8)
    system = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        data.cell_tags,
        mpc=floquet.mpc,
        appended_global_rows=nm,
        strict_local_checks=True,
        retain_local_schur_for_matrix_free=True,
        retain_local_original_for_native_audit=True,
        materialize_global_matrix=False,
        geometry_identity_policy="raw_unrounded",
        share_identity_cache=True,
    )
    costs["local_condensation_setup"] = perf_counter() - began
    classes = list(system.retained_local_original_by_class)
    settle_local_classes(class_attempt, len(classes))
    cache_dicts = [
        system.interior_lu_by_class,
        system.interior_from_trace_by_class,
        system.trace_from_interior_rhs_by_class,
        system.retained_local_schur_by_class,
    ]
    arrays = {}
    for d in cache_dicts:
        for item in d.values():
            for a in item if isinstance(item, tuple) else (item,):
                arrays[id(a)] = a
    payload = sum(a.nbytes for a in arrays.values())
    if len(classes) > 16 or payload > 256 * 2**20:
        raise MemoryError("bounded internal class/cache gate")
    tensors = [system.retained_local_original_by_class[k] for k in classes]
    class_indices = np.array(
        [classes.index(c.class_key) for c in system.cell_recovery_maps], np.int64
    )
    volume = LocalNativeVolumeAction(lit, tensors, class_indices, n)
    began = perf_counter()
    oracle_mat = dolfinx_mpc.assemble_matrix(compiled, floquet.mpc, diagval=0.0)
    oracle_mat.assemble()
    indptr, indices, values = oracle_mat.getValuesCSR()
    oracle = csr_matrix((values.copy(), indices.copy(), indptr.copy()), shape=(n, n))
    costs["independent_small_native_sparse_assembly"] = perf_counter() - began
    began = perf_counter()
    # Independent polynomial rule checks one representative of each actual
    # air/substrate material in this witness, without another native JIT.
    qchecks = []
    seen = set()
    element = V.element.basix_element
    tags = {
        int(c): int(t)
        for c, t in zip(data.cell_tags.indices, data.cell_tags.values, strict=True)
    }
    for cell, class_id in enumerate(class_indices):
        tag = tags[cell]
        if tag in seen:
            continue
        seen.add(tag)
        eps = cfg.eps_r if tag == cfg.tags.air else cfg.substrate_index**2
        coords = lit["coordinates"][lit["geometry_dofmap"][cell]]
        a15 = polynomial_volume(element, coords, eps, cfg.k0, cfg.mu_r, 15)
        a17 = polynomial_volume(element, coords, eps, cfg.k0, cfg.mu_r, 17)
        _orient_cell_tensor(
            V.element, a15, np.array([lit["permutations"][cell]], np.uint32)
        )
        _orient_cell_tensor(
            V.element, a17, np.array([lit["permutations"][cell]], np.uint32)
        )
        qchecks.extend(
            [
                dict(kind="volume_q15_vs_q17", tag=tag, **metric(a15, a17)),
                dict(
                    kind="native_volume_vs_Basix_q17",
                    tag=tag,
                    **metric(tensors[class_id], a17),
                ),
            ]
        )
    costs["independent_volume_polynomial_oracle"] = perf_counter() - began
    if not all(c["passed"] for c in qchecks):
        write_json(folder / "volume_failed_checks.json", qchecks)
        raise ValueError("native/volume quadrature gate")
    C, D = native["C_from_adapter"], native["D_from_adapter"]
    interior = lit["interiors"]
    trace = np.setdiff1d(np.arange(n), interior)
    # No numerical clipping: the entity-supported map never contains cell
    # interior columns, independently checked against all original 882 bases.
    terms = [
        P6DirectTracePortTerms(m, trace, C[trace, m], trace, D[m, trace])
        for m in range(nm)
    ]
    condensed = P6CellCondensedAction(
        system, H_p=np.eye(nm, dtype=np.complex128), direct_trace_terms=terms
    )
    coupled = CoupledNativeBoundaryAction(adapter, action, volume)
    rng = np.random.default_rng(423901)
    x = random_complex(rng, n)
    x[lit["slaves"]] = 0
    y = random_complex(rng, n)
    y[lit["slaves"]] = 0
    f = random_complex(rng, n)
    f[lit["slaves"]] = 0
    g = random_complex(rng, nm)
    z = random_complex(rng, condensed.reduced_size)
    alpha = z[system.active_rows :]
    began = perf_counter()
    reduced_rhs = condensed.reduce_rhs(f, port_rhs=g, rhs_is_mpc_dual=True)
    storage_u = condensed.recover_storage(z, full_rhs=f)
    expanded = condensed.recover_storage(z, full_rhs=f, expand_trace=True)
    audit = condensed.evaluate_native_residual(
        z,
        f,
        lambda a: oracle @ a + native["C_native"] @ (native["D_native"] @ a),
        port_rhs=g,
    )
    costs["reduce_recover_original_residual"] = perf_counter() - began
    rFE = f - (oracle @ storage_u + native["C_native"] @ alpha)
    rport = g + native["D_native"] @ storage_u - alpha
    rnative = (
        f
        - native["C_native"] @ g
        - (oracle @ storage_u + native["C_native"] @ (native["D_native"] @ storage_u))
    )
    z2 = random_complex(rng, condensed.reduced_size)
    error = storage_u - condensed.recover_storage(z2, full_rhs=f)
    homogeneous = condensed.recover_storage(
        z - z2, full_rhs=f
    ) - condensed.recover_storage(np.zeros_like(z), full_rhs=f)
    points, _ = __import__("basix").make_quadrature(
        __import__("basix").CellType.quadrilateral, 30
    )
    interior_trace = np.concatenate(
        [
            element.tabulate(0, np.column_stack((points, np.full(len(points), zz))))[0][
                :, element.entity_dofs[3][0], :2
            ].ravel()
            for zz in (0.0, 1.0)
        ]
    )
    vectors = {
        "x": x,
        "y": y,
        "f": f,
        "g": g,
        "alpha": alpha,
        "u_storage": storage_u,
        "u_expanded": expanded,
        "slaves": lit["slaves"],
        "interiors": interior,
        "volume": volume(x),
        "volume_oracle": oracle @ x,
        "full_action": coupled.apply(x),
        "full_action_oracle": oracle @ x
        + native["C_native"] @ (native["D_native"] @ x),
        "adjoint": coupled.apply(y, adjoint=True),
        "adjoint_oracle": oracle.conjugate().T @ y
        + native["D_native"].conjugate().T @ (native["C_native"].conjugate().T @ y),
        "r_FE": rFE,
        "r_port": rport,
        "r_native": rnative,
        "B_rport": native["C_native"] @ rport,
        "local_internal_balance": rFE[interior],
        "condensed_identity_left": audit["augmented_fe_residual"],
        "condensed_identity_right": rFE,
        "affine_error_correct": error,
        "affine_error_subtraction": homogeneous,
        "internal_trace_values": interior_trace,
        "reduced_rhs": reduced_rhs,
        "z": z,
        "native_identity_from_existing": audit["native_residual"],
        "original_internal_B": native["C_native"][interior],
        "original_internal_D": native["D_native"][:, interior],
    }
    checks = check_coupled_vectors(vectors)
    checks += qchecks
    receipts = {
        "vectors": array_file(
            folder / "coupled_vectors.npz", deduplicate=True, **vectors
        ),
        "literal": array_file(folder / "coupled_literal.npz", **lit),
        "volume": array_file(
            folder / "volume_classes.npz",
            **{f"class_{i}": a for i, a in enumerate(tensors)},
            class_indices=class_indices,
        ),
        "oracle": array_file(
            folder / "native_small_oracle.npz",
            data=oracle.data,
            indices=oracle.indices,
            indptr=oracle.indptr,
            shape=np.array(oracle.shape, np.int64),
        ),
    }
    class_meta = {
        "class_count": len(classes),
        "class_keys": list(map(repr, classes)),
        "local_LU_recovery_Schur_cache_bytes": payload,
        "original_tensor_bytes": sum(a.nbytes for a in tensors),
        "local_internal_rows": 450,
        "retained_identity": "raw_unrounded+material+orientation+source",
        "global_LU": False,
        "local_internal_LU_present": True,
    }
    oracle_mat.destroy()
    return {
        "status": "COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES"
        if all(c["passed"] for c in checks)
        else "COUPLED_INTERFACE_NOT_QUALIFIED",
        "description": desc,
        "checks": checks,
        "costs": costs,
        "class_cache": class_meta,
        "volume_calls": volume.calls,
        "volume_seconds": volume.seconds,
        "adapter_cost": dict(adapter.stats),
        "small_oracle_shape": list(oracle.shape),
        "small_oracle_nnz": oracle.nnz,
        "Hp": "IMPLICIT_IDENTITY_IN_TARGET_API; witness-only 12x12 original Hp",
        "Hhat": "equals witness Hp because topology-supported Bi=Di=0",
        "boundary_projection_denominator": "distinct ordered positive H_i, D normalized once",
        "environment": environment(fe=True),
        "MPI": 1,
        "PDE_solved": False,
        "official_RTA": False,
        **receipts,
    }


def checker_stage(folder):
    adapter, _ = read_stage("ADAPTER")
    coupled, _ = read_stage("COUPLED")
    expected = witness_plan()["patches"]
    if [p["description"] for p in adapter["patches"]] != expected:
        raise ValueError("complete four native classes")
    checks = []
    action = selected_action()
    for p in adapter["patches"]:
        checks.extend(
            dict(patch=p["description"]["name"], **c)
            for c in check_adapter_vectors(read_arrays(p["vectors"]))
        )
        obj = NativeBoundaryAdapter.from_arrays(
            read_arrays(p["adapter"]), identity=p["description"]["name"]
        )
        lit = read_arrays(p["literal"])
        rebuilt, _ = build_literal_adapter(
            action.layout.polynomial.element,
            lit,
            p["description"],
            action.layout,
            obj.native_size,
            lit["slaves"],
        )
        checks.append(
            dict(
                kind="saved_entity_map_reconstruction",
                patch=p["description"]["name"],
                **metric(obj.E.toarray(), rebuilt.E.toarray()),
            )
        )
    checks.extend(check_coupled_vectors(read_arrays(coupled["vectors"])))
    return {
        "status": "NATIVE_INTEGRATION_SAVED_ARRAYS_QUALIFIED"
        if all(c["passed"] for c in checks)
        else "SAVED_ARRAYS_NOT_QUALIFIED",
        "checks": checks,
        "complete_classes": 4,
        "selected_modes": 12,
        "reference_read": False,
        "PDE_solved": False,
    }


def deploy(folder):
    require_stage("CHECK", "NATIVE_INTEGRATION_SAVED_ARRAYS_QUALIFIED")
    adapter, _ = read_stage("ADAPTER")
    coupled, _ = read_stage("COUPLED")
    from scipy.sparse import csr_matrix

    p = next(p for p in adapter["patches"] if p["description"]["name"] == "xy_corner")
    a = NativeBoundaryAdapter.from_arrays(
        read_arrays(p["adapter"]), identity="xy_corner"
    )
    action = selected_action(p["description"])
    d = read_arrays(coupled["oracle"])
    oracle = csr_matrix((d["data"], d["indices"], d["indptr"]), shape=tuple(d["shape"]))
    wrapper = CoupledNativeBoundaryAction(
        a,
        action,
        lambda x, adjoint=False: oracle.conjugate().T @ x if adjoint else oracle @ x,
    )
    vectors = read_arrays(coupled["vectors"])
    began = perf_counter()
    output = wrapper.apply(vectors["x"])
    modal = wrapper.modal_rhs(vectors["g"])
    receipt = array_file(
        folder / "consumer_demo.npz",
        action=output,
        modal=modal,
        amplitudes=wrapper.port_extract(vectors["x"]),
    )
    checks = [
        dict(
            kind="frozen_callback_demo", **metric(output, vectors["full_action_oracle"])
        )
    ]
    return {
        "status": "WITNESS_INTEGRATION_CONSUMER_READY"
        if all(c["passed"] for c in checks)
        else "CONSUMER_NOT_QUALIFIED",
        "checks": checks,
        "arrays": receipt,
        "seconds": perf_counter() - began,
        "interfaces": [
            "extract",
            "scatter",
            "boundary.apply(adjoint=...)",
            "port_extract",
            "modal_rhs",
            "volume_apply(x,adjoint=...)",
            "implicit hp_apply",
        ],
        "dtype": "complex128 finite exact shape; independent native slave-zero storage",
        "ownership": "whole entity owner once, conjugate MPC pullback; physical expanded copy isolated",
        "lifecycle": "immutable input snapshot; q/geometry/mode change requires new object; release callback, adapter, Fourier cache after actor",
        "MPI_qualification": 1,
        "global_target_native_rows": "UNKNOWN_NOT_CONSTRUCTED",
        "target_solve": False,
        "neural_training": False,
        "global_factor_or_QR": False,
    }


def execute(role, folder, state):
    plan_record()
    window.guard_worker_parent()
    function = {
        "EVIDENCE": evidence,
        "ADAPTER": adapter_stage,
        "COUPLED": coupled_stage,
        "CHECK": checker_stage,
        "DEPLOY": deploy,
    }[role]
    return function(folder)
