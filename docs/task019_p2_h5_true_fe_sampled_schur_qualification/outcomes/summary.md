# Outcome Summary

## Task

Task019：验证 `p=2 h=5` 下，Task018 在 `p=1 h=5` 成功的 `AMS/HX + top_bottom_y true-FE sampled Schur residual-correction` 是否还能保持有效。

## Branch

`codex/20260707-real-split-ams-hx-qualification`

## Final Answer

不能。`p=2 h=5` 的矩阵导出和 real-split 等价性通过了，但 required `top_bottom_y` one-shot 只有 `1.0018x` 改善；最强的创造性低维扩展也只有 `1.0804x`，没有达到 `<1e-2` 或 `>=2x` 的 minimum useful gate。

失败点不是 mode id 选错。baseline 残差约 `92.7%` 仍然集中在 selected `top_bottom_y` auxiliary 分量上；真正的问题是 p=2 下 selected FE response / low-dimensional Schur correction 不能同时消掉 auxiliary 残差和由耦合项 `C` 诱发的 FE bulk 后效应。

## Key Results

| item | value |
|---|---:|
| complex dofs | `301648` |
| real dofs | `603296` |
| real nnz estimate | `142535504` |
| export RSS | `3.356 GB` |
| 120-step FE-AMS baseline residual | `1.638606e-02` |
| 240-step continuation residual | `1.581607e-02` |
| best required `top_bottom_y` one-shot | `1.635705e-02` |
| best required one-shot improvement | `1.002x` |
| best creative low-dimensional variant | `1.516624e-02` |
| best creative variant improvement | `1.080x` |

## Residual Structure

| block | relative to b | relative to total residual |
|---|---:|---:|
| `fe_real` | `4.547862e-03` | `0.278` |
| `aux_real` | `6.012441e-03` | `0.367` |
| `fe_imag` | `4.137961e-03` | `0.253` |
| `aux_imag` | `1.394803e-02` | `0.851` |
| `selected_top_bottom_y_aux_components` | `1.518858e-02` | `0.927` |
| `all` | `1.638606e-02` | `1.000` |

## Selected FE RHS Sweep

| solver label | mode set | FE RHS max residual | one-shot residual | improvement |
|---|---|---:|---:|---:|
| `offline_scipy_gcrotmk_diag_rtol_0.01_maxit_16_top_bottom_y` | `top_bottom_y` | `2.213e-01` | `1.635705e-02` | `1.002x` |
| `offline_scipy_gcrotmk_diag_rtol_0.01_maxit_8_top_bottom_y` | `top_bottom_y` | `2.244e-01` | `1.635892e-02` | `1.002x` |
| `offline_scipy_gcrotmk_diag_rtol_0.01_maxit_4_top_bottom_y` | `top_bottom_y` | `2.550e-01` | `1.636890e-02` | `1.001x` |
| `offline_scipy_lgmres_diag_rtol_0.01_maxit_16_top_bottom_y` | `top_bottom_y` | `3.187e-01` | `1.637528e-02` | `1.001x` |
| `offline_scipy_gmres_diag_rtol_0.01_maxit_16_top_bottom_y` | `top_bottom_y` | `3.310e-01` | `1.637946e-02` | `1.000x` |

## Low-Dimensional Variants

| variant | residual after | improvement | decision |
|---|---:|---:|---|
| `selected_fe_lift_plus_fe_residual_gcrotmk_maxit_32` | `1.516624e-02` | `1.080x` | weak positive only |
| `selected_fe_lift_plus_fe_residual_lgmres_maxit_32` | `1.516883e-02` | `1.080x` | weak positive only |
| `aux_only_plus_fe_residual_lgmres_maxit_32` | `1.519766e-02` | `1.078x` | weak positive only |
| `aux_only_top_bottom_y` | `1.638567e-02` | `1.000x` | no useful signal |

## Resource Notes

一次性 `baseline_max_it=1000` 尝试超过 2 小时仍未写出 baseline summary，观测 RSS 约 `12.78/13.65 GiB`，因此改成可恢复的 120-step baseline/continuation。120 步 solve time 约 `1420.8 s`，240 continuation 又花费 `1357.5 s`，真实残差只从 `1.638606e-02` 到 `1.581607e-02`。

## Local Paper Signals

| paper file | relevant signal |
|---|---|
| `0610531v5.pdf` | optimized Schwarz for Maxwell，说明阻抗/特征传输条件比普通重叠更关键 |
| `2606.04982v1.pdf` | heterogeneous time-harmonic Maxwell 的 impedance overlapping DDM，和下一步最贴近 |
| `2501.18305v2.pdf` | 带吸收 Maxwell 的 two-level weighted Schwarz 和 adaptive coarse space |
| `1809.05634v1.pdf` | quasi-periodic layered media 的 sweeping preconditioner，贴合当前 z 分层 grating/port |
| `1007.4291v2.pdf` | moving-PML sweeping 思路，可作为波动问题预条件器设计参考 |
| `High Performance Parallel Solvers for the time-harmonic Maxwell Equations.pdf` | HX/AMS 对 nearby positive Maxwell 有价值，但不定问题需要更强全局策略 |
| `A_Novel_Matrix-Free_Finite_Element_Method_for_Time-Harmonic_Maxwells_Equations.pdf` | p=2 内存压力提示后续应考虑 matrix-free matvec + DDM/sweeping |

## Gate Decision

| gate | decision |
|---|---|
| export and real split equivalence | pass |
| p=2 h=5 baseline availability | partial pass: 120-step baseline completed; 1000-step single run not workstation-safe as one shot |
| required `top_bottom_y` one-shot minimum | fail |
| residual outer loop | not run by gate rule |
| strong gate | fail |
| production-like `1e-6` | fail |
| p=2 h=2 preflight | closed |

## Next Questions for Review

1. 是否同意停止 `top_bottom_y` low-dimensional sampled Schur 作为 p=2 主线？
2. 是否将 Task020 转向 impedance DDM / sweeping / two-level Schwarz 路线？
3. 是否把当前 runner 保留为 research diagnostic，而不合入 production solver？
