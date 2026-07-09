# Solver Profile Ranking

## 排名表

| 排名 | profile / auxiliary | 证据 | 优点 | 问题 | 决策 |
|---:|---|---|---|---|---|
| 1 | real-split AMS, H1 degree=p | p2 h5 310 iter, true residual `9.964e-7`, RSS `1.323 GB` | 本轮唯一 p2 h5 收敛且低内存 | 迭代数高，仍是 FE-only | 下一轮进入 reduced Stage 4 block PC |
| 2 | real-split AMS, H1 degree=p+1 | p2 h10 219 iter converged；p2 h5 150 iter `8.004e-6` | 理论上更接近 task011 standard AMS | p2 h5 RSS `6.306 GB`，慢 | 不作为主线 |
| 3 | Jacobi baseline | p2 h5 150 iter `7.605e-6`，RSS `1.08 GB` | 极便宜 | p2 h10 1000 步失败，泛化差 | 仅作 baseline |
| 4 | real-split AMS, H1 degree=1 | p2 h5 50 iter `7.764e-5` | setup 很便宜 | 预条件太弱 | 放弃主线 |
| 5 | full Stage 4 real-split | 未运行 | 目标路线 | 需要 MPC/DtN FE/aux block 集成 | 下一任务，不在本轮合并 |

## 与任务书成功标准对照

| 标准 | 结果 | 是否满足 |
|---|---|---|
| Stage A relative matvec error <= 1e-12 | 所有 case 约 `1e-16` | 是 |
| p2 h5 true residual <= 1e-6 | same-H1 310 iters `9.964e-7` | 是 |
| RSS 明显低于 BLR 17.85 GB | same-H1 p2 h5 `1.323 GB` | 是 |
| 无 hypre signal 11 | real mode 全部未崩溃 | 是 |
| full Stage 4 p2 h2 R/T/A 对齐 | 未运行 | 否 |

## 结论

本轮 solver profile 排名给出 B 档继续研究结论：

```text
real-split AMS/HX + same-H1 auxiliary 值得继续；
standard-H1 AMS 内存不理想；
linear-H1 太弱；
Jacobi 不能作为可靠路线；
full Stage 4 集成必须另开 gated task。
```
