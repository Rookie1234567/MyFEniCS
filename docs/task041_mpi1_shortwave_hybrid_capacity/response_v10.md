# Task041 Review V7 进度快照

**不是结项。** 最近的G2c是显式三条顶部响应诊断；G2c的一修正策略未运行完整固定八项consumer、正式Schur、outer/RTA/EH或全场。V6历史fixed-eight组件结果另行保留，不与G2c策略资格混同。Q表示粗层校正，p4恢复回到原有限元自由度，A4是原方程残差检查。

## 已测结果

G1在列12/493/666上检查7个冻结PC节点、14次同输入Q。14次输入与PH输出都逐字节一致；Q差`4.4621e-11–5.2173e-11`，超过原`1e-11`限值，而所有physical/augmented A4低于原`1e-10`门。G1没有执行修正；根因仍未证明。G2r2对PC1的Q1/Q2做0/1/2步骤：step0 Q差分别`4.8268e-11`、`5.1937e-11`且A4门均通过；step1后分别降至`2.9155e-14`、`3.3070e-14`，step2保持通过。

G2c运行源码SHA为`c0a077212cc3dd0ed6989ba66ff44ca0a7cbce74`，仅覆盖顶部列12/493/666。三列`e_x/e_A`都低于原`1e-8`门；14个冻结Q回放、7个PC回放及共同A4门均通过。最大共同输入Q差`3.9961e-14`（限`1e-11`），PC差`3.8442e-14`（限`1e-8`），A4 physical/augmented最大`2.8028e-13`（限`1e-10`）。自由轨迹PC差`2.75725e-6`来自输入分叉，gate不适用。

| 代表响应 | `e_x/e_A` | 迭代 full/condensed | 响应 wall full/condensed |
|---|---:|---:|---:|
| 列12 | `1.43184e-9/3.88661e-9` | 57/57 | `290.461/329.031 s` |
| 列493 | `1.35854e-9/3.68755e-9` | 57/57 | `284.837/320.628 s` |
| 列666 | `1.86359e-13/9.03085e-14` | 17/17 | `84.999/95.603 s` |

三条响应 full 合计`660.297 s`、condensed`745.262 s`；本场凝聚慢`84.964 s`，不能宣称提速。524个P4调用中，521个step0的原physical和augmented A4门都通过，仍执行了单次修正；另3个仅physical略超限；524个step1均通过。因此“只在原A4门失败时修正”不适用。现有数据也不足以支持更严的新残差阈值。

G2c service正常完成、finalizer清场/检查通过、swap为0；authority/tree峰`42,588,479,488 B`，硬cap`53,221,163,008 B`。finalizer只追加一次`3315.690725968 s`，V5账本当前45条、`35847.63433988102 s`。用户允许隔离CPU并行，但本场与邻heavy并行，性能不作为无竞争资格。worker/public诊断检查通过，`qualification_pass=false`表示诊断尚未取得完整资格，不代表动作门失败。旧G1/G2r2负证据和r2原service exit3均保留。

## 下一步

优先评审一个G3局部热点：在`src/solvers/p4_cell_condensed_inverse.py`因子生命周期内缓存稳定的trace→active索引和owner/request通信计划；保留每次RHS必需的数据交换、LU求解和回代。三列现有缩减+恢复区间合计`84.002 s`只是理论节省上界，实际收益未知。先以已有fixture和serial/MPI2核对，不微基准、不跑FE。

修正策略继续显式opt-in；不采纳原A4失败才修正，也不推导新阈值。下一次数值资格工作需另行审核，不能把G2c三列外推为完整八项或正式全场通过。逐节点A4/Q/p4差、G2阶段表、资源及证据索引见[中心outcome](outcomes/causal_fix_5nm_v7.md)和[机器record](outcomes/records/task041_v7_causal_fix_5nm.json)。
