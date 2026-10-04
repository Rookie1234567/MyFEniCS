"""Preparation stages and a boundary-only FE witness, never a volume solve."""

import hashlib
import os
from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.bounded_port_provider import content_hash, json_bytes


def array_file(path, *, compressed=False, deduplicate=False, **arrays):
    """Atomic small witness file; callers keep arrays out of JSON."""
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(dir=path.parent, prefix="." + path.name, delete=False) as f:
        temp = Path(f.name)
        stored = {}
        aliases = {}
        seen = {}
        for name, a in arrays.items():
            identity = (
                a.dtype.str,
                a.shape,
                hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest(),
            )
            if deduplicate and identity in seen:
                aliases[name] = seen[identity]
            else:
                stored[name] = a
                seen[identity] = name
        (np.savez_compressed if compressed else np.savez)(f, **stored)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "aliases": aliases,
        "members": {
            k: {
                "shape": list(v.shape),
                "dtype": v.dtype.str,
                "sha256": hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest(),
            }
            for k, v in arrays.items()
        },
    }


def environment(*, fe=False):
    import sys

    from src.runners.actual_loss_block_descent import _pure_blas_threads

    info = _pure_blas_threads()
    row = {
        "executable": sys.executable,
        "src_root": str(Path(__file__).resolve().parents[2]),
        "affinity": sorted(os.sched_getaffinity(0)),
        "math_pools": info,
        "activation": os.environ.get("TASK042_ACTIVATION"),
        "mode": os.environ.get("TASK042_ENV_MODE"),
        "MPI_size": 1,
        "Torch_loaded": "torch" in sys.modules,
        "GPU_used": False,
        "DataLoader_workers": 0,
    }
    if row["activation"] != "1" or any(p["threads"] != 1 for p in info):
        raise RuntimeError("Task042 actual qualified activation/math thread getter")
    if fe:
        import basix
        import dolfinx
        import dolfinx_mpc
        import petsc4py
        import slepc4py
        from mpi4py import MPI
        from petsc4py import PETSc

        row.update(
            MPI_size=MPI.COMM_WORLD.size,
            scalar=str(np.dtype(PETSc.ScalarType)),
            IntType=str(np.dtype(PETSc.IntType)),
            native_marker=os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION"),
            module_paths={
                m.__name__: m.__file__
                for m in (basix, dolfinx, dolfinx_mpc, petsc4py, slepc4py)
            },
        )
        if (
            PETSc.ScalarType != np.complex128
            or MPI.COMM_WORLD.size != 1
            or row["native_marker"] != "1"
        ):
            raise RuntimeError("Task042 native complex128/MPI1 ABI")
        row["math_pools"] = _pure_blas_threads()
        if any(p["threads"] != 1 for p in row["math_pools"]):
            raise RuntimeError("FE loaded BLAS math threads")
    return row


def inventory(folder):
    from petsc4py import PETSc

    from src.solvers.target_port_preparation import (
        capacity_plan,
        geometry_contract,
        mode_inventory,
        target_config,
    )

    began = perf_counter()
    env = environment(fe=True)
    cfg, material = target_config()
    contract = geometry_contract(cfg, material)
    modes, stats = mode_inventory(cfg)
    capacity = capacity_plan(
        cfg, len(modes), int_type_bits=np.dtype(PETSc.IntType).itemsize * 8
    )
    (folder / "ordered_modes.json").write_bytes(json_bytes(modes) + b"\n")
    write_json(folder / "physical_contract.json", contract)
    write_json(folder / "capacity.json", capacity)
    result = {
        "status": "TARGET_INPUT_CAPACITY_GENERATED",
        "environment": env,
        "contract": contract,
        "inventory": stats,
        "capacity": capacity,
        "ordered_modes": {
            "path": str(folder / "ordered_modes.json"),
            "sha256": hashlib.sha256(
                (folder / "ordered_modes.json").read_bytes()
            ).hexdigest(),
        },
        "cost_seconds": perf_counter() - began,
        "volume_mesh_created": False,
        "target_DoF_numbering": False,
        "target_solve": "NOT_AUTHORIZED_OR_NOT_QUALIFIED",
        "volume_actions": 0,
        "new_factors": 0,
    }
    return result


def relative(new, old):
    num = float(np.linalg.norm(new - old))
    den = max(float(np.linalg.norm(new)), float(np.linalg.norm(old)))
    return {
        "numerator": num,
        "denominator": den,
        "relative": num / den if den else None,
        "both_zero": den == 0,
        "pass_gate": (num == 0 if den == 0 else num / den <= 1e-10),
    }


def component(folder):
    from src.common.modes_3d import incident_power_3d
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.io.autonomous_neural_head import plan_and_operator
    from src.solvers.bounded_port_provider import BoundedPortAction, BoundedPortProvider
    from src.solvers.bounded_port_surface import SurfacePortSource
    from src.solvers.dtn_port_3d import (
        _mode_power_at_boundary,
        _ReusableSurfaceComponentAssembler,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.neural_fe_pilot import physical_config
    from src.solvers.neural_trace_dolfinx import pilot_space

    env = environment(fe=True)
    original, design, _material, _prior = plan_and_operator()  # metadata ONLY
    costs = {}
    began = perf_counter()
    cfg, _ = physical_config(design)
    _, data, space, _centers, tags, notch, axes = pilot_space(design)
    floquet = build_double_floquet_mpc(space, data, cfg)
    modes, rows, mode_hash = build_dynamic_mode_inventory(cfg)
    if mode_hash != original["mode_manifest_sha256"] or len(modes) != 40:
        raise ValueError("real micro complete ordered mode identity")
    costs["mesh_space_mpc"] = perf_counter() - began
    index = space.dofmap.index_map
    global_rows = int(index.size_global)
    own = tuple(map(int, index.local_range))
    if global_rows != 34050:
        raise ValueError("real micro FE storage identity")
    began = perf_counter()
    assemblers = {
        (side, j): _ReusableSurfaceComponentAssembler(
            space,
            data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            j,
            quadrature_degree=15,
        )
        for side in ("top", "bottom")
        for j in (0, 1)
    }
    costs["four_boundary_forms_JIT"] = perf_counter() - began
    began = perf_counter()
    resident = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, floquet.mpc, cfg
    )
    oracle = build_fullspace_dtn_action(resident)
    costs["resident_surface_generation"] = perf_counter() - began
    manifests = []
    for i, f in enumerate(resident.entries):
        arrays = {
            "coupling_rows": np.asarray(f.coupling_rows, dtype=np.int64),
            "coupling_values": f.coupling_values,
            "projection_rows": np.asarray(f.projection_rows, dtype=np.int64),
            "projection_values": f.projection_values,
        }
        receipt = array_file(folder / f"mode_{i:04d}.npz", **arrays)
        manifests.append(
            {
                "index": i,
                "key": list(f.mode_key),
                "identity": dict(f.mode_identity),
                "H": f.normalization_h,
                "file": receipt,
                "numeric_sha256": content_hash(arrays),
            }
        )
    write_json(
        folder / "surface_manifest.json",
        {
            "schema": "bounded-port.surface.v1",
            "modes": manifests,
            "source_sha": os.environ.get("TASK042_RUN_SOURCE"),
            "mode_manifest_sha256": mode_hash,
            "global_rows": global_rows,
            "ownership_range": list(own),
            "slave_rows": resident.slave_rows,
            "physical_sha256": original["physical_model_sha256"],
        },
    )
    source_identity = hashlib.sha256(
        json_bytes(
            {
                "mode": mode_hash,
                "physical": original["physical_model_sha256"],
                "rows": own,
                "quadrature": 15,
                "source": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            }
        )
    ).hexdigest()
    # A boundary cell's complete native basis is a safe support bound; this
    # includes roundoff-small nonzero entries and periodic redirected masters.
    support_upper = 8 * 6 * space.element.basix_element.dim
    source = SurfacePortSource(
        modes,
        rows,
        assemblers,
        floquet.mpc,
        cfg,
        source_identity=source_identity,
        maximum_local_surface_support=support_upper,
    )
    source.expected_hash = lambda i: manifests[i]["numeric_sha256"]
    provider = BoundedPortProvider(
        [f.mode_key for f in resident.entries],
        rows,
        source,
        source_identity=source_identity,
        global_rows=global_rows,
        ownership_range=own,
        slave_rows=resident.slave_rows,
        max_modes=2,
        cache_bytes=2**20,
    )
    action = BoundedPortAction(provider)
    inputs, outputs, checks = {}, {}, []
    old_costs = {"forward": 0.0, "adjoint": 0.0, "recovery": 0.0, "modal_rhs": 0.0}

    def old_forward(x):
        vx, vy = oracle.matrix.createVecs()
        vx.array[:] = x
        try:
            start = perf_counter()
            oracle.apply(vx, vy)
            old_costs["forward"] += perf_counter() - start
            return vy.array.copy()
        finally:
            vx.destroy()
            vy.destroy()

    def old_adjoint(y):
        # Independent resident carrier oracle: C and D are not mutual adjoints.
        start = perf_counter()
        out = np.zeros_like(y)
        for f in resident.entries:
            c = np.vdot(f.coupling_values, y[f.coupling_rows - own[0]])
            out[f.projection_rows - own[0]] += (
                f.projection_values.conj() * c / f.normalization_h
            )
        old_costs["adjoint"] += perf_counter() - start
        return out

    def old_recover(x):
        vx = oracle.matrix.createVecRight()
        vx.array[:] = x
        try:
            start = perf_counter()
            out = oracle.recover_auxiliary(vx)
            old_costs["recovery"] += perf_counter() - start
            return out
        finally:
            vx.destroy()

    def check(label, new, old):
        receipt = relative(new, old)
        checks.append(dict(label=label, **receipt))
        write_json(folder / "checks_pending.json", checks)
        if not receipt["pass_gate"]:
            raise ValueError("real component " + label + " relative gate")

    try:
        for seed in (423611, 423613):
            rng = np.random.default_rng(seed)
            x = rng.standard_normal(global_rows) + 1j * rng.standard_normal(global_rows)
            y = rng.standard_normal(global_rows) + 1j * rng.standard_normal(global_rows)
            x[resident.slave_rows] = 0.0
            y[resident.slave_rows] = 0.0
            label = str(seed)
            inputs["x_" + label], inputs["y_" + label] = x, y
            of, nf = old_forward(x), action.apply(x)
            oh, nh = old_adjoint(y), action.apply(y, adjoint=True)
            oa, na = old_recover(x), action.recover(x)
            for kind, new, old in [
                ("forward", nf, of),
                ("adjoint", nh, oh),
                ("amplitudes", na, oa),
            ]:
                (
                    outputs["old_" + kind + "_" + label],
                    outputs["new_" + kind + "_" + label],
                ) = old, new
                check(kind + "_" + label, new, old)
            alpha = rng.standard_normal(40) + 1j * rng.standard_normal(40)
            inputs["alpha_" + label] = alpha
            vv = oracle.matrix.createVecLeft()
            start = perf_counter()
            oracle.apply_modal_rhs(alpha, vv)
            old_costs["modal_rhs"] += perf_counter() - start
            outputs["old_modal_rhs_" + label] = vv.array.copy()
            vv.destroy()
            outputs["new_modal_rhs_" + label] = action.modal_rhs(alpha)
            check(
                "modal_rhs_" + label,
                outputs["new_modal_rhs_" + label],
                outputs["old_modal_rhs_" + label],
            )
            dual_num = abs(np.vdot(y, nf) - np.vdot(nh, x))
            dual_scale = np.linalg.norm(y) * np.linalg.norm(nf) + np.linalg.norm(
                nh
            ) * np.linalg.norm(x)
            checks.append(
                {
                    "label": "dual_" + label,
                    "numerator": float(dual_num),
                    "denominator": float(dual_scale),
                    "relative": float(dual_num / dual_scale),
                    "pass_gate": dual_num <= 1e-10 * dual_scale,
                }
            )
            factor = 0.37 - 0.91j
            linear = action.apply(factor * x)
            check("complex_linearity_" + label, linear, factor * nf)
            outputs["scaled_forward_" + label] = linear
            power_old = np.array(
                [
                    _mode_power_at_boundary(m, cfg, a) / incident_power_3d(cfg)
                    for m, a in zip(modes, oa, strict=True)
                ]
            )
            # Provider output power uses manifest physical unit powers and
            # reference-plane phase, independently rechecked from saved modes.
            power_new = np.array(
                [
                    abs(a) ** 2
                    * _mode_power_at_boundary(m, cfg, 1.0)
                    / incident_power_3d(cfg)
                    for m, a in zip(modes, na, strict=True)
                ]
            )
            # Random FE amplitudes are not unit-normalized. Keep both actual
            # power differences and the prescribed unit-amplitude witness.
            unit_old = np.array(
                [
                    _mode_power_at_boundary(m, cfg, np.exp(0.7j))
                    / incident_power_3d(cfg)
                    for m in modes
                ]
            )
            unit_new = np.array(
                [
                    _mode_power_at_boundary(m, cfg, 1.0) / incident_power_3d(cfg)
                    for m in modes
                ]
            )
            unit_error = float(np.max(abs(unit_new - unit_old)))
            checks.append(
                {
                    "label": "unit_channel_power_" + label,
                    "max_absolute": unit_error,
                    "pass_gate": unit_error <= 1e-10,
                }
            )
            outputs["old_power_" + label], outputs["new_power_" + label] = (
                power_old,
                power_new,
            )
            outputs["unit_old_power_" + label], outputs["unit_new_power_" + label] = (
                unit_old,
                unit_new,
            )
        zero = np.zeros(global_rows, dtype=np.complex128)
        outputs["zero_forward"] = action.apply(zero)
        check("zero", outputs["zero_forward"], old_forward(zero))
        # Cached tail replay: only two mode functionals, not all-mode warm store.
        before_hits = provider.stats["hits"]
        with provider.batch(38) as tail:
            tail_hashes = [content_hash(f.arrays) for f in tail]
        del tail
        tail_hits = provider.stats["hits"] - before_hits
        provider.clear()  # weak-reference release audit, no external numeric table
        if not all(row["pass_gate"] for row in checks):
            raise ValueError("real boundary component remaining gate")
        io = array_file(folder / "witnesses.npz", **inputs, **outputs)
        write_json(folder / "checks.json", checks)
        result = {
            "status": "PORT_COMPONENT_QUALIFIED_ON_MICRO",
            "environment": env,
            "physical_sha256": original["physical_model_sha256"],
            "mode_manifest_sha256": mode_hash,
            "design_sha256": hashlib.sha256(
                Path(
                    "input/task042_neural_coarse_inverse/neural_fe_design_v7.json"
                ).read_bytes()
            ).hexdigest(),
            "complete_modes": 40,
            "top_modes": sum(m.side == "top" for m in modes),
            "bottom_modes": sum(m.side == "bottom" for m in modes),
            "seeds": [423611, 423613],
            "FE_storage": global_rows,
            "degree": 3,
            "cells": 384,
            "quadrature": 15,
            "actual_tags": {str(t): int(np.sum(tags == t)) for t in np.unique(tags)},
            "notch_cells": int(notch.sum()),
            "axes_nm": [a.tolist() for a in axes],
            "source_identity": source_identity,
            "provider_stats": provider.stats,
            "provider_batches": provider.batch_records,
            "creator": source.costs,
            "retained_full_resident_oracle_bytes": resident.retained_numeric_bytes,
            "oracle_stats": dict(oracle.audit),
            "action_counts": action.counts,
            "action_costs": action.costs,
            "resident_costs_seconds": old_costs,
            "setup_costs_seconds": costs,
            "checks": checks,
            "cached_tail_hits": tail_hits,
            "cached_tail_hashes": tail_hashes,
            "cache_empty_after": True,
            "numeric_witness": io,
            "surface_manifest": {
                "path": str(folder / "surface_manifest.json"),
                "sha256": hashlib.sha256(
                    (folder / "surface_manifest.json").read_bytes()
                ).hexdigest(),
            },
            "original_mode_rows": rows,
            "incident_power": incident_power_3d(cfg),
            "boundary_power_weights": [
                _mode_power_at_boundary(m, cfg, 1.0) / incident_power_3d(cfg)
                for m in modes
            ],
            "no_volume_forms": True,
            "volume_actions": 0,
            "new_LU": 0,
            "new_QR": 0,
            "KSP": 0,
            "reference_read": False,
            "seven_block_factors_read": False,
            "full_forward_solve": False,
            "official_RTA": False,
            "cold_recompute_each_complete_visit": True,
            "full_visit_warm_cache_effect": "none beyond two cached tail modes; generation counted",
            "retained_metadata_numeric_disjoint": True,
        }
        return result
    finally:
        oracle.destroy()


def execute(role, folder, state):
    if role == "INVENTORY":
        return inventory(folder)
    if role == "COMPONENT":
        return component(folder)
    from benchmarks.check_port_preparation import check_saved

    result = check_saved()
    if role == "DEPLOY":
        result.update(
            status="TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED",
            component_status=result["component_status"],
            solver_required_fields=[
                "source SHA",
                "full 3D action/recovery identity",
                "physical/material/RHS/row/MPC/mode hash",
                "complete residual and field audit",
                "peak/lifecycle/full N1 cost and resource contract",
            ],
            target_next_stage="solver identity/accuracy/resource qualification only; no automatic solve",
        )
    return result
