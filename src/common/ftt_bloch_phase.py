"""Physical Bloch identity, usable without importing Torch or FE libraries."""

import hashlib
import json
import numpy as np

def phase_definition(design):
    """Read the unfolded incident wavevector from the original physical cfg."""
    from src.solvers.feinn_fem import physical_config

    cfg, _ = physical_config(design["model"])
    k = np.asarray([cfg.kx, cfg.ky], dtype=np.complex128)
    if np.any(k.imag != 0) or not np.isfinite(k).all():
        raise ValueError("BLOCH_REAL_UNFOLDED_INCIDENT_VECTOR_REQUIRED")
    bounds = np.asarray(design["model"]["geometry"]["bounds_nm"])
    value = dict(
        wavevector_nm_inverse=[float(k[0].real), float(k[1].real), 0.0],
        origin_nm=bounds.mean(1).tolist(),
        coordinate_unit="physical_nm",
        sign=1,
        unfolded_incident_wavevector=True,
        phase_applied="before_complete_moments_and_Piola",
        MPC_expansion_count=1,
        mode_manifest_sha256=design["native_identity"]["mode_manifest_sha256"],
    )
    value["sha256"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return value

