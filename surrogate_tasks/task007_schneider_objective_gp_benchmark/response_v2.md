# Task007 Response V2：M3 Level-A continuous sequential BO

## 执行范围

已按 Review V1 的 M3 Level A 完成纯算法 benchmark。所有查询都来自冻结 Task006 Legendre-3 response model；本轮没有运行新的 FEM，没有访问或修改 Task006 frozen validation，也没有修改 Task006 model lock。实现 clean SHA 为 `555abf1`。

保留 Task007 V1 的全部结果和原始证据。尤其是 V1 的 P3 负结果仍标记为 `one_shot_offline_posterior_mean_not_qualified`：它只做一次 offline posterior-mean minimization，不是 Schneider-style continuous sequential BO，因此不得解释为 Schneider 方法失败。

## M3 实现

1. 固定 12 个不在 train37 中的 off-grid `(h,w)` targets；每个 target 为 J1/J0 两个独立 measurement contract 各生成一次 N1/N2 固定噪声。
2. 先在连续 `[115,125] nm × [16,18] nm` 域用 dense grid、确定性 bounded multistart L-BFGS-B 求每个 noisy oracle objective 的真实连续 MAP。48 个 MAP objective 均为正，没有把 hidden target 作为零值观测写入 GP。
3. 对 P0 cold5、P1 Sobol12、P2 Sobol37、P3 existing train37，每次循环执行 Matérn-5/2 ARD exact GP fit、连续 EI 优化、实际 oracle query、objective 记录和 GP update，最多 20 次 online query。EI 网格最大值低于 `1e-3` 时切换到 bounded local refinement。
4. 同时报告 B0 random continuous search 和 B1 bounded multistart local oracle baselines，并保存每个 query、best actually evaluated point、MAP tolerance、GP kernel/LML/warning/boundary metadata。

## 结果

主 J1 contract 的 Sobol37 continuous EI 通过两种噪声 Gate：

| 场景 | 命中 | median queries-to-MAP | p90 | max |
|---|---:|---:|---:|---:|
| J1/N1 | 12/12 | 3.0 | 4.8 | 5 |
| J1/N2 | 12/12 | 2.0 | 3.0 | 3 |

P1 Sobol12 在 J1/N1、J1/N2 也分别为 12/12；existing train37 的 sequential 对照为 9/12 和 10/12，作为 design comparison 保留，不提升为主方法。Secondary J0 的 P2 为 N1 `11/12`（controlled negative）和 N2 `12/12`；这些结果没有通过改 Gate 或调参修饰。

GP 审计共 1,361 次 update，选中 jitter `1e-10` 1,090 次、`1e-8` 271 次；selected-run warnings 2,028、boundary collisions 196、bounded local refinement 473，所有候选 LML 有限。独立 Case147 checker 重算 45,054 项，状态为 `pass`，`new_fem_count=0`。

## 证据与停止点

- 合同、冻结 identity 和 source hashes：`outcomes/M3_LEVEL_A_CONTRACT.json`、`outcomes/M3_IMPLEMENTATION_IDENTITY.json`。
- 连续 oracle、MAP、目标噪声和完整 BO trace：`outcomes/M3_ORACLE_MODEL_AUDIT.json`、`M3_MAP_AUDIT.json`、`M3_TARGETS.json`、`M3_BO_REPLAY.json`。
- 方法/GＰ审计：[M3_METHOD_COMPARISON.md](outcomes/M3_METHOD_COMPARISON.md)、[M3_GP_AUDIT.json](outcomes/M3_GP_AUDIT.json)、[summary_m3.md](outcomes/summary_m3.md)。
- 独立 checker：`benchmarks/cases/147_task007_m3_continuous_bo/records/case147_check.json`。

本轮到此停止，等待下一轮审阅；不得据此启动真实 FEM、Task006 重试、正式 Bayesian inversion 或修改 Task006 model lock。
