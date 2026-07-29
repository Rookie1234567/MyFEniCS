# Task002 observable schema v3

The production mother response is frozen as
`task002.fixed-n0-orders.v3` with one stable axis per port:

```text
n = 0
m = -7,-6,-5,-4,-3,-2,-1,0,+1,+2,+3
ports = reflection, transmission
components = outgoing S, outgoing P
```

Each order preserves complex `kx`, `ky`, `kz`; S/P amplitudes use explicit
real/imaginary fields; S power, P power and total order power share the same
order identity. `dispersion_propagating` and `power_carrying` remain distinct,
and structural non-power-carrying channels retain `power=null`.

The checker re-extracted 206 existing Case114/115 raw PDE artifacts without a
PDE rerun. Every extraction has the full v3 identity, including `m=+2,+3`, no
missing order and no raw power-carrying `n=0` order outside the frozen window.
The dense full-wavevector analytic audit found the observed `n=0` propagating
union `m=-7..0`; the extra positive identities are retained explicitly to make
the angle-domain output axis stable and to satisfy the conservative Review V4
window. Nonzero-`n` raw responses remain leakage diagnostics and are not
promoted into production outputs; their maximum observed raw power was
`5.240324047482559e-06`.

Dataset v2 checks exact order-axis equality and rejects any sample reporting a
power-carrying `n=0` response outside v3.
