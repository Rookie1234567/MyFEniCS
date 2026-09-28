# Task041 Review V7 进度快照

**不是结项。** 最近的G2c是显式三条顶部响应诊断；G2c的一修正策略未运行完整consumer、正式Schur、outer/RTA/EH或全场。随后G2d已在分开的bottom与top运行中覆盖固定manifest八项并通过原配对门；这不证明单个完整consumer同时持有两侧时的资源或全场资格。Q表示粗层校正，p4恢复回到原有限元自由度，A4是原方程残差检查。

## 已测结果

G1在列12/493/666上检查7个冻结PC节点、14次同输入Q。14次输入与PH输出都逐字节一致；Q差`4.4621e-11–5.2173e-11`，超过原`1e-11`限值，而所有physical/augmented A4低于原`1e-10`门。G1没有执行修正；根因仍未证明。G2r2对PC1的Q1/Q2做0/1/2步骤：step0 Q差分别`4.8268e-11`、`5.1937e-11`且A4门均通过；step1后分别降至`2.9155e-14`、`3.3070e-14`，step2保持通过。

G2c运行源码SHA为`c0a077212cc3dd0ed6989ba66ff44ca0a7cbce74`，仅覆盖顶部列12/493/666。三列`e_x/e_A`都低于原`1e-8`门；14个冻结Q回放、7个PC回放及共同A4门均通过。最大共同输入Q差`3.9961e-14`（限`1e-11`），PC差`3.8442e-14`（限`1e-8`），A4 physical/augmented最大`2.8028e-13`（限`1e-10`）。自由轨迹PC差`2.75725e-6`来自输入分叉，gate不适用。

| 代表响应 | `e_x/e_A` | 迭代 full/condensed | 响应 wall full/condensed |
|---|---:|---:|---:|
| 列12 | `1.43184e-9/3.88661e-9` | 57/57 | `290.461/329.031 s` |
| 列493 | `1.35854e-9/3.68755e-9` | 57/57 | `284.837/320.628 s` |
| 列666 | `1.86359e-13/9.03085e-14` | 17/17 | `84.999/95.603 s` |

三条响应 full 合计`660.297 s`、condensed`745.262 s`；本场凝聚慢`84.964 s`，不能宣称提速。524个P4调用中，521个step0的原physical和augmented A4门都通过，仍执行了单次修正；另3个仅physical略超限；524个step1均通过。因此“只在原A4门失败时修正”不适用。**G2c阶段**没有据此提出更严的内部残差阈值。后续已实现并分侧验证`5e-13`内部精化目标，最多修正两次；原最终A4门`1e-10`不变。

G2c 收口时 ledger 为45条、`35847.63433988102 s`；当场 finalizer 追加`3315.690725968 s`。G2c 与邻 heavy 并行，性能不作为无竞争资格。worker/public 诊断检查通过，`qualification_pass=false`表示诊断尚未取得完整资格，不代表动作门失败。旧 G1/G2r2 负证据和 r2 原 service exit3 均保留。

G2d 的 bottom/top 分别运行四项 target 诊断，合计覆盖固定manifest八项，八项原配对门均通过。Bottom 四响应的`e_x`约`1.19e-13–6.55e-13`；原 service exit3 的策略声明误判保留，后续只读合同复核25项通过。Top 四响应`e_x`均不高于`4.367853753649037e-10`，public/service exit0且25项检查通过。两次运行身份与检查文件分别记录；分侧覆盖不等于单个完整consumer同时持有两侧的资源资格或全场资格。已推送的正式5nm cell-condensed target入口修复在源码`c5f95db7f7c2c640b666035a1949f9dc666f4da4`。

## 2026-09-28：13.5 nm registered cell-condensed 终态

源码`c5f95db7f7c2c640b666035a1949f9dc666f4da4`下，13.5 nm/M120 registered cell-condensed consumer 自然完成、worker与service exit0；数值与物理门通过。实测`R/T/A/A_volume=0.3656257890944995/0.012990632409140064/0.6213835784963604/0.6213835794981195`，closure`1.001759120100587e-9`，5项真实残差均过门；复用旧 producer、consumer 内QEP调用0。本场未使用5e-13 target。

运行中首次出现共享主机 global swap 增`286720 B`、pswpout增70页；当时 worker group仍存活。Task041/job/cgroup swap为0，峰值authority/tree`8910348288 B`、cgroup`6212177920 B`，低于53,221,163,008 B硬cap；但零global增量合同未通过，来源归因未知。作业自然退出，不曾人工停止。Finalizer 10项检查全真，wall`2269.036298547 s`；V5 ledger共54条、累计`45194.90092220603 s`。原始证据与V1 compact保留；tracked record绑定修正后的producer manifest路径/hash。

## 下一步

下一项先审核现有`src/runners/task041_supervisor.py`中`_run_phase`：复用采样记录已有的`global_swap_used_bytes_delta`、`global_pswpin_pages_delta`、`global_pswpout_pages_delta`，在现有 job-swap 停止条件处纳入原零增量资源门；样本先写入`memory_stages.jsonl`，再判断停止。最小测试扩展`src/test/test_344_task041_public_supervisor.py`中的`test_phase_resource_limits_terminate_the_child`及`test_phase_cgroup_only_swap_is_authoritative`，验证零增量继续、任一正增量触发既有受控停止与原分类。当前只提出方案，未改源码/重跑。

完整5nm consumer、正式Schur、outer/RTA/EH仍未运行。逐节点数值、G2阶段表、资源与证据索引见[中心outcome](outcomes/causal_fix_5nm_v7.md)和[机器record](outcomes/records/task041_v7_causal_fix_5nm.json)。
