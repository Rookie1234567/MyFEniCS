"""Pure tensor-axis plan for a fully 3D, six-parameter layered pillar.

No native imports or numerics are required to validate a plan. Refinement
subdivides existing regions, never changes geometry or the six parameters.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite, prod

LAYER_MATERIALS = ("Si", "SiGe", "Si", "SiGe", "Si", "SiO2")
REPRESENTATIVES = {
    "A": (0.5,) * 6, "B": (0.75,) * 6, "C": (1.0,) * 6,
    "D": (0.5, 1.0, 0.5, 1.0, 0.5, 1.0),
}


def _axis(knots, subdivisions):
    return tuple(float(a + (b-a)*i/n) for a,b,n in zip(knots[:-1],knots[1:],subdivisions)
                 for i in range(n)) + (float(knots[-1]),)


def sixlayer_plan(thicknesses_nm, *, y_refinement=1, z_refinement=1, x_refinement=1,
                  top_air_nm=0.5):
    if len(thicknesses_nm) != 6:
        raise ValueError("exactly six independent thicknesses are required")
    if any(isinstance(t, bool) or not isinstance(t,(int,float)) or not isfinite(t)
           or not 0.5 <= t <= 1.0 for t in thicknesses_nm):
        raise ValueError("each independent thickness must lie in [0.5,1.0] nm")
    if any(type(n) is not int or n < 1 for n in (x_refinement,y_refinement,z_refinement)):
        raise ValueError("refinement factors must be positive exact integers")
    if isinstance(top_air_nm,bool) or not isfinite(top_air_nm) or top_air_nm not in (0.5,1.0):
        raise ValueError("top air must be the declared 0.5 or 1.0 nm comparison")
    t = tuple(float(v) for v in thicknesses_nm)
    planes = [0.0]
    for v in t:
        planes.append(planes[-1]+v)
    H = planes[-1]
    x = _axis((0.0,0.825,1.675,2.5),(x_refinement,)*3)
    y = _axis((0.0,0.75,1.75,2.5),(2*y_refinement,)*3)
    z = _axis((-0.5,*planes,H+top_air_nm),(1,)+(z_refinement,)*6+(1,))
    volumes = {"air": 5.4*H+6.25*top_air_nm,"substrate":3.125}
    volumes.update({f"layer_{i+1}":0.85*v for i,v in enumerate(t)})
    plan = {
        "schema":"sixlayer-structured-plan.v1", "coordinate_unit":"nm",
        "thicknesses_nm":t, "layer_materials":LAYER_MATERIALS,
        "height_nm":H, "top_air_nm":float(top_air_nm),
        "bottom_reference_z_nm":-0.5, "incident_phase_reference_nm":(0.0,0.0,0.0),
        "x_values":x,"y_values":y,"z_values":z,"layer_planes_nm":tuple(planes),
        "cell_counts":(len(x)-1,len(y)-1,len(z)-1),
        "cells":(len(x)-1)*(len(y)-1)*(len(z)-1),
        "expected_region_volumes_nm3":volumes,
        "expected_material_volumes_nm3":{
            "air":volumes["air"],"Si":3.125+0.85*(t[0]+t[2]+t[4]),
            "SiGe":0.85*(t[1]+t[3]),"SiO2":0.85*t[5]},
        "domain_volume_nm3":6.25*(H+top_air_nm+0.5),
        "minimum_affine_jacobian_determinant":prod(min(b-a for a,b in zip(axis[:-1],axis[1:])) for axis in (x,y,z)),
    }
    plan["geometry_sha256"] = sha256(json.dumps(plan,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return plan


def cell_material_at(x,y,z,plan):
    if z < 0.0:
        return "substrate",2
    if 0.825 < x < 1.675 and 0.75 < y < 1.75:
        for i,(low,high) in enumerate(zip(plan["layer_planes_nm"][:-1],plan["layer_planes_nm"][1:])):
            if low <= z < high:
                return f"layer_{i+1}",21+i
    return "air",1
