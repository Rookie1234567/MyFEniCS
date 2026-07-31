# Training-only CV

The five folds are deterministic, hash-bound, maximin-ordered folds over the
96 training feature rows (`seed=20260731`). Degree-2 and degree-3 PCE and the
primary Matérn-5/2 ARD exact-GP were evaluated sequentially on CPU.

The GP hard Gate failed for all three aggregate quantities under the required
NRMSE / p95 absolute / significant-truth relative thresholds. It also failed
for the 21 training-defined primary order-power channels under the required
normalised p95 power threshold. These are recorded verbatim in
`outcomes/training_cv.json`; no tolerance or Gate was changed. Sparse exact
corner and cutoff anchors are retained and reported, not removed.

Because the hard Gate failed, the prescribed next stage is a separately
reviewed active-learning FEM round (maximum three rounds of eight points). No
candidate was evaluated and no new FEM point was consumed in this run.

