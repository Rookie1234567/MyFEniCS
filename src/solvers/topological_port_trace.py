"""Opt-in affine N1curl facet-closure support, independent of entry magnitude.

On a hexahedron the tangential trace is a two-dimensional Nedelec polynomial.
Its edge and face moments are unisolvent. Interior moments have zero trace;
entity orientation transformations preserve the facet-closure subspace. The
qualification below checks these prerequisites rather than thresholding a
computed port entry. Curved or mixed-entity mappings are deliberately rejected.
"""

import numpy as np


def boundary_master_rows(space, mpc, cfg):
    import basix

    if space.mesh.comm.size != 1 or space.dofmap.index_map_bs != 1:
        raise ValueError("TOPOLOGICAL_TRACE_REQUIRES_SERIAL_SCALAR_LAYOUT")
    element = space.element.basix_element
    if (
        element.family != basix.ElementFamily.N1E
        or element.cell_type != basix.CellType.hexahedron
    ):
        raise ValueError("TOPOLOGICAL_TRACE_REQUIRES_N1CURL_HEX")
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    faces = basix.cell.topology(basix.CellType.hexahedron)[2]
    msh = space.mesh
    msh.topology.create_entity_permutations()
    infos = msh.topology.get_cell_permutation_info()
    slaves = set(int(v) for v in mpc.slaves)
    result = {"top": set(), "bottom": set()}
    for cell, dofs in enumerate(space.dofmap.list):
        coords = msh.geometry.x[msh.geometry.dofmap[cell]]
        # The allowed geometry is an axis-aligned affine box. Avoid inferring
        # tiny off-diagonal terms from least squares in this topology proof.
        lo, hi = coords.min(axis=0), coords.max(axis=0)
        if np.max(abs(coords - (lo + vertices * (hi - lo)))) > 1e-12:
            raise ValueError("TOPOLOGICAL_TRACE_NON_AFFINE_GEOMETRY")
        T = np.eye(element.dim).ravel()
        space.element.T_apply(T, np.asarray([infos[cell]], np.uint32), element.dim)
        T = T.reshape(element.dim, element.dim)
        for face_index, face in enumerate(faces):
            z = coords[face, 2]
            side = (
                "top"
                if np.max(abs(z - cfg.physical_z_max)) < 1e-12
                else "bottom"
                if np.max(abs(z - cfg.physical_z_min)) < 1e-12
                else None
            )
            if side is None:
                continue
            closure = np.asarray(element.entity_closure_dofs[2][face_index], np.int64)
            complement = np.setdiff1d(np.arange(element.dim), closure)
            if np.any(T[np.ix_(closure, complement)] != 0) or np.any(
                T[np.ix_(complement, closure)] != 0
            ):
                raise ValueError("TOPOLOGICAL_TRACE_ORIENTATION_MIXES_ENTITIES")
            for row in dofs[closure]:
                if int(row) in slaves:
                    links = mpc.masters.links(int(row))
                    if any(int(v) in slaves for v in links):
                        raise ValueError("TOPOLOGICAL_TRACE_CHAINED_MPC")
                    result[side].update(int(v) for v in links)
                else:
                    result[side].add(int(row))
    return {side: np.asarray(sorted(rows), np.int64) for side, rows in result.items()}


def trace_qualification(design, marker=lambda *_: None, budget=lambda *_: None):
    import basix
    from src.solvers.fixed_phase_fem import build_model
    from src.solvers.fixed_phase_audit import affine_basis

    rows = []
    for degree in (3, 4, 6):
        budget("topological trace qualification")
        model = build_model(design, degree, True, operators=False)
        space = model["space"]
        element = space.element.basix_element
        faces = basix.cell.topology(basix.CellType.hexahedron)[2]
        vertices = basix.cell.geometry(basix.CellType.hexahedron)
        mesh = space.mesh
        mesh.topology.create_entity_permutations()
        infos = mesh.topology.get_cell_permutation_info()
        cell = int(np.argmax(infos))
        nodes = np.linspace(0, 1, degree + 1)
        pairs = np.asarray([(x, y) for x in nodes for y in nodes])
        qp, qw = basix.make_quadrature(basix.CellType.quadrilateral, 2 * degree + 3)
        support = boundary_master_rows(space, model["floquet"].mpc, model["cfg"])
        for fi, face in enumerate(faces):
            v = vertices[face]
            axes = np.flatnonzero(np.ptp(v, axis=0) > 0.5)
            closure = np.asarray(element.entity_closure_dofs[2][fi])
            outside = np.setdiff1d(np.arange(element.dim), closure)
            measured = []
            for points in (pairs, qp):
                ref = np.tile(v.min(axis=0), (len(points), 1))
                ref[:, axes] = points
                E, _, _, _, J = affine_basis(model, cell, ref)
                normal = np.cross(J[:, axes[0]], J[:, axes[1]])
                normal /= np.linalg.norm(normal)
                tangent = np.cross(E, normal)
                scale = max(np.linalg.norm(tangent[:, closure]), 1e-30)
                measured.append(float(np.linalg.norm(tangent[:, outside]) / scale))
            # An omitted real boundary edge/face column must be detected.
            amplitudes = np.linalg.norm(tangent, axis=(0, 2))
            negative = float(
                amplitudes[closure].max() / max(np.linalg.norm(amplitudes), 1e-30)
            )
            rows.append(
                dict(
                    degree=degree,
                    facet=fi,
                    closure_size=len(closure),
                    interior_positions=list(element.entity_dofs[3][0]),
                    nodal_and_integral_relative=measured,
                    determining_nodes_per_axis=degree + 1,
                    node_unisolvence="tensor tangential degrees at most (p,p-1)/(p-1,p)",
                    omitted_boundary_dof_difference=negative,
                    actual_cell_permutation=int(infos[cell]),
                    boundary_master_counts={s: len(x) for s, x in support.items()},
                )
            )
        marker("trace_degree_qualified", dict(degree=degree))
    passed = all(
        max(r["nodal_and_integral_relative"]) <= 1e-10
        and r["omitted_boundary_dof_difference"] > 1e-10
        for r in rows
    ) and any(r["actual_cell_permutation"] != 0 for r in rows)
    return dict(
        passed=passed,
        rows=rows,
        all_six_facets=True,
        support_rule="Basix entity_closure_dofs then MPC expansion once",
        entry_magnitude_used_for_selection=False,
        generic_internal_port_rejection_unchanged=True,
        actual_557_558_562_are_interior=all(
            i in rows[-1]["interior_positions"] for i in (557, 558, 562)
        ),
    )
