"""Run the dependency-light structured-background Maxwell symbol smoke."""

from __future__ import annotations

import argparse
import json

import numpy as np

from src.solvers.floquet_background_hcurl import (
    PeriodicBox3D,
    apply_periodic_background_inverse,
    apply_periodic_background_operator,
    estimate_periodic_fft_working_set_bytes,
    maxwell_fourier_symbol,
    maxwell_symbol_inverse,
    relative_l2_error,
)


def run_smoke(seed: int = 17) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    field = rng.standard_normal((6, 5, 4, 3)) + 1j * rng.standard_normal(
        (6, 5, 4, 3)
    )
    parameters = {
        "box": PeriodicBox3D((2.0, 2.5, 3.0)),
        "bloch": (0.13, -0.07, 0.11),
        "mu_inv": 1.0 - 0.02j,
        "epsilon": 1.6 + 0.09j,
        "k0": 0.8,
        "shift": -0.3j,
    }
    applied = apply_periodic_background_operator(field, **parameters)
    recovered = apply_periodic_background_inverse(applied, **parameters)
    round_trip_error = relative_l2_error(recovered, field)

    symbol_kwargs = {
        "mu_inv": parameters["mu_inv"],
        "epsilon": parameters["epsilon"],
        "k0": parameters["k0"],
        "shift": parameters["shift"],
    }
    wavevector = (0.4, -0.6, 0.9)
    symbol = maxwell_fourier_symbol(wavevector, **symbol_kwargs)
    inverse = maxwell_symbol_inverse(wavevector, **symbol_kwargs)
    symbol_inverse_error = float(np.linalg.norm(symbol @ inverse - np.eye(3)))

    thresholds = {
        "round_trip_error": 2.0e-12,
        "symbol_inverse_error": 1.0e-12,
    }
    passed = bool(
        round_trip_error <= thresholds["round_trip_error"]
        and symbol_inverse_error <= thresholds["symbol_inverse_error"]
    )
    return {
        "schema": "task040.parallel.background_symbol_smoke.v1",
        "status": "pass" if passed else "fail",
        "pass": passed,
        "seed": int(seed),
        "shape": [6, 5, 4, 3],
        "round_trip_error": round_trip_error,
        "symbol_inverse_error": symbol_inverse_error,
        "thresholds": thresholds,
        "working_set_payload_bytes_4_vectors": (
            estimate_periodic_fft_working_set_bytes((6, 5, 4))
        ),
        "scope": (
            "fully_periodic_constant_coefficient_numpy_reference_only;"
            "not_open_z_not_dolfinx_not_pde_qualification"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    arguments = parser.parse_args()
    result = run_smoke(arguments.seed)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
