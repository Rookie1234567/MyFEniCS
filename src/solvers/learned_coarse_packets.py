"""Task042 deterministic whole-trajectory split and streamed RHS inventory."""

import numpy as np

from src.solvers.coarse_inverse_protocol import CoarseRHS
from src.solvers.learned_coarse_inverse import manufacture


def from_reduced(action, residual):
    return CoarseRHS(
        action.inject_trace_port(residual), residual[action.condensed.active_rows :]
    )


def synthetic_packets(action, native, *, seed, count, offset=0):
    rng = np.random.default_rng(seed)
    slaves = np.asarray(
        [
            row
            for row in action.condensed.owned_trace_original_dofs
            if int(row) not in action.condensed.trace_constraints.original_to_active
        ],
        dtype=np.int64,
    )
    interiors = np.concatenate([cell.original_interiors for cell in action._cells])
    n, m = action.condensed.full_rows, action.condensed.appended_rows
    for index in range(count):
        if index % 2:
            x = rng.standard_normal(action.reduced_size) + 1j * rng.standard_normal(
                action.reduced_size
            )
            x = np.asarray(x / np.linalg.norm(x), dtype=np.complex128)
            gi = np.zeros(n, dtype=np.complex128)
            gi[interiors] = (
                (
                    rng.standard_normal(len(interiors))
                    + 1j * rng.standard_normal(len(interiors))
                )
                / np.sqrt(len(interiors))
                * 0.01
            )
            field = action.recover_storage(x, full_rhs=gi)
            g, p = manufacture(action, native, field, x[action.condensed.active_rows :])
            kind = "manufactured_original_A4"
        else:
            g = np.asarray(
                rng.standard_normal(n) + 1j * rng.standard_normal(n),
                dtype=np.complex128,
            )
            g[slaves] = 0.0
            g /= np.linalg.norm(g)
            p = np.asarray(
                rng.standard_normal(m) + 1j * rng.standard_normal(m),
                dtype=np.complex128,
            )
            p /= np.linalg.norm(p)
            kind = "seeded_full_internal_port"
        phase = (1.0, 1j, -1.0, -1j)[index % 4]
        amplitude = (1.0e-3, 1.0, 1.0e3)[index % 3]
        yield (
            {
                "problem_id": f"seed{seed}_{index + offset:04d}",
                "whole_problem": f"seed{seed}_{index + offset:04d}",
                "kind": kind,
                "seed": seed,
                "phase_real": float(complex(phase).real),
                "phase_imag": float(complex(phase).imag),
                "amplitude": amplitude,
            },
            CoarseRHS(amplitude * phase * g, amplitude * phase * p),
        )


def frozen_split_packets(action, native, *, split, f1_artifacts):
    from pathlib import Path

    f1_artifacts = Path(f1_artifacts)
    if split == "train":
        count, seed, trajectory_ids = 256, 420200, (1, 2, 3)
    elif split == "validation":
        count, seed, trajectory_ids = 64, 420300, ()
    elif split == "heldout":
        count, seed, trajectory_ids = 64, 420400, (0,)
    else:
        raise ValueError("unknown split")
    captured = 0
    if split == "heldout":
        with np.load(f1_artifacts / "rhs_000.npz", allow_pickle=False) as packet:
            physical = CoarseRHS(packet["rhs_fe"], packet["rhs_port"])
        yield (
            {
                "problem_id": "physical_PH_b6",
                "kind": "actual_fine_physical_coarse_call",
                "whole_problem": "physical_F1_trajectory",
            },
            physical,
        )
        captured += 1
        yield (
            {"problem_id": "zero", "kind": "exact_zero", "whole_problem": "zero"},
            CoarseRHS(
                np.zeros(action.condensed.full_rows, dtype=np.complex128),
                np.zeros(action.condensed.appended_rows, dtype=np.complex128),
            ),
        )
        captured += 1
    for index in trajectory_ids:
        with np.load(
            f1_artifacts / f"trajectory_{index:03d}.npz", allow_pickle=False
        ) as packet:
            for key in sorted(packet.files):
                yield (
                    {
                        "problem_id": f"F1_rhs{index}_{key}",
                        "kind": "actual_inner_Krylov_residual",
                        "whole_problem": "physical_F1_trajectory"
                        if index == 0
                        else "seed420110_F1_synthetic_family",
                        "seed": None if index == 0 else 420110,
                    },
                    from_reduced(action, packet[key]),
                )
                captured += 1
    if split == "heldout":
        # All scale/phase relatives stay in this single held-out problem.
        for label, multiplier in (
            ("phase_i", 1j),
            ("amp_1e-3", 1.0e-3),
            ("amp_1e3", 1.0e3),
        ):
            yield (
                {
                    "problem_id": "physical_" + label,
                    "kind": label,
                    "whole_problem": "physical_F1_trajectory",
                },
                CoarseRHS(multiplier * physical.fe, multiplier * physical.port),
            )
            captured += 1
        generated = synthetic_packets(action, native, seed=seed, count=count)
        _, base = next(generated)
        interiors = np.concatenate([cell.original_interiors for cell in action._cells])
        gi = np.zeros_like(base.fe)
        gi[interiors] = base.fe[interiors]
        for label, g, p in (
            ("unseen_internal_only", gi, np.zeros_like(base.port)),
            ("unseen_port_only", np.zeros_like(base.fe), base.port),
            ("unseen_mixed", base.fe, base.port),
            ("unseen_mixed_phase_i", 1j * base.fe, 1j * base.port),
            ("unseen_mixed_amp_1e-3", 1.0e-3 * base.fe, 1.0e-3 * base.port),
            ("unseen_mixed_amp_1e3", 1.0e3 * base.fe, 1.0e3 * base.port),
        ):
            yield (
                {
                    "problem_id": label,
                    "kind": label,
                    "seed": seed,
                    "whole_problem": "heldout_seed420400_first_full_rhs_family",
                },
                CoarseRHS(g, p),
            )
            captured += 1
        for number in range(count - captured):
            label, rhs = next(generated)
            label["problem_id"] = f"seed{seed}_remaining_{number:04d}"
            yield label, rhs
        return
    yield from synthetic_packets(
        action, native, seed=seed, count=count - captured, offset=captured
    )
