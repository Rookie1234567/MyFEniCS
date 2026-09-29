"""Opt-in, fixed Gram-diagonal coordinates for the Task42extra full-FE pilot."""

import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse

from src.solvers.feinn_native import ResidualMetric, load_native
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.neural_fe_action_packet import array_hash


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(2**20):
            digest.update(block)
    return digest.hexdigest()


class GramDiagonalCoordinates:
    """c=D*y, with D from the already constrained global Hermitian Gram."""

    def __init__(self, gram):
        gram = sparse.csr_matrix(gram, dtype=np.complex128)
        diagonal = np.asarray(gram.diagonal(), dtype=np.complex128)
        if gram.shape[0] != gram.shape[1] or len(diagonal) != gram.shape[0]:
            raise ValueError("SCALING_DEFINITION_FAILED: Gram shape")
        a = diagonal.real.copy()
        imag_defect = float(
            np.max(np.abs(diagonal.imag) / np.maximum(np.abs(a), 1e-300))
        )
        if (
            not np.isfinite(diagonal).all()
            or not np.all(a > 0)
            or imag_defect > 1e-12
        ):
            raise ValueError("SCALING_DEFINITION_FAILED: diagonal positivity/Hermitian")
        self.a = a
        self.D = 1 / np.sqrt(a)
        if not np.isfinite(self.D).all() or not np.all(self.D > 0):
            raise ValueError("SCALING_DEFINITION_FAILED: nonfinite D")
        self.diagonal_imag_relative_max = imag_defect
        self.normalized_diagonal_relative_max = float(
            np.max(np.abs(self.D**2 * diagonal - 1))
        )

    def to_c(self, y):
        y = np.asarray(y, dtype=np.complex128)
        if y.shape != self.D.shape or not np.isfinite(y).all():
            raise ValueError("finite full complex y required")
        return self.D * y

    def to_y(self, c):
        c = np.asarray(c, dtype=np.complex128)
        if c.shape != self.D.shape or not np.isfinite(c).all():
            raise ValueError("finite full complex c required")
        return c / self.D

    def gradient(self, g_c):
        g_c = np.asarray(g_c, dtype=np.complex128)
        if g_c.shape != self.D.shape or not np.isfinite(g_c).all():
            raise ValueError("finite full complex coefficient gradient required")
        return self.D.conj() * g_c

    def record(self):
        return dict(
            source="already MPC-constrained global G diagonal",
            rows=len(self.D),
            a_sha256=array_hash(self.a),
            D_sha256=array_hash(self.D),
            diagonal_imag_relative_max=self.diagonal_imag_relative_max,
            normalized_diagonal_relative_max=self.normalized_diagonal_relative_max,
            formula="a=real(diag(G)); D=1/sqrt(a); c=D*y; g_y=conj(D)*g_c",
        )


def read_frozen_scale(path, gram):
    scale = GramDiagonalCoordinates(gram)
    with np.load(path, allow_pickle=False) as item:
        if set(item.files) != {"a", "D"}:
            raise ValueError("frozen scaling packet fields differ")
        if not np.array_equal(item["a"], scale.a) or not np.array_equal(
            item["D"], scale.D
        ):
            raise ValueError("frozen D differs from original constrained Gram")
    return scale


def magnitude_statistics(x):
    values = np.abs(np.asarray(x)).ravel()
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("finite nonempty statistics input required")
    points = np.quantile(values, [0, 0.01, 0.5, 0.99, 1])
    return dict(
        count=int(len(values)),
        zero_count=int(np.count_nonzero(values == 0)),
        min=float(points[0]),
        p1=float(points[1]),
        p50=float(points[2]),
        p99=float(points[3]),
        max=float(points[4]),
        norm=float(np.linalg.norm(values)),
    )


def family_masks(packet, moments):
    cells = moments["native_cell_dofs"]
    masters = packet.a["masters"]
    masks = {}
    for name, key in (("edge", "edge_positions"), ("face", "face_positions"),
                      ("interior", "interior_positions")):
        masks[name] = np.isin(masters, np.unique(cells[:, moments[key]]))
    if np.sum(np.stack(list(masks.values())), axis=0).max() != 1 or not np.all(
        np.logical_or.reduce(list(masks.values()))
    ):
        raise ValueError("edge/face/interior independent partition failed")
    if {k: int(v.sum()) for k, v in masks.items()} != {
        "edge": 3744, "face": 14400, "interior": 13824
    }:
        raise ValueError("frozen independent family counts differ")
    return masks


def _frozen_parameters(index):
    path = index["files"]["checkpoint"]["path"]
    if file_sha256(path) != index["files"]["checkpoint"]["sha256"]:
        raise ValueError("V1 committed checkpoint hash mismatch")
    with np.load(path, allow_pickle=False) as item:
        return np.array(item["parameters"]), np.array(item["c"]), {
            "state_kind": str(item["state_kind"]),
            "parameter_only": bool(item["parameter_only"]),
            "closures": int(item["closures"]),
            "committed_steps": int(item["committed_steps"]),
        }


def _history(index):
    path = index["files"]["history"]["path"]
    if file_sha256(path) != index["files"]["history"]["sha256"]:
        raise ValueError("V1 history hash mismatch")
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    closure = [row for row in rows if row["kind"] == "closure"]
    audits = [row for row in rows if row["kind"] == "audit"]
    adam = [row for row in audits if row["tag"] == "adam_committed" and row["closures"] == 500]
    return dict(
        complete_loss_gradient_rows=len(closure),
        first_complete_closure=closure[0] if closure else None,
        last_complete_closure=closure[-1] if closure else None,
        adam500_audit=adam[-1] if adam else "NOT_RETAINED",
        adam500_parameter_snapshot="NOT_RETAINED",
        accepted_inner_step_lengths="unknown_not_recorded",
        last_audit=audits[-1] if audits else None,
        last_trial_is_committed=False,
    )


def state_diagnostic(design, native_index, grad_index, route_indices, artifact, marker):
    """Evaluate only zero and three saved V1 final states; never load reference."""
    import torch

    from src.solvers.feinn_torch import CompleteMomentMap, CoordinateField
    from src.solvers.feinn_validation import assign, load_moments, parameters

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    began = perf_counter()
    packet = load_native(native_index["files"]["native"]["path"])
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    scale = GramDiagonalCoordinates(G)
    moments = load_moments(grad_index["files"]["moments"]["path"])
    masks = family_masks(packet, moments)
    path = Path(artifact) / "gram_diagonal_scale.npz"
    np.savez(path, a=scale.a, D=scale.D)
    marker("fixed_gram_diagonal_scale", scale.record())
    gram = SparseRiesz(G, design, marker)
    rows = {}
    state_pool = {"ZERO": np.zeros(packet.size, dtype=np.complex128)}
    metadata = {}
    try:
        metric = ResidualMetric(packet, gram)
        for name, index in route_indices.items():
            p, c, state = _frozen_parameters(index)
            if c.shape != (packet.size,) or c.dtype != np.complex128:
                raise ValueError("V1 saved c shape/dtype mismatch")
            history = _history(index)
            if int(index["result"]["counts"]["closures"]) != state["closures"]:
                raise ValueError("V1 history/checkpoint count mismatch")
            state_pool[name] = c
            trial_entry = index["files"]["last_trial"]
            if file_sha256(trial_entry["path"]) != trial_entry["sha256"]:
                raise ValueError("V1 last-trial hash mismatch")
            with np.load(trial_entry["path"], allow_pickle=False) as trial_item:
                trial_parameters = np.array(trial_item["parameters"])
                trial_c = np.array(trial_item["c"])
                trial_state_kind = str(trial_item["state_kind"])
            if trial_parameters.shape != p.shape or trial_c.shape != c.shape:
                raise ValueError("V1 last-trial shape mismatch")
            metadata[name] = dict(
                saved_state=state,
                checkpoint_sha256=index["files"]["checkpoint"]["sha256"],
                history_sha256=index["files"]["history"]["sha256"],
                historical_counts=index["result"]["counts"],
                stop_reason=index["result"]["stop_reason"],
                historical=history,
                last_trial=dict(
                    sha256=trial_entry["sha256"],
                    state_kind=trial_state_kind,
                    parameter_delta_from_committed_norm=float(np.linalg.norm(trial_parameters - p)),
                    c_delta_from_committed_norm=float(np.linalg.norm(trial_c - c)),
                    is_committed=bool(np.array_equal(trial_parameters, p) and np.array_equal(trial_c, c)),
                    substituted_for_final=False,
                ),
                Adam_state="NOT_RETAINED",
                LBFGS_state="NOT_RETAINED",
                initial_to_final_parameter_delta_norm=float(np.linalg.norm(p))
                if name == "FREE-FE-DUAL" else "see_network_parameter_groups",
            )
        mapping = CompleteMomentMap(moments)
        model = CoordinateField(design["geometry"]["bounds_nm"], design["network"]["seed"])
        initial_network = parameters(model)
        for name, c in state_pool.items():
            loss, _, gc = metric.value(c, gradient=True)
            gy = scale.gradient(gc)
            row = dict(
                committed_state=True,
                dual_loss=loss,
                native_and_augmented=packet.audit(c),
                fixed_dual_denominator=metric.denominator,
                families={
                    family: {
                        "G_diagonal": magnitude_statistics(scale.a[mask]),
                        "D": magnitude_statistics(scale.D[mask]),
                        "c": magnitude_statistics(c[mask]),
                        "y_for_diagnostic": magnitude_statistics(scale.to_y(c)[mask]),
                        "g_c": magnitude_statistics(gc[mask]),
                        "g_y": magnitude_statistics(gy[mask]),
                    }
                    for family, mask in masks.items()
                },
                g_c_norm=float(np.linalg.norm(gc)),
                g_y_norm=float(np.linalg.norm(gy)),
            )
            if name.startswith("FEINN-"):
                p, saved_c, _ = _frozen_parameters(route_indices[name])
                assign(model, p)
                reconstructed = mapping.forward(model)
                mismatch = np.linalg.norm(reconstructed - saved_c) / max(
                    np.linalg.norm(saved_c), 1e-12
                )
                if mismatch > 1e-10:
                    raise ValueError("V1 network checkpoint/complete moment mismatch")
                grad_p = mapping.vjp(model, gc)
                split = len(p) - (64 * 6 + 6)
                row["network_parameter_groups"] = {
                    "hidden_parameters": magnitude_statistics(p[:split]),
                    "output_parameters": magnitude_statistics(p[split:]),
                    "hidden_dual_gradient": magnitude_statistics(grad_p[:split]),
                    "output_dual_gradient": magnitude_statistics(grad_p[split:]),
                    "initial_to_final_change": magnitude_statistics(p - initial_network),
                }
                row["reconstructed_c_relative"] = float(mismatch)
            rows[name] = row
            marker("state_diagnostic_" + name, dict(loss=loss, native=row["native_and_augmented"]["native_relative"]))
        if len(rows) > 20:
            raise ValueError("D0 loss-gradient evaluation budget exceeded")
        result = dict(
            status="D0_STATE_DIAGNOSTIC_COMPLETE",
            state_evaluations=len(rows),
            retained_states=list(rows),
            missing_adam500_parameters="NOT_RETAINED",
            last_trial_substituted=False,
            scaling=scale.record(),
            states=rows,
            historical_metadata=metadata,
            original_packet_sha256=native_index["files"]["native"]["sha256"],
            original_gram_sha256=native_index["files"]["gram"]["sha256"],
            reference_loaded=False,
            gram_factor=gram.record,
            setup_and_diagnostic_seconds=perf_counter() - began,
        )
    finally:
        gram.close()
    result["gram_factor"] = gram.record
    result["action_counts"] = packet.counts
    return result, {"scale": path}


def _synthetic_checks():
    rng = np.random.default_rng(421004)
    A = rng.standard_normal((5, 5)) + 1j * rng.standard_normal((5, 5))
    B = rng.standard_normal((5, 5)) + 1j * rng.standard_normal((5, 5))
    G = B.conj().T @ B + np.diag(np.arange(1, 6))
    scale = GramDiagonalCoordinates(sparse.csr_matrix(G))
    f = rng.standard_normal(5) + 1j * rng.standard_normal(5)
    y = rng.standard_normal(5) + 1j * rng.standard_normal(5)
    z = rng.standard_normal(5) + 1j * rng.standard_normal(5)
    c = scale.to_c(y)
    r = A @ c - f
    q = np.linalg.solve(G, r)
    den = np.vdot(f, np.linalg.solve(G, f)).real
    gc = A.conj().T @ q / den
    gy = scale.gradient(gc)
    adjoint = abs(np.vdot(A @ c, z) - np.vdot(y, scale.gradient(A.conj().T @ z))) / max(abs(np.vdot(A @ c, z)), 1e-12)
    direction = rng.standard_normal((2, 5))
    direction /= np.linalg.norm(direction)
    exact = float(np.dot(np.r_[gy.real, gy.imag], direction.ravel()))
    def loss(v):
        rr = A @ scale.to_c(v) - f
        return float(np.vdot(rr, np.linalg.solve(G, rr)).real / (2 * den))
    h = 1e-5
    dv = direction[0] + 1j * direction[1]
    fd = (loss(y + h * dv) - loss(y - h * dv)) / (2 * h)
    return dict(
        A_is_complex_nonhermitian=bool(np.linalg.norm(A - A.conj().T) > 0),
        G_is_complex_hermitian_positive=bool(np.linalg.eigvalsh(G).min() > 0),
        roundtrip_relative=float(np.linalg.norm(scale.to_y(c) - y) / np.linalg.norm(y)),
        unchanged_loss=float(np.vdot(r, q).real / (2 * den)),
        AD_adjoint_relative=float(adjoint),
        gradient_relative=float(abs(fd - exact) / max(abs(exact), 1e-12)),
    )


def scaling_checks(design, native_index, grad_index, scale_index, artifact, marker):
    """Synthetic and fixed-M5 algebra/gradient/transaction qualification."""
    import torch

    from src.solvers.feinn_optimization import transactional_step
    from src.solvers.feinn_validation import load_moments

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    synthetic = _synthetic_checks()
    if max(synthetic["roundtrip_relative"], synthetic["AD_adjoint_relative"]) > 1e-10 or synthetic["gradient_relative"] > 1e-5:
        raise ValueError("synthetic scaling gate failed")
    packet = load_native(native_index["files"]["native"]["path"])
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    scale = read_frozen_scale(scale_index["files"]["scale"]["path"], G)
    gram = SparseRiesz(G, design, marker)
    try:
        metric = ResidualMetric(packet, gram)
        rng = np.random.default_rng(421005)
        algebra = []
        for _ in range(3):
            y = (rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)) * 1e-3
            z = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
            c = scale.to_c(y)
            roundtrip = np.linalg.norm(scale.to_y(c) - y) / np.linalg.norm(y)
            lhs = np.vdot(packet.apply(c), z)
            rhs = np.vdot(y, scale.gradient(packet.apply(z, adjoint=True)))
            adjoint = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-12)
            loss_c = metric.value(c)[0]
            loss_y = metric.value(scale.to_c(y))[0]
            algebra.append(dict(roundtrip_relative=float(roundtrip), AD_adjoint_relative=float(adjoint), unchanged_loss_relative=float(abs(loss_y - loss_c) / max(abs(loss_c), 1e-12))))
        y = (rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)) * 1e-3
        loss, _, gc = metric.value(scale.to_c(y), gradient=True)
        gy = scale.gradient(gc)
        masks = family_masks(packet, load_moments(grad_index["files"]["moments"]["path"]))
        derivatives = []
        for family, mask in masks.items():
            dr = np.zeros(packet.size)
            di = np.zeros(packet.size)
            dr[mask] = gy.real[mask]
            di[mask] = gy.imag[mask]
            norm = np.linalg.norm(np.r_[dr, di])
            if norm <= 1e-12:
                raise ValueError("nonzero real direction missing")
            dr, di = dr / norm, di / norm
            exact = float(np.dot(gy.real, dr) + np.dot(gy.imag, di))
            samples = []
            for h in (1e-4, 1e-5, 1e-6):
                direction = dr + 1j * di
                plus = metric.value(scale.to_c(y + h * direction))[0]
                minus = metric.value(scale.to_c(y - h * direction))[0]
                observed = (plus - minus) / (2 * h)
                samples.append(dict(h=h, relative_error=float(abs(observed - exact) / abs(exact)), observed=float(observed)))
            derivatives.append(dict(family=family, analytic=exact, samples=samples, two_consecutive_pass=any(samples[i]["relative_error"] <= 1e-5 and samples[i+1]["relative_error"] <= 1e-5 for i in (0, 1))))
        # Same transactional helper as the route: an interrupted line search must
        # restore y, and its already observed trial/cost must remain observable.
        parameter = torch.nn.Parameter(
            torch.as_tensor(np.stack((y.real, y.imag)), dtype=torch.float64).clone()
        )
        committed = parameter.detach().numpy().copy()
        transaction = dict(attempts=0, trial_loss=None, charged_closures=0)
        def read():
            return parameter.detach().numpy().copy()
        def restore(value):
            with torch.no_grad():
                parameter.copy_(torch.as_tensor(value))
        def closure():
            transaction["charged_closures"] += 1
            transaction["trial_loss"] = loss
            with torch.no_grad():
                parameter.add_(1)
            raise RuntimeError("deliberate line-search interruption")
        def step(cb):
            transaction["attempts"] += 1
            cb()
        try:
            transactional_step(step, closure, read, restore)
        except RuntimeError as error:
            if str(error) != "deliberate line-search interruption":
                raise
        transaction["restored_y_exact"] = bool(np.array_equal(read(), committed))
        transaction["saved_c_equals_Dy"] = bool(np.array_equal(
            scale.to_c(read()[0] + 1j * read()[1]), scale.to_c(y)
        ))
        passed = (
            all(max(row.values()) <= 1e-10 for row in algebra)
            and all(row["two_consecutive_pass"] for row in derivatives)
            and transaction["restored_y_exact"]
            and transaction["saved_c_equals_Dy"]
            and transaction["charged_closures"] == 1
            and transaction["trial_loss"] == loss
            and gram.max_relative <= 1e-11
        )
        result = dict(status="SCALING_CHECKS_PASS" if passed else "SCALING_CHECKS_FAIL", synthetic=synthetic, fixed_M5_algebra=algebra, nonzero_y_loss=loss, nonzero_real_parameter_directions=derivatives, transaction=transaction, scaling=scale.record(), Gsolve_max_true_relative=gram.max_relative, Gsolve_count=gram.solves, Gsolve_seconds=gram.solve_seconds, Gram_factor=gram.record, original_model_and_loss_unchanged=True, reference_loaded=False)
    finally:
        gram.close()
    result["Gram_factor"] = gram.record
    marker("scaling_checks", dict(status=result["status"], Gsolve_count=result["Gsolve_count"]))
    if not passed:
        raise ValueError("SCALING_CHECKS_FAIL")
    return result, {}
