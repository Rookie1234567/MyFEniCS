# TRAIN112 local candidate comparison

All results use the frozen 112-row outer folds and training-only response.

| candidate | R NRMSE | T NRMSE | A NRMSE | max Gate score | supported-window Gate | uncertainty Gate | Aggregate Level A |
|---|---:|---:|---:|---:|---|---|---|
| L1_local_rbf_k24_s1e-08 | 0.017540259 | 0.023495225 | 0.036288143 | 3.849247 | False | True | False |
| L4_trend_local_residual_k24 | 0.017029682 | 0.024231737 | 0.036688767 | 4.071891 | False | True | False |
| L2_local_matern_k24 | 0.027526119 | 0.018068222 | 0.035199897 | 4.3384048 | True | False | False |
| E1_latent_median_ensemble | 0.026117993 | 0.019498953 | 0.037082738 | 4.5726532 | True | False | False |
| L2_local_matern_k32 | 0.027061976 | 0.023869174 | 0.03853436 | 4.7639542 | True | False | False |
| E2_cross_fitted_nonnegative_stack | 0.023030793 | 0.017979496 | 0.035778952 | 4.9550184 | False | False | False |

Training-CV selection is `L1_local_rbf_k24_s1e-08`.  No model lock is created unless all Aggregate Level A gates pass.
