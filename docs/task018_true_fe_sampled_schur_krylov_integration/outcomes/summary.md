# Outcome Summary

## Task

Task018: adaptive true-FE sampled Schur / AMS-HX Krylov integration。

本轮目标是把 Task017 中 `top_bottom_y` true-FE sampled lift 的 one-shot 正信号，转化为稳定的 Krylov / residual-correction / augmentation 求解过程；如果不能转化，则给出足够证据暂停当前 AMS/HX + modal sampled Schur 主线。

## Branch

`codex/20260707-real-split-ams-hx-qualification`

## Final Answer

Task017 的 true-FE sampled lift 正信号可以转化为稳定的 solver-like 过程。最佳结果来自 `residual_outer_zero`：从零初值开始，交替执行 bounded FE-AMS 段和 `top_bottom_y` true-FE sampled Schur residual correction，3 个 cycle 后完整真实残差达到 `1.6616234679826358e-3`，相对 baseline `2.145878536207579e-2` 改善 `12.914x`，通过 minimum useful 和 strong gate。

这还不是 production-like solver，因为没有达到 `1e-6`，而且 selected FE RHS 仍依赖 SciPy diagonal GMRES 研究路径；但它已经不是单次离线 one-shot，而是可重复的外层残差校正流程。

## Changed Files

| 文件 | 作用 |
|---|---|
| `src/studies/run_stage4_true_fe_sampled_schur_krylov.py` | 新增 Task018 研究 runner：selected FE RHS sweep、initial correction、residual-corrected loop、projected residual GMRES prototype |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/*.csv` | 本轮数值结果主表 |
| `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/*.md` | 本轮中文总结、排名、合并建议和下一步决策 |
| `docs/README.md` | 更新 task018 索引结论 |
| `notes/theory/maxwell_iterative_preconditioners_task012.md` | 补充 task018 后的理论路线判断 |

## Run Commands

| 阶段 | 命令摘要 |
|---|---|
| complex export | `docker run ... code-dolfinx-mpc:latest sh -lc '. /usr/local/bin/dolfinx-complex-mode && python -m src.studies.run_stage4_real_split_block_pc export-complex ...'` |
| stable real run | `docker run ... code-dolfinx-mpc:latest sh -lc '. /usr/local/bin/dolfinx-real-mode && python -m src.studies.run_stage4_true_fe_sampled_schur_krylov diagnose-real ...'` |
| validation | `python -m py_compile src/studies/run_stage4_true_fe_sampled_schur_krylov.py` |
| cleanup | 删除 task018 raw_runs 中的 `.npz` 大矩阵，仅保留 metadata/log/CSV |

## Physical Model

| 项 | 值 |
|---|---|
| case | `task014a_default100_stage4_block_grating_p1_h5` |
| domain preset | `default100` |
| period | `100 nm x 100 nm` |
| z 尺寸 | substrate `50 nm`，grating `50 nm`，air `100 nm` |
| wavelength | `13.5 nm` |
| material | Si / silicon, `n = 0.999002304859 + 0.00182649365i` |
| boundary | Floquet x/y + Stage4 Fourier-DtN auxiliary port |
| selected modes | top `(0,0),y` mode `177` and bottom `(0,0),y` mode `531` |

## Numerical Settings

| 项 | 值 |
|---|---|
| real system size | `79956 x 79956` |
| complex dofs | `39978` |
| FE complex dofs | `39270` |
| aux complex dofs | `708` |
| real nnz | `9390960` |
| baseline KSP | right-preconditioned FGMRES, max_it `1000`, restart `200` |
| FE block PC | real hypre AMS/HX, same-H1 auxiliary data, setup once then reused |
| selected FE RHS solvers | SciPy GMRES rtol `1e-2/1e-4/1e-6`, LGMRES, GCROTmk, BiCGStab |
| outer loop | bounded FE-AMS segment + true-FE sampled Schur residual correction |

## Key Results

| profile | final true residual | improvement | decision |
|---|---:|---:|---|
| baseline FE-AMS + aux identity | `2.145878536e-2` | `1.000x` | reproduced |
| one-shot `top_bottom_y`, SciPy GMRES rtol `1e-2` | `1.732413109e-3` | `12.387x` | strong positive |
| initial correction omega `1.0` + 200-step continuation | `1.680968603e-3` | `12.766x` | stable positive |
| residual outer loop from baseline | `1.698334842e-3` | `12.635x` | stable, then stagnates |
| residual outer loop from zero | `1.661623468e-3` | `12.914x` | best, strong gate pass |
| projected residual GMRES + final coarse | `1.708423696e-3` | `12.561x` | positive but not better than Stage D |

## Selected FE RHS Sweep

| selected FE RHS solver | FE RHS max residual | one-shot residual | improvement | time |
|---|---:|---:|---:|---:|
| PETSc selected FE-AMS opt-in | failed | - | - | `2.05 s` |
| SciPy GMRES diag rtol `1e-2` | `5.913e-3` | `1.732e-3` | `12.387x` | `3.03 s` |
| SciPy GMRES diag rtol `1e-4` | `9.980e-5` | `2.506e-3` | `8.561x` | `88.71 s` |
| SciPy GMRES diag rtol `1e-6` | `9.994e-7` | `2.476e-3` | `8.665x` | `181.59 s` |
| SciPy LGMRES diag rtol `1e-4` | `9.988e-5` | `2.429e-3` | `8.836x` | `17.85 s` |
| SciPy GCROTmk diag rtol `1e-4` | `9.995e-5` | `2.468e-3` | `8.696x` | `16.91 s` |
| SciPy BiCGStab diag rtol `1e-4` | `4.970e-3` | `4.291e-3` | `5.001x` | `11.54 s` |
| symmetry `top_bottom_xy` rtol `1e-4` | `9.980e-5` | `2.506e-3` | `8.561x` | `172.86 s` |

更精确的 FE RHS solve 没有增强 one-shot，反而弱于 loose `1e-2`。这说明当前最强 basis 可能不是“越接近精确 `A_FE^{-1}C_j` 越好”，而是 loose GMRES diagonal response 恰好对 dominant slow residual 起到有利滤波。

## Energy Check

本任务不输出 R/T/A。所有 gate 都基于完整真实线性残差：

```text
||A_real x - b_real|| / ||b_real||
```

没有把 PETSc reported residual 当作最终判据。

## Mesh / DoF / Solver Cost

| 项 | 值 |
|---|---:|
| complex export RSS | `0.460 GB` |
| stable runner RSS upper | `1.571 GB` |
| stable real run wall time | 约 `21.7 min` |
| projected GMRES prototype time | `350.2 s` |
| best residual outer loop cycles | 3 cycles 后停滞 |

## Answers To Task Questions

| 问题 | 回答 |
|---|---|
| Task017 `top_bottom_y` one-shot 是否复现？ | 是，同一 mode set 上 residual 达到 `1.732e-3`，比 Task017 的 `3.689e-3` 更强。 |
| 更准确 selected FE RHS 是否增强信号？ | 没有。`1e-4/1e-6` 均弱于 loose `1e-2`。 |
| initial correction 是否保持 `<1e-2` 或 `>=2x`？ | 是。omega `1.0` 后 residual `1.732e-3`，继续 KSP 后 `1.681e-3`。 |
| residual-corrected loop 是否稳定改善？ | 是。从零初值 3 cycle 到 `1.662e-3`，随后停滞但不反弹。 |
| augmented/recycled prototype 是否更好？ | 不更好。projected GMRES 最终 `1.708e-3`，仍为正但弱于 Stage D。 |
| 是否允许进入 p=2 h=5？ | 允许作为下一轮 gated qualification，但本轮未直接运行 p=2。 |
| 是否建议合并代码？ | 建议合并为 opt-in research runner，不改变 production 默认求解器。 |
| 是否满足暂停 AMS/HX + modal sampled Schur 条件？ | 不满足。主线已经成功通过 strong gate。 |
| 若主线暂停，下一条路线是什么？ | 当前不暂停；若后续 p=2 失败，下一路线是 layered-background / RCWA-like inverse 或 two-level DDM/sweeping。 |

## Known Issues

1. PETSc selected FE-AMS opt-in path在同一进程中不稳定，会触发 `KSPSetUp/PCSetUp` error 101，并可能污染后续 AMS communicator setup；稳定 runner 默认禁用它。
2. 最佳结果仍依赖 SciPy selected FE RHS 和小维 coarse correction，尚未封装成 production solver。
3. strong gate 已通过，但 production-like `1e-6` 未达到。
4. `p=2 h=5` 仍需单独任务验证，不能把 p=1 strong gate 自动外推为大规模成功。

## Final Sentence

Task017 的 true-FE sampled lift 正信号可以被转化为稳定的 AMS/HX + sampled Schur residual-correction 集成；当前 AMS/HX + modal sampled Schur 主线不应暂停，而应进入 p=2 h=5 的下一轮 gated qualification。
