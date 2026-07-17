from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.neural_pc.evaluate_local_pc import evaluate
from benchmarks.neural_pc.export_slab_dataset import export_dataset
from benchmarks.neural_pc.train_local_pc import train


def run_toy_smoke(args: argparse.Namespace) -> dict[str, object]:
    root = Path(args.artifact_root)
    dataset = root / "toy_dataset"
    checkpoint = root / "toy_checkpoint"
    export_result = export_dataset(
        SimpleNamespace(
            operator_dir=None,
            output=str(dataset),
            real_krylov_dir=None,
            real_krylov_limit=0,
            toy_size=args.toy_size,
            synthetic_samples=args.synthetic_samples,
            teacher_samples=args.teacher_samples,
            validation_fraction=0.2,
            seed=args.seed,
            maximum_teacher_entries=4_000_000,
        )
    )
    train_result = train(
        SimpleNamespace(
            dataset=str(dataset),
            output=str(checkpoint),
            device=args.device,
            allow_cpu_training=False,
            pod_rank=min(2 * args.toy_size, args.pod_rank),
            hidden_width=args.hidden_width,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=2.0e-3,
            residual_weight=1.0,
            delta=1.0e-12,
            beta1=0.9,
            beta2=0.999,
            report_stride=max(1, args.epochs // 10),
            seed=args.seed,
        )
    )
    evaluation = evaluate(
        SimpleNamespace(
            dataset=str(dataset),
            checkpoint=str(checkpoint),
            split="validation",
            output=str(root / "toy_evaluation.json"),
        )
    )
    result = {
        "identity": "para_task001_toy_smoke",
        "classification": (
            "local_feasibility_only"
            if evaluation["local_feasibility_gate"]
            else "numeric_failure"
        ),
        "global_solver_run": False,
        "export": export_result,
        "training": train_result,
        "evaluation": evaluation,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "toy_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PARA-Task001 neural local-PC offline runner"
    )
    parser.add_argument("--mode", choices=("toy-smoke",), default="toy-smoke")
    parser.add_argument(
        "--artifact-root", default="benchmarks/artifacts/cases/090/toy_smoke"
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--toy-size", type=int, default=24)
    parser.add_argument("--synthetic-samples", type=int, default=768)
    parser.add_argument("--teacher-samples", type=int, default=256)
    parser.add_argument("--pod-rank", type=int, default=48)
    parser.add_argument("--hidden-width", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args()
    print(json.dumps(run_toy_smoke(args), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
