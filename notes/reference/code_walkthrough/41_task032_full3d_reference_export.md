# Task032 full-3D reference export

## Entry points

The ordinary 3D runner remains unchanged unless
`--full3d-reference-export` is supplied.  The related public options are:

```text
--full3d-reference-export
--full3d-reference-plane-z <z0> <z1> ...
--full3d-reference-sample-count-x <nx>
--full3d-reference-sample-count-y <ny>
```

`run_3d_cases._config_with_overrides` maps these options to
`SimulationConfig3D`.  `postprocess_3d` calls
`export_full3d_reference_samples` only after the total E field and curl-based H
field are available.

## Ownership and communication

`periodic_plane_sample_grid` creates a small replicated point list in
`(z,y,x,xyz)` order.  Each rank evaluates only points colliding with its local
or ghost cells.  Small `(point index, side score, value)` packets are
all-gathered, and the deterministic side score selects the middle-region trace
when a point lies on a z facet.

This is not a global FE-vector gather.  The uncompressed replicated payload is
computed before evaluation and is rejected above 64 MiB.  The Task032 frozen
40 x 20 x 5 E/H request is 384000 bytes.

## Interface orientation

Requested planes must be strictly increasing.  The first interface uses the
+z cell and the last uses the -z cell; both therefore approach the interfaces
from the middle modal region.  Interior facet-coincident planes use the +z
cell.  The archive explicitly stores x/y tangential traces for the first and
last planes.

## Outputs and limits

Only rank 0 writes `full3d_reference_samples.npz` and its lightweight JSON
metadata.  The JSON SHA-256 is copied into `run_summary.json`.  The feature is
off by default, does not replace rank-local VTU/PVD output, and does not yet
perform Hybrid alignment or error computation; those consumers belong to
later Task032 phases.
