"""Fail-closed Task003 command line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import verify_case119_dataset
from .m0 import run_m0
from .training import run_training_stage


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task003-surrogate")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-dataset")
    sub.add_parser("smoke")
    sub.add_parser("training-cv")
    predict = sub.add_parser("predict")
    predict.add_argument("--model-package", required=True)
    predict.add_argument("--height-nm", type=float, required=True)
    predict.add_argument("--width-nm", type=float, required=True)
    predict.add_argument("--grazing-deg", type=float, required=True)
    predict.add_argument("--azimuth-deg", type=float, required=True)
    predict.add_argument("--polarization", default="S")
    predict.add_argument("--wavelength-nm", type=float, default=13.5)
    predict.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "verify-dataset":
        print(json.dumps(verify_case119_dataset().as_dict(), indent=2))
        return 0
    if args.command == "smoke":
        print(json.dumps(run_m0(), indent=2))
        return 0
    if args.command == "training-cv":
        print(json.dumps(run_training_stage(), indent=2))
        return 0
    if args.command == "predict":
        if args.polarization.upper() != "S":
            raise SystemExit("Task003 supports S incident polarization only")
        if args.wavelength_nm != 13.5:
            raise SystemExit("Task003 supports wavelength=13.5 nm only")
        package = Path(args.model_package)
        manifest = package / "MODEL_MANIFEST.json" if package.is_dir() else package
        if not manifest.exists():
            raise SystemExit("model package is missing or not yet qualified")
        identity = json.loads(manifest.read_text())
        if identity.get("qualification_status") != "qualified":
            raise SystemExit("model package is not qualified; frozen validation remains sealed")
        raise SystemExit("qualified package adapter is not present in this controlled-stop run")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

