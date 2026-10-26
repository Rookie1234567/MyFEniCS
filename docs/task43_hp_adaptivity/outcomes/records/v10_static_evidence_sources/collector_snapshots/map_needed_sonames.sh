#!/usr/bin/env bash
set +e
raw=/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v9_resume_preparation/raw
printf 'scope=static loader-cache lookup for direct NEEDED names; no library loading\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
awk -F'[][]' '/Shared library: \[/ {print $2}' "$raw/recheck_15_elf.stdout" | LC_ALL=C sort -u > "$raw/direct_needed_sonames.txt"
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  printf '\nSONAME %s\n' "$name"
  ldconfig -p 2>&1 | awk -v n="$name" '$1 == n { print }'
done < "$raw/direct_needed_sonames.txt"
