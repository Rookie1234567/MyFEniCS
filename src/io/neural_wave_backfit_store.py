"""Hash-bound append-only block replacements and atomic matched boundaries."""

import json
from pathlib import Path
from time import monotonic_ns

import numpy as np

from src.solvers.neural_wave_greedy import atomic_json, atomic_npz, sha


class BackfitStore:
    def __init__(self, directory, binding, anchor):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.binding, self.anchor = binding, anchor

    def save(self, space, blocks, event, algorithm_state, *, replacement=None):
        previous_file = self.directory / "committed.json"
        old = json.loads(previous_file.read_text()) if previous_file.exists() else None
        count = int(algorithm_state["accepted"])
        index = [dict(e) for e in (old["chunks"] if old else self.anchor["chunks"])]
        replay = list(old["qr_replay"] if old else [])
        tag = f"{algorithm_state['visits']:03d}_{count:03d}_{monotonic_ns()}"
        if replacement is not None:
            block_id, trial = replacement
            block = blocks[block_id]
            chunk = self.directory / f"replacement_{tag}_{block_id:03d}.npz"
            if chunk.exists():
                raise ValueError("IMMUTABLE_BACKFIT_REPLACEMENT_EXISTS")
            decay = ({"q_real": block["wave_q"], "decay_kappa": block["decay_kappa"]}
                     if "decay_kappa" in block else {})
            atomic_npz(
                chunk,
                u=trial.columns,
                applied=trial.applied,
                wave_q=block["wave_q"],
                amplitude_map=block["amplitude_map"],
                center=np.asarray(block["patch"].center),
                radius=np.asarray(block["patch"].radius),
                patch_level=np.asarray(block["patch"].level),
                patch_kind=np.asarray(block["patch"].kind),
                **decay,
            )
            entry = dict(
                path=str(chunk.resolve()),
                sha256=sha(chunk),
                start=block["start"],
                stop=block["stop"],
                source_sha=self.binding["source_sha"],
            )
            index[block_id] = entry
            replay.append(dict(entry, block_id=block_id))
        state = self.directory / f"state_{tag}.npz"
        # No stale optimizer history: this is matched all-amplitude/QR/wave
        # state, with an explicit exact low-rank QR reconstruction chain.
        if state.exists():
            tag += f"_boundary_{algorithm_state['boundary_count']}"
            state = self.directory / f"state_{tag}.npz"
        if state.exists():
            raise ValueError("IMMUTABLE_BACKFIT_STATE_EXISTS")
        atomic_npz(state, a=space.a, c=space.c, r=space.r, R=space.R)
        value = dict(
            schema=("neural-wave.complex-backfit-boundary.v1"
                    if self.binding.get("wave_representation") == "oscillation+decay.v1"
                    else "neural-wave.backfit-boundary.v1"),
            committed=True,
            binding=self.binding,
            anchor=self.anchor,
            chunks=index,
            state=dict(path=str(state.resolve()), sha256=sha(state)),
            qr_replay=replay,
            columns=space.m,
            iteration=algorithm_state["visits"],
            algorithm_state=algorithm_state,
            event=event,
            reference_used_for_training=False,
            features_reference_exposed=False,
            pde_only_solve=True,
            benchmark_previously_seen=True,
            reference_used_for_validation=True,
            continuation_uses_validation_scalars=True,
            production_initialization_allowed=False,
            optimizer_state="fresh bounded block optimization per visit; full amplitude/QR/queue/RNG saved",
            parameter_representation=(
                "explicit real q_real and decay_kappa arrays; legacy anchor means kappa=0"
                if self.binding.get("wave_representation") == "oscillation+decay.v1"
                else "real wave_q; no decay parameter"
            ),
        )
        with np.load(state, allow_pickle=False) as z:
            if not all(
                np.array_equal(z[k], getattr(space, k)) for k in ("a", "c", "r", "R")
            ):
                raise ValueError("BACKFIT_ARRAY_REOPEN_FAILED")

        # Compare canonical JSON values, including actual complex/NumPy events,
        # rather than invoking a second incompatible default JSON encoder.
        def convert(item):
            if isinstance(item, complex):
                return dict(real=item.real, imag=item.imag)
            if hasattr(item, "tolist"):
                return item.tolist()
            raise TypeError(type(item).__name__)

        value = json.loads(json.dumps(value, default=convert, allow_nan=False))
        if old:
            atomic_json(self.directory / "previous_committed.json", old)
        atomic_json(previous_file, value)
        if json.loads(previous_file.read_text()) != json.loads(json.dumps(value)):
            raise ValueError("BACKFIT_BOUNDARY_REOPEN_FAILED")
        return value


def check_boundary(path):
    path = Path(path)
    value = json.loads(path.read_text())
    if value["schema"] not in ("neural-wave.backfit-boundary.v1",
                               "neural-wave.complex-backfit-boundary.v1") or not value["committed"]:
        raise ValueError("BACKFIT_COMPLETE_BOUNDARY_REQUIRED")
    first = 0
    for entry in value["chunks"]:
        if entry["start"] != first or not first < entry["stop"] <= value["columns"]:
            raise ValueError("BACKFIT_BLOCK_COVERAGE_CORRUPT")
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("BACKFIT_MODEL_HASH_FAILED")
        if value["schema"] == "neural-wave.complex-backfit-boundary.v1":
            legacy = any(entry["path"] == x["path"] and entry["sha256"] == x["sha256"]
                         for x in value["anchor"]["chunks"])
            with np.load(entry["path"], allow_pickle=False) as arrays:
                q = arrays["wave_q"]
                if not legacy and not {"q_real", "decay_kappa"} <= set(arrays.files):
                    raise ValueError("COMPLEX_REPLACEMENT_DECAY_NOT_SAVED")
                if "decay_kappa" in arrays.files:
                    k = arrays["decay_kappa"]
                    if (q.shape != k.shape or np.iscomplexobj(q) or np.iscomplexobj(k)
                            or not np.array_equal(q, arrays["q_real"])
                            or q.dtype != np.float64 or k.dtype != np.float64
                            or not np.isfinite(k).all() or not np.isfinite(q).all()):
                        raise ValueError("COMPLEX_REPLACEMENT_PARAMETER_LAYOUT_CORRUPT")
        first = entry["stop"]
    if (
        first != value["columns"]
        or sha(value["state"]["path"]) != value["state"]["sha256"]
    ):
        raise ValueError("BACKFIT_MATCHED_STATE_HASH_FAILED")
    for entry in value["qr_replay"]:
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("BACKFIT_QR_REPLAY_HASH_FAILED")
    return value


def accept_and_save(space, blocks, block_id, complement, trial, store, event, state,
                    *, refresh_costs=None):
    from src.solvers.neural_wave_backfit import commit_replacement

    block = blocks[block_id]
    first, last = block["start"], block["stop"]
    old = (
        space.U[:, first:last].copy(),
        space.Q,
        space.R,
        space.a,
        space.c,
        space.r,
        block["wave_q"].copy(),
        block.get("decay_kappa", None),
    )
    try:
        pair = commit_replacement(space, block, complement, trial)
        if refresh_costs is not None:
            refresh_costs()
        boundary = store.save(
            space, blocks, event, state, replacement=(block_id, trial)
        )
        return pair, boundary
    except BaseException:
        u, space.Q, space.R, space.a, space.c, space.r, block["wave_q"], decay = old
        space.U[:, first:last] = u
        if decay is not None:
            block["decay_kappa"] = decay
        raise
