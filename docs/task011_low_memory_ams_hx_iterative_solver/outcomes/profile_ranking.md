# Profile Ranking

## 生产候选

目前没有新的低内存生产候选。

## 短期 fallback

`iter_fgmres_mumps_blr_eps1e-5` 仍是短期可运行 fallback。它来自 task010，不是本轮新增的真正低内存迭代法；本质仍依赖 MUMPS-BLR factorization。

## 本轮排序

| 排名 | 路线/Profile | 当前状态 | 关键数值 | 优点 | 问题 | 决策 |
|---:|---|---|---|---|---|---|
| 1 | real-imag split + real hypre AMS/HX | 未实现，证据最强 | real FE-only `p=2 h=5`：7 次迭代，true residual `4.024e-7` | 符合 H(curl) Maxwell 结构 | 需要 real block 化并接入 Stage 4 | 下一轮主线 |
| 2 | matrix-free FE action + AMS/HX | matvec 已验证 | complex `p=2 h=5` action error `7.56e-16` | 可降低 A 矩阵存储压力 | 尚未处理 MPC/DtN/KSP PC 集成 | real-split 收敛后再做 |
| 3 | `iter_gmres_jacobi_restart40` | 未收敛 | p=2 h=4 true residual `0.2343204328` | 低内存，p=1 有下降 | 离 `1e-6` 太远 | 不继续加密 |
| 4 | `iter_fgmres_jacobi_restart20` | 未收敛 | p=2 h=4 true residual `0.2351484757` | 低内存 | 离 `1e-6` 太远 | 不继续加密 |
| 5 | `iter_lgmres_jacobi_restart20` | 未收敛 | p=2 h=4 true residual `0.2471943132` | 低内存 | 不如 GMRES/FGMRES | 不继续加密 |
| 6 | `iter_tfqmr_jacobi` | 未收敛 | p=2 h=4 true residual `0.6682568382` | 内存低 | 残差下降差 | 放弃 |
| 7 | `iter_bicgstab_jacobi` | 发散 | p=2 h=4 true residual `2.1649273487` | 无明显优势 | 发散 | 放弃 |
| 8 | `iter_cgs_jacobi` | 硬发散 | p=2 h=4 true residual `1.4194e5` | 无 | 9 步即 `DIVERGED_DTOL` | 放弃 |

1. `real-imag split + real hypre AMS/HX`：未完成，但证据最强。real FE-only AMS 能在少量迭代内收敛，下一步应把 complex 系统拆成 real block。
2. `matrix-free FE action + AMS/HX preconditioner`：matvec 误差通过，但缺少 Stage 4 MPC/DtN 集成。
3. `iter_gmres_jacobi_restart40`：低内存但不收敛。p=2/h=4 true relative residual 为 `0.234320432830893`。
4. `iter_fgmres_jacobi_restart20`：低内存但不收敛。p=2/h=4 true relative residual 为 `0.23514847566593405`。
5. `iter_lgmres_jacobi_restart20`：低内存但不收敛。
6. `iter_tfqmr_jacobi`：残差下降差。
7. `iter_bicgstab_jacobi` 和 `iter_cgs_jacobi`：发散或硬发散，应移出后续搜索重点。

## 结论

不要继续在 Jacobi 上消耗时间。真正有希望的方向是 real-split AMS/HX block preconditioner；matrix-free 是后续内存优化层，不是收敛性答案本身。
