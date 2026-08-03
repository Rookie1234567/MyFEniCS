# Topology support and fail-closed policy

This audit uses only analytic angle/mask geometry and the existing Case125
design evidence; it does not read blind responses.  Case125 records:

| design | observed mask signatures | unseen signatures |
|---|---:|---:|
| train96 | 8 | — |
| blind24 design | — | 0 relative to train96 |
| candidate pool 4096 | — | 7 rare signatures |

The five training folds each have support for their test signatures.  In the
4096-point candidate pool, the seven unseen signatures account for 38 points
(about 0.93%).  They are close to propagation boundaries and are not evidence
that a response has been measured there.

The topology-aware expert was compared as L3 and did not qualify.  Regardless
of aggregate model choice, a query with an unseen order mask must return an
explicit `unsupported_mask_topology`/warning status for order-resolved output;
it must not be silently extrapolated and labeled qualified.  Aggregate R/T/A
and order-resolved powers therefore retain separate topology semantics.

The original Case125 `MASK_TOPOLOGY_COVERAGE.json` and the old spatial stress
authority remain unchanged.  `SUPPORTED_INTERPOLATION_WINDOWS_V2.json`
contains four finite local holes with six disjoint support rows per held-out
point; those windows are the hard local-support diagnostic, while the old
whole-region holdouts remain advisory extrapolation stress tests.
