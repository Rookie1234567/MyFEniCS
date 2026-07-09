# Next Decision

## 推荐决策

进入 real-imag split AMS/HX prototype。

## 决策矩阵

| 选项 | 可用性 | 收敛证据 | 内存前景 | Stage 4 接入难度 | 风险 | 建议 |
|---|---|---|---|---|---|---|
| 继续 Jacobi-Krylov 加密到 h=3/2.5/2 | 已可运行 | p=2 h=4 仍停在 true residual `0.234` | 低 | 低 | 很可能继续不收敛 | 不推荐 |
| 直接 complex hypre AMS | 不安全 | 最小 p=1 h=10 段错误 | 理论上好 | 中 | PETSc/hypre complex 崩溃 | 禁止作为主线 |
| real-imag split + real AMS/HX | 需要实现 | real FE-only p=2 h=5 已收敛 | 好 | 中到高 | 需处理 block operator 和 DtN auxiliary | 推荐主线 |
| MUMPS-BLR eps=1e-5 | 已可运行 | task010 p=2 h=2 已通过 | 中等 | 低 | h=1.5 仍被 kill | 短期 fallback |
| matrix-free FE action | matvec 已验证 | 只验证算子动作 | 很好 | 高 | 不能单独解决收敛 | 作为第二阶段优化 |

## 原因

Jacobi-Krylov 已经覆盖 task011 指定 profile，在 p=2/h=5 和 h=4 上全部失败。它们证明了低内存 assembled A baseline 的内存优势，但没有给出可用 R/T/A。

real AMS/HX 在 FE-only positive Maxwell 上表现很好，说明 H(curl) auxiliary-space 预条件器路线正确。当前阻碍不是 AMS 理论不可行，而是 complex PETSc/hypre AMS 在这个 build 中会崩溃。

## 下一步建议

1. 新建 real block system 原型：将 complex 系统 `A = Ar + i Ai` 写成 `[[Ar, -Ai], [Ai, Ar]]`。
2. 对 real/imag 主对角块使用 real hypre AMS。
3. 先忽略或 diagonal 近似交叉块，测试 p=1/h=5 和 p=2/h=5。
4. 若收敛，再接入 Stage 4 DtN auxiliary 与 Floquet MPC。
5. 最后再考虑 matrix-free 化，减少 assembled A 内存。

## 暂停项

- 不继续测试 h=3/h=2.5/h=2 的 Jacobi profile。
- 不直接运行 complex `pc_hypre_type=ams` Stage 4 profile。
- 不把未收敛 Krylov 结果用于 official R/T/A。
