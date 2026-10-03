"""Thin pure-array entry; existing task supervisor supplies all resource gates."""

import argparse

from src.runners.feinn_common_descent_arrays import run, check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("analyze", "check"))
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    (run if args.mode == "analyze" else check)(args.input, args.output)


if __name__ == "__main__":
    main()
