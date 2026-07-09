# Solver Profile Ranking

## 总览

| rank | 路线 | default100 residual | improvement | KSP 一致性 | 结论 |
|---:|---|---:|---:|---|---|
| 1 | true-FE sampled lift, top_bottom_y, one-shot | `3.688783940e-3` | `5.819x` | 未通过 | 最有价值的新信号 |
| 2 | true-FE sampled lift, top_y, one-shot | `1.575120238e-2` | `1.363x` | 未测独立 KSP | 有弱信号 |
| 3 | Petrov W_AZ / minres | `2.146459669e-2` | `1.000045x` | 不值得继续 | 与 Task016 minres 等价 |
| 4 | adjoint_diag / adjoint_pfe W | `>=2.146892848e-2` | `<=0.999843x` | 不值得继续 | left/test space 变差 |
| 5 | true-FE sampled lift as right PC | `2.354987702e-2` | `0.911x` | 失败 | one-shot basis 不能直接这样接入 KSP |

## Petrov/Test-Space 排名

| W type | best Z | best residual | best improvement | 解释 |
|---|---|---:|---:|---|
| `W_AZ` | `diag_lift` | `2.146459669e-2` | `1.000045x` | 最小残差投影，小幅改善 |
| `W_AZ_normalized` | `diag_lift` | `2.146459669e-2` | `1.000045x` | 与 W_AZ 一致 |
| `W_adjoint_diag` | `pfe_lift` | `2.146892848e-2` | `0.999843x` | 轻微变差 |
| `W_adjoint_pfe` | `diag_lift` | `2.244233310e-2` | `0.956476x` | 明显变差 |
| `W_aux_residual` / `W_residual_projected` | 多组 | 未进入前列 | 未达 gate | 不能解释 coupled slow direction |

## True-FE Lift 排名

| FE lift | mode set | FE RHS residual | one-shot residual | improvement | 解释 |
|---|---|---:|---:|---:|---|
| SciPy GMRES + FE diagonal | top_bottom_y | `9.65e-3` | `3.688783940e-3` | `5.819x` | minimum useful signal |
| SciPy GMRES + FE diagonal | top_y | `6.39e-3` | `1.575120238e-2` | `1.363x` | top-only 不够 |
| exact SPLU tiny10 | top_bottom_y | `3.65e-15` | `9.601240747e-7` | `1.000010x` | tiny10 baseline 已收敛，主要作 sanity |
| PETSc selected FE AMS | top_y/top_bottom_y | failed | - | - | `PCSetUp` error 101，需要另行处理 |

## 推荐排序

1. 继续 true-FE sampled Schur，但改 KSP 集成方式。
2. 用更可靠的 selected FE solve 替代 SciPy diagonal GMRES fallback。
3. 暂停 Petrov/adjoint W 空间继续微调。
4. 保留 BLR/direct 作为 selected RHS 或最终 fallback，不在 task017 合并 production。
