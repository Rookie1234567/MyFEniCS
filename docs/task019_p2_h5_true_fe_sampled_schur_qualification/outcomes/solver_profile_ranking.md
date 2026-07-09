# Solver Profile Ranking

| rank | profile | residual | improvement | decision |
|---:|---|---:|---:|---|
| 1 | best low-dimensional enriched variant `selected_fe_lift_plus_fe_residual_gcrotmk_maxit_32` | `1.516624e-02` | `1.080x` | weak positive only |
| 2 | 240-step FE-AMS continuation | `1.581607e-02` | `1.036x` vs iter120 | too slow for gate |
| 3 | required `top_bottom_y` one-shot `offline_scipy_gcrotmk_diag_rtol_0.01_maxit_16_top_bottom_y` | `1.635705e-02` | `1.002x` | fails minimum signal |
| 4 | 120-step FE-AMS baseline | `1.638606e-02` | `1.000x` | denominator |

## Interpretation

Task019 ranking 里没有通过 p=2 h=5 gate 的 sampled-Schur profile。唯一有意义的下降来自加入 current-FE-residual 向量，这已经把路线从 pure sampled Schur 推向更宽的 domain-decomposition / sweeping style preconditioner。
