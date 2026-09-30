"""Opt-in full p3 FE exporter and independent native interface witnesses.

There is no interior elimination or Maxwell factor in this exporter.
"""

from dataclasses import replace
from time import perf_counter

import numpy as np
from scipy import sparse

from src.common.optical_material_table import load_si_optical_constants
from src.geometry.neural_micro_pilot import geometry_config
from src.solvers.feinn_native import FullNativePacket, packet_hashes
from src.solvers.neural_fe_action_packet import array_hash


def physical_config(design, degree=3):
    material = load_si_optical_constants(design["wavelength_nm"])
    if (
        material.provenance["material_table_sha256"]
        != design["materials"]["material_table_sha256"]
        or [material.n.real, material.n.imag] != design["materials"]["si_n"]
    ):
        raise ValueError("MATERIAL_IDENTITY_MISMATCH")
    return replace(
        geometry_config(design),
        case_name="task42extra_m5_full_fe",
        nedelec_degree=degree,
        n_substrate=material.n,
        n_grating=material.n,
        mu_r=material.mu,
    ), material


def build_model(design, degree=3, marker=lambda *_: None, *, dtn_quadrature_degree=None):
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.feinn_interpolation import full_space
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
    )

    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
    ):
        raise RuntimeError("MPI1 complex128/int64 required")
    start = perf_counter()
    cfg, material = physical_config(design, degree)
    if dtn_quadrature_degree is not None:
        # Explicit authority audit freezes the original surface rule while p
        # changes; ordinary callers retain the original automatic rule.
        cfg.stage4_dtn_quadrature_degree = int(dtn_quadrature_degree)
    _, data, space, centers, tags, notch, axes = full_space(design, degree)
    floquet = build_double_floquet_mpc(space, data, cfg)
    modes, rows, mode_hash = build_dynamic_mode_inventory(cfg)
    setup = dict(
        mesh=data.mesh,
        mesh_data=data,
        spaces={degree: space},
        floquets={degree: floquet},
    )
    bundle = build_same_mesh_physical_action(
        setup,
        cfg,
        degree,
        mode_inventory=(modes, rows, mode_hash),
        volume_quadrature_metadata=(
            {"quadrature_degree": 15},
            {"quadrature_degree": 15},
        ),
    )
    record = dict(
        material=material.provenance,
        mode_manifest_sha256=mode_hash,
        modes=rows,
        channels=len(modes),
        degree=degree,
        mesh_coordinates_sha256=array_hash(data.mesh.geometry.x),
        geometry_cell_dofs_sha256=array_hash(data.mesh.geometry.dofmap),
        cell_tags_sha256=array_hash(tags),
        centers_sha256=array_hash(centers),
        cells=len(centers),
        actual_material_cell_counts={
            str(int(t)): int(sum(tags == t)) for t in np.unique(tags)
        },
        actual_notch_cells=int(sum(notch)),
        nonseparable_y_z_witness=bool(
            len(np.unique(centers[notch, 1])) > 1
            and len(np.unique(centers[notch, 2])) > 1
        ),
        native_rows=space.dofmap.index_map.size_local,
        slaves=len(floquet.mpc.slaves),
        dtn_quadrature_degree=bundle["dtn_quadrature_degree"],
        full_fe_setup_seconds=perf_counter() - start,
    )
    if not record["nonseparable_y_z_witness"]:
        raise ValueError("NONSEPARABLE_GEOMETRY_FAILED")
    marker("physical_model", record)
    return dict(
        cfg=cfg,
        data=data,
        space=space,
        floquet=floquet,
        bundle=bundle,
        centers=centers,
        tags=tags,
        axes=axes,
        record=record,
    )


def export_native(model, marker=lambda *_: None):
    from dolfinx import fem
    from src.solvers.common_3d_fields import stage4_layered_background_field
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs
    from src.solvers.hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        _tabulate_raw_tensor_class,
        _orient_cell_tensor,
    )
    from src.solvers.learned_coarse_inverse import native_numpy_apply

    start = perf_counter()
    space, mpc, bundle = model["space"], model["floquet"].mpc, model["bundle"]
    msh = space.mesh
    dofs = np.asarray(space.dofmap.list, dtype=np.int64)
    full_rows, dim = space.dofmap.index_map.size_local, space.element.basix_element.dim
    slaves = np.asarray(mpc.slaves, dtype=np.int64)
    masters = np.setdiff1d(np.arange(full_rows, dtype=np.int64), slaves)
    lookup = np.full(full_rows, -1, dtype=np.int64)
    lookup[masters] = np.arange(len(masters))
    coefficients, offsets = mpc.coefficients()
    erows, eids, evals = [], [], []
    for cell, rows in enumerate(dofs):
        for position, row in enumerate(rows):
            if lookup[row] >= 0:
                ids, vals = [lookup[row]], [1 + 0j]
            else:
                links = mpc.masters.links(int(row))
                ids, vals = lookup[links], coefficients[offsets[row] : offsets[row + 1]]
                if np.any(ids < 0):
                    raise ValueError("chained MPC or incomplete independent masters")
            erows.extend([cell * dim + position] * len(ids))
            eids.extend(ids)
            evals.extend(vals)
    compiled = fem.form(bundle["volume_action"].bilinear_form)
    kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
    msh.topology.create_entity_permutations()
    infos = msh.topology.get_cell_permutation_info()
    tensors, classes, cache = [], [], {}
    for cell, tag in enumerate(model["tags"]):
        coordinates = np.array(
            msh.geometry.x[msh.geometry.dofmap[cell]], dtype=np.float64
        )
        coordinates -= coordinates[0]
        key = (int(tag), coordinates.tobytes(), int(infos[cell]))
        if key not in cache:
            tensor = _tabulate_raw_tensor_class(
                compiled, kernels, coordinates, tag=int(tag), dimension=dim
            )
            _orient_cell_tensor(
                space.element, tensor, np.asarray([infos[cell]], dtype=np.uint32)
            )
            cache[key] = len(tensors)
            tensors.append(tensor)
        classes.append(cache[key])
    br, bp, bv, dr, dp, dv, H = [], [], [], [], [], [], []
    for port, entry in enumerate(bundle["dtn_action"].carrier.entries):
        b, d = lookup[entry.coupling_rows], lookup[entry.projection_rows]
        if np.any(b < 0) or np.any(d < 0):
            raise ValueError("DtN did not apply MPC exactly once")
        br.extend(b)
        bp.extend([port] * len(b))
        bv.extend(entry.coupling_values)
        dr.extend(d)
        dp.extend([port] * len(d))
        dv.extend(entry.projection_values)
        H.append(entry.normalization_h)
    rhs, rhs_facts = build_physical_rhs(bundle)
    try:
        total_g = rhs.array[masters].copy()
    finally:
        rhs.destroy()
    background_storage = stage4_layered_background_field(
        space, model["cfg"]
    ).x.array.copy()
    background_storage[slaves] = 0
    background = background_storage[masters]
    arrays = dict(
        F=np.asarray(tensors),
        classes=np.asarray(classes, dtype=np.int64),
        cell_dofs=dofs,
        masters=masters,
        slaves=slaves,
        erows=np.asarray(erows, dtype=np.int64),
        eids=np.asarray(eids, dtype=np.int64),
        evals=np.asarray(evals, dtype=np.complex128),
        br=np.asarray(br, dtype=np.int64),
        bp=np.asarray(bp, dtype=np.int64),
        bv=np.asarray(bv, dtype=np.complex128),
        dr=np.asarray(dr, dtype=np.int64),
        dp=np.asarray(dp, dtype=np.int64),
        dv=np.asarray(dv, dtype=np.complex128),
        H=np.asarray(H, dtype=np.float64),
        full_rows=np.asarray(full_rows),
        idofs=dofs[:, space.element.basix_element.entity_dofs[3][0]],
        g=total_g.copy(),
        gp=np.zeros(len(H), dtype=np.complex128),
        total_g=total_g,
        background=background,
        background_alpha=np.zeros(len(H), dtype=np.complex128),
    )
    provisional = FullNativePacket(arrays)
    native = native_numpy_apply(bundle)
    bg_native = native(background_storage)[masters]
    bg_packet = provisional.apply(background)
    shift_relative = float(
        np.linalg.norm(bg_native - bg_packet) / np.linalg.norm(bg_native)
    )
    if shift_relative > 1e-10:
        raise ValueError(f"original background affine shift failed: {shift_relative}")
    arrays = dict(
        arrays,
        g=total_g - bg_native,
        background_alpha=provisional.port_solve(provisional.D(background)),
    )
    packet = FullNativePacket(arrays)
    record = dict(
        model["record"],
        full_independent_rows=packet.size,
        interior_rows=packet.a["idofs"].size,
        local_tensor_classes=len(tensors),
        local_tensor_payload_bytes=packet.a["F"].nbytes,
        packet_payload_bytes=sum(a.nbytes for a in arrays.values()),
        packet_array_hashes=packet_hashes(packet),
        rhs=rhs_facts,
        affine_background_native_relative=shift_relative,
        export_seconds=perf_counter() - start,
        global_Maxwell_matrix_created=False,
        interior_elimination=False,
    )
    marker("full_native_export", record)
    return packet, record


def native_gate(model, packet):
    from src.solvers.learned_coarse_inverse import native_numpy_apply

    rng = np.random.default_rng(421002)
    native = native_numpy_apply(model["bundle"])
    samples = []
    for _ in range(3):
        c = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
        y = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
        ac, ahy = packet.apply(c), packet.apply(y, adjoint=True)
        expected = native(packet.storage(c))[packet.a["masters"]]
        alpha = packet.alpha(c)
        top = packet.volume(c) + packet.B(alpha) - packet.a["g"]
        bottom = -packet.D(c) + packet.a["H"] * alpha - packet.a["gp"]
        scale = np.linalg.norm(ac) * np.linalg.norm(y) + np.linalg.norm(
            ahy
        ) * np.linalg.norm(c)
        samples.append(
            dict(
                original_native_relative=float(
                    np.linalg.norm(ac - expected) / np.linalg.norm(expected)
                ),
                adjoint_dot_relative=float(
                    abs(np.vdot(y, ac) - np.vdot(ahy, c)) / scale
                ),
                augmented_native_relative=float(
                    np.linalg.norm(top - (ac - packet.f))
                    / np.linalg.norm(ac - packet.f)
                ),
                original_port_operation_relative=float(
                    np.linalg.norm(bottom)
                    / (
                        np.linalg.norm(packet.D(c))
                        + np.linalg.norm(packet.a["H"] * alpha)
                    )
                ),
                arbitrary_interior_norm=float(
                    np.linalg.norm(packet.storage(c)[packet.a["idofs"]])
                ),
            )
        )
    gp = rng.standard_normal(packet.np) + 1j * rng.standard_normal(packet.np)
    g = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
    shifted = FullNativePacket(dict(packet.a, g=g, gp=gp))
    alpha = shifted.alpha(c)
    top = shifted.volume(c) + shifted.B(alpha) - g
    bottom = shifted.a["H"] * alpha - shifted.D(c) - gp
    load_pair = float(
        np.linalg.norm(top - (shifted.apply(c) - shifted.f)) / np.linalg.norm(top)
    )
    port = float(
        np.linalg.norm(bottom)
        / (
            np.linalg.norm(gp)
            + np.linalg.norm(shifted.D(c))
            + np.linalg.norm(shifted.a["H"] * alpha)
        )
    )
    passed = (
        all(s[k] <= 1e-10 for s in samples for k in s if k != "arbitrary_interior_norm")
        and max(load_pair, port) <= 1e-10
    )
    return dict(
        status="PASS" if passed else "PORT_ELIMINATION_NOT_QUALIFIED",
        samples=samples,
        nonzero_FE_and_port_load_relative=load_pair,
        nonzero_port_load_operation_relative=port,
        actual_blocks="[V B; -D H], A=V+B solve(H,D), f=g-B solve(H,gp)",
        port_original_diagonal_min=float(np.min(packet.a["H"])),
        port_original_diagonal_max=float(np.max(packet.a["H"])),
        explicit_port_inverse_created=False,
        full_FE_retained=packet.size,
    )


def assemble_gram(model, design):
    from dolfinx import fem
    import dolfinx_mpc
    import ufl

    start = perf_counter()
    space, mpc = model["space"], model["floquet"].mpc
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=space.mesh, metadata={"quadrature_degree": 15})
    ell = design["riesz"]["ell_nm"]
    form = fem.form(
        (ufl.inner(u, v) + ell**2 * ufl.inner(ufl.curl(u), ufl.curl(v))) * dx
    )
    matrix = dolfinx_mpc.assemble_matrix(form, mpc)
    try:
        matrix.assemble()
        p, i, x = matrix.getValuesCSR()
        native = sparse.csr_matrix(
            (x.copy(), i.copy(), p.copy()), shape=matrix.getSize()
        )
    finally:
        matrix.destroy()
    masters = np.setdiff1d(np.arange(native.shape[0]), mpc.slaves)
    G = native[masters, :][:, masters].tocsr()
    G.eliminate_zeros()
    G.sort_indices()
    norm = sparse.linalg.norm(G)
    defect = float(sparse.linalg.norm(G - G.conj().T) / norm)
    rng = np.random.default_rng(421002)
    positives = []
    for _ in range(3):
        z = rng.standard_normal(len(masters)) + 1j * rng.standard_normal(len(masters))
        value = np.vdot(z, G @ z)
        positives.append(
            dict(
                real=float(value.real),
                imaginary_relative=float(abs(value.imag) / value.real),
            )
        )
    if defect > 1e-12 or any(
        v["real"] <= 0 or v["imaginary_relative"] > 1e-12 for v in positives
    ):
        raise ValueError("GRAM_VARIATIONAL_GATE_FAILED")
    return G, dict(
        label="RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR",
        rows=G.shape[0],
        nnz=G.nnz,
        ell_nm=ell,
        coordinate_unit="nm; no variable rescaling",
        material_independent=True,
        constrained_projection_count=1,
        masters_sha256=array_hash(masters),
        hermitian_relative=defect,
        nonzero_positive_forms=positives,
        csr_payload_bytes=G.data.nbytes + G.indices.nbytes + G.indptr.nbytes,
        csr_hashes={
            name: array_hash(value)
            for name, value in [
                ("indptr", G.indptr),
                ("indices", G.indices),
                ("data", G.data),
            ]
        },
        assembly_seconds=perf_counter() - start,
        SPD_proof="positive mass on linearly independent full MPC basis; successful LLH factor required",
    )


def positive_smoke():
    """Eight-cell unit cube diagnostic with analytic complex polynomial boundary."""
    import basix.ufl
    import ufl
    from dolfinx import fem, mesh
    from dolfinx.fem import petsc as fp
    from mpi4py import MPI
    from petsc4py import PETSc

    msh = mesh.create_unit_cube(
        MPI.COMM_WORLD, 2, 2, 2, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 3))
    x = ufl.SpatialCoordinate(msh)
    exact = ufl.as_vector(
        (
            1 + x[1] ** 2 + 0.1j * x[2],
            x[0] ** 2 + 0.2j * x[2] ** 2,
            x[2] ** 2 + 0.3j * x[0] * x[1],
        )
    )
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": 15})
    a = fem.form((ufl.inner(ufl.curl(u), ufl.curl(v)) + ufl.inner(u, v)) * dx)
    L = fem.form(ufl.inner(ufl.curl(ufl.curl(exact)) + exact, v) * dx)
    analytic = fem.Function(space)
    analytic.interpolate(fem.Expression(exact, space.element.interpolation_points))
    facets = mesh.locate_entities_boundary(msh, 2, lambda p: np.full(p.shape[1], True))
    dofs = fem.locate_dofs_topological(space, 2, facets)
    bc = fem.dirichletbc(analytic, dofs)
    A = fp.assemble_matrix(a, bcs=[bc])
    A.assemble()
    b = fp.assemble_vector(L)
    fp.apply_lifting(b, [a], bcs=[[bc]])
    b.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
    fp.set_bc(b, [bc])
    solution = fem.Function(space)
    ksp = PETSc.KSP().create(MPI.COMM_WORLD)
    try:
        ksp.setOperators(A)
        ksp.setType("preonly")
        ksp.getPC().setType("lu")
        ksp.getPC().setFactorSolverType("mumps")
        ksp.solve(b, solution.x.petsc_vec)
        residual = b.duplicate()
        A.mult(solution.x.petsc_vec, residual)
        residual.axpy(-1, b)
        relative = residual.norm() / b.norm()
        residual.destroy()
        error = solution - analytic
        err = np.sqrt(
            max(0, fem.assemble_scalar(fem.form(ufl.inner(error, error) * dx)).real)
        )
        scale = np.sqrt(
            fem.assemble_scalar(fem.form(ufl.inner(analytic, analytic) * dx)).real
        )
        coefficient = np.linalg.norm(
            solution.x.array - analytic.x.array
        ) / np.linalg.norm(analytic.x.array)
        return dict(
            status="PASS"
            if max(relative, err / scale, coefficient) <= 1e-10
            else "MANUFACTURED_FAILED",
            residual_relative=relative,
            L2_relative=err / scale,
            coefficient_relative=coefficient,
            cells=8,
            degree=3,
            positive_mass=1,
            positive_curl=1,
            wavelength_nm=None,
            role="analytic positive diagnostic; never M5 training data",
        )
    finally:
        ksp.destroy()
        A.destroy()
        b.destroy()
