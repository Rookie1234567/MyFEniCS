# Task40 D13 continuation and Z2 contract — 2026-10-18

## Authorization and history boundary

On 2026-10-18 the user authorized continuing the Task40 sequence from 13.5 nm
toward 5 nm and 0.7 nm, using bounded, evidence-led comparisons. This
supersedes the earlier stop after field 14 as the current continuation
instruction. It does not rewrite the historical 12/13/14-field accounting or
retroactively change the authorization under which those fields were run. No
old Task39 N0/p3 work is resumed.

The D13 center is the existing same-policy relative-only Y2 run
`20261016T190312.893443Z`: 2016 cells, axes `[6,24,14]`, R13 with 612 modes,
surface quadrature q28, volume q15/default, and
`scale_homogeneous_relative_only_v1` at `1e-13`. Existing same-policy Y3
`20261016T202834.284773Z` supplies the y-only comparison; existing X2 supplies
the x-only comparison. They are reused as evidence, not rerun.

The next single field is Z2, obtained by bisecting every realized Y2 z
interval once. This changes only z relative to Y2. Its plan is a comparison
candidate, not a live-mesh result or a claim that the z refinement will pass.
Reference-tail expansion is considered only after Z2 and only if the finite
R13 evidence supports it. `FULL_DTN_NOT_VERIFIED` and `AUTHORITY_LIMITED`
remain in force.

## Frozen Z2 axis and geometry contract

The plan is `task40_phi90_d13_z2_axes_bisect_from_y2_v1`, SHA256
`82bc3addb84e5e2926395f567171b71066d74e4a829ed405d1a0579001e839ac`.
Coordinates are in nm:

| Axis | Coordinates | Segment cell counts | Parent identity |
|---|---|---:|---|
| x | `[0, 8.25, 16.5, 25, 33.5, 41.75, 50]` | `[2,2,2]` | exactly Y2, SHA256 `bb1d6be1…b6f2a5361` |
| y | `[0, 1.875, 3.75, 5.625, 7.5, 9.375, 11.25, 13.125, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5, 35, 36.875, 38.75, 40.625, 42.5, 44.375, 46.25, 48.125, 50]` | `[8,8,8]` | exactly Y2, SHA256 `7e10438f…6e2e9e16` |
| z | `[-10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130]` | `[2,24,2]` | bisected Y2, SHA256 `4892232f…d01b08c` |

Axis counts are `[6,24,28]`, or 4032 hexahedra. The planes `z=-10,0,120,130`
and periodic x/y faces stay aligned. Independent cell-interval midpoint
classification predicts air/substrate/grating counts `3360/288/384`; this is
an expected-count contract only. The formal run must still compare actual
coordinates, axis hashes, cell tags, and global cell count against it.

| Identity | Value |
|---|---|
| Run ID | `task40_phi90_13p5_D13_Z2_from_Y2_p6_direct_v1` |
| Profile | `task40para_phi90_13p5_D13_Z2_from_Y2_p6_direct_v1` |
| Input SHA256 | `32eae0338865ad3784bc9d835b5fb21ca27ea525529e12be0688317b49048309` |
| Physical SHA256 | `30d1d0525b5c477cabd1ce3dbd9b20cead50e07113caeefcbad9ec31c3cf5e24` |
| Resolved SHA256 | `c674f9f256b5d24cf60cf8aa9dca8a5d8b842dd23532da68bfd778a09e955084` |
| Active and parent modes | 612; SHA256 `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e` |
| Surface / volume quadrature | q28 fixed R+2 envelope / q15 default |
| Sparse policy | `scale_homogeneous_relative_only_v1`, relative tolerance `1e-13` |

Numerical gates and direct-solver lifecycle are unchanged: condensed residual
`1e-9`, independent native A6 `1e-6`, energy `1e-5`, one MUMPS factor and at
most two same-factor corrections. CPU9 parent / CPU24 worker, MPI1, math
threads1, NUMA interleave nodes0-1, PSS/USS/smaps disabled, swap observed
without using prediction as a stop gate, and the actual 64 GiB host-availability
floor/shared heavy lock remain required. No fixed RSS ceiling applies to this
13.5 nm case. No cross-mesh FE vectors or factor are reused.

## Canonical pillar-sidewall trace plan — not yet measured

The existing horizontal z-plane `Et/Ht` samples do not satisfy the canonical
pillar-sidewall observation. The bounded follow-up uses the saved Y2 p6 storage
vector from the exact Y2 run above, after verifying its artifact SHA, vector
length, source/input/resolved identities, actual axis hashes, material tags,
mode manifest, and MPC/phase identity. It reconstructs the same mesh, p6
Nedelec space, and periodic MPC mapping, then uses the existing
`restore_p0_full_field` homogenize/backsubstitute/scatter path. It does not use
DG6 VTU interpolation, create a global matrix, assemble a factor, or solve.

On the four pillar walls (`x=16.5/33.5` for `15<=y<=35` and
`y=15/35` for `16.5<=x<=33.5`, `0<=z<=120`), evaluate unaveraged one-sided
traces from the adjacent tagged cells at the production surface rule. Keep
air-side and Si-side rows separate, retain geometry/normal/orientation and
periodic-face mapping, and omit only the predeclared geometric corner/edge
neighborhoods where traces meet. Compare both tangential E components and both
tangential H components using the production `H-from-curl(E)` convention and
material scaling. Report absolute scales and existing task normalization
separately; do not average, interpolate from VTU, or claim a pass before actual
capture. This remains `PLAN_ONLY` until the bounded extraction is executed.

## Current execution state

The Z2 planner, explicit profile/input, live mesh-evidence route, and focused
manifest/worker tests are prepared. The exact package must bind the final clean
source before fresh admission. No Z2 mesh, FE assembly, factor, or solve has
been started at this point.
