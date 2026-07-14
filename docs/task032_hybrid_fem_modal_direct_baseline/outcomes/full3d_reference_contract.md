# Phase 1 full-3D reference contract

## 1. Purpose and status

Phase 1 reuses the existing Stage-4 p2 Nédélec, double-Floquet, Fourier-DtN,
MPI4 direct path.  It does not introduce a second full-3D solver.  The new
interface only adds an explicit, bounded export of complex E/H samples needed
by later Hybrid comparisons.

```text
ordinary default = export disabled
formal h5/h3 reference runs = pending clean source commit
diagnostic h5 MPI4 export = passed
```

The normal rank-local VTU/PVD output remains the full volume-field artifact.
The structured archive below is a compact comparison surface, not a gathered
copy of the full finite-element vector.

## 2. Frozen sampling contract

The Task032 primary run uses:

```text
z planes [nm] = 10, 30, 60, 90, 110
x/y grid = periodic cell-centred 40 x 20
main E/H shape = (5, 20, 40, 3)
dtype = complex128
```

The first and last planes are the Hybrid interfaces.  Their tangential traces
are evaluated from inside the middle modal region:

```text
z = 10 nm  -> positive-z cell
z = 110 nm -> negative-z cell
```

This one-sided convention is important for the DG-interpolated H field when an
exact requested z plane coincides with a mesh facet.  Interior planes use the
positive-z cell in the same situation.  The x/y grid excludes duplicate copies
of the periodic boundaries.

## 3. Heavy artifact schema

`full3d_reference_samples.npz` contains:

| array | shape | meaning |
|---|---:|---|
| `x_nm` | `(40,)` | periodic cell-centred x coordinates |
| `y_nm` | `(20,)` | periodic cell-centred y coordinates |
| `z_nm` | `(5,)` | ordered requested planes |
| `E_V_per_m` | `(5,20,40,3)` | complex total electric field |
| `H_A_per_m` | `(5,20,40,3)` | complex magnetic field reconstructed from curl E |
| `interface_z_nm` | `(2,)` | bottom/top internal interface coordinates |
| `E_t_interface_V_per_m` | `(2,20,40,2)` | explicit x/y electric trace |
| `H_t_interface_A_per_m` | `(2,20,40,2)` | explicit x/y magnetic trace |

`full3d_reference_samples.json` records the schema version, SHA-256, archive
bytes, shape, point count, trace sides, component names and per-plane max-norm
metrics.  `run_summary.json` repeats the archive identity and plane list so a
future Hybrid checker can reject a missing or mismatched reference.

The NPZ, VTU/PVD and raw run directory live below ignored
`benchmarks/artifacts/`.  Git keeps only lightweight hashes, metrics, commands
and environment identity.

## 4. Memory boundary

Each MPI rank reconstructs only the requested structured samples.  For the
frozen grid, the uncompressed replicated E/H payload is:

```text
5 * 20 * 40 * 3 * 16 bytes * 2 fields = 384000 bytes
```

The exporter fails closed above 64 MiB.  It never gathers a full FE vector,
full matrix, LU factor or complete volume mesh to rank 0.

## 5. Diagnostic evidence

The post-convention h5 diagnostic produced finite complex128 arrays, matching
JSON/NPZ/run-summary SHA-256, and exact derived tangential slices.  Its main
solver values were:

```text
FE DoF = 44698
auxiliary Fourier-DtN modes = 80
linear true relative residual = 5.6433276626e-12
R/T/A = 0.0890216029364 / 0.4425882786570 / 0.4683901184066
port-volume closure = -9.5035090908e-14
```

This dirty-source diagnostic validates the exporter only.  It is not the
formal Phase 1 reference record; h5 and h3 will be rerun from the clean export
implementation commit.
