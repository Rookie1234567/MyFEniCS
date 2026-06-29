from __future__ import annotations

from ..common.config import SimulationConfig


def near_field_regions_2d(cfg: SimulationConfig) -> dict[str, dict[str, float]]:
    """Return near-field integration boxes used by the 2D EUV convergence study."""
    x0 = max(cfg.x_min, cfg.grating_x_min - cfg.near_field_margin_x)
    x1 = min(cfg.x_max, cfg.grating_x_max + cfg.near_field_margin_x)
    air_y0 = cfg.grating_y_min
    air_y1 = min(cfg.physical_y_max, cfg.near_field_air_top)
    sub_y1 = cfg.substrate_y_max
    sub_y0 = max(cfg.physical_y_min, cfg.substrate_y_max - cfg.near_field_sub_depth)
    return {
        "grating": {
            "x_min": cfg.grating_x_min,
            "x_max": cfg.grating_x_max,
            "y_min": cfg.grating_y_min,
            "y_max": cfg.grating_y_max,
        },
        "air_near": {"x_min": x0, "x_max": x1, "y_min": air_y0, "y_max": air_y1},
        "sub_near": {"x_min": x0, "x_max": x1, "y_min": sub_y0, "y_max": sub_y1},
    }


def _rect_area(bounds: dict[str, float]) -> float:
    return max(float(bounds["x_max"] - bounds["x_min"]), 0.0) * max(
        float(bounds["y_max"] - bounds["y_min"]), 0.0
    )


def _intersection_area(a: dict[str, float], b: dict[str, float]) -> float:
    x0 = max(float(a["x_min"]), float(b["x_min"]))
    x1 = min(float(a["x_max"]), float(b["x_max"]))
    y0 = max(float(a["y_min"]), float(b["y_min"]))
    y1 = min(float(a["y_max"]), float(b["y_max"]))
    return max(x1 - x0, 0.0) * max(y1 - y0, 0.0)


def near_field_reference_areas_2d(cfg: SimulationConfig) -> dict[str, float]:
    """Reference geometric areas for a constant unit field in each near region."""
    regions = near_field_regions_2d(cfg)
    grating_area = _rect_area(regions["grating"])
    air_box_area = _rect_area(regions["air_near"])
    return {
        "grating": grating_area,
        "air_near": max(air_box_area - _intersection_area(regions["air_near"], regions["grating"]), 0.0),
        "sub_near": _rect_area(regions["sub_near"]),
    }
