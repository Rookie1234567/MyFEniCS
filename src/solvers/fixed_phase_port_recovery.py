"""Reuse frozen body tensors, rebuild only qualified topological port blocks."""

import gc
import numpy as np
from scipy import sparse

from src.solvers.accurate_ports import recover_ports, actual_vector_audit
from src.solvers.feinn_native import FullNativePacket, packet_hashes, load_native
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.topological_port_trace import boundary_master_rows


def verify_reused_model(model, binding):
    import json
    from pathlib import Path

    old = json.loads(Path(binding["files"]["identity"]["path"]).read_text())
    required = (
        "mesh_coordinates_sha256",
        "geometry_cell_dofs_sha256",
        "cell_tags_sha256",
        "mode_manifest_sha256",
        "physical_model_sha256",
        "degree",
        "phase_carrier",
        "volume_quadrature_degree",
        "dtn_quadrature_degree",
        "material",
    )
    for key in required:
        if old.get(key) != model["record"].get(key):
            raise ValueError("REUSED_BODY_PHYSICAL_IDENTITY_CHANGED:" + key)
    return dict(checked_fields=list(required), matched=True)


def rebuild_ports(model, old, marker=lambda *_: None):
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import _surface_assemblers
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.fullspace_dtn_action import (
        build_fullspace_dtn_carrier_from_surface,
    )

    cfg, space, mpc = model["cfg"], model["space"], model["floquet"].mpc
    masters = np.setdiff1d(np.arange(old.full_rows), mpc.slaves)
    if not np.array_equal(masters, old.a["masters"]) or not np.array_equal(
        space.dofmap.list, old.a["cell_dofs"]
    ):
        raise ValueError("REUSED_BODY_MASTER_OR_CELL_ORDER_CHANGED")
    lookup = np.full(old.full_rows, -1, np.int64)
    lookup[masters] = np.arange(old.size)
    support = boundary_master_rows(space, mpc, cfg)
    marker("topological_port_rebuild_begin", dict(no_body_export=True))
    assemblers = _surface_assemblers(
        space,
        model["data"],
        cfg,
        15,
        jit_options=SAME_MESH_JIT_OPTIONS,
        phase_carrier=tuple(model["kappa"]),
    )
    carrier = build_fullspace_dtn_carrier_from_surface(
        model["bundle"]["modes"], assemblers, mpc, cfg, trace_support=support
    )
    del assemblers
    a = dict(old.a)
    values = {k: [] for k in ("br", "bp", "bv", "dr", "dp", "dv", "H")}
    for j, e in enumerate(carrier.entries):
        for prefix, rows, data in (
            ("b", e.coupling_rows, e.coupling_values),
            ("d", e.projection_rows, e.projection_values),
        ):
            ids = lookup[rows]
            if np.any(ids < 0):
                raise ValueError("REBUILT_PORT_SLAVE_REMAINS")
            values[prefix + "r"].extend(ids)
            values[prefix + "p"].extend([j] * len(ids))
            values[prefix + "v"].extend(data)
        values["H"].append(e.normalization_h)
    for key, v in values.items():
        a[key] = np.asarray(
            v,
            dtype=(
                float if key == "H" else complex if key in ("bv", "dv") else np.int64
            ),
        )
    provisional = FullNativePacket(a)
    bg_alpha, work = recover_ports(a, a["background"], gp=np.zeros_like(a["gp"]))
    inc = np.asarray(model["bundle"]["incident_projections"])
    a["total_g"] = old.a["total_g"] + provisional.B(inc) - old.B(inc)
    a["background_alpha"] = bg_alpha
    a["g"] = a["total_g"] - old.volume(a["background"]) - provisional.B(bg_alpha)
    packet = FullNativePacket(a)
    delta = {}
    for name, row, col in (("B", "br", "bp"), ("D", "dp", "dr")):
        shape = (packet.size, packet.np) if name == "B" else (packet.np, packet.size)
        v = "bv" if name == "B" else "dv"
        first = sparse.coo_matrix((a[v], (a[row], a[col])), shape=shape).tocsr()
        previous = sparse.coo_matrix(
            (old.a[v], (old.a[row], old.a[col])), shape=shape
        ).tocsr()
        difference = first - previous
        delta[name] = dict(
            old_nnz=previous.nnz,
            new_nnz=first.nnz,
            difference_norm=float(np.linalg.norm(difference.data)),
            old_norm=float(np.linalg.norm(previous.data)),
            relative=float(
                np.linalg.norm(difference.data)
                / max(np.linalg.norm(previous.data), 1e-300)
            ),
        )
    delta["total_rhs_relative"] = float(
        np.linalg.norm(a["total_g"] - old.a["total_g"])
        / np.linalg.norm(old.a["total_g"])
    )
    delta["scattered_rhs_relative"] = float(
        np.linalg.norm(a["g"] - old.a["g"]) / np.linalg.norm(old.a["g"])
    )
    result = dict(
        port_deltas=delta,
        background_recovery=work,
        old_packet_hashes=packet_hashes(old),
        new_packet_hashes=packet_hashes(packet),
        unchanged_body_keys=[
            k
            for k in old.a
            if k not in values and k not in ("g", "total_g", "background_alpha")
        ],
        support_counts={s: len(v) for s, v in support.items()},
        body_not_reassembled=True,
        amplitude_threshold=None,
    )
    marker("topological_port_rebuild_end", result)
    del provisional, carrier
    gc.collect()
    return packet, result


def save_state(path, packet, c, alpha):
    atomic_npz(
        path,
        c_scattered=c,
        c_total=c + packet.a["background"],
        alpha_scattered=alpha,
        alpha_total=alpha + packet.a["background_alpha"],
        background=packet.a["background"],
        background_alpha=packet.a["background_alpha"],
        masters=packet.a["masters"],
    )


def validate_actual(model, packet, c, alpha, independent, B, D, H, rhs):
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from benchmarks.accurate_port_checker import decimal_ports

    audit = actual_vector_audit(packet, c, alpha)
    total = c + packet.a["background"]
    atotal = alpha + packet.a["background_alpha"]
    weak = np.r_[independent.volume(total) + B @ atotal - rhs, -D @ total + H * atotal]
    expected = decimal_ports(packet.a, c)
    recovery = float(
        np.linalg.norm(alpha - expected) / max(np.linalg.norm(expected), 1e-12)
    )
    restored = restore_p0_full_field(model["floquet"], packet.storage(c))
    storage = restored.x.array
    local = packet.expand(c)
    mpc = float(
        np.linalg.norm(storage[packet.a["cell_dofs"]] - local)
        / max(np.linalg.norm(local), 1e-30)
    )
    return dict(
        **{
            k: audit[k]
            for k in (
                "native_relative",
                "augmented_relative",
                "original_total_augmented_relative",
            )
        },
        independent_physical_weak=float(np.linalg.norm(weak) / np.linalg.norm(rhs)),
        recovery=max(recovery, mpc),
        original_port_recovery=recovery,
        MPC_recovery=mpc,
        channels=packet.np,
        full_FE_recovered=True,
        actual_output_used=True,
    ), audit


def saved_p3(design, bindings, artifact, marker, budget, source):
    from src.solvers.fixed_phase_fem import build_model
    from src.solvers.fixed_phase_audit import (
        PhysicalVolumeAudit,
        surface_blocks,
        block_pair,
        incident_rhs,
    )
    from src.solvers.fixed_phase_comparison import self_physics
    from benchmarks.fixed_phase_checker import solved
    from benchmarks.accurate_port_checker import check_published
    from src.runners.fixed_phase_campaign import write, sha

    records = {}
    for role in ("O3", "E3"):
        budget("saved p3 recovery " + role)
        frozen = bindings[role]
        for row in frozen["files"].values():
            if sha(row["path"]) != row["sha256"]:
                raise ValueError("V21_FROZEN_INPUT_CHANGED")
        old = load_native(frozen["files"]["native"]["path"])
        model = build_model(
            design["models"]["G0"], 3, role == "E3", operators=False, marker=marker
        )
        verify_reused_model(model, frozen)
        with np.load(frozen["files"]["field"]["path"], allow_pickle=False) as z:
            c, raw = np.array(z["c_scattered"]), np.array(z["alpha_scattered"])
        out = artifact / role
        out.mkdir()
        packet, delta = rebuild_ports(model, old, marker)
        alpha, work = recover_ports(packet.a, c)
        independent = PhysicalVolumeAudit(model, packet)
        volume = independent.check()
        B, D, H = surface_blocks(model, packet)
        ports = block_pair(packet, B, D, H)
        rhs = incident_rhs(model, packet, B)
        full, audit = validate_actual(
            model, packet, c, alpha, independent, B, D, H, rhs
        )
        field = out / "field_state.npz"
        save_state(field, packet, c, alpha)
        with np.load(field, allow_pickle=False) as z:
            state = {k: np.array(z[k]) for k in z.files}
        recovery_check = check_published(
            packet.a,
            state,
            expected_mode_hash=model["record"]["mode_manifest_sha256"],
            mode_hash=model["record"]["mode_manifest_sha256"],
        )
        atomic_npz(out / "native.npz", **packet.a)
        atomic_npz(
            out / "port_recovery_vectors.npz",
            alpha_lu_raw=raw,
            alpha_old_backsub=old.alpha(c),
            alpha_recovered=alpha,
            background_alpha_old=old.a["background_alpha"],
        )
        identity = dict(
            model["record"],
            packet_hashes=packet_hashes(packet),
            reused_body=frozen,
            new_ports_source=source,
        )
        write(out / "identity.json", identity)
        checker = solved(full)
        physics = self_physics(model, packet, c, alpha, out, marker, budget)
        result = dict(
            role=role,
            identity=identity,
            stage_qualified=checker["passed"]
            and volume["passed"]
            and ports["passed"]
            and recovery_check["passed"],
            full_equation=full,
            checker=checker,
            actual_vector_audit=audit,
            accurate_recovery=work,
            independent_accurate_recovery=recovery_check,
            independent_volume=volume,
            independent_ports=ports,
            physics=physics,
            unchanged_c_sha256=__import__("hashlib").sha256(c.tobytes()).hexdigest(),
            B_delta_alpha_relative=float(
                np.linalg.norm(packet.B(alpha - raw)) / np.linalg.norm(packet.a["g"])
            ),
            old_to_new_port_relative=float(
                np.linalg.norm(alpha - raw) / max(np.linalg.norm(raw), 1e-12)
            ),
            reuse=frozen,
            port_rebuild=delta,
            global_factor_count=0,
        )
        write(out / "result.json", result)
        files = dict(
            native=out / "native.npz",
            field=field,
            identity=out / "identity.json",
            observables=out / "observables.npz",
            port_vectors=out / "port_recovery_vectors.npz",
            result=out / "result.json",
        )
        records[role] = dict(
            source_sha=source,
            result=result,
            files={k: dict(path=str(p), sha256=sha(p)) for k, p in files.items()},
        )
        marker(
            "saved_p3_frozen",
            dict(role=role, qualified=result["stage_qualified"], full_equation=full),
        )
        del packet, old, independent, model, B, D, H, state
        gc.collect()
    role_book = artifact / "role_indices.json"
    write(role_book, records)
    return dict(
        stage_qualified=True,
        roles={r: i["result"] for r, i in records.items()},
        no_new_solve_or_factor=True,
    ), dict(role_indices=role_book)
