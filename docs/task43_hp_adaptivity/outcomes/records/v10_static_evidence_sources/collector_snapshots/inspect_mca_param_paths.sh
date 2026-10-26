#!/usr/bin/env bash
set +e
printf 'scope=static strings for OpenMPI parameter/override paths in already identified ELF; no library load/import/MPI command\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
for f in \
  /usr/lib/x86_64-linux-gnu/libopen-pal.so.40.30.3 \
  /usr/lib/x86_64-linux-gnu/libopen-rte.so.40.30.3 \
  /usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_pml_cm.so \
  /usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_pml_ob1.so \
  /usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_pmix_ext3x.so; do
  printf '\nFILE %s\n' "$f"
  strings -a "$f" | rg -i 'mca[^[:space:]]*(param|override)|param[^[:space:]]*mca|mca-params|openmpi-mca-params|mca_base' | LC_ALL=C sort -u
done
