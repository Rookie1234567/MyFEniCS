"""One frozen twelve-port B loss/adjoint witness, using current coefficients."""

import numpy as np
import torch

from benchmarks.check_boundary_witness import read_arrays
from src.solvers.isolated_ml_sparse import csr_matrix
from src.solvers.neighborhood_residual_core import ratio
from src.solvers.neighborhood_residual_models import _OriginalAction
from src.solvers.neighborhood_residual_scope import parent
from src.solvers.port_component_study import array_file


def saved_port_check(folder, budget):
    m = read_arrays(parent("Bcsr")["arrays"])
    matrix = csr_matrix((m["data"], m["indices"], m["indptr"]), shape=tuple(m["shape"]))
    matrix_adjoint = matrix.conjugate().T
    a = read_arrays(parent("Brecovery")["arrays"])
    c, d, f, g = a["C_native"], a["D_native"], a["f"], a["g"]
    if c.shape[1] != 12 or d.shape != (12, matrix.shape[0]) or not np.linalg.norm(g):
        raise ValueError("actual complete nonzero B port inventory")
    n = matrix.shape[0]
    literal = read_arrays(parent("Bgeometry")["arrays"])

    class Augmented:
        def apply(self, values, *, adjoint=False):
            def op(z):
                u, alpha = z[:n], z[n:]
                if adjoint:
                    return np.concatenate(
                        (
                            matrix_adjoint @ u - d.conjugate().T @ alpha,
                            c.conjugate().T @ u + alpha,
                        ),
                        axis=0,
                    )
                return np.concatenate((matrix @ u + c @ alpha, -d @ u + alpha), axis=0)

            return budget.call(
                op, values, key="B_actions", kind="B_AH" if adjoint else "B_A"
            )

    actor = Augmented()
    rng = np.random.default_rng(424361)
    z = rng.normal(size=n + 12) + 1j * rng.normal(size=n + 12)
    direction = rng.normal(size=n + 12) + 1j * rng.normal(size=n + 12)
    z[literal["slaves"]] = 0
    direction[literal["slaves"]] = 0
    direction /= np.linalg.norm(direction)
    offsets = literal["master_offsets"]
    expansion = csr_matrix(
        (
            literal["master_dual_coefficients"].conjugate(),
            literal["master_rows"],
            offsets,
        ),
        shape=(n, n),
    )
    current_expanded = expansion @ z[:n]
    current_dual = expansion.conjugate().T @ direction[:n]
    mpc_left = np.vdot(direction[:n], current_expanded)
    mpc_right = np.vdot(current_dual, z[:n])
    mpc_scale = float(np.linalg.norm(direction[:n]) * np.linalg.norm(current_expanded))
    mpc_passed = abs(mpc_left - mpc_right) <= 1e-10 * mpc_scale
    rhs = np.r_[f, g]
    norm2 = float(np.linalg.norm(rhs) ** 2)
    point = torch.from_numpy(z[None, :]).requires_grad_()
    residual = _OriginalAction.apply(point, actor) - torch.from_numpy(rhs[None, :])
    loss = torch.sum(abs(residual) ** 2) / (2 * norm2)
    gradient = torch.autograd.grad(loss, point)[0].numpy()[0]
    jv = actor.apply(direction)
    manual = float(np.vdot(jv, residual.detach().numpy()[0]).real / norm2)
    backward = float(np.vdot(direction, gradient).real)
    operation_scale = float(
        np.linalg.norm(jv) * np.linalg.norm(residual.detach().numpy()) / norm2
    )
    fd = []
    for h in (1e-4, 3e-5, 1e-5):
        plus = actor.apply(z + h * direction)
        minus = actor.apply(z - h * direction)
        fd.append(dict(step=h, **ratio((plus - minus) / (2 * h), jv, tol=1e-5)))
    receipt = array_file(
        folder / "B_current_gradient.npz",
        compressed=True,
        deduplicate=False,
        z=z,
        direction=direction,
        rhs=rhs,
        residual=residual.detach().numpy()[0],
        gradient=gradient,
        jvp=jv,
        current_expanded=current_expanded,
        current_dual=current_dual,
    )
    return {
        "passed": abs(manual - backward) / operation_scale <= 1e-10
        and sum(c["passed"] for c in fd) >= 2
        and mpc_passed,
        "nonzero_g_norm": float(np.linalg.norm(g)),
        "ports": 12,
        "original_Hp": "identity",
        "sign": "[V C; -D I]",
        "not_C_H": float(np.linalg.norm(d - c.conjugate().T)),
        "current_output_hash": __import__("hashlib").sha256(z.tobytes()).hexdigest(),
        "saved_producer_u_used_as_candidate": False,
        "current_slave_norm": float(np.linalg.norm(z[literal["slaves"]])),
        "current_MPC_dual": {
            "numerator": float(abs(mpc_left - mpc_right)),
            "operation_scale": mpc_scale,
            "passed": bool(mpc_passed),
        },
        "current_arrays": receipt,
        "left": manual,
        "right": backward,
        "operation_scale": operation_scale,
        "relative_dual": abs(manual - backward) / operation_scale,
        "FD_vector": fd,
        "source_bytes": {
            name: parent(name)["arrays"]["sha256"] for name in ("Bcsr", "Brecovery")
        },
        "no_new_integral_factor_or_mesh": True,
    }
