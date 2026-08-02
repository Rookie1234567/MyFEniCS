"""Public fixed-geometry angle surrogate interface."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from ..physics import power_mask_authority
from .design import cutoff_distance
from .models import angle_features


class AngleSurrogate:
    """Predict Task004 observables at one in-domain grazing/azimuth pair.

    The object never changes geometry: ``height_nm=120`` and ``width_x_nm=17``
    are part of the returned provenance.  Inputs outside the qualified angle
    rectangle are rejected rather than silently clipped.
    """

    def __init__(self, package: dict[str, Any], *, metadata: dict[str, Any] | None = None):
        self.package = package
        self.metadata = metadata or {}

    @classmethod
    def from_package(cls, package_dir: Path) -> "AngleSurrogate":
        package_dir = Path(package_dir)
        with (package_dir / "angle_model.pkl").open("rb") as stream:
            package = pickle.load(stream)
        manifest = json.loads((package_dir.parent / "compact_dataset/dataset_manifest.json").read_text()) \
            if (package_dir.parent / "compact_dataset/dataset_manifest.json").exists() else {}
        return cls(package, metadata=manifest)

    def predict(self, grazing_deg: float, azimuth_deg: float) -> dict[str, Any]:
        grazing = float(grazing_deg); azimuth = float(azimuth_deg)
        if not (np.isfinite(grazing) and np.isfinite(azimuth)):
            raise ValueError("Task004 angles must be finite")
        if not (0.5 <= grazing <= 10.0 and 0.0 <= azimuth <= 90.0):
            raise ValueError("Task004 angle is outside the qualified domain")
        angles = np.asarray([[grazing, azimuth]], dtype=np.float64)
        aggregate_model = self.package["aggregate_model"]
        mean, std = aggregate_model.predict(angles, return_std=True)
        calibration = float(self.package.get("calibration_factor", 1.0))
        if np.all(np.isfinite(std)):
            std = std * calibration
        inputs = np.asarray([[120.0, 17.0, grazing, azimuth]], dtype=np.float64)
        mask_identity = power_mask_authority(inputs)
        mask = mask_identity["power_carrying"][0]
        powers, power_std = self.package["power_model"].predict(
            angles, mean, mask_identity["power_carrying"], aggregate_std=std,
        )
        nearest = np.min(np.linalg.norm(
            (angles - np.asarray(self.package["training_angles"])[None, :, :]) /
            np.asarray([9.5, 90.0]), axis=2,
        ))
        cut = float(cutoff_distance(angles)[0])
        warning = None
        if cut <= 0.02:
            warning = "near_analytic_rayleigh_cutoff"
        return {
            "status": "predicted", "configuration": {
                "height_nm": 120.0, "width_x_nm": 17.0, "wavelength_nm": 13.5,
                "incident_polarization": "S", "grazing_deg": grazing,
                "azimuth_deg": azimuth,
            },
            "R_total": float(mean[0, 0]), "T_total": float(mean[0, 1]),
            "A_balance": float(mean[0, 2]),
            "aggregate_mean": mean[0].tolist(), "aggregate_std": std[0].tolist(),
            "order_powers": powers[0].tolist(), "order_power_std": power_std[0].tolist(),
            "power_carrying_mask": mask.tolist(),
            "dispersion_propagating": mask_identity["dispersion_propagating"][0].tolist(),
            "cutoff_distance": cut, "nearest_training_distance": float(nearest),
            "model_id": "S_PROD_FULL3D_STATIC_P5_H10_NY4",
            "solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
            "dataset_id": self.package.get("dataset_id"),
            "selected_candidate": self.package.get("selected_candidate"),
            "warning": warning,
        }
