#!/usr/bin/env bash
set -u
printf 'scope=bounded installed package/config ownership; no activation, library load, native import, or recursive scan\n'
date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
printf '\n--- actual config owner and package file lists ---\n'
dpkg-query -S /etc/openmpi/openmpi-mca-params.conf
for pkg in openmpi-common libopenmpi3t64:amd64; do
  printf 'PACKAGE %s\n' "$pkg"
  dpkg-query -W -f='${binary:Package} ${Version}\n' "$pkg"
  dpkg-query -L "$pkg" | rg '(^|/)(openmpi-mca-params|mca-params)(-override)?\.conf$|^/etc/openmpi/?$' || true
done
printf '\n--- package conffile registration ---\n'
dpkg-query -W -f='${binary:Package}\n${Conffiles}\n' openmpi-common
printf '\n--- bounded installed path strings ---\n'
strings -a /usr/lib/x86_64-linux-gnu/libopen-pal.so.40.30.3 | rg -F -e '/etc/openmpi' -e '/usr/etc/openmpi' -e 'openmpi-mca-params.conf' -e 'openmpi-mca-params-override.conf' -e '.openmpi/mca-params.conf' | LC_ALL=C sort -u
