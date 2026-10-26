#!/usr/bin/env bash
set -u
repo=/home/fenics/Projects/NN-Lab-V2
shared=/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/.venv
printf 'scope=read-only; no activation sourced; no native import\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
printf '\n--- tracked activation and stated source ---\n'
realpath -e "$repo/scripts/activate_task40_phi90_pord64.sh"
sha256sum "$repo/scripts/activate_task40_phi90_pord64.sh"
rg -n 'source |\. |LD_LIBRARY_PATH|PYTHONPATH|OMPI_MCA|PMIX_MCA|PRTE_MCA|ORTE_MCA|HWLOC_COMPONENTS|TASK39EXTRA|TASK40_SHARED' "$repo/scripts/activate_task40_phi90_pord64.sh" || true
printf '\n--- venv activation identities and source selectors ---\n'
realpath -e "$shared/bin/activate" "$shared/pyvenv.cfg"
sha256sum "$shared/bin/activate" "$shared/pyvenv.cfg"
rg -n 'source |\. |LD_LIBRARY_PATH|PYTHONPATH|OMPI_MCA|PMIX_MCA|PRTE_MCA|ORTE_MCA|HWLOC_COMPONENTS|VIRTUAL_ENV|PATH=' "$shared/bin/activate" "$shared/pyvenv.cfg" || true
printf '\n--- current shell selected environment (unset distinguished from empty) ---\n'
for v in OMPI_MCA_pml OMPI_MCA_btl OMPI_MCA_mtl OMPI_MCA_mca_param_files OMPI_MCA_mca_base_param_file_prefix OMPI_MCA_mca_base_component_path OMPI_MCA_mca_base_env_list PMIX_MCA_mca_param_files PMIX_MCA_mca_base_param_file_prefix PMIX_MCA_psec PMIX_MCA_gds PRTE_MCA_mca_param_files PRTE_MCA_mca_base_param_file_prefix ORTE_MCA_mca_param_files ORTE_MCA_mca_base_param_file_prefix HWLOC_COMPONENTS OPAL_PREFIX LD_LIBRARY_PATH LD_PRELOAD PATH PYTHONPATH VIRTUAL_ENV TASK40_SHARED_VENV TASK40_SHARED_REPO_ROOT TASK39EXTRA_INT64_STACK_ROOT TASK39EXTRA_PORD64_ROOT; do
  if [[ ${!v+x} ]]; then printf 'SET %s=%q\n' "$v" "${!v}"; else printf 'UNSET %s\n' "$v"; fi
done
printf '\n--- known OpenMPI parameter files and selected MCA values ---\n'
for f in "$HOME/.openmpi/mca-params.conf" "$HOME/.openmpi/openmpi-mca-params.conf" /etc/openmpi/openmpi-mca-params.conf /etc/openmpi-mca-params.conf /usr/etc/openmpi-mca-params.conf; do
  if [[ -f "$f" ]]; then
    printf 'PRESENT %s\n' "$f"
    realpath -e "$f"
    sha256sum "$f"
    rg -n '^[[:space:]]*(pml|btl|mtl|mca_param_files|mca_base_param_file_prefix|mca_base_component_path|mca_base_env_list)[[:space:]]*=' "$f" || true
  else printf 'ABSENT %s\n' "$f"; fi
done
printf '\n--- login startup chain candidates, only source and MPI/library override lines ---\n'
for f in /etc/profile /etc/bash.bashrc "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile" "$HOME/.bashrc"; do
  if [[ -f "$f" ]]; then
    printf 'PRESENT %s\n' "$f"
    realpath -e "$f"
    sha256sum "$f"
    rg -n '(^|[[:space:]])(source|\.)[[:space:]]|LD_LIBRARY_PATH|OMPI_MCA|PMIX_MCA|PRTE_MCA|ORTE_MCA|HWLOC_COMPONENTS|OPAL_PREFIX|mca-params|mca_param_files|param_file_prefix' "$f" || true
  else printf 'ABSENT %s\n' "$f"; fi
done
