"""One p3 mesh/space/MPC environment for frozen-field integrals only.

No Maxwell operator, global CSR, factor, target solve, network or power campaign
is constructed. The original packet supplies fields; original MPC expands them.
"""

import hashlib
import json
from time import perf_counter

import numpy as np

from src.solvers.frozen_fe_error import complex_correlation, defect
from src.solvers.neural_fe_action_packet import array_hash, operation_relative


def field_localization(design, packet, cache, errors, original_fe):
    import ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.solvers.neural_fe_pilot import physical_inventory
    from src.solvers.neural_trace_dolfinx import pilot_space

    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
    ):
        raise RuntimeError("existing qualified complex128/int64 MPI1 required")
    timings, counts = (
        {},
        dict(
            FE_scalar_integrals=0,
            MPC_field_expansions=0,
            FE_environment_builds=1,
            Maxwell_operator_assemblies=0,
            global_CSR=0,
            new_factor=0,
            target_solves=0,
        ),
    )
    began = perf_counter()
    physical, (cfg, _, _, _) = physical_inventory(design)
    if any(
        physical[key] != original_fe["physical"][key]
        for key in ("physical_model_sha256", "mode_manifest_sha256")
    ):
        raise ValueError("rebuilt channel/physical recipe differs from original packet")
    _, data, space, centers, tags, notch, _ = pilot_space(design)
    floquet = build_double_floquet_mpc(space, data, cfg)
    a = packet.a
    dofs = np.asarray(space.dofmap.list)
    if (
        not np.array_equal(dofs[:, a["ipositions"]], a["idofs"])
        or not np.array_equal(dofs[:, a["tpositions"]], a["tdofs"])
        or not np.array_equal(np.sort(floquet.mpc.slaves), a["slaves"])
        or not np.array_equal(
            np.setdiff1d(a["tdofs"], floquet.mpc.slaves), a["masters"]
        )
    ):
        raise ValueError(
            "actual full/trace/interior/master/slave FE numbering mismatch"
        )
    canonical = sorted(
        [
            dict(center=np.round(center, 13).tolist(), tag=int(tag), notch=bool(edited))
            for center, tag, edited in zip(centers, tags, notch, strict=True)
        ],
        key=lambda row: row["center"],
    )
    geometry_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()
    if geometry_hash != original_fe["geometry"]["canonical_geometry_tags_sha256"]:
        raise ValueError("original canonical geometry/masks changed")
    regions = np.zeros(len(tags), dtype=np.int32)
    regions[(tags == 1) & ~notch] = 1
    regions[notch] = 2
    regions[tags == 2] = 3
    regions[tags == 3] = 4
    names = {1: "air_excluding_notch", 2: "notch_air", 3: "substrate", 4: "Si_block"}
    actual_counts = {names[k]: int(np.count_nonzero(regions == k)) for k in names}
    if actual_counts != dict(
        zip(names.values(), (192, 8, 48, 136), strict=True)
    ) or np.any(regions == 0):
        raise ValueError(
            "four mutually exclusive actual masks must cover 192/8/48/136 cells"
        )
    cell_ids = np.arange(data.mesh.topology.index_map(3).size_local, dtype=np.int32)
    region_tags = mesh.meshtags(data.mesh, 3, cell_ids, regions)
    timings["FE_mesh_space_MPC_and_identity"] = perf_counter() - began
    began = perf_counter()
    probe = fem.Function(floquet.mpc.function_space)
    first = fem.Function(floquet.mpc.function_space)
    second = fem.Function(floquet.mpc.function_space)
    homogeneous = fem.Function(floquet.mpc.function_space)
    dx = ufl.Measure(
        "dx",
        domain=data.mesh,
        subdomain_data=region_tags,
        metadata={"quadrature_degree": 15},
    )
    densities = [ufl.real(ufl.conj(probe[k]) * probe[k]) for k in range(3)]
    densities += [ufl.real(ufl.inner(probe, probe))]
    curl = ufl.curl(probe)
    densities += [ufl.real(ufl.conj(curl[k]) * curl[k]) / cfg.k0**2 for k in range(3)]
    densities += [ufl.real(ufl.inner(curl, curl)) / cfg.k0**2]
    forms = {
        region: [
            fem.form(density * (dx if region == 0 else dx(region)))
            for density in densities
        ]
        for region in (0, *names)
    }
    # Explicit first-argument conjugation, independent of UFL inner convention.
    cross_form = fem.form(ufl.dot(ufl.conj(first), second) * dx)
    difference_form = fem.form(ufl.real(ufl.inner(first - second, first - second)) * dx)
    total_difference_form = fem.form(
        ufl.real(ufl.inner(first - second - homogeneous, first - second - homogeneous))
        * dx
    )
    timings["FE_scalar_form_JIT_setup"] = perf_counter() - began

    def assemble(form):
        counts["FE_scalar_integrals"] += 1
        return fem.assemble_scalar(form)

    def integrals(expanded, region=0):
        probe.x.array[:] = expanded
        values = np.asarray([assemble(form).real for form in forms[region]])
        if not np.isfinite(values).all() or np.min(values) < -1e-12:
            raise ValueError("nonfinite or negative FE norm integral")
        return values

    def expand(storage):
        counts["MPC_field_expansions"] += 1
        return restore_p0_full_field(floquet, storage).x.array.copy()

    expanded = {name: expand(state["field"]) for name, state in cache.items()}
    mpc_checks = {}
    for name, state in cache.items():
        mpc_checks[name] = defect(
            expanded[name][a["tdofs"]], packet._expand(state["z"][: packet.nt])
        )
        if mpc_checks[name]["operation_relative"] > 1e-10:
            raise ValueError("original canonical trace expansion/MPC pair failed")
    background = expand(a["background"])
    ref = expanded["REF7"]
    ref_global = integrals(ref)
    ref_regions = {region: integrals(ref, region) for region in names}
    ref_total = integrals(ref + background)
    reference = dict(
        L2_squared=float(ref_global[3]),
        curl_scaled_squared=float(ref_global[7]),
        total_L2_squared=float(ref_total[3]),
        total_curl_scaled_squared=float(ref_total[7]),
        region_L2_squared={names[k]: float(v[3]) for k, v in ref_regions.items()},
        region_curl_scaled_squared={
            names[k]: float(v[7]) for k, v in ref_regions.items()
        },
    )
    field_rows, region_rows, consistency = [], [], {}
    began = perf_counter()
    for name, state in cache.items():
        candidate = integrals(expanded[name])
        field = state["field"]
        z = state["z"]
        e = cache["REF7"]["z"] - z
        delta = cache["REF7"]["field"] - field
        row = dict(
            state=name,
            coefficient_l2=float(np.linalg.norm(field)),
            trace_coefficient_l2=float(np.linalg.norm(z[: packet.nt])),
            internal_coefficient_l2=float(np.linalg.norm(field[a["idofs"]])),
            port_coefficient_l2=float(np.linalg.norm(z[packet.nt :])),
            error_coefficient_l2=float(np.linalg.norm(delta)),
            trace_error_coefficient_l2=float(np.linalg.norm(e[: packet.nt])),
            internal_error_coefficient_l2=float(np.linalg.norm(delta[a["idofs"]])),
            port_error_coefficient_l2=float(np.linalg.norm(e[packet.nt :])),
            scattered_L2=float(np.sqrt(max(candidate[3], 0))),
            scattered_curl_scaled_L2=float(np.sqrt(max(candidate[7], 0))),
            coefficient_unit="original native FE coefficient; not physical L2",
            field_norm_unit="incident-normalized E times nm^(3/2)",
        )
        if name == "REF7":
            field_rows.append(row)
            continue
        expanded_error = ref - expanded[name]
        error_global = integrals(expanded_error)
        regions_error = {region: integrals(expanded_error, region) for region in names}
        error_hom = expand(errors[name]["homogeneous"])
        first.x.array[:], second.x.array[:] = expanded_error, error_hom
        hom_difference_squared = float(assemble(difference_form).real)
        # Both total fields include exactly the same background; no normalization.
        first.x.array[:], second.x.array[:] = (
            ref + background,
            expanded[name] + background,
        )
        homogeneous.x.array[:] = expanded_error
        total_minus_scattered_squared = float(assemble(total_difference_form).real)
        total_error = integrals((ref + background) - (expanded[name] + background))
        first.x.array[:], second.x.array[:] = ref, expanded[name]
        inner = complex(assemble(cross_form))
        correlation = complex_correlation(inner, ref_global[3], candidate[3])
        trace_storage = np.zeros(packet.full_rows, dtype=np.complex128)
        trace_storage[a["masters"]] = e[: packet.nt]
        interior_storage = np.zeros_like(trace_storage)
        interior_storage[a["idofs"]] = delta[a["idofs"]]
        trace_field, internal_field = expand(trace_storage), expand(interior_storage)
        trace_l2_sq, internal_l2_sq = (
            integrals(trace_field)[3],
            integrals(internal_field)[3],
        )
        first.x.array[:], second.x.array[:] = trace_field, internal_field
        trace_internal_cross = complex(assemble(cross_form))
        expanded_norm_sq = trace_l2_sq + internal_l2_sq + 2 * trace_internal_cross.real
        l2_sum = sum(v[3] for v in regions_error.values())
        curl_sum = sum(v[7] for v in regions_error.values())
        consistency[name] = dict(
            homogeneous_field_difference_L2_squared=hom_difference_squared,
            homogeneous_field_relative=operation_relative(
                np.sqrt(max(hom_difference_squared, 0)), np.sqrt(error_global[3])
            ),
            total_minus_scattered_error_L2_squared=total_minus_scattered_squared,
            total_error_identity=defect(
                np.array([total_error[3], total_error[7]]), error_global[[3, 7]]
            ),
            region_L2_identity=defect(np.array([l2_sum]), np.array([error_global[3]])),
            region_curl_identity=defect(
                np.array([curl_sum]), np.array([error_global[7]])
            ),
            component_L2_identity=defect(
                np.array([sum(error_global[:3])]), np.array([error_global[3]])
            ),
            component_curl_identity=defect(
                np.array([sum(error_global[4:7])]), np.array([error_global[7]])
            ),
            trace_internal_cross_identity=defect(
                np.array([expanded_norm_sq]), np.array([error_global[3]])
            ),
        )
        row.update(
            error_L2=float(np.sqrt(max(error_global[3], 0))),
            error_curl_scaled_L2=float(np.sqrt(max(error_global[7], 0))),
            scattered_L2_relative=float(np.sqrt(error_global[3] / ref_global[3])),
            scattered_curl_scaled_relative=float(
                np.sqrt(error_global[7] / ref_global[7])
            ),
            total_L2_relative=float(np.sqrt(total_error[3] / ref_total[3])),
            total_curl_scaled_relative=float(np.sqrt(total_error[7] / ref_total[7])),
            amplitude_norm_ratio=correlation["amplitude_norm_ratio"],
            correlation_real=correlation["correlation"].real
            if correlation["correlation"] is not None
            else None,
            correlation_imag=correlation["correlation"].imag
            if correlation["correlation"] is not None
            else None,
            correlation_absolute=abs(correlation["correlation"])
            if correlation["correlation"] is not None
            else None,
            inner_reference_candidate_real=inner.real,
            inner_reference_candidate_imag=inner.imag,
            trace_field_L2_squared=float(trace_l2_sq),
            internal_field_L2_squared=float(internal_l2_sq),
            trace_internal_cross_real=trace_internal_cross.real,
            trace_internal_cross_imag=trace_internal_cross.imag,
            error_L2_squared=float(error_global[3]),
            error_curl_scaled_squared=float(error_global[7]),
        )
        for k, component in enumerate("xyz"):
            row["error_E_" + component + "_squared"] = float(error_global[k])
            row["error_curl_" + component + "_scaled_squared"] = float(
                error_global[4 + k]
            )
        field_rows.append(row)
        for region in names:
            v, rv = regions_error[region], ref_regions[region]
            region_row = dict(
                state=name,
                region=names[region],
                cells=actual_counts[names[region]],
                error_L2_squared=float(v[3]),
                reference_L2_squared=float(rv[3]),
                error_L2_fraction=float(v[3] / error_global[3]),
                error_curl_scaled_squared=float(v[7]),
                reference_curl_scaled_squared=float(rv[7]),
                error_curl_fraction=float(v[7] / error_global[7]),
                unit="E^2 nm^3; curl divided by k0^2",
            )
            for k, component in enumerate("xyz"):
                region_row["error_E_" + component + "_squared"] = float(v[k])
                region_row["error_curl_" + component + "_scaled_squared"] = float(
                    v[4 + k]
                )
            region_rows.append(region_row)
    timings["FE_all_fixed_field_integrals"] = perf_counter() - began
    return dict(
        reference=reference,
        fields=field_rows,
        regions=region_rows,
        consistency=consistency,
        mpc_checks=mpc_checks,
        region_counts=actual_counts,
        geometry_sha256=geometry_hash,
        actual_cell_dofmap_sha256=array_hash(dofs),
        actual_master_sha256=array_hash(a["masters"]),
        actual_slave_sha256=array_hash(a["slaves"]),
        scalar_form_count=sum(map(len, forms.values())) + 3,
        quadrature_degree=15,
        correlation_convention="explicit dot(conj(reference),candidate)",
        counts=counts,
        costs_exclusive_seconds=timings,
        reference_feedback=False,
        new_power_report=False,
        global_FE_matrix=False,
        global_factor=False,
    )
