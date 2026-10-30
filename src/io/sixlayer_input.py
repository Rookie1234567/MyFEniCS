"""Strict, stdlib-only six-layer input and physical identity resolution."""
from __future__ import annotations

from hashlib import sha256
import json
from math import floor, pi
from pathlib import Path
import re

from .input_loader import InputError, load_dat_input
from ..common.sixlayer_materials import load_sixlayer_materials
from ..geometry.sixlayer_block import sixlayer_plan

MODEL = "sixlayer_surrogate_0p7nm"
GENERATOR = "sixlayer-p6-centered-dtn-v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def resolve_sixlayer_input(path):
    loaded = load_dat_input(path)
    doc = dict(loaded.document)
    allowed = {"model", "sample_id", "thicknesses_nm", "generator_version",
               "output_directory", "mesh", "dtn", "top_air_nm"}
    if set(doc) - allowed:
        raise InputError(f"unknown six-layer fields: {sorted(set(doc)-allowed)}")
    required = {"model", "sample_id", "thicknesses_nm", "generator_version"}
    if required - set(doc) or doc.get("model") != MODEL:
        raise InputError("six-layer model/sample_id/thicknesses_nm/generator_version required")
    sample = doc["sample_id"]
    if not isinstance(sample, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", sample) is None:
        raise InputError("sample_id must be a safe nonempty identifier (at most 80 characters)")
    if doc["generator_version"] != GENERATOR:
        raise InputError(f"unsupported generator_version; expected {GENERATOR}")
    mesh = dict(doc.get("mesh", {}))
    if set(mesh) - {"x_refinement", "y_refinement", "z_refinement"}:
        raise InputError("unknown mesh field")
    try:
        plan = sixlayer_plan(doc["thicknesses_nm"], top_air_nm=doc.get("top_air_nm", 0.5), **mesh)
    except (ValueError, TypeError) as exc:
        raise InputError(str(exc)) from exc
    dtn = dict(doc.get("dtn", {}))
    if set(dtn) - {"evanescent_padding", "quadrature_degree"}:
        raise InputError("unknown DtN field")
    padding, quadrature = dtn.get("evanescent_padding", 2), dtn.get("quadrature_degree", 32)
    if type(padding) is not int or not 1 <= padding <= 8:
        raise InputError("evanescent_padding must be an exact integer in [1,8]")
    if type(quadrature) is not int or not 20 <= quadrature <= 64:
        raise InputError("surface quadrature_degree must be an exact integer in [20,64]")
    material = load_sixlayer_materials()
    physics = {"schema": "sixlayer-physical-model.v1", "model": MODEL,
               "wavelength_nm": 0.7, "geometry": {
                   key: plan[key] for key in ("thicknesses_nm", "layer_materials", "height_nm",
                       "top_air_nm", "bottom_reference_z_nm", "incident_phase_reference_nm")},
               "period_nm": [2.5,2.5], "pillar_width_nm": [0.85,1.0], "substrate_thickness_nm": 0.5,
               "materials": material["identity"], "materials_identity_sha256": material["identity_sha256"],
               "theta_deg": 89.0, "phi_deg": 90.0, "polarization": "s",
               "floquet": ["x", "y"], "boundary": "air-top-Si-bottom-Fourier-DtN",
               "incident_phase_reference_nm": [0.0, 0.0, 0.0]}
    discretization = {"generator_version": GENERATOR,
                      "material_identity_sha256": material["identity_sha256"],
                      "parameter_domain_nm": [[0.5,1.0]]*6,
                      "mesh_recipe": {"x_refinement": mesh.get("x_refinement",1),
                                      "y_refinement": mesh.get("y_refinement",1),
                                      "z_refinement": mesh.get("z_refinement",1)},
                      "top_air_nm": plan["top_air_nm"],
                      "dtn": {"evanescent_padding": padding, "quadrature_degree": quadrature,
                              "phase_gauge": "boundary_plane"},
                      "element": "uniform-p6-N1curl", "scalar": "complex128",
                      "solver": "assembly_time_static_condensed_exact_MUMPS"}
    output = doc.get("output_directory", f"benchmarks/artifacts/task44/{sample}")
    if not isinstance(output, str) or not output.strip():
        raise InputError("output_directory must be a nonempty path")
    result = {"schema": "sixlayer-resolved-input.v1", "sample_id": sample,
              "input_sha256": loaded.input_sha256, "input_path": str(loaded.source_path),
              "output_directory": output, "physical_model": physics,
              "physical_model_sha256": sha256(_canonical(physics)).hexdigest(),
              "mesh_plan": plan, "discretization": discretization,
              "resolved_numerical_config_sha256": sha256(_canonical({"plan":plan,"recipe":discretization})).hexdigest(),
              "generator_identity_sha256": sha256(_canonical(discretization)).hexdigest(),
              "qualification": "NOT_RUN; 144 cells are a candidate, not an accuracy guarantee"}
    return loaded, result


def build_sixlayer_config(resolved):
    """Build the native configuration only after strict input resolution."""
    from ..common.config_3d import SimulationConfig3D
    from ..common.material_regions_3d import grating_layers
    material = load_sixlayer_materials()
    plan = resolved["mesh_plan"]
    labels = tuple(plan["layer_materials"])
    cfg = SimulationConfig3D(
        case_name=resolved["sample_id"], stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating", geometry_model_variant="sixlayer_pillar",
        geometry_identity=plan["geometry_sha256"], lambda0=0.7,
        period_x=2.5, period_y=2.5, z_min=-0.5, z_max=plan["height_nm"]+plan["top_air_nm"],
        air_height=plan["top_air_nm"], substrate_thickness=0.5, interface_z=0.0,
        grating_height=plan["height_nm"], grating_width_x=0.85, grating_width_y=1.0,
        n_air=material["refractive_indices"]["air"], n_substrate=material["refractive_indices"]["Si"],
        n_grating=material["refractive_indices"]["Si"],
        grating_layer_thicknesses_nm=tuple(plan["thicknesses_nm"]),
        grating_layer_indices=tuple(material["refractive_indices"][s] for s in labels),
        grating_layer_labels=labels, material_identity_sha256=material["identity_sha256"],
        substrate_material_label="Si", grating_material_label="sixlayer independent-atom test model",
        incident_theta_deg=89.0, incident_phi_deg=90.0, polarization_kind="s", custom_polarization=None,
        nedelec_degree=6, visualization_degree=1, use_floquet_xy=True, use_pml=False,
        mesh_cell_type="hexahedron", mesh_spacing_mode="boundary_fitted",
        mesh_axis_cell_counts=tuple(plan["cell_counts"]), mesh_axis_x_values=tuple(plan["x_values"]),
        mesh_axis_y_values=tuple(plan["y_values"]), mesh_axis_z_values=tuple(plan["z_values"]),
        mesh_axis_z_profile="sixlayer-interface-fitted-v1", mesh_plan_id="sixlayer-tensor-v1",
        mesh_plan_sha256=plan["geometry_sha256"], stage4_preserve_structured_input_partition=True,
        stage4_boundary_model="dtn_port", stage4_dtn_order_policy="manual",
        diffraction_zero_order_only=False, stage4_full3d_assembly_backend="assembly_time_static_condensed",
        direct_release_solver_before_postprocess=True, petsc_direct_solver_profile="default",
        petsc_extra_options={"pc_factor_mat_solver_type": "mumps", "mat_mumps_icntl_14": 100,
                             "mat_mumps_icntl_24": 1, "mat_mumps_icntl_35": 0},
    )
    # Same complete propagating-lattice upper bounds as modes_3d, followed by
    # explicit evanescent padding. Never infer bounds from a previous case.
    medium_max = max(abs(cfg.n_air), abs(cfg.substrate_index))
    bounds = tuple(floor((medium_max*cfg.k0+abs(k))*period/(2*pi)+1e-12)
                   for k, period in ((cfg.kx,cfg.period_x),(cfg.ky,cfg.period_y)))
    padding = resolved["discretization"]["dtn"]["evanescent_padding"]
    cfg.diffraction_order_max_m, cfg.diffraction_order_max_n = (int(v)+padding for v in bounds)
    cfg.stage4_dtn_quadrature_degree = resolved["discretization"]["dtn"]["quadrature_degree"]
    cfg.dtn_phase_gauge = "boundary_plane"
    cfg.require_full_explicit_residual = True
    grating_layers(cfg)
    return cfg
