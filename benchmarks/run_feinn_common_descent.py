"""Thin pure-array entry; existing task supervisor supplies all resource gates."""

import argparse

from src.runners.feinn_common_descent_arrays import run, check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("analyze", "check"))
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--run-index")
    parser.add_argument("--expected-result-sha256")
    parser.add_argument("--native-attribution", action="store_true")
    args = parser.parse_args()
    if args.mode == "analyze":
        if args.run_index or args.expected_result_sha256 or args.native_attribution:
            parser.error("verification options are check-only")
        run(args.input, args.output)
    else:
        check(args.input, args.output, run_index_path=args.run_index,
              expected_result_sha256=args.expected_result_sha256,
              native_attribution=args.native_attribution)


if __name__ == "__main__":
    main()
