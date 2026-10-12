"""V7 observations on the converged 572-channel field; no new PDE/factor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .n0_full_dtn_endpoint import _chunk_norm, _field


def _key(mode):
    return tuple(_field(mode, key) for key in ("side", "m", "n", "polarization"))


def validate_n0_keys(modes):
    keys = [_key(mode) for mode in modes]
    expected = {
        (side, m, 0, pol)
        for side in ("bottom", "top")
        for m in range(-142, 1)
        for pol in ("s", "p")
    }
    if len(keys) != 572 or set(keys) != expected:
        raise ValueError(
            "V7 output requires all 572 unique N0 keys, including 0 and -1"
        )
    return keys


def truncation_action_observation(
    *, modes, entries, solution, residual, rhs_norm, incident_projections
):
    """Compute A572-A84 with existing MPC-processed functionals, once.

    D already includes conjugation. C includes the original DtN traction and
    phase; no modal power approximation is used for this operator observation.
    One full-space scratch vector is released on return. MPI1 owned storage is
    the same zero-slave full p6 storage used by the independent A6 check.
    """
    started = perf_counter()
    keys = validate_n0_keys(modes)
    if len(entries) != len(keys) or len(incident_projections) != len(keys):
        raise ValueError("V7 carrier/incident inventory mismatch")
    solution, residual = np.asarray(solution), np.asarray(residual)
    if (
        solution.dtype != np.complex128
        or residual.dtype != np.complex128
        or solution.ndim != 1
        or solution.shape != residual.shape
        or not np.isfinite(rhs_norm)
        or rhs_norm <= 0
    ):
        raise ValueError("V7 residual/solution/RHS identity is invalid")
    omitted = np.zeros_like(residual)
    count = 0
    for key, entry, incident in zip(keys, entries, incident_projections, strict=True):
        if _key(_field(entry, "mode_identity")) != key:
            raise ValueError("V7 carrier ordering differs from modes")
        if key[1] >= -20:
            continue
        if complex(incident) != 0j:
            raise ValueError("A84 observation would change the incident RHS")
        h = float(_field(entry, "normalization_h"))
        if not np.isfinite(h) or h <= 0:
            raise ValueError("invalid normalization H")
        arrays = []
        for row_key, value_key in (
            ("projection_rows", "projection_values"),
            ("coupling_rows", "coupling_values"),
        ):
            rows, values = (
                np.asarray(_field(entry, row_key)),
                np.asarray(_field(entry, value_key)),
            )
            if (
                rows.ndim != 1
                or not np.issubdtype(rows.dtype, np.integer)
                or values.shape != rows.shape
                or not np.isfinite(values).all()
                or (
                    rows.size
                    and (
                        rows[0] < 0
                        or rows[-1] >= solution.size
                        or np.any(np.diff(rows) <= 0)
                    )
                )
            ):
                raise ValueError("invalid owned functional rows/values")
            arrays.append((rows, values))
        (dr, dv), (cr, cv) = arrays
        coefficient = np.dot(dv, solution[dr]) / h
        omitted[cr] += cv * coefficient
        count += 1
    if count != 488:
        raise ValueError("A572-A84 must contain exactly 488 omitted contributions")
    delta = _chunk_norm(omitted) / rhs_norm
    # A84 = A572 - omitted, so b-A84u = r572 + omitted.
    direct_square = 0.0
    for first in range(0, residual.size, 65536):
        part = residual[first : first + 65536] + omitted[first : first + 65536]
        direct_square += float(np.vdot(part, part).real)
    direct = float(np.sqrt(direct_square)) / rhs_norm
    original = _chunk_norm(residual) / rhs_norm
    if not np.isfinite([delta, direct, original]).all():
        raise ValueError("nonfinite truncation observation")
    return {
        "schema": "task39extra.v7.same-field-truncation-action.v1",
        "status": "OBSERVED_NOT_A84_SOLUTION",
        "A6_n0_relative": original,
        "delta20": delta,
        "b572_minus_A84_u572_relative": direct,
        "rhs_norm": float(rhs_norm),
        "omitted_mode_count": count,
        "retained_A84_count": 84,
        "incident_rhs_unchanged": True,
        "projection_convention": "dot(D,u)/H; D already conjugated",
        "formula": "r84_on_u572 = r572 + (A572-A84)u572",
        "new_factor_calls": 0,
        "new_PDE_calls": 0,
        "new_FE_assembly_calls": 0,
        "scratch_vector_bytes": int(omitted.nbytes),
        "elapsed_seconds": perf_counter() - started,
    }


def grouped_powers(rows):
    validate_n0_keys(rows)
    ranges = [
        ("m0", 0, 0),
        ("m_minus1", -1, -1),
        ("m_minus20_to_minus2", -20, -2),
        ("m_minus40_to_minus21", -40, -21),
        ("m_minus80_to_minus41", -80, -41),
        ("m_minus142_to_minus81", -142, -81),
    ]
    if any(
        not np.isfinite([row["R"], row["T"]]).all() or min(row["R"], row["T"]) < -1e-12
        for row in rows
    ):
        raise ValueError("invalid modal powers")
    groups = {}
    for name, lo, hi in ranges:
        group = [row for row in rows if lo <= row["m"] <= hi]
        groups[name] = {
            "R": float(sum(row["R"] for row in group)),
            "T": float(sum(row["T"] for row in group)),
            "count": len(group),
        }
    return {
        "groups": groups,
        "tail20_power": float(
            sum(row["R"] + row["T"] for row in rows if row["m"] < -20)
        ),
        "R_total": float(sum(row["R"] for row in rows)),
        "T_total": float(sum(row["T"] for row in rows)),
        "normalization": "same incident power as all 572 original port rows",
        "near_cutoff_modes": [
            {key: row[key] for key in ("side", "m", "n", "polarization", "R", "T")}
            for row in rows
            if row.get("rayleigh_warning") is True
        ],
    }


def y_variation_observation(electric, magnetic, y_nm):
    electric, magnetic, y_nm = (
        np.asarray(electric),
        np.asarray(magnetic),
        np.asarray(y_nm),
    )
    if (
        electric.shape != magnetic.shape
        or electric.ndim != 4
        or electric.shape[-1] != 3
        or y_nm.ndim != 1
        or not np.isfinite(y_nm).all()
        or electric.shape[1] != len(y_nm)
        or len(np.unique(y_nm)) < 4
        or not np.iscomplexobj(electric)
        or not np.iscomplexobj(magnetic)
        or not np.isfinite(electric).all()
        or not np.isfinite(magnetic).all()
    ):
        raise ValueError("V7 needs finite complex E/H at >=4 common y sample positions")
    facts = {
        "scope": "sampled complex fields at fixed (x,z); no phase fitting",
        "y_nm": y_nm.tolist(),
        "phase_fitting": False,
        "threshold": 1e-4,
        "threshold_role": "diagnostic_warning_only",
        "FE_y_variation_norm": None,
        "FE_y_variation_norm_status": "NOT_COMPUTED",
    }
    for label, array, cross in (("E", electric, (0, 2)), ("H", magnetic, (1,))):
        norm = float(np.linalg.norm(array))
        scale = max(norm, np.finfo(float).tiny)
        facts[f"{label}_sample_y_variation_relative"] = (
            float(np.linalg.norm(array - array[:, :1])) / scale
        )
        facts[f"{label}_cross_polarization_relative"] = (
            float(np.linalg.norm(array[..., cross])) / scale
        )
    facts["diagnostic_warning"] = any(
        float(value) > 1e-4 for key, value in facts.items() if key.endswith("_relative")
    )
    return facts


def saved_output_observation(directory, outputs, cfg, action):
    """Consume bounded saved samples and modal JSON, without another FE solve."""
    directory = Path(directory)
    modal_path = directory / "dtn_port_diffraction_orders_3d.json"
    modal_bytes = modal_path.read_bytes()
    modal = json.loads(modal_bytes)
    powers = grouped_powers(modal["orders"])
    field_path = Path(outputs["field_export"]["full3d_reference_archive"])
    with np.load(field_path, allow_pickle=False) as data:
        e, h = data["E_V_per_m"], data["H_A_per_m"]
        y_facts = y_variation_observation(e, h, data["y_nm"])
        # H exporter uses exactly this relation to its DG interpolation of curl.
        curl_code = h * (1j * cfg.k0 * cfg.mu_r / cfg.magnetic_field_scale_A_per_m)
        curl_path = directory / "v7_curl_samples.npz"
        np.savez(
            curl_path,
            x_nm=data["x_nm"],
            y_nm=data["y_nm"],
            z_nm=data["z_nm"],
            curl_E_code_per_nm=curl_code,
        )
    return {
        "schema": "task39extra.v7.diffraction-tail-and-scope.v1",
        "operator_scope": "A6_n0",
        "active_mode_count": 572,
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        "A6_full_relative": None,
        "reference_status": "REFERENCE_NOT_AVAILABLE",
        "authority": "AUTHORITY_LIMITED",
        "omitted_channel_values": "NOT_COMPUTED",
        "power_groups": powers,
        "same_field_truncation": action,
        "y_diagnostics": y_facts,
        "future_A84_candidate_screen": bool(
            powers["tail20_power"] <= 1e-5 and action["delta20"] <= 1e-7
        ),
        "future_A84_screen_is_current_solve_gate": False,
        "modal_file": str(modal_path),
        "modal_sha256": hashlib.sha256(modal_bytes).hexdigest(),
        "curl_samples": {
            "path": str(curl_path),
            "sha256": hashlib.sha256(curl_path.read_bytes()).hexdigest(),
            "scope": "DG-interpolated curl samples from exported H; native full FE coefficients saved separately",
        },
    }
