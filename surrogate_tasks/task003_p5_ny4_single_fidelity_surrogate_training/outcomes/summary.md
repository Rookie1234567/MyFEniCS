# Task003 summary

M0-L passed on local WSL2 CPU. The Case119 compact dataset is exact (112
rows, 96 training, 16 sealed validation), the independent CPU environment is
`.venv-surrogate-cpu`, the one-aggregate exact-GP smoke is reproducible, and
swap remained unchanged.

Training-only M1/M2 contracts and the corrected M3R PCE/Matérn-5/2 ARD
exact-GP comparison were completed. The selected candidate is
`exact_gp:features=B`; the hard training-CV Gate still did not pass, so this
run remains a controlled stop before `MODEL_SELECTION_LOCK.json`.
The frozen-validation targets remain sealed and no FEM was rerun.

Qualified in this run: dataset integrity, train-only loader, analytic mask,
CPU exact-GP smoke, corrected latent/feature/basis contracts, and auditable
OOF diagnostics. Not qualified: a production power surrogate,
complex-amplitude surrogate, model lock, or frozen validation. Active-learning
FEM is left as a separately reviewed next step (zero points consumed).
