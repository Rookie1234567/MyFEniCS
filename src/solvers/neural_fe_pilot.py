"""Opt-in reviewed single-degree Maxwell pilot; ordinary defaults unchanged."""

import json
from dataclasses import replace
from time import perf_counter

import numpy as np

from src.common.optical_material_table import load_si_optical_constants
from src.geometry.neural_micro_pilot import geometry_config, hexa_inventory
from src.solvers.neural_fe_action_packet import (
    ActionPacket,
    array_hash,
    capacity_before_allocation,
    export_action_packet,
    operation_relative,
)


def physical_config(design):
    material = load_si_optical_constants(design["wavelength_nm"])
    if (
        material.provenance["material_table_sha256"]
        != design["materials"]["material_table_sha256"]
        or [material.n.real, material.n.imag] != design["materials"]["si_n"]
    ):
        raise ValueError("material table/design integrity mismatch")
    return replace(
        geometry_config(design),
        case_name="task042_v7_micro_0p7nm",
        n_substrate=material.n,
        n_grating=material.n,
        mu_r=material.mu,
    ), material


def physical_inventory(design):
    from src.solvers.fullspace_dtn_action import (
        _canonical_json_bytes,
        build_dynamic_mode_inventory,
    )

    cfg, material = physical_config(design)
    modes, rows, mode_hash = build_dynamic_mode_inventory(cfg)
    inventory = hexa_inventory(design["geometry"]["cells"], 3)
    capacity = capacity_before_allocation(inventory, len(modes))
    recipe = dict(
        geometry=design["geometry"],
        material=material.provenance,
        incidence=design["incidence"],
        boundary=design["boundary"],
        finite_element=design["finite_element"],
        modes=rows,
        mode_manifest_sha256=mode_hash,
        nominal_wavelength_nm=0.7,
    )
    identity = array_hash(np.frombuffer(_canonical_json_bytes(recipe), dtype=np.uint8))
    return dict(
        status="MATERIAL_READY_USER_SUPPLIED",
        physical_model_sha256=identity,
        full_channel_inventory=rows,
        mode_manifest_sha256=mode_hash,
        top_channels=sum(row["side"] == "top" for row in rows),
        bottom_channels=sum(row["side"] == "bottom" for row in rows),
        total_channels=len(rows),
        material=material.provenance,
        derived_fe_inventory=inventory,
        capacity_before_allocation=capacity,
        recipe=recipe,
    ), (cfg, modes, rows, mode_hash)


def build_and_check(design, moments, *, stage_callback):
    """Real S/native/recovery checks; no accurate solve or global FE matrix."""
    from dolfinx import fem
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.common_3d_fields import stage4_layered_background_field
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.learned_coarse_inverse import native_numpy_apply
    from src.solvers.neural_trace_dolfinx import pilot_space
    from src.solvers.p6_cell_condensed_action import (
        build_p6_cell_condensed_action_from_carrier,
    )

    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
    ):
        raise RuntimeError("qualified MPI1 complex128/int64 required")
    inventory, (cfg, modes, rows, mode_hash) = physical_inventory(design)
    stage_callback("capacity", inventory)
    costs = {}
    began = perf_counter()
    _, data, space, centers, tags, notch, axes = pilot_space(design)
    floquet = build_double_floquet_mpc(space, data, cfg)
    costs["mesh_space_mpc"] = perf_counter() - began
    if not np.array_equal(moments["native_cell_dofs"], space.dofmap.list):
        raise ValueError(
            "reused material-independent moment packet changed native cell numbering"
        )
    setup = dict(
        mesh=data.mesh, mesh_data=data, spaces={3: space}, floquets={3: floquet}
    )
    began = perf_counter()
    bundle = build_same_mesh_physical_action(
        setup,
        cfg,
        3,
        mode_inventory=(modes, rows, mode_hash),
        volume_quadrature_metadata=(
            {"quadrature_degree": 15},
            {"quadrature_degree": 15},
        ),
    )
    costs["original_physical_actions_jit"] = perf_counter() - began
    action = None
    try:
        stage_callback("original_action_built", dict(modes=len(modes), degree=3))
        began = perf_counter()
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bundle["volume_action"].bilinear_form),
            space,
            data.cell_tags,
            mpc=floquet.mpc,
            appended_global_rows=len(modes),
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            retain_local_original_for_native_audit=True,
            geometry_identity_policy="raw_unrounded",
            share_identity_cache=True,
        )
        action = build_p6_cell_condensed_action_from_carrier(
            condensed, bundle["dtn_action"].carrier, owns_condensed=True
        )
        costs["p3_local_condensation_port_setup"] = perf_counter() - began
        if (
            condensed.full_rows != 34050
            or condensed.active_rows != 18144
            or not np.array_equal(
                condensed.trace_constraints.owned_active_original_dofs,
                moments["master_native_rows"],
            )
        ):
            raise ValueError("actual canonical trace/native moment mapping mismatch")
        stage_callback(
            "condensation_built",
            dict(
                full_rows=condensed.full_rows,
                trace=condensed.active_rows,
                local_classes=len(condensed.retained_local_schur_by_class),
            ),
        )
        native = native_numpy_apply(bundle)
        began = perf_counter()
        total_rhs, rhs_metadata = build_physical_rhs(bundle)
        try:
            total_g = total_rhs.array.copy()
        finally:
            total_rhs.destroy()
        background = stage4_layered_background_field(space, cfg).x.array.copy()
        slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
        background[slaves] = 0
        background_alpha = action.original_hp_solve(action.apply_D_full(background))
        # Exact affine coordinate change of the original discrete total-field
        # equation. The known analytic layered background is never a FE solve.
        g = total_g - native(background)
        gp = np.zeros(len(modes), dtype=np.complex128)
        packet = export_action_packet(
            action,
            space,
            g,
            gp,
            background=background,
            background_alpha=background_alpha,
            total_g=total_g,
        )
        costs["rhs_analytic_background_packet_export"] = perf_counter() - began
        stage_callback(
            "physical_packet_built", dict(size=packet.size, bnorm=packet.bnorm)
        )
        rng = np.random.default_rng(420908)
        checks = []
        began = perf_counter()
        for index in range(3):
            x = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
            y = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
            Sx, SHy = packet.apply(x), packet.apply(y, adjoint=True)
            original_Sx = action.apply(x)
            field = packet.recover(x)
            original_field = action.recover_storage(x, full_rhs=g)
            af, port, Df = packet.uncondensed(field, x[packet.nt :])
            native_packet = af + action.apply_B_full(action.original_hp_solve(port))
            native_fe = native(field)
            audit = packet.audit(x)
            checks.append(
                dict(
                    index=index,
                    S_pair=operation_relative(
                        np.linalg.norm(Sx - original_Sx), np.linalg.norm(original_Sx)
                    ),
                    SH_dot=operation_relative(
                        abs(np.vdot(y, Sx) - np.vdot(SHy, x)),
                        max(abs(np.vdot(y, Sx)), abs(np.vdot(SHy, x))),
                    ),
                    recovery_pair=operation_relative(
                        np.linalg.norm(field - original_field),
                        np.linalg.norm(original_field),
                    ),
                    native_independent_pair=operation_relative(
                        np.linalg.norm(native_packet - native_fe),
                        np.linalg.norm(native_fe),
                    ),
                    D_pair=operation_relative(
                        np.linalg.norm(Df - action.apply_D_full(field)),
                        np.linalg.norm(Df),
                    ),
                    schur_native_identity=audit[
                        "schur_original_identity_operation_relative"
                    ],
                    recovery_original=operation_relative(
                        np.linalg.norm((g - af)[packet.a["idofs"]]),
                        max(np.linalg.norm(g), np.linalg.norm(af)),
                    ),
                    slave_zero=audit["slave_storage_max"],
                    port_unknown_norm=float(np.linalg.norm(x[packet.nt :])),
                )
            )
        # A separate nonzero interior/port RHS witness; no accurate solution.
        arbitrary_g = rng.standard_normal(
            condensed.full_rows
        ) + 1j * rng.standard_normal(condensed.full_rows)
        arbitrary_g[slaves] = 0
        arbitrary_gp = rng.standard_normal(len(modes)) + 1j * rng.standard_normal(
            len(modes)
        )
        probe = export_action_packet(
            action,
            space,
            arbitrary_g,
            arbitrary_gp,
            background=np.zeros_like(g),
            background_alpha=gp,
            total_g=arbitrary_g,
        )
        probe_audit = action.evaluate_native_residual(
            x, arbitrary_g, native, port_rhs=arbitrary_gp
        )
        probe_field = probe.recover(x)
        probe_native = native(probe_field)
        probe_af, probe_port, _ = probe.uncondensed(probe_field, x[probe.nt :])
        probe_native_packet = probe_af + action.apply_B_full(
            action.original_hp_solve(probe_port)
        )
        nonzero_rhs = dict(
            interior_rhs_norm=float(np.linalg.norm(arbitrary_g[packet.a["idofs"]])),
            port_rhs_norm=float(np.linalg.norm(arbitrary_gp)),
            native_independent_pair=operation_relative(
                np.linalg.norm(probe_native - probe_native_packet),
                np.linalg.norm(probe_native),
            ),
            recovery_pair=operation_relative(
                np.linalg.norm(
                    probe_field - action.recover_storage(x, full_rhs=arbitrary_g)
                ),
                np.linalg.norm(probe_field),
            ),
            original_audit={
                key: value
                for key, value in probe_audit.items()
                if isinstance(value, (float, int, bool, str))
            },
        )
        del probe
        costs["independent_original_FE_checks"] = perf_counter() - began
        canonical = sorted(
            [
                dict(
                    center=np.round(center, 13).tolist(),
                    tag=int(tag),
                    notch=bool(edited),
                )
                for center, tag, edited in zip(centers, tags, notch, strict=True)
            ],
            key=lambda row: row["center"],
        )
        import hashlib

        geometry = dict(
            canonical_geometry_tags_sha256=hashlib.sha256(
                json.dumps(canonical, sort_keys=True).encode()
            ).hexdigest(),
            canonical_mesh_sha256=hashlib.sha256(
                json.dumps(
                    sorted(np.round(data.mesh.geometry.x, 13).tolist()), sort_keys=True
                ).encode()
            ).hexdigest(),
            cells=len(tags),
            full_fe_rows=condensed.full_rows,
            independent_trace_rows=condensed.active_rows,
            interior_rows=condensed.interior_rows,
            slave_rows=len(slaves),
            tag_counts={
                str(tag): int(np.count_nonzero(tags == tag)) for tag in np.unique(tags)
            },
            notch_cells=int(np.count_nonzero(notch)),
            axes=[a.tolist() for a in axes],
            facet_counts={
                str(tag): int(np.count_nonzero(data.facet_tags.values == tag))
                for tag in np.unique(data.facet_tags.values)
            },
        )
        passed = all(
            row[key] <= 1e-10
            for row in checks
            for key in (
                "S_pair",
                "SH_dot",
                "recovery_pair",
                "native_independent_pair",
                "D_pair",
                "schur_native_identity",
                "recovery_original",
                "slave_zero",
            )
        )
        passed &= (
            nonzero_rhs["native_independent_pair"] <= 1e-10
            and nonzero_rhs["recovery_pair"] <= 1e-10
        )
        report = dict(
            status="PASS" if passed else "N1_REAL_FE_FAILED",
            physical=inventory,
            geometry=geometry,
            tests=checks,
            nonzero_rhs=nonzero_rhs,
            rhs_metadata=rhs_metadata,
            background="exact affine shift by interpolated analytic layered field; scattered trace and all ports start zero",
            g_scattered_sha256=array_hash(g),
            rhs_schur_sha256=array_hash(packet.a["b"]),
            local_factors_degree=3,
            global_p4_factor=False,
            global_FE_matrix=False,
            private_audit_CSR=False,
            reference_loaded=False,
            hidden_fallback=False,
            condensation_audit=condensed.build_audit,
            action_buffers=dict(action.buffer_inventory),
            costs_exclusive_seconds=costs,
            packet_payload_bytes=sum(v.nbytes for v in packet.a.values()),
        )
        return packet, report
    finally:
        if action is not None:
            action.destroy()
        destroy_same_mesh_physical_action(bundle)


def load_packet(path):
    with np.load(path, allow_pickle=False) as data:
        return ActionPacket({key: np.array(data[key]) for key in data.files})
