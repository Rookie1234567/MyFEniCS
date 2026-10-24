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

## Y5/Y6/Y7 comparison result

The completed offline comparison is recorded in [`d5c_y5_y6_y7_saved_output_comparison_20261024_v1.json`](records/d5c_y5_y6_y7_saved_output_comparison_20261024_v1.json), with every signed mode in [`d5c_y5_y6_y7_all_3772_modes_20261024_v1.csv`](records/d5c_y5_y6_y7_all_3772_modes_20261024_v1.csv) and a reproducible comparator at [`d5c_y5_y6_y7_saved_output_comparison_20261024_v1.py`](records/d5c_y5_y6_y7_saved_output_comparison_20261024_v1.py). It reads the compact modal JSON and saved field-sample archives only; no FE, factor, VTU, or resource stream was read.

| Pair | Global R/T/A_balance/A_volume | All 3772 and power-carrying channel R/T | Boundary amplitude and same-coordinate E/H | Result |
|---|---|---|---|---|
| Y5 → Y6 | PASS; largest relevant absolute change is about 7.64e-8 | PASS; max R 7.65e-8, max T 1.17e-11 | PASS; boundary 1.14e-7, E 1.52e-6, H 1.48e-5 | All three groups pass |
| Y5 → Y7 | FAIL; ΔR_total=-6.36415e-4, ΔA_balance=-6.36141e-4, ΔA_volume=-6.36141e-4 | FAIL; R00_s and the largest all-mode/power-carrying ΔR are -6.36887e-4; max ΔT is 9.56e-8 | FAIL; boundary 9.48e-4, E 1.244e-3, H 1.892e-3 | All three groups fail |
| Y6 → Y7 | FAIL; ΔR_total=-6.36338e-4, ΔA_balance=-6.36064e-4, ΔA_volume=-6.36064e-4 | FAIL; R00_s and the largest all-mode/power-carrying ΔR are -6.36810e-4; max ΔT is 9.56e-8 | FAIL; boundary 9.48e-4, E 1.244e-3, H 1.892e-3 | All three groups fail |

All-mode and power-carrying groups include 3772 and 2506 channels respectively; the propagating-only subset is reported separately and does not replace either gate. Y5→Y6 passes this pairwise comparison. The Y6/Y7 pair has the same 30 y layers but reallocates them from 12/6/12 to 10/10/10; its failure shows that equal layer count alone is not sufficient. The predeclared condition is met, so run the already specified Y8 case (12/10/12, 1224 cells) after a fresh admission. Then compare Y6→Y8 and Y7→Y8 under the same gates. This does not establish convergence or full-DtN authority.

Y5 predates the Y6/Y7 profile-source revision. The comparison record binds each source SHA and confirms that the revision changed only Task40 D5C axis/profile/admission/test routing; the numerical assembly/solver kernels, physical configuration, mode hash, surface/volume quadrature, and cutoff policy match. Y5→Y7 and Y6→Y7 remain saved-output comparisons across their recorded source identities.

The comparison gates remain: global R/T/A_balance/A_volume absolute difference ≤1e-5; per-channel R/T absolute difference ≤1e-6 over all 3772 signed modes, including every power-carrying channel; boundary complex amplitudes and same-coordinate complex E/H relative L2 difference ≤1e-4, without phase fitting or interpolation. `FULL_DTN_NOT_VERIFIED` and canonical sidewall `NOT_MEASURED` remain in force.

## Fixed solver and host contract

The physical model remains the 5 nm Task40 D5C case. Keep p6 condensed direct MUMPS, one factor, at most two same-factor correction solves, mode SHA `752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc` (3772 modes), q39 surface, q15/default volume, and `scale_homogeneous_relative_only_v1` at 1e-13. Single-run gates remain condensed residual ≤1e-9, original active-R5 A6 residual ≤1e-6, and energy ≤1e-5.

Run one case at a time through the standard `run_case` entry after a fresh host check. Keep parent CPU9, worker CPU24, MPI1, math threads1, NUMA interleave 0-1, 64 GiB available-memory floor, no fixed RSS cap, PSS/USS disabled, and swap observation only. Cell-count scaling is not a guarantee of MUMPS memory use.

## Validation and run status

The Task40-qualified focused batch passed **105 tests** across the D5C axis/profile/live-tag checks, exact Task41 parallel-admission pair through `run_case`, and real manifest-to-worker payload checks. The test batch did not create an FE mesh, matrix, factor, or solve. Y6 and Y7 each have their own clean-source, fresh admission, live mesh QA, direct solve, and natural-cleanup records. Y8 has not started; it requires its own fresh admission and live mesh QA. Earlier attempts and stop records remain historical and are not overwritten.
