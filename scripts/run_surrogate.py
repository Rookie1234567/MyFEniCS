"""Thin, non-PDE CLI for deterministic design and explicitly gated GP analysis."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.surrogate.design import extend_training, make_design  # noqa: E402
from src.surrogate.workflow import (  # noqa: E402
    evaluate_blind, fit_experiment, freeze_strategy, learning_curve, read_json, save_new,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    design = sub.add_parser("design")
    design.add_argument("--train-count", type=int, default=8)
    design.add_argument("--dev-count", type=int, default=4)
    design.add_argument("--blind-count", type=int, default=6)
    design.add_argument("--seed", type=int, default=440700)
    design.add_argument("--output", type=Path, required=True)
    extend = sub.add_parser("extend")
    extend.add_argument("--design", type=Path, required=True)
    extend.add_argument("--reason", required=True)
    extend.add_argument("--output", type=Path, required=True)
    train = sub.add_parser("train")
    for name in ("design", "qualification", "train-records", "dev-records", "output"):
        train.add_argument(f"--{name}", type=Path, required=True)
    train.add_argument("--synthetic-test-only", action="store_true")
    freeze = sub.add_parser("freeze")
    for name in ("design", "qualification", "experiment", "output"):
        freeze.add_argument(f"--{name}", type=Path, required=True)
    freeze.add_argument("--reason", required=True)
    freeze.add_argument("--blind-count", type=int)
    blind = sub.add_parser("blind")
    for name in ("design", "qualification", "experiment", "freeze", "blind-records", "output"):
        blind.add_argument(f"--{name}", type=Path, required=True)
    curve = sub.add_parser("curve")
    curve.add_argument("--experiments", type=Path, nargs="+", required=True)
    curve.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "design":
        value = make_design(args.seed, args.train_count, args.dev_count, args.blind_count)
    elif args.command == "extend":
        value = extend_training(read_json(args.design), reason=args.reason)
    elif args.command == "train":
        value = fit_experiment(read_json(args.design), read_json(args.qualification),
                               read_json(args.train_records), read_json(args.dev_records),
                               allow_synthetic=args.synthetic_test_only)
    elif args.command == "freeze":
        value = freeze_strategy(read_json(args.experiment), read_json(args.design),
                                read_json(args.qualification), reason=args.reason,
                                blind_count=args.blind_count)
    elif args.command == "blind":
        value = evaluate_blind(read_json(args.experiment), read_json(args.design),
                               read_json(args.qualification), read_json(args.freeze), args.blind_records)
    else:
        value = learning_curve([read_json(p) for p in args.experiments])
    save_new(args.output, value)


if __name__ == "__main__":
    main()
