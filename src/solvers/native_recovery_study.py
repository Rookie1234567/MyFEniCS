"""V40 finite native recovery, stage packets and independent consumption.

All volume mathematics comes from the original assembly/condensation core.
This module schedules only the single authorized finite witness, not a solve.
"""

import json
import os
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
from scipy.sparse import csr_matrix

from benchmarks.check_boundary_witness import metric, read_arrays
from src.runners.task042_shared import write_json
from src.solvers.native_boundary_adapter import (
    CoupledNativeBoundaryAction,
    LocalNativeVolumeAction,
    NativeBoundaryAdapter,
    boundary_identity,
    build_literal_adapter,
    independent_trace_port_terms,
)
from src.solvers.native_integration_study import (
    native_literal,
    polynomial_volume,
    random_complex,
    selected_action,
)
from src.solvers.native_recovery_packets import (
    PacketStore,
    load_system,
    save_system,
    sha,
)
from src.solvers.native_recovery_scope import (
    ARTIFACT,
    PLAN,
    ROOT,
    charge_native,
    parent_adapter,
    plan_record,
    read_stage,
    reserve_classes,
    settle_class,
    window,
)
from src.solvers.port_component_study import environment


def dependencies():
    env = environment(fe=True)
    return {
        "plan": sha(PLAN),
        "material": sha(ROOT / "input/materials/si_optical_constants_v1.json"),
        "numeric_sources": {
            p: sha(ROOT / p)
            for p in (
                "src/solvers/common_3d_forms.py",
                "src/solvers/hcurl_assembly_time_condensation.py",
                "src/solvers/p6_cell_condensed_action.py",
                "src/solvers/native_boundary_adapter.py",
                "src/solvers/directional_boundary.py",
            )
        },
        "ABI": {
            k: env[k]
            for k in ("executable", "scalar", "IntType", "module_paths", "MPI_size")
        },
    }


def store():
    p = patch_record()
    expected = contract(read_arrays(p["literal"]), selected_action(p["description"]))
    return PacketStore(
        ARTIFACT / "checkpoints", dependencies(), expected_contract=expected
    )


def patch_record():
    return next(
        p
        for p in parent_adapter()["patches"]
        if p["description"]["name"] == plan_record()["selected_case"]
    )


def contract(lit, action):
    from src.solvers.bounded_port_provider import content_hash
    from src.solvers.target_port_preparation import geometry_contract, target_config

    cfg, mat = target_config()
    return {
        "schema": "native-volume-boundary-consumer.v1",
        "boundary": boundary_identity(action),
        "native": content_hash(lit),
        "physical": geometry_contract(cfg, mat)["physical_contract_sha256"],
        "material": sha(ROOT / "input/materials/si_optical_constants_v1.json"),
        "dependencies": dependencies(),
        "basis": "N1E-hexahedron-p6-Legendre-882",
        "q_volume": 15,
        "Hp": "IMPLICIT_IDENTITY",
        "port_D": "normalized_once",
    }


def public_carrier_check(system, C, D):
    from src.solvers.p6_cell_condensed_action import P6CellCondensedAction

    terms = independent_trace_port_terms(system, C, D)
    # Invoke the actual public constructor, with no cells/factors required to
    # exercise its independent-row carrier conversion.
    minimal = SimpleNamespace(
        matrix=None,
        retained_local_schur_by_class={},
        appended_rows=C.shape[1],
        cell_recovery_maps=(),
        trace_constraints=system.trace_constraints,
        active_rows=system.trace_constraints.active_rows,
        build_audit={},
    )
    action = P6CellCondensedAction(
        minimal, H_p=np.eye(C.shape[1], dtype=np.complex128), direct_trace_terms=terms
    )
    return {
        "constructor": "P6CellCondensedAction",
        "rows": len(system.trace_constraints.owned_active_original_dofs),
        "terms": len(terms),
        "audit": dict(action.audit),
        "new_LU": 0,
    }


def preflight(folder):
    from benchmarks.check_native_integration import native_entity_map_checks

    checks = []
    for p in parent_adapter()["patches"]:
        lit = read_arrays(p["literal"])
        old = read_arrays(p["adapter"])
        action = selected_action(p["description"])
        new, meta = build_literal_adapter(
            action.layout.polynomial.element,
            lit,
            p["description"],
            action.layout,
            int(old["sizes"][0]),
            lit["slaves"],
        )
        for key in (
            "E_data",
            "E_indices",
            "E_indptr",
            "compact_rows",
            "sizes",
            "slaves",
        ):
            if key in ("E_data",):
                checks.append(
                    dict(
                        patch=p["description"]["name"],
                        key=key,
                        **metric(new.arrays()[key], old[key]),
                    )
                )
            elif not np.array_equal(new.arrays()[key], old[key]):
                raise ValueError("old/new sparse entity inventory")
        checks += native_entity_map_checks(
            action.layout.polynomial.element,
            action.layout,
            p["description"],
            lit,
            new.arrays(),
        )
        values = read_arrays(p["vectors"])
        for label in ("a", "b", "interior", "zero", "scale"):
            x = values[label + "_x"]
            checks.append(
                dict(
                    kind="saved_native_extract_replay",
                    **metric(new.extract(x), values[label + "_t"]),
                )
            )
        target = np.zeros(new.native_size, np.complex128)
        w = values["boundary_dual"]
        checks.append(
            dict(
                kind="caller_owned_scatter",
                **metric(new.scatter_into(w, target), new.scatter(w)),
            )
        )
        if new.EH.format != "csc" or len(new.EH.indptr) != len(new.compact_rows) + 1:
            raise ValueError("bounded transpose pointer storage")
        p["construction_replayed"] = meta
    return {
        "status": "SPARSE_ENTITY_REPLAY_QUALIFIED"
        if all(c["passed"] for c in checks)
        else "NATIVE_RECOVERY_NOT_QUALIFIED",
        "checks": checks,
        "new_native_hex": 0,
        "new_LU": 0,
        "environment": environment(fe=True),
    }


def copy_exact_jit(folder):
    """Copy verified artifacts only; FFCx must select the identical signature."""
    import shutil
    import subprocess

    manifest = json.loads(
        (
            ROOT
            / "docs/task042_neural_coarse_inverse/outcomes/records/jit_inventory_v39.json"
        ).read_text()
    )
    parent_source = "79f8e25bda6e74d3222c23228360c3b1b9f5d519"
    for file in (
        "src/solvers/common_3d_forms.py",
        "src/solvers/target_port_preparation.py",
    ):
        old = subprocess.check_output(
            ["git", "show", parent_source + ":" + file], cwd=ROOT
        )
        if __import__("hashlib").sha256(old).hexdigest() != sha(ROOT / file):
            raise ValueError("JIT numerical dependency changed")
    old_adapter = parent_adapter().get("environment", None)
    env = environment(fe=True)
    # The formal successful adapter stores environment per patch.
    if old_adapter is None:
        old_adapter = parent_adapter()["patches"][0]["environment"]
    for k in ("executable", "scalar", "IntType", "module_paths"):
        if old_adapter[k] != env[k]:
            raise ValueError("JIT ABI identity")
    dest = Path(os.environ["XDG_CACHE_HOME"]) / "fenics"
    dest.mkdir(parents=True, exist_ok=True)
    copies = []
    for item in manifest["files"]:
        src = ROOT / item["path"]
        if sha(src) != item["sha256"]:
            raise ValueError("old JIT artifact hash")
        target = dest / src.name
        if target.exists():
            if sha(target) != item["sha256"]:
                raise ValueError("new JIT namespace collision")
        else:
            shutil.copyfile(src, target)
        copies.append(dict(item, new_path=str(target), new_sha256=sha(target)))
    row = {
        "files": copies,
        "copied_bytes": sum(c["bytes"] for c in copies),
        "source_dependencies_match": True,
        "ABI": env,
        "FFCx_signature_still_required": True,
    }
    write_json(folder / "jit_reuse_precheck.json", row)
    return row


def build(folder):
    from src.solvers.target_port_preparation import target_config

    s = store()
    if s.has("quadrature") and s.has("oracle") and s.has("system"):
        return {
            "status": "NATIVE_VOLUME_PACKETS_READY",
            "checkpoint_reuse": True,
            "root": str(s.root),
            "new_hex": 0,
            "new_LU": 0,
        }
    prior, _ = read_stage("PREFLIGHT")
    if prior["status"] != "SPARSE_ENTITY_REPLAY_QUALIFIED":
        raise ValueError("sparse preflight prerequisite")
    p = patch_record()
    desc = p["description"]
    cfg, _ = target_config()
    costs = {}
    # Calibrated V39 failed cold construction took 912.592s; its individual
    # kernel/LU times were not saved. Keep a conservative cold allowance,
    # complete checks and one limited repair in the same remaining window.
    remaining = window.native_remaining_inside_worker()
    forecast = {
        "selected_case": desc["name"],
        "hex": len(desc["cells"]),
        "cold_build_seconds_planned_upper": 1500,
        "exact_cache_seconds": "unknown_before_load",
        "checker_recovery_deployment_seconds_reserved": 300,
        "one_software_repair_seconds_reserved": 400,
        "calibration_source": "V39 failed COUPLED wall 912.591881218s; no accurate sub-timers",
        "required_native_remaining_seconds": 1900,
        "remaining_native_seconds": remaining,
        "class_cache_planned_bytes_upper": 8
        * (450**2 + 2 * 450 * 432 + 432**2 + 450**2)
        * 16,
        "peak_tree_planned_bytes_upper": 6 * 2**30,
        "new_JIT_coexist_bytes_upper": 3 * 2**29,
        "evidence_reserve_bytes": 256 * 2**20,
    }
    write_json(folder / "native_prior_plan.json", forecast)
    if (
        not s.has("system")
        and remaining < forecast["required_native_remaining_seconds"]
    ):
        raise RuntimeError(
            "chosen xy-corner native construction and repair reserve do not fit"
        )
    if not s.has("system"):
        import ufl
        from dolfinx import fem

        from src.solvers.common_3d_forms import _build_physical_volume_terms
        from src.solvers.hcurl_assembly_time_condensation import (
            _canonical_axis_aligned_coordinates,
            _owned_trace_numbering,
            _trace_constraint_map,
            build_unconstrained_assembly_time_condensation,
        )
        from src.solvers.target_boundary_witness import build_patch

        charge_native(len(desc["cells"]))
        began = perf_counter()
        data, V, floquet = build_patch(desc, cfg)
        lit = native_literal(V, floquet.mpc, desc)
        old = read_arrays(p["literal"])
        if any(not np.array_equal(lit[k], old[k]) for k in old):
            raise ValueError("native fixture literal identity")
        action = selected_action(desc)
        n, nm = V.dofmap.index_map.size_global, len(action.modes)
        element = V.element.basix_element
        ip = np.array(element.entity_dofs[3][0], np.int64)
        owned, mapping, trace_rows, _ = _owned_trace_numbering(
            V, tuple(d[ip] for d in lit["cell_dofs"])
        )
        constraints = _trace_constraint_map(V, owned, mapping, trace_rows, floquet.mpc)
        native = read_arrays(p["vectors"])
        carrier = public_carrier_check(
            SimpleNamespace(trace_constraints=constraints),
            native["C_from_adapter"],
            native["D_from_adapter"],
        )
        tags = np.full(len(desc["cells"]), -1, np.int32)
        tags[data.cell_tags.indices] = data.cell_tags.values
        classes = []
        for cell in range(len(desc["cells"])):
            _, widths = _canonical_axis_aligned_coordinates(
                V.mesh, cell, tolerance=1e-11, geometry_identity_policy="raw_unrounded"
            )
            classes.append((int(tags[cell]), *widths, int(lit["permutations"][cell])))
        unique = len(set(classes))
        costs["native_geometry_constraints_carrier"] = perf_counter() - began
        if unique > 8 or set(tags) != {cfg.tags.air, cfg.tags.substrate}:
            raise ValueError("native class/material prior inventory")
        geometry_metadata = {
            "description": desc,
            "contract": contract(lit, action),
            "class_keys": list(map(repr, classes)),
            "independent_trace_carrier": carrier,
            "costs": dict(costs),
            "class_count": unique,
            "n": int(n),
            "ports": nm,
        }
        if s.has("geometry"):
            old_meta, old_arrays = s.read("geometry")
            if old_meta["metadata"]["contract"] != geometry_metadata["contract"] or any(
                not np.array_equal(old_arrays[k], v)
                for k, v in {**lit, "cell_tags": tags}.items()
            ):
                raise ValueError("rebuild native geometry dependency mismatch")
        else:
            s.save("geometry", {**lit, "cell_tags": tags}, geometry_metadata)
        copy_exact_jit(folder)
        began = perf_counter()
        u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
        dx = ufl.Measure(
            "dx",
            domain=V.mesh,
            subdomain_data=data.cell_tags,
            metadata={"quadrature_degree": 15},
        )
        curl, mass = _build_physical_volume_terms(cfg, u, v, dx)
        compiled = fem.form(curl + mass)
        costs["native_volume_compile_or_exact_cache_load"] = perf_counter() - began
        write_json(
            folder / "compiled_kernel_identity.json",
            {
                "module": str(compiled.module.__name__),
                "file": str(compiled.module.__file__),
                "sha256": sha(compiled.module.__file__),
                "seconds": costs["native_volume_compile_or_exact_cache_load"],
            },
        )
        attempt = reserve_classes(unique)
        names = []

        def completed(key, arrays, timing):
            settle_class(attempt)
            name = "class_attempt_" + str(attempt) + "_" + str(len(names))
            s.save(name, arrays, {"original_key": repr(key), **timing})
            names.append(name)

        began = perf_counter()
        system = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            data.cell_tags,
            mpc=floquet.mpc,
            appended_global_rows=nm,
            strict_local_checks=True,
            retain_local_schur_for_matrix_free=True,
            retain_local_original_for_native_audit=True,
            materialize_global_matrix=False,
            geometry_identity_policy="raw_unrounded",
            share_identity_cache=True,
            class_checkpoint=completed,
        )
        costs["original_class_build_with_atomic_save"] = perf_counter() - began
        settle_class(attempt, complete=True)
        save_system(s, system, names)
        s.save("build_costs", {}, costs)
        # Persist the native oracle immediately, before quadrature or recovery.
        import dolfinx_mpc

        began = perf_counter()
        oracle_mat = dolfinx_mpc.assemble_matrix(compiled, floquet.mpc, diagval=0.0)
        oracle_mat.assemble()
        indptr, indices, values = oracle_mat.getValuesCSR()
        s.save(
            "oracle",
            {
                "data": values.copy(),
                "indices": indices.copy(),
                "indptr": indptr.copy(),
                "shape": np.array([n, n], np.int64),
            },
            {
                "original_native_assembly_seconds": perf_counter() - began,
                "unfactored": True,
                "hex": len(desc["cells"]),
            },
        )
        oracle_mat.destroy()
    _geometry, lit = s.read("geometry")
    system, class_data = load_system(s)
    if not s.has("oracle"):
        raise RuntimeError(
            "native CSR checkpoint missing: requires explicit bounded rebuild"
        )
    if not s.has("quadrature"):
        import basix

        # Original Basix element and its native direction wrapper can be
        # reconstructed without a native volume mesh, JIT or factorization.
        element = basix.create_element(
            basix.ElementFamily.N1E,
            basix.CellType.hexahedron,
            6,
            basix.LagrangeVariant.legendre,
        )
        # _orient_cell_tensor needs the native DOLFINx element transformation;
        # for this packet path use the exact Basix equivalent on both axes.
        arrays, checks, seen = {}, [], set()
        began = perf_counter()
        class_ids = s.read("system")[1]["cell_class"]
        for cell, ci in enumerate(class_ids):
            tag = int(lit["cell_tags"][cell])
            if tag in seen:
                continue
            seen.add(tag)
            eps = cfg.eps_r if tag == cfg.tags.air else cfg.substrate_index**2
            coords = lit["coordinates"][lit["geometry_dofmap"][cell]]
            for q in (15, 17):
                a = polynomial_volume(element, coords, eps, cfg.k0, cfg.mu_r, q)
                # Apply native basis-column orientation: T A T^T.
                element.T_apply(a.ravel(), element.dim, int(lit["permutations"][cell]))
                b = np.ascontiguousarray(a.T)
                element.T_apply(b.ravel(), element.dim, int(lit["permutations"][cell]))
                arrays[f"tag{tag}_q{q}"] = np.ascontiguousarray(b.T)
            arrays[f"tag{tag}_native"] = class_data[int(ci)]["original"]
            arrays[f"tag{tag}_cell"] = np.array([cell, ci], np.int64)
            checks += [
                dict(
                    kind=f"tag{tag}_q15_q17",
                    **metric(arrays[f"tag{tag}_q15"], arrays[f"tag{tag}_q17"]),
                ),
                dict(
                    kind=f"tag{tag}_native_q17",
                    **metric(arrays[f"tag{tag}_native"], arrays[f"tag{tag}_q17"]),
                ),
            ]
        s.save(
            "quadrature",
            arrays,
            {
                "checks": checks,
                "seconds": perf_counter() - began,
                "tags": sorted(seen),
                "orientation": "Basix T on both native tensor axes",
            },
        )
        if not all(c["passed"] for c in checks):
            return {
                "status": "NATIVE_RECOVERY_NOT_QUALIFIED",
                "failed_stage": "quadrature",
                "checks": checks,
            }
    cache = sum(
        v.nbytes
        for d in class_data
        for k, v in d.items()
        if k in ("lu", "pivots", "recovery", "rhs_trace", "schur", "identity")
    )
    if cache > 256 * 2**20:
        raise MemoryError("native cache capacity")
    return {
        "status": "NATIVE_VOLUME_PACKETS_READY",
        "checkpoint_root": str(s.root),
        "class_cache_bytes": cache,
        "classes": len(class_data),
        "costs": costs,
        "description": patch_record()["description"],
        "local_internal_LU_present": True,
        "global_LU": False,
        "PDE_solved": False,
    }


def loaded_objects():
    from src.solvers.p6_cell_condensed_action import P6CellCondensedAction

    s = store()
    geometry, lit = s.read("geometry")
    identity = geometry["metadata"]["contract"]
    p = patch_record()
    action = selected_action(p["description"])
    a = NativeBoundaryAdapter.from_arrays(read_arrays(p["adapter"]), identity=identity)
    system, classes = load_system(s)
    cell_ids = s.read("system")[1]["cell_class"]
    volume = LocalNativeVolumeAction(
        lit,
        [c["original"] for c in classes],
        cell_ids,
        a.native_size,
        identity=identity,
    )
    coupled = CoupledNativeBoundaryAction(a, action, volume, contract=identity)
    native = read_arrays(p["vectors"])
    C, D = native["C_from_adapter"], native["D_from_adapter"]
    condensed = P6CellCondensedAction(
        system,
        H_p=np.eye(C.shape[1], dtype=np.complex128),
        direct_trace_terms=independent_trace_port_terms(system, C, D),
    )
    d = s.read("oracle")[1]
    oracle = csr_matrix((d["data"], d["indices"], d["indptr"]), shape=tuple(d["shape"]))
    return s, lit, native, system, classes, volume, coupled, condensed, oracle


def recover(folder):
    s, lit, native, system, _classes, volume, coupled, condensed, oracle = (
        loaded_objects()
    )
    from benchmarks.check_native_recovery import audit_packets

    n, nm = oracle.shape[0], len(coupled.boundary.modes)
    rng = np.random.default_rng(423901)
    arrays = {
        "C_native": native["C_native"],
        "D_native": native["D_native"],
        "C_adapter": native["C_from_adapter"],
        "D_adapter": native["D_from_adapter"],
    }
    began = perf_counter()
    for label in ("a", "b", "zero", "scale"):
        if label == "zero":
            x = np.zeros(n, np.complex128)
        elif label == "scale":
            x = (0.37 - 0.91j) * arrays["a_x"]
        else:
            x = random_complex(rng, n)
            x[lit["slaves"]] = 0
        arrays[label + "_x"] = x
        arrays[label + "_volume"] = volume(x)
        arrays[label + "_adjoint_volume"] = volume(x, adjoint=True)
        arrays[label + "_action"] = coupled.apply(x)
        arrays[label + "_adjoint"] = coupled.apply(x, adjoint=True)
    f = random_complex(rng, n)
    f[lit["slaves"]] = 0
    g = random_complex(rng, nm)
    z = random_complex(rng, condensed.reduced_size)
    z2 = random_complex(rng, condensed.reduced_size)
    r = condensed.reduce_rhs(f, port_rhs=g, rhs_is_mpc_dual=True)
    u = condensed.recover_storage(z, full_rhs=f)
    expanded = condensed.recover_storage(z, full_rhs=f, expand_trace=True)
    arrays.update(
        f=f,
        g=g,
        z=z,
        z2=z2,
        alpha=z[system.active_rows :],
        reduced_rhs=r,
        schur_action=condensed.apply(z),
        u=u,
        expanded=expanded,
        u2=condensed.recover_storage(z2, full_rhs=f),
        u_difference=condensed.recover_storage(z - z2, full_rhs=f),
        u_zero=condensed.recover_storage(np.zeros_like(z), full_rhs=f),
    )
    C, D = native["C_native"], native["D_native"]
    arrays["rFE"] = f - (oracle @ u + C @ arrays["alpha"])
    arrays["rport"] = g + D @ u - arrays["alpha"]
    arrays["rnative"] = f - C @ g - (oracle @ u + C @ (D @ u))
    arrays["native_coupled_u"] = coupled.apply(u)
    arrays["reduced_injection"] = condensed.inject_trace_port(
        r - arrays["schur_action"]
    )
    s.save(
        "recovery",
        arrays,
        {
            "seconds": perf_counter() - began,
            "input_norms": {
                "f": float(np.linalg.norm(f)),
                "g": float(np.linalg.norm(g)),
            },
            "volume_calls": dict(volume.calls),
            "volume_seconds": dict(volume.seconds),
            "condensed_calls": dict(condensed.audit),
            "physical_solution": False,
        },
    )
    result = audit_packets(s)
    write_json(folder / "initial_independent_audit.json", result)
    return {
        "status": "COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES"
        if result["passed"]
        else "NATIVE_RECOVERY_NOT_QUALIFIED",
        "checks": result["checks"],
        "checkpoint": str(s.root),
        "costs": s.read("recovery")[0]["metadata"],
        "PDE_solved": False,
    }


def check(folder):
    from benchmarks.check_native_recovery import audit_packets

    result = audit_packets(store())
    return dict(
        result,
        status="SAVED_NATIVE_RECOVERY_QUALIFIED"
        if result["passed"]
        else "NATIVE_RECOVERY_NOT_QUALIFIED",
    )


def deploy(folder):
    checked, _ = read_stage("CHECK")
    if checked["status"] != "SAVED_NATIVE_RECOVERY_QUALIFIED":
        raise ValueError("independent physical callback checker prerequisite")
    began = perf_counter()
    s, _lit, native, _system, _classes, volume, coupled, condensed, oracle = (
        loaded_objects()
    )
    _row, saved = s.read("recovery")
    times = {"hash_decode_load_setup": perf_counter() - began}
    began = perf_counter()
    arrays = {
        "forward": coupled.apply(saved["a_x"]),
        "adjoint": coupled.apply(saved["b_x"], adjoint=True),
    }
    times["two_full_native_actions"] = perf_counter() - began
    began = perf_counter()
    arrays.update(
        u=condensed.recover_storage(saved["z"], full_rhs=saved["f"]),
        reduced_rhs=condensed.reduce_rhs(
            saved["f"], port_rhs=saved["g"], rhs_is_mpc_dual=True
        ),
    )
    times["nonzero_rhs_reduce_recover"] = perf_counter() - began
    checks = [
        dict(kind=key, **metric(arrays[key], saved[parent]))
        for key, parent in (
            ("forward", "a_action"),
            ("adjoint", "b_adjoint"),
            ("u", "u"),
            ("reduced_rhs", "reduced_rhs"),
        )
    ]
    began = perf_counter()
    alpha = saved["alpha"]
    C, D = native["C_native"], native["D_native"]
    arrays["rFE"] = saved["f"] - oracle @ arrays["u"] - C @ alpha
    arrays["rport"] = saved["g"] + D @ arrays["u"] - alpha
    arrays["rnative"] = (
        saved["f"] - C @ saved["g"] - oracle @ arrays["u"] - C @ (D @ arrays["u"])
    )
    checks.append(
        dict(
            kind="fresh_consumer_native_augmented_identity",
            **metric(arrays["rnative"], arrays["rFE"] - C @ arrays["rport"]),
        )
    )
    times["independent_original_CSR_residual_audit"] = perf_counter() - began
    began = perf_counter()
    receipt = s.save(
        "consumer",
        arrays,
        {
            "costs": times,
            "contract": coupled.adapter.identity,
            "callback": "REAL_SAVED_NATIVE_CLASS_TENSORS",
            "fresh_process": True,
        },
    )
    times["save_hash_IO"] = perf_counter() - began
    return {
        "status": "REAL_VOLUME_RECOVERY_CONSUMER_QUALIFIED"
        if all(c["passed"] for c in checks)
        else "NATIVE_RECOVERY_NOT_QUALIFIED",
        "checks": checks,
        "costs": times,
        "packet": receipt,
        "volume_calls": volume.calls,
        "volume_seconds": volume.seconds,
        "adapter_cost": coupled.adapter.stats,
        "PDE_solved": False,
        "MPI": 1,
    }


def capacity(folder):
    from src.solvers.target_port_preparation import capacity_plan, target_config

    cfg, _ = target_config()
    nboundary, nvolume, cells = 378432, 345771066, 530856
    inventory = capacity_plan(cfg, 32060, int_type_bits=64)
    axes = inventory["axes_nm"]
    from collections import Counter
    from itertools import product

    categories = []
    for axis in ("x", "y", "z"):
        a = np.asarray(axes[axis], dtype=np.float64)
        c = (a[:-1] + a[1:]) / 2
        lo, hi = (
            getattr(cfg, "grating_" + axis + "_min"),
            getattr(cfg, "grating_" + axis + "_max"),
        )
        categories.append(
            Counter(
                (
                    float(w).hex(),
                    bool(lo <= midpoint <= hi),
                    bool(midpoint < cfg.interface_z) if axis == "z" else False,
                )
                for w, midpoint in zip(np.diff(a), c, strict=True)
            )
        )
    raw_classes = Counter()
    for (x, nx), (y, ny), (z, nz) in product(
        *(category.items() for category in categories)
    ):
        tag = cfg.tags.substrate if z[2] else cfg.tags.air
        if x[1] and y[1] and z[1]:
            tag = cfg.tags.grating
        raw_classes[(int(tag), x[0], y[0], z[0])] += nx * ny * nz
    if sum(raw_classes.values()) != cells or cfg.use_pml or cfg.cell_notch is not None:
        raise ValueError("frozen target raw-axis/material inventory")
    raw_inventory = [
        {
            "material_tag": key[0],
            "raw_float64_width_hex": list(key[1:]),
            "cell_count": count,
        }
        for key, count in sorted(raw_classes.items())
    ]
    # Full native row IDs remain unconstructed. For scalar-blocked same-family
    # moments, an entity has <=60 rows and a bounded local basis transform.
    nnz_upper = nboundary * 60
    E = nnz_upper * (16 + 8) + (nboundary + 1) * 8
    per_entity = 60 * 60 * (16 + 8) + 60 * 8
    return {
        "status": "ORIGINAL_SIZE_CONDITIONAL_INTEGRATION_CONTRACT",
        "capacity": inventory,
        "trace_entity_protocol": {
            "rows": nboundary,
            "row_ids": "CONDITIONAL_NOT_NATIVE_DOLFINX_IDS",
            "max_entity_rows": 60,
            "max_master_links_per_native_entity_row": "one for qualified MPI1 Floquet witness; general MPC bound must be supplied",
            "conditional_nnz_upper": nnz_upper,
            "E_CSR_bytes_upper": E,
            "E_conjugate_CSC_copy_bytes_upper": E,
            "entity_workspace_bytes_upper": per_entity,
            "full_native_width_dense_arrays": False,
            "transpose_indptr_length": nboundary + 1,
            "scatter": "caller-owned owner-local vector, sparse add; distributed owner routing not qualified",
        },
        "volume_cache": {
            "cells": cells,
            "one_complex_vector_bytes": nvolume * 16,
            "per_cell_LU_recovery_Schur_condition_bytes": 4956275464704,
            "raw_width_material_classes": raw_inventory,
            "raw_width_material_class_count": len(raw_inventory),
            "orientation_class_count": "UNKNOWN_NATIVE_MESH_NOT_CONSTRUCTED",
            "raw_key_source": "float64 axis differences without rounding; midpoint tags from frozen rectangular model",
            "sharing_limit": "conditional width/material keys; exact native geometry/orientation/source still required",
            "per_cell_map_882_int64_bytes": cells * 882 * 8,
            "raw_orientation_exact_sharing_required": True,
        },
        "implicit_Hp_saved_dense_bytes": 32060**2 * 16,
        "time_formula": "setup+K*(volume+boundary+adapter+PC)+recovery+audit+IO",
        "unmeasured": [
            "full-volume native row IDs/MPC",
            "target class inventory and simultaneous cache",
            "distributed ownership",
            "full volume/PC action",
            "K and solver vectors",
            "full recovery/audit/IO",
            "h/p accuracy",
        ],
        "NN20": "NOT_DEMONSTRATED_NO_NEURAL_TRAINING_OR_QUALIFIED_BASELINE",
        "full_target_solve": False,
        "lifecycle": [
            {
                "stage": "entity map construction",
                "resident": "short axes + one complete entity <=60 rows + sparse rows/owner index",
                "forbidden": "boundary_rows times native_width dense temporary",
            },
            {
                "stage": "finite native setup",
                "resident": "original class tensors + shared identity + LU/recovery/Schur + tiny unfactored CSR",
                "measured_packet": str(ARTIFACT / "checkpoints"),
                "full_target_peak": "unknown",
            },
            {
                "stage": "full volume iteration (not run)",
                "resident": "owner-local volume input/output + class cache + boundary operator + solver/PC workspaces",
                "solver_K_PC": "unknown; no global LU/QR/Krylov allocated in V40",
            },
            {
                "stage": "recovery and audit",
                "resident": "nonzero-RHS particular + trace solution + field audit + IO buffers",
                "cost": "finite witness measured separately; target unmeasured",
            },
        ],
        "next_integration_required_fields": [
            "exact global native entity->owner row mapping/MPC",
            "per-class raw tensor and oriented matrix hashes",
            "owner-local forward/adjoint and nonzero f/g recovery contract",
            "system-independent original residual oracle",
            "qualified full-volume PC and iteration budget",
            "matching material/background/mode/reference/h-p identities",
        ],
    }


def execute(role, folder, state):
    plan_record()
    window.guard_worker_parent()
    return {
        "PREFLIGHT": preflight,
        "BUILD": build,
        "RECOVER": recover,
        "CHECK": check,
        "DEPLOY": deploy,
        "CAPACITY": capacity,
    }[role](folder)
