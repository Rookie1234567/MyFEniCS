"""One reviewed right column scaling, from the assembled original Schur S.

No row weights, clipping, damping, normal matrix, factor or reference solution.
Only setup owns a small CSR; deployed actions own the original packet and D.
"""

from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.neural_fe_action_packet import (
    array_hash,
    file_hash,
    operation_relative,
)


class ScalingDefinitionError(ValueError):
    pass


def column_norm_scaling(matrix):
    """Merge contributions before stable norms of complete assembled columns."""
    columns = matrix.tocsc(copy=True)
    columns.sum_duplicates()
    columns.eliminate_zeros()
    if not np.isfinite(columns.data).all():
        raise ScalingDefinitionError("nonfinite original S coefficients")
    c = np.array(
        [
            np.hypot.reduce(
                np.abs(columns.data[columns.indptr[j] : columns.indptr[j + 1]]),
                initial=0.0,
            )
            for j in range(columns.shape[1])
        ]
    )
    if not np.isfinite(c).all() or np.any(c <= 0):
        bad = np.flatnonzero(~np.isfinite(c) | (c <= 0))
        raise ScalingDefinitionError(
            f"zero/nonfinite column norms: {bad[:16].tolist()}"
        )
    with np.errstate(over="ignore", under="ignore", divide="ignore", invalid="ignore"):
        D = 1.0 / c
        inverse = 1.0 / D
    if not np.isfinite(D).all() or np.any(D <= 0) or not np.isfinite(inverse).all():
        raise ScalingDefinitionError("D or its inverse is not representable")
    return c, D


class ColumnScaledOperator:
    """S(Dy), D^H S^H v, and exact recovery z=Dy; no matrix or inverse."""

    def __init__(self, packet, diagonal):
        self.packet = packet
        raw = np.asarray(diagonal)
        if np.iscomplexobj(raw) or raw.shape != (packet.size,):
            raise ScalingDefinitionError(
                "positive real D must cover every trace and port"
            )
        self.D = np.asarray(raw, dtype=np.float64).copy()
        if not np.isfinite(self.D).all() or np.any(self.D <= 0):
            raise ScalingDefinitionError("invalid D")
        with np.errstate(over="ignore", divide="ignore"):
            if not np.isfinite(1.0 / self.D).all():
                raise ScalingDefinitionError("D inverse not representable")

    def recover(self, y):
        z = self.D * np.asarray(y, dtype=np.complex128)
        if not np.isfinite(z).all():
            raise ScalingDefinitionError("physical z=Dy overflow/nonfinite")
        return z

    def apply(self, y):
        return self.packet.apply(self.recover(y))

    def adjoint(self, v):
        result = self.D.conj() * self.packet.apply(v, adjoint=True)
        if not np.isfinite(result).all():
            raise ScalingDefinitionError("scaled adjoint overflow/nonfinite")
        return result


def check_scaled_actions(packet, D, seed):
    operator = ColumnScaledOperator(packet, D)
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(3):
        y = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
        v = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
        applied = operator.apply(y)
        dual = operator.adjoint(v)
        lhs, rhs = np.vdot(v, applied), np.vdot(dual, y)
        dot = operation_relative(
            abs(lhs - rhs),
            np.linalg.norm(v) * np.linalg.norm(applied)
            + np.linalg.norm(dual) * np.linalg.norm(y),
        )
        z = operator.recover(y)
        expected = packet.apply(z)
        residual = packet.a["b"] - applied
        original_residual = packet.a["b"] - expected
        rows.append(
            dict(
                index=index,
                dot_relative=dot,
                recovered_z_relative=operation_relative(
                    np.linalg.norm(z - D * y), np.linalg.norm(z)
                ),
                action_relative=operation_relative(
                    np.linalg.norm(applied - expected), np.linalg.norm(expected)
                ),
                original_loss=float(
                    np.vdot(original_residual, original_residual).real
                    / (2 * packet.bnorm**2)
                ),
                scaled_loss=float(
                    np.vdot(residual, residual).real / (2 * packet.bnorm**2)
                ),
            )
        )
    passed = all(
        max(r["dot_relative"], r["recovered_z_relative"], r["action_relative"]) <= 1e-10
        and abs(r["original_loss"] - r["scaled_loss"])
        <= 1e-10 * max(abs(r["original_loss"]), 1e-12)
        for r in rows
    )
    return dict(
        status="PASS" if passed else "FAIL",
        seed=seed,
        pairs=rows,
        action_counts=dict(packet.counts),
        nonzero_complex_tests=True,
    )


def prepare_column_scaling(packet, plan, artifact, *, sample, save):
    """Operator-only exception: assemble once, compute D, release and exit."""
    from src.solvers.neural_fe_blind_reference import reference_csr

    began = perf_counter()
    artifact = Path(artifact)
    triplets = packet.nc * (packet.lt**2 + 2 * packet.lt * packet.np)
    triplets += packet.np**2 + len(packet.a["bv"]) + len(packet.a["dv"])
    upper = 4 * triplets * 32 + 512 * 2**20
    initial = sample()
    gate = dict(
        allocation_upper_bytes=upper,
        tree_rss_before_bytes=initial["rss_bytes"],
        planning_cap_bytes=12 * 2**30,
        admitted=initial["rss_bytes"] + upper < 12 * 2**30,
        includes_COO_CSR_CSC_duplicates_and_norm_workspace=True,
    )
    save("pre_assembly_capacity", gate)
    if not gate["admitted"]:
        return dict(status="SCALING_SETUP_CAPACITY_NOT_ADMITTED", capacity=gate)
    start = perf_counter()
    matrix = reference_csr(packet)
    assembly_seconds = perf_counter() - start
    matrix.sum_duplicates()
    matrix.eliminate_zeros()
    matrix.sort_indices()
    matrix_identity = dict(
        shape=list(matrix.shape),
        nnz=int(matrix.nnz),
        indptr_sha256=array_hash(matrix.indptr),
        indices_sha256=array_hash(matrix.indices),
        values_sha256=array_hash(matrix.data),
    )
    start = perf_counter()
    try:
        c, D = column_norm_scaling(matrix)
    except ScalingDefinitionError as error:
        del matrix
        return dict(
            status="SCALING_DEFINITION_BLOCKED",
            reason=str(error),
            CSR_released=True,
            symbolic_calls=0,
            numeric_calls=0,
            solve_calls=0,
        )
    norms_seconds = perf_counter() - start
    start = perf_counter()
    pairs = []
    for j in plan["columns"]:
        unit = np.zeros(packet.size, dtype=np.complex128)
        unit[j] = 1
        value = packet.apply(unit)
        actual = float(np.linalg.norm(value))
        difference = operation_relative(abs(actual - c[j]), c[j])
        pairs.append(
            dict(
                column=j,
                kind="trace" if j < packet.nt else "port",
                assembled_norm=float(c[j]),
                action_norm=actual,
                relative=difference,
            )
        )
    vectors = []
    for seed in plan["csr_vector_seeds"]:
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
        direct = matrix @ v
        actual = packet.apply(v)
        difference = operation_relative(
            np.linalg.norm(direct - actual), np.linalg.norm(direct)
        )
        vectors.append(dict(seed=seed, operation_relative=difference))
    paired = all(r["relative"] <= 1e-10 for r in pairs) and all(
        r["operation_relative"] <= 1e-10 for r in vectors
    )
    pair_seconds = perf_counter() - start
    del matrix
    if not paired:
        return dict(
            status="SCALING_MATRIX_ACTION_PAIR_FAILED",
            columns=pairs,
            vectors=vectors,
            CSR_released=True,
        )
    path = artifact / "column_scale.npz"
    start = perf_counter()
    np.savez(path, c=c, D=D)
    array_record = dict(
        path=str(path),
        sha256=file_hash(path),
        c_sha256=array_hash(c),
        D_sha256=array_hash(D),
        rows=packet.size,
        trace_rows=packet.nt,
        port_rows=packet.np,
        payload_bytes=c.nbytes + D.nbytes,
    )
    io_seconds = perf_counter() - start

    def stats(value):
        return dict(
            min=float(value.min()),
            max=float(value.max()),
            median=float(np.median(value)),
            dynamic_range=float(value.max() / value.min()),
        )

    return dict(
        status="COLUMN_SCALING_READY",
        kind="SCALING_SETUP_USES_SMALL_ASSEMBLED_S",
        definition="c_j=norm(S e_j); D_jj=1/c_j; original canonical coordinate/order",
        matrix=matrix_identity,
        capacity=gate,
        column_pairs=pairs,
        vector_pairs=vectors,
        column_statistics=dict(
            all=stats(c), trace=stats(c[: packet.nt]), port=stats(c[packet.nt :])
        ),
        diagonal_statistics=stats(D),
        scale=array_record,
        CSR_released=True,
        symbolic_calls=0,
        numeric_calls=0,
        solve_calls=0,
        dense_S=False,
        normal_matrix=False,
        reference_loaded=False,
        row_scaling=False,
        clipping=False,
        damping=False,
        assembly_dependency="original V7 local Schur/MPC/complex phase and complete port packet; unchanged reference_csr assembly function",
        assembled_CSR_saved=False,
        action_counts=dict(packet.counts),
        costs_exclusive_seconds=dict(
            assembly=assembly_seconds,
            column_norms=norms_seconds,
            pairs=pair_seconds,
            io=io_seconds,
        ),
        setup_wall_seconds=perf_counter() - began,
    )


def verify_scaled_candidate(
    design,
    packet,
    frozen,
    frozen_path,
    reference_record,
    reference_path,
    artifact,
    plan,
):
    """Post-freeze only: reuse a saved accurate p3 state, never refactor."""
    from benchmarks.neural_fe_gate_check import check_report
    from src.io.neural_fe_continuation import V7_ROOT, read_index
    from src.solvers.neural_fe_blind_reference import independent_physics

    began = perf_counter()
    states = {}
    for name, record, parent in (
        ("FE-LSQR-COLUMN-SCALED", frozen["state"], frozen_path.parent),
        ("REFERENCE", reference_record["reference_state"], V7_ROOT),
    ):
        path = Path(record["path"]).resolve()
        if not path.is_relative_to(parent) or file_hash(path) != record["sha256"]:
            raise ValueError("frozen or saved reference file identity mismatch")
        with np.load(path, allow_pickle=False) as contents:
            vector = contents["z"].copy()
        if (
            vector.shape != (packet.size,)
            or array_hash(vector) != record["z_sha256"]
            or not np.isfinite(vector).all()
        ):
            raise ValueError("frozen or saved reference array identity mismatch")
        states[name] = vector
    if (
        frozen["operator_packet"] != reference_record["operator_packet"]
        or frozen["physical"] != reference_record["physical"]
    ):
        raise ValueError(
            "candidate/reference do not share the unchanged physical operator"
        )
    physics, comparisons = independent_physics(
        design, packet, states.pop("REFERENCE"), states, artifact
    )
    report = dict(physics=physics, comparisons=comparisons)
    checker = check_report(report)
    name = "FE-LSQR-COLUMN-SCALED"
    row = physics["rows"][name]
    old, _ = read_index("frozen_lsqr")
    workload = all(
        frozen["action_counts"][k] <= old["action_counts"][k] for k in ("S", "SH")
    )
    residual_signal = (
        workload
        and row["audit"]["schur_relative"] <= plan["gates"]["research_schur"]
        and row["audit"]["native_relative"] <= plan["gates"]["research_native"]
    )
    field_signal = (
        row["scattered_FE_L2_relative"] <= plan["gates"]["research_scattered_L2"]
    )
    strict = (
        checker["routes"][name]["status"] == "SAME_DISCRETE_QUALIFIED"
        and row["scattered_FE_L2_relative"] <= plan["gates"]["strict_scattered_L2"]
    )
    return dict(
        status="SAME_DISCRETE_QUALIFIED" if strict else "NOT_QUALIFIED",
        physics=physics,
        comparisons=comparisons,
        independent_gate=checker,
        research_signal="RESEARCH_POSITIVE"
        if residual_signal and field_signal
        else "RESIDUAL_ONLY_IMPROVEMENT"
        if residual_signal
        else "NO_REVIEW_DEFINED_POSITIVE",
        strict_scattered_pass=bool(row["scattered_FE_L2_relative"] <= 1e-4),
        same_or_fewer_actions=workload,
        old_action_counts=old["action_counts"],
        new_action_counts=frozen["action_counts"],
        frozen_candidate=frozen["state"],
        candidate_source_sha=frozen["source_sha"],
        reference_state=reference_record["reference_state"],
        reference_result_path=str(reference_path),
        reference_result_sha256=file_hash(reference_path),
        symbolic_calls=0,
        numeric_calls=0,
        solve_calls=0,
        p4_enrichment="NOT_RUN_V8_CONTRACT",
        reference_feedback=False,
        checkpoint_selection=False,
        verification_seconds=perf_counter() - began,
        action_counts=dict(packet.counts),
        costs_exclusive_seconds=dict(packet.costs),
    )
