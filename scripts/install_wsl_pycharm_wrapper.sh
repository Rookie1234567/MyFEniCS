#!/usr/bin/env bash
set -euo pipefail

source_path="/mnt/c/Users/Administrator/Desktop/MyProject/scripts/wsl_python_complex.sh"
target_dir="${HOME}/.local/bin"
target_path="${target_dir}/myfenics-python-complex"
mkdir -p "$target_dir"
install -m 0755 "$source_path" "$target_path"
echo "$target_path"
