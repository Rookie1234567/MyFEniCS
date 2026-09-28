"""One explicit Task042 stage per dat; numerical kernels live in src.solvers."""

import ctypes
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.io.task042_profile import TASK042_PROFILES
from src.runners.physical_retained_condensed_v20 import RetainedCondensedRuntime
from src.runners.task042_shared import ARTIFACTS, write_json
from src.solvers.coarse_inverse_protocol import (
    CoarseReturnRejected,
    CoarseRHS,
    StrictCoarseReturn,
)
from src.solvers.learned_coarse_inverse import (
    BoundedBlockPC,
    IterativeCoarseBackend,
    OriginalEquationAudit,
    cell_declarations,
    manufacture,
    native_numpy_apply,
)
from src.solvers.p6_cell_condensed_action import (
    build_p6_cell_condensed_action_from_carrier,
)


def digest(array):
    a = np.ascontiguousarray(array)
    return hashlib.sha256(
        str((a.dtype.str, a.shape)).encode() + a.tobytes()
    ).hexdigest()


def relative(error, target):
    return float(
        np.linalg.norm(error) / max(np.linalg.norm(target), np.finfo(float).tiny)
    )


def scalar_audit(d):
    return {k: v for k, v in d.items() if isinstance(v, (str, bool, int, float))}


def mpc_identity(mpc):
    coeff, offsets = mpc.coefficients()
    return {
        "slaves_sha256": digest(mpc.slaves),
        "masters_sha256": digest(mpc.masters.array),
        "master_offsets_sha256": digest(mpc.masters.offsets),
        "coefficients_sha256": digest(coeff),
        "coefficient_offsets_sha256": digest(offsets),
        "slaves": len(mpc.slaves),
    }


def thread_qualification():
    pools = []
    for path in sorted(
        {
            line.split()[-1]
            for line in Path("/proc/self/maps").read_text().splitlines()
            if "openblas" in line and line.split()[-1].startswith("/")
        }
    ):
        lib = ctypes.CDLL(path)
        for name in ("openblas_get_num_threads", "openblas_get_num_threads64_"):
            if hasattr(lib, name):
                fn = getattr(lib, name)
                fn.restype = ctypes.c_int
                threads = fn()
                pools.append({"path": path, "function": name, "threads": threads})
                if threads != 1:
                    raise RuntimeError("Actual OpenBLAS threads !=1")
                break
    if not pools:
        raise RuntimeError("Actual BLAS thread probe unavailable")
    return pools


def component_checks(runtime, p4_action, directory, marker):
    from src.solvers.fullspace_physical_intermediate_runtime import (
        AlgebraicOwnerTransfer,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        build_same_mesh_hcurl_owner_transfer,
    )

    native4 = native_numpy_apply(runtime.p4)
    native6 = native_numpy_apply(runtime.fine)
    owner = build_same_mesh_hcurl_owner_transfer(
        runtime.levels["spaces"][6],
        runtime.levels["floquets"][6],
        runtime.levels["spaces"][4],
        runtime.levels["floquets"][4],
    )
    transfer = AlgebraicOwnerTransfer(owner)
    rng = np.random.default_rng(420100)
    tests = []
    try:
        c = PETSc.Vec().createSeq(p4_action.condensed.full_rows)
        c.array[:] = rng.standard_normal(c.getSize()) + 1j * rng.standard_normal(
            c.getSize()
        )
        c.array[
            np.asarray(runtime.levels["floquets"][4].mpc.slaves, dtype=np.int64)
        ] = 0.0
        fine = transfer.apply_primal(c)
        a6 = PETSc.Vec().createSeq(fine.getSize())
        a6.array[:] = native6(fine.array)
        ph = transfer.apply_adjoint(a6)
        a4 = native4(c.array)
        rho = relative(ph.array - a4, a4)
        tests.append(
            {"check": "original_A4_equals_PH_A6_P", "relative": rho, "limit": 1.0e-10}
        )
        y = fine.duplicate()
        y.array[:] = rng.standard_normal(y.getSize()) + 1j * rng.standard_normal(
            y.getSize()
        )
        y.array[
            np.asarray(runtime.levels["floquets"][6].mpc.slaves, dtype=np.int64)
        ] = 0.0
        phy = transfer.apply_adjoint(y)
        left = fine.dot(y)
        right = c.dot(phy)
        tests.append(
            {
                "check": "primal_dual_adjoint",
                "relative": float(
                    abs(left - right) / max(abs(left), abs(right), 1.0e-300)
                ),
                "limit": 1.0e-10,
            }
        )
        for v in (c, fine, a6, ph, y, phy):
            v.destroy()
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_physical_rhs,
        )

        b6, _ = build_physical_rhs(runtime.fine)
        coarse = transfer.apply_adjoint(b6)
        physical_rhs = coarse.array.copy()
        b6.destroy()
        coarse.destroy()
    finally:
        owner.destroy()
    for name, a, native in [
        ("A4", p4_action, native4),
        ("A6", runtime.p6_action, native6),
    ]:
        x = rng.standard_normal(a.reduced_size) + 1j * rng.standard_normal(
            a.reduced_size
        )
        g_i = np.zeros(a.condensed.full_rows, dtype=np.complex128)
        interiors = np.concatenate([cell.original_interiors for cell in a._cells])
        g_i[interiors] = 0.01 * (
            rng.standard_normal(len(interiors))
            + 1j * rng.standard_normal(len(interiors))
        )
        field = a.recover_storage(x, full_rhs=g_i)
        g, p = manufacture(a, native, field, x[a.condensed.active_rows :])
        d = a.evaluate_native_residual(x, g, native, port_rhs=p)
        for key in (
            "native_residual_relative",
            "port_residual_relative",
            "internal_residual_relative",
            "native_identity_relative",
            "schur_port_identity_relative",
        ):
            tests.append(
                {"check": name + "_" + key, "relative": d[key], "limit": 1.0e-10}
            )
        tests.append(
            {
                "check": name + "_nonzero_internal_rhs",
                "count": int(np.count_nonzero(g[interiors])),
                "required": True,
            }
        )
        tests.append(
            {
                "check": name + "_nonzero_port_rhs",
                "count": int(np.count_nonzero(p)),
                "required": True,
            }
        )
        if name == "A4":
            xb = runtime.p4_system.matrix.createVecRight()
            yb = xb.duplicate()
            xb.array[:] = x
            runtime.p4_system.matrix.mult(xb, yb)
            tests.append(
                {
                    "check": "assembled_A4_Schur_equals_independent_cell_action",
                    "relative": relative(yb.array - a.apply(x), yb.array),
                    "limit": 1.0e-10,
                }
            )
            xb.destroy()
            yb.destroy()
    passed = all(
        t.get("relative", 0.0) <= t.get("limit", 1.0) and (t.get("count", 1) > 0)
        for t in tests
    )
    record = {
        "status": "PASS" if passed else "F1_INTERFACE_NOT_QUALIFIED",
        "checks": tests,
    }
    write_json(directory / "component_checks.json", record)
    marker("component_checks_complete", record)
    if not passed:
        raise RuntimeError(
            "Real A4/A6/interface Gate failed; do not generate teacher data"
        )
    return physical_rhs


def rhs_inventory(action, physical):
    rng = np.random.default_rng(420110)
    n = action.condensed.full_rows
    m = action.condensed.appended_rows
    slaves = np.asarray(
        [
            i
            for i in action.condensed.owned_trace_original_dofs
            if int(i) not in action.condensed.trace_constraints.original_to_active
        ],
        dtype=np.int64,
    )
    g = np.asarray(
        rng.standard_normal(n) + 1j * rng.standard_normal(n), dtype=np.complex128
    )
    g[slaves] = 0.0
    g /= np.linalg.norm(g)
    p = np.asarray(
        rng.standard_normal(m) + 1j * rng.standard_normal(m), dtype=np.complex128
    )
    p /= np.linalg.norm(p)
    gi = np.zeros_like(g)
    interiors = np.concatenate([cell.original_interiors for cell in action._cells])
    gi[interiors] = g[interiors]
    zf = np.zeros_like(g)
    zp = np.zeros_like(p)
    return [
        ("physical_PH_b6", CoarseRHS(physical, zp)),
        ("internal_only", CoarseRHS(gi, zp)),
        ("port_only", CoarseRHS(zf, p)),
        ("mixed_seed420110", CoarseRHS(g, p)),
        ("phase_i", CoarseRHS(1j * g, 1j * p)),
        ("amplitude_1e-3", CoarseRHS(1.0e-3 * g, 1.0e-3 * p)),
        ("amplitude_1e3", CoarseRHS(1.0e3 * g, 1.0e3 * p)),
        ("zero", CoarseRHS(zf, zp)),
    ]


def reference_solve(matrix, action, rhs, ksp):
    b = matrix.createVecRight()
    x = b.duplicate()
    residual = b.duplicate()
    correction = b.duplicate()
    try:
        b.array[:] = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
        x.set(0.0)
        ksp.solve(b, x)
        refinements = 0
        for _ in range(3):
            matrix.mult(x, residual)
            residual.array[:] = b.array - residual.array
            if relative(residual.array, b.array) <= 1.0e-13:
                break
            ksp.solve(residual, correction)
            x.axpy(1.0, correction)
            refinements += 1
        return x.array.copy(), refinements
    finally:
        for v in (b, x, residual, correction):
            v.destroy()


def run_f1(runtime, action, physical, stage, directory, artifacts, marker):
    from src.solvers.p4_cell_condensed_inverse import petsc_csr_content_identity

    matrix = runtime.p4_system.matrix
    sha = petsc_csr_content_identity(matrix)["csr_sha256"]
    native = native_numpy_apply(runtime.p4)
    rows = []
    pc = None
    ksp = None
    declarations = cell_declarations(action)
    if stage == "F1-B0":

        def block_reader(start, stop):
            ids = np.arange(start, stop, dtype=PETSc.IntType)
            return matrix.getValues(ids, ids)

        started = time.perf_counter()
        pc = BoundedBlockPC(
            matrix.getSize()[0],
            block_reader,
            cell_factor_bytes=sum(d.payload_bytes for d in declarations),
            width=512,
        )
        write_json(
            directory / "candidate_construction.json",
            {
                "global_p4_factor_created": False,
                "runtime_p4_factor_is_none": runtime.p4_factor is None,
                "matrix_owner": "borrowed runtime p4_system.matrix",
                "private_audit_csr": False,
                "patches": len(pc.factors),
                "max_patch_rows": 512,
                "patch_factor_payload_bytes": pc.factor_bytes,
                "cell_port_factor_payload_bytes": sum(
                    d.payload_bytes for d in declarations
                ),
                "setup_seconds": time.perf_counter() - started,
                "policy": "fixed disjoint consecutive blocks; no overlap, shift, scan or fallback",
            },
        )
        backend = IterativeCoarseBackend(matrix, action, pc, sha, declarations)
        audit = OriginalEquationAudit(action, native)
        slaves = tuple(int(i) for i in runtime.levels["floquets"][4].mpc.slaves)

        def failure(packet):
            index = len(rows)
            s = packet["state"]
            r = packet["rhs"]
            np.savez(
                artifacts / f"failure_{index:03d}.npz",
                rhs_fe=r.fe,
                rhs_port=r.port,
                state_fe=np.zeros_like(r.fe) if s is None else s.fe,
                state_port=np.zeros_like(r.port) if s is None else s.port,
            )

        verifier = StrictCoarseReturn(
            backend,
            witness_operator_sha256=sha,
            original_a4=audit.native,
            port_closure=audit.port,
            recovery=audit.recovery,
            slave_dofs=slaves,
            failure_sink=failure,
        )
    else:
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        from src.solvers.fullspace_p4_reference import reference_budget
        from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

        marker(
            "offline_reference_global_p4_factor_started", {"rows": matrix.getSize()[0]}
        )
        started = time.perf_counter()
        ksp = _MumpsFactor(matrix)
        ksp.set_icntl(22, 0)  # Explicitly prohibit MUMPS out-of-core storage.
        ksp.set_icntl(23, 8192)  # Offline workspace cap in MUMPS decimal MB.
        ksp.symbolic(matrix)
        raw = ksp.info((1, 7, 16, 22, 29))
        sample = process_tree_snapshot(
            int(os.environ["TASK042_WATCHDOG_PARENT_PID"]),
            "teacher_symbolic",
            include_pss=False,
        )
        sample.update(launch_cap_bytes=16 * 2**30, planning_cap_bytes=16 * 2**30)
        budget = reference_budget(sample, raw, 2**30, marker=marker)
        write_json(directory / "reference_symbolic_budget.json", budget)
        ksp.numeric(matrix)
        marker(
            "offline_reference_global_p4_factor_complete",
            {
                "setup_seconds": time.perf_counter() - started,
                "factor_backend": "MUMPS",
                "offline_only": True,
                "factor_info": ksp.info((1, 7, 16, 22, 29)),
                "icntl22": ksp.get_icntl(22),
                "icntl23": ksp.get_icntl(23),
            },
        )
    try:
        for index, (label, rhs) in enumerate(rhs_inventory(action, physical)):
            np.savez(
                artifacts / f"rhs_{index:03d}.npz",
                rhs_fe=rhs.fe,
                rhs_port=rhs.port,
            )
            started = time.perf_counter()
            success = True
            if stage == "F1-B0":
                try:
                    verifier.solve(rhs)
                except CoarseReturnRejected:
                    success = False
                d = dict(verifier.last_audit)
                d.update(
                    ksp_reason=backend.last_reason,
                    ksp_history=backend.history if d["backend_called"] else [],
                )
                if d["backend_called"]:
                    np.savez(
                        artifacts / f"trajectory_{index:03d}.npz",
                        **{
                            f"r_{iteration:03d}": r
                            for iteration, r in backend.trajectory
                        },
                    )
            else:
                x, refinements = reference_solve(matrix, action, rhs, ksp)
                native_audit = action.evaluate_native_residual(
                    x, rhs.fe, native, port_rhs=rhs.port
                )
                d = scalar_audit(native_audit)
                d["refinements"] = refinements
                success = all(
                    d[key] <= 1.0e-10
                    for key in (
                        "native_residual_relative",
                        "port_residual_relative",
                        "internal_residual_relative",
                        "native_identity_relative",
                        "schur_port_identity_relative",
                    )
                )
                d["status"] = (
                    "REFERENCE_CHECK_PASS" if success else "F1_REFERENCE_NOT_QUALIFIED"
                )
                np.savez(
                    artifacts / f"reference_{index:03d}.npz",
                    rhs_fe=rhs.fe,
                    rhs_port=rhs.port,
                    solution=x,
                )
            d.update(
                label=label, seconds=time.perf_counter() - started, success=success
            )
            rows.append(d)
            write_json(directory / "coarse_results.json", rows)
            marker("coarse_rhs_complete", d)
        return {
            "status": "F1_REFERENCE_PASS"
            if stage != "F1-B0" and all(r["success"] for r in rows)
            else "F1_B0_QUALIFIED"
            if all(r["success"] for r in rows)
            else "COARSE_INVERSE_NOT_QUALIFIED",
            "rows": rows,
            "operator_sha256": sha,
            "global_p4_factor_created": stage != "F1-B0",
        }
    finally:
        if ksp is not None:
            ksp.destroy()
            marker("offline_reference_factor_destroyed", {})
        if pc is not None:
            pc.factors.clear()


def main():
    specification = load_and_resolve(Path(sys.argv[1]))
    directory = Path(sys.argv[2])
    manifest = json.loads((directory / "run_manifest.json").read_text())
    source = manifest["source_sha"]
    stage = TASK042_PROFILES[specification.solver["preconditioner"]]
    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType is not np.complex128
        or PETSc.IntType is not np.int64
        or len(os.sched_getaffinity(0)) != 1
        or os.environ.get("TASK042_ENV_MODE") != "fe"
    ):
        raise RuntimeError("Task042 MPI1/complex128/int64/single-core/FE Gate failed")
    pools = thread_qualification()
    write_json(
        directory / "actual_threads.json",
        {
            "pools": pools,
            "affinity": sorted(os.sched_getaffinity(0)),
            "nice": os.getpriority(os.PRIO_PROCESS, 0),
        },
    )
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    runtime = None
    action = None
    artifact = ARTIFACTS / directory.name
    artifact.mkdir()

    def marker(name, facts):
        row = {
            "event": name,
            "seconds": time.monotonic(),
            "source_sha": source,
            "stage": stage,
            "facts": facts,
        }
        with (directory / "stages.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        print(name, flush=True)

    result = {
        "status": "STARTED",
        "stage": stage,
        "source_sha": source,
        "shared_workstation": True,
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "official_result": None,
        "artifact_directory": str(artifact),
        "performance_conclusion": "inconclusive under shared load",
    }
    write_json(directory / "numerical_summary.json", result)
    started = time.perf_counter()
    try:
        if stage not in ("F1-reference", "F1-B0"):
            raise RuntimeError(
                "Later stage has not passed its preceding Gate or been implemented yet"
            )
        runtime = RetainedCondensedRuntime.build(
            cfg, MPI.COMM_WORLD, retain_coarse_schur=True, marker=marker
        )
        action = build_p6_cell_condensed_action_from_carrier(
            runtime.p4_system,
            runtime.p4["dtn_action"].carrier,
            owns_condensed=False,
            borrowed_p4_witness=True,
        )
        from benchmarks.run_task038_full3d_t5 import _mesh_identity

        mesh = runtime.levels["mesh"]
        coords = mesh.geometry.x
        identity = {
            "mesh": _mesh_identity(mesh),
            "axes": [np.unique(coords[:, i]).tolist() for i in range(3)],
            "material_tags": {
                "indices_sha256": digest(runtime.levels["mesh_data"].cell_tags.indices),
                "values_sha256": digest(runtime.levels["mesh_data"].cell_tags.values),
            },
            "p6_full_rows": runtime.p6_system.full_rows,
            "p4_full_rows": runtime.p4_system.full_rows,
            "p4_reduced_rows": runtime.p4_system.matrix.getSize()[0],
            "ports": runtime.mode_count,
            "mode_sha256": runtime.mode_sha256,
            "mode_rows": runtime.fine["mode_rows"],
            "mpc": {
                str(d): mpc_identity(runtime.levels["floquets"][d].mpc) for d in (4, 6)
            },
            "quadrature": runtime.fine["volume_quadrature_metadata"],
            "physical_model_sha256": specification.physical_model_sha256,
        }
        write_json(directory / "operator_identity.json", identity)
        if (
            runtime.p6_system.full_rows > 200000
            or runtime.p4_system.full_rows + runtime.mode_count > 60000
        ):
            raise RuntimeError("Task042 size Gate exceeded")
        if identity["mesh"]["cells_global"] != 252 or identity["ports"] != 80:
            raise RuntimeError(
                "Frozen scale differs from historical seed; stop before expansion"
            )
        physical = component_checks(runtime, action, directory, marker)
        result.update(
            run_f1(runtime, action, physical, stage, directory, artifact, marker)
        )
    except BaseException as exc:
        result.update(status="FAILED", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        if action is not None:
            action.destroy()
        if runtime is not None:
            runtime.destroy()
        result["worker_seconds"] = time.perf_counter() - started
        write_json(directory / "numerical_summary.json", result)
        marker("task042_objects_released", {"status": result["status"]})
    return 0 if result["status"] != "FAILED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
