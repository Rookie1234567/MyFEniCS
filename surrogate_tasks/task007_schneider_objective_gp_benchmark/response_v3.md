# Task007 Response V3：M4A robustness and independence closeout

## 执行边界

已执行 Review V2 的 Required M4A，`new FEM = 0`。本轮没有运行 Task006 retry、Full3D online pilot、正式 Bayesian inversion 或参数扩展；Task006 lock、train37 manifest、Task007 V1 和 M3 artifacts 均保持 hash-bound 不变。

M4A clean implementation SHA：`34d52d075842f177f2c055f8f0ef5cdf48d63d67`。

## 已完成的审计

1. **独立 MAP stability**：对全部 48 个 target/contract/noise 组合使用 Differential Evolution + bounded L-BFGS-B polish。48/48 满足 objective Gate 和 `dh/dw` Gate，未发现 objective-equivalent 坐标多极小值。
2. **Standalone acquisition replay**：对 J1/P2 的 24 条 M3 trajectories，从 initial `(x,F)` 独立重拟合 ExactARDGP，重新最大化连续 EI，并重新执行低 EI local refinement。24/24 的 query geometry、EI、mode、objective、final best 与 stored trace 一致。它是 acquisition audit，不宣称第二套物理 oracle。
3. **Response-blind stopping**：冻结 `EI < 1e-3` 两次且最好 log-objective improvement `<1e-3` 三次的停止合同，最多 20 次；运行时不访问 hidden MAP，结束后才评分。
4. **Noise Monte Carlo**：J1 的 12 targets、N1/N2、每组 10 个新确定性 seed，P1/P2 共 240 个 measurement realization；保存每个 seed、measurement hash、MAP 和 query 结果。
5. **Initialization cost**：只比较 I0 existing train37、I1 Sobol12、I2 Sobol37、I3 train37+Sobol6、I4 train37+Sobol12，分开记录 initial response count、online query 和相对 train37 的新增三照明 FEM 数。
6. **GP warning taxonomy**：从 M3 全部 1,361 updates 重拟合，按 method、contract/noise、observed count、jitter、kernel 参数和 warning category 分组；不改变 kernel bounds。

## 结果与 controlled negatives

MAP stability 和 acquisition replay 均通过。response-blind readiness 只有 P2/N2 通过；P1/N1、P1/N2、P2/N1 的具体结果保留为负结果：

| method/noise | MAP hit | median queries | p90 | Gate |
|---|---:|---:|---:|---|
| P1/N1 | 12/12 | 20.0 | 20.0 | controlled negative |
| P1/N2 | 11/12 | 10.5 | 15.9 | controlled negative |
| P2/N1 | 12/12 | 11.0 | 14.9 | controlled negative |
| P2/N2 | 12/12 | 7.0 | 8.0 | PASS |

10-seed Monte Carlo 的 P1/N1、P2/N1 也因 N1 query-cost Gate 为 controlled negative；P1/N2、P2/N2 通过。没有删除失败 realization、提高掠射角/容差、改变停止规则或调参直到通过。

## 解释与停止

M4A 证明了 M3 reference MAP 和 acquisition trace 的数值稳定性，并量化了 noise/stopping/initialization 成本；它仍是同一 Legendre-3 oracle 内的 self-consistent benchmark，不能替代独立 Full3D/FEM 物理验证。Case148 checker 通过不等于代理资格或反演授权。

Task007 V1 的 one-shot posterior-mean P3 负结果保持 `one_shot_offline_posterior_mean_not_qualified`，不得解释为 Schneider 方法失败。M4A 完成后停止，等待 Review V3；在此之前不运行任何 FEM 或正式反演。

证据总览见 [outcomes/summary_m4a.md](outcomes/summary_m4a.md)，独立 checker 见 `benchmarks/cases/148_task007_m4a_robustness/records/case148_check.json`。
