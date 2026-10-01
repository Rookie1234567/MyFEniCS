"""Common-point field/curl energies without full high-order AD/JIT tables."""

import numpy as np


class BoundedFieldIntegrals:
    def __init__(self, mesh, k0):
        import basix

        self.mesh, self.k0 = mesh, k0
        mesh.topology.create_entity_permutations()
        self.infos = mesh.topology.get_cell_permutation_info()
        vertices = basix.cell.geometry(basix.CellType.hexahedron)
        self.fit_matrix = np.column_stack((np.ones(8), vertices))
        self.geometry = []
        for cell in range(mesh.topology.index_map(3).size_local):
            x = mesh.geometry.x[mesh.geometry.dofmap[cell]].copy()
            x -= x[0]
            fit = np.linalg.lstsq(self.fit_matrix, x, rcond=None)[0]
            J = fit[1:].T
            if (
                np.linalg.norm(self.fit_matrix @ fit - x) > 1e-11
                or np.linalg.det(J) <= 0
            ):
                raise ValueError("BOUNDED_INTEGRAL_AFFINE_GEOMETRY_FAILED")
            self.geometry.append(J)

    def coefficients(self, field):
        space = field.function_space
        element = space.element.basix_element
        local = np.asarray(field.x.array[np.asarray(space.dofmap.list)]).copy()
        cache = {}
        for cell, info in enumerate(self.infos):
            if int(info) not in cache:
                T = np.eye(element.dim).ravel()
                space.element.T_apply(T, np.asarray([info], np.uint32), element.dim)
                cache[int(info)] = T.reshape(element.dim, element.dim)
            local[cell] = local[cell] @ cache[int(info)]
        return element, local

    def energies(self, field, q=15, indicator=1):
        import basix

        fields = field if isinstance(field, tuple) else (field,)
        terms = [self.coefficients(E) for E in fields]
        points, weights = basix.make_quadrature(basix.CellType.hexahedron, q)
        energies = np.zeros(2)
        mask = None if isinstance(indicator, (int, float)) else indicator.x.array
        for first_q in range(0, len(points), 128):
            section = slice(first_q, min(first_q + 128, len(points)))
            basis = []
            for element, _ in terms:
                t = element.tabulate(1, points[section])
                curl = np.stack(
                    (
                        t[2, :, :, 2] - t[3, :, :, 1],
                        t[3, :, :, 0] - t[1, :, :, 2],
                        t[1, :, :, 1] - t[2, :, :, 0],
                    ),
                    axis=2,
                )
                basis.append((t[0], curl))
            for first in range(0, len(self.geometry), 8):
                for cell in range(first, min(first + 8, len(self.geometry))):
                    scale = (
                        float(indicator)
                        if mask is None
                        else float(
                            mask[
                                indicator.function_space.dofmap.cell_dofs(cell)[0]
                            ].real
                        )
                    )
                    if scale == 0:
                        continue
                    J = self.geometry[cell]
                    determinant = np.linalg.det(J)
                    E, C = 0, 0
                    for term, ((_, coefficients), (eb, cb)) in enumerate(
                        zip(terms, basis, strict=True)
                    ):
                        sign = 1 if term == 0 else -1
                        E = E + sign * (
                            np.einsum("i,qia->qa", coefficients[cell], eb)
                            @ np.linalg.inv(J)
                        )
                        C = (
                            C
                            + sign
                            * (np.einsum("i,qia->qa", coefficients[cell], cb) @ J.T)
                            / determinant
                        )
                    energies += (
                        scale
                        * determinant
                        * np.array(
                            [
                                np.dot(weights[section], np.sum(abs(E) ** 2, axis=1)),
                                np.dot(weights[section], np.sum(abs(C) ** 2, axis=1))
                                / self.k0**2,
                            ]
                        )
                    )
        return energies
