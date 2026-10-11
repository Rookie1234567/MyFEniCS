"""Compare retained complete states at a time chosen without reference scores."""

import json
import math
import shlex
from pathlib import Path

from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz


def select_common_wall(histories, indices):
    rows = {}
    for name, history in histories.items():
        records = {r["sha256"]: r for r in indices[name] if r["retained"]}
        candidates = []
        for event in history:
            if event["kind"] not in ("core", "hidden", "round"):
                continue
            sha = event.get("committed_checkpoint_sha256")
            if sha not in records:
                raise ValueError("COMMON_WALL_COMPLETE_BOUNDARY_NOT_RETAINED")
            elapsed = event["elapsed_route_seconds"]
            if not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("COMMON_WALL_NONFINITE_TIME")
            candidates.append(
                dict(
                    elapsed_route_seconds=elapsed,
                    kind=event["kind"],
                    checkpoint=records[sha],
                )
            )
        if not candidates:
            raise ValueError("COMMON_WALL_NO_COMPLETE_BOUNDARY")
        if any(
            b["elapsed_route_seconds"] < a["elapsed_route_seconds"]
            for a, b in zip(candidates, candidates[1:])
        ):
            raise ValueError("COMMON_WALL_TIME_NOT_MONOTONIC")
        rows[name] = candidates
    common = min(v[-1]["elapsed_route_seconds"] for v in rows.values())
    selected = {}
    for name, candidates in rows.items():
        choices = [r for r in candidates if r["elapsed_route_seconds"] <= common]
        if not choices:
            raise ValueError("COMMON_WALL_NO_STATE_BEFORE_SHARED_TIME")
        selected[name] = choices[-1]
    return dict(
        common_new_wall_seconds=common,
        selected=selected,
        selection_uses_reference=False,
        selection_rule="Latest retained complete boundary at or before the lesser final committed new wall",
    )


def initialize_output(artifact):
    """Establish the per-audit namespace before the first atomic record."""
    artifact = Path(artifact)
    artifact.mkdir(parents=True, exist_ok=True)
    return artifact


def prepare(artifact, source_root, manifest):
    artifact = initialize_output(artifact)
    from src.io.ftt_continuation_campaign import DESIGN, routes
    from src.io.ftt_campaign import load_files
    from src.runners.ftt_worker import load_arrays, ftt_abi
    from src.runners.ftt_bloch_worker import field_factory
    width_run = manifest["spec"].get("campaign_version") == 44
    if width_run:
        from src.io.ftt_width_campaign import DESIGN, routes
    from src.solvers.feinn_native import load_native
    from src.solvers.ftt_factored_moments import FactoredMomentMap
    from src.solvers.ftt_core_training import load_checkpoint
    from src.postprocessing.ftt_verification import validate_checkpoint_identity
    from src.solvers.ftt_conditional_core import relative_pair

    design = json.loads(DESIGN.read_text())
    if digest(DESIGN) != manifest["design_sha256"]:
        raise ValueError("COMMON_WALL_DESIGN_CHANGED")
    histories, indices = {}, {}
    for stage, _ in routes():
        folder = source_root / stage
        histories[stage] = [
            json.loads(x) for x in (folder / "history.jsonl").read_text().splitlines()
        ]
        indices[stage] = json.loads((folder / "checkpoint_index.json").read_text())
    selection = select_common_wall(histories, indices)
    files = load_files(design)
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    atomic_json(artifact / "abi.json", ftt_abi("ml"))
    audit_saved_forks(artifact, source_root, design)
    for stage, route in routes():
        row = selection["selected"][stage]
        ck = row["checkpoint"]
        pt = source_root / stage / "checkpoints" / ck["name"]
        if pt.stat().st_size != ck["bytes"]:
            raise ValueError("COMMON_WALL_CHECKPOINT_SIZE_CHANGED")
        state = load_checkpoint(pt, ck["sha256"])
        candidate = dict(ck["metadata"], checkpoint=ck)
        if width_run:
            from src.runners.ftt_width_worker import model_factory
            model = model_factory(design, candidate)
        else:
            model = field_factory(design, candidate["model_kind"])
        validate_checkpoint_identity(state, candidate, model, False)
        if (
            candidate["route"] != route
            or candidate["parent_checkpoint_sha256"]
            != design["parent_checkpoint"]["sha256"]
        ):
            raise ValueError("COMMON_WALL_PARENT_OR_ROUTE_MISMATCH")
        model.load_state_dict(state["model"], strict=True)
        c = FactoredMomentMap(packet, point_batch=512).forward(model)
        r = action.apply(c) - action.f
        pair = {"c": relative_pair(c, state["c"]), "r": relative_pair(r, state["r"])}
        if max(v["relative"] for v in pair.values()) > 1e-10:
            raise ValueError("COMMON_WALL_SAVED_FIELD_PAIR_FAILED")
        folder = artifact / stage
        folder.mkdir(parents=True, exist_ok=True)
        field = folder / "field.npz"
        atomic_npz(field, c=c, r=r)
        request = dict(
            round=candidate["position"]["complete_rounds"],
            field_path=str(field.relative_to(ROOT)),
            field_sha256=digest(field),
            boundary_sha256=ck["sha256"],
            source_sha=manifest["source_sha"],
            design_sha256=manifest["design_sha256"],
            production_initialization_allowed=False,
        )
        atomic_json(folder / "request.json", request)
        row.update(
            route=route,
            checkpoint_path=str(pt.relative_to(ROOT)),
            saved_field_pair=pair,
            checkpoint_numerical_source=candidate["source_sha"],
            diagnostic_source=manifest["source_sha"],
            counts=candidate["counts"],
            new_counts=candidate["new_counts"],
            position=candidate["position"],
            request_path=str((folder / "request.json").relative_to(ROOT)),
        )
    atomic_json(artifact / "selection.json", selection)


def saved_width_participation(initial, final, hidden_keys):
    """Read retained tensors only; do not compute a new network gradient."""
    import torch

    if initial["parameter_order"] != final["parameter_order"]:
        raise ValueError("SAVED_WIDTH_PARAMETER_ORDER_CHANGED")
    gradients = dict(
        zip(
            (row["name"] for row in final["parameter_order"]),
            final["gradients"],
            strict=True,
        )
    )
    axes = {}
    for axis in range(3):
        prefix = f"cores.{axis}."
        keys = [key for key in hidden_keys if key.startswith(prefix)]
        old_delta2 = new_delta2 = new_gradient2 = 0.0
        old_count = new_count = retained = missing = 0
        for key in keys:
            before, after = initial["model"][key], final["model"][key]
            if before.shape != after.shape:
                raise ValueError("SAVED_WIDTH_HIDDEN_SHAPE_CHANGED")
            old = torch.zeros_like(before, dtype=torch.bool)
            if key.endswith("2.weight"):
                old[:16, :16] = True
            else:
                old[:16] = True
            delta = after - before
            old_delta2 += float((delta[old] ** 2).sum())
            new_delta2 += float((delta[~old] ** 2).sum())
            old_count += int(old.sum())
            new_count += int((~old).sum())
            gradient = gradients[key]
            if gradient is None:
                missing += 1
            else:
                if gradient.shape != after.shape:
                    raise ValueError("SAVED_WIDTH_GRADIENT_SHAPE_CHANGED")
                retained += 1
                new_gradient2 += float((gradient[~old] ** 2).sum())
        output_key = prefix + "4.weight"
        before_output = initial["model"][output_key][:, 16:]
        after_output = final["model"][output_key][:, 16:]
        axes["xyz"[axis]] = dict(
            old_hidden_real_parameters=old_count,
            new_hidden_real_parameters=new_count,
            new_output_real_parameters=after_output.numel(),
            initial_new_output_weight_norm=float(torch.linalg.vector_norm(before_output)),
            final_new_output_weight_norm=float(torch.linalg.vector_norm(after_output)),
            new_output_weight_change_norm=float(
                torch.linalg.vector_norm(after_output - before_output)
            ),
            old_hidden_change_norm=math.sqrt(old_delta2),
            new_hidden_change_norm=math.sqrt(new_delta2),
            retained_new_hidden_gradient_norm=(
                math.sqrt(new_gradient2) if retained else None
            ),
            gradient_tensors_retained=retained,
            gradient_tensors_not_retained=missing,
            gradient_status=(
                "NOT_RETAINED" if not retained else
                "PARTIAL_NOT_RETAINED" if missing else "RETAINED_CHECKPOINT_GRADIENT_BUFFERS"
            ),
        )
    return dict(
        axes=axes,
        old_hidden_real_parameters=sum(row["old_hidden_real_parameters"] for row in axes.values()),
        new_hidden_real_parameters=sum(row["new_hidden_real_parameters"] for row in axes.values()),
        gradient_scope="Stored gradient buffers may originate from core-adjoint VJP or hidden optimization; no fresh final-state gradient computed and no hidden update inferred",
        new_network_forward_calls=0,
        new_gradient_calls=0,
    )


def audit_saved_forks(artifact, source_root, design):
    import numpy as np
    from src.io.ftt_continuation_campaign import routes
    width_run = design["campaign_version"] == 44
    if width_run:
        from src.io.ftt_width_campaign import routes
    from src.solvers.optimization_checkpoint import load_checkpoint
    from src.runners.ftt_bloch_worker import field_factory
    from src.solvers.ftt_conditional_core import hidden_parameters

    parent = load_checkpoint(
        ROOT / design["parent_checkpoint"]["path"],
        design["parent_checkpoint"]["sha256"],
    )
    model = field_factory(design, "fttnn")
    hidden_ids = {id(p) for p in hidden_parameters(model)}
    hidden_keys = [name for name, p in model.named_parameters() if id(p) in hidden_ids]
    buffer_keys = [name for name, _ in model.named_buffers()]
    initial_models = []
    records = {}
    hidden_counts = {}
    for stage, route in routes():
        folder = source_root / stage
        index = json.loads((folder / "checkpoint_index.json").read_text())
        final = json.loads((folder / "result.json").read_text())["checkpoint"]
        zero = index[0]
        s0 = load_checkpoint(folder / "checkpoints" / zero["name"], zero["sha256"])
        s1 = load_checkpoint(folder / "checkpoints" / final["name"], final["sha256"])
        initial_models.append(s0["model"])
        expected = parent["model"]
        if width_run and s0["metadata"]["hidden_width"] == 32:
            from src.solvers.ftt_width_extension import widen_field
            model.load_state_dict(parent["model"], strict=True)
            expected = widen_field(model).state_dict()
        same_model = all(v.equal(expected[k]) for k, v in s0["model"].items())
        from src.solvers.ftt_conditional_core import relative_pair
        field_pairs = {
            key: relative_pair(np.asarray(s0[key]), np.asarray(parent[key]))
            for key in ("c", "r")
        }
        bitwise_field = all(np.array_equal(s0[key], parent[key]) for key in ("c", "r"))
        same_field = (
            all(row["relative"] <= 1e-10 for row in field_pairs.values())
            if width_run else bitwise_field
        )
        same_rng = (
            s0["torch_rng"].equal(parent["torch_rng"])
            and s0["python_rng"] == parent["python_rng"]
        )
        same_rng &= all(
            np.array_equal(a, b)
            for a, b in zip(s0["numpy_rng"], parent["numpy_rng"], strict=True)
        )
        fixed_buffers = all(
            s1["model"][k].equal(parent["model"][k]) for k in buffer_keys
        )
        delta2 = sum(
            float(((s1["model"][k] - s0["model"][k]) ** 2).sum())
            for k in hidden_keys
        )
        frozen = all(s1["model"][k].equal(s0["model"][k]) for k in hidden_keys)
        if not (same_model and same_field and same_rng and fixed_buffers):
            raise ValueError("SAVED_FORK_MODEL_FIELD_RNG_OR_BUFFER_MISMATCH")
        if ("FREEZE" in route or "FROZEN" in route) and not frozen:
            raise ValueError("SAVED_FREEZE_HIDDEN_CHANGED")
        hidden_counts[route] = sum(s0["model"][key].numel() for key in hidden_keys)
        if width_run and hidden_counts[route] != s1["metadata"]["hidden_real_parameters"]:
            raise ValueError("SAVED_WIDTH_HIDDEN_INVENTORY_MISMATCH")
        record = dict(
            initial_checkpoint_sha256=zero["sha256"],
            final_checkpoint_sha256=final["sha256"],
            initial_c_r_bitwise_equal_parent=bitwise_field,
            initial_RNG_equal_parent=bool(same_rng),
            final_all_buffers_equal_parent=fixed_buffers,
            inherited_counts=s1["metadata"]["inherited_state"]["inherited_counts"],
            new_counts=s1["metadata"]["new_counts"],
        )
        if width_run:
            record.update(
                all_initial_model_buffers_equal_function_preserving_import=same_model,
                initial_architecture_equals_parent=s0["metadata"]["hidden_width"] == 16,
                initial_c_r_pair=field_pairs,
                final_hidden_bitwise_equal_initial_import=frozen,
                hidden_delta_from_initial_import_norm=float(np.sqrt(delta2)),
                hidden_real_parameter_count=hidden_counts[route],
                actual_real_parameter_count=sum(
                    s0["model"][row["name"]].numel() for row in s0["parameter_order"]
                ),
            )
            if s0["metadata"]["hidden_width"] == 32:
                record["expanded_parameter_participation"] = saved_width_participation(
                    s0, s1, hidden_keys
                )
        else:
            record.update(
                all_initial_model_buffers_equal_parent=same_model,
                final_hidden_bitwise_equal_parent=frozen,
                hidden_delta_from_parent_norm=float(np.sqrt(delta2)),
            )
        records[route] = record
    compared_models = initial_models[1:] if width_run else initial_models
    same_forks = all(v.equal(compared_models[1][k]) for k, v in compared_models[0].items())
    if not same_forks:
        raise ValueError("SAVED_INITIAL_FORKS_DIFFERENT")
    atomic_json(
        artifact / "initial_and_final_forks.json",
        dict(
            parent_sha256=design["parent_checkpoint"]["sha256"],
            actual_initial_forks_bitwise_same=same_forks,
            **(
                dict(hidden_real_parameter_counts=hidden_counts)
                if width_run else dict(hidden_real_parameter_count=912)
            ),
            records=records,
            production_initialization_allowed=False,
            new_training_calls=0,
            new_reference_solve_count=0,
        ),
    )


def compare_common_wall(manifest, artifact, marker, directory):
    from src.runners.saved_field_supervision import run_checker
    from src.io.ftt_continuation_campaign import DESIGN
    if manifest["spec"].get("campaign_version") == 44:
        from src.io.ftt_width_campaign import DESIGN

    output = artifact / "common_wall"
    selection_file = output / "selection.json"
    if not selection_file.exists():
        command = [
            "bash",
            "-lc",
            "source scripts/activate_task42extra.sh ml && exec python -m src.postprocessing.ftt_common_wall "
            + shlex.quote(str(directory.relative_to(ROOT))),
        ]
        run_checker(
            command,
            artifact / ("common_wall_prepare_" + directory.name),
            manifest["worker_stop_monotonic"],
            manifest["source_sha"],
        )
    selection = json.loads(selection_file.read_text())
    for stage, row in selection["selected"].items():
        folder = output / stage
        scalar = folder / "scalars.json"
        request = ROOT / row["request_path"]
        if not scalar.exists():
            isolated = folder / "isolated_scoring"
            command = [
                "bash",
                "-lc",
                "source scripts/activate_task42extra.sh fe && exec python -m src.postprocessing.ftt_bloch_scalars "
                + " ".join(
                    shlex.quote(str(p.relative_to(ROOT)))
                    for p in (request, isolated, scalar)
                )
                + " --design "
                + shlex.quote(str(DESIGN.relative_to(ROOT))),
            ]
            run_checker(
                command,
                artifact / (stage + "_wall_scoring_" + directory.name),
                manifest["worker_stop_monotonic"],
                manifest["source_sha"],
            )
        from src.postprocessing.ftt_bloch_scalars import read_scalars

        row["scalars"] = read_scalars(scalar, json.loads(request.read_text()))
    selection.update(
        reference_feedback="scalars_only_after_routes_frozen",
        production_initialization_allowed=False,
        same_accuracy_resource_gain_qualified=False,
        no_reference_vector_returned_to_training=True,
        new_reference_solve_count=0,
    )
    atomic_json(artifact / "common_wall_comparison.json", selection)
    marker(
        "common_wall_saved_boundary_comparison_complete",
        dict(common_new_wall_seconds=selection["common_new_wall_seconds"]),
    )
    return dict(
        path=str((artifact / "common_wall_comparison.json").relative_to(ROOT)),
        sha256=digest(artifact / "common_wall_comparison.json"),
        selection_uses_reference=False,
    )


if __name__ == "__main__":
    import sys

    directory = ROOT / Path(sys.argv[1])
    manifest = json.loads((directory / "run_manifest.json").read_text())
    artifact = ROOT / manifest["artifact"]
    prepare(
        artifact / "common_wall",
        ROOT / ("benchmarks/artifacts/task42extra/v44" if manifest["spec"].get("campaign_version") == 44 else "benchmarks/artifacts/task42extra/v43"),
        manifest,
    )
