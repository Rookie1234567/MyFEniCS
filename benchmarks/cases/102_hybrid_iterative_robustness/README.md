# Task037c hybrid iterative robustness

This case is an explicit, research-only parameter envelope for the Task037c
robustness stages.  It records the three grazing-angle azimuths `-5`, `0`, and
`+5` degrees, requested internal modal counts `M=120` and `M=160`, and formal
MPI sizes `1` and `8`.  The two compact records bind the measured result to
the final clean source SHA; large raw outputs remain ignored.

The existing Task037b `--frozen-m10` profile remains the unchanged 10-degree,
`phi=0`, `M=120`, MPI8 anchor.  Task037c must be selected by its separate
explicit opt-in and uses the same p6/h10, 13.5 nm, S-polarized, static-condensed
operator and PC family.  The original scalar-traction, `max_it=1600` stage is
kept as historical negative evidence.  The later user-authorized research
extension uses the explicit exact one-cell Schur traction and two fixed side
residual-correction applications with `max_it=4500`; it is a bounded research
extension, not a production-qualified default.  Its compact records bind the
Full3D/direct/iterative comparisons and MPI1 identity/resource checks to the
same clean source SHA.

`records/` contains only the two compact qualification carriers listed in the
case configuration.  Large fields, timelines, and process artifacts remain
ignored.
