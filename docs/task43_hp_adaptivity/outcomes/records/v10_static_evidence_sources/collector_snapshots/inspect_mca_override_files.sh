#!/usr/bin/env bash
set -u

printf 'scope=bounded static config/override path check; no activation source, library load, native import, MPI command, or recursive filesystem scan\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'

printf '\n--- package ownership and installed config inventory ---\n'
dpkg-query -S /usr/lib/x86_64-linux-gnu/libopen-pal.so.40.30.3
dpkg-query -W -f='${binary:Package} ${Version}\n' libopenmpi3t64:amd64
dpkg-query -L libopenmpi3t64:amd64 | rg '(^|/)(openmpi-mca-params|mca-params)(-override)?\.conf$|^/etc/openmpi/?$'

printf '\n--- bounded config candidates derived from installed strings and package paths ---\n'
for f in \
  "$HOME/.openmpi/mca-params.conf" \
  "$HOME/.openmpi/openmpi-mca-params.conf" \
  "$HOME/.openmpi/openmpi-mca-params-override.conf" \
  /etc/openmpi/openmpi-mca-params.conf \
  /etc/openmpi/openmpi-mca-params-override.conf \
  /etc/openmpi/mca-params.conf \
  /etc/openmpi/mca-params-override.conf \
  /etc/openmpi-mca-params.conf \
  /etc/openmpi-mca-params-override.conf \
  /usr/etc/openmpi-mca-params.conf \
  /usr/etc/openmpi-mca-params-override.conf; do
  if [[ -e "$f" ]]; then
    printf 'PRESENT %s\n' "$f"
    realpath -e "$f"
    sha256sum "$f"
    rg -n '^[[:space:]]*(pml|btl|mtl|mca_param_files|mca_base_param_file_path|mca_base_param_file_path_force|mca_base_param_file_prefix|mca_base_env_list)[[:space:]]*=' "$f" || true
  else
    printf 'ABSENT %s\n' "$f"
  fi
done

printf '\n--- bounded MCA parameter selectors in current login shell ---\n'
for v in \
  OPAL_PREFIX \
  OMPI_MCA_mca_base_param_file_path \
  OMPI_MCA_mca_base_param_file_path_force \
  OMPI_MCA_mca_base_param_file_prefix \
  OMPI_MCA_mca_base_envar_file_prefix \
  OMPI_MCA_mca_base_env_list \
  OMPI_MCA_mca_base_component_path \
  OMPI_MCA_mca_param_files \
  OMPI_MCA_mca_base_override_param_file \
  OMPI_MCA_pml \
  OMPI_MCA_pml_base_pml \
  PMIX_MCA_mca_base_param_file_path \
  PRTE_MCA_mca_base_param_file_path \
  ORTE_MCA_mca_base_param_file_path; do
  if [[ ${!v+x} ]]; then printf 'SET %s=%q\n' "$v" "${!v}"; else printf 'UNSET %s\n' "$v"; fi
done
