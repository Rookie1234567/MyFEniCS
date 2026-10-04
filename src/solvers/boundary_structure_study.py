"""Boundary-only staged experiment, reusing the preparation runner and oracle."""

import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.boundary_structure_scope import plan_record, read_stage, window
from src.solvers.directional_boundary import (
    BoundaryLayout,
    DirectionalBoundaryAction,
    FacetPolynomial,
    zvalue,
)
from src.solvers.port_component_study import array_file, environment, relative
from src.solvers.target_boundary_witness import (
    NativeFacetTiles,
    build_patch,
    complex_value,
    dense_tiles,
    evaluate_tiled_witness,
    mode_object,
    parent_inventory,
)


def witness_plan():
    plan = plan_record()
    p = json.loads(Path(plan["parent_identity"]["path"]).read_text())["witness_plan"]
    if hashlib.sha256(Path(p["path"]).read_bytes()).hexdigest() != p["sha256"]:
        raise ValueError("frozen witness plan")
    return json.loads(Path(p["path"]).read_text())


class DirectionalFacetTiles(NativeFacetTiles):
    def __init__(self, *a, polynomial, **kw):
        super().__init__(*a, **kw)
        self.polynomial = polynomial
        self.local_records = {}

    def components(self, i, t):
        c, J, o, _z = self.faces[t]
        side = self.identities[i]["side"]
        k = np.array([complex_value(v) for v in self.identities[i]["k_vector"]])
        local = self.polynomial.integral(side, k, J, o, self.q)
        self.local_records[(i, t)] = local.copy()
        self.V.element.T_apply(
            local.view(np.float64).ravel(), self.permutations[c : c + 1], 4
        )
        rows = []
        values = []
        for j, row in enumerate(self.V.dofmap.cell_dofs(c)):
            masters, coeff = self.maps[int(row)]
            rows.extend(masters)
            values.extend(coeff[:, None] * local[j])
        unique, inverse = np.unique(np.array(rows, np.int64), return_inverse=True)
        out = np.zeros((len(unique), 2), np.complex128)
        np.add.at(out, inverse, np.array(values))
        self.costs["calls"] += 1
        return unique, out


def native_counter(n):
    path = window.TMP / "native_construct_count.json"
    used = json.loads(path.read_text())["count"] if path.exists() else 0
    if used + n > 32:
        raise RuntimeError("V38 cumulative native hex cap")
    write_json(path, {"count": used + n, "before_construct": True})


def bridge(folder):
    import basix.ufl

    from benchmarks.check_boundary_witness import read_arrays
    from src.runners.port_preparation import storage
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_form_vector,
        _ReusableSurfaceComponentAssembler,
        _set_scalar_constant,
    )
    from src.solvers.target_port_preparation import target_config

    cfg, _ = target_config()
    env = environment(fe=True)
    wp = witness_plan()
    rows = [
        dict(r, original_mode_index=r["mode_index"], mode_index=i)
        for i, r in enumerate(wp["selected_modes"])
    ]
    polynomial = FacetPolynomial(
        basix.ufl.element("N1curl", "hexahedron", 6).basix_element
    )
    capacity = json.loads(Path(plan_record()["parent_capacity"]["path"]).read_text())
    complete = []
    resume = window.TMP / "bridge_resume.json"
    if resume.exists():
        pointer = json.loads(resume.read_text())
        raw = Path(pointer["path"])
        if hashlib.sha256(raw.read_bytes()).hexdigest() != pointer["sha256"]:
            raise ValueError("bridge resume immutable prefix hash")
        complete = json.loads(raw.read_text())
        for done in complete:
            done.setdefault("record_source_sha", pointer["source_sha"])
            if done["description"] not in wp["patches"]:
                raise ValueError("bridge resume geometry")
            for field in ("native", "directional", "independent", "literal"):
                read_arrays(done[field])
    for desc in wp["patches"]:
        name = desc["name"]
        if any(p["description"] == desc for p in complete):
            continue
        native_counter(len(desc["cells"]))
        from benchmarks.archive_jit_cache import archive, restore_cached_sources

        storage(192 * 2**20, namespace="v38")
        restore_receipt = restore_cached_sources(
            Path(os.environ["FFCX_CACHE_DIR"]), window.TMP
        )
        start = perf_counter()
        data, V, mpc = build_patch(desc, cfg)
        setup = perf_counter() - start
        n = V.dofmap.index_map.size_global
        src = DirectionalFacetTiles(
            V, mpc.mpc, cfg, rows, 30, "v38-" + name, polynomial=polynomial
        )
        for i, r in enumerate(rows):
            r["tile_ids"] = list(src.tile_ids(i))
        native = {}
        cost = {"cache_source_restore": restore_receipt}
        began = perf_counter()
        if name == "min_ordinary":
            native = read_arrays(capacity["native_files"]["30"])
            cost["reused_native_q30"] = True
        else:
            # q30 forms only. Budget all four C/o/so plus temporary coexistence
            # from the observed q30 generation bound; no q60 native is called.
            # Observed q30 single form C/o/so ~96MB. Archive each generated
            # C/o losslessly before the next form; .so stays loaded/reusable.
            # Reserve covers 4 resident so, one C/o pair, compression overlap
            # and hashes/evidence, with no q60 UFL generation.
            cost["storage_before_JIT"] = storage(100 * 2**20, namespace="v38")

            assemblers = {}
            archives = []
            for side in ("top", "bottom"):
                for j in (0, 1):
                    storage(100 * 2**20, namespace="v38")
                    assemblers[(side, j)] = _ReusableSurfaceComponentAssembler(
                        V,
                        data,
                        cfg.tags.z_max if side == "top" else cfg.tags.z_min,
                        j,
                        quadrature_degree=30,
                    )
            archives.append(
                archive(
                    Path(os.environ["FFCX_CACHE_DIR"]),
                    window.TMP / f"jit_archive_{name}_complete",
                    namespace="v38",
                    suffixes=(".c", ".o"),
                    reuse_root=window.TMP,
                )
            )
            cost["jit_archives"] = archives
            for i, row in enumerate(rows):
                mode = mode_object(row)
                comp = np.zeros((n, 2), np.complex128)
                for j in (0, 1):
                    asm = assemblers[(mode.side, j)]
                    for c, v in [
                        (asm.alpha, mode.alpha),
                        (asm.gamma, mode.gamma),
                        (asm.kz, mode.k_vector[2]),
                    ]:
                        _set_scalar_constant(c, v)
                    vec = _assemble_mpc_form_vector(asm.form, mpc.mpc)
                    try:
                        comp[:, j] = vec.array.copy()
                    finally:
                        vec.destroy()
                traction = np.array([complex_value(v) for v in row["traction_vector"]])
                native.update(
                    {
                        f"native_components_{i}": comp,
                        f"C_{i}": comp @ (-traction[:2]),
                        f"D_{i}": (comp @ mode.e_vector[:2]).conj(),
                    }
                )
            del assemblers
        cost["native_including_JIT_seconds"] = perf_counter() - began
        native_receipt = (
            capacity["native_files"]["30"]
            if name == "min_ordinary"
            else array_file(folder / (name + "_native30.npz"), **native)
        )
        checks = []
        directional = {}
        independent = {}
        local = {}
        slow = NativeFacetTiles(V, mpc.mpc, cfg, rows, 60, "slow-" + name)
        for i in range(len(rows)):
            C, D, comp = dense_tiles(src, i, n)
            C60, D60, comp60 = dense_tiles(slow, i, n)
            directional.update({f"C_{i}": C, f"D_{i}": D, f"components_{i}": comp})
            independent.update(
                {f"C_{i}": C60, f"D_{i}": D60, f"components_{i}": comp60}
            )
            for kind, a, b in [
                ("native30_components", comp, native[f"native_components_{i}"]),
                ("native30_C", C, native[f"C_{i}"]),
                ("native30_D", D, native[f"D_{i}"]),
                ("q30_q60_C", C, C60),
                ("q30_q60_D", D, D60),
                ("q30_q60_components", comp, comp60),
            ]:
                checks.append(
                    dict(
                        index=i,
                        original_index=rows[i]["original_mode_index"],
                        kind=kind,
                        **relative(a, b),
                    )
                )
        for (i, t), a in src.local_records.items():
            local[f"local_{i}_{t}"] = a
        offsets = np.r_[0, np.cumsum([len(m[0]) for m in src.maps])].astype(np.int64)
        local.update(
            master_offsets=offsets,
            master_rows=np.concatenate([m[0] for m in src.maps]),
            master_dual_coefficients=np.concatenate([m[1] for m in src.maps]),
        )
        local.update(
            permutations=src.permutations,
            cell_dofs=np.array(
                [V.dofmap.cell_dofs(c) for c in range(len(desc["cells"]))]
            ),
            coordinates=V.mesh.geometry.x.copy(),
            geometry_dofmap=V.mesh.geometry.dofmap.copy(),
            slaves=np.asarray(mpc.mpc.slaves),
            interval_transform=polynomial.element.entity_transformations()["interval"],
            quadrilateral_transform=polynomial.element.entity_transformations()[
                "quadrilateral"
            ],
        )
        component = {"status": "NOT_RUN_MAPPING_GATE"}
        if all(c["pass_gate"] for c in checks):
            component = evaluate_tiled_witness(
                src, rows, n, native, folder, name, mpc.mpc.slaves, cfg
            )
        record = {
            "record_source_sha": os.environ["TASK042_RUN_SOURCE"],
            "description": desc,
            "checks": checks,
            "native": native_receipt,
            "directional": array_file(
                folder / (name + "_directional30.npz"), **directional
            ),
            "independent": array_file(
                folder / (name + "_independent60.npz"), **independent
            ),
            "literal": array_file(folder / (name + "_literal.npz"), **local),
            "component": component,
            "setup_seconds": setup,
            "cost": cost,
            "storage_rows": n,
            "slaves": list(map(int, mpc.mpc.slaves)),
        }
        complete.append(record)
        write_json(folder / "bridge_pending.json", complete)
        del src, slow, data, V, mpc, native, directional, independent, local
    qualified = all(
        all(c["pass_gate"] for c in p["checks"])
        and p["component"]["status"] == "TILED_P6_PATCH_QUALIFIED"
        for p in complete
    )
    return {
        "status": "NATIVE_P6_PERIODIC_PATCH_BRIDGE_QUALIFIED"
        if qualified
        else "NATIVE_P6_PATCH_BRIDGE_PARTIAL",
        "patches": complete,
        "environment": env,
        "q_native": 30,
        "q_independent": 60,
        "native_q60": "NOT_RUN_STORAGE_GATE_PRESERVED",
        "completed_native_hex_count": 20,
        "native_hex_count": json.loads(
            (window.TMP / "native_construct_count.json").read_text()
        )["count"],
        "MPI_qualification": 1,
        "shared_dependency": "Basix native basis; q60 direct 2D tabulation independent of directional contraction",
        "volume_action_count": 0,
        "target_solve": False,
    }


def make_action(modes, q):
    import basix.ufl

    parent, _ = parent_inventory()
    axes = parent["capacity"]["axes_nm"]
    p = FacetPolynomial(basix.ufl.element("N1curl", "hexahedron", 6).basix_element)
    phases = modes[0]["floquet_phases"]
    # Frozen inventory stores x/y named complex phase values.
    ph = (
        [zvalue(phases[k]) for k in ("x", "y")]
        if isinstance(phases, dict)
        else [zvalue(v) for v in phases]
    )
    layout = BoundaryLayout(axes["x"], axes["y"], p, ph)
    return DirectionalBoundaryAction(layout, modes, q)


def layout_stage(folder):
    parent, modes = parent_inventory()
    b, _ = read_stage("BRIDGE")
    if b["status"] != "NATIVE_P6_PERIODIC_PATCH_BRIDGE_QUALIFIED":
        raise RuntimeError("native bridge gate")
    action = make_action(modes, 30)
    l = action.layout
    if l.rows != 378432:
        raise ValueError("derived complete trace entity count")
    adapter = qualify_patch_layout(l, b, folder)
    numeric = {s + "_rows": l.maps[s] for s in ("bottom", "top")}
    numeric.update({s + "_primal_phases": l.weights[s] for s in ("bottom", "top")})
    numeric.update(
        {s + "_polynomial": l.polynomial.coefficients[s] for s in ("bottom", "top")}
    )
    receipt = array_file(folder / "layout.npz", **numeric)
    return {
        "status": "BOUNDARY_LAYOUT_ONLY_QUALIFIED",
        "layout": receipt,
        "native_patch_adapter": adapter,
        "rows": l.rows,
        "side_rows": l.side_rows,
        "faces_per_side": l.nx * l.ny,
        "numeric_cache_bytes": action.cache_bytes,
        "shared_layout_bytes": l.nbytes,
        "modes": len(modes),
        "environment": environment(fe=True),
        "global_volume_canonical_rows": "NOT_CONSTRUCTED_EXPLICIT_NATIVE_EXTRACT_SCATTER_ADAPTER_REQUIRED",
        "physical_parent": parent["contract"],
        "basis": "all native p6 tangential edge/face moments, local tensor polynomial coordinates",
        "decoder": "boundary periodic entity assembly; no volume numbering claimed",
        "target_solve": False,
    }


def execute(role, folder, state):
    if role == "BRIDGE":
        return bridge(folder)
    if role == "LAYOUT":
        return layout_stage(folder)
    if role == "COMPONENT":
        return component(folder)
    if role == "ORACLE":
        return explicit_oracle(folder)
    from benchmarks.check_boundary_structure import check_saved

    result = check_saved()
    if role == "DEPLOY":
        result.update(
            consumer="SOLVER_PACKAGE_NOT_QUALIFIED",
            row_adapter_required=True,
            global_solver_run=False,
        )
    return result


def bounded_call(function, *args, **kwargs):
    import signal

    old = signal.getsignal(signal.SIGALRM)

    def timeout(*_):
        raise TimeoutError("one complete boundary action 600s")

    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 600)
    try:
        return function(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def evaluate(action, x, y, alpha):
    start = perf_counter()
    numeric = {}
    times = {}
    for key, call, args, kw in [
        ("amplitudes", action.recover, (x,), {}),
        ("forward", action.apply, (x,), {}),
        ("adjoint", action.apply, (y,), {"adjoint": True}),
        ("modal", action.modal_rhs, (alpha,), {}),
        ("linear", action.apply, ((0.37 - 0.91j) * x,), {}),
        ("zero", action.apply, (np.zeros_like(x),), {}),
    ]:
        t = perf_counter()
        numeric[key] = bounded_call(call, *args, **kw)
        times[key] = perf_counter() - t
    checks = {
        "linearity": relative(numeric["linear"], (0.37 - 0.91j) * numeric["forward"]),
        "dual": relative(
            np.array([np.vdot(y, numeric["forward"])]),
            np.array([np.vdot(numeric["adjoint"], x)]),
        ),
        "zero_exact": not numeric["zero"].any(),
    }
    return numeric, {
        "wall_seconds": perf_counter() - start,
        "per_action_seconds": times,
        "checks": checks,
        "stats": dict(action.stats),
        "cache_bytes": action.cache_bytes,
    }


def component(folder):
    from src.runners.port_preparation import storage

    parent, modes = parent_inventory()
    layout_record, _ = read_stage("LAYOUT")
    plan = plan_record()
    nm = len(modes)
    n = layout_record["rows"]
    if n != 378432 or nm != 32060:
        raise ValueError("complete boundary inventory")
    inputs = []
    for seed in plan["component_seeds"]:
        rng = np.random.default_rng(seed)
        inputs.append(rng.normal(size=n) + 1j * rng.normal(size=n))
    alpha_rng = np.random.default_rng(423801)
    alpha = alpha_rng.normal(size=nm) + 1j * alpha_rng.normal(size=nm)
    receipt = array_file(folder / "inputs.npz", x=inputs[0], y=inputs[1], alpha=alpha)
    ladder = []
    all_outputs = {}
    qchecks = []
    maxqdiff = []
    for count in plan["cost_ladder"]:
        if count == nm:
            prior = ladder[-1]["measurement"]
            remaining = window.active_remaining("COMPONENT")
            ratio = nm / ladder[-1]["count"]
            # Literal linear prefix upper extrapolation includes both q groups
            # and both inputs; actual tensor contraction may grow more slowly.
            predicted = ratio * prior["wall_seconds"] * 4 + 120
            predicted_action = ratio * max(prior["per_action_seconds"].values())
            gate = {
                "predicted_remaining_seconds": predicted,
                "available_seconds": remaining,
                "predicted_max_single_action_seconds": predicted_action,
                "formula": "4*32060/1024*prefix6action_wall+120; no speedup/48h claim",
            }
            write_json(folder / "full_admission.json", gate)
            if predicted > remaining or predicted_action > 600:
                return {
                    "status": "BOUNDARY_ACTION_PARTIAL_COST_GATE",
                    "highest_completed_prefix": ladder[-1]["count"],
                    "ladder": ladder,
                    "inputs": receipt,
                    "admission": gate,
                    "target_solve": False,
                }
            storage(144 * 2**20, namespace="v38")
        t = perf_counter()
        action = make_action(modes[:count], 30)
        setup = perf_counter() - t
        output, measure = evaluate(action, inputs[0], inputs[1], alpha[:count])
        measure["setup_seconds"] = setup
        ladder.append({"count": count, "measurement": measure})
        write_json(folder / "ladder_pending.json", ladder)
        if count < nm:
            del output, action
            continue
        for k, a in output.items():
            all_outputs["q30_a_" + k] = a
        t = perf_counter()
        output2, measure2 = evaluate(action, inputs[1], inputs[0], alpha)
        for k, a in output2.items():
            all_outputs["q30_b_" + k] = a
        del action, output, output2
        action = make_action(modes, 60)
        for label, x, y in [("a", inputs[0], inputs[1]), ("b", inputs[1], inputs[0])]:
            output, measure60 = evaluate(action, x, y, alpha)
            for k, a in output.items():
                all_outputs["q60_" + label + "_" + k] = a
                qchecks.append(
                    dict(
                        input=label,
                        kind=k,
                        **relative(a, all_outputs["q30_" + label + "_" + k]),
                    )
                )
                if k == "amplitudes":
                    b = all_outputs["q30_" + label + "_" + k]
                    den = np.maximum(abs(a), abs(b))
                    diff = abs(a - b)
                    good = np.divide(diff, den, out=np.zeros_like(diff), where=den != 0)
                    maxqdiff.append(
                        {
                            "input": label,
                            "maximum": float(good.max()),
                            "worst_original_index": int(good.argmax()),
                            "numerator": float(diff[good.argmax()]),
                            "denominator": float(den[good.argmax()]),
                            "pass_gate": bool((good <= 1e-10).all()),
                        }
                    )
            if label == "a":
                q60measure = measure60
        hcheck, powercheck = [], []
        from src.solvers.target_port_preparation import target_config

        cfg, _ = target_config()
        for r in modes:
            k = np.array([zvalue(v) for v in r["k_vector"]])
            e = np.array([zvalue(v) for v in r["e_vector"]])
            hh = np.cross(k, e) / (cfg.k0 * cfg.mu_r)
            phase = np.exp(1j * k[2] * r["reference_plane_nm"])
            H = (
                cfg.period_x
                * cfg.period_y
                * np.vdot(e[:2], e[:2]).real
                * abs(phase) ** 2
            )
            hcheck.append(
                abs(H - r["projection_denominator"]) / r["projection_denominator"]
            )
            flux = (
                0.5
                * np.cross(e, hh.conj())[2].real
                * abs(phase) ** 2
                * cfg.period_x
                * cfg.period_y
                * (1 if r["side"] == "top" else -1)
            )
            powercheck.append(abs(flux - r["power_at_reference_unit_amplitude"]))
        all_outputs.update(
            H_errors=np.array(hcheck), unit_power_errors=np.array(powercheck)
        )
        resultfile = array_file(
            folder / "complete_actions.npz",
            compressed=True,
            deduplicate=True,
            **all_outputs,
        )
    return {
        "status": "COMPLETE_BOUNDARY_ACTIONS_FROZEN_PENDING_ORACLE",
        "inputs": receipt,
        "outputs": resultfile,
        "ladder": ladder,
        "second_input_q30": measure2,
        "q60_first": q60measure,
        "q60_second": measure60,
        "q30_q60": qchecks,
        "per_channel_q30_q60": maxqdiff,
        "mode_count": nm,
        "rows": n,
        "environment": environment(fe=True),
        "physical_parent_sha256": parent["contract"]["physical_contract_sha256"],
        "cache_bytes": action.cache_bytes,
        "H_max_relative": max(hcheck),
        "unit_power_max_absolute": max(powercheck),
        "MPI_qualification": 1,
        "target_solve": False,
        "official_RTA": False,
        "volume_actions": 0,
        "training": 0,
    }


def explicit_oracle(folder):
    """Complete selected channels by explicit facets and independent 2D rule."""
    import basix

    from benchmarks.check_boundary_witness import read_arrays

    component_record, _ = read_stage("COMPONENT")
    if component_record["status"] != "COMPLETE_BOUNDARY_ACTIONS_FROZEN_PENDING_ORACLE":
        return {"status": "NOT_RUN_INCOMPLETE_COMPONENT", "reference_read": False}
    saved = read_arrays(component_record["inputs"])
    _, modes = parent_inventory()
    wp = witness_plan()
    layout = make_action(modes[:1], 30).layout
    selected = wp["selected_modes"]
    rng = np.random.default_rng(423801)
    alpha_full = rng.normal(size=len(modes)) + 1j * rng.normal(size=len(modes))
    outputs = {}
    start = perf_counter()
    counter = 0
    costs = []
    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, 60)
    for label in ("a", "b"):
        outputs[label + "_forward"] = np.zeros(layout.rows, complex)
        outputs[label + "_adjoint"] = np.zeros(layout.rows, complex)
        outputs[label + "_modal"] = np.zeros(layout.rows, complex)
        outputs[label + "_amplitudes"] = np.zeros(len(selected), complex)
    for mi, row in enumerate(selected):
        side = row["side"]
        refz = 0 if side == "bottom" else 1
        # Full 882 basis direct tabulation, no polynomial contraction path.
        fulltab = layout.polynomial.element.tabulate(
            0, np.column_stack((rule, np.full(len(rule), refz)))
        )[0][:, :, :2]
        e = np.array([zvalue(v) for v in row["e_vector"][:2]])
        traction = np.array([zvalue(v) for v in row["traction_vector"][:2]])
        k = np.array([zvalue(v) for v in row["k_vector"]])
        C = np.zeros(layout.rows, complex)
        D = np.zeros(layout.rows, complex)
        cache = {}
        t = perf_counter()
        for i in range(layout.nx):
            for j in range(layout.ny):
                dx = layout.x[i + 1] - layout.x[i]
                dy = layout.y[j + 1] - layout.y[j]
                key = (dx.hex(), dy.hex())
                if key not in cache:
                    phase = np.exp(
                        1j * (k[0] * dx * rule[:, 0] + k[1] * dy * rule[:, 1])
                    )
                    full = np.einsum("q,qjc->jc", weights * phase, fulltab) * [dy, dx]
                    cache[key] = full[layout.polynomial.active[side]].copy()
                integral = cache[key] * np.exp(
                    1j
                    * (
                        k[0] * layout.x[i]
                        + k[1] * layout.y[j]
                        + k[2] * row["reference_plane_nm"]
                    )
                )
                ids = layout.maps[side][i, j]
                ph = layout.weights[side][i, j]
                np.add.at(C, ids, (integral @ (-traction)) * ph.conj())
                np.add.at(D, ids, (integral @ e).conj() * ph)
                counter += 1
        for label, xkey, ykey in [("a", "x", "y"), ("b", "y", "x")]:
            a = D @ saved[xkey] / row["projection_denominator"]
            h = np.vdot(C, saved[ykey]) / row["projection_denominator"]
            outputs[label + "_amplitudes"][mi] = a
            outputs[label + "_forward"] += C * a
            outputs[label + "_adjoint"] += D.conj() * h
            outputs[label + "_modal"] += C * alpha_full[row["mode_index"]]
        costs.append(
            {
                "original_index": row["mode_index"],
                "explicit_faces": layout.nx * layout.ny,
                "wall_seconds": perf_counter() - t,
                "cache_bytes": sum(v.nbytes for v in cache.values()),
            }
        )
        write_json(
            folder / "oracle_progress.json",
            {
                "completed_modes": mi + 1,
                "faces": counter,
                "elapsed_seconds": perf_counter() - start,
            },
        )
    # Separate contraction of exactly these 12 modes, with actual global indices.
    action = make_action(selected, 30)
    checks = []
    for label, xkey, ykey in [("a", "x", "y"), ("b", "y", "x")]:
        expect = {
            label + "_amplitudes": action.recover(saved[xkey]),
            label + "_forward": action.apply(saved[xkey]),
            label + "_adjoint": action.apply(saved[ykey], adjoint=True),
            label + "_modal": action.modal_rhs(
                np.array([alpha_full[r["mode_index"]] for r in selected])
            ),
        }
        for k, v in expect.items():
            checks.append(dict(kind=k, **relative(v, outputs[k])))
            outputs["new_" + k] = v
    return {
        "status": "FULL_SURFACE_SELECTED_ORACLE_QUALIFIED"
        if all(c["pass_gate"] for c in checks)
        else "ORACLE_NUMERICAL_GATE_FAILED",
        "checks": checks,
        "outputs": array_file(
            folder / "oracle.npz", compressed=True, deduplicate=True, **outputs
        ),
        "costs": costs,
        "explicit_face_visits": counter,
        "modes": [r["mode_index"] for r in selected],
        "coverage": "entire two boundary surfaces, fixed12mode",
        "wall_seconds": perf_counter() - start,
        "environment": environment(fe=True),
        "target_solve": False,
        "reference_read": False,
    }


def qualify_patch_layout(layout, bridge_record, folder):
    """Bounded local coordinate adapters, not full-volume canonical row IDs."""
    from benchmarks.check_boundary_witness import read_arrays

    checks = []
    receipts = []
    for patch in bridge_record["patches"]:
        desc = patch["description"]
        lit = read_arrays(patch["literal"])
        native = read_arrays(patch["native"])
        if "master_offsets" in lit:
            offsets = lit["master_offsets"]
            mr = lit["master_rows"]
            mc = lit["master_dual_coefficients"].conj()
        elif not patch["slaves"]:
            offsets = np.arange(patch["storage_rows"] + 1)
            mr = np.arange(patch["storage_rows"])
            mc = np.ones(len(mr), complex)
        else:
            raise ValueError("missing actual MPC map for local adapter")
        blocks = []
        ownblocks = []
        indices = []
        transforms = []
        for c, raw_rows in enumerate(lit["cell_dofs"]):
            coords = lit["coordinates"][lit["geometry_dofmap"][c]]
            bounds = np.column_stack((coords.min(axis=0), coords.max(axis=0))).tolist()
            found = [a for a in desc["cells"] if a["bounds_nm"] == bounds]
            if len(found) != 1:
                raise ValueError("literal native cell geometry bijection")
            side = found[0]["side"]
            i, j, _ = found[0]["indices"]
            active = layout.polynomial.active[side]
            T = np.zeros((882, len(active)))
            T[active, np.arange(len(active))] = 1
            layout.polynomial.element.T_apply(
                T.ravel(), len(active), int(lit["permutations"][c])
            )
            Ta = T[active]
            transforms.append(Ta)
            G = np.zeros((len(active), patch["storage_rows"]), complex)
            for a, row in enumerate(raw_rows[active]):
                q = slice(offsets[row], offsets[row + 1])
                G[a, mr[q]] = mc[q]
            blocks.append(Ta.T @ G)
            rows = layout.maps[side][i, j]
            indices.extend(rows)
            ownblocks.append((rows, layout.weights[side][i, j]))
        compact = np.unique(indices)
        left = np.row_stack(blocks)
        master = np.flatnonzero(np.any(left != 0, axis=0))
        left = left[:, master]
        right = np.zeros((left.shape[0], len(compact)), complex)
        cursor = 0
        for rows, ph in ownblocks:
            right[cursor + np.arange(len(rows)), np.searchsorted(compact, rows)] = ph
            cursor += len(rows)
        # This is a small fragment coordinate conversion only, independently
        # checked in both primal and dual. It is not a volume solve or PC.
        X, _, rank, _ = np.linalg.lstsq(left, right, rcond=None)
        identity = relative(left @ X, right)
        if (
            rank != len(master)
            or len(master) != len(compact)
            or not identity["pass_gate"]
        ):
            raise RuntimeError("native boundary local coordinate bijection gate")
        checks.append(
            dict(
                patch=desc["name"],
                kind="primal_bijection",
                rank=int(rank),
                native_rows=len(master),
                compact_rows=len(compact),
                **identity,
            )
        )
        # Independent full native fields paired with direct compact decoding.
        for mi, r in enumerate(witness_plan()["selected_modes"]):
            expected = np.zeros((len(compact), 2), complex)
            for c, a in enumerate(desc["cells"]):
                # Use original description order for geometry; compact local
                # coefficients do not depend on native cell renumbering.
                side = a["side"]
                i, j, _kidx = a["indices"]
                bounds = np.array(a["bounds_nm"])
                J = np.diag(bounds[:, 1] - bounds[:, 0])
                o = bounds[:, 0]
                local = layout.polynomial.integral(
                    side, np.array([zvalue(v) for v in r["k_vector"]]), J, o, 30
                )
                if r["side"] != side:
                    continue
                act = layout.polynomial.active[side]
                rows = layout.maps[side][i, j]
                np.add.at(
                    expected,
                    np.searchsorted(compact, rows),
                    local[act] * layout.weights[side][i, j, :, None].conj(),
                )
            e = np.array([zvalue(v) for v in r["e_vector"][:2]])
            tr = np.array([zvalue(v) for v in r["traction_vector"][:2]])
            for kind, desired in [
                ("C", expected @ (-tr)),
                ("D", (expected @ e).conj()),
            ]:
                actual = (
                    X.conj().T @ native[f"C_{mi}"][master]
                    if kind == "C"
                    else native[f"D_{mi}"][master] @ X
                )
                checks.append(
                    dict(
                        patch=desc["name"],
                        mode=r["mode_index"],
                        kind=kind,
                        **relative(actual, desired),
                    )
                )
        receipts.append(
            array_file(
                folder / (desc["name"] + "_row_adapter.npz"),
                compact_rows=compact,
                native_rows=master,
                primal_map=X,
                restricted_transforms=np.array(transforms),
            )
        )
    if not all(c["pass_gate"] for c in checks):
        raise RuntimeError("native compact extract/scatter gate")
    return {
        "status": "NATIVE_PATCH_BOUNDARY_ROW_BIJECTION_QUALIFIED",
        "checks": checks,
        "arrays": receipts,
        "full_volume_adapter": "NOT_QUALIFIED_NOT_CONSTRUCTED",
        "native_MPI_size": 1,
    }
