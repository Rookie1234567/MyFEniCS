# Outcome Summary

## Task

Task011 的目标是继续寻找不依赖 global LU / MUMPS-BLR 的可用迭代求解器路线。本轮重点验证三件事：轻量 Jacobi-Krylov 是否能给出 Stage 4 R/T/A，hypre AMS/HX 在当前 DOLFINx/PETSc 环境中是否可用，以及 matrix-free matvec 是否值得作为后续降内存方向。

## Branch

`codex/20260707-low-memory-ams-hx-iterative-solver`

## Changed Files

见 `changed_files.md`。本轮新增低内存 Krylov profile、FE-only AMS/HX 烟测脚本、matrix-free matvec 烟测脚本，并补充 matrix-scale CSV 字段与 profile 单元测试。

## Run Commands

核心命令记录见 `run_log.txt`。本轮主要运行：

- Stage A：`p=2, h=5/4, np=8`，7 个 Jacobi-Krylov profile。
- 补充 sanity：`p=1, h=5, np=8`，4 个相对较好的 Jacobi-Krylov profile。
- AMS/HX：real mode 下 FE-only positive Maxwell，`p=1 h=10`、`p=1 h=5`、`p=2 h=5` 成功。
- AMS/HX：complex mode 下最小 `p=1 h=10` 复现 PETSc/hypre 段错误。
- Matrix-free：complex mode 下 `p=1/2 h=5`，验证 UFL action matvec 与 assembled matrix matvec 一致。

## Physical Model

Stage A 使用 task008/task010 的 Stage 4 block grating 设置：`period_x=50 nm`、`period_y=25 nm`、`substrate=10 nm`、`grating_height=120 nm`、`air_height=130 nm`、`lambda0=13.5 nm`、`theta=80 deg`、`s` 偏振、DtN port auxiliary 装配、基座和光栅复折射率 `0.999002304859+0.00182649365j`。

AMS/HX smoke 和 matrix-free smoke 使用同尺寸 FE-only positive Maxwell 块，目的是验证预条件器和算子动作，不输出 official R/T/A。

## Numerical Settings

Stage A profiles：

- `iter_gmres_jacobi_restart20`
- `iter_gmres_jacobi_restart40`
- `iter_fgmres_jacobi_restart20`
- `iter_lgmres_jacobi_restart20`
- `iter_tfqmr_jacobi`
- `iter_bicgstab_jacobi`
- `iter_cgs_jacobi`

共同设置：`rtol=1e-6`、`atol=1e-12`、`max_it=1000`、`pc_type=jacobi`。

## Comparison Tables

### Stage A 低内存 Krylov 总览

| Profile | p | h (nm) | KSP/PC | 迭代 | 结论 | true relative residual | RSS upper (GB) | 是否允许 R/T/A |
|---|---:|---:|---|---:|---|---:|---:|---|
| `iter_gmres_jacobi_restart20` | 2 | 5 | GMRES/Jacobi, restart 20 | 1000 | 未收敛 | 0.3038503501 | 2.742 | 否 |
| `iter_gmres_jacobi_restart20` | 2 | 4 | GMRES/Jacobi, restart 20 | 1000 | 未收敛 | 0.2688494509 | 3.275 | 否 |
| `iter_gmres_jacobi_restart40` | 2 | 5 | GMRES/Jacobi, restart 40 | 1000 | 未收敛 | 0.2494949774 | 2.647 | 否 |
| `iter_gmres_jacobi_restart40` | 2 | 4 | GMRES/Jacobi, restart 40 | 1000 | 未收敛但本组最好 | 0.2343204328 | 3.284 | 否 |
| `iter_fgmres_jacobi_restart20` | 2 | 5 | FGMRES/Jacobi, restart 20 | 1000 | 未收敛 | 0.2814752157 | 2.648 | 否 |
| `iter_fgmres_jacobi_restart20` | 2 | 4 | FGMRES/Jacobi, restart 20 | 1000 | 未收敛 | 0.2351484757 | 3.243 | 否 |
| `iter_lgmres_jacobi_restart20` | 2 | 5 | LGMRES/Jacobi, restart 20 | 1000 | 未收敛 | 0.2772788903 | 2.643 | 否 |
| `iter_lgmres_jacobi_restart20` | 2 | 4 | LGMRES/Jacobi, restart 20 | 1000 | 未收敛 | 0.2471943132 | 3.258 | 否 |
| `iter_tfqmr_jacobi` | 2 | 5 | TFQMR/Jacobi | 1000 | 未收敛 | 0.7776431766 | 2.644 | 否 |
| `iter_tfqmr_jacobi` | 2 | 4 | TFQMR/Jacobi | 1000 | 未收敛 | 0.6682568382 | 3.276 | 否 |
| `iter_bicgstab_jacobi` | 2 | 5 | BiCGStab/Jacobi | 1000 | 发散 | 5.9137648049 | 2.675 | 否 |
| `iter_bicgstab_jacobi` | 2 | 4 | BiCGStab/Jacobi | 1000 | 发散 | 2.1649273487 | 3.242 | 否 |
| `iter_cgs_jacobi` | 2 | 5 | CGS/Jacobi | 9 | 硬发散 | 352477.7694596985 | 2.640 | 否 |
| `iter_cgs_jacobi` | 2 | 4 | CGS/Jacobi | 9 | 硬发散 | 141940.3211343898 | 3.275 | 否 |

### AMS/HX 烟测总览

| 模式 | 测试 | p | h (nm) | 迭代 | true relative residual | RSS upper (GB) | 结论 |
|---|---|---:|---:|---:|---:|---:|---|
| real | FE-only positive Maxwell | 1 | 10 | 3 | 1.8962457516e-7 | 0.428 | 可收敛 |
| real | FE-only positive Maxwell | 1 | 5 | 4 | 4.0339860323e-8 | 0.991 | 可收敛 |
| real | FE-only positive Maxwell | 2 | 5 | 7 | 4.0244411713e-7 | 6.930 | 可收敛 |
| real | FE-only positive Maxwell | 2 | 4 | 未完成 | 无 | 12.86 GiB Docker 占用 | 资源压力，已停止 |
| complex | FE-only positive Maxwell | 1 | 10 | 未完成 | 无 | 无 | PETSc/hypre AMS 段错误 |

### 候选路线对比

| 路线 | 是否真正低内存 | 是否收敛 | 是否能给 Stage 4 R/T/A | 当前证据 | 本轮决策 |
|---|---|---|---|---|---|
| Direct LU | 否 | 是 | 是 | task008 `p=2 h=2` reference | 保留作 reference |
| MUMPS-BLR `eps=1e-5` | 部分降低 | 是 | 是 | task010 `p=2 h=2` 与 direct 一致 | 短期 fallback |
| Jacobi-Krylov | 是 | 否 | 否 | 本轮 p=2 h=5/h=4 全失败 | 停止继续加密 |
| real hypre AMS/HX | 可能 | 是，FE-only | 尚未接入 Stage 4 | real `p=2 h=5` 7 次收敛 | 下一步核心路线 |
| complex hypre AMS/HX | 理论上可能 | 否 | 否 | 最小 complex smoke 段错误 | 不直接使用 |
| matrix-free FE action | 是 | 只验证 matvec | 否 | p=2/h=5 action error `7.56e-16` | 作为后续内存优化 |

## Key Results

没有找到可以直接用于 Stage 4 official R/T/A 的纯 Jacobi-Krylov 求解器。p=2 的 h=5/h=4 全部失败，最佳 true relative residual 仍为 `0.234320432830893`，对应 `iter_gmres_jacobi_restart40, h=4`。p=1/h=5 的补充 sanity 最佳为 `7.056576750190423e-05`，仍未达到 `1e-6`。

real mode 的 hypre AMS/HX 是本轮最有价值信号：FE-only positive Maxwell 在 `p=2 h=5` 用 7 次迭代达到 true relative residual `4.0244411713016064e-07`。但是 complex mode 直接使用 hypre AMS 会触发 `malloc(): invalid size` 和 PETSc signal 11，因此不能把 complex AMS 直接作为 Stage 4 profile。

## Energy Check

Stage A 未收敛，因此未允许 official R/T/A。所有失败行的 `R_total/T_total/A` 保持空值，避免误把不收敛结果当物理结果。

## Mesh / DoF / Solver Cost

低内存 Jacobi-Krylov 的 RSS upper 很低：p=2/h=4 约 `3.24-3.28 GB`，但不收敛。real AMS/HX 的 p=2/h=5 FE-only 烟测 RSS upper 约 `6.93 GB`，p=2/h=4 在 17 分钟后达到 `12.86 GiB / 13.65 GiB` Docker 内存占用，被停止并记录为资源压力。

matrix-free matvec 的 p=2/h=5 relative action error 为 `7.563218028818796e-16`，说明 FE 块的 UFL action 路线数值上可行。

## Known Issues

- 当前 PETSc/hypre AMS 在 complex mode 下不安全，最小 `p=1 h=10` 即崩溃。
- Jacobi-Krylov 只能作为低内存失败基线，不是可用求解器。
- Stage 4 blockdiag AMS profile 未运行，因为直接 complex AMS 已被最小烟测否定。
- matrix-free 目前只验证 FE-only 正定 Maxwell 块，还未覆盖 Floquet MPC 和 DtN auxiliary 增广系统。

## Next Questions for Review

建议下一轮不要继续调 Jacobi。最合理路线是实现 real-imag split 的 Stage 4 预条件器：把 complex Maxwell 系统转为 real block 形式，对 real/imag 两个 H(curl) 块使用 real hypre AMS，交叉项先用 identity 或 diagonal approximation。短期可继续使用 task010 的 `iter_fgmres_mumps_blr_eps1e-5` 作为可运行 fallback。
