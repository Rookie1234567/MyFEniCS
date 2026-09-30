"""Fixed V4 hidden features, one reference-exposed linear readout diagnosis.

ML-only: the FE checker must not import this module. No optimizer is created.
"""

from copy import deepcopy
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from src.runners.feinn_workflow import ROOT, sha, replay_closure_deadline
from src.solvers.feinn_gqr import GramColumns, ReadoutStop, project, squared_norm
from src.solvers.feinn_reference_fit import load_problem, _relative
from src.solvers.feinn_validation import parameters
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    atomic_json,
    atomic_write,
    load_checkpoint,
    parameter_order,
)

ROUTE = "FEINN-FROZEN-HIDDEN-READOUT-G"
ANCHOR_SHA = "e33a2c9eafb50639a36555e159895d62617feda7e4831238a7868887700f9363"
PT_SHA = "e09b94364837bdb72714f7c229d19993836072dd035c85249bfc19376a44a790"
POLICY = dict(
    reference_used_for_training=True,
    pde_only_solve=False,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
    data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
)


def frozen_hashes(model):
    return dict(
        hidden={
            k: array_hash(v.detach().numpy())
            for k, v in model.named_parameters()
            if not k.startswith("envelopes.6.")
        },
        buffers={k: array_hash(v.detach().numpy()) for k, v in model.named_buffers()},
    )


def readout(model):
    final = model.envelopes[-1]
    weight, bias = final.weight.detach().numpy(), final.bias.detach().numpy()
    return (
        np.column_stack(
            (weight[0::2] + 1j * weight[1::2], bias[0::2] + 1j * bias[1::2])
        )
        .ravel()
        .copy()
    )


def write_readout(model, a):
    a = np.asarray(a, dtype=np.complex128).reshape(3, 65)
    if not np.isfinite(a).all():
        raise ValueError("READOUT_NONFINITE_WEIGHTS")
    with torch.no_grad():
        model.envelopes[-1].weight[0::2].copy_(torch.from_numpy(a[:, :64].real))
        model.envelopes[-1].weight[1::2].copy_(torch.from_numpy(a[:, :64].imag))
        model.envelopes[-1].bias[0::2].copy_(torch.from_numpy(a[:, 64].real))
        model.envelopes[-1].bias[1::2].copy_(torch.from_numpy(a[:, 64].imag))


def load_anchor(design, native, grad, reference, previous):
    packet, metric, mapping, model, label = load_problem(
        design, native, grad, reference
    )
    for key, digest in (("checkpoint", ANCHOR_SHA), ("durable_final", PT_SHA)):
        entry = previous["files"][key]
        if entry["sha256"] != digest or sha(entry["path"]) != digest:
            raise ValueError("ARTIFACT_BLOCKED_V4_FINAL: " + key)
    if previous["result"]["status"] != "DURABLE_BOUNDARY_REPLAY_COMPLETE":
        raise ValueError("V4_FINAL_COMMITTED_STATE_REQUIRED")
    state = load_checkpoint(previous["files"]["durable_final"]["path"], PT_SHA)
    if state["metadata"]["state_kind"] != "final_committed" or state[
        "parameter_order"
    ] != parameter_order(model):
        raise ValueError("V4_FINAL_MODEL_ORDER_MISMATCH")
    model.load_state_dict(state["model"], strict=True)
    with np.load(previous["files"]["checkpoint"]["path"], allow_pickle=False) as data:
        saved = np.array(data["c"])
        if (
            str(data["state_kind"]) != "final_committed"
            or str(data["durable_checkpoint_sha256"]) != PT_SHA
        ):
            raise ValueError("V4_NPZ_NOT_FINAL_COMMITTED")
        if not np.array_equal(
            parameters(model), data["parameters"]
        ) or not np.array_equal(saved, state["complete_c"]):
            raise ValueError("V4_DURABLE_NPZ_PAIRING_FAILED")
        for name, value in model.named_buffers():
            if not np.array_equal(value.numpy(), data[name]):
                raise ValueError("V4_BUFFER_PAIRING_FAILED")
        for key, expected in POLICY.items():
            if key != "data_role" and bool(data[key]) != expected:
                raise ValueError("V4_LABEL_POLICY_CHANGED")
    for name, value in model.named_parameters():
        value.requires_grad_(name.startswith("envelopes.6."))
    if sum(p.numel() for p in model.parameters() if p.requires_grad) != 390:
        raise ValueError("READOUT_PARAMETER_INVENTORY_FAILED")
    if (
        sha(ROOT / "input/materials/si_optical_constants_v1.json")
        != "55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2"
    ):
        raise ValueError("FROZEN_MATERIAL_HASH_CHANGED")
    label.update(
        V4_checkpoint=previous["files"]["checkpoint"],
        V4_durable_final=previous["files"]["durable_final"],
        frozen_hashes=frozen_hashes(model),
        readout_a0_sha256=array_hash(readout(model)),
    )
    return packet, metric, mapping, model, label, saved


def feature_columns(model, mapping, marker, deadline):
    """One hidden forward per <=8 cells, <=8 feature columns per moment batch.

    Reuse the qualified packet tensors and ownership, with an independent
    linear feature extraction path. The original forward/VJP are unchanged.
    No reference or PDE operator is an argument to this function.
    """
    began = perf_counter()
    Phi = np.empty((mapping.size, 195), np.complex128)
    counts = dict(hidden_cell_batches=0, moment_column_batches=0)
    with torch.no_grad():
        for start in range(0, mapping.nc, 8):
            if perf_counter() >= deadline:
                raise ReadoutStop("READOUT_SAVE_WINDOW_REACHED")
            stop = min(start + 8, mapping.nc)
            coords = mapping.coordinates[start:stop]
            h = model.envelopes[:-1](
                (coords.reshape(-1, 3) - model.center) / model.half_width
            )
            h = (
                torch.cat((h, torch.ones((len(h), 1), dtype=torch.float64)), dim=1)
                .reshape(stop - start, -1, 65)
                .to(torch.complex128)
            )
            counts["hidden_cell_batches"] += 1
            rows = mapping.packet["owner_rows"][start:stop]
            selected = rows >= 0
            transforms = mapping.transforms[
                mapping.packet["orientation_ids"][start:stop]
            ]
            for s in range(3):
                for j in range(0, 65, 8):
                    end = min(j + 8, 65)
                    # A unit component s is pulled back by row s of J.
                    pulled = torch.einsum(
                        "cqk,cb->cbqk",
                        h[:, :, j:end],
                        mapping.jacobians[start:stop, s, :],
                    )
                    moments = torch.einsum(
                        "lv,cvk->clk",
                        mapping.interpolation,
                        pulled.reshape(stop - start, -1, end - j),
                    )
                    oriented = torch.bmm(transforms, moments)
                    Phi[rows[selected], s * 65 + j : s * 65 + end] = oriented[
                        torch.as_tensor(selected)
                    ].numpy()
                    counts["moment_column_batches"] += 1
            if start % 64 == 0:
                marker(
                    "fixed_feature_columns",
                    dict(cells=stop, elapsed=perf_counter() - began),
                )
    if not np.isfinite(Phi).all():
        raise ValueError("READOUT_COLUMNS_NONFINITE")
    return Phi, dict(
        counts,
        wall_seconds=perf_counter() - began,
        Phi_payload_bytes=Phi.nbytes,
        feature_source="V4 hidden parameters and coordinate buffers only",
        reference_columns_added=0,
    )


def checks(design, native, grad, reference, previous, artifact, marker, manifest):
    began = perf_counter()
    qualification = (
        ROOT / "docs/task042extra_feinn_5nm/outcomes/records/readout_checks_v5.json"
    )
    proof = json.loads(qualification.read_text())
    if proof["small_checks_status"] != "PASS":
        raise ValueError("READOUT_SMALL_QUALIFICATION_REQUIRED")
    for entry in proof["small_checks_evidence"]:
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("READOUT_SMALL_EVIDENCE_CHANGED")
    packet, metric, mapping, model, label, saved = load_anchor(
        design, native, grad, reference, previous
    )
    deadline = replay_closure_deadline(manifest)
    if perf_counter() >= deadline:
        raise ReadoutStop("READOUT_SAVE_WINDOW_REACHED_BEFORE_NUMERICAL_WORK")
    c0 = mapping.forward(model, 8)
    loss = metric.value(c0)[0]
    audit = packet.audit(c0)
    if (
        _relative(c0, saved) > 1e-12
        or abs(np.sqrt(2 * loss) - 0.013871691297506997) > 1e-11
        or abs(audit["native_relative"] - 1.6088447201145775) > 1e-8
    ):
        raise ValueError("V4_FINAL_ANCHOR_NOT_QUALIFIED")
    a0 = readout(model)
    Phi, construction = feature_columns(model, mapping, marker, deadline)
    rows = [dict(test="original_a0", relative=_relative(Phi @ a0, c0))]
    rng = np.random.default_rng(421501)
    vectors = [
        rng.standard_normal(195) + 1j * rng.standard_normal(195) for _ in range(3)
    ]
    vectors += [1j * rng.standard_normal(195)]
    bias = np.zeros(195, complex)
    bias[[64, 129, 194]] = [0.3 + 0.7j, -0.5j, 1.2 - 0.1j]
    vectors.append(bias)
    families = np.empty(mapping.size, dtype="U8")
    for family in ("edge", "face", "interior"):
        ids = mapping.packet["owner_rows"][
            :, mapping.packet[family + "_positions"]
        ].ravel()
        families[ids[ids >= 0]] = family
    for i, a in enumerate(vectors):
        write_readout(model, a)
        actual = mapping.forward(model, 8)
        relative = _relative(Phi @ a, actual)
        row = dict(
            test="nonzero_complex"
            if i < 3
            else "pure_imaginary"
            if i == 3
            else "three_component_bias",
            index=i,
            relative=relative,
            family_relative={
                str(f): _relative((Phi @ a)[families == f], actual[families == f])
                for f in np.unique(families)
            },
        )
        if i == 0:
            row["batch_1_8_relative"] = _relative(mapping.forward(model, 1), actual)
        rows.append(row)
    write_readout(model, a0)
    if frozen_hashes(model) != label["frozen_hashes"] or not np.array_equal(
        readout(model), a0
    ):
        raise ValueError("READOUT_CHECK_MUTATED_ANCHOR")
    passed = rows[0]["relative"] <= 1e-12 and all(
        row["relative"] <= 1e-10
        and max(row.get("family_relative", {"": 0}).values()) <= 1e-10
        and row.get("batch_1_8_relative", 0) <= 1e-10
        for row in rows
    )
    if not passed:
        raise ValueError("READOUT_LINEAR_MAPPING_NOT_QUALIFIED")
    path = Path(artifact) / "qualified_readout_columns.npz"
    atomic_write(
        path,
        lambda stream: np.savez(
            stream,
            Phi=Phi,
            a0=a0,
            c0=c0,
            hidden_hashes=json.dumps(label["frozen_hashes"], sort_keys=True),
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            reference_c_sha256=label["reference_c_sha256"],
            **POLICY,
        ),
    )
    result = dict(
        status="FROZEN_READOUT_CHECKS_PASS",
        anchor_E_G=float(np.sqrt(2 * loss)),
        native_audit=audit,
        linear_pairing=rows,
        construction=construction,
        Phi_sha256=array_hash(Phi),
        labels=label,
        all_independent_FE=31968,
        columns=195,
        hidden_real_parameters_frozen=8576,
        readout_real_parameters=390,
        G_action_columns=metric.matvec_count,
        native_action_counts=packet.counts,
        no_Gram_factor=True,
        no_Gsolve=True,
        no_optimizer=True,
        wall_seconds=perf_counter() - began,
        **POLICY,
    )
    marker(
        "readout_checks_pass",
        dict(E_G=result["anchor_E_G"], pairing=rows, Phi_sha256=result["Phi_sha256"]),
    )
    return result, dict(columns=path)


def run(
    design, native, grad, reference, previous, qualified, artifact, marker, manifest
):
    began = perf_counter()
    deadline = replay_closure_deadline(manifest)
    artifact = Path(artifact)
    files = {}
    if qualified["result"]["status"] != "FROZEN_READOUT_CHECKS_PASS":
        raise ValueError("READOUT_CHECKS_REQUIRED")
    packet, metric, mapping, model, label, c0 = load_anchor(
        design, native, grad, reference, previous
    )
    if perf_counter() >= deadline:
        raise ReadoutStop("READOUT_SAVE_WINDOW_REACHED_BEFORE_NUMERICAL_WORK")
    a0 = readout(model)
    original_hashes = frozen_hashes(model)
    entry = qualified["files"]["columns"]
    if sha(entry["path"]) != entry["sha256"]:
        raise ValueError("QUALIFIED_PHI_HASH_CHANGED")
    with np.load(entry["path"], allow_pickle=False) as data:
        Phi = np.array(data["Phi"])
        if (
            not np.array_equal(data["a0"], a0)
            or not np.array_equal(data["c0"], c0)
            or array_hash(Phi) != qualified["result"]["Phi_sha256"]
            or json.loads(str(data["hidden_hashes"])) != original_hashes
        ):
            raise ValueError("QUALIFIED_PHI_ANCHOR_CHANGED")
    anchor = artifact / "readout_anchor.npz"
    atomic_write(
        anchor,
        lambda stream: np.savez(
            stream,
            parameters=parameters(model),
            c=c0,
            a0=a0,
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            reference_c_sha256=label["reference_c_sha256"],
            **POLICY,
        ),
    )
    files["anchor"] = anchor
    action = GramColumns(
        metric.G,
        limit=2500 - qualified["result"]["G_action_columns"] - metric.matvec_count,
        deadline=deadline,
    )
    try:
        arrays, stats = project(
            Phi, metric.reference - c0, metric.reference, action, marker
        )
        basis = artifact / "projection_arrays.npz"
        atomic_write(basis, lambda stream: np.savez(stream, **arrays))
        files["projection_arrays"] = basis
        a1 = a0 + arrays["delta_a"]
        write_readout(model, a1)
        c1 = mapping.forward(model, 8)
        c_columns = c0 + arrays["delta_columns"]
        c_ideal = c0 + arrays["delta_ideal"]
        denom = np.sqrt(stats["E0_squared"] * metric.denominator)
        pairings = {}
        for name, target in (("columns", c_columns), ("ideal_projection", c_ideal)):
            diff = c1 - target
            pairings[name] = dict(
                euclidean_relative=_relative(c1, target),
                G_relative=float(
                    np.sqrt(
                        squared_norm(
                            diff, action(diff, "network_reconstruction_verification")
                        )
                    )
                    / np.sqrt(metric.denominator)
                ),
            )
        error = c1 - metric.reference
        E1_squared = (
            squared_norm(error, action(error, "actual_network_error"))
            / metric.denominator
        )
        stats.update(
            actual_E1_squared=E1_squared,
            actual_E_G=float(np.sqrt(E1_squared)),
            actual_nonincrease=E1_squared <= stats["E0_squared"] + 1e-10,
            actual_pythagorean_defect=abs(
                stats["E0_squared"] - E1_squared - stats["correction_relative_energy"]
            ),
            reconstruction=pairings,
            hidden_buffers_unchanged=frozen_hashes(model) == original_hashes,
            a0_norm=float(np.linalg.norm(a0)),
            a1_norm=float(np.linalg.norm(a1)),
            a1_max=float(np.max(np.abs(a1))),
            cancellation_amplification=float(
                np.linalg.norm(Phi, axis=0)
                @ np.abs(arrays["delta_a"])
                / max(np.linalg.norm(arrays["delta_columns"]), 1e-30)
            ),
            projection_to_original_error_G_relative=max(
                v["G_relative"] for v in pairings.values()
            )
            * np.sqrt(metric.denominator)
            / denom,
        )
        stable = (
            stats["G_orthogonality_F"] <= 1e-9
            and stats["normalized_QR_G_F_relative"] <= 1e-9
            and stats["retained_optimality"] <= 1e-9
            and stats["actual_nonincrease"]
            and stats["actual_pythagorean_defect"] <= 1e-8
            and stats["hidden_buffers_unchanged"]
        )
        reconstruction_ok = all(
            x["G_relative"] <= 1e-9 and x["euclidean_relative"] <= 1e-10
            for x in pairings.values()
        )
        status = (
            "FROZEN_HIDDEN_READOUT_COMPLETE"
            if stable and reconstruction_ok
            else "READOUT_RECONSTRUCTION_UNSTABLE"
            if not reconstruction_ok
            else "NUMERICAL_SPAN_UNRESOLVED"
        )
        metadata = dict(
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            run_id=manifest["run_id"],
            state_kind="parameter_only_supervised_readout",
            optimizer_state_saved=False,
            resumable_optimizer=False,
            inherited_LBFGS_history_used=False,
            label_identity=label,
            Phi_sha256=array_hash(Phi),
            frozen_hashes=original_hashes,
            readout_sha256=array_hash(a1),
            retained_rank=stats["retained_rank"],
            **POLICY,
        )
        pt = artifact / "frozen_model_parameter_only.pt"
        atomic_write(
            pt,
            lambda stream: torch.save(
                dict(
                    model=deepcopy(model.state_dict()),
                    parameter_order=parameter_order(model),
                    metadata=metadata,
                ),
                stream,
            ),
        )
        checkpoint = artifact / "frozen_checkpoint.npz"
        buffers = {k: v.detach().numpy().copy() for k, v in model.named_buffers()}
        atomic_write(
            checkpoint,
            lambda stream: np.savez(
                stream,
                parameters=parameters(model),
                c=c1,
                a0=a0,
                a1=a1,
                **buffers,
                source_sha=manifest["source_sha"],
                input_sha256=manifest["input_sha256"],
                state_kind=metadata["state_kind"],
                model_sha256=sha(pt),
                Phi_sha256=array_hash(Phi),
                reference_c_sha256=label["reference_c_sha256"],
                **POLICY,
            ),
        )
        files.update(checkpoint=checkpoint, parameter_only_model=pt)
        result = dict(
            status=status,
            projection=stats,
            labels=label,
            qualified_columns=entry,
            Phi_sha256=array_hash(Phi),
            optimizer_steps=0,
            optimizer_state_saved=False,
            no_Gsolve=True,
            no_Gram_factor=True,
            no_Maxwell_factor=True,
            **POLICY,
        )
    except ReadoutStop as error:
        result = dict(
            status="CONTROLLED_STOP",
            reason=str(error),
            final_fit_parameters_retained=False,
            **POLICY,
        )
    result.update(
        route=ROUTE,
        G_action_columns_main=action.count + metric.matvec_count,
        G_action_columns_S0_and_main=action.count
        + metric.matvec_count
        + qualified["result"]["G_action_columns"],
        G_action_columns_by_role=action.by_role,
        G_action_seconds_nested=action.seconds,
        closure_count=0,
        native_action_counts=packet.counts,
        wall_seconds=perf_counter() - began,
        launch_origin_monotonic=manifest["supervision_budget_origin_monotonic"],
        numeric_cutoff_monotonic=deadline,
        finish_monotonic=perf_counter(),
        exit_reserve_from_launch_seconds=manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - perf_counter(),
    )
    record = artifact / "readout_projection.json"
    atomic_json(
        record,
        json.loads(
            json.dumps(
                result,
                default=lambda v: dict(real=v.real, imag=v.imag)
                if isinstance(v, complex)
                else v.tolist(),
            )
        ),
    )
    files["projection"] = record
    marker(
        "frozen_readout_final",
        dict(status=result["status"], G_columns=result["G_action_columns_S0_and_main"]),
    )
    return result, files
