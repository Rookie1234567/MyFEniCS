# Task002 M3R frozen sampling design

All point tables are design-only and bind clean implementation SHA
`eaf17cd01f9e69eff4575b83ea94490a453e09bb`. No M4 PDE was run.

- training: 96 p5 points, seed 20260729;
- frozen validation: 16 p5 points, seed 20260730;
- candidate pool: 4096 points, seed 20260731;
- discretization audit: 8 diagnostic candidates.

Training and frozen validation have exact tuple intersection zero. Frozen
validation is prohibited from feature, transform, kernel, hyperparameter,
model, and acquisition selection. Audit candidates never become production
dataset samples. Combined design hash: `f072c0f3ac03cd97026a85338fd4a79e3cd498c492aea1e79dacbb009e22faa3`.
