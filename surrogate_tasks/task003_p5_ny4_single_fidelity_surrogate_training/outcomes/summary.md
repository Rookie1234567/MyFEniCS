# Task003 summary

M0-L passed on local WSL2 CPU. The Case119 compact dataset is exact (112
rows, 96 training, 16 sealed validation), the independent CPU environment is
`.venv-surrogate-cpu`, the one-aggregate exact-GP smoke is reproducible, and
swap remained unchanged.

Training-only M1/M2 contracts and the deterministic M3 PCE/Matérn-5/2 ARD
exact-GP evaluation were completed. The hard training-CV Gate did not pass;
therefore this run is a controlled stop before `MODEL_SELECTION_LOCK.json`.
The frozen-validation targets remain sealed and no FEM was rerun.

Qualified in this run: dataset integrity, train-only loader, analytic mask,
CPU exact-GP smoke, and physical contracts. Not qualified: a production power
surrogate, complex-amplitude surrogate, uncertainty package, or frozen
validation. Active-learning FEM is left as a separately reviewed next step
(zero points consumed).

