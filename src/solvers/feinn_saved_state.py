"""ML-only read of hash-bound saved states; no optimizer or numerical solve."""

from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.feinn_workflow import sha
from src.solvers.neural_fe_action_packet import array_hash


def checked_entry(entry):
    path = Path(entry["path"])
    root = Path(__file__).resolve().parents[2] / "benchmarks/artifacts/task42extra"
    if not path.resolve().is_relative_to(root) or sha(path) != entry["sha256"]:
        raise ValueError("SAVED_STATE_IDENTITY_FAILED")
    return path


def checked_c(entry, key="c"):
    with np.load(checked_entry(entry), allow_pickle=False) as data:
        c = np.array(data[key])
    if c.shape != (31968,) or c.dtype != np.complex128 or not np.isfinite(c).all():
        raise ValueError("COMPLETE_MASTER_VECTOR_IDENTITY_FAILED")
    return c


def model_state(design, entry):
    """Restore immutable model only; retain but never load optimizer into a solver."""
    from src.solvers.optimization_checkpoint import load_checkpoint, parameter_order
    from src.solvers.feinn_phase import make_model
    from src.solvers.feinn_validation import parameters

    saved = load_checkpoint(checked_entry(entry), entry["sha256"])
    model = make_model(design, bool(entry.get("phase", True)))
    if saved["parameter_order"] != parameter_order(model):
        raise ValueError("FROZEN_PARAMETER_ORDER_CHANGED")
    model.load_state_dict(saved["model"], strict=True)
    meta = saved["metadata"]
    theta = parameters(model)
    if meta.get("parameter_sha256") and array_hash(theta) != meta["parameter_sha256"]:
        raise ValueError("FROZEN_PARAMETER_HASH_CHANGED")
    if (
        "complete_c" in saved
        and array_hash(saved["complete_c"]) != meta["complete_c_sha256"]
    ):
        raise ValueError("FROZEN_COMPLETE_C_HASH_CHANGED")
    if meta.get("accepted_outer") != entry.get(
        "accepted_outer", meta.get("accepted_outer")
    ):
        raise ValueError("FROZEN_COMMITTED_COUNTER_CHANGED")
    if meta.get("reference_used_for_training", False) != entry["reference_exposed"]:
        raise ValueError("FROZEN_LABEL_BOUNDARY_CHANGED")
    return model, saved


def freeze(design, pre, artifact, marker, manifest):
    import torch
    from src.solvers.feinn_phase_training import configure
    from src.solvers.feinn_validation import parameters
    from src.solvers.optimization_checkpoint import atomic_write

    configure()
    arrays, rows = {}, {}
    cutoff = (
        manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - 150
    )
    for name, entry in (pre["states"] | pre["decline_steps"]).items():
        if perf_counter() >= cutoff:
            raise RuntimeError("FREEZE_SAVE_RESERVE")
        if entry.get("status") == "NOT_RETAINED":
            rows[name] = entry.copy()
            continue
        c = checked_c(entry["checkpoint"]) if "checkpoint" in entry else None
        row = dict(
            source_sha=entry["source_sha"],
            reference_exposed=entry["reference_exposed"],
            selection=entry["selection"],
            files={
                k: v for k, v in entry.items() if k in ("checkpoint", "durable_final")
            },
            retained_residual="NOT_RETAINED",
            optimizer_state="NOT_RETAINED",
            buffers="NOT_RETAINED",
            RNG="NOT_RETAINED",
            parameters="NOT_RETAINED",
        )
        if "durable_final" in entry:
            model, saved = model_state(
                design,
                {
                    **entry["durable_final"],
                    **{k: entry[k] for k in ("phase", "reference_exposed")},
                    **(
                        {"accepted_outer": entry["accepted_outer"]}
                        if "accepted_outer" in entry
                        else {}
                    ),
                },
            )
            stored = saved.get("complete_c")
            if "checkpoint" in entry:
                with np.load(
                    checked_entry(entry["checkpoint"]), allow_pickle=False
                ) as raw:
                    if "parameters" in raw and not np.array_equal(
                        raw["parameters"], parameters(model)
                    ):
                        raise ValueError("SAVED_NPZ_PT_PARAMETER_DISAGREEMENT")
                    for key, buffer in model.named_buffers():
                        if key in raw and not np.array_equal(raw[key], buffer.numpy()):
                            raise ValueError("SAVED_NPZ_PT_BUFFER_DISAGREEMENT")
            if c is not None and stored is not None and not np.array_equal(c, stored):
                raise ValueError("SAVED_NPZ_PT_C_DISAGREEMENT")
            c = stored.copy() if c is None and stored is not None else c
            row.update(
                parameters_sha256=array_hash(parameters(model)),
                parameters="RETAINED",
                parameter_order=saved["parameter_order"],
                buffers={
                    k: array_hash(b.detach().numpy()) for k, b in model.named_buffers()
                },
                optimizer_state="RETAINED"
                if "optimizer" in saved
                else "NOT_RETAINED_PARAMETER_ONLY",
                optimizer_class=saved.get("optimizer_class", "NOT_RETAINED"),
                optimizer_keys=list(saved.get("optimizer", {})),
                RNG={
                    k: "RETAINED" if k in saved else "NOT_RETAINED"
                    for k in ("torch_rng", "numpy_rng", "python_rng")
                },
                original_metadata={
                    k: saved["metadata"].get(k, "NOT_RETAINED")
                    for k in (
                        "stage",
                        "state_kind",
                        "accepted_outer",
                        "mu",
                        "h0",
                        "d_G",
                        "d_ref",
                        "native_sha256",
                        "Gram_sha256",
                        "moments_sha256",
                        "complete_c_sha256",
                        "parameter_sha256",
                        "buffers_sha256",
                        "reference_used_for_training",
                        "features_reference_exposed",
                        "pde_only_solve",
                    )
                },
            )
            if "torch_rng" in saved:
                row["torch_RNG_sha256"] = array_hash(saved["torch_rng"].numpy())
        if c is None:
            row["status"] = "NOT_RETAINED"
        else:
            if (
                c.shape != (31968,)
                or c.dtype != np.complex128
                or not np.isfinite(c).all()
            ):
                raise ValueError("FROZEN_MASTER_VECTOR_INVALID")
            arrays[name] = c
            row.update(
                status="RETAINED", c_sha256=array_hash(c), independent_complex_FE=31968
            )
        rows[name] = row
        marker("frozen_state", dict(state=name, status=row["status"]))
    if (
        "Mfinal" in arrays
        and "M95" in arrays
        and not np.array_equal(arrays["Mfinal"], arrays["M95"])
    ):
        raise ValueError("FINAL_AND_LAST_ACCEPTED_BOUNDARY_DISAGREE")
    path = Path(artifact) / "frozen_saved_fields.npz"
    atomic_write(path, lambda stream: np.savez(stream, **arrays))
    return dict(
        status="SAVED_STATE_FREEZE_COMPLETE",
        states=rows,
        default_field_count=len(pre["states"]),
        extra_decline_field_reads=len(pre["decline_steps"]),
        source_sha=manifest["source_sha"],
        no_training=True,
        optimizer_steps=0,
        Gram_factor_created=False,
        Gsolve_count=0,
        A_count=0,
        AH_count=0,
        ML_ABI=dict(
            torch=str(torch.__version__),
            dtype="float64",
            CPU_only=True,
            threads=torch.get_num_threads(),
            interop_threads=torch.get_num_interop_threads(),
        ),
        reference_used_for_diagnostic=True,
        reference_used_for_training=False,
        pde_only_solve=False,
        production_initialization_allowed=False,
        official_candidate_results=False,
    ), dict(fields=path)
