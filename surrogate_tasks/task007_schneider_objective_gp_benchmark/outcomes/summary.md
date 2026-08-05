# Task007 outcomes summary

## 范围与状态

Task007 M0–M2 已完成为 **stored-response replay benchmark**。本轮没有运行新 FEM，没有读取 Task006 frozen validation，没有修改 Task006 model lock，也没有进行正式代理部署或 Bayesian inversion。

GP 学习的是给定 synthetic measurement 对应的二维标量目标 `log10(F+1e-12)`，不是直接学习 Maxwell response。`B0` 是最近离线点，`B1` 是固定初始点的随机回放，`P0/P1/P2` 分别使用 5/12/37 个训练点的 Matérn-5/2 ARD exact-GP + expected improvement，`P3` 是连续域 posterior-mean MAP 诊断。

## 不可变身份

| 项目 | 身份 |
|---|---|
| branch | `codex/only-one-13p5nm-surrogate-inversion` |
| Task007 clean implementation SHA | `75e5cdb` (`Task007 objective GP replay implementation`) |
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| model / route | `S_PROD_FULL3D_STATIC_P5_H10_NY4` / `full3d_static_uniform_n1curl_p5_h10_ny4` |
| observable | `task002.fixed-n0-orders.v3` |
| train source | immutable Task006 train37；manifest SHA `f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84` |
| Task006 lock | `f08180f891b485a4ddedcf4066a2bed6a4164342fc0e296bfb06d2278469a7a1` |
| replay universe | 37 offline + 11 Case141 external = 48 complete geometries |
| excluded | `(117.5,17.25)`，A07/A09 不完整，未进入 replay |

J1 六通道按 A05/A07/A09 的 m=0 reflection/transmission `order_total_power=S+P` 展开；J0 使用同一照明顺序的 `R_total,T_total`。两种 contract 分开计算，不重复计数。N1/N2 只是冻结的 synthetic diagonal weighting，不代表实验协方差。

## 离散 replay 结果

在线查询数不计初始训练点，第一次 query 记为 1。表中 `runs` 为 11 个目标乘固定初始集合数，B1 为 100 repeats/target。

| contract | noise | method | targets | runs | hit fraction | median queries | p90 queries |
|---|---|---|---:|---:|---:|---:|---:|
| J1 | N1 | B0 nearest offline | 11 | 11 | 0 exact | — | — |
| J1 | N1 | B1 random | 11 | 1100 | 1.000 | 23 | 39 |
| J1 | N1 | P0 cold5 | 11 | 66 | 1.000 | 6 | 8 |
| J1 | N1 | P1 trained12 | 11 | 66 | 1.000 | 1 | 2 |
| J1 | N1 | P2 trained37 | 11 | 11 | 1.000 | 1 | 1 |
| J1 | N2 | B1 random | 11 | 1100 | 1.000 | 24 | 39 |
| J1 | N2 | P0 cold5 | 11 | 66 | 1.000 | 6 | 7.5 |
| J1 | N2 | P1 trained12 | 11 | 66 | 1.000 | 1 | 3 |
| J1 | N2 | P2 trained37 | 11 | 11 | 1.000 | 1 | 1 |
| J0 | N1 | B0 nearest offline | 11 | 11 | 0 exact | — | — |
| J0 | N1 | B1 random | 11 | 1100 | 1.000 | 23 | 39 |
| J0 | N1 | P0 cold5 | 11 | 66 | 1.000 | 6 | 8 |
| J0 | N1 | P1 trained12 | 11 | 66 | 1.000 | 1 | 2 |
| J0 | N1 | P2 trained37 | 11 | 11 | 1.000 | 1 | 1 |
| J0 | N2 | B0 nearest offline | 11 | 11 | 0 exact | — | — |
| J0 | N2 | B1 random | 11 | 1100 | 1.000 | 23 | 39 |
| J0 | N2 | P0 cold5 | 11 | 66 | 1.000 | 5.5 | 7.5 |
| J0 | N2 | P1 trained12 | 11 | 66 | 1.000 | 1 | 3 |
| J0 | N2 | P2 trained37 | 11 | 11 | 1.000 | 1 | 1 |

B0 的 11 个目标均没有 exact target hit；其 J1/N1 median best offline objective 为 `10.6995`（p90 `29.3652`），说明单纯离线最近点不能替代查询。P2 相对 B1 的中位查询数由 23–24 降至 1，但这是 48 点 replay 上的 synthetic benchmark，不是新 FEM 成本预测。

## readiness gates

- J1/N1 replay objective 唯一最小值：11/11，通过（每个目标 `F(x*)=0` 在 log floor 前）。
- P2 J1/N1 exact target ≤5 queries：11/11，通过；全部 ≤11：11/11，通过。
- P3 J1/N1 连续 MAP tolerance `|h-h*|≤0.25 nm, |w-w*|≤0.05 nm`：2/11，通过，**未通过**。这不是被删除或调参后的结果，保留为 controlled-negative。

P3 的完整失败证据保留在 `MAP_RECOVERY_SUMMARY.json`。J1/N1 的 11 个点如下（限值分别为 0.25 nm、0.05 nm）：

| target | MAP `(h,w)` nm | `|dh|` nm | `|dw|` nm | 结果 |
|---|---|---:|---:|---|
| (117.5,16.5) | (117.3007,16.5678) | 0.1993 | 0.0678 | fail: width |
| (117.5,16.75) | (117.8018,16.6851) | 0.3018 | 0.0649 | fail: height,width |
| (117.5,17.5) | (117.9864,17.3768) | 0.4864 | 0.1232 | fail: height,width |
| (118.75,16.5) | (118.9698,16.4655) | 0.2198 | 0.0345 | pass |
| (118.75,17.5) | (119.4452,17.4641) | 0.6952 | 0.0359 | fail: height |
| (121.25,16.5) | (120.6807,16.5190) | 0.5693 | 0.0190 | fail: height |
| (121.25,17.5) | (121.1341,17.5302) | 0.1159 | 0.0302 | pass |
| (122.5,16.5) | (122.0837,16.6110) | 0.4163 | 0.1110 | fail: height,width |
| (122.5,16.75) | (122.1078,16.7337) | 0.3922 | 0.0163 | fail: height |
| (122.5,17.25) | (122.2168,17.3229) | 0.2832 | 0.0729 | fail: height,width |
| (122.5,17.5) | (122.6038,17.4426) | 0.1038 | 0.0574 | fail: width |

P3 J1/N2、J0/N1、J0/N2 也分别为 0/11、2/11、0/11；详细 p90/max 见 `METHOD_COMPARISON.md` 和 `MAP_RECOVERY_SUMMARY.json`。

## GP 审计与独立 checker

使用确定性 8 个优化初值、jitter 候选 `1e-10/1e-8`，并仅用当前训练 objective 的 LML 选择 jitter。共 2022 次 fit；全部 LML 有限；记录了 1626 个 optimizer warnings 和 1558 个 boundary collisions，没有静默丢弃。

独立 checker 从 train37 数组和 Case141 原始 JSON 重新提取 J1/J0、重算 objective/hash、检查 initial leakage、query 顺序与 revealed truth、P3 误差和 Task006 identity。`records/case146_check.json` 的 checker status 为 `pass`；其中 qualification 明确为 `controlled_negative_p3_map`，不能解释为正式 surrogate 资格通过。

完整证据索引：`SCHNEIDER_METHOD_TRANSLATION.md`、`REPLAY_DATA_INVENTORY.json`、`REPLAY_TARGETS.json`、`OBJECTIVE_CONTRACT.json`、`OBJECTIVE_IDENTITY_AUDIT.json`、`OBJECTIVE_GP_MODEL_AUDIT.json`、`BAYESIAN_OPTIMIZATION_REPLAY.json`、`MAP_RECOVERY_SUMMARY.json`、`METHOD_COMPARISON.md`、`test_summary_v1.md` 和 `../response_v1.md`。
