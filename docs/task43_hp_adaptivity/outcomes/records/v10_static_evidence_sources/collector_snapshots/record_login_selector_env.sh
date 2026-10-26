#!/usr/bin/env bash
set -u
printf 'scope=current login-invoked shell environment, no profile source or activation; distinguishes unset/empty\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
for v in XDG_SESSION_TYPE XDG_CURRENT_DESKTOP DESKTOP_SESSION GNOME_DESKTOP_SESSION_ID XDG_CONFIG_HOME BASH_ENV ENV OMPI_MCA_pml OMPI_MCA_pml_base_pml OMPI_MCA_btl OMPI_MCA_mtl OMPI_MCA_mca_base_param_file_prefix OMPI_MCA_mca_base_envar_file_prefix OMPI_MCA_mca_base_env_list OMPI_MCA_mca_base_component_path OMPI_MCA_mca_param_files OMPI_MCA_mca_base_override_param_file PMIX_MCA_mca_base_param_file_prefix PRTE_MCA_mca_base_param_file_prefix ORTE_MCA_mca_base_param_file_prefix HWLOC_COMPONENTS LD_LIBRARY_PATH LD_PRELOAD; do
  if [[ ${!v+x} ]]; then printf 'SET %s=%q\n' "$v" "${!v}"; else printf 'UNSET %s\n' "$v"; fi
done
