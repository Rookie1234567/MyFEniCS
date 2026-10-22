# D15 X2 and Z3-3 offline comparison

This comparison uses only the completed D15-B, D15-X2, and D15-Z3-3 small outputs. No FE, factorization, solve, VTU, or resource-stream read was performed.

Source identities: source SHA differs; actual physics/mode/q/cutoff/mesh identities checked separately. D15-B to X2 changes only x; D15-B to Z3-3 changes only z. All pairs retain p6 direct, the same 612-mode R5 active rectangle, surface q28, volume q15/default, and relative-only cutoff 1e-13.

## Results

- **D15-B_vs_D15-X2 — PASS**: max all-612 |ΔR|=6.27999e-09 ({'side': 'top', 'm': 0, 'n': 0, 'polarization': 's'}), |ΔT|=5.0013e-12 ({'side': 'bottom', 'm': 0, 'n': 0, 'polarization': 's'}); power-carrying max |ΔR|=6.27999e-09, |ΔT|=5.0013e-12; ΔRtotal=-6.28158e-09, ΔTtotal=-4.20511e-12, ΔAvol=6.29044e-09; Erel=2.40558e-06, Hrel=4.82255e-07.
- **D15-B_vs_D15-Z3-3 — FAIL**: max all-612 |ΔR|=1.85176e-06 ({'side': 'top', 'm': 0, 'n': 0, 'polarization': 's'}), |ΔT|=3.26344e-07 ({'side': 'bottom', 'm': 0, 'n': 0, 'polarization': 's'}); power-carrying max |ΔR|=1.85176e-06, |ΔT|=3.26344e-07; ΔRtotal=-1.21817e-06, ΔTtotal=9.26692e-07, ΔAvol=2.91466e-07; Erel=0.000409813, Hrel=0.000447399.

## Interpretation limits

The comparison applies the original three gates: global R/T/A_balance/A_volume absolute difference <=1e-5; each of all 612 signed channel R/T values, including power-carrying channels, <=1e-6; boundary complex amplitude and same-coordinate complex E/H relative L2 <=1e-4 without phase fitting. The CSV contains all 1,224 pair-channel rows. Horizontal Et/Ht remain diagnostic; canonical pillar sidewalls are NOT_MEASURED. The finite R5 active rectangle does not establish full DtN convergence.

Machine-readable result: `docs/task40para_phi90_mesh_modes_direct/outcomes/records/d15_x2_z3_3_saved_output_comparison_20261023_v1.json` (SHA256 `622892aa126f7c2a6d3d135e46a32d112c94262dfb5cf2e125850cde3706be6f`).
Per-channel data: `docs/task40para_phi90_mesh_modes_direct/outcomes/records/d15_x2_z3_3_all_612_modes_20261023_v1.csv` (SHA256 `ced275fd2e8e08fb095a5f80925dcf66ce59f1de66d66f9d8c120b505ac8eea0`).
