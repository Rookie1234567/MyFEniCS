"""True MPI2/4 consumer stages for the unchanged V40 eight-cell anchor."""

from time import perf_counter

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from src.solvers.distributed_saved_recovery import (
    SavedRecoveryConsumer,
    create_distributed_patch,
    native_bridge,
)
from src.solvers.distributed_volume_scope import ROOT, reserve_mesh
from src.solvers.native_entity_study import save_rank
from src.solvers.native_recovery_packets import PacketStore, sha


def producer_store():
    """Current consumer physics/ABI/source, with explicit producer MPI1 ABI."""
    from src.solvers.bounded_port_provider import content_hash
    from src.solvers.native_boundary_adapter import boundary_identity, identity_digest
    from src.solvers.native_integration_study import selected_action
    from src.solvers.native_recovery_scope import PLAN
    from src.solvers.native_recovery_study import patch_record
    from src.solvers.target_port_preparation import geometry_contract, target_config

    p = patch_record()
    cfg, mat = target_config()
    deps = {
        "plan": sha(PLAN),
        "material": sha(ROOT / "input/materials/si_optical_constants_v1.json"),
        "numeric_sources": {
            name: sha(ROOT / name)
            for name in (
                "src/solvers/common_3d_forms.py",
                "src/solvers/hcurl_assembly_time_condensation.py",
                "src/solvers/p6_cell_condensed_action.py",
                "src/solvers/native_boundary_adapter.py",
                "src/solvers/directional_boundary.py",
            )
        },
        "ABI": producer_abi(),
    }
    expected = {
        "schema": "native-volume-boundary-consumer.v1",
        "boundary": boundary_identity(selected_action(p["description"])),
        "native": content_hash(read_arrays(p["literal"])),
        "physical": geometry_contract(cfg, mat)["physical_contract_sha256"],
        "material": deps["material"],
        "dependencies": deps,
        "basis": "N1E-hexahedron-p6-Legendre-882",
        "q_volume": 15,
        "Hp": "IMPLICIT_IDENTITY",
        "port_D": "normalized_once",
    }
    s = PacketStore(
        ROOT / "benchmarks/artifacts/task042/v40/checkpoints",
        deps,
        expected_contract=expected,
    )
    row, _ = s.read("geometry")
    if identity_digest(row["metadata"]["contract"]) != identity_digest(expected):
        raise ValueError("immutable producer versus live consumer physics/ABI/source")
    return s, p


def producer_abi(env=None):
    """Validate the live multi-rank stack without calling MPI1-only producers."""
    from src.solvers.native_entity_study import environment

    env = environment() if env is None else env
    if (
        env["scalar"] != "complex128"
        or env["IntType"] != "int64"
        or env["MPI_size"] not in (1, 2, 4)
    ):
        raise ValueError("live consumer ABI is not the qualified finite native stack")
    abi = {k: env[k] for k in ("executable", "scalar", "IntType", "module_paths")}
    abi["MPI_size"] = 1  # Explicit immutable producer rank metadata only.
    return abi


def recover(folder, ranks):
    from dolfinx import fem
    from mpi4py import MPI
    from scipy.sparse import csr_matrix

    from src.solvers.distributed_volume_study import require_live_envelope
    from src.solvers.target_port_preparation import target_config

    require_live_envelope()
    comm = MPI.COMM_WORLD
    if comm.size != ranks or ranks not in (2, 4):
        raise ValueError("actual finite recovery MPI size")
    s, patch = producer_store()
    geom, lit = s.read("geometry")
    system, numbering = s.read("system")
    _saved_meta, saved = s.read("recovery")
    classes = []
    for item in system["metadata"]["classes"]:
        if sha(s.root / (item["name"] + ".json")) != item["sha256"]:
            raise ValueError("immutable class parent hash")
        classes.append(s.read(item["name"])[1])
    if len(classes) != 4:
        raise ValueError("the exact four producer factors")
    if comm.rank == 0:
        reserve_mesh(8)
    comm.barrier()
    began = perf_counter()
    V, mpc = create_distributed_patch(patch["description"], target_config()[0], comm)
    bridge = native_bridge(V, mpc, lit)
    actor = SavedRecoveryConsumer(
        comm, lit, numbering, classes, bridge, saved["C_adapter"], saved["D_adapter"]
    )
    geometry_seconds = perf_counter() - began
    own = actor.owned_ids
    checks, arrays = (
        [],
        {
            "producer_owned_ids": own,
            "producer_row_owners": bridge["producer_owner"],
            "producer_cells": bridge["producer_cells"],
            "owned_cells": np.asarray([bridge["owned_cells"]]),
            "actual_native_ids": bridge["native_ids"],
            "actual_native_owners": bridge["native_owners"],
            "consumer_permutations": bridge["consumer_permutations"],
            "native_cell_dofs": bridge["native_dofs"],
        },
    )
    for label in ("a", "b", "zero", "scale"):
        x = saved[label + "_x"][own]
        arrays[label + "_x"] = x
        for suffix, adjoint, coupled in (
            ("volume", False, False),
            ("adjoint_volume", True, False),
            ("action", False, True),
            ("adjoint", True, True),
        ):
            result = actor.apply_original(x, adjoint=adjoint, coupled=coupled)
            arrays[label + "_" + suffix] = result
            checks.append(
                dict(
                    kind=label + "_" + suffix,
                    **metric(result, saved[label + "_" + suffix][own]),
                )
            )
    u = actor.recover(saved["z"], saved["f"])
    u2 = actor.recover(saved["z2"], saved["f"])
    ud = actor.recover(saved["z"] - saved["z2"], saved["f"])
    u0 = actor.recover(np.zeros_like(saved["z"]), saved["f"])
    rhs = actor.reduced_rhs(saved["f"], saved["g"])
    arrays.update(u=u, u2=u2, u_difference=ud, u_zero=u0, reduced_rhs=rhs)
    for name in ("u", "u2", "u_difference", "u_zero"):
        checks.append(
            dict(
                kind=name + "_immutable_reference",
                **metric(arrays[name], saved[name][own]),
            )
        )
    checks.extend(
        [
            dict(kind="homogeneous_recovery", **metric(u - u2, ud - u0)),
            dict(kind="compressed_nonzero_f_g", **metric(rhs, saved["reduced_rhs"])),
        ]
    )
    Vu = actor.apply_original(u)
    Du = comm.allreduce(actor.D @ u)
    alpha, g = saved["alpha"], saved["g"]
    rFE = saved["f"][own] - Vu - actor.C @ alpha
    rport = g + Du - alpha
    rnative = saved["f"][own] - actor.C @ g - Vu - actor.C @ Du
    arrays.update(
        Vu=Vu,
        alpha=alpha,
        extracted_channels=Du,
        rFE=rFE,
        rport=rport,
        rnative=rnative,
        native_coupled_u=Vu + actor.C @ Du,
    )
    for name in ("rFE", "rnative", "native_coupled_u"):
        checks.append(
            dict(
                kind=name + "_original_reference",
                **metric(arrays[name], saved[name][own]),
            )
        )
    checks.extend(
        [
            dict(kind="complete_12_port", **metric(rport, saved["rport"])),
            dict(
                kind="native_augmented_identity",
                **metric(rnative, rFE - actor.C @ rport),
            ),
            dict(
                kind="normalized_once_D", **metric(Du, saved["D_native"] @ saved["u"])
            ),
        ]
    )
    # True finalized native MPC is an oracle for the producer/current transfer.
    G = csr_matrix(
        (
            lit["master_dual_coefficients"].conjugate(),
            lit["master_rows"],
            lit["master_offsets"],
        ),
        shape=(7056, 7056),
    )
    expanded = G @ saved["u"]
    fun = fem.Function(mpc.function_space)
    expected = np.zeros_like(fun.x.array)
    covered = np.zeros(len(expected), np.int32)
    for j, old in enumerate(bridge["producer_cells"]):
        current = bridge["transfer"][j] @ expanded[lit["cell_dofs"][old]]
        ids = bridge["native_dofs"][j]
        expected[ids] = current
        covered[ids] += 1
    dm = mpc.function_space.dofmap.index_map
    if not np.all(covered[: dm.size_local] > 0):
        raise ValueError("current native owned coefficient coverage")
    fun.x.array[:] = expected
    fun.x.array[np.asarray(mpc.slaves, np.int32)] = 0
    fun.x.scatter_forward()
    computation = fun.x.array.copy()
    mpc.backsubstitution(fun)
    fun.x.scatter_forward()
    actual = fun.x.array.copy()
    checks.append(
        dict(
            kind="actual_native_MPC_recovery",
            **metric(actual[: dm.size_local], expected[: dm.size_local]),
        )
    )
    checks.append(
        {
            "kind": "actual_slave_zero",
            "passed": bool(np.all(computation[np.asarray(mpc.slaves, np.int32)] == 0)),
        }
    )
    arrays.update(
        native_expected=expected,
        native_expanded=actual,
        native_computation=computation,
        native_slaves=np.asarray(mpc.slaves, np.int32),
        current_owned_size=np.asarray([dm.size_local]),
    )
    local_fields = actor.expand_cells(u)
    balances = []
    for j, field in enumerate(local_fields):
        c = int(bridge["producer_cells"][j])
        a = classes[int(numbering["cell_class"][c])]
        ii, ip = numbering["cell_interior"][c], a["interior_positions"]
        response = (a["original"] @ field)[ip]
        balances.append(response)
        checks.append(
            dict(
                kind="internal_balance_cell" + str(c),
                **metric(response, saved["f"][ii]),
            )
        )
    arrays["cell_recovered_fields"] = np.asarray(local_fields)
    arrays["internal_balances"] = np.asarray(balances)
    packets = save_rank(
        folder,
        arrays,
        {
            "checks": checks,
            "new_LU": 0,
            "kernel_JIT": 0,
            "producer_MPI": 1,
            "consumer_MPI": ranks,
            "producer_contract": geom["metadata"]["contract"],
            "parent_recovery": {
                "path": str(s.root / "recovery.json"),
                "sha256": sha(s.root / "recovery.json"),
            },
            "geometry_seconds": geometry_seconds,
            "calls": actor.calls,
            "seconds": actor.seconds,
            "live_consumer_source": sha(
                ROOT / "src/solvers/distributed_saved_recovery.py"
            ),
            "production_port_fields": ["V40.C_adapter", "V40.D_adapter"],
            "independent_port_oracle_fields": ["V40.C_native", "V40.D_native"],
        },
        name="recovery",
    )
    passed = comm.allreduce(int(all(c["passed"] for c in checks))) == ranks
    return {
        "status": "FINITE_DISTRIBUTED_RECOVERY_SAVED"
        if passed
        else "RECOVERY_NOT_QUALIFIED",
        "packets": packets,
        "MPI_size": ranks,
        "passed": passed,
        "new_LU": 0,
        "PDE_solved": False,
        "immutable_parent": {
            "path": str(s.root / "recovery.json"),
            "sha256": sha(s.root / "recovery.json"),
        },
        "checks": checks,
    }
