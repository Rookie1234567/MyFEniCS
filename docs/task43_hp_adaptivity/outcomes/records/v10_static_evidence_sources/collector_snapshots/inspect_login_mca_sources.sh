#!/usr/bin/env bash
set +e
printf 'scope=read-only source-chain inspection; no file sourced, no activation, no native import\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
printf '\n--- /etc/profile source loop and per-user login selection ---\n'
sed -n '1,32p' /etc/profile
sed -n '1,24p' "$HOME/.profile"
sed -n '1,32p' "$HOME/.bashrc"
printf '\n--- startup source files and MCA/library override matches ---\n'
for f in /etc/profile.d/*.sh "$HOME/.bash_aliases"; do
  [[ -f "$f" ]] || continue
  printf '\nFILE %s\n' "$f"
  realpath -e "$f"
  sha256sum "$f"
  rg -n '(^|[[:space:]])(source|\.)[[:space:]]|LD_LIBRARY_PATH|LD_PRELOAD|OMPI_MCA|PMIX_MCA|PRTE_MCA|ORTE_MCA|HWLOC_COMPONENTS|OPAL_PREFIX|mca-params|mca_param_files|param_file_prefix|mca_base_component_path' "$f" || true
done
printf '\n--- full current MCA namespace names only (values are config, not secrets) ---\n'
env | LC_ALL=C awk -F= '$1 ~ /^(OMPI_MCA_|PMIX_MCA_|PRTE_MCA_|ORTE_MCA_)/ || $1 == "HWLOC_COMPONENTS" || $1 == "OPAL_PREFIX" || $1 == "LD_LIBRARY_PATH" || $1 == "LD_PRELOAD" || $1 == "BASH_ENV" || $1 == "ENV" {print}'
