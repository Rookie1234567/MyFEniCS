"""Frozen Review V19 meshes; only constants migrate from the Task40 interface.

The rational subdivisions reproduce 2374d0d's G0/GX560 without float ceil.
This module never imports a solver, reference, neural model or FE runtime.
"""

from fractions import Fraction
import hashlib
import json

import numpy as np

INTERFACE_SOURCE = "2374d0d556aed7a415202757daa2b94b76ad399b"
INTERFACE_SHA256 = "44a878f85c6e50f5aa5c6b53f58addf1350041c33593cf72ea8cb6b961f29e43"
PLAN_SOURCE_SHA256 = "90d5b83081194cb8f080d2ef6080138d37e5c9bfc5b9553af2d8a016d736b475"
MATERIAL_SHA256 = "55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2"
SEGMENTS = dict(
    G0=([2, 1, 1, 2], [1, 2, 1], [1, 4, 4, 4, 1]),
    GX560=([3, 2, 2, 3], [1, 2, 1], [1, 4, 4, 4, 1]),
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def axes(mesh_id):
    points = (
        [0, Fraction(33, 2), 25, Fraction(67, 2), 50],
        [0, Fraction(25, 4), Fraction(75, 4), 25],
        [-10, 0, 40, 80, 120, 130],
    )
    result = []
    for ps, counts in zip(points, SEGMENTS[mesh_id], strict=True):
        values = [Fraction(ps[0])]
        for low, high, count in zip(ps[:-1], ps[1:], counts, strict=True):
            values.extend(
                Fraction(low) + (Fraction(high) - Fraction(low)) * j / count
                for j in range(1, count + 1)
            )
        result.append([float(v * Fraction(7, 135)) for v in values])
    return result


def physical_design(mesh_id="G0"):
    scale = Fraction(7, 135)
    bounds = [
        [float(Fraction(a) * scale), float(Fraction(b) * scale)]
        for a, b in [(0, 50), (0, 25), (-10, 130)]
    ]
    return dict(
        schema="fixed-transverse-phase.physical.v1",
        wavelength_nm=0.7,
        geometry=dict(
            bounds_nm=bounds,
            substrate_z_nm=0.0,
            block_bounds_nm=[
                [float(Fraction(a) * scale), float(Fraction(b) * scale)]
                for a, b in [(Fraction(33, 2), Fraction(67, 2)), (0, 25), (0, 120)]
            ],
            notch_bounds_nm=[
                [float(Fraction(a) * scale), float(Fraction(b) * scale)]
                for a, b in [
                    (25, Fraction(67, 2)),
                    (Fraction(25, 4), Fraction(75, 4)),
                    (40, 80),
                ]
            ],
            axis_coordinates_nm=axes(mesh_id),
            mesh_id=mesh_id,
            cells=[sum(c) for c in SEGMENTS[mesh_id]],
        ),
        materials=dict(
            legacy_table_sha256=MATERIAL_SHA256,
            source="Review V19 and frozen Task40 interface; not legacy 0.7 entry",
            interface_sha256=INTERFACE_SHA256,
            si_n=[0.99988517036884961, 4.3236152269189515e-6],
        ),
        incidence=dict(
            grazing_deg=1.0, azimuth_deg=0.0, polarization="s", amplitude=1.0
        ),
        boundary=dict(max_m=8, max_n=2, channels=340, reference_origin_nm=[0, 0, 0]),
        finite_element=dict(family="N1curl", quadrature_degree=15),
        interface_source=INTERFACE_SOURCE,
        interface_sha256=INTERFACE_SHA256,
    )


def fixture_design():
    """One 2x2x2 air box, nonzero ky and nonunit Floquet phases; preregistered."""
    d = physical_design()
    bounds = [[0.0, 0.28], [0.0, 0.21], [0.0, 0.07]]
    d.update(fixture=True)
    d["geometry"] = dict(
        bounds_nm=bounds,
        substrate_z_nm=-1.0,
        block_bounds_nm=[[2, 3]] * 3,
        notch_bounds_nm=[[2, 3]] * 3,
        axis_coordinates_nm=[np.linspace(*b, 3).tolist() for b in bounds],
        cells=[2, 2, 2],
        mesh_id="AIR8",
    )
    d["incidence"]["azimuth_deg"] = 17.0
    d["boundary"].update(max_m=1, max_n=1, channels=36)
    return d
