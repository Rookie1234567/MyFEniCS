# Task004 M4C training-only CV

CV 使用同一份不可变 train96、固定 `FOLD_SEED=20260731` 的 space-filling 5-fold，未读取 validation。Aggregate 采用 `zR=log((R+eps)/(A+eps))`、`zT=log((T+eps)/(A+eps))`，再以 `softmax(zR,zT,0)` 恢复 R/T/A；每个 GP 折保存 8 个确定性优化初值、fitted kernel、LML、边界碰撞和 warnings。

本轮选择诊断分数最低的 production GP `gp:F3, jitter=1e-6` 作为失败结果的代表；它并未被标记为 qualified。

| Gate | 结果 | 主要证据 |
|---|---:|---|
| aggregate | FAIL | `A_balance` NRMSE=0.04139、p95=0.02466、max=0.14322；`R_total` max=0.14197；`T_total` p95=0.01437 |
| local spatial windows | FAIL | cutoff-near p95：R=0.04861、A=0.04718；high-azimuth p95：T=0.07421、A=0.09901 |
| composition | PASS | softmax reconstruction error ≤1e-12 |
| cross-fitted uncertainty | PASS | R/T/A coverage = 0.9271/0.9583/0.9479；每个 target 独立 factor |
| power end-to-end | FAIL | side ledger=2.22e-16、mask=100%，但 primary channel accuracy 未达 NRMSE≤0.03 和 p95≤0.01 |
| training_gate | FAIL | 不创建 model lock |

F1、F2、F3 及三种 jitter 的完整数值、逐点 OOF truth/prediction/std/error/fold、signed cutoff order/margin、overlapping region、spatial-window membership 和实际 fold-training 距离见同目录 `training_cv.json` 与 `training_cv_oof.json`。当前最优 GP 的 score 仍高于 local-RBF baseline（4.9507 对 4.4861），所以不满足主动学习资格：本轮不运行 16 个新 FEM，也不运行 blind validation。
