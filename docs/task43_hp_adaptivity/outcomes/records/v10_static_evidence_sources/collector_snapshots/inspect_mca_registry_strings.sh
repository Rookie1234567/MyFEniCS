#!/usr/bin/env bash
set +e
printf 'scope=static strings from already identified OpenMPI 4.1.6 ELF; no load/import/MPI command\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
for f in \
  /usr/lib/x86_64-linux-gnu/libopen-pal.so.40.30.3 \
  /usr/lib/x86_64-linux-gnu/libopen-rte.so.40.30.3 \
  /usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_pml_cm.so \
  /usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_pml_ob1.so \
  /usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_pmix_ext3x.so; do
  printf '\nFILE %s\n' "$f"
  realpath -e "$f"
  sha256sum "$f"
  strings -a "$f" | rg -i 'mca_base_(param|override|component|env|envar)|mca_param_files|pml_base_pml|(^|[^a-z])pml([^a-z]|$)|OMPI_MCA|PMIX_MCA|OPAL_PREFIX' | LC_ALL=C sort -u
done
