# D5C-Y7 finite-R5 modal-cutoff follow-up

This is a static preparation record for four serial, systemd-supervised `run_case` candidates using the completed D5C-Y7 solution as the finite R5 reference. No FE run was started during this preparation. The frozen parent is Y7, 1080 cells (`[6,30,6]`), source `1207cb78889fba6de4fd03ea72a238b334aa61a7`, input `53e82a6b60bacec37f34f1ce628c673fdfa376d666699c491c873a1b0b2f8bd6`, physical `af7e3fe0c0872420af56902aff4c8369a087b25cd7de9e8352930196fcb3c87c`, and resolved config `70943fba5c3531904651688371978d15afa0fc2fcfe447d6b6b31e1b4ff0047a`. Its finite R5 inventory has 3772 ordered signed keys, mode SHA `752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc`; 1230 are propagating and 2506 are power-carrying, including lossy-bottom channels marked nonpropagating.

| Case | Centered rectangle `|m|≤M, |n|≤N` | Active keys | Propagating | Power-carrying | Omitted-boundary relative-L2 lower bound | Static implication |
|---|---:|---:|---:|---:|---:|---|
| M7_N9 | 7 × 9 | 1140 | 506 | 826 | 2.280735864e-3 | Guaranteed fail of the all-3772 boundary gate |
| M9_N14 | 9 × 14 | 2204 | 962 | 1588 | 1.116616374e-3 | Guaranteed fail of the all-3772 boundary gate |
| M9_N20 | 9 × 20 | 3116 | 1230 | 2178 | 2.649614889e-5 | Necessary condition only; outcome unknown |
| M10_N20 | 10 × 20 | 3444 | 1230 | 2342 | 7.626844689e-6 | Necessary condition only; outcome unknown |

The first two cases are retained as authorized coarse-cutoff diagnostics and must not be skipped because their boundary failure is already implied. The last two retain every propagating key, but still omit finite-parent channels. No candidate is described as infinite-DtN or as passing before its solve and comparison.

Each candidate is bound to the same Y7 finite R5 parent, preserving its signed-key order. The actual selection hashes are in the static v2 plan and per-case execution packages: active mode, selected signed-key, and selected parent-index SHA256. Comparisons zero-extend each candidate to all 3772 parent keys. The gates remain: global R/T/A_balance/A_volume absolute difference ≤1e-5; every signed per-mode R/T absolute difference ≤1e-6, including R00 and all power-carrying channels; boundary complex amplitudes and same-coordinate complex E/H relative L2 ≤1e-4 without phase fitting. Horizontal Et/Ht remain diagnostics; canonical sidewall remains `NOT_MEASURED`. `FULL_DTN_NOT_VERIFIED` and `AUTHORITY_LIMITED` remain in force.

Per-run active-A6 checks are limited to the candidate rectangle. Single-run condensed residual, active-A6 and energy thresholds, one same-factor lifecycle with at most two correction solves, q39 surface integration, q15/default volume integration, relative-only sparse cutoff and the existing host-floor/systemd contracts remain unchanged. The packages require their own fresh admission and one independent systemd user service at a time; no automatic retry is allowed.

The earlier v1 static plan is preserved unchanged (SHA256 `917f7268c502f7aa1f888f78b176e71f4b23de495de9c9776f616b3660fb1e54`). Its four square-cutoff candidates all omitted signed key top `(m=0,n=-20,s)` and therefore each had an irreducible boundary error above 1e-4. Corrected v2 supersedes that candidate ladder but does not delete its history. The Y7/Y8 size record is also explicit: Y7 is 1080 cells (`6×30×6`) and Y8 is 1224 cells (`6×34×6`); they are not same-size meshes.

Main's static review is `/tmp/task40_d5c_5nm_modal_cutoff_followup_20261025_v1/supervisor_static_review_rectangles_v1.json` (SHA256 `55f4f660b04885e206066a48be0dd257432ecb7a2b632accab55c91c09d8a930`). This record covers the corrected static range and implementation scope. Exact clean-source packages and sidecars are generated after the source freeze; no FE launch occurs until the main technical review of those exact hashes.
