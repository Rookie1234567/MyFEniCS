# D5C Y6/Y7/Y8 y-only follow-up

This dated supplement records the user's 2026-10-24 extension after the original twelve D5C cases. It leaves the original plan and all earlier run records unchanged. The new candidates are independent children of D5C-B. D5C-Y5 is a comparison reference only and is not a mesh parent.

| Case | Segment counts x / y / z | Cells | Independent midpoint tags (air / substrate / grating) | Parent |
|---|---|---:|---|---|
| Y6 | 2/2/2 / 12/6/12 / 2/2/2 | 1080 | 696 / 360 / 24 | B |
| Y7 | 2/2/2 / 10/10/10 / 2/2/2 | 1080 | 680 / 360 / 40 | B |
| Y8 | 2/2/2 / 12/10/12 / 2/2/2 | 1224 | 776 / 408 / 40 | B; conditional |

All cases use y breakpoints 0/15/35/50 nm and uniform spacing within each segment. Their x and z coordinate arrays and SHA256 hashes are identical to B. The complete coordinate arrays, axis hashes, mesh-plan and input hashes, static positive-volume/aspect checks, and source baseline are recorded in [`d5c_y6_y7_y8_static_axis_plan_20261024_v1.json`](records/d5c_y6_y7_y8_static_axis_plan_20261024_v1.json). Its classifications are static planner evidence; each launched case must still pass live mesh QA.

## Sequence and Y8 condition

Run Y6 first, then wait for its natural completion and clear tree before comparing. Run Y7 next under a separate fresh admission. Before Y8, compare these three pairs under all three existing comparison groups:

1. Y5 → Y6
2. Y5 → Y7
3. Y6 ↔ Y7

Run Y8 if any one of the three pairs fails any comparison group. Do not trigger Y8 solely from an already-known B-to-fine mismatch. If Y8 runs, compare Y6 → Y8 and Y7 → Y8; B and Y5 remain diagnostic references. Do not automatically add another mesh.

The comparison gates remain: global R/T/A_balance/A_volume absolute difference ≤1e-5; per-channel R/T absolute difference ≤1e-6 over all 3772 signed modes, including every power-carrying channel; boundary complex amplitudes and same-coordinate complex E/H relative L2 difference ≤1e-4, without phase fitting or interpolation. `FULL_DTN_NOT_VERIFIED` and canonical sidewall `NOT_MEASURED` remain in force.

## Fixed solver and host contract

The physical model remains the 5 nm Task40 D5C case. Keep p6 condensed direct MUMPS, one factor, at most two same-factor correction solves, mode SHA `752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc` (3772 modes), q39 surface, q15/default volume, and `scale_homogeneous_relative_only_v1` at 1e-13. Single-run gates remain condensed residual ≤1e-9, original active-R5 A6 residual ≤1e-6, and energy ≤1e-5.

Run one case at a time through the standard `run_case` entry after a fresh host check. Keep parent CPU9, worker CPU24, MPI1, math threads1, NUMA interleave 0-1, 64 GiB available-memory floor, no fixed RSS cap, PSS/USS disabled, and swap observation only. Cell-count scaling is not a guarantee of MUMPS memory use.

## Validation before the first run

The Task40-qualified focused batch passed **105 tests** across the D5C axis/profile/live-tag checks, exact Task41 parallel-admission pair through `run_case`, and real manifest-to-worker payload checks. The test batch did not create an FE mesh, matrix, factor, or solve. The first fresh admission and live mesh QA are still required before Y6 results can be claimed.
