"""Explicit research boundary-plane coordinates, independent of mode policy.

Primary forms evaluate centered phases directly. Coordinate conversions are
only for declared RHS/output semantics and representable-equivalence oracles;
they are never used to construct centered C/D from tiny global coefficients.
"""

from __future__ import annotations

from typing import Any, Sequence
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import hashlib
import sys
import re
from importlib.metadata import version as package_version

import numpy as np


GLOBAL_Z = "global_z"
BOUNDARY_PLANE = "boundary_plane"
GAUGE_SCHEMA = "task40extra.dtn-boundary-phase-gauge.v1"


class PhaseGaugeConversionError(FloatingPointError):
    def __init__(self, reason, index, mode):
        self.mode_index = int(index)
        self.mode_key = (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
        self.reason = str(reason)
        self.diagnostics = None
        super().__init__(f"mode_index={index}, key={self.mode_key}: {reason}")


def deep_frozen_identity(value):
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): deep_frozen_identity(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_frozen_identity(item) for item in value)
    return value


def _array_signature(value):
    array = np.asarray(value)
    digest = hashlib.sha256()
    for chunk in np.nditer(array, flags=["external_loop", "buffered", "zerosize_ok"],
                           order="C", buffersize=65536):
        digest.update(memoryview(np.ascontiguousarray(chunk)).cast("B"))
    return {"shape": tuple(array.shape), "dtype": str(array.dtype), "sha256": digest.hexdigest()}


def compiled_surface_quadrature_identity(ufl_form, compiled_form, *, semantic_constants=None):
    """Verify analyzed FFCx rules/nodes/weights against actual compiled C tables.

    This is a bounded qualification/provenance action, not a replacement
    quadrature rule. Unsupported or unavailable generated code stops the gate.
    """
    from ffcx.analysis import analyze_ufl_objects
    from ffcx.ir.representationutils import create_quadrature_points_and_weights, QuadratureRule
    analysis = analyze_ufl_objects([ufl_form], np.dtype(np.complex128))
    form_data = analysis.form_data[0]
    code = compiled_form.code
    if code is None or (isinstance(code, (tuple, list)) and not all(isinstance(part, str) for part in code)):
        module = compiled_form.module
        path = Path(module.__file__).parent/(module.__name__+".c")
        if not path.is_file():
            raise ValueError("actual compiled FFCx C source is unavailable for Gauss verification")
        code = path.read_text()
    elif isinstance(code, (tuple, list)):
        code = "\n".join(code)
    records = []
    for group in form_data.integral_data:
        for integral in group.integrals:
            md = integral.metadata()
            rule, degree = str(md["quadrature_rule"]), int(md["quadrature_degree"])
            if rule in {"custom", "vertex"} or integral.integral_type() != "exterior_facet":
                raise ValueError("this gauge proof requires the existing standard exterior-facet Gauss rule")
            points, weights, _ = create_quadrature_points_and_weights(
                integral.integral_type(), integral.ufl_domain().ufl_cell(), degree, rule,
                form_data.argument_elements, False,
            )
            for cell in points:
                q = QuadratureRule(np.asarray(points[cell]), np.asarray(weights[cell]))
                hash(q)  # Same FFCx identifier initialization used by IR.
                symbol = "weights_"+q.id()
                pattern = rf"\b{re.escape(symbol)}\s*\[\s*(\d+)\s*\]\s*=\s*\{{([^}}]*)\}}"
                tables = re.findall(pattern, code, re.S)
                if not tables:
                    raise ValueError("actual generated C lacks the analyzed Gauss weight/node-id table")
                for count, table in tables:
                    actual = np.fromstring(table.replace("\n", " "), dtype=float, sep=",")
                    if actual.shape != (int(count),) or actual.shape != np.asarray(weights[cell]).shape:
                        raise ValueError("compiled Gauss weight count differs from analyzed nodes")
                    if not np.allclose(actual, weights[cell], rtol=32*np.finfo(float).eps, atol=0):
                        raise ValueError("actual compiled Gauss weights differ from analyzed rule")
                records.append({"integral_type": integral.integral_type(), "tag": integral.subdomain_id(),
                                "degree": degree, "rule": rule, "facet_cell": cell,
                                "points": _array_signature(points[cell]), "weights": _array_signature(weights[cell]),
                                "compiled_weight_symbol": symbol, "compiled_weight_tables_verified": len(tables)})
    if not records:
        raise ValueError("no compiled exterior-facet Gauss rule was verified")
    result = {"rules": records, "compiled_C_sha256": hashlib.sha256(code.encode()).hexdigest(),
              "verification": "FFCx analyzed nodes/rule plus actual generated C weight table and node-id symbol"}
    if semantic_constants is not None:
        result["loaded_kernel"] = loaded_surface_kernel_identity(
            ufl_form, compiled_form, code, semantic_constants)
    return deep_frozen_identity(result)



def loaded_surface_kernel_identity(ufl_form, compiled_form, code, semantic_constants):
    """Record the actual loaded kernel and verify its semantic packed slots.

    The probe packs three distinct representable Constant values without any
    numerical form assembly. Every original value is restored in finally,
    with an exact restored-value/packed-buffer check. No UFL counter reset or
    source/hash normalization is performed.
    """
    from dolfinx import fem
    if tuple(semantic_constants) != ("alpha", "gamma", "kz"):
        raise ValueError("surface kernel requires the complete alpha/gamma/kz map")
    constants = tuple(ufl_form.constants())
    ufcx = compiled_form.ufcx_form
    module = compiled_form.module
    if len(constants) != 3 or int(ufcx.num_constants) != 3:
        raise ValueError("actual surface kernel must have exactly three scalar Constants")
    roles = []
    for role, constant in semantic_constants.items():
        slots = [index for index, value in enumerate(constants) if value is constant]
        if len(slots) != 1 or tuple(constant.ufl_shape) != ():
            raise ValueError("semantic Constant is missing, duplicated or nonscalar")
        roles.append({"role": role, "ufl_count": int(constant.count()), "form_slot": slots[0]})
    before = fem.pack_constants(compiled_form).copy()
    saved = [np.asarray(value.value).copy() for value in constants]
    sentinels = {"alpha": 11+13j, "gamma": 17+19j, "kz": 23+29j}
    packed = None
    try:
        for role, constant in semantic_constants.items():
            constant.value[...] = sentinels[role]
        packed = np.asarray(fem.pack_constants(compiled_form)).copy()
        if packed.shape != (3,) or not np.isfinite(packed).all():
            raise ValueError("actual packed Constant buffer is incomplete/nonfinite")
        for item in roles:
            value = sentinels[item["role"]]
            slots = np.flatnonzero(packed == value)
            if len(slots) != 1 or int(slots[0]) != item["form_slot"]:
                raise ValueError("runtime Constant pack map differs from semantic form map")
            item["packed_slot"] = int(slots[0])
            item["sentinel"] = value
    finally:
        for constant, original in zip(constants, saved, strict=True):
            constant.value[...] = original
        if (not all(_array_signature(np.asarray(value.value)) == _array_signature(original)
                    for value, original in zip(constants, saved, strict=True))
                or _array_signature(fem.pack_constants(compiled_form)) != _array_signature(before)):
            raise ValueError("surface kernel Constant restoration was not exact")
    module_path = Path(module.__file__).resolve()
    if not module_path.is_file():
        raise ValueError("actual loaded kernel binary is unavailable")
    c_path = module_path.parent/(module.__name__+".c")
    signature = module.ffi.string(ufcx.signature).decode()
    if not c_path.is_file():
        raise ValueError("actual module-bound C source is missing")
    module_C = c_path.read_text()
    if signature not in module_C:
        raise ValueError("actual module-bound C source lacks the loaded form signature")
    def digest_file(path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    offsets = [int(ufcx.form_integral_offsets[index]) for index in range(6)]
    integral_names = re.findall(r"\bufcx_integral\s+(\w+)\s*=\s*\{", module_C)
    if len(integral_names) != offsets[-1]:
        raise ValueError("module-bound integral symbol inventory is incomplete")
    integrals = []
    for index in range(offsets[-1]):
        integral = ufcx.form_integrals[index]
        integrals.append({"index": index, "tag": int(ufcx.form_integral_ids[index]),
                          "coordinate_element_hash": int(integral.coordinate_element_hash),
                          "needs_facet_permutations": bool(integral.needs_facet_permutations)})
    return deep_frozen_identity({
        "schema": "task40extra.loaded-surface-kernel.v1",
        "module_name": module.__name__, "module_path": str(module_path),
        "binary_sha256": digest_file(module_path), "module_bound_C_path": str(c_path),
        "module_bound_C_sha256": digest_file(c_path),
        "UFL_form_signature": ufl_form.signature(),
        "UFCx_form_signature": signature,
        "FFCx_form_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "num_constants": int(ufcx.num_constants), "constant_roles": roles,
        "constant_name_map": [module.ffi.string(ufcx.constant_name_map[index]).decode()
                              for index in range(3)],
        "constant_ranks": [int(ufcx.constant_ranks[index]) for index in range(3)],
        "integral_offsets": offsets, "integrals": integrals, "module_bound_integral_symbols": integral_names,
        "packed_before_signature": _array_signature(before),
        "packed_sentinel_signature": _array_signature(packed),
        "restoration_exact": True, "numerical_assembly_during_probe": False,
    })

def build_gauge_assembly_context(space, mesh_data, mpc, cfg, qdegree, surface_assemblers,
                                 *, quotient_context=None):
    """Bind actual discrete inputs/source; initially MPI1 only, no big tables.

    Degree/rule and compiler/Basix ABI bind the same current default facet
    Gauss algorithm. Independent compiled-form metadata/rule verification is
    still a qualification gate; no persistent cache may bypass that gate.
    """
    import basix
    import dolfinx
    import dolfinx_mpc
    import ffcx
    from petsc4py import PETSc
    from .fullspace_dtn_action import _canonical_json_bytes
    mesh = space.mesh
    if int(mesh.comm.size) != 1:
        raise NotImplementedError("boundary-plane context initially requires MPI1")
    mesh.topology.create_entity_permutations()
    mesh.topology.create_connectivity(mesh.topology.dim-1, 0)
    facet_vertices = mesh.topology.connectivity(mesh.topology.dim-1, 0)
    dofs_digest = hashlib.sha256()
    cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    for cell in range(cell_count):
        row = np.asarray(space.dofmap.cell_dofs(cell))
        dofs_digest.update(_canonical_json_bytes(_array_signature(row)))
    coeff, offsets = mpc.coefficients()  # Public finalized-MPC API.
    mpc_payload = {name: _array_signature(value) for name, value in (
        ("slaves", mpc.slaves), ("masters", mpc.masters.array),
        ("coefficients", coeff), ("offsets", offsets),
    )}
    mesh_payload = {name: _array_signature(value) for name, value in (
        ("geometry_x", mesh.geometry.x), ("geometry_dofmap", mesh.geometry.dofmap),
        ("facet_vertices", facet_vertices.array), ("facet_vertex_offsets", facet_vertices.offsets),
        ("facet_indices", mesh_data.facet_tags.indices), ("facet_values", mesh_data.facet_tags.values),
        ("cell_indices", mesh_data.cell_tags.indices), ("cell_values", mesh_data.cell_tags.values),
    )}
    element = space.element.basix_element
    source_paths = [Path(__file__), Path(__file__).with_name("dtn_port_3d.py"),
                    Path(__file__).with_name("fullspace_dtn_action.py"),
                    Path(__file__).with_name("fullspace_same_mesh_hcurl_pmg_physical.py"),
                    Path(__file__).with_name("dtn_boundary_plane_qualification.py"),
                    Path(__file__).parent.parent/"common"/"modes_3d.py",
                    Path(__file__).parent.parent/"common"/"config_3d.py"]
    payload = {
        "schema": "task40extra.dtn-plane-discrete-context.v1",
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        "mesh": mesh_payload, "cell_dofmap_sha256": dofs_digest.hexdigest(),
        "orientation": _array_signature(mesh.topology.get_cell_permutation_info()),
        "needs_dof_transformations": bool(space.element.needs_dof_transformations),
        "basix_coefficients": _array_signature(element.coefficient_matrix),
        "element_degree": int(element.degree), "element_map_type": element.map_type.name,
        "MPC": mpc_payload, "config_sha256": hashlib.sha256(_canonical_json_bytes(cfg.as_jsonable())).hexdigest(),
        "gauss": {"degree": int(qdegree), "rule": "current_FFCx_default_facet_rule",
                  "facet_cell": "quadrilateral", "compiled_forms_verified": {
                      f"{side}/{component}": assembler.compiled_gauss_identity
                      for (side, component), assembler in surface_assemblers.items()}},
        "ABI": {"python": sys.version, "numpy": np.__version__, "basix": basix.__version__,
                "dolfinx": dolfinx.__version__, "dolfinx_mpc": package_version("dolfinx_mpc"),
                "ffcx": ffcx.__version__, "PETSc": PETSc.Sys.getVersion(),
                "scalar": str(np.dtype(PETSc.ScalarType)), "integer": str(np.dtype(PETSc.IntType))},
    }
    if quotient_context is not None:
        from .y_orbit_quotient_context import YOrbitTwoCellQuotientContext, _config_sha256
        from .y_orbit_condensed_adapter import _mpc_expansion_width
        if not isinstance(quotient_context, YOrbitTwoCellQuotientContext):
            raise TypeError("quotient context must use the frozen two-cell contract")
        expected_local_cells = 40
        if quotient_context.direct_profile_name is not None:
            from .y_orbit_raw_observer_admission import direct_raw_observer_expected_local_cells
            expected_local_cells = direct_raw_observer_expected_local_cells(quotient_context, cfg)
        if (quotient_context.assembly_config_sha256 != _config_sha256(cfg)
                or int(element.degree) != 4 or cell_count != expected_local_cells or int(qdegree) != 23
                or not all(np.array_equal(np.unique(mesh.geometry.x[:, axis]), expected)
                           for axis, expected in enumerate(quotient_context.local_axes))):
            raise ValueError("actual local mesh/config/Basix/Gauss differs from the frozen p4 quotient")
        rows = int(space.dofmap.index_map.size_local)
        width = _mpc_expansion_width(mpc, rows)
        constraints = Path(__file__).parent.parent / "constraints"
        extra_sources = [Path(__file__).with_name("y_orbit_quotient_context.py"),
                         Path(__file__).with_name("fullspace_same_mesh_hcurl_pmg_global.py"),
                         Path(__file__).with_name("y_orbit_condensed_adapter.py"),
                         constraints/"floquet_3d.py", constraints/"floquet_3d_high_order.py",
                         constraints/"high_order_floquet_trace.py"]
        payload["source_sha256"].update({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in extra_sources})
        payload["y_orbit_quotient"] = {
            "contract": quotient_context.identity(), "contract_sha256": quotient_context.sha256,
            "actual_local_cells": cell_count, "actual_local_storage_rows": rows,
            "actual_finalized_mpc_max_expansion_width": width,
            "actual_finalized_mpc_slave_rows": len(mpc.slaves),
            "actual_finalized_mpc_nonzero_master_check": "existing public-map admission validator",
            "local_boundary_area": float((cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)),
            "global_boundary_area": float((cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*quotient_context.replication_count),
            "twist_requires_global_dual_rhs_transport": True,
        }
    return deep_frozen_identity(payload)


def validate_phase_gauge(gauge: str) -> str:
    if gauge not in {GLOBAL_Z, BOUNDARY_PLANE}:
        raise ValueError("DtN phase gauge must be global_z or explicit boundary_plane")
    return gauge


def port_plane_z(mode: Any, cfg: Any) -> float:
    if mode.side not in {"top", "bottom"}:
        raise ValueError("DtN port side must be top or bottom")
    return float(cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min)


def assembly_projection_denominator(mode: Any, cfg: Any, gauge: str) -> float:
    validate_phase_gauge(gauge)
    if gauge == GLOBAL_Z:
        from .dtn_port_3d import _mode_projection_denominator
        return _mode_projection_denominator(mode, cfg)
    # No exp/global H/division in this primary centered normalization path.
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    result = float(area * mode.electric_tangential_norm_sq)
    if not np.isfinite(result) or result <= 0:
        raise ValueError("boundary-plane DtN normalization must be finite and positive")
    return result


def phase_gauge_descriptor(mode: Any, cfg: Any, gauge: str) -> dict[str, Any]:
    validate_phase_gauge(gauge)
    exponent = 1j * complex(mode.k_vector[2]) * port_plane_z(mode, cfg)
    if not np.isfinite(exponent):
        raise ValueError("DtN phase exponent is nonfinite")
    return {
        "schema": GAUGE_SCHEMA, "gauge": gauge,
        "port_plane_z": port_plane_z(mode, cfg),
        "phase_convention": ("exp(i*alpha*x+i*gamma*y+i*kz*(z-z_port))"
                             if gauge == BOUNDARY_PLANE else "exp(i*alpha*x+i*gamma*y+i*kz*z)"),
        "solver_coordinate": "b=s*a_global" if gauge == BOUNDARY_PLANE else "a_global",
        "log_abs_physical_boundary_phase": float(exponent.real),
        "argument_physical_boundary_phase": float(exponent.imag),
        "primary_coefficients_from_direct_centered_UFL": gauge == BOUNDARY_PLANE,
        "primary_does_not_require_global_exponential": gauge == BOUNDARY_PLANE,
        "future_identity_can_store_log_scale_without_changing_mode_keys": True,
        "absolute_sparse_floor": 1e-30, "relative_sparse_cutoff": 1e-13,
        "cutoff_scope": "existing collective component and combination stages, unchanged",
    }


def _conversion_scale(mode: Any, cfg: Any, gauge: str) -> complex:
    validate_phase_gauge(gauge)
    if gauge == GLOBAL_Z:
        return 1 + 0j
    exponent = 1j * complex(mode.k_vector[2]) * port_plane_z(mode, cfg)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        scale = complex(np.exp(exponent))
    if not np.isfinite(scale) or scale == 0:
        raise FloatingPointError("global/plane coordinate scale is zero or nonfinite; conversion unrepresentable")
    return scale


def _values(values: Any, modes: Sequence[Any]) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim not in (1, 2) or result.shape[0] != len(modes):
        raise ValueError("mode amplitudes/RHS must have complete ordered vector or multiRHS shape")
    if not np.isfinite(result).all():
        raise ValueError("mode amplitudes/RHS are nonfinite")
    return result


def _convert(values: Any, modes: Sequence[Any], cfg: Any, gauge: str,
             *, divide: bool, conjugate: bool) -> np.ndarray:
    values = _values(values, modes)
    scales = []
    for index, mode in enumerate(modes):
        try:
            scales.append(_conversion_scale(mode, cfg, gauge))
        except FloatingPointError as error:
            raise PhaseGaugeConversionError(str(error), index, mode) from error
    scales = np.asarray(scales, dtype=np.complex128)
    if conjugate:
        scales = np.conjugate(scales)
    if values.ndim == 2:
        scales = scales[:, None]
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        result = values / scales if divide else values * scales
    invalid = ~np.isfinite(result) | ((values != 0) & (result == 0))
    if np.any(invalid):
        invalid_rows = np.any(invalid, axis=1) if invalid.ndim == 2 else invalid
        index = int(np.flatnonzero(invalid_rows)[0])
        raise PhaseGaugeConversionError("global/plane output or RHS conversion overflows or loses a nonzero value",
                                        index, modes[index])
    return np.ascontiguousarray(result)


def global_amplitudes_from_solver(values, modes, cfg, gauge):
    return _convert(values, modes, cfg, gauge, divide=True, conjugate=False)


def solver_amplitudes_from_global(values, modes, cfg, gauge):
    return _convert(values, modes, cfg, gauge, divide=False, conjugate=False)


def plane_port_rhs_from_global(values, modes, cfg, gauge):
    return _convert(values, modes, cfg, gauge, divide=True, conjugate=True)


def global_port_rhs_from_plane(values, modes, cfg, gauge):
    return _convert(values, modes, cfg, gauge, divide=False, conjugate=True)


def incident_projection_in_solver_coordinates(mode: Any, cfg: Any, gauge: str) -> complex:
    validate_phase_gauge(gauge)
    if gauge == GLOBAL_Z:
        from .dtn_port_3d import _incident_projection_onto_top_mode
        return _incident_projection_onto_top_mode(mode, cfg)
    if mode.side != "top" or mode.m != 0 or mode.n != 0:
        return 0 + 0j
    # Current qualification is air1. Other conventions must pass an independent
    # same-Gauss/RHS gate before use, rather than silently repairing old semantics.
    if complex(cfg.n_air) != 1 + 0j:
        raise NotImplementedError("boundary-plane incident contract is initially qualified only for air1")
    if complex(mode.k_vector[2]).imag != 0:
        raise NotImplementedError("plane incident equivalence initially requires real outgoing top00 kz")
    incident_e = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    overlap = np.vdot(np.asarray(mode.e_vector)[:2], incident_e[:2])
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    phase = np.exp(1j * complex(cfg.kz) * port_plane_z(mode, cfg))
    result = complex(area * overlap * phase / assembly_projection_denominator(mode, cfg, gauge))
    if not np.isfinite(result):
        raise FloatingPointError("direct plane incident projection is nonfinite")
    return result


def outgoing_solver_amplitudes(total: Any, incident: Any, modes: Sequence[Any]) -> np.ndarray:
    total, incident = _values(total, modes), _values(incident, modes)
    if total.shape != incident.shape:
        raise ValueError("total and incident mode amplitudes have different RHS shapes")
    result = total.copy()
    for index, mode in enumerate(modes):
        if mode.side == "top":
            result[index] -= incident[index]
        elif mode.side != "bottom":
            raise ValueError("DtN port side must be top or bottom")
    return result


def boundary_mode_power_from_solver(mode: Any, cfg: Any, value: complex, gauge: str) -> float:
    validate_phase_gauge(gauge)
    if gauge == GLOBAL_Z:
        from .dtn_port_3d import _mode_power_at_boundary
        return _mode_power_at_boundary(mode, cfg, value)
    from ..common.modes_3d import mode_power
    from .dtn_port_3d import _outward_normal
    field = complex(value) * np.asarray(mode.e_vector, dtype=np.complex128)
    reference_field = np.asarray(mode.e_vector, dtype=np.complex128)
    if (not np.isfinite(field).all()
            or np.any((complex(value) != 0) & (reference_field != 0) & (field == 0))):
        raise FloatingPointError("finite-plane electric field is nonfinite or loses a nonzero product")
    denominator = cfg.k0*complex(cfg.mu_r)
    if not np.isfinite(denominator) or denominator == 0:
        raise FloatingPointError("finite-plane magnetic denominator is invalid")
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        magnetic = np.cross(mode.k_vector, field)/denominator
        flux = np.cross(field, np.conjugate(magnetic))
        result = float(mode_power(mode.k_vector, field, cfg, _outward_normal(mode.side)))
        unit = float(mode_power(mode.k_vector, reference_field, cfg, _outward_normal(mode.side)))
    if (not np.isfinite(magnetic).all() or not np.isfinite(flux).all()
            or not np.isfinite(result) or not np.isfinite(unit)
            or (value != 0 and unit > 0 and result == 0)):
        raise FloatingPointError("finite-plane magnetic field/power is nonfinite or unrepresentable")
    return result


def analytic_lossless_evanescent_zero_power(mode, cfg, field):
    """Narrow exact-zero theorem plus finite-arithmetic cancellation certificate.

    For real kx/ky, kz=i*kappa!=0 and real d=k0*mu, transversality gives
    Re(E cross conj(H))_z = -Re((k dot E)*conj(Ez))/d = 0.
    gamma_n=n*eps/(1-n*eps) bounds the explicitly counted dot/cross/division
    operations; propagated magnetic-field and power-rounding bounds are kept.
    No nonpropagating/unit-power classification or absolute tolerance is used.
    """
    k = np.asarray(mode.k_vector, dtype=np.complex128)
    e = np.asarray(mode.e_vector, dtype=np.complex128)
    E = np.asarray(field, dtype=np.complex128)
    report = {"proved": False, "theorem": "lossless transverse strictly-imaginary-kz normal real power is zero"}
    if k.shape != (3,) or e.shape != (3,) or E.shape != (3,) or not all(np.isfinite(a).all() for a in (k, e, E)):
        return {**report, "reason": "invalid/nonfinite wave or field"}
    mu, k0 = complex(cfg.mu_r), complex(cfg.k0)
    index = getattr(mode, "refractive_index", None)
    if index is None or mu.imag != 0 or mu.real == 0 or k0.imag != 0 or k0.real <= 0:
        return {**report, "reason": "real nonzero material/mu and positive real k0 required"}
    material_eps = complex(index)**2/mu
    if (not np.isfinite(material_eps) or material_eps.imag != 0
            or k[0].imag != 0 or k[1].imag != 0 or k[2].real != 0 or k[2].imag == 0):
        return {**report, "reason": "not analytically lossless strictly evanescent"}
    if not ((mode.side == "top" and k[2].imag > 0) or (mode.side == "bottom" and k[2].imag < 0)):
        return {**report, "reason": "side/kz is not the outgoing evanescent branch"}
    eps = np.finfo(float).eps
    gamma = lambda count: count*eps/(1-count*eps)
    dispersion_scale = float(np.sum(np.abs(k)**2)+abs((k0*complex(index))**2))
    dispersion_error = abs(np.dot(k, k)-(k0*complex(index))**2)
    unit_scale = float(np.sum(np.abs(k)*np.abs(e)))
    unit_error = abs(np.dot(k, e))
    field_scale = float(np.sum(np.abs(k)*np.abs(E)))
    field_residual = abs(np.dot(k, E))
    if (not all(np.isfinite(v) for v in (dispersion_scale, dispersion_error, unit_scale, unit_error, field_scale, field_residual))
            or np.linalg.norm(e) == 0 or dispersion_scale == 0
            or dispersion_error > gamma(64)*dispersion_scale
            or unit_error > gamma(32)*unit_scale
            or field_residual > gamma(64)*field_scale):
        return {**report, "reason": "Maxwell dispersion/transversality certificate failed"}
    d = abs(k0*mu)
    H = np.cross(k, E)/(k0*mu)
    flux = np.cross(E, np.conjugate(H))
    area = (cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)
    if not np.isfinite(area) or area <= 0 or not np.isfinite(d) or d <= 0:
        return {**report, "reason": "finite positive area and denominator magnitude required"}
    signed = float(0.5*area*np.real(flux[2])*(1 if mode.side == "top" else -1))
    ax = abs(k[1])*abs(E[2])+abs(k[2])*abs(E[1])
    ay = abs(k[2])*abs(E[0])+abs(k[0])*abs(E[2])
    flux_scale = abs(E[0])*abs(H[1])+abs(E[1])*abs(H[0])
    if not all(np.isfinite(value) and value >= 0 for value in (ax, ay, flux_scale)):
        return {**report, "reason": "invalid intermediate operation scale"}
    bound = float(0.5*area*(abs(E[2])*(field_residual+gamma(32)*field_scale)/d
                            +(gamma(32)+gamma(4))*flux_scale
                            +gamma(32)*(abs(E[0])*ay+abs(E[1])*ax)/d))
    # Relative gamma bounds require representable normal products. Tiny
    # subnormal cases cannot use this exception to a representability guard.
    operands = [(abs(k[j]), abs(E[l])) for j, l in ((1, 2), (2, 1), (2, 0), (0, 2))]
    operands += [(abs(E[0]), abs(H[1])), (abs(E[1]), abs(H[0]))]
    products = [left*right for left, right in operands]
    if (not np.isfinite(H).all() or not np.isfinite(flux).all()
            or not np.isfinite(signed) or not np.isfinite(bound) or bound < 0
            or any(left != 0 and right != 0 and product == 0 for (left, right), product in zip(operands, products, strict=True))
            or any(0 < value < np.finfo(float).tiny for value in products)):
        return {**report, "reason": "rounding-bound intermediate is unrepresentable/subnormal"}
    return {**report, "proved": bool(abs(signed) <= bound),
            "reason": "signed cancellation within counted machine-epsilon bound" if abs(signed) <= bound else "signed cancellation exceeds machine bound",
            "raw_signed_power": signed, "machine_epsilon_power_bound": bound,
            "dispersion_error": float(dispersion_error), "dispersion_bound": float(gamma(64)*dispersion_scale),
            "unit_transversality_error": float(unit_error), "unit_transversality_bound": float(gamma(32)*unit_scale),
            "field_transversality_error": float(field_residual), "field_transversality_bound": float(gamma(64)*field_scale),
            "mu": mu, "effective_epsilon": material_eps, "kz": complex(k[2])}


def prepare_boundary_plane_outputs(total, incident, modes, cfg, *, include_global=True):
    """Return direct finite-plane diagnostics, optionally legacy global output.

    A failed optional coordinate conversion returns an indexed controlled
    stop with the plane values/reason intact. No official R/T/A is generated.
    """
    total, incident = _values(total, modes), _values(incident, modes)
    if total.ndim != 1:
        raise ValueError("postprocessing requires one complete mode vector")
    outgoing = outgoing_solver_amplitudes(total, incident, modes)
    power = [boundary_mode_power_from_solver(mode, cfg, value, BOUNDARY_PLANE)
             for mode, value in zip(modes, outgoing, strict=True)]
    result = {"status": "plane_only_diagnostics", "official_results": False,
              "solver_auxiliary_coordinate": BOUNDARY_PLANE,
              "plane_total_auxiliary": total.copy(), "plane_incident_projections": incident.copy(),
              "plane_outgoing_auxiliary": outgoing, "direct_plane_outgoing_power_diagnostic": power}
    if not include_global:
        return result
    try:
        global_total = global_amplitudes_from_solver(total, modes, cfg, BOUNDARY_PLANE)
        global_incident = global_amplitudes_from_solver(incident, modes, cfg, BOUNDARY_PLANE)
    except PhaseGaugeConversionError as error:
        result.update({"status": "controlled_stop_global_output_unrepresentable",
                       "global_output_failure": {"mode_index": error.mode_index,
                                                 "mode_key": error.mode_key, "reason": error.reason}})
        return result
    result.update({"status": "representable_global_output",
                   "global_total_auxiliary": global_total, "global_incident_projections": global_incident})
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            global_outgoing = outgoing_solver_amplitudes(global_total, global_incident, modes)
        with np.errstate(over="ignore", invalid="ignore"):
            invalid_outgoing = np.flatnonzero(~np.isfinite(global_outgoing) | ~np.isfinite(np.abs(global_outgoing)))
        if len(invalid_outgoing):
            index = int(invalid_outgoing[0])
            raise PhaseGaugeConversionError("legacy global outgoing subtraction is nonfinite", index, modes[index])
        returned_outgoing = solver_amplitudes_from_global(global_outgoing, modes, cfg, BOUNDARY_PLANE)
        for index, (mode, value) in enumerate(zip(modes, global_outgoing, strict=True)):
            expected = outgoing[index]
            if ((expected != 0 and returned_outgoing[index] == 0)
                    or not np.isfinite(returned_outgoing[index])
                    or abs(returned_outgoing[index]-expected) > 1e-10*(abs(returned_outgoing[index])+abs(expected))):
                raise PhaseGaugeConversionError("post-conversion outgoing subtraction/roundtrip loses consistency", index, mode)
            scale = _conversion_scale(mode, cfg, BOUNDARY_PLANE)
            global_field = value*scale*np.asarray(mode.e_vector)
            plane_field = expected*np.asarray(mode.e_vector)
            if (not np.isfinite(global_field).all()
                    or np.any((plane_field != 0) & (global_field == 0))):
                raise PhaseGaugeConversionError("post-conversion finite-plane field is unrepresentable", index, mode)
            magnetic = np.cross(mode.k_vector, plane_field)/(cfg.k0*complex(cfg.mu_r))
            operation_scale = 0.5*(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*np.linalg.norm(plane_field)*np.linalg.norm(magnetic)
            global_power = boundary_mode_power_from_solver(mode, cfg, value, GLOBAL_Z)
            difference = abs(global_power-power[index])
            positive_to_zero = bool(power[index] > 0 and global_power == 0)
            zero_certificate = None
            if positive_to_zero:
                zero_certificate = {
                    "plane": analytic_lossless_evanescent_zero_power(mode, cfg, plane_field),
                    "global": analytic_lossless_evanescent_zero_power(mode, cfg, global_field)}
                result.setdefault("analytic_zero_power_checks", []).append({"mode_index": index, "certificate": zero_certificate})
            proved_zero = (zero_certificate is not None and zero_certificate["plane"]["proved"]
                           and zero_certificate["global"]["proved"])
            if (not np.isfinite(global_power) or (positive_to_zero and not proved_zero)
                    or (difference > 1e-10*operation_scale)):
                error = PhaseGaugeConversionError("legacy global outgoing power differs from direct finite-plane power", index, mode)
                error.diagnostics = {"direct_plane_power": power[index], "legacy_global_power": global_power,
                                     "absolute_difference": difference, "power_operation_scale": float(operation_scale),
                                     "unchanged_limit": float(1e-10*operation_scale),
                                     "positive_plane_to_zero_global_check": bool(power[index] > 0 and global_power == 0),
                                     "analytic_zero_certificate": zero_certificate,
                                     "physical_mode_unit_power": getattr(mode, "power_per_unit_amplitude", None),
                                     "propagating": getattr(mode, "propagating", None),
                                     "k_vector": tuple(complex(x) for x in mode.k_vector),
                                     "e_vector": tuple(complex(x) for x in mode.e_vector),
                                     "global_outgoing": complex(value), "plane_outgoing": complex(expected)}
                raise error
    except PhaseGaugeConversionError as error:
        result.update({"status": "controlled_stop_global_output_inconsistent",
                       "global_output_failure": {"mode_index": error.mode_index,
                                                 "mode_key": error.mode_key, "reason": error.reason}})
        result["global_output_failure"]["operation_diagnostics"] = error.diagnostics
        return result
    result["global_output_component_consistency_checked"] = True
    return result
