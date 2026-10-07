"""Training receives only independently frozen scalar continuation decisions."""

import json
from pathlib import Path


def continuation_gate(artifact, columns, elapsed, strategy):
    from src.solvers.neural_wave_greedy import atomic_json

    artifact = Path(artifact)
    for node, (rank, seconds) in enumerate(((512, 5400), (1024, 7200)), 1):
        path = artifact / f"validation_scalars_{node}.json"
        if path.exists():
            result = json.loads(path.read_text())
            if set(result) != {
                "schema",
                "node",
                "boundary_sha256",
                "native_relative",
                "augmented_relative",
                "scattered_E_relative",
                "scattered_curl_relative",
                "continue",
                "source_sha",
                "scoring_result_sha256",
            }:
                raise ValueError("VALIDATION_SCALAR_SCHEMA_REQUIRED")
            ineffective = (
                max(result["native_relative"], result["augmented_relative"]) > 1e-2
                and result["scattered_E_relative"] > 0.5
                and result["scattered_curl_relative"] > 0.5
            )
            if result["continue"] != (not ineffective or node == 1):
                raise ValueError("VALIDATION_DECISION_NOT_RECOMPUTABLE")
            if not result["continue"]:
                return "MULTISCALE_NO_USEFUL_PROGRESS"
            continue
        if columns >= rank or elapsed >= seconds:
            boundary = artifact / "basis/committed.json"
            if not boundary.exists():
                return "NO_COMPLETE_STATE_AT_VALIDATION_NODE"
            atomic_json(
                artifact / f"validation_requested_{node}.json",
                dict(
                    node=node, columns=columns, elapsed_seconds=elapsed, committed=True
                ),
            )
            return f"INDEPENDENT_VALIDATION_REQUESTED_{node}"
    return None
