"""Bounded, reference-exposed error/residual geometry; no optimization."""

from time import perf_counter

import numpy as np
from scipy import sparse

from src.solvers.feinn_native import load_native
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.neural_fe_action_packet import operation_relative
from src.runners.feinn_workflow import sha


EXPECTED = {
    "native": "2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215",
    "gram": "2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9",
    "reference": "0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7",
}


def indexed_array(index, key, field):
    entry = index["files"][key]
    if sha(entry["path"]) != entry["sha256"]:
        raise ValueError(f"ARTIFACT_IDENTITY_FAILED: {key}")
    with np.load(entry["path"], allow_pickle=False) as item:
        return np.array(item[field])


def reference_label(native_index, reference_index, packet, *, used_for_training=False):
    if reference_index["result"]["status"] != "INDEPENDENT_REFERENCE_PASS":
        raise ValueError("REFERENCE_NOT_QUALIFIED")
    if (
        native_index["files"]["native"]["sha256"] != EXPECTED["native"]
        or native_index["files"]["gram"]["sha256"] != EXPECTED["gram"]
        or reference_index["files"]["reference"]["sha256"] != EXPECTED["reference"]
    ):
        raise ValueError("V1_DATA_IDENTITY_MISMATCH")
    c = indexed_array(reference_index, "reference", "c")
    alpha = indexed_array(reference_index, "reference", "alpha")
    if (
        c.shape != (packet.size,)
        or c.dtype != np.complex128
        or alpha.shape != (packet.np,)
        or alpha.dtype != np.complex128
    ):
        raise ValueError("REFERENCE_MASTER_ORDER_OR_DTYPE_FAILED")
    if not np.isfinite(c).all() or not np.isfinite(alpha).all():
        raise ValueError("REFERENCE_NONFINITE")
    actual = packet.alpha(c)
    port_error = float(
        np.linalg.norm(actual - alpha) / max(np.linalg.norm(alpha), 1e-12)
    )
    if port_error > 1e-10 or packet.a["background"].shape != (packet.size,):
        raise ValueError("REFERENCE_PORT_OR_BACKGROUND_FAILED")
    physical = native_index["result"]["identity"]
    if not physical.get("cell_tags_sha256") or not physical.get("mode_manifest_sha256"):
        raise ValueError("REFERENCE_PHYSICAL_METADATA_MISSING")
    return c, dict(
        reference_state=reference_index["files"]["reference"],
        source_sha=reference_index["source_sha"],
        port_recovery_relative=port_error,
        native_sha256=EXPECTED["native"],
        gram_sha256=EXPECTED["gram"],
        mesh_sha256=physical["mesh_coordinates_sha256"],
        cell_tags_sha256=physical["cell_tags_sha256"],
        mode_sha256=physical["mode_manifest_sha256"],
        material_sha256=physical["material"]["material_table_sha256"],
        independent_master_count=packet.size,
        slave_count=packet.full_rows - packet.size,
        reference_used_for_training=used_for_training,
        pde_only_solve=False,
        production_initialization_allowed=False,
        data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
    )


def _real_quadratic(x, G):
    value = np.vdot(x, G @ x)
    if value.real <= 0 or abs(value.imag) > 1e-10 * value.real:
        raise ValueError("GRAM_QUADRATIC_FAILED")
    return float(value.real)


def run_geometry(
    design, native_index, reference_index, route_indices, artifact, marker
):
    began = perf_counter()
    packet = load_native(native_index["files"]["native"]["path"])
    reference, identity = reference_label(native_index, reference_index, packet)
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    if G.shape != (packet.size, packet.size):
        raise ValueError("GRAM_MASTER_ORDER_FAILED")
    d_ref = _real_quadratic(reference, G)
    gram = None
    rows = {}
    try:
        gram = SparseRiesz(G, design, marker)
        d_G = float(np.vdot(packet.f, gram.solve(packet.f)).real)
        if not np.isfinite(d_G) or d_G <= 0:
            raise ValueError("DUAL_DENOMINATOR_FAILED")
        r_ref = packet.apply(reference) - packet.f
        states = {"ZERO": np.zeros(packet.size, dtype=np.complex128)}
        for name in ("FREE-FE-DUAL", "FREE-FE-DUAL-GRAM-DIAG", "FEINN-DUAL"):
            index = route_indices.get(name)
            if index is None or "checkpoint" not in index["files"]:
                rows[name] = {"status": "NOT_RETAINED"}
                continue
            states[name] = indexed_array(index, "checkpoint", "c")
            if (
                states[name].shape != reference.shape
                or states[name].dtype != reference.dtype
            ):
                raise ValueError(f"SAVED_STATE_MASTER_ORDER_FAILED: {name}")
        for name, c in states.items():
            e = c - reference
            r = packet.apply(c) - packet.f
            Ae = packet.apply(e)
            identity_error = operation_relative(
                np.linalg.norm(Ae - (r - r_ref)),
                np.linalg.norm(Ae) + np.linalg.norm(r) + np.linalg.norm(r_ref),
            )
            if identity_error > 1e-10:
                raise ValueError(f"ERROR_RESIDUAL_IDENTITY_FAILED: {name}")
            q_e = gram.solve(Ae)
            q_r = gram.solve(r)
            grad = packet.apply(q_r, adjoint=True) / d_G
            v = -grad
            correction = -e
            norm_v, norm_correction = np.linalg.norm(v), np.linalg.norm(correction)
            cosine = (
                float(np.vdot(v, correction).real / (norm_v * norm_correction))
                if norm_v > 1e-14 and norm_correction > 1e-14
                else None
            )
            row = dict(
                status="MEASURED",
                state_source="saved committed checkpoint"
                if name != "ZERO"
                else "exact zero",
                error_residual_operation_relative=identity_error,
                G_field_error=float(np.sqrt(_real_quadratic(e, G) / d_ref)),
                G_dual_error_residual=float(np.sqrt(np.vdot(Ae, q_e).real / d_G)),
                native_relative=float(np.linalg.norm(r) / packet.bnorm),
                original_dual_loss=float(np.vdot(r, q_r).real / (2 * d_G)),
                coefficient_gradient_norm=float(norm_v),
                negative_gradient_reference_correction_real_cosine=cosine,
                gradient_angle_status="MEASURED"
                if cosine is not None
                else "UNDEFINED_NEAR_ZERO",
            )
            if name in ("FREE-FE-DUAL", "FREE-FE-DUAL-GRAM-DIAG"):
                w = packet.apply(v)
                p = gram.solve(w)
                denominator = float(np.vdot(w, p).real)
                if denominator > 1e-24 and np.isfinite(denominator):
                    tstar = -float(np.vdot(w, q_r).real) / denominator
                    witness = c + tstar * v
                    rw = r + tstar * w
                    qw = q_r + tstar * p
                    row["single_real_step_witness"] = dict(
                        status="MEASURED_OFFLINE_NOT_SOLVER",
                        t_star=tstar,
                        positive_denominator=denominator,
                        dual_loss=float(np.vdot(rw, qw).real / (2 * d_G)),
                        native_relative=float(np.linalg.norm(rw) / packet.bnorm),
                        G_field_error=float(
                            np.sqrt(_real_quadratic(witness - reference, G) / d_ref)
                        ),
                    )
                else:
                    row["single_real_step_witness"] = {
                        "status": "INCONCLUSIVE_DENOMINATOR"
                    }
            rows[name] = row
            marker("geometry_" + name, row)
        if any(packet.counts[k] > 24 for k in ("A", "AH")) or gram.solves > 24:
            raise RuntimeError("P0_ACTION_BUDGET_EXCEEDED")
        if perf_counter() - began > 1200:
            raise RuntimeError("P0_WALL_BUDGET_EXCEEDED")
    finally:
        if gram is not None:
            gram.close()
    result = dict(
        status="ERROR_RESIDUAL_GEOMETRY_COMPLETE",
        reference=identity,
        d_ref=d_ref,
        d_G=d_G,
        reference_native_relative=float(np.linalg.norm(r_ref) / packet.bnorm),
        states=rows,
        actions=packet.counts,
        Gram_factor=gram.record,
        Gram_setup_seconds=gram.setup_seconds,
        Gram_solve_seconds=gram.solve_seconds,
        worker_wall_seconds=perf_counter() - began,
        global_Maxwell_factor_created=False,
        no_parameter_updates=True,
    )
    return result, {}
