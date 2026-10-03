"""Saved full-field error/residual geometry, one charged sparse G lifecycle."""

from pathlib import Path
from time import perf_counter
import numpy as np
from scipy import sparse

from src.solvers.feinn_native import load_native
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.feinn_error_geometry import reference_label
from src.solvers.feinn_saved_state import checked_entry
from src.solvers.feinn_diagnostic_algebra import energy, quadratic_change, weighted_qr
from src.solvers.neural_fe_action_packet import operation_relative, array_hash
from src.solvers.feinn_discretization_audit import atomic_npz
from src.runners.feinn_workflow import write_json


class DiagnosticActions:
    def __init__(self, packet, G, factor, limits, manifest):
        self.packet, self.G, self.factor, self.limits = packet, G, factor, limits
        self.G_count = 0
        self.cutoff = (
            manifest["supervision_budget_origin_monotonic"]
            + manifest["supervised_limit_seconds"]
            - 150
        )

    def guard(self, kind=None):
        if perf_counter() >= self.cutoff:
            raise RuntimeError("DIAGNOSTIC_SAVE_RESERVE")
        counts = self.record()
        if kind and counts[kind] >= self.limits[kind]:
            raise RuntimeError("DIAGNOSTIC_OPERATION_CAP_" + kind)

    def A(self, v, adjoint=False):
        self.guard("AH" if adjoint else "A")
        return self.packet.apply(np.asarray(v, np.complex128), adjoint=adjoint)

    def gm(self, v):
        self.guard("G_matvec")
        self.G_count += 1
        return self.G @ v

    def solve(self, v):
        self.guard("Gsolve")
        self.guard("G_matvec")
        return self.factor.solve(v)

    def record(self):
        return dict(
            A=self.packet.counts["A"],
            AH=self.packet.counts["AH"],
            Gsolve=self.factor.solves,
            G_matvec=self.G_count + self.factor.solves,
        )


def frozen_fields(index, names=None):
    with np.load(checked_entry(index["files"]["fields"]), allow_pickle=False) as data:
        return {k: np.array(data[k]) for k in (data.files if names is None else names)}


def run(stage, design, pre, artifact, marker, manifest, load_index):
    native, ref = load_index("e1_fe"), load_index("e3_reference")
    packet = load_native(checked_entry(native["files"]["native"]))
    c_ref, identity = reference_label(native, ref, packet)
    fields = frozen_fields(load_index("v12_saved_state_freeze"))
    historical = load_index("v11_phase_block_metric")
    decline_history = {
        f"M{x['accepted_outer']}": x
        for x in historical["result"]["accepted_history"]
        if 90 <= x["accepted_outer"] <= 95
    }
    for name, entry in pre["decline_steps"].items():
        if (
            decline_history[name]["checkpoint"]["sha256"]
            != entry["durable_final"]["sha256"]
        ):
            raise ValueError("DECLINE_SCALAR_STATE_HASH_MISMATCH")
    G = sparse.load_npz(checked_entry(native["files"]["gram"]))
    factor = None
    rows, steps, vectors = {}, [], {}
    result = dict(
        status="DIAGNOSTIC_PARTIAL",
        no_training=True,
        optimizer_steps=0,
        data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
        reference_used_for_training=False,
        reference_used_for_diagnostic=True,
        pde_only_solve=False,
        production_initialization_allowed=False,
        pde_only_solver_qualified=False,
        official_candidate_results=False,
        source_sha=manifest["source_sha"],
        reference=identity,
        Maxwell_factor_created=False,
        Maxwell_CSR_created=False,
        rows=rows,
        steps=steps,
    )
    result["decline_scalar_source"] = historical["files"]["result"]
    try:
        factor = SparseRiesz(G, design, marker)
        ops = DiagnosticActions(packet, G, factor, pre["B"], manifest)
        qf = ops.solve(packet.f)
        d_G = energy(packet.f, qf)
        Gref = ops.gm(c_ref)
        d_ref = energy(c_ref, Gref)
        r_ref = ops.A(c_ref) - packet.f
        vectors.update(f=packet.f, qf=qf, c_ref=c_ref, Gref=Gref, r_ref=r_ref)
        computed = {}
        for name, c in fields.items():
            e = c - c_ref
            r = ops.A(c) - packet.f
            Ae = ops.A(e)
            Ge, qr, qe = ops.gm(e), ops.solve(r), ops.solve(Ae)
            scale = np.linalg.norm(Ae) + np.linalg.norm(r) + np.linalg.norm(r_ref)
            defect = operation_relative(np.linalg.norm(Ae - (r - r_ref)), scale)
            row = dict(
                error_residual_defect=defect,
                error_residual_operation_scale=float(scale),
                field_G_squared=energy(e, Ge),
                field_G_denominator=d_ref,
                E_G=float(np.sqrt(energy(e, Ge) / d_ref)),
                dual_residual_squared=energy(r, qr),
                dual_denominator=d_G,
                dual_loss=energy(r, qr) / (2 * d_G),
                native_absolute=float(np.linalg.norm(r)),
                native_denominator=packet.bnorm,
                native_relative=float(np.linalg.norm(r) / packet.bnorm),
                dual_error_image_squared=energy(Ae, qe),
                directional_A_gain=float(np.sqrt(energy(Ae, qe) / energy(e, Ge))),
                total_scattered_difference_numerator_defect=float(
                    np.linalg.norm(
                        (c + packet.a["background"] - (c_ref + packet.a["background"]))
                        - e
                    )
                    / (np.linalg.norm(e) + np.linalg.norm(c) + np.linalg.norm(c_ref))
                ),
                reference_exposed=pre["states"].get(
                    name, pre["decline_steps"].get(name, {})
                )["reference_exposed"],
                c_sha256=array_hash(c),
            )
            if defect > 1e-10:
                raise ValueError("SAVED_ERROR_RESIDUAL_IDENTITY_FAILED_" + name)
            rows[name] = row
            computed[name] = dict(c=c, e=e, r=r, Ae=Ae, Ge=Ge, qr=qr, qe=qe)
            vectors.update({name + "_" + k: v for k, v in computed[name].items()})
            marker(
                "saved_geometry",
                dict(state=name, native=row["native_relative"], E_G=row["E_G"]),
            )
        previous = "M3600"
        for nxt in ["M90", "M91", "M92", "M93", "M94", "M95", "Mfinal"]:
            if nxt == "Mfinal":
                continue
            if previous not in computed or nxt not in computed:
                steps.append(dict(start=previous, end=nxt, status="NOT_RETAINED"))
                previous = nxt
                continue
            a, b = computed[previous], computed[nxt]
            delta = b["c"] - a["c"]
            Ad = ops.A(delta)
            Gd, qd = ops.gm(delta), ops.solve(Ad)
            field = quadratic_change(a["e"], delta, a["Ge"], Gd)
            dual = quadratic_change(a["r"], Ad, a["qr"], qd)
            meta = decline_history[nxt]
            row = dict(
                start=previous,
                end=nxt,
                status="MEASURED_OFFLINE_NO_UPDATE",
                field=field,
                residual=dual,
                dual_loss_change=dual["change"] / (2 * d_G),
                native_before=rows[previous]["native_relative"],
                native_after=rows[nxt]["native_relative"],
                pred=meta["pred"],
                ared=meta["ared"],
                eta=meta["eta"],
                trial_loss=meta["trial_loss"],
                CG_iterations=meta["cg"]["iterations"],
                original_parameter_CG_true_relative=meta["cg"][
                    "original_parameter_true_relative"
                ],
                parameter_step_norm=meta["accepted_update_norm"],
                parameter_relative_step=meta["accepted_relative_update"],
                prediction_loss_defect=abs(dual["change"] / (2 * d_G) + meta["ared"])
                / max(abs(meta["ared"]), rows[previous]["dual_loss"]),
                nonlinear_pred_minus_ared=meta["pred"] - meta["ared"],
            )
            if (
                max(field["defect"], dual["defect"], row["prediction_loss_defect"])
                > 1e-8
            ):
                raise ValueError("DECLINE_QUADRATIC_RECONSTRUCTION_FAILED_" + nxt)
            steps.append(row)
            vectors.update(
                {
                    nxt + "_delta": delta,
                    nxt + "_Adelta": Ad,
                    nxt + "_Gdelta": Gd,
                    nxt + "_qdelta": qd,
                }
            )
            marker(
                "decline_step",
                dict(
                    start=previous,
                    end=nxt,
                    cross=field["cross"],
                    update=field["update_energy"],
                ),
            )
            previous = nxt
        a, b = computed["M3600"], computed["Mfinal"]
        delta = b["c"] - a["c"]
        Ad = ops.A(delta)
        Gd = ops.gm(delta)
        qd = ops.solve(Ad)
        result["decline_total"] = dict(
            field=quadratic_change(a["e"], delta, a["Ge"], Gd),
            residual=quadratic_change(a["r"], Ad, a["qr"], qd),
        )
        directions = [
            computed["phase75"]["e"],
            a["e"],
            b["e"],
            computed["Ifinal"]["e"],
            a["c"] - computed["phase75"]["c"],
            delta,
            computed["Ifinal"]["c"] - computed["phase75"]["c"],
            computed["M90"]["c"] - a["c"],
        ]
        names = pre["B"]["field_directions"]
        X = np.column_stack(directions)
        GX = np.column_stack([ops.gm(x) for x in directions])
        AX = np.column_stack([ops.A(x) for x in directions])
        QAX = np.column_stack([ops.solve(x) for x in AX.T])
        qr = weighted_qr(X, GX, real=False, qr_tol=1e-10)
        U, sig, _ = np.linalg.svd(qr["R"], full_matrices=False)
        keep = sig > 1e-10 * sig[0]
        T = qr["T"] @ U[:, keep]
        images, duals = AX @ T, QAX @ T
        H = images.conj().T @ duals
        H = (H + H.conj().T) / 2
        eigen = np.linalg.eigvalsh(H)
        result["finite_field_subspace"] = dict(
            names=names,
            columns=8,
            rank=int(sum(keep)),
            QR_rank=qr["QR_rank"],
            singular_values=sig.tolist(),
            field_orthogonality=qr["G_orthogonality"],
            field_reconstruction=qr["normalized_reconstruction"],
            image_energy_eigenvalues=eigen.tolist(),
            gain_min=float(np.sqrt(max(0, eigen[0]))),
            gain_max=float(np.sqrt(max(0, eigen[-1]))),
            eigenvalue_ratio=float(eigen[-1] / eigen[0]) if eigen[0] > 0 else None,
            individual_gain=[
                float(np.sqrt(energy(AX[:, i], QAX[:, i]) / energy(X[:, i], GX[:, i])))
                for i in range(8)
            ],
            field_span="finite observed complex field directions",
            global_inf_sup_or_condition_number=False,
        )
        if max(qr["G_orthogonality"], qr["normalized_reconstruction"]) > 1e-8:
            raise ValueError("OBSERVED_FIELD_SUBSPACE_DECOMPOSITION_UNSTABLE")
        vectors.update(
            direction_X=X,
            direction_GX=GX,
            direction_AX=AX,
            direction_qAX=QAX,
            small_T=T,
            small_image_H=H,
        )
        result.update(
            status="SAVED_FIELD_ATTRIBUTION_COMPLETE",
            C_admitted=True,
            d_G=d_G,
            d_ref=d_ref,
            native_f_norm=packet.bnorm,
            p3_reference_native=float(np.linalg.norm(r_ref) / packet.bnorm),
            no_parameter_updates=True,
        )
    finally:
        if factor is not None:
            result.update(
                actions=ops.record() if "ops" in locals() else {},
                Gram_factor=factor.record,
            )
            factor.close()
        path = Path(artifact) / "attribution_vectors.npz"
        atomic_npz(path, **vectors)
        write_json(Path(artifact) / "partial_attribution.json", result)
    return result, dict(vectors=path)
