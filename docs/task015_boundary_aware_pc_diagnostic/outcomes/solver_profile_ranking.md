# Solver Profile Ranking

## 结论排名

| rank | profile | default100 true residual | improvement vs aux identity | decision |
|---:|---|---:|---:|---|
| 1 | FE-AMS + aux identity | 2.147e-2 | 1.00x | baseline，仍未通过 |
| 1 | FE-AMS + aux exact | 2.147e-2 | 1.00x | `A_aux` exact 无效 |
| 1 | FE-AMS + aux diag | 2.147e-2 | 1.00x | `A_aux` diag 无效 |
| 1 | FE-AMS + modal zero-order | 2.147e-2 | 1.00x | aux-space only，无效 |
| 1 | FE-AMS + modal propagating | 2.147e-2 | 1.00x | aux-space only，无效 |
| 6 | Jacobi | 3.436e-2 | 0.62x | baseline 较差 |
| 7 | FE-AMS + Schur_diag | 4.427e-1 | 0.048x | 明显变差，停止 |

## 解释

`FE-AMS + aux identity` 已把 FE residual 压低，但留下的 residual 几乎全部在 `top,(0,0),y` auxiliary mode。`aux exact/diag` 和 aux-space modal correction 都不改变 residual，说明问题不是 `A_aux` 自身，而是这个模态与 FE trace/volume 的耦合没有被 PC 捕获。

## 下一步优先级

| next candidate | priority | reason |
|---|---:|---|
| lifted zero-order FE+aux coarse correction | 高 | 直接打中 dominant residual mode |
| residual-dominant sampled Schur | 高 | 只需先处理 1-4 个 zero-order modes，不做 full 708 Schur |
| full Schur_diag | 低 | 已显著变差 |
| aux-only modal correction | 低 | 已证明等价于 aux identity |
| 继续黑盒 PETSc profile sweep | 低 | 不能解释 dominant modal residual |
