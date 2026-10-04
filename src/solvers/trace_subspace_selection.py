"""Complete Nedelec coefficient-selection witnesses, not a reduced PDE solve."""

from time import perf_counter

import numpy as np
from scipy.sparse import csr_matrix


def relative(actual, expected):
    num, den = float(np.linalg.norm(actual - expected)), float(np.linalg.norm(expected))
    return num / den if den else (0.0 if num == 0 else None)


def bridge_packet(arrays):
    bridge = csr_matrix((arrays["bridge_data"], arrays["bridge_indices"], arrays["bridge_indptr"]),
                        shape=tuple(arrays["shape"]), copy=False)
    ntrace = int(arrays["offsets"][np.flatnonzero(arrays["sizes"] == 450)[0]])
    return bridge, ntrace


def bridge_checks(bridge, graph):
    identity = bridge.conjugate().T @ bridge
    identity.sum_duplicates()
    rows = np.diff(identity.indptr)
    unit = bool(np.all(rows == 1) and np.array_equal(identity.indices, np.arange(bridge.shape[1]))
                and np.max(abs(identity.data - 1)) <= 1e-10)
    used = np.flatnonzero(np.diff(bridge.indptr))
    coverage = np.array_equal(used, graph["independent"])
    slaves_zero = not np.any(np.diff(bridge.indptr)[graph["slaves"]])
    return {"JH_J_identity": unit, "complete_independent_coverage": bool(coverage),
            "slave_zero": bool(slaves_zero), "passed": bool(unit and coverage and slaves_zero)}


class SingleCSR:
    """Original matrix with transpose view: AH*x = conj(A.T*conj(x))."""
    def __init__(self, arrays, budget=None):
        self.matrix = csr_matrix((arrays["data"], arrays["indices"], arrays["indptr"]),
                                 shape=tuple(arrays["shape"]), copy=False)
        self.transpose = self.matrix.transpose(copy=False)
        self.budget = budget
        self.calls = {"A": 0, "AH": 0}
        self.seconds = {"A": 0.0, "AH": 0.0}
        self.payload_bytes = sum(v.nbytes for v in (self.matrix.data, self.matrix.indices, self.matrix.indptr))

    def apply(self, vector, *, adjoint=False):
        vector = np.asarray(vector, np.complex128)
        kind = "AH" if adjoint else "A"
        def operation(value):
            return np.conjugate(self.transpose @ np.conjugate(value)) if adjoint else self.matrix @ value
        began = perf_counter()
        result = self.budget.call(operation, vector, kind=kind) if self.budget else operation(vector)
        self.calls[kind] += 1 if vector.ndim == 1 else vector.shape[1]
        self.seconds[kind] += perf_counter() - began
        return result


def wave_parameters(seed, family, bounds, rules):
    rng = np.random.default_rng(seed)
    directions = rng.normal(size=(2, 3))
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    polarizations = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    polarizations /= np.linalg.norm(polarizations, axis=1)[:, None]
    amplitudes = rng.uniform(*rules["amplitude_range"], size=2)
    phase = rng.uniform(-np.pi, np.pi, size=2)
    bounds = np.asarray(bounds)
    center = bounds[:, 0] + rng.uniform(*rules["center_fraction_range"], size=3) * np.diff(bounds).ravel()
    width = rng.uniform(*rules["width_fraction_range"], size=3) * np.diff(bounds).ravel()
    return {"family": family, "seed": seed, "directions": directions,
            "polarizations": polarizations, "amplitudes": amplitudes, "phase": phase,
            "center": center, "width": width, "k0": 2*np.pi / 0.7}


def oscillatory_field(points, parameters):
    phases = parameters["k0"] * (points @ parameters["directions"].T) + parameters["phase"]
    out = (np.exp(1j*phases) * parameters["amplitudes"]) @ parameters["polarizations"]
    if parameters["family"] == "localized_two_waves":
        out *= np.exp(-0.5 * np.sum(((points-parameters["center"])/parameters["width"])**2, axis=1))[:, None]
    elif parameters["family"] != "two_waves":
        raise ValueError("unregistered field family")
    return out


def interpolate_complete(element, literal, parameters, *, independent=False):
    """Affine covariant Piola, all x/M, and genuine p6 DOF transformations."""
    from src.solvers.distributed_entity_volume import cell_transform

    xyz, cells = literal["coordinates"], literal["cell_vertices"]
    rows = literal["cell_native_dofs"]
    total = int(np.max(rows)) + 1
    native, count = np.zeros(total, complex), np.zeros(total, np.int32)
    maximum_duplicate = 0.0
    local_all = []
    # A single reusable transformation, not a class cache of new local factors.
    for cell, vertices in enumerate(cells):
        p = xyz[vertices]
        jacobian = np.column_stack((p[1]-p[0], p[2]-p[0], p[4]-p[0]))
        reference = __import__("basix").cell.geometry(element.cell_type)
        if relative(reference @ jacobian.T + p[0], p) > 1e-12 or np.linalg.det(jacobian) <= 0:
            raise ValueError("saved geometry is not the original positive affine hex")
        if independent:
            moments = np.zeros(element.dim, complex)
            for dimension in range(4):
                for entity, points in enumerate(element.x[dimension]):
                    if not len(points):
                        continue
                    pulled = oscillatory_field(points @ jacobian.T + p[0], parameters) @ jacobian
                    values = np.einsum("mvq,qv->m", element.M[dimension][entity][..., 0], pulled)
                    moments[element.entity_dofs[dimension][entity]] = values
            transform = cell_transform(element, int(literal["cell_permutations"][cell]))
            oriented = transform @ moments
        else:
            points = element.points
            pulled = oscillatory_field(points @ jacobian.T + p[0], parameters) @ jacobian
            moments = element.interpolation_matrix @ pulled.T.ravel()
            real, imag = moments.real.copy(), moments.imag.copy()
            element.T_apply(real, 1, int(literal["cell_permutations"][cell]))
            element.T_apply(imag, 1, int(literal["cell_permutations"][cell]))
            oriented = real + 1j*imag
        ids = rows[cell]
        previous = count[ids] > 0
        if np.any(previous):
            scale = max(float(np.linalg.norm(oriented[previous])), np.finfo(float).tiny)
            maximum_duplicate = max(maximum_duplicate, float(np.linalg.norm(native[ids[previous]]/count[ids[previous]]-oriented[previous]))/scale)
        np.add.at(native, ids, oriented)
        np.add.at(count, ids, 1)
        local_all.append(oriented)
    if np.any(count == 0):
        raise ValueError("full native coefficient interpolation coverage")
    return native/count, np.asarray(local_all), maximum_duplicate


def expand_mpc(carrier, literal):
    expanded = carrier.copy()
    for row in literal["slave_local_dofs"]:
        lo, hi = literal["MPC_offsets"][row:row+2]
        expanded[row] = literal["MPC_coefficients"][lo:hi] @ carrier[literal["MPC_masters"][lo:hi]]
    return expanded


def mask_from_scores(scores, ntrace, fraction):
    if len(scores) != ntrace or not np.isfinite(scores).all():
        raise ValueError("complete finite trace scores")
    count = int(np.floor(fraction * ntrace))
    if not 0 <= count <= ntrace:
        raise ValueError("mask budget")
    chosen = np.lexsort((np.arange(ntrace), -np.asarray(scores)))[:count]
    mask = np.zeros(ntrace, bool)
    mask[chosen] = True
    return mask


def masked_coefficients(canonical, mask):
    out = canonical.copy()
    out[:len(mask)] *= mask
    return out


def witness_metrics(canonical, selected, original_rhs, actual_residual, ntrace):
    eta = relative(selected, canonical)
    trace = relative(selected[:ntrace], canonical[:ntrace])
    numerator, denominator = float(np.linalg.norm(actual_residual)), float(np.linalg.norm(original_rhs))
    rho = numerator / denominator if denominator else (0.0 if numerator == 0 else None)
    return {"eta": eta, "trace_error": trace, "rho": rho,
            "residual_numerator": numerator, "original_rhs_denominator": denominator,
            "omitted_energy": float(np.linalg.norm(selected-canonical)**2),
            "coefficient_energy": float(np.linalg.norm(canonical)**2),
            "passed": eta is not None and trace is not None and rho is not None and eta <= 1e-4 and trace <= 1e-4 and rho <= 1e-6,
            "classification": "SUBSPACE_WITNESS_ONLY"}


def grouped_omission(canonical, selected, graph, ntrace):
    node_of = np.repeat(np.arange(len(graph["sizes"])), graph["sizes"])
    delta = canonical[:ntrace]-selected[:ntrace]
    energy = abs(delta)**2
    node_energy = np.bincount(node_of[:ntrace], weights=energy, minlength=len(graph["sizes"]))
    groups = {}
    for dimension in (1, 2):
        for direction in (0, 1, 2):
            active = (graph["keys"][:, 0] == dimension) & (graph["keys"][:, 1] == direction)
            groups[f"entity{dimension}_direction{direction}"] = float(np.sum(node_energy[active]))
    hardest = np.argsort(-energy, kind="stable")[:8]
    details = [{"canonical_id": int(i), "entity_key": graph["keys"][node_of[i]].tolist(),
                "moment_index": int(i-graph["offsets"][node_of[i]]),
                "center_nm": graph["centers"][node_of[i]].tolist(), "omitted_energy": float(energy[i])} for i in hardest]
    return {"groups": groups, "hardest_coefficients": details,
            "squared_sum_matches": bool(abs(sum(groups.values())-float(energy.sum())) <= 1e-10*max(float(energy.sum()), np.finfo(float).tiny))}
