# CODEX TASK 20260703: Stage 4 power consistency

## 0. Branch

Continue on the existing branch:

```text
codex/20260702-rta-output-volume-absorption
```

Read first:

```text
notes/docs/REVIEW_REPORT_20260703_rta_output_volume_absorption.md
```

The goal is to fix the Stage 4 flat-layer power-consistency problem exposed by the previous outcomes. Keep the new `power_summary.csv`, `port_power.json`, `probe_power.json`, `flux_power.json`, and `volume_absorption.json` structure.

---

## 1. Problem

The previous task successfully split the R/T/A outputs and added an initial `A_volume` calculation, but all consistency checks failed. Typical symptoms were:

```text
flat_layer 10 nm:
  port and net_flux are close to R=1, T=0, A=0
  probe_eh_fourier gives A about 0.996

flat_layer 5/3 nm:
  port gives T>1 and negative A
  net_flux gives R>1 and negative T
  A_volume does not close with port balance
```

This means the next task should focus on analytic flat-layer calibration, not on more complex grating physics.

---

## 2. Goal

Make the following four quantities agree for the Stage 4A flat-layer benchmark:

```text
port
probe_eh_fourier
net_flux
volume_absorption
```

They should also agree with an analytic flat-layer Fresnel/layered reference using the same top and bottom reference planes as the numerical result.

---

## 3. Required work

### 3.1 Add analytic flat-layer reference

Add a small reference module, suggested path:

```text
src/postprocessing/flat_layer_reference_3d.py
```

It should compute and output, at minimum:

```text
R_ref
T_ref_at_bottom_reference_plane
A_ref_between_reference_planes
r_amplitude
t_amplitude
incident_power_ref
reflected_power_ref
bottom_transmitted_power_ref
absorbed_power_ref
reference_plane_z_top
reference_plane_z_bottom
interface_z
```

For lossy substrate, `T_ref_at_bottom_reference_plane` must include propagation loss from the interface to the selected bottom reference plane. It should not be confused with interface-only Fresnel transmittance.

### 3.2 Add analytic-only postprocess tests

Before any heavy FEM run, add tests or diagnostics that feed an analytic layered field directly into the postprocessors:

```text
analytic E/H -> probe_eh_fourier
analytic E/H -> net_flux
analytic E/H -> volume_absorption
```

These tests should verify that the postprocessors can recover the analytic `R_ref`, `T_ref`, and `A_ref` without involving a finite-element solve.

### 3.3 Fix probe_eh_fourier if analytic input fails

If the analytic field still gives wrong probe R/T/A, inspect:

```text
incident-field subtraction on top plane
up/down wave direction naming
vertical_sign and k_z convention
phase factors exp(+/- i beta z)
H-field sign convention
complex beta in lossy substrate
modal power normalization
```

E-only Fourier remains diagnostic only. The official probe result should stay E/H Fourier directional fitting.

### 3.4 Verify net_flux sign convention

For analytic fields, check explicitly:

```text
top_flux_outward = P_reflected - P_incident
bottom_flux_outward = P_transmitted_at_bottom_plane
R_flux = 1 + top_flux_outward / P_incident
T_flux = bottom_flux_outward / P_incident
A_flux = 1 - R_flux - T_flux
```

The analytic field should not produce negative transmitted flux for the flat-layer benchmark.

### 3.5 Re-derive A_volume normalization

The current implementation uses:

```text
P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV
```

Re-derive the coefficient using the project code units:

```text
H_code = curl(E) / (i*k0*mu_r)
S_code = 0.5*Re(E x H_code*)
```

Check whether the material loss density should instead use:

```text
0.5*k0*Im(epsilon_r)*|E_total|^2
```

Do not choose the coefficient by intuition. Verify it using analytic lossy plane-wave attenuation and flux loss. The expected check is:

```text
A_volume_ref approximately equals A_flux_ref
```

### 3.6 Check DtN port amplitudes

For flat-layer FEM results, compare the DtN auxiliary amplitudes with the analytic reference:

```text
incident_projection
outgoing_amplitude_top
outgoing_amplitude_bottom
R_port
T_port
A_port_balance
```

Inspect the top incident projection, top source traction sign, upward/downward vertical signs, complex-substrate beta, and `mode.power_per_unit_amplitude`.

### 3.7 Add reference output files

For each flat-layer result folder, write:

```text
flat_layer_reference.json
power_consistency.json
```

`flat_layer_reference.json` should contain the analytic reference values. `power_consistency.json` should contain differences such as:

```text
R_port - R_ref
T_port - T_ref
A_port - A_ref
R_probe - R_ref
T_probe - T_ref
A_probe - A_ref
R_flux - R_ref
T_flux - T_ref
A_flux - A_ref
A_volume - A_ref
closure_error_port_volume = R_port + T_port + A_volume - 1
```

---

## 4. Validation plan

### 4.1 Analytic-only tests

Add tests for:

1. Normal-incidence Fresnel/layered reference.
2. Analytic field through `probe_eh_fourier`.
3. Analytic field through `net_flux`.
4. Analytic lossy-substrate volume absorption against flux loss.
5. Lossless substrate gives near-zero `A_volume`.

### 4.2 FEM flat-layer runs

After analytic-only tests pass, run Stage 4A flat-layer:

```text
mesh_target_size = 10 nm, 5 nm, 3 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = auto_propagating
```

### 4.3 zero-contrast regression

After flat-layer is fixed, run Stage 4B zero-contrast:

```text
mesh_target_size = 10 nm, 5 nm, 3 nm
n_grating = 1 + 0j
```

It should match the flat-layer result at the same mesh size.

### 4.4 real Si block smoke test

Run real Si block at least at 10 nm after the flat-layer and zero-contrast checks pass. Run 5/3 nm only if the preceding checks are already meaningful and resources allow it.

---

## 5. Outcomes

Create:

```text
notes/outcomes/20260703_stage4_power_consistency/
```

with:

```text
summary.md
metrics.csv
parameters.json
run_log.txt
changed_files.md
```

`summary.md` should include these tables:

### Table 1: analytic-only tests

| test | status | max_error | note |
|---|---|---:|---|

### Table 2: flat-layer FEM vs analytic reference

| mesh_nm | method | R | T | A | R_ref | T_ref | A_ref | dR | dT | dA | pass |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### Table 3: zero-contrast regression

| mesh_nm | method | flat_value | zero_contrast_value | difference | pass |
|---:|---|---:|---:|---:|---|

### Table 4: root cause summary

| issue | status | fix |
|---|---|---|

Issues to cover:

```text
probe direction/phase
net flux sign
A_volume normalization
DtN incident/outgoing amplitude
complex substrate beta power normalization
```

### Table 5: final recommendation

State whether Stage 4 power postprocess is ready for zero-contrast and real-block validation, or still diagnostic only.

---

## 6. Acceptance criteria

This task is complete when:

1. `flat_layer_reference.json` is produced for flat-layer cases.
2. Analytic-only probe/net_flux/volume tests pass before heavy FEM runs.
3. Flat-layer FEM results are compared with analytic reference at 10/5/3 nm.
4. `probe_eh_fourier` no longer gives near-total artificial absorption for flat-layer 10 nm.
5. Analytic net_flux no longer gives negative transmitted power.
6. `A_volume` normalization is derived and verified against analytic flux loss.
7. `R + T + A_volume` is checked using consistent reference planes.
8. zero-contrast remains close to flat-layer after fixes.
9. The new outcomes clearly state whether the result is a physical benchmark candidate or still numerical sanity only.
10. Large `results/` folders remain uncommitted.
