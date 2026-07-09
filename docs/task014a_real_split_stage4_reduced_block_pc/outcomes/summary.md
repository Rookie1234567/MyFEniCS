# Outcome Summary

## Task

Task014a：reduced Stage 4 real-split FE/aux block PC integration qualification。

本轮目标不是 production solver，而是判断 task013 的 FE-only same-H1 real-split AMS 正信号能否安全进入 reduced Stage 4 的 Floquet MPC + DtN auxiliary 系统。

## Branch

```text
codex/20260707-real-split-ams-hx-qualification
```

## 结论

当前结论是：

```text
real split 与 MPC 后 AMS 数据构造通过；
但当前 P_FE=same-H1 AMS、P_aux=identity 的最小 block PC 没有达到 Stage C 成功门槛；
不进入 p=2 h=5，不进入 full Stage 4 p=2 h=2。
```

一句话回答 task14a：task013 的 FE-only same-H1 real-split AMS 正信号还不能直接进入 Stage 4 reduced system；需要先加入 DtN-aware Schur/aux correction 或 Rayleigh/Floquet modal deflation。

## Run Commands

| 阶段 | 命令 |
|---|---|
| 语法检查 | `python -m py_compile src/studies/run_stage4_real_split_block_pc.py src/constraints/floquet_3d.py` |
| tiny10 complex export | `. /usr/local/bin/dolfinx-complex-mode; python3 -m src.studies.run_stage4_real_split_block_pc export-complex --degree 1 --h-nm 5 --stage-case stage4_block_grating` |
| tiny10 real solve | `python3 -m src.studies.run_stage4_real_split_block_pc solve-real --degree 1 --h-nm 5 --stage-case stage4_block_grating ...` |
| default100 complex export | `. /usr/local/bin/dolfinx-complex-mode; python3 -m src.studies.run_stage4_real_split_block_pc export-complex --degree 1 --h-nm 5 --stage-case stage4_block_grating --domain-preset default100` |
| default100 real solve | `python3 -m src.studies.run_stage4_real_split_block_pc solve-real --degree 1 --h-nm 5 --stage-case stage4_block_grating --domain-preset default100 ...` |
| zero-order 对照 | 同上，附加 `--dtn-order-policy zero_order` |

## 物理与数值设置

| case | 用途 | Stage4 边界 | period | z 高度 | p | h/nm |
|---|---|---|---:|---:|---:|---:|
| `task014a_stage4_block_grating_p1_h5` | tiny10 smoke / 小矩阵 sanity | auxiliary DtN | 10 x 10 nm | -5 到 5 nm | 1 | 5 |
| `task014a_default100_stage4_block_grating_p1_h5` | 主 reduced p1 h5 诊断 | auxiliary DtN auto propagating | 100 x 100 nm | -50 到 100 nm | 1 | 5 |
| `task014a_default100_zero_order_stage4_block_grating_p1_h5` | 补充定位，不计入通过条件 | zero-order local Robin，无 aux unknown | 100 x 100 nm | -50 到 100 nm | 1 | 5 |

## Stage A：real split 等价性

验证对象是 constraint 后的 reduced/assembled PETSc matrix，即 `dolfinx_mpc.assemble_matrix` 后再加入 DtN auxiliary rows 的最终 Stage4 矩阵。没有混用 constraint 前 full matrix 与显式 `C^H A C` 口径。

| case | FE complex dofs | aux complex dofs | n real | nnz real | matvec error | RHS error | RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| tiny10 auto | 144 | 4 | 296 | 18,600 | 1.575e-16 | 0 | 0.262 GB |
| default100 auto | 39,270 | 708 | 79,956 | 9,390,960 | 6.805e-16 | 0 | 0.458 GB |
| default100 zero-order | 39,270 | 0 | 78,540 | 5,228,128 | 2.176e-16 | 0 | 0.378 GB |

Stage A 通过。误差远低于 `1e-10`。

## FE / Aux Block 划分

real split 向量采用：

```text
[ real(FE, aux), imag(FE, aux) ]
```

因此 block PC 切片为：

| block | real split 行 |
|---|---|
| FE real | `0 : n_fe` |
| aux real | `n_fe : n_complex` |
| FE imag | `n_complex : n_complex + n_fe` |
| aux imag | `n_complex + n_fe : 2*n_complex` |

当前 profile 中 `P_aux=identity`。auto-propagating default100 case 有 708 个 complex aux unknowns；zero-order local Robin 分支没有 aux unknown，只作为定位对照。

## AMS 数据

same-H1 AMS 数据可以在 normal-incidence real PETSc mode 下稳定构造。为此本轮把 Floquet MPC 系数转换为当前 PETSc scalar type：complex-mode 保持复数；real-mode 只允许纯实相位，否则显式报错。

| case | B rows | B nnz | G rows | G cols / H1 dofs | G nnz | AMS setup RSS before -> after |
|---|---:|---:|---:|---:|---:|---:|
| tiny10 auto | 144 | 4,574 | 144 | 64 | 1,800 | 0.259 -> 0.261 GB |
| default100 auto | 39,270 | 1,307,032 | 39,270 | 13,671 | 667,340 | 0.683 -> 0.718 GB |
| default100 zero-order | 39,270 | 1,307,032 | 39,270 | 13,671 | 667,340 | 0.470 -> 0.670 GB |

官方 PETSc 文档也要求 AMS/ADS 提供离散梯度等 auxiliary data；本轮脚本按这个口径提供 `G` 和 edge constant vectors。

## Stage C：p=1 h=5 对比

| case | profile | status | iter | true relative residual | KSP residual | RSS | 判断 |
|---|---|---|---:|---:|---:|---:|---|
| tiny10 auto | Jacobi | converged | 39 | 8.817e-7 | 8.335e-6 | 0.259 GB | tiny case 太容易 |
| tiny10 auto | FE-AMS + aux identity | converged | 37 | 9.601e-7 | 9.076e-6 | 0.261 GB | 迭代少 2 步，但 residual 未优于 Jacobi |
| default100 auto | Jacobi | max_it | 1000 | 3.436e-2 | 3.199 | 0.683 GB | 不收敛 |
| default100 auto | FE-AMS + aux identity | max_it | 1000 | 2.147e-2 | 1.998 | 0.786 GB | residual 约 1.60x 改善，但远不到 10x，也未收敛 |
| default100 zero-order | Jacobi | max_it | 1000 | 4.397e-1 | 40.927 | 0.470 GB | local Robin 对照，不计入通过 |
| default100 zero-order | FE-AMS | max_it | 1000 | 5.337e-1 | 49.680 | 0.737 GB | 更差 |

Stage C 未通过。主 default100 auto-propagating case 只出现弱改善，且没有达到 `true_relative_residual_norm <= 1e-6`。

## True Residual 与 KSP Residual

所有判断使用：

```text
||A_real x - b_real|| / ||b_real||
```

KSP residual 与 true residual 数值不同，原因是 PETSc reported residual 是当前 KSP 口径下的残差范数，不等于本报告归一化 true residual。但排序一致：default100 auto 中 FE-AMS 的 KSP residual 和 true residual 都比 Jacobi 小；zero-order 对照中两者都更差。

## 内存判断

| case | real matrix loaded | after Jacobi | after FE-AMS | 主要增量 |
|---|---:|---:|---:|---|
| tiny10 auto | 0.258 GB | 0.259 GB | 0.261 GB | 几乎都来自矩阵和 Python/DOLFINx 基础开销 |
| default100 auto | 0.683 GB | 0.683 GB | 0.786 GB | AMS hierarchy + work vectors 约 0.10 GB |
| default100 zero-order | 0.463 GB | 0.470 GB | 0.737 GB | AMS setup 增量较明显 |

内存远低于 direct/BLR full p2 h2 的 17-20 GB 参考，但当前 PC 收敛不足，所以低内存本身不能作为成功。

## p=2 h=5 决策

未运行。原因是 Stage C 主 case 没有满足“明显优于 Jacobi”或 `<=1e-6` 的进入条件。继续硬跑 p2 h5 会违反本任务 gated execution，也可能制造无意义的大算例残差表。

## 是否进入 full Stage 4 p=2 h=2

不允许。当前最小 block PC 的结论是：

```text
real split: yes
MPC 后 same-H1 AMS data: yes
FE-AMS + aux identity as Stage4 PC: no / too weak
```

下一步应先做 DtN-aware block correction、aux Schur approximation 或 Rayleigh/Floquet modal deflation。

## 是否建议合并代码

不建议把本轮实验代码合并进 production solver。可以考虑 docs-only 合并，或者保留在研究分支供后续 task015 使用。
