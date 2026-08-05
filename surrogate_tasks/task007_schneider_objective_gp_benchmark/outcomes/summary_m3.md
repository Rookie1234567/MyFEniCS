# Task007 M3 Level-A outcomes summary

## 结论

本轮是纯算法 benchmark，不运行新的 FEM，也不修改 Task006 model lock。连续 oracle 是冻结的 Task006 `legendre_3` response model；实现和证据绑定 clean implementation `555abf1`。独立 Case147 checker 通过，45,054 项重算检查全部为真。

M3 的主要问题是验证真正的 Schneider-style continuous sequential BO：每轮重新拟合 GP、在连续二维域优化 EI、调用 oracle 获得实际 objective、更新 GP，再以实际已查询点中的最好点和进入 oracle MAP 容差所需 query 数评价。EI 网格最大值低于 `1e-3` 时按冻结规则切换 bounded local posterior-mean refinement。

## 主 Gate 与比较

容差为 `|h-h_MAP| <= 0.25 nm`、`|w-w_MAP| <= 0.05 nm`；每种组合包含 12 个 off-grid target。主方法为 `P2_sobol37`，即使用 37 个固定 Sobol 几何的 objective 初始化，而不是把隐藏 target 提前放入 GP。

| objective | noise | 初始化/方法 | MAP 命中 | median queries | p90 | max | Gate |
|---|---|---|---:|---:|---:|---:|---|
| J1 | N1 | P2 Sobol37 continuous EI | 12/12 | 3.0 | 4.8 | 5 | PASS |
| J1 | N2 | P2 Sobol37 continuous EI | 12/12 | 2.0 | 3.0 | 3 | PASS |
| J0 | N1 | P2 Sobol37 continuous EI | 11/12 | 3.0 | 5.0 | 6 | controlled negative |
| J0 | N2 | P2 Sobol37 continuous EI | 12/12 | 2.0 | 4.9 | 19 | PASS |
| J1 | N1 | P1 Sobol12 continuous EI | 12/12 | 5.5 | 7.9 | 8 | PASS |
| J1 | N2 | P1 Sobol12 continuous EI | 12/12 | 5.0 | 6.0 | 18 | PASS |

`J1` 是主 measurement contract（3 个照明下的 m=0 reflection/transmission order-total power）；`J0` 是独立 aggregate R/T secondary contract，二者没有在同一个 objective 中重复计数。J0/N1 的 11/12 是保留的 secondary negative，不调整 noise、target、容差或方法来掩盖它。

## Existing train37、冷启动和基线

| 方法 | J1/N1 | J1/N2 | 解释 |
|---|---:|---:|---|
| P3 existing train37 continuous EI | 9/12，median 7.0 | 10/12，median 3.5 | 报告为 design comparison；不是主 Gate |
| P0 cold5 continuous EI | 8/12，median 8.5 | 11/12，median 10.0 | 仅作冷启动基线 |
| B0 random continuous search | 2000 次 oracle eval | 2000 次 oracle eval | 不是高效 BO 方法 |
| B1 bounded multistart local | median 847.5 次 | median 550.5 次 | 说明连续局部优化的 oracle 成本 |

V1 的 one-shot offline posterior-mean P3 结果仍保留原文件和原负结果；它没有执行连续 EI、online oracle query 或 GP update，因此不能称作 Schneider method failure。本轮 P3 名称仅表示 existing-train37 初始化的 sequential EI 对照。

## GP、MAP 与 provenance 审计

- 48 个 target/contract/noise 组合的 oracle MAP objective 均为正（未强制为零）；固定 N1/N2 噪声由 seed 复现。
- Matérn-5/2 ARD、constant mean、8 个确定性优化初值；jitter `[1e-10, 1e-8]` 仅按 training-only LML 选择。
- 1,361 次 sequential GP update；记录 2,028 个 selected-run warnings、196 个 boundary collisions 和 473 次 bounded local refinement。LML 候选均为有限值，warning 没有静默丢弃。
- Task006 model lock SHA `f08180f891b485a4ddedcf4066a2bed6a4164342fc0e296bfb06d2278469a7a1`、train37 manifest SHA `f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84` 和 forward SHA `fdf961545f217d620e22800f2704ae9913a6d270` 均未改变。
- `new_fem_count = 0`；Task006 failed points 未重试；没有修改 Task006 model lock。

## 证据索引

- 合同与身份：[M3_LEVEL_A_CONTRACT.json](M3_LEVEL_A_CONTRACT.json)、[M3_IMPLEMENTATION_IDENTITY.json](M3_IMPLEMENTATION_IDENTITY.json)
- oracle/MAP/targets：[M3_ORACLE_MODEL_AUDIT.json](M3_ORACLE_MODEL_AUDIT.json)、[M3_MAP_AUDIT.json](M3_MAP_AUDIT.json)、[M3_TARGETS.json](M3_TARGETS.json)
- 全部 BO traces：[M3_BO_REPLAY.json](M3_BO_REPLAY.json)、[M3_GP_AUDIT.json](M3_GP_AUDIT.json)、[M3_METHOD_COMPARISON.md](M3_METHOD_COMPARISON.md)
- 独立 checker：[case147_check.json](../../../benchmarks/cases/147_task007_m3_continuous_bo/records/case147_check.json)
- 复现命令：[test_command.txt](../../../benchmarks/cases/147_task007_m3_continuous_bo/test_command.txt)
