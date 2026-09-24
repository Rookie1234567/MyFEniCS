## Review V26 / V28 融合 A6：修复后正式验证完成，修复前负结果保留

获准的一次修复后 V28 正式运行在990个 cells、p6/h7.5、80个 DtN 通道、MPI1/thread1下完成126步；worker exit0，独立显式真残差 `9.283164917015627e-7`，低于 `1e-6`，分类 `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`。同 R2 离散场的 full FE `L2/scaled-curl` 相对差为 `2.38e-14/8.92e-14`，80通道、模态功率、E/H/curl 导出均通过。workflow monotonic/conservative realtime budget=`2936.076242/3203.447880 s`，R2相同口径=`3114.283620/3407.555410 s`；此单次观察分别短 `5.72%/5.99%`，不能单独证明因果加速。R2 保留为本轮比较分母；ordinary default 不变。

修复后进程树 RSS/PSS peak=`7,356,289,024/7,324,145,664 B`，10,901个样本、PSS全可读、swap=0。累计账本 `3902.9635367376695 s` 包含前面受控停止/失败与本次修复后正式运行，**不是单次求解时间**。完整分项和逐16步展示见 [V28 outcome](fused_operator_speed_v28.md) 与 [post-repair compact](records/fused_operator_speed_v28_post_repair_compact.json)。

修复前唯一 worker 在 KSP 前遇到 retained-inventory `KeyError` 的失败及更早启动/停止记录保持原分类、成本和 raw evidence，见下面历史段落及原 [compact](records/fused_operator_speed_v28_compact.json)。当前修复后运行已完成；任何进一步 PDE 仍需新的明确授权。

## V28 修复前正式回归在 KSP 前失败（历史负结果，原样保留）

组件保存向量试验支持 A6 fusion-only 进入正式候选；H6 shared-contraction 增量未采用，两线程未试。唯一正式输入在 p4 factor/H6 setup 后、KSP 第1步前遇到 fused retained-inventory `KeyError`，分类为 `WORKER_FAILED`，不是离散不收敛。没有新残差、用户要求的16步更新点或任务合同的每8步 residual/每32步 field checkpoint、KSP/full-workflow 性能、最终场或 R/T/A。部分失败流程进程树 RSS/PSS=`6,569,861,120/6,537,753,600 B`、swap=0，不代表完整峰值或内存收益。

最小 owner-inventory/temporary-budget 修复提交 `f403cf126817a9019d2be59df6b2be6fc0d6bffd`，三个 task-focused 文件 `15 passed`。当时该修复尚无 fresh PDE 证据；此后的一次获准 post-repair 验证通过，已在本节开头单独登记。原始失败成本和分类不改写；R2继续作为这次结果的比较分母，ordinary default 不变。进一步 fresh regression 需新授权。

逐阶段负结果、两个未进入 worker/KSP 的启动记录、保留成本、历史 p4 baseline 与 raw artifact hashes 见 [V28 outcome](fused_operator_speed_v28.md)、[Response V29](../response_v29.md)、[compact](records/fused_operator_speed_v28_compact.json)、[decision](records/fused_operator_speed_v28_decision.json) 和 [selective merge manifest](selective_merge_manifest_v28.md)。测试细目见 [test summary](test_summary.md) 与 [run index](records/run_index.json)。旧 V27/V26 结果保持原样。

## V27 working-set / p6 setup：工程配对完成，未启动正式场

一次获准的探针 bug replay 后，R1 六组保存残差向量算子配对均通过 `1e-10` 等价门，且所有 R2/V26 输出差均为0；范围仅为 engineering actions，不是 Krylov solve。受控裁定 `NO_REPRODUCED_IMPLEMENTATION_REGRESSION`：没有在这些短操作中复现历史全 KSP 约18.9%的 V26 slowdown，但不能据此排除系统态或完整 solver 差异。attempt03 的原始 adapter 失败及负记录仍保留，attempt04 另行绑定 dirty source/probe hash。

| 项目 | 结果 | 分类/边界 |
|---|---:|---|
| p4 factor | 两次各一次：213.987342 / 223.155029 s；84680 rows；`ICNTL(23)=4687 MB` | 合计 numeric factor 437.142371 s；不是 solver iteration |
| p6 setup | 内部total 255.476535 / 249.130047 s；outer wrapper 255.485893 / 249.145521 s | builder audits 249.919023 / 242.479440 s；嵌套项不可再加到 setup |
| i=16 A6/H6/BAL_H | V26/R2 median wall ratios 0.997073 / 0.994038 / 0.994679 | 输出差均0；仅算子短操作，不是 Krylov iteration |
| i=112 A6/H6/BAL_H | V26/R2 median wall ratios 1.001948 / 0.978271 / 1.014972 | 输出差均0；仅算子短操作，不是 fresh residual |
| 历史 p4/Q4 i=112 baseline | residual `2.71399585136905e-6`；solve time `3437.233336 s`；RSS/PSS=`7384477696/7352336384 B`；swap=0 | V25 历史记录；不是 V27 fresh solver result |
| watchdog process-tree | attempt03/04 RSS=`7132229632/7148744704 B`；PSS=`7100228608/7116825600 B`；swap均0 | 两次工程进程保留factor/cache与两侧actions；没有完整formal FGMRES history，非production内存峰值 |
| R2/R4 | `NO_ADOPTED_CHANGE` / `NOT_RUN` | r2 保持速度基线；ordinary default 不变；没有正式 R/T/A/字段结果 |

R1/R2 原始证据、两次attempt计时边界、memory caveat与source/hash见 [V27 outcome](workingset_p6_setup_v27.md)、[Response V28](../response_v28.md) 和 [pair/selection/compact/decision records](records/workingset_p6_setup_v27_pair.json)。历史 V26 与更早负结果不回写。

---

## V26 setup-efficiency 收口：与 r2 数值一致，但没有端到端提速

V26 本轮唯一正式完成场是 `20260923T001753.478027Z`：Full3D、p6/h7.5、coarse p4、990 cells、MPI1/thread1、126 步，最终显式真残差 `9.283164976754267e-7`，分类为 `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`。它没有匹配的独立 h7.5 reference，不宣称 continuum convergence。

| 模型 | full workflow 单调（s） | KSP（s） | setup 单调（s） | final residual | RSS/PSS（B） | 裁决 |
|---|---:|---:|---:|---:|---:|---|
| V26 setup-efficiency | 3595.9571450339936 | 2716.518828 | 823.0868099959989 | 9.283164976754267e-7 | 7381557248 / 7346483200 | 一致性通过，authority limited |
| V25 Q4 r2 speed baseline | 3114.283619607013 | 2284.681783819 | 781.971881371981 | 9.283165086752956e-7 | 7390937088 / 7354803200 | 速度基线 |

V26 相对 r2 的 full/KSP/setup 分别慢 `15.46659149457179%`、`18.90140881935669%`、`5.257852565220267%`。因此 r2 保持速度基线，V26 仅显式 opt-in/review-only，不提升为 ordinary default。V26 每 16 步残差与耗时、场/通道/功率离线回归、T5 `DEFERRED` 和本次 worker 前 gate rejection 见 [V26 outcome](setup_efficiency_v26.md)、[response V27](../response_v27.md) 与 [V26 compact](records/setup_efficiency_v26_compact.json)。

执行端的一次重复启动没有进入 PDE：`myfenics-case-20260923T014131-156906.service` 因一次 replay 额度耗尽在 worker 前退出；没有新残差或新物理结果。原始 log、账本 hash 和 `REJECTED_BEFORE_WORKER` 分类见 [relaunch gate record](records/setup_efficiency_v26_relaunch_gate_rejection_20260923T014131.json)。旧 64.917 s 首次 implementation-bug 记录和 V26 本轮正式结果均保留。

---

## V25 A6/H6 粗阶对照：Q4/Q3 通过，Q2 受控停止

本批在同一冻结 source cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32、p6/h7.5、990 cells、Full3D、MPI1、complex128 条件下登记 p4/p3/p2 粗阶。粗阶改变的是预条件器的离散空间与因子规模；它不自动代表连续极限收敛，也不能把没有终态的 Q2 写成失败或通过。

| 模型 | 完整流程/停止（s） | 纯 KSP（s） | 进度 | 最后显式真残差 | RSS/PSS 峰值（B） | 状态 |
|---|---:|---:|---:|---:|---:|---|
| V24 p4 reference | 4579.015917060999 | 3716.1522563079925 | 126 | 9.283164961979326e-7 | 7339319296 / 7307023360 | completed PASS |
| Q4 p4 | 4718.70844729399 | 3766.626355408 | 126 | 9.283165086752956e-7 | 7389360128 / 7357231104 | completed PASS |
| Q3 p3 | 7065.949492944987 | 6082.501362726 | 361 | 9.460140452867132e-7 | 4031815680 / 3999603712 | completed PASS |
| Q2 p2 | 15755.054311790009 start-to-stop | unknown | iteration 1048；PC1052 partial | 0.0006086703757232677 | 2702069760 / 2670846976 observed | RESOURCE_CONTROLLED_STOP |

本段是 V25 阶段的历史横向结论；截至 V28 修复后，另有一场同配置正式观察比 R2 denominator 的 workflow 时间短，详细口径和单次运行限制见本页顶部。Q3 是当时合格通过场中 RSS/PSS 最低。Q2 的最后显式 iteration 1048 未达 1e-6，但 active PC1052 是 PC sequence counter 而非 iteration；没有 final KSP、official field 或 physical result，故分类为 RESOURCE_CONTROLLED_STOP / CONVERGENCE_NOT_ESTABLISHED_BEFORE_STOP。

同迭代 112 的 p4 基线：V24 真残差/solve_seconds/RSS/PSS = 2.7139958442857524e-6 / 3606.8307935579464 s / 7334645760 / 7302341632 B；Q4 = 2.71399585136905e-6 / 3437.2333360950015 s / 7384477696 / 7352336384 B。每 16 次的 8/16/32/64/96/112/128 checkpoints 与 endpoint 已在 [V25 outcome](a6_h6_coarse_degree_v25.md) 中逐项记录；无记录项保持“—”。

## V25 Q4 AC 重跑 r2：正常完成，残差与上一完整 Q4 一致

用户在上次 AC 重复被控停止后授权同配置 r2。r2 没有改数值算法；它在第 126 步正常达到 `9.283165086752956e-7`，worker/service 退出 `0`，watchdog `COMPLETED`，动态 checker `DYNAMIC_PASS`，物理检查和资源检查通过。结果仍为 authority-limited discrete pass，没有匹配 reference，也不外推连续极限。

| 检查点 | r2 真残差 | r2 `solve_seconds`（s） | 前一完整 Q4（s） | 节省（s） |
|---:|---:|---:|---:|---:|
| 16 | 0.0041437222964080065 | 323.3362546709826 | 356.4489566070092 | 33.11270193602661 |
| 32 | 0.0003352917960387092 | 635.7431107280124 | 699.1251847339931 | 63.38207400598071 |
| 48 | 0.00019419221371048617 | 957.0546633300296 | 1059.2216401279873 | 102.16697679795766 |
| 64 | 3.0233523443058283e-5 | 1270.2234611949964 | 1399.241939390997 | 129.01847819600061 |
| 80 | 1.760946862124978e-5 | 1590.69534846704 | 1914.236668254 | 323.54131978696 |
| 96 | 3.7766998795463687e-6 | 1903.8770562190532 | 2676.8190681720002 | 772.942011952947 |
| 112 | 2.71399585136905e-6 | 2225.8895136200404 | 3437.2333360950015 | 1211.3438224749611 |

112 步 p4 对照也已落盘：两次 logical call 的 r2/前一完整 Q4 残差分别完全一致为 `3.578488052253746e-11`、`3.470567778839567e-13`；elapsed 分别为 `0.7877780729904771/1.7836893460043939 s` 和 `0.7901757570216432/1.907731957995565 s`。p4 独立内存字段没有记录。完整表和 AC1 起止观察见 [r2 outcome](v25_q4_ac_swap_observe_r2.md) 与 [r2 compact](records/v25_q4_ac_swap_observe_r2_result.json)。

S6 没有重跑 PDE、第四场或修改 swap 规则。既有 FE audit glue 以最小 tracked utility 提升到 benchmarks/fe_metric_v25_q4_glue.py，仅修正 repository-root parents 层级，保留旧 tool SHA，提升后不重算 FE。机器可读证据见 [components](records/a6_h6_coarse_degree_v25_components.json)、[frozen manifest](records/a6_h6_coarse_degree_v25_frozen_manifest.json)、[Q4](records/a6_h6_coarse_degree_v25_q4.json)、[Q3](records/a6_h6_coarse_degree_v25_q3.json)、[Q2](records/a6_h6_coarse_degree_v25_q2.json)、[decision](records/a6_h6_coarse_degree_v25_decision.json) 和 [selective merge manifest](selective_merge_manifest_v25.md)。

## V24-1 正式 B：laptop-speed discrete pass，authority limited

本节记录 Review V22 唯一一次正式 B；下方原有 V24/V23 历史段落保持原样，不把旧 `58/59` 改写成通过。

| 项目 | V24 正式事实 |
|---|---|
| 模型/身份 | original p6/h7.5，`[9,5,22]`、990 cells、80 modes、MPI1；source=`b480178314efdf434c5f7405f2ab356ff9137c17` |
| 结果 | `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`；126 iterations；explicit/post-release residual=`9.283164961979326e-7` |
| 官方物理量 | R/T/A/`A_volume`=`0.36509755370062585/0.013016803347759889/0.6218856429516143/0.6218856421339044`；`R00_total=0.3650608628870489` |
| 资源 | 正式连续 watchdog process-tree RSS/PSS=`7339319296/7307023360 B`；16998 samples；swap=`0`；watchdog `COMPLETED`；descendants cleared |
| 时间 | full workflow=`4579.015917060999 s`，相对旧 `5581.178597819002 s` 为 `1.218859837771x`；端到端比较，不作 kernel-only attribution |
| 线程 | single-core selected；2/4-thread memory-neutral qualification `NOT_RUN`，不写成采用 |
| authority | 无匹配 h7.5 independent reference；不宣称 continuum convergence |

P1 的 bounded same-factor repair 已单独记录；P5 交付入口为 [response V25](../response_v25.md)、[V24 outcome](laptop_speed_v24.md)、[compact](records/laptop_speed_v24_compact.json)、[decision](records/laptop_speed_v24_decision.json)、[selective manifest V24](selective_merge_manifest_v24.md)。正式 raw output、residual、watchdog 和 resource logs 仍在 ignored run root。

### V24-1 P5 独立核对与资源口径

| 核对项 | 结果与边界 |
|---|---|
| raw-field offline checker | `passed=true`；audit SHA=`58ca321b21a01ac60a57beaf1699c9f76f17f0b92a8f2af7a565fbc96c0b32ef`；checker SHA=`c4205d929f4add3f4ca0dd58ca6f736cb749e7ff941786ecf00856f30cbaaebf`；不创建 solver、不启动 PDE/factor/component |
| 身份 | `input_original.dat`=`2ba250…eb6928`；resolved=`3e4a07…7c4587`；physical=`d8c5ab…1d036`；RHS vector=`b85dde…87824`；final/post/official packet identity一致；旧 B matrix/map/80-mode identity一致 |
| A4/PC | 127 boundaries、254 logical calls、254 raw+1 correction、255 physical solves；`BAL_H` 两 coarse calls，`inner_ksp=false`，`max_it=2048`，`restart=32`；formal `time_policy=observe_only`、未启用时间终止；抽样 closure relative 最大 `4.309333201200774e-11` |
| FE same-discrete | L2/scaled-curl relative=`1.8744734231920724e-14/1.351616670038343e-13`，由 artifact absolute/reference 重算，限值 `1e-4`；不是新 PDE |
| formal resource authority | resources SHA=`0b220a16d4cb096ea6a00a808e1a76b547bee42867b5152044f04e1e5e6a4e79`；RSS/PSS=`7339319296/7307023360 B`；global swap delta 0；worker `1142` sample 只作非权威旁证 |
| 时间/阶段 | KSP true monotonic=`3716.1522563079925 s`（不使用 solver.elapsed=`4064.2847061239304 s`）；factor INFOG19/22=`4687/4326 MB`；JIT `11 hit/0 miss`；唯一 correction boundary elapsed=`2.602906637999695 s`，裸 interface=`0.9039880140044261 s` |
| 成本 | formal workflow=`4579.015917060999 s`；formal ledger=`4995.987698561707 s`；prefix watchdog=`863.445624881002 s`；full-PC component watchdog=`811.4285155539983 s`；各账本不相加 |

FE 指标工程 wrapper 的首次记录是 `TIMEBASE_INCONSISTENCY`（49.30150357799721 s，RSS `1280192512 B`，swap0，清场）；成功记录为 `24.127236970991362 s`、RSS `559112192 B`，但使用 `LEGACY_STATIC_MEMORY_ENVELOPE + time_policy=enforce`，不是正式物理资源策略。两份记录和 SHA 均保留，首次受控停止不改判成数值失败。

组件边界也分开记录：P1 source=`72115b6655c3d6ab5f9c3f74ba746e8eb184efb2`；owner manifest tracked diff=`7dd69e7541657d2fe48e1a5893f285b65cca0f68020cc1cb5976afe310cad468`、owner script=`160124274e648a70c25d4bef7eca4a64925f210df5fc672f8d30a5666a407bbd`、first-attempt 实际文件=`aa26c3d8df57464b4348b32f0aeebbcd7e1eb2c05c3d51bd361ab70e7ab0c92d`（旧 manifest 中陈旧 `75bfb...` 冲突保留）；full-PC dirty diff=`0a6fe7f6ee4d99aa9cffbed079586321a8159d94046063eb80db2cff5fa6d08d`、script=`4ec5bcc1bfae4bd9320c4a8cd28d5707769f6601afdc848c72ef29090b306adb`。owner 首次 P/PH 为 baseline `4.10675620699476/0.7427930510020815 s`、candidate `0.3230319220019737/0.3155690860003233 s`；三次 warm 样本中位 P/PH 为 baseline `4.218087512999773/0.7719355450026342 s`、candidate `0.32633427099790424/0.2924728030047845 s`。full-PC candidate 是 owner+packed-A6+packed-power10 组合，不是最终 owner-only 直接配对；其 setup/apply=`206.372522398/53.11041180999018 s`，baseline=`136.53963406301045/52.3144450539985 s`，采用判断为负/不归因稳定加速。正式路线仍 owner-only/native A6/old native H6，未把组件整体提速写成 formal 结论。

## V24 增量：V23 original-B fresh 与登记 bug replay 完成，但保留在线 p4 A4 数值负结果

| 项目 | 本批事实 |
|---|---|
| 范围 | 同一 `990-cell original B` 完成一次 V23 fresh 及一次登记的 hash-bound implementation-bug replay；计算结束后仅整理证据，未追加 PDE；没有 C、new notch 或 new PC |
| 状态 | B 求解完成 `126` 步，独立 A6（释放前后）=`9.2831649554582e-7`；总体不是 PASS |
| checker | `58/59` 通过；唯一失败为原 `online_native_A4`：PC2 首次调用 `rho=2.8870661155266027e-10 > 1e-10` |
| worker/parent/checker | worker=`Z3_ORIGINAL_H7P5_AUTHORITY_LIMITED_PASS`；parent=`worker_exit0/COMPLETED`；checker=`V23_FULL_PHYSICAL_CHECK_FAIL` |
| 物理输出 | `R/T/A/A_volume=0.3650975537006217/0.013016803347759965/0.6218856429516183/0.6218856421339087`；`R00_s/p/total=0.3650608628870448/3.427344920479581e-25/0.3650608628870448`；80/80 通道、场/旋度 finite、能量闭合适用项通过 |
| 资源 | RSS=`7387607040 B`；native allocated=`4687 MB`、upper=`4688000000 B`；used=`4326 MB`、upper=`4327000000 B`；p6 cache payload=`450893192 B`，不等同 RSS；swap=`0`、清场 true |
| 时间与对照 | B KSP=`4737.310983555995 s`/126步，O10 KSP=`1151.635034 s`/112步；单步约`10.28246→37.597706 s`，RSS比约`2.60885`；O10自身含p6 target cache miss/compile峰，冷暖JIT分开 |
| native/backend | `INFOG(1)=0`；`INFOG(9)=INFOG(29)=221594144`；`ICNTL(23)=4687 MB`且readback=`4687 MB`；allocated/used与p6 payload分列 |
| V23策略 | 真实 RSS、MemAvailable/cgroup 压力和 zero-swap/清场裁决，仅保留`128 MiB` watchdog/write证据余量；不沿用旧固定6/8GiB或3.857GB续算阻断；[授权记录](../user_authorization_v23_physical_memory.md) |
| 身份 | formal source=`d3596ac31bdabc2bb9233963adea3e91ddc2f220`；base=`8700e65c68b57455586df41f37484d37397dda92`；metadata commit SHA=`null`，由 containing commit 识别；旧109文件/27 profile不变 |
| 决策 | `AWAITING_CHATGPT_REVIEW`、`NOT_FULL_PASS`、`NO_MERGE`；下一研究对象只能另行批准的 PC2 A4 数值缺陷审查，禁止擅自跑 C/notch/new PC |

正式增量入口：[response V24](../response_v24.md)、[V23 compact](records/dual_condensed_physical_memory_v23_compact.json)、[V23 decision](records/dual_condensed_physical_memory_v23_decision.json)、[V23 checker](records/dual_condensed_physical_memory_v23_checker.json)、[V24 detailed summary](summary_v24.md)。旧内容从下一行起保持原样。

## V23 增量：一次 original-B 容量试验（待 ChatGPT 审阅）

| 项目 | 本批事实 |
|---|---|
| 范围与身份 | 新增独立 V22 profile、冻结有限额度，并完成一次 `Z3_ORIGINAL_H7P5` original B；formal source=`57d1f601119900a52b7aa574fd4df557cfe0aa6c`，checker 修复=`cf9f2346c400612e41926e0b21b7946e9a5e6715` |
| 数值与停止 | `INFOG(1)=0`、实际因子条目=`221594144`；numeric 成功不等于完整求解通过，因 allocated continuation ceiling 受控停止（不是 RSS 超限或 MUMPS `-9/-19`） |
| 三层分类 | worker=`CONTROLLED_STOP/RESOURCE_CONTROLLED_STOP`；parent=`WORKER_FAILED`；独立 checker=`CAPACITY_EVIDENCE_VALID_AUTHORITY_LIMITED`，physics/official result 未通过 |
| 资源与时间 | tree RSS peak=`6913208320 B`，swap=`0`、清场完成；numeric=`217.1021214370012 s`，full workflow=`493.84353463599837 s`，V22 ledger=`538.0163161130178 s`，已知 V21+V22 ledger=`2422.4842713640884 s`；setup 已含在正式 workflow/ledger，外部修复与 checker 时间 unknown |
| 边界 | A6、outer residual、完整 B/物理场、C 未运行；JIT `11 miss/0 hit`，编译 elapsed=`101.78435976599758 s`，嵌套于全流程 |

机器可读入口：[V23 response](../response_v23.md)、[V22 compact](records/dual_condensed_capacity_v22_compact.json)、[V22 decision](records/dual_condensed_capacity_v22_decision.json)、[tracked checker evidence](records/dual_condensed_capacity_v22_checker.json)。阶段 RSS/单调时差、compiler-descendant 筛选和 raw SHA 索引在 compact；正式状态为 `AWAITING_CHATGPT_REVIEW`、`no merge`、`no new PDE`。

# Task39extra 当前汇总：Review V21 / Response V22 Z5 四模型收口

Z5 是一个聚合账本，不是一次新的 PDE 重跑：O10 只读复用，A 完成正式非可分 h10，B 在 h7.5 全局 p4 trace 因子的 symbolic-after/numeric-before 容量 Gate 前受控停止，C 因 B 的适用前置条件失败而未启动。Z1 base=`f9e16c21b936673b5a2dadcf52d2c344e61aabe8`；B formal run source/current pre-Z5 HEAD=`f8d0fbf3da48fd3cbe5cc3a226dbff3feb1d9b48`；A formal solver source=`863ec3bcd7eead867795284db11fc39e758a6f08`。ordinary default 不变，master merge 未批准。

| 模型 | 状态与 residual | 资源/时间 | 结果边界 |
|---|---|---|---|
| O10 只读复用 | 112 步；A6=`9.730817853580463e-7` | tree RSS=`2831749120 B`；monotonic=`1479.1772295139963 s` | V20 original baseline；不是本轮 fresh PDE，仅作 `B/112` 分母 |
| A / `Z2_NOTCH_H10` | **MATCHED_REFERENCE_PASS**；146 步；worker residual=`9.756517234801763e-7`；independent A6=`9.756517234802322e-7` | tree RSS/PSS=`2297982976/2267706368 B`；swap=`0 B`；monotonic=`1648.8478095369937 s` | 本批新场 official result 仅属于 A，O10 为历史 PASS；R/T/A/`A_volume`、80 modes、closure 和 field/curl gates 通过；checker `65/65` |
| B / `Z3_ORIGINAL_H7P5` | `H7P5_RESOURCE_BLOCKED_ON_LAPTOP`；outer residual/physical outputs=`not_run` | watchdog tree RSS=`2318045184 B`；worker-sampled tree PSS=`2287882240 B`；inventory/workspace=`1136131046/76405680 B`；swap=`0 B` | p4 CSR 已 materialize；symbolic request=`10131000000 B`，不是已分配内存；父层 `WORKER_FAILED`，worker 层 `RESOURCE_CONTROLLED_STOP`；不是 OOM 或 numerical failure |
| C / `Z4_NOTCH_H7P5` | `not_run_by_review_condition` | 无 C worker/资源/时间 | B 的 h7.5 资源前置 Gate 失败，不能填充 C 的迭代或物理量 |

## B 的可审计中间结果

B 已完成 `84680×84680` complex128 p4 CSR，exact stored NNZ=`32320342`；CSR/mapping/values SHA256 分别为 `857bc8bb5f04b28a55283fb960a2b695e1078983e55ff151687780de5dab8ee0`、`bed2794532a40630632e06637cfda5a7bb52a06a7209824d5344085b6fa2cb1d`、`cf081185f6950ebb2c704e0426e02bb0687ef7ae47faf34115d729c8eb832b34`。raw tensor class=`12`、oriented Schur class=`26`、retained local numeric cache=`24541920 B`（LU/recovery/RHS projection/RHS trace=`4863456/8626176/2426112/8626176 B`）；p6 local cache=`not_built`。

symbolic rows=`84680`，`nz_used/nz_allocated=32320342/45403840`，INFOG16/17=`5060/5060 MB`，INFOG3/20=`221594144/221594144`。冻结公式给出 request=`10,131,000,000 B`；`1,136,131,046 + 10,131,000,000 = 11,267,131,046 B > cap 6,442,450,944 B`，所以在 numeric factor 前停止。该 request 是政策上界，不是 numeric RSS 或已经分配的 factor。

## 几何、缓存与证据闭环

冻结 notch union 是 `x=[16.5,33.5] nm`、`y=[0,8.333333333333334] nm`、`z=[40,80] nm`，来自 8 个实体；h7.5 mesh 每轴 `[9,5,22]`、owned cells=`990`，含保持外边界对齐的 neutral alignment planes，不是 720 cells 或 uniform multiplier。11 个 prepared forms 的 cache 计数为 O10=`10 hit/1 miss`（唯一 miss=`p6_condensation`）、A=`11/0`、B=`11/0`；form event time 为 `56.7998199990252 / 0.017299229046329856 / 0.02241471700835973 s`。A/B 没有 compiler descendant samples；这些不是完整 setup/workflow，也不支持 warm-cache RSS 优势。

Z5 frozen authority check 已检查 `50` 个 frozen files、`26` 个旧 profiles，`changed=0`、`passed=true`，SHA256=`880534b2c2bb72939669ef098cb809510b666930101a74a0a1312905e0b3a5b3`；saved cost comparison SHA256=`87975d656484936f6b3ca1ca067bd539fd6a752a91a98acb8816fd2e6fe1d577`。A 的更正路径为 `49 passed`，Z1 formal 前工程资格为 `99 passed`，A checker 为 `65/65`；三组集合不相加，B checker=`not_run`。

机器可读入口：[V21 compact](records/dual_condensed_robustness_v21_compact.json)、[V21 decision](records/dual_condensed_robustness_v21_decision.json)、[V21 detailed outcome](dual_condensed_robustness_v21.md)、[V22 response](../response_v22.md)、[run index](records/run_index.json)、[selective merge manifest V22](selective_merge_manifest_v22.md)。当前 tracked Z5 状态：`LOCAL_REVIEWED_REMOTE_PUSH_PENDING_AUTH`。

---

# Task39extra 当前汇总：Review V20 双层凝聚低内存生命周期完成一场 original PASS

单元凝聚先消去每个有限元单元内部未知量，只把共享 trace 和端口交给外层迭代，最后恢复完整场。本轮 V20 只资格化一个固定的 13.5 nm、Full3D p6/h10、252 cells、MPI1 original；目标是把 p6 编译、identity payload 和求解对象释放顺序做成可核验的生命周期，而不是宣称新的物理模型或生产默认。

| 项目 | 当前结论 | 证据边界 |
|---|---|---|
| 范围与身份 | source `b337d215c3d278d0c1e715f53e28b69f7f0ee3fe`；profile `physical_p6_trace_p4_condensed_lowmem_v20`；run id `task39extra_v20_y3_lowmem_original` | one-dat/one-run；formal run 1，PDE replay 0 |
| 数值 Gate | independent A6=`9.730817853580463e-7`，limit `1e-6`；112 步 | port closure `5.8476980231808125e-16`、internal residual `2.1627175873860883e-17`；independent 57 checks/24 physical subchecks 全通过 |
| 官方物理量 | R/T/A/`A_volume`=`0.3656258136701664 / 0.012990624019505325 / 0.6213835623103282 / 0.6213833803349053` | 最大 total power difference `1.981579103027542e-7 < 1e-5`；selected field difference `8.291924787930399e-7 < 1e-4` |
| 内存 | full tree RSS=`2831749120 B`，PSS=`2797270016 B`，swap=`0` | 比 V19 低 `28.59098%`，但比 V18 高 `11.99498%`；不是全面低内存 |
| 时间 | measured monotonic=`1479.1772295139963 s`；conservative billing=`1611.2442379729905 s` | billing 不是 measured runtime，也不与 monotonic 相加；本场比 V19 measured monotonic 慢 `9.4056%` |
| 后端生命周期 | p4 policy=`MATRIX_RETAINED_BACKEND_DEPENDENCY`，early-release saved=`0 B` | MUMPS allocated/used/matrix upper=`1463000000 / 838000000 / 232205060 B`，均不是 RSS |
| 交付分类 | `PASS_ORIGINAL_MEMORY_LIFECYCLE_MIXED_TRADEOFF` | explicit lowmem 可作为同 original 的内存优先候选；V19 保留为时间基线；ordinary default 不变 |

已完成：V20 Y0/Y1/Y2/Y3 证据和轻量文档收口。未运行：notch、5 nm、0.7 nm、MPI2/4 新资格、Ruff、全仓 pytest、CI 和 detach 研究重启。负结果和未知账本（包括旧 V18/V19 policy/unknown history）保留，不改写为通过、零费用或已测 runtime。

机器可读入口：[V20 compact](records/dual_condensed_memory_v20_compact.json)、[V20 decision](records/dual_condensed_memory_v20_decision.json)、[V20 lifecycle outcome](dual_condensed_memory_v20.md)、[V20 response](../response_v21.md)、[run index](records/run_index.json)、[selective merge manifest](selective_merge_manifest_v21.md)。

---

# Task39extra Response V20 / Review V19：original 112步完整通过，以更高内存换取时间

单元凝聚是在每个有限元单元内先解掉内部未知量，只迭代相邻单元共享的边界与原80端口；最后把内部场准确恢复。本轮把这个过程也用于p6，p4继续用V18准确凝聚LU。这样减少外层向量与全局纠错次数，代价是新增局部缓存；原p6本来就是matrix-free，没有删除一张原本存在的全局A6矩阵。

| 指标（同一 original，Full3D p6/h10，13.5 nm，MPI1） | V18 准确 p4、完整 p6 空间 | V19 p6/p4 双层凝聚 | 结论 |
|---|---:|---:|---|
| 外层向量长度 | 173802 storage | 51272 trace＋端口 | 少70.50%，属于载荷/维数变化 |
| FGMRES32 步数 | 564 | 112 | 少80.1418% |
| KSP 算子作用 / 求解PC | 581 / 564 | 115 / 112 | 同一KSP；X1另1次PC |
| 原 A6 最终真实残差 | 9.92314718715201e-7 | 9.730817853580687e-7 | 均≤1e-6 |
| L2 / scaled-curl | 1.3644783293e-8 / 4.3714257233e-9 | 1.5860495296e-7 / 1.5359268899e-7 | 均≤1e-4；新场误差没有更小 |
| 全过程树 RSS，B | 2528460800 | 3965534208 | **增加1437073408 B，+56.8359%** |
| 同口径 PSS，B | 2494237696 | 3931141120 | +57.6089% |
| 数值常驻库存，B | 1830284886 | 2031387110 | +201102224 B，+10.9875% |
| 同时临时池上界，B | 396129600 | 423441224 | +6.8946%；不是RSS |
| 完整流程 monotonic，s | 6609.6613787800015 | 1352.0121227929922 | **减少5257.649256 s，-79.5449%** |
| 保守账本结算，s | 7210.314084736167 | 1474.858420017083 | 与monotonic分列，不相加 |
| 完整数值 / 物理 / 资源安全 | PASS / PASS / PASS | PASS / PASS / PASS | 资源安全不等于节省内存 |

**推荐把V19保留为下一轮唯一优先验证候选：此固定模型完整通过，时间显著降低；同时承认内存退步，V18保留为内存较低的已通过基线。** 这不是生产默认切换或新计算授权。状态为`PASS_ORIGINAL_TIME_GAIN_MEMORY_REGRESSION`，不能写成“全面省资源”，也不能忽略实测时间收益而写成“无任何资源收益”。

新original仅一场、无正式重放；独立用户服务正常结束，整树零swap且清场。旧notch保持用户关闭/最终未知，本批没有notch、BLR、其他PC、参数扫描或新参考，不影响5nm线。完整数据和同scope边界见下方报告；普通默认不变，不合并master，等待统一审阅。

[Response V20](../response_v20.md)、[详细结果](dual_cell_condensed_v19.md)、[compact](records/dual_cell_condensed_v19_compact.json)、[decision](records/dual_cell_condensed_v19_decision.json)。下方历史原样保留。

---

# Task39extra Response V19 / Review V18：原始p6通过，notch按用户要求停止续算

| 研究问题/模型 | 已测结果与结论 |
|---|---|
| 同三RHS的准确p4凝聚 | 原A4残差≤7.52867e-11，场/旋度约5.2e-12；共享12类局部LU，trace+80端口仅一个21824行全局因子，NNZ8184464；完整恢复和slave-zero通过 |
| 同口径p4内存 | Q1全过程RSS2825973760 B→U2 1785585664 B，减少36.8152%；库存1776346158 B，临时134217728 B。不是完整p6内存百分比 |
| 唯一凝聚BLR tau1e-5 | 质量通过，条目减2.3564%，RSS反增1.4163%；保留负结果并选exact |
| original p6/h10，Full3D，13.5 nm，MPI1 | **564步，A6=9.92314718715201e-7，完整物理/资源PASS**；L2/curl=1.36448e-8/4.37143e-9；RSS2528460800 B，库存1830284886 B，临时396129600 B |
| original物理量 | R/T/A/A_volume=0.365625790969/0.0129906323212/0.621383576710/0.621383574597；80模式、近场和守恒通过；能量偏差2.11291e-9 |
| notch同配置 | 494步后父watchdog丢失；最后真实残差第488步5.478307207552461e-6，未到1e-6；第480步L2/curl=8.36579e-8/4.43005e-8。无最终official物理资格，只有收敛趋势 |
| 失败与修复 | original前两次计时实现失败保留，修复后第三次通过；notch外部父监控失联已用独立用户服务薄入口修正，仅ABI/help验证，最新用户要求不再恢复计算 |
| 完整成本 | original通过场monotonic6609.661379 s，保守结算7210.314085 s；五个已结算场保守总7709.181734 s，notch已见前缀另5704.197024 s，完整总耗时unknown |

单元凝聚先消去单元内部未知量，解共享边界与原端口后恢复完整场，以局部缓存费用换取较小全局因子。本批改进准确粗逆的存储组织，保留BAL_H/H6与同一FGMRES32；历史V5原始模型也需564步，因此没有迭代加速结论。基线复用Q1，旧宏块与BLR负结果保留，不新增参考或扫描参数。

notch的Codex空闲任务卸载记录与最后父心跳同秒，worker明确报专用watchdog不存在；具体退出信号和最终结算unknown。已见资源前缀安全、宿主进程清场确认，但缺父最终资源authority，不能称完整资源PASS。旧43200秒未结算预留以幂等记录转成政策占用，不改写为实测；无活动attempt、无基础设施重跑，原600秒unknown历史不改。

最新用户明确要求修正后不再计算：original收敛已有实证；notch不凭趋势升级PASS。106项相关测试通过，运行方式仅轻量验证。保持ordinary default与5nm工作线，等待统一审阅，不合并master。

[完整回应](../response_v19.md)、[详细结果](p4_cell_condensed_v18.md)、[compact](records/p4_cell_condensed_v18_compact.json)、[decision](records/p4_cell_condensed_v18_decision.json)、[合并边界](selective_merge_manifest_v19.md)。下方保留历史。

---

# 当前汇总：Review V17 的 T1 同时未达内存与质量线，关闭本批阈值试验

BLR 用较少数据近似全局消元因子中的部分矩阵块，代价是回代误差。本次唯一新 p4 控制使用 `CNTL(7)=1e-3`；三个真实输入共用一份因子，各做一次 MatSolve，没有迭代改进。它仍需要全局因子，不代表已完成完整 p6 求解。

| 指标 | 原 p4 LU（历史 Q1） | 旧 BLR 1e-5（历史 V16） | 本次 T1 1e-3 | 条件 T2 1e-4 |
|---|---:|---:|---:|---|
| 全过程 / factor-live 树 RSS，B | 2825973760 / 2825973760 | 2741243904 / 2741243904 | 2672054272 / 2672054272 | not_run |
| 实际因子条目 | 53417584 | 53040280 | 48706124 | not_run |
| allocated / used upper，B | 2343000000 / 1382000000 | 1693000000 / 1420000000 | 1623000000 / 1351000000 | not_run |
| 全流程 monotonic，s | 536.468042244 | 571.514731005 | 571.461267577 | not_run |
| 三 RHS 质量线 | 通过原 A4 精度 | 通过历史 p4 筛选 | rho 与场误差均有失败项 | not_run |

RSS 和条目是实测字段；upper bytes 是由后端实测 decimal-MB 字段保守换算。T1 fronts=33，覆盖比例49.0%；条目减少8.8201%，RSS减少5.4466%。`R_peak=R_live=0.945534` 未达0.90，亦未达 resident 分支的0.80，故 M=false。三 RHS rho为4.78774/0.194757/6.06357（限值0.5），场L2为0.604297/0.682241/0.620539，scaled-curl为0.603768/0.681708/0.620123（均限值0.25），Q=false。

T1 source为 `a1bc6b54e613ebf91c5c97ecddcc14555b084ee0`，requested base为 `863c71d5133b137a888a587becb9cbe8ed2daca9`。模型为13.5 nm、252 hex、p6/h10宿主、MPI1/线程1；实际控制是p4增广53164行、80端口、24730144 NNZ。全部资源检查通过，zero job swap、全局交换增量0、后代清空；时间保持observe_only。571.4613 s 中，setup37.4301 s、assembly494.3436 s、factor阶段17.0804 s。保守ledger结算626.1990 s另列，不能与monotonic相加；旧V14/V16费用及600 s真实耗时unknown的政策占用仍保留。

全局矩阵内容hash未采集；三个输出各有4个约1e-18的slave存储残量，strict slave-zero检查未通过。维数、输入/map/source hash和三个冻结向量的算子作用核对不冒充矩阵字节相等证明。这些证据/坐标格式缺口如实保留，M的独立失败已经足以禁止T2，不为补metadata重跑。

最终行动 `T5_CLOSE`。T2、T3 original、T4 notch均未触发；没有本轮原A6、完整E/H、R/T/A、A_volume、80模式或守恒的通过/失败结论。此次关闭有限设计，不推断整个BLR阈值区间无解，不影响5 nm线，不合并master。

完整数值、调用与全过程成本见 [response_v18](../response_v18.md)、[tradeoff结果](p4_blr_tradeoff_v17.md)、[compact](records/p4_blr_tradeoff_v17_compact.json)、[decision](records/p4_blr_tradeoff_v17_decision.json)、[测试](test_summary.md)和[selective manifest V18](selective_merge_manifest_v18.md)。下方历史全部原样保留。

---

# 当前汇总：S2 p4 BLR 质量通过但内存收益不足，S3/S4 未准入

| 当前问题 | 实测结论 | 原因及证据范围 |
|---|---|---|
| 实际压缩与内存收益 | `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN` | S2 BLR native entries `53417584 -> 53040280`，实测条目比 `0.992936707882558`，约降 `0.706%`；完整 RSS `2825973760 -> 2741243904 B`，`R_peak=R_live=0.9700174654134085`，约降3.0%。 |
| allocated/used 是否一致改善 | 不一致 | allocated upper `2343000000 -> 1693000000 B` 降27.7%，但 used upper `1382000000 -> 1420000000 B` 增 `38000000 B`；workspace 两边均 `17825792 B`。不能用 allocated-only 通过 RSS Gate。 |
| 三 RHS 是否保住 p4 全局纠错 | S2 质量筛选通过 | rho=`.012747787/.000716687/.017677845`；field L2=`.000468941/.000638197/.000518460`；scaled-curl=`.000465015/.000633006/.000514229`；每个恰好一次 MatSolve。 |
| 完整 p6/original/notch/非可分 | 全部 `not_run` | S3 memory admission 未满足；没有 p6 outer true residual、E/H、R/T/A、`A_volume`、80模式或守恒结果。 |
| 最终决定 | 关闭固定 BLR 配置 | 不试新 epsilon、不启动 p6；TRACE bundle 的 ICNTL(49) public getter unsupported，本轮不展开新调查、不改变策略，也不升级 ABI；保留 p4 research evidence，ordinary default不变。 |

模型为13.5 nm、p6/h10、252 cells、Full3D、MPI1/线程1、complex128/int32；但正式批只对 p4 的 `53164` 行增广矩阵做控制，没有 p6 outer solve。直接求解会保存消元产生的矩阵块，BLR 用较少数据近似其中一部分以尝试省内存，代价是回代误差需检查；它不是 factor-free PC。S2 正式 source 为 `24bd767e6b0d158ac20deb360a135f10c0611ede`，三个 RHS 使用同一个 BLR factor，控制在 symbolic 前设置并逐次读回。

S2 的 `S2_BLR_CONTROL_PASS` / `DISCRETE_SOLVER_OUTPUT_PASS` 只适用于 p4 三 RHS control。三次 native identity relative 为 `8.30e-17/2.74e-18/9.82e-17`；没有 refinement 或参考解进入回代。完整四问、控制读回、factor-live/全流程资源和 phase-derived 时间见 [V17 response](../response_v17.md) 与 [p4 BLR outcome](p4_blr_v16.md)。

独立 checker 从 raw vectors/resources/factor fields 重新计算：comparison、control、resource gates 全过；质量通过但 `R_peak/R_live` 不满足 S3 线，所以 S3 original、S4 notch 不启动。这个结果不否定全部 BLR 或全部 p4，只关闭当前固定配置的内存适用边界。

完整 formal workflow monotonic `571.514731005 s`，phase-derived setup/assembly/factor 为 `37.088510941/494.414024999/20.378098889 s`；parent monotonic `571.483797368 s`，conservative settled `625.736658980034 s`。phase audit 是从记录边界派生，不把每段写成独立函数计时；工程窗口单独记录，不并入 PDE ledger。Q1/S2 配对成本为 symbolic `0.2683213069976773/0.33692986499954714 s`、numeric `18.488779414998135/19.946495771997434 s`、full monotonic `536.4680422439997/571.5147310050015 s`、conservative settled `584.7709557270404/625.736658980034 s`；BLR `RINFOG3=39449025878.0` theoretical、`RINFOG14=41079564559.0` actual。

V16 使用独立 batch ledger `review_v16_p4_blr`，旧 V14 ledger SHA `1e3b9c01745fef72f7a794b23e5077508fd65b3951485131d8b639043bd4ecb3` 和旧 `600 s` policy debit 只读保留；该引用不可返还、不可冒作新实测，新 batch ledger 单列其关系；新 batch unique replay 为0。S2 job swap为0、global delta为0/0、后代清场；旧 Schur/interface 负结果和未知范围不被覆盖。

[V17 compact](records/p4_blr_v16_compact.json)、[decision](records/p4_blr_v16_decision.json)、[run index](records/run_index.json)绑定 source/input/physical/mode/run/resource hashes；[test_summary](test_summary.md)记录 128 项相关测试和未运行的 full repository/Ruff/CI。选择性合并边界见 [manifest V17](selective_merge_manifest_v17.md)。不扩大到5nm/0.7nm或连续收敛，不合并 master。

# 历史快照（HEAD 原始当前段）

# 当前汇总：准确 Schur 不省内存，固定接口近似未通过准入

| 当前问题 | 实测结论 | 原因及证据范围 |
|---|---|---|
| 准确 Schur 是否省内存 | 精度通过，内存没有节省 | Q1/Q2 RSS 2825973760/4267347968 B，Q2/Q1=1.510045；常驻库存2906619390/4698023554 B，比值1.616319。 |
| 接口近似是否有效 | 冻结候选关闭 | 三 RHS 的 rho=37.272086/.726414/41.825936；分别要求≤.5/≤.2/≤.5，L2/curl 也全部未过。 |
| original/notch 是否通过 | 两者未运行 | Q3 未准入；无本轮 A6 最终1e-6、E/H、R/T/A、A_volume、80模式或守恒资格。 |
| Q6 是否完成 | Q6_FINALIZED | 零 PDE 的证据收口，不能理解为完整 PC/物理通过；BAL_H map guard 异常及旧失败保留。 |

模型为13.5 nm、p6/h10、252 hex、Full3D、MPI1/线程1、complex128/int32。Schur先消去42宏块内部，只在共享接口求解再恢复完整场；全流程同时包含内部与接口因子，接口行数减少并不自动节省内存。Q1原p4 LU与Q2准确Schur在同一source、同三输入及原A4残差/场/旋度标准下配对；两个全局factor顺序运行。

准确Q1/Q2三份原A4残差最大值为6.55690292958073e-11/8.675448391967837e-11（限1e-10），最大参考场/旋度差0/1.938608248500389e-12（限1e-8）；Q1的零差是复现既有离散向量，不是连续物理误差为零。完整三输入表、setup/调用、allocated/used、全部内部耦合与全过程RSS/PSS见[当前详细结果](p4_schur_v14.md)与[response_v16](../response_v16.md)。

Q3第一次因常驻库存projected3331318958 B超过3 GiB而停止；唯一生命周期修复提前释放无用active volume430410244 B，原cap不变。重放完成42个局部LU/SVD与rank416的小粗层，三次F_int含评价约1秒，内部残差约1e-12，但全场误差接近1、接口残差大。三输入向量/指标先保存，随后BAL_H metadata key-set guard异常。worker真实终态WORKER_FAILED与保存包重算MEASURED_NEGATIVE_CANDIDATE分别保留；没有为了补BAL_H再跑PC。

Q0/Q1/Q2/第一次Q3 source为`6a8b273c383d5bd9da37d6630a48bd24d6a90cce`；正式Q3重放为clean `188224ad5fc81b34156a0ae3678bd2121b1206da`；Q6只读汇总为`d9530636ab2f043a84235b515846b410a8deb4b3`。fresh Q0实际核心PASS；Q6仍保留旧Q0终态未知字段，不追溯认证旧EIO。用户时间授权仅启用observe_only，原残差、步数、内存、reserve、zero-swap、清场与物理规则不变。

Q1/Q2全流程保守计费584.770956/773.019110秒，monotonic536.468042/708.431790秒。最终formal ledger结算4082.128437647174秒，另列旧600秒政策占用和3.1秒保守allowance，有效费用4685.228437647174秒；旧EIO实际耗时和完整工程总时长仍unknown。ledger hash为`1e3b9c01745fef72f7a794b23e5077508fd65b3951485131d8b639043bd4ecb3`；Q6自身结算前快照不作为最终总数。新增各场job swap0、global delta0/0、最终子进程清空；旧负结果及未知范围不被覆盖。

[compact](records/p4_schur_v14_compact.json)、[comparison](records/p4_schur_v14_comparison.json)、[run index](records/run_index.json)保存精确source、数值、运行目录与raw hashes；[test_summary](test_summary.md)区分新旧工程资格。没有本轮p6完整物理输出，不扩大该固定案例到5nm/0.7nm或连续收敛结论。接口候选保持research-only，保留共同消元核心和所有负证据；不提升production default，不合并master，同分支推送后等待统一审阅。

---

# 历史快照：Task39extra Review V15 汇总（Q6 refresh 前）

本批最终不是完整 Maxwell 数值通过，而是一次有界的恢复、Q0 性能受控停止和既有证据收口。模型为 13.5 nm fixed、p6/h10、Full3D、MPI1、complex128/int32，源码绑定 `ea5ed4cd511a9f169cd5bbf63c06f33bfed85d9e`。

| 阶段/模型 | 状态 | 实际结果 | 关键边界与证据 |
|---|---|---|---|
| R0 cleanup → R1 | `R0_PASS` → `APPLIED` | C: 剩余 `37233180672 B`；全部准入通过；实际 4 轮 probe `16178076 B`，累计 `32955292 B`；R1 policy debit `600 s` | R0 accepted/source `665a09b6a7d66eff15b4a744036d21f1dad3649d`；无 R1 PDE action；[I/O compact](records/v14_io_recovery_v15.json) |
| Q0 `Q0_CORE` | `PERFORMANCE_CONTROLLED_STOP` | settled `604.5503952971432 s` / reservation `600 s`；assembly 后 `v14_p4_volume_compile_started`；树 RSS `1769385984 B`；PSS 可读样本峰值 `1734977536 B`（2151/2152）；swap 0；formal worker 1 | completed core qualification=0、linear solve=0、worker summary unavailable；不是 numerical failure；[Q0 compact](records/p4_schur_v14_compact.json) |
| Q1/Q2 | `not_run_after_q0_gate` | no matched full-direct/accurate-Schur workflow | memory ratio、resident inventory、三 RHS residual/field/curl、setup/apply不可得 |
| Q3/Q4/Q5 | `not_run_after_q0_gate` | no interface admission、original/notch p6 run | official R/T/A、`A_volume`、衍射、守恒均 `not_run` |
| Q6 | `Q6_EVIDENCE_INCOMPLETE` | packet generated；outer `WORKER_FAILED` exit4，`error=null`，new PDE actions 0 | no missing evidence ⇒ no method-failure claim；下一项 `COMPLETE_EXISTING_REVIEW_NO_NEW_METHOD` |

最终账本 SHA256 为 `59aa33110927596a27af04382ac7830b0631fb3a1892e3460a77d812ab6b75ba`。`613.2807354921454 s` 是按既定 conservative-realtime 规则结算的账本 elapsed 字段，不是 monotonic-only 运行时长；policy debit `600 s`、allowance `3.1 s`、budget used `1216.3807354921453 s`、remaining `41983.619264507855 s`、active attempts 为空。准确 Schur memory 仍 `COMPARISON_INCONCLUSIVE`；接口近似逆 `EVIDENCE_INCOMPLETE`/`Q3_admission=false`；original/notch 均未资格化。状态仍为 `NOT_APPROVED_FOR_MASTER_MERGE`。

工程编辑、监督和等待没有完整独立计时，记为 `unknown`，不写成 0，也不并入 PDE 账本。可复核的观察窗口是 targeted tests `0.17 s`、文档契约测试 `0.05 s`、compileall `0.226307897 s`；这些是工程验证时间，不是正式 PDE 的 residual/solve 时间。文档测试的既有 registry 审计另有 1 个历史缺件失败，详见 [test summary](test_summary.md) 与 recovery compact 的 `engineering_validation`。

---

# 历史快照：Review V15 宿主存储 Gate 阻断（后续已解除）

以下段落保留 R0 阻断时点；其“没有 R1/Q0/PDE”只适用于当时，不覆盖上面的最终汇总。

本节是当前状态入口，覆盖 Review V15 的 R0 基础设施恢复检查。R0 用小型临时文件验证独占创建、哈希回读、同目录原子发布和目录持久化；它不能证明重型 PDE 的可用空间或旧故障的唯一根因。本轮最终分类为 **`INFRASTRUCTURE_BLOCKED`**：宿主范围核验显示 Ubuntu-24.04 WSL VHD 位于 Windows `C:` 宿主卷，而该卷只剩 `827174912 B`。健康状态为 `Healthy/OK`，但空间风险足以阻止 R1 账本迁移和正式计算。

| 评审轴 | 当前结果 | 证据与边界 |
|---|---|---|
| source / 工作树 | `9aeee371d3ad8a3fcfcc776bd13e5e2c10518e77` / `task39extra` | canonical linked worktree 已登记；本轮没有源码数值改动 |
| 模型身份 | 13.5 nm、p6/h10、Full3D、80 DtN modes、MPI1、complex128/int32 | 沿用 V14 physical/mode identity；没有新 p/h、Hybrid、M 或 MPI 结果 |
| R0 写入探针 | `PASS_WITHIN_RESTRICTED_SANDBOX_VIEW` | ledger/results 各两轮、每轮 `4194304 B`，共 `16777216 B`；hash、rename、fsync、清理均通过，但 sandbox PID/`/mnt/c` 视图不代表宿主全局 |
| 宿主范围核验 | `BLOCKED` | 33 个进程 PID 条目中 `old_q0_matches=[]`；当前无旧 Q0 匹配，但 `historical_cleanup_proven=false` |
| 承载卷 | C: NTFS，`407550365696 B` 总容量，`827174912 B` 剩余，`Healthy/OK` | Ubuntu-24.04 注册路径为 `C:\Users\admin\AppData\Local\wsl\{bb298883-9031-4854-a46f-fe067cfd0cb8}\ext4.vhdx`；上述容量/余量属于承载卷，不是 VHD 文件大小 |
| D: 卷 | `540298133504 B` 剩余 | 本轮没有使用、搬移或改变 D: |
| V14 formal Q0 | `partial_observation` 保留 | 最后可靠阶段仍为 `setup`；parent `EIO`、缺失 worker 终态和 373 个有效 watchdog 前缀不改判为 solver pass |
| V15 R1 / PDE | `not_run` | 没有 ledger migration、新 Q0、Q1/Q2、Q3–Q6 或 official p6 output |

## 本轮预算与科学结论

| 项目 | 数值/状态 | 口径 |
|---|---:|---|
| 总预算 | `43200 s` | V14 总批次上限不变 |
| 旧 Q0 实际耗时 | `unknown` | 原 ledger `elapsed_seconds=0.0` 是未结算字段，不是零耗时；不能写成 `600 s` 实测 |
| 旧预留的政策责任 | `600 s` | 不返还责任；本轮未正式写入真实 ledger |
| R0 已知收集时间 | `2.387310507 s` | sandbox UTC `0.497441 s` + 宿主只读 UTC `1.889869507 s`；属于应计原总预算的准入费用，尚未写入 ledger |
| 已知最低预算责任 | `602.387310507 s` | `600 + 2.387310507`；未测保存/审核时间仍 unknown |
| 剩余预算上界 | `42597.612689493 s` | 只是上界，不是继续运行许可 |
| 真实 ledger | `RESERVED`, `active_attempt=0`，SHA 前后均为 `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0` | `old_ledger_snapshot.json` mode `0444`；formal policy debit、R1 migration 均 false |

准确 Schur 的内存问题仍为 `inconclusive`，因为 Q1 全局直接法和 Q2 准确 Schur 没有配对完成；唯一接口近似逆仍 `not_qualified`，因为没有三 RHS/p6 admission；下一方法不变，先处理宿主存储并按后续指令复核 V15 准入。这个停止是基础设施边界，不是算法失败。

历史正式模型的统一 R/T/A、`A_volume`、衍射、DoF/NNZ、峰值内存和分阶段时间仍见下方 V14/V13/V12 表；本轮没有产生新的 R/T/A 或 `A_volume`。Full3D/Hybrid、p/h、M 和 MPI 的历史结果不得被本轮 `not_run` 状态替代，也不得用历史数值填充本轮 Q1/Q2。

## 证据入口

完整逐项回应见 [response_v16](../response_v16.md)；机器记录见 [V15 I/O compact](records/v14_io_recovery_v15.json)、[V14 compact](records/p4_schur_v14_compact.json)、[comparison](records/p4_schur_v14_comparison.json) 和 [run index](records/run_index.json)。原始 R0 报告 SHA 为 `d61561d645073565db1206bbdacd74faf66007c55e26fb2201e2ee793dd2da5f`；宿主范围 JSON SHA 为 `0485560050ed880dca11a87fda4d853f3db1ecc3f4cefbd7e045838878d696dc`。旧窗口 journal 命令没有明确 UTC 基准，不能证明覆盖 `2026-09-12T12:35Z` 故障窗口；保存的 orphan/recovery/journal 行不证明 EIO 根因。

本轮新增内容只属于 compact evidence/docs。未执行的 R1 草稿、ignored raw、大型 field/matrix/factor/timeline、原 ledger 和任何凭据均不进入 Git 或 master；合入边界见 [V14 selective manifest](selective_merge_manifest_v14.md)。

# Task39extra Review V14 当前阶段：Q0部分证据，Q1/Q2待可用记录

| 阶段 | 当前状态 | 证据边界 |
|---|---|---|
| Q0 `Q0_CORE` | `partial_observation` | 仅完成 preflight、公共预分配门、fine quadrature 和 P64 transfer；最后 phase 为 `setup`；没有 RHS、原 A4 residual、field L2、scaled-curl 或 Q0 完成摘要 |
| Q1 `Q1_FULL_DIRECT` | `not_available` | 当前工作区没有 Q1 run directory 或终态记录；不复用 V5/V13 数值 |
| Q2 `Q2_SCHUR_DIRECT` | `not_available` | 当前工作区没有 Q2 run directory 或终态记录；不复用 V5/V13 数值 |
| Q1/Q2 memory comparison | `COMPARISON_INCONCLUSIVE` | 没有配对的完整 RSS/PSS、inventory、factor-live repeated apply、setup/cleanup 与 residual/field/curl 数据，不能回答准确 Schur 是否省内存 |
| Q3–Q6 | `pending_review_v14_continuation` | 工程实现和测试继续，正式准入未完成；不提前结项、不修改 ledger、不进行 PDE replay |

Q0 的唯一现有目录、I/O 故障、373 个有效 watchdog 前缀样本及全部 SHA 见 [阶段 response_v15](../response_v15.md)、[V14阶段记录](p4_schur_v14.md)、[Q0–Q2 compact](records/p4_schur_v14_compact.json) 和 [comparison](records/p4_schur_v14_comparison.json)。这次 parent launcher 在写 `run_manifest.json` 时遇到 `EIO`，ledger settlement 读取时再次遇到 `EIO`；这是已知工程 I/O 故障。有效前缀没有触发资源 Gate，但 worker 终态缺失，最终数值/资源分类为 `not_available`。共享 ledger 原样保持 `RESERVED`，所以 `elapsed_seconds=0.0` 不被解释为零消耗。

---

# Task39extra V13 续算当前总览：三输入完整诊断与未资格化的接口提案

| 评审项 | 当前结果 | 具体边界 |
|---|---|---|
| P0 / 续算身份 | 已资格化身份复用 | 01 复用 Z/AZ 和42个局部响应；不重建参考、不重做未受影响的 ABI/MUMPS/metric 资格 |
| P1 / P2 / P3 | 三输入全部完成 | 01、02、09 各 actual / best-Z residual与field / scaled-Z / best-L residual与field / selected-L10，完整向量与恒等式已保存；P1/P2 均先于 P3 原子发布 |
| 当前 PC 内部质量 | 局部回代与分解准确，全局修正仍弱 | 局部回代最大相对误差3.941e-14；actual 三输入场误差约0.965、0.878、0.993 |
| 两个便宜候选 | strong-action 均 false | 困难01/09均未让场误差减半；02残差还超过 actual 的1.1倍；不能用参考辅助场最优替代真实残差 |
| P4 优先项 | PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN | 架构选择 confidence=medium；新PC性能 confidence=low，尚未实现或资格化，非生产默认 |
| 正式费用（含既有失败与只读核查） | 2160.401528466149 s / 原7200 s | 外层续算保守计费1204.4717857759497 s；工程修复时间单列，未清零或延期 |
| 新诊断工作集 | 保守估计369,795,024 B < 536,870,912 B | 含QR/SVD临时副本；旧256MiB负结果仍保留 |
| 其他内存 | 局部保守库存2,180,383,916 B；同时树RSS采样峰值3,287,973,888 B | 局部库存上限2.5GiB、原临时预留1GiB和整机reserve/watchdog不变；job swap与全局交换增量均0 |
| restart / original / notch / official物理 | 本批 NOT_RUN | 不补R64、不启动p6长跑；原A6最终1e-6及完整物理Gate未放宽；5nm线不变 |

source 为 `3457b5e2f54dec690fcb70deb1f387fe7f6d57cd`，continuation base 为 `07b77c49e65f725f2b8bf00189777ef7f833f1c2`，Review V13 base 为 `1ebe076df8dc1052c5a7ec5ad3d391957ad6c94f`。一次必要 fresh42 构建300.807805 s，三输入阶段216.485850/272.964772/272.377783 s；各时间嵌套于父workflow，不能重复相加。

“接口多层”拟先消去块内部未知量，再对共享行和DtN辐射边界作全局修正。提案明确了真实复物理Schur作用、局部奇异方向与DtN通道、容量受限层级和固定一次周期；它付出新的内部因子与谱setup成本，目前没有性能实测。best-L场误差可到0.213/0.146/0.195但残差为86.7/3.16/110，说明响应含有有用信息，而无参考的经济选择尚不合格，不能推断没有折中组合。

完整表、范数定义、反证和下一original/notch计划见 [统一 response_v14](../response_v14.md)、[方向诊断](p4_direction_diagnosis_v13.md)、[可执行蓝图](next_method_blueprint_v13.md)、[decision](records/next_method_decision_v13.json)。[续算 compact](records/p4_direction_diagnosis_v13_continuation.json)保留完整精度；[provenance](records/p4_direction_diagnosis_v13_continuation_provenance.json)、[向量审计](records/p4_direction_diagnosis_v13_continuation_audit.json)、[资源审计](records/p4_direction_diagnosis_v13_resource_review.json)绑定原始证据。旧失败、旧256MiB停止、V5成功参考及V6–V12负结果均保留。所有新数值路径仍为 research-only，等待 ChatGPT review，不合并 master。

---

> 以下保留续算之前各版本的历史时点；旧文中的“当前/本轮/最新”仅指当时，不覆盖上面的续算结果。

# Task39extra Review V13 最新结果：P0通过，P1/P3部分证据，诊断账本受控停止

本节是当前权威收口；V12 及更早章节保持历史。V13 使用固定原始13.5 nm物理模型、p6/p4 map、MPI1 和三份输入 `A2R160/01`、`A2R160/02`、`LIGHT448/09`。它没有完成三输入 P0–P4，也没有产生 official Maxwell 输出。

| 轴 | 当前结论 | 证据边界 |
|---|---|---|
| P0 输入身份 | `PASS` | 三份 `g/c_ref/A4c_ref`、map、旧四步包、有限非零 `r_ref` 均可读；物理/模式 hash 保持冻结 |
| P0 metric | `PASS` | direct/pullback mass/curl 最大输出差约 `2.9e-15`；固定正 D 已落盘；probe 已归一化 |
| P1 | `PARTIAL` | 仅 A2R160/01；4 个真实 counted right-PC 输出、rank4、重建 `2.873e-16`；02/09 `not_run` |
| P2 | `INCOMPLETE` | 01 的局部 response 参与了 P3，但完整 `a/d/t`、`D_i d_i`、`D_iR_i e_h` packet 未落盘，三输入阶段表 `not_run` |
| P3 | `PARTIAL` | 01 的42个 A像和 `A_a/A_t` 落盘；full 48列残差 rho=`0.935877`、rank47；selected 10列 rho=`0.967891`、rank10；eta/curl unavailable |
| 资源 | `DERIVED_UNCERTIFIED` | 明确同时存活下界 `273571328 B` > 256 MiB新增诊断 cap；不是RSS cap违规，也不是OOM |
| P4 | `DECISION_DELIVERY_INCOMPLETE` | 唯一下一项 `IMPLEMENTATION_OR_METRIC_REPAIR`；不选D、selective或接口重设计生产路线 |
| official physics | `not_run` | p6/original/notch、E/H、R/T/A、A_volume、衍射、守恒均未运行 |

V13 的完整叙述见 [P4诊断](p4_direction_diagnosis_v13.md)、[response V14](../response_v14.md)、[下一方法蓝图](next_method_blueprint_v13.md)。机器记录见 [P4 compact](records/p4_direction_diagnosis_v13.json)、[offline audit](records/p4_direction_diagnosis_v13_offline_audit.json) 和 [memory liveness](records/p4_direction_diagnosis_v13_memory_liveness.json)。

---

# Task39extra Review V12 supplement 最新结果：构造通过、完整 PC 排除、R64 主动停止

本节是 V12 bounded supplement 的最新总览；下方原 V12 O0–O4 表格和更早版本均保留为历史。续算没有追加 O3 original/notch 验证，也没有改变既有 runner/schema/flag。

| 结论层级 | 最新结果 | 证据边界 |
|---|---|---|
| local construction / inventory / transfer / I4 coupling | `measured_and_audited` | O1 fresh source `7d9df5e…` 完成 42/42 physical blocks、18 个 C_U internal-response classes、C_U/W transfer、84 witnesses；inventory `759/0`，p4 `132/0`，shared `96/0` |
| shared-q selection | selected `BAL_H`；ONE_C 切换条件 `gate_pass=false` | A2R160、JOINT448、LIGHT448 三组 matched comparisons；residual geometric mean `1.0240463212446451`，超过 1.0 threshold；L2 geometric `1.000603999343256` 也超过 `0.8`，但 curl、最大 field 和累计 time 条件通过；这不是 O1 workflow 失败 |
| complete PC efficiency | `negative / unqualified` | repaired R32 source `d39261bb…` 完成 64 outer steps，final full explicit true residual `0.7666389832389989`，未达 A6 `1e-6`；field diagnostics 不能改变此结论 |
| inherited first R32 | `WORKER_FAILED` / `partial_checkpoint_evidence` | 已保存 8/16/24 residual=`0.8283760020203784/0.8172376273064963/0.811621467511064`；candidate unavailable、restart comparison incomplete；TypeError 是工程失败 |
| R64 | `USER_CONTROLLED_STOP` / `partial_checkpoint_evidence` | 已保存 8/16/24 residual=`0.8283760020203784/0.8172376273064963/0.811621467511064`；candidate unavailable、restart comparison incomplete；不能写成 numeric failure |
| official Maxwell | official fields/power 与 O3 formal verification `not_run` | R32 已在原始 A6/b 上实测 full explicit residual `0.7666389832389989`，相对 `1e-6` gate 为 `measured_not_met`；official field/power recovery、O3 original/notch、E/H、near-field、R/T/A、`A_volume`、modal/diffraction/conservation 仍未运行；A6 gate 未放宽 |

## Supplement formal ledger

O1 fresh charge `601.0369560300772 s`、继承的首次 R32 工程失败 `1028.6465685711235 s`、修复 R32 `1846.2808846201353 s`、停止 R64 `885.4244810280746 s`，合计 `4361.38889024941 s`，剩余 `6438.61110975059 s`。最终 continuation ledger SHA 为 `74a863666e4b299002306f505d070ff248847c9e7c91d1bc97494beec2b6c329`；旧原始 ledger SHA `af72d67ab51af205841c4757de5b7413ed2f6ddccbbf8c5a92bc4ccbe633d5fe` 保持不变。

源码身份是分段的：O1 fresh summary/terminal 绑定 `7d9df5e19d324776588aaa9efc4996cc3fe36d8e`；修复 R32 和 R64 绑定 `d39261bb17e8d9042c03d4d4990258da5043b621`。最终文档 HEAD 不替换 formal run source。

## O1 six p4 controls and three shared comparisons

O1 的 6 条 calibration record 均为 4-step I4、4 次 B4、3 次显式 A4，并以 `INNER_APPROXIMATE_RETURN` 返回：

| record | true residual | field L2 | scaled curl |
|---|---:|---:|---:|
| A2R160/01 | 0.9502310252350668 | 0.9647147926182198 | 0.964639027200986 |
| A2R160/02 | 0.1012649488434464 | 0.8777570760481551 | 0.8773717677729929 |
| LIGHT448/09 | 0.9778952412775763 | 0.9928176043406823 | 0.9928022756707928 |
| LIGHT448/10 | 0.10194959659698315 | 0.8775511199054001 | 0.8771869820432219 |
| JOINT448/17 | 0.9734051084398233 | 0.9806440886743487 | 0.980603344241886 |
| JOINT448/18 | 0.1011280660537276 | 0.8789881692075479 | 0.8786124210764896 |

三组 `ONE_C/BAL_H` ratios 分别为：A2R160 `time=0.6326677621909856`、`residual=1.0338976430017037`；JOINT448 `0.6375811337022439`、`1.0205035889757637`；LIGHT448 `0.640273569147282`、`1.0178100236981422`。field ratios 都约为 `1.0003–1.0010`。因此 `BAL_H` 是有效选择；未通过的只是 ONE_C switching gate，不是 O1 workflow failure。修复 R32 的 128 次 I4 中 `0/128` 达到内部 `1e-4` target，最大 I4 elapsed 为 `10.24374708600115 s`。

修复 R32 的 32/64 节点对照为：node32 full residual/field L2/scaled-curl=`0.8025891203479081/0.9384007607744688/0.9382432819659642`，node64=`0.7666389832389989/0.9488237463600627/0.9486448577201997`；residual 下降但 field error 变差，故 residual 与 field gate 都是 `measured_not_met`。最后 coupling closure relative 为 `1.4796776236757317e-13`（limit `1e-8`）；inventory allocated/used/retained=`1671000000/888000000/2180383916 B`，local cap=`2684354560 B`。

## 资源、历史对照和测试边界

O1 fresh process-tree RSS/PSS peak 为 `3250446336/3215799296 B`（2137 samples，PSS 全可读）；继承的首次 R32 工程失败为 `2534461440/2499849216 B`（3654 samples，PSS 全可读）；修复 R32 为 `3350794240 B` RSS、可读 PSS 最大 `3316318208 B`（6540 samples，但有一个 exit-phase PSS 缺样）；R64 为 `2552774656/2517919744 B`（3133 samples）。四者 swap 均为 0、后代均清场。这些是 sampled simultaneous process-tree measurements，不是连续峰值或 workstation capacity。

修复 R32 的 8–64 checkpoints 和历史点见 [comparison SVG](charts/v12_supplement_comparison.svg)、[PNG](charts/v12_supplement_comparison.png) 与 [history audit](records/v12_supplement/audits/task39extra-v12-supplement-history.json)。图只绘制 repaired R32 与历史对照，不含 R64 时间曲线；setup、outer、field-diagnostic 的采样频率和时钟口径不同，不能读作连续效率曲线。

修复后 focused regression 为 `51 passed`，另有 2 个 field-metric smoke tests；qualified ABI 为 complex128/int32、MPI1、线程1。最终只读 budget audit 为 `errors=[]`。full repository pytest 和 CI 均 `not_run`。

证据入口：[supplement README](records/v12_supplement/README.md)、[center](physical_macro_v12.md)、[response V13](../response_v13.md)、[compact](records/physical_macro_v12_compact.json)、[run index](records/run_index.json)、[continuation ledger](records/v12_supplement/core/repair_continuation_ledger.json)。当前仍为 research-only、`ordinary default unchanged`、`NOT_APPROVED_FOR_MASTER_MERGE`。

---

# 历史：Task39extra Review V12当前结果：42块物理宏块完成，p4控制受共享预算停止

V12 在 `physical_macro_dd4_v12` 与 `2684354560 B` 局部库存 cap 下完成 O0、42/42 physical macro block numeric inventory、84 witness recount、cached/native bridge、C_U/W transfer 记录及 4 条有限 p4 I4 控制；随后 O1 因共享 O0/O1 保守预算耗尽而 `PERFORMANCE_CONTROLLED_STOP`。42 个宏块各有独立 numeric factor record；另有 18 个 C_U 元素内部响应类因子，二者不是同一计数。

| 范围 | 当前结论 | 证据口径/边界 |
|---|---|---|
| 身份 | source `e8c3c82bab2687a811a11f0798a2879c725532b5`；13.5 nm、p6/h10、Full3D、MPI1、80 modes、complex128；physical/mode SHA 与 p6/p4 size 见 compact | V12 hash-bound；不是 official PDE output |
| O0 | `O0_PRECHECK_COMPLETED` | 2.0600177589932294 s；RSS 147095552 B；swap 0；descendants cleared |
| O1 coverage | 42/42 numeric blocks；84 witnesses；covered rows 48960；max local residual `2.1772149386553977e-15`；6 native witnesses max `8.243915633632588e-16` | 局部质量和构建证据，不是 p4/p6 收敛 |
| bridge/C_U | cached/native relative `2.787784119354311e-15 < 1e-11`；C_U/W inventory recorded | C_U closure scalar `not_persisted_not_verified`；未执行完整 BAL_H/ONE_C outer |
| p4 controls | 4 persisted records；每条 4 I4 B4 calls、3 explicit A4；I4 residual `0.1012649488434464`–`0.9778952412775763` | record 名称中的 BAL_H 来自历史 packet；本轮只做 bare B4/I4 内部检查；field L2/curl 仍约 0.878–0.993 |
| O1 stop | `PERFORMANCE_CONTROLLED_STOP` | shared O0/O1 charged `7201.319691806935 s` vs 7200 s；不是 OOM 或 solver exception；tree RSS/PSS 2574671872/2539922432 B，swap 0 |
| O2/O3/O4 | O2/O3 `not_run`；O4 `O4_FINALIZED` | O1 未完成且无 framework selection；O4 无新 reference solve/factor |
| official fields | `not_run` | p6 original/notch、A6 `1e-6` true-residual gate、E/H、R/T/A、`A_volume`、modes、diffraction、守恒均未检验 |
| 当前决定 | `NOT_APPROVED_FOR_MASTER_MERGE`；ordinary default unchanged | V5 原始/notch成功 baseline 与 448 页 global `pswpout` attribution `UNRESOLVED` 保持历史边界 |

四条 p4 的 bare/I4 residual 与 field error 对照、精确资源口径和 raw/hash 入口见 [V12 中心结果](physical_macro_v12.md)；机器记录见 [V12 compact](records/physical_macro_v12_compact.json)、[lossless raw JSON evidence](records/v12_raw_json_evidence.json)、[p4 audit](records/v12_p4_supervisor_audit.json) 和 [resource audit](records/v12_resource_supervisor_audit.json)。测试结果见本目录的 [test summary](test_summary.md)。大型 matrix/factor/field/cache/timeline 仍在 ignored artifact root，不进入 Git。

---

# 历史：Task39extra Review V11当前结果：N1 policy equivalence pass，N2 retained-inventory controlled negative

本节是当前权威摘要。V11 验证显式 `physical_macro_dd4_v11` / `SYMBOLIC_SIZED_LOCAL_MUMPS_V11`：局部块把附近未知量组成小矩阵，先做局部分解并保留因子，再用于局部回代。新的 workspace 请求由 symbolic-sized MUMPS 信息计算，不能用 used/min/RSS 替代。V10 旧策略和 ordinary default 保持不变。

| 范围 | 当前结论 | 证据口径/边界 |
|---|---|---|
| 身份 | source `7c936958451bc196f784ecc30db9278c4e5b402f`；13.5 nm、p6/h10、Full3D、MPI1、80 modes、`complex128`；physical SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` | V11 N0–N2 hash-bound run；不是 official PDE output |
| N0 | qualified activation、PETSc/MUMPS 5.6.2 identity、手册语义和 public controls 已核验 | `/usr/lib/x86_64-linux-gnu/libpetsc_complex.so.3.19.6`、`libzmumps-5.6.1.so`、`libmumps_common-5.6.1.so`、`libmpi.so.40.30.6`；`ICNTL(23)` 可读回；公开 `ICNTL(49)` getter runtime error 62，setter source verified |
| N1 | 两个冻结代表块 old/new policy equivalence PASS | 4 numeric factorizations；最大 local residual `5.438606648780365e-13`；same-RHS solution diff `0.0`；最大 solves/factor 6 |
| N1 memory fields | block 0 old/new allocated `262/53 MB`、used `29/29 MB`；block 1 old/new allocated `261/51 MB`、used `28/28 MB`；old/new ICNTL23 `490/73`、`491/71 MB` | decimal padded fields；used 并列保存，不并入 retained inventory |
| V11 policy | `E=1e6*(1+max(INFOG16,17))`；`Q=1e6*ceil(max(32MiB,2E+8MiB)/1e6)`；设置并读回 `ICNTL(23)=Q/1e6` | 无 used/min/RSS offset；无提高 2 GiB、1 GiB、512 MiB cap |
| N2 | 41/42 blocks 完成 numeric/backsolve；block 41 在 numeric 前被 local resident workspace Gate 阻断 | retained `2,132,081,608 B` + block41 matrix `7,128,340 B` + Q `39,000,000 B` = `2,178,209,948 B` > cap `2,147,483,648 B`，超 `30,726,300 B` |
| N2 语义 | `LOCAL_INVENTORY_RESOURCE_BLOCKED` | 不是 system OOM、MUMPS `-9/-19` 或 Maxwell convergence failure；block41 没有 numeric |
| N3/N4 | `not_run_by_N2_gate` | restart32/64、BAL_H/ONE_C、cached-native/map、p4 true error、original/notch、E/H/R/T/A、official output 均未运行 |
| ledger | charged `4857.702833182024 s`；remaining `2342.297166817976 s` | independent V11 N0–N2 ledger；exact N1→N2 handoff included once；N5 docs time separate |
| 当前决定 | N5 closeout：`LOCAL_INVENTORY_RESOURCE_BLOCKED` | 不重跑、不调参、不扩 MPI、不改 cap；重开需新 review、预算和 identity |

中心结果见 [V11 macro memory lifecycle](macro_memory_lifecycle_v11.md)，紧凑记录见 [V11 compact](records/macro_memory_lifecycle_v11.json)，其 SHA256 为 `14df814fe9b59e8dcdfee89a835837318d936d59ac45d060cc6085113845f5e2`。选择性合并边界见 [V11 selective merge manifest](selective_merge_manifest_v11.md)。V10 及更早成功/负结果在下方按历史保留，不因 V11 局部证据改判。

---

# 历史：Task39extra V10结果：macro inverse M1 受控资源负结果

以下是 V10 历史摘要，保留其原始局部证据和负结果；当前授权以本文件上方 V11 节为准。V10 的 M0/M1 只推进到局部 macro factorization；第二次 M1 在冻结的局部常驻预审策略处停止，未进入 M2/M3。V9 以及更早的成功/负结果在下方按历史保留，不因 V11 局部证据而改判。

| 范围 | 当前结论 | 证据口径/边界 |
|---|---|---|
| 输入/身份 | 13.5 nm、p6/h10、Full3D、MPI1、80 DtN modes、`complex128`；80 modes 是冻结输入合同，不是完整新 macro identity 的证明；source `b0df7457c0c4b33c66abda16862926da3426bb7d`；input SHA `f6a3bc446fa7ce34a446e6a52f07be4a3841df649272fae6164f1ecfaca3dd66`；physical SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` | hash-bound measured identity；非 official PDE output |
| M1 第一次尝试 | source `99428016a73fdbb29f6531974ed1ee4756d96bbc`；native DtN 已构建，代表块选择逻辑抛出 `ValueError`，I4/B4=`0/0` | `REPRESENTATIVE_SELECTOR_FAILURE_BEFORE_LOCAL_FACTORIZATION`；随后已窄修并保留 raw |
| M1 第二次尝试 | 42 blocks；局部 cache retained=`45,710,148 B`；block 0–7 进入矩阵/数值阶段；block 7 后触发 resident policy | `RESOURCE_BLOCKED` / `LOCAL_INVERSE_UNQUALIFIED`；不是系统 OOM |
| 内部质量轴 | block 0–6 保存 14 次回代，最大相对残差=`2.0002787934351233e-15`；代表块 native witness 6 次，最大=`8.243915633632588e-16`；p4 true error/residual 未测 | `PARTIAL_PASS`；block 7 回代值、cached/native bridge 和完整 p4 误差均未持久化/未运行 |
| 局部阶段 partial observables | blocks 0–7 symbolic=`0.13301346899970667 s`、numeric=`0.8125463649976155 s`、matrix NNZ=`5,379,856`、raw `INFOG(3)=INFOG(9)` factor entries=`5,796,240` | 从 stages facts 汇总；回代耗时/缓存加载=`UNKNOWN`，全局粗层/Krylov/后处理=`not_run` |
| 框架耦合轴 | `verify_recursive_map`、6 个 g calibration、BAL_H/ONE_C 均 `not_run` | `FRAMEWORK_COMPARISON_LIMITED`；局部小残差不能代替全系统纠错质量 |
| restart 轴 | restart32/64 均 `not_run` | `RESTART_DIAGNOSIS_LIMITED`；旧 ENTITY16/g1 不作本轮证据 |
| policy 触发 | `resident_before_factor=1,982,365,908 B`；block 7 allocated factor=`261,000,000 B`；精确保守累计=`2,243,365,908 B`；2 GiB cap 超出=`95,882,260 B` | derived conservative allocation policy；不等于实测常驻或系统 OOM |
| 实测资源 | process-tree RSS 峰=`1,107,648,512 B`；job swap peak=`0 B`；descendants cleared | measured；系统资源 Gate 未触发 |
| M2/M3/official | original、notch、E/H、R/T/A、`A_volume` 均 `not_run` | 前置 M1 Gate 未通过，不能写 solver/physics PASS |
| 总成本轴 | 账本已记录 preparation=`1281.5 s`（截至 `2026-09-10T12:14:07.163Z`）+ 两次 M1 终态=`380.27739690501534 s`，合计 charged=`1661.7773969050152 s`、nominal remaining=`3738.222603094985 s` | 12:14 之后的 repair、测试和 M4 文档未完整计入；complete total cost=`UNKNOWN` |
| 当前决定 | 停止 V10 candidate；不调参、不改块、不改 MPI、不换 used 值绕 Gate、不重跑；ordinary default 不变 | M4 closeout；唯一主要缺口是完整新局部逆尚未跨过 allocation 预审 |

四条证据轴分别为：内部质量轴（局部 partial，p4 true error/residual 未测）；框架耦合轴；restart 轴；总成本轴。完整中心说明见 [V10 macro inverse 结果](physical_macro_inverse_v10.md)，机器可读证据见 [V10 compact](records/physical_macro_inverse_v10.json)。

---

# 历史：Task39extra V9当前结果：等新工作量复用对照为受控负结果

本节是当前权威摘要。V9 的 L1 以每次 I4 最多 16 个新 B4/Arnoldi 方向隔离新搜索量；12 个 sequence I4 加 4 个 complete-control I4 共 16 次，L2 原始模型的 76 次 I4 也全部完成该上限，但完整外层在首个约 1800 s 安全检查点仍未达到绝对进展门槛。`WORKER_FAILED` 是 runner 对 worker exit 4 的 parent 分类；独立 checker、watchdog 和资源 authority 仍分别保留。

| 范围 | 当前结论 |
|---|---|
| L1 equal-new-work | 12/12 sequence rows 完成 16 新 B4，另有 4 个 complete-control I4；总 I4=`16`；6 对、5 对进入统计；全六行累计 RESET/CARRY=`96.98303711495828 / 112.19278895820025 s`（CARRY 多 `15.68%`）；`G=0.4822327326491708`、q<1=`0.8`、qmax=`1.5802611912316964`；`L1_ADMISSION_OPEN` |
| L2 original | PC38；首个安全检查 solve=`1842.2495024400364 s`，full explicit true residual=`0.1292009191903606 > 0.10`；`TIME_PROGRESS_SCREEN_STOP` / `EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE` |
| 等新工作成本 | 76 I4、B4=`1216`、`A4_matvec=1292`、`explicit_A4=168`；每行 completed_new_B4=`16`，discarded=`0`；最大 I4=`21.477697932044975 s` |
| 内部 payload | instrumented peak=`90099456 B`，cap=`134217728 B`；最终持久池=`12533760 B`；这些是 derived ledger，不是 full-process RSS |
| 资源 | process-tree RSS 峰=`1426276352 B`，job swap peak=`0 B`，global pswpin/pswpout delta=`0/0`，descendants cleared；不是资源阻断 |
| official/notch/recovery | `not_run`；没有 E/H、near-field、R/T/A、`A_volume`、80 模式输出或 notch/recovery |
| 账本 | L0 partial=`1.853111845 s`；L1 charge=`530.530732766 s`；L2 outer charge=`2071.995232478 s`；总 charge=`2604.379077089 s`，余=`33395.620922911 s`；总额不含未知的完整实现准备时间，不能完整追认 `3600 s` preparation Gate；`14400 s` reservation 与 elapsed 分开 |
| 当前决定 | 不重跑、不启动 notch/新候选、不扩 rank/参数、不启动 workstation heavy；ordinary default 不变 |

V9 的 PC32 residual=`0.1312380111087104`，到 PC38 仅降至 `0.1292009191903606`，约 `1.55%`（derived）。V5/V7/V8 的同时间或同步数 scalar 仍按历史 measured 记录并列，不能把终点差异解释为 solver speedup。V5 双模型成功 baseline、V6/V7/V8 controlled negatives、旧 checker 和 ignored raw 均保持不变。

机器可读证据为 [V9 compact](records/equal_work_recycled_p4_v9.json)，完整中心说明见 [V9 equal-work 结果](equal_work_recycled_p4_v9.md)。它绑定 L1/L2 raw、terminal solution/checkpoint、checker、watchdog、ledger 及逐 I4 标量 hash；不嵌入 field/matrix/factor 大数组。

---

# 历史：Task39extra V7 J5当前结果：两条 bounded 候选均关闭为 controlled negative

本节是当前权威摘要；本节以下的 V6、V5 及更早内容全部是历史记录，保留原始负结果和资源限制，不应按其中旧的“当前/下一步”文字重新授权运行。

| 范围 | 当前结论 |
|---|---|
| 任务范围 | 完成 V7 J1 finite/control 与 A/B 两条冻结 bounded outer；J5 仅文档和紧凑证据收口 |
| V7 A | `bounded_entity16_v7`：121 步，中点 full explicit true residual `0.04256451212826674`，`PROGRESS_INSUFFICIENT_AT_MID_BUDGET` |
| V7 B | `bounded_projected_seq2_16_v7`：88 步，中点 full explicit true residual `0.06385558342151046`，`PROGRESS_INSUFFICIENT_AT_MID_BUDGET` |
| B finite | 输入 unchanged、slave constraints 通过、seq2 explicit relative `0.0`；2 个 complete PC 和 4 个 I4 控制通过，`J2_ADMISSION_OPEN` |
| V5 baseline | 原始 564 步、notch 576 步完整成功仍保留，是本任务唯一双模型 complete success baseline；R/T/A=`0.365625791/0.0129906323/0.621383577`、`0.337120585/0.0162886742/0.646590741`；whole `6997.531 s` / `7058.7424 s`，RSS `3466235904 B` / `3600924672 B` |
| V6 | 递归粗逆仍为未资格化负结果；真实难误差定位属于 `response_v6` 历史补充授权，不是本轮 V7 新结果；不改写、不重跑、不升为 production default |
| official output | A/B fields、R/T/A、`A_volume`、near-field、衍射级和 notch 均 `not_run`，不是 physics mismatch |
| 当前决定 | 只关闭 entity16 与 projected seq2 两条冻结候选，不能推出所有无 global p4 LU 方法不可能 |

逐 8 步 residual 曲线、实际调用成本、资源口径、finite audit 计数差异及 raw hash 见 [V7 中心结果](bounded_inexact_outer_v7.md)。机器可读记录见 [A compact](records/bounded_inexact_outer_a_original_v7.json)、[B finite compact](records/bounded_inexact_outer_b_controls_v7.json) 和 [B original compact](records/bounded_inexact_outer_b_original_v7.json)。

| 资源/账本 | A entity16 | B projected seq2 |
|---|---:|---:|
| process-tree RSS peak | `1449623552 B` | `1517813760 B` |
| process-tree swap peak | `0 B` | `0 B` |
| global swap delta | `0/0` | `0/0` |
| parent/whole conservative | `5637.122687149011 s` | `5622.279368720655 s` |
| shared ledger after both | — | charged `12327.598368146999 s`; remaining `30872.401631853 s` |

两次 RSS 均低于 2 GB，但对应的是未完成 outer 的受控进程树观测，不能写成 2 GB 成功 PDE。B 的 p2 `rows=7326`、`NNZ=818100` 和 factor budget 是 derived policy budget，不是 RSS 上界；全局 p4 matrix/factor 未使用。

本轮没有新的 heavy case、checker/production 修改或 workstation 0.7 nm 授权。source HEAD 仍为 `355322e8be0716cdc3dd70df2665b8c74ff76583`，分支 `task39extra` 与 `origin/task39extra` ahead/behind `0/0`；文档和 compact 待审阅后再提交推送。

---

# 历史：Task39extra V6递归粗逆未资格化，V5双模型成功基线保留

最新补空间诊断：单个p4内部RHS从64步残差0.03132214953分段接续至256步0.0003738177529，改善83.7899倍但未达1e-4。新增192 B4/384 S、0精化；两次parent实际计费240.039471秒，第二次为时间受控停止，不能写预算PASS。局部检查通过、固定方向块外耦合与权重项存在抵消，不据此改权重。G5仍开放，V5双模型成功不变；见[简明证据](recursive_p4_complement_diagnostic_v6.md)及[compact](records/recursive_p4_complement_diagnostic_v6.json)。以下旧阶段文字保留。

当前实测：9dbf12355e6e6c7eac23d055c12da4e7eda2a7d8唯一owner-route组件60步，native true0.008002412387388793>1e-4，M0/curl场误差0.002380888345/0.002379682686。三owner桥和same-g B4差均0；11502项核验通过的是合法负结果。父106.718187118s、RSS911257600B、swap增量0、35PID清场；G5开放。后续仅考察共享edge/face局部耦合的只读预审，未实现或启动新求解。旧阶段文字如下保留。

最新补记：348373缓存组件已测42步，native真残差0.029242939406004885>1e-4，M0/curl场误差0.008839885/0.008835480；保留未达目标分类。三向量只读owner路由对照逐位相同，支持仅MPI1固定索引优化；现已实现显式opt-in并通过同一最小fixture（1 passed），额外预算4117888B，默认/MPI2及数值流程不变。本次未启动正式计算，生产桥与新I4均未运行，等待监督审阅，G5开放。下文旧状态按历史保留；最新细节见[中心补记](coarse_inverse_replacement_v6.md)。

最新完整高阶实体组件（564e42b43391f1857934ef064778636aff06894b）：原60s I4在22步停止，true=0.134111120未达1e-4，但M0/curl场误差已降为0.040714718/0.040705987，是继续定位的正信号。11430项raw核验通过；cold保守115.004649472s、全树RSS峰883875840B、swap增量0、全部进程退出。三冻结向量的缓存体积+原端口对native A4差异均<1e-11。仅实现同数学性能优化待审，显式残差继续由native A4负责；未重跑I4或关闭G5。[中心证据](coarse_inverse_replacement_v6.md)、[compact](records/p4_causal_research_v6.json)。

此前内部响应定位（55a795e5b31b5c6b0323b92c517f6e989faf5803）：Eg仅占原误差M0/curl范数0.003091639/0.003815295；内部方程消去相对误差1.2834e-14，但全dual残差比1.637625109，不能称solver通过。129项raw检查通过；保守流程9.496253621s、同时全树RSS峰251469824B、swap增量0。后续450255完整PQ固定g诊断已完成，CUg场误差仍约0.93067；这些中途证据与当前实体组件一并保留，详见中心报告及compact。

G1/G2已完成，旧新C真实负结果保留；用户补充授权继续有依据的p4/p2诊断，G5与response_v8尚未最终收口。该授权超出V6原停止分流，不改变物理、精度或安全线；不复跑G1/G2。

| 项目 | 最新结论 |
|---|---|
| V6原始LO | 13步true0.667843080037，1800.799s筛选不合格；COARSE_APPROXIMATION_UNQUALIFIED |
| G1/G2精度 | 固定6输入0/6达LO；正式26I4均未达；映射/残差闭合与成本账通过 |
| 资源 | 新screen峰1491857408B、swap/globalΔ0；仅失败13步，不是2GB成功解/完整求解峰 |
| V5保留 | 原始564/notch576步，完整残差、匹配参考与物理Gate通过；参考448页global out归因UNRESOLVED保留 |
| 分流 | HI未资格化、notch/recovery未运行；G1_G2_COMPLETED_DIAGNOSTIC_CONTINUATION_AUTHORIZED；无W0/5nm/0.7nm/生产默认资格 |

中途诊断、投影互补及全网格bubble实测见[中心结果](coarse_inverse_replacement_v6.md)与[compact](records/p4_causal_research_v6.json)。新W/S构造身份通过，但唯一I4在15步/约61.15s的真残差0.981425253未过1e-4；M0/curl误差剩余约0.9966。下一步仅提出内部particular/高阶trace定位方案，尚未运行；G5保持开放。

详见[中心结果](coarse_inverse_replacement_v6.md)、[compact](records/coarse_inverse_replacement_v6.json)与[移交](workstation_handoff.md)。

以下完整保留历史正文；“当前/下一步”仅指当时阶段，以本节为最新状态。

---

# Task39extra V5当前结果：两个完整BAL_H通过，参考swap归因保留限制

| 项目 | 当前结论 |
|---|---|
| 原始13.5nm/p6h10/MPI1零初值 | 564步，完整真残差9.932289220e-7；solve6102.614s，含输出恢复6997.531s；R/T/A=0.365625791/0.0129906323/0.621383577 |
| 唯一notch | 576步，完整真残差9.351705517e-7；solve6261.471s；R/T/A=0.337120585/0.0162886742/0.646590741 |
| 匹配参考 | 两模型场、scaled curl、80复振幅、功率/体耗散Gate通过；非连续真解 |
| 资源边界 | 原始与notch迭代global swap Δ=0；条件参考global pswpout448页，归因UNRESOLVED，采样tree swap0；不能声称全workflow全系统swap0 |
| 未完成资格 | 2GB/0.7nm/生产默认/连续收敛未取得；BAL_S与PROJ heavy为not_run_goal_met |
| 唯一下一对象 | 有界内存/分布式物理近似C替代全局p4 LU，保持粗细平衡；未实施 |

完整结果、时钟/资源口径、原始输出失败与恢复、证据和依赖分组见[本次结果](balanced_coupling_v5.md)及[compact](records/balanced_coupling_v5.json)。

以下保留历史阶段记录；其中“当前/下一步/未通过”仅指当时阶段，以本节及本次结果为最新状态。

---

# Task39extra补充授权：真实难误差已定位

| 当前结果 | 实测与边界 |
|---|---|
| 原始模型/参考 | 13.5nm、1°、p6/h10、MPI1；匹配fine原A6残差1.6160304782604192e-11 |
| 三真实误差 | 相对L2=22.46%/24.92%/31.34%；phase-invariant M0相关>0.9975 |
| 表示与精度 | p4互补范数仅0.8300%/0.8421%/0.8225%；四native A4≤1e-10、零精化；range identity2.53e-12 |
| 主机制 | 物理粗层—细层互补耦合失衡；粗RHS几乎等大反向，相消比1.7–2.0%，粗响应差/互补范数57–59倍 |
| MR抑制 | 单位粗修正剩余场约48%，细层残差增22–53倍；MR小步长后场误差近乎不变，不是MR公式bug |
| 独立资源 | fine参考7,229,845,504 B/574.7957s；诊断3,881,811,968 B/1510.7222s；swap0，不能相加或称2GB资格 |
| 唯一下一对象 | 现有physical p4粗修正与p6互补耦合/平衡；下一轮待资格化设计要求，未实施新PC |
| 未通过 | 旧negative不改判；2GB生产迭代/非可分/0.7nm/official仍未通过，无新参数扫描 |

用户补充授权“直到把真实难误差定位了”的范围完成，不伪装为V4原始范围。真实误差来自匹配离散参考与三旧失败快照之差；其小互补场在物理算子下却产生很强的粗层驱动。闭合方程与场误差测量支持上述定位，不能外推条件数、色散定理、整体近共振或连续真解。

详见[中心说明](actual_error_diagnosis_v5.md)、[中心JSON](records/actual_error_diagnosis_v5.json)、[Response V6](../response_v6.md)。旧V4以下内容保留为历史，当时“参考仍缺失”等状态不代表本次最新结果。

## 历史V4及此前结果（原文当前仅指当时）

# Task39extra Review V4：诊断完成，真实散射参考仍缺失

| 项目 | 最新结果 |
|---|---|
| 正式source/model | b127546f172e46d0b217680338b4e0ea7aa39f12；13.5nm/1°/s/Full3D p6h10/MPI1/线程1/80modes |
| 终态与计数 | DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS；watchdog/launch COMPLETED、exit0；8PC/4互补/10逻辑p4/12MatSolve |
| 表示/粗响应 | 110步投影闭合，eta_space=0.084774901、eta_G=0.092065368、range identity=3.92727e-13 |
| 互补/真实残差 | H6/S6场误差保留0.941689514/0.934259170；JOINT448 LIGHT/JOINT残差比0.999706716/0.999674195 |
| p4精度 | 重建首次1.0086968840613473e-10>1e-10，1次精化9.492574739321824e-13；旧失败保留 |
| 资源/时间 | RSS峰3540959232 B、cap最低8314208256 B、reserve4GiB、swap0、3936样本无违规；outer保守1130.973243s<5400s |
| 清场/范围 | 父进程及2后代均清场；无新full solve、official R/T/A/A_volume/R00_s/p/total/衍射级/EH、p/h/M/MPI/Hybrid扫描 |
| 唯一下一优先 | 取得同A6、同b、同1°的匹配fine参考/真实误差，复用现有packet定位；本轮不造新PC或延长迭代 |

质量投影用无损L2尺子找p4最佳表示，粗响应则用实际p4算子求修正；这个人工误差上两者都较好，不能硬判p4色散/严重粗层失配。互补残差改善却留下大部分场误差；粗方向MR令场误差比0.092→0.213同时残差改善，反映目标不同，不是已证bug。人工e不等于实际散射误差。C4现有2D截面QEP不能提供规定3D Bloch控制，UNRESOLVED，未新建平台。

方法、原因矩阵、数值边界、全部raw哈希及分阶段成本见[中心说明](diagnostic_completion_v4.md)、[中心JSON](records/diagnostic_completion_v4.json)、[Response V5](../response_v5.md)。新7200s计算账与旧V3分开，审计时1142.571742s；编辑/等待另列，最后静态补费见中心JSON。旧7响应/3identity仅按hash复用。

## 历史V3收口（以下当前仅指当时）

# Task39extra：D5最新收口——原A4数值Gate拒绝，7次PC诊断完成

| 项目 | 最新结果与适用边界 |
|---|---|
| 来源与模型 | clean source `bf8e0c1d16c9c86677e866cdf29fd5491f076e32`；原始13.5nm、1°、s、Full3D p6/h10、MPI1/线程1、80 DtN modes；无参考D1/D3诊断 |
| 数据/作用 | 3份历史快照原A6残差复现，最大绝对差2.77556e-16；native独立系数逐位匹配，分项和与A作用一致 |
| 调用计数 | 8 started / 7 completed；第8次JOINT448→LIGHT未完成，不能记为完整PC；已知误差/投影/互补/D4均not_run |
| 终止 | 原A4残差1.0086968840613509e-10>1e-10（超限0.8696884%）；worker DIAGNOSTICS_FAILED，watchdog/launch WORKER_FAILED，outer exit2 |
| 资源/清场 | 同期树RSS峰3777171456 B<实际cap8367992832 B；reserve4294967296 B、最低available9252577280 B；3324样本无违规，swap0；父进程及20个已观测后代清场 |
| 时间 | watchdog mono866.072315784 / BOOTTIME866.072315245 / UTC945.518512242 s；逐段保守收费945.519546580 s，outer含pre/post952.495114811 s |
| 规模 | p6存储173802/独立164592行、252cells；p4存储53084/独立48960、增广53164行、allocated NNZ24730144、factor NNZ53417584 |
| 物理输出与比较 | 无新R/T/A、A_volume、R00_s/p/total、衍射级、复E/H或full solve资格；无p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 后续范围 | 数学根因仍未完成；唯一优先是补存同一失败p4输入，核对增广系统与原A4残差差别/可靠性，再补缺失表示与响应诊断；本轮不重跑或精化 |

详见[中心报告](nonconvergence_diagnosis_v3.md)、[中心JSON](records/nonconvergence_diagnosis_v3.json)与[Response V4](../response_v4.md)。 PC为求解提供近似修正，本次测量的是同输入单次残差变化；缺少已知误差和投影，不能确定空间/粗响应根因。

## 历史状态（下文当前/0次等仅指当时）

# Task39extra：Review V3 / D5 证据收口

| 对象 | 当前结果 |
|---|---|
| 原始13.5nm/1°/p6h10/MPI1/80modes诊断 | 唯一启动source `24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650`；`TIMEBASE_INCONSISTENCY`，不是新完整求解或数值失败 |
| 完成/未完成 | D0与微型验证完成；setup止于s6_transfer_cycles_started；fresh canonical/原A残差、已知误差、p4投影及PC探测均未完成；完整PC0、互补0、投影0，D4 not_run |
| 时间 | 首次Gate区间mono61.410906241 / BOOTTIME61.410906659 / UTC67.359115896 s，差5.948209655>5 s；245样本发现两次离散UTC相对跳变，系统原因未定 |
| 资源/清场 | 同期树RSS峰639950848 B<cap8417038336 B；reserve4294967296 B、最低effective available12219453440 B、swap0、违规0；parent及已观测后代清场 |
| D2 | 缺完整MPI1峰值上界，参考未启动；REFERENCE_UNAVAILABLE_ON_16GB仅限本轮安全路径，非普遍不可能 |
| 结果边界 | 新残差/official R/T/A/A_volume/R00_s/p/total/衍射级/EH均not_run；历史LIGHT576=0.0791360407785889、JOINT476=0.10535820013809101仍>1e-6 |
| 模型规模/比较 | 历史存储173802行、独立164592行、252cells；fresh NNZ未到达。未新增p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 下一步 | 数学原因UNRESOLVED；仅优先时间资格及冻结同输入最小补证，本轮不重试、不提新PC、不merge |

方法解释、原因矩阵、各失败数值、hash及selective merge依赖组见[中心报告](nonconvergence_diagnosis_v3.md)、[中心JSON](records/nonconvergence_diagnosis_v3.json)。watchdog摘要为终止权威，launch为初始记录、worker终态缺失，raw保持原样。

## 历史V2及此前记录（原文“当前”指当时）

# Task39extra：Review V2 / F5 用户收尾

| Review V2 / F5 | 当前结论 |
|---|---|
| F1 / F2 | 完整packed S6数学等价通过；配对中位0.938459>0.75，速度不足，F2 not_run |
| F3原始模型 | 13.5nm/1°/p6h10/MPI1/80modes；source `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；零初值476步真残差0.10535820013809101>1e-6 |
| 方法与失败含义 | 保留H6–准确p4–H6三个顺序方向，仅末尾联合选权；局部残差比中位0.979479，rank3/无回退；不足以让完整p6收敛 |
| 用户收尾 | USER_REQUESTED_CONTROLLED_STOP；raw worker CONTROLLED_STOP、wrapper WORKER_FAILED/exit4并列；未触发原自动budget/stagnation Gate |
| 时间限制 | workflow monotonic7588.369777 / UTC8363.831318 s；solve至请求monotonic6791.466003 / UTC7478.995420 s；UTC solve超7200，原因未唯一确定，不能声称全部wall预算通过 |
| 资源与清场 | RSS/PSS峰3351887872/3317217280 B，28753样本均可读；cap8525078528 B、至少4GiB余量无违规；swap0，56 PID清场 |
| 后续 | F4/official锁定，无第三候选、续跑或0.7nm资格；仅F5文档/测试/审阅后提交推送，非master merge |

联合选权是在一次辅助修正末尾重新组合已有方向，能减小本次输入的误差，却不能保证后续整个求解更快。准确p4是诊断factor，不能替代原p6残差/物理验收。完整周期、早晚成本、双时钟与哈希见[本轮中心报告](packed_and_joint_mr_v2.md)、[小JSON](records/packed_and_joint_mr_v2.json)和[response_v3](../response_v3.md)。R/T/A、A_volume、R00_s/p/total、衍射级及复E/H本轮均未生成；无新增p/h/M/MPI或Hybrid比较。

## 历史 Review V1 / R6（以下当前/未运行指当时）


| 项目 | 当前结果 |
|---|---|
| 模型 | 原始13.5 nm、掠入射1°、Full3D p6/h10、MPI1、80 modes；零初值完整R3 |
| R0 / R1 | 原PC同机非warm中位22.021386729524238 s；等价实现74.87089344408014 s，3.3999172878472805倍，未满足≤0.75倍；等价误差通过，速度失败 |
| R3 LIGHT | H6–p4–H6，582完整PC中位10.293892393587157 s；7200.255611149943 s求解后 `PERFORMANCE_CONTROLLED_STOP` |
| 完整wall / RSS峰值 | 7966.278611822054 s / 3352014848 B（同期parent+后代RSS采样）；swap=0，cap=8588566528 B，系统余量≥4294967296 B，30230样本无违规 |
| 最后安全结果 | 第576步原A6真残差0.0791360407785889 >1e-6；第582步reported=0.07877047901292458，不是终止瞬间真残差 |
| p4参考逆 | 583次原A4残差最大7.058163970105702e-11≤1e-10；仍未带来合格p6场 |
| 退出缺口 | parent记录预算停止并清场；worker terminal summary、final arrays与normal checker未生成；第583个PC的post未证明完成 |
| official物理输出 | R/T/A、A_volume、R00_s/R00_p/R00_total、衍射级、复E/H和近场均not_run |
| 条件未触发 | R2因速度Gate失败跳过；R4非可分、R5参考/direct与h5 heavy未运行；无第三PC、5nm或0.7nm资格 |
| 事后修复 | `597546311feea60d61acb2a9999b706dd895dcf0`只修未来LIGHT安全停止路由；没有R3重跑，不提升正式负结果 |

轻量组合用p6上的局部平滑H6代替S6内的p3/p1多层步骤，减少每次辅助修正的工作，但方向对原方程误差的削弱仍不足。准确的p4直接逆是诊断依赖，不能替代外层真残差和物理输出Gate。两条路线按本轮合同结束，不能说两种算法已彻底研究完：完整S6配合后续contiguous packing的重新资格化为not_run。

在共同32步观测下，接近0.1826残差的累计周期时间由旧A2R的3528.55 s降至R3的2861.69 s，约19%；这不等于相同残差的精确穿越时间，也不是趋近1e-6的外推。方法、计时嵌套范围、贡献统计、完整曲线、source及hash见 [成本与贡献](cost_and_contribution_v1.md)、[紧凑JSON](records/cost_and_contribution_v1.json)、[response_v2](../response_v2.md)。p/h、Full3D/Hybrid、M和MPI扫描无新增对照，0.7nm物理收敛和global p4 factor扩展能力未资格化。当前进入集中审阅，不继续formal。

## 历史 A5 证据（原结论保留，当前阶段以上表为准）

| 项目 | 结论 |
|---|---|
| 研究对象 | 13.5 nm、掠入射 1°、Full3D p6/h10、MPI1、80 DtN 模式；不是 0.7 nm 已通过模型 |
| 最终状态 | A2R 在原 3600 s solve Gate 触发 `PERFORMANCE_CONTROLLED_STOP`；外层未达到 1e-6 |
| 已证明的边界 | p4 参考矩阵容量可容纳；163 次中间逆均通过原 A4 真残差 1e-10 Gate；最后有效第 160 步外层残差为 0.18250767622880507 |
| 移交资格 | 可移交机制与负结果证据，未满足 `LOCAL_13P5NM_3D_READY_FOR_WORKSTATION` 或 `REFERENCE_ONLY_HANDOFF` |
| 未运行 | A3 非可分、A4 h5/独立 direct、official recovery/输出、5 nm、0.7 nm；不补跑 |

主候选用较低阶 p4 的迭代解辅助 p6 外层修正。A2R 把中间迭代逆换成原 p4 物理矩阵的一次直接分解，取得准确且可复用的中间修正，代价是装配时间和分解内存。A6、传递、80 modes、S6 pre/post、MR、FGMRES32/max512 和零初值不变，生产默认不变；中间逆通过不能替代外层通过。

时间为 s，内存为 B；RSS 为 watchdog 同期进程树采样峰值，含 parent、MPI worker、编译后代。

| 运行 / source SHA | 分类与阶段 | workflow / RSS peak / swap | 数值边界 |
|---|---|---|---|
| A2 旧 setup；`39448e6a0e5705ad2c40b4bf7733ce2249e35a84` | 用户 setup 受控停止 | 5946.465141321009 / 1582481408 / 0 | outer 未开始 |
| A2 优化后；`2bed3d4248a465a9cf2224c575fc8b64357fd020` | `USER_AUTHORIZED_COST_CONTROLLED_STOP` | 3015.3758775380556 / 1849683968 / 0 | 7 完整 PC，第 8 partial；outer final 不可用 |
| A2R 入口；`f93edc8ae9e90c4ed07e375d964312eb68999ee9` | `adapter_unavailable`，测量前登记遗漏 | 0.014696567959617823 / 未采样 / 未采样 | watchdog/MPI/symbolic/PDE 均未开始，不计 reference 正式次数 |
| A2R 唯一正式；`54ab46cf4c8378a9b27650ca6963cadb34013a2f` | `PERFORMANCE_CONTROLLED_STOP`，solve 3600 s Gate | 4451.728501909005 / 3588677632 / 0 | 163 完整 PC，第 164 仅 pre 开始；最后 checkpoint=160 |

PC 是一次辅助修正。优化后 A2 的 7 个 PC 各运行 36 个中间步，A4 残差依次为 0.846787、0.815692、0.720637、0.794347、0.817342、0.635752、0.803464，均未达到中间目标 1e-2。这些 RHS 不同，不能串成收敛曲线；其 checkpoint 0=1 只代表初始零解。

| A2R 周期末迭代 | 原 A6 显式相对真残差 | 成功门槛 |
|---:|---:|---|
| 32 | 0.46338436888430473 | 1e-6，未通过 |
| 64 | 0.41005441732961595 | 1e-6，未通过 |
| 96 | 0.3139861672303239 | 1e-6，未通过 |
| 128 | 0.2753887167051727 | 1e-6，未通过 |
| 160 | 0.18250767622880507 | 1e-6，未通过；最后有效 checkpoint |

每周期 reported 与显式残差差值通过既定核验，精确对照见索引。163/164 步最终残差不可用，不把第 160 步结果当作停止瞬间最终场。残差降低但预算内未达标，不证明整个 p4 空间或 Full3D 迭代数学不可能。

| 对象 / 阶段 | 实际或推导值 | 口径 |
|---|---:|---|
| p6 / p4 rows（独立 rows） | 173802（164592）/ 53084（48960） | 原模型 |
| p4 slaves / modes | 4124 / 80 | actual MPC/carrier |
| volume / augmented NNZ | 24666128 / 24730144 | 实际；augmented rows=53164 |
| S6 / 至 solve 开始 | 117.70526724500814 / 847.9243652080186 | 本次 marker 跨度；后者包含全部 worker setup |
| reference volume compile / values | 13.712174824962858 / 588.368423515989 | marker 跨度 |
| augmentation / symbolic / numeric | 0.5967822759994306 / 0.3211546370293945 / 18.394115508999676 | 各一次；numeric 含 preflight 设置 |
| post-symbolic RSS / 预测峰值 / cap | 2292035584 / 6988289408 / 8736759808 | 预测为 2×带 padding 的 MUMPS 估计加 workspace 和 1 GiB，非严格上界 |
| reference solve / 原 A4 action | 163 / 163 | 最大相对残差 5.7889315844880267e-11 |
| 完整 PC 最小 / 中位 / 最大耗时 | 20.112385745043866 / 20.611484433989972 / 21.111527371045668 | 原 A2 约 290–446 s；成本下降不等于 outer PASS |
| RSS / 可读 PSS 采样峰值 | 3588677632 / 3554077696 | RSS 的 16993 样本均可读；1 个 PSS 不可读样本，PSS 非完整 Gate 权威 |

S6 精确对角优化省掉取得对角项时不需要的单元耦合，保持原积分和约束；旧 S6 5916.818793114 s（约 98.6 min）降至优化后 A2 的 143.69 s。本次 S6 为 117.71 s。S6 单段不等于完整 setup 或 workflow。

| 计数 / 尾段证据 | 审计结果 |
|---|---|
| S6/S3 次数更正 | 原 cycles 将生命周期序号相加，五周期误报 2080/6176/10272/14368/18464；逐次重算每周期均为 64。163 完整 PC 合计 S6 326 次、S3 326 次；最后完整周期后的 3 个完整 PC 合计增加 S6 6 次、S3 6 次；partial 第 164 不推算 |
| 修复边界 | cycles 原文不改；checker 只读重算；未来 ledger 只修序号误加，不改数值路径 |
| 终止时间 | solve Gate 的 monotonic 阈值为 503631.500417347；最后 marker 为 solve 3596.8651744240196 s；单独发信号时间戳未记录，不伪造精确触发时刻 |
| 清场 | parent 及 61 后代共 62 PID 均消失；cache metadata 稳定；swap 与全局换页增量均 0 |
| worker 尾段缺口 | physical_intermediate_summary.json 未生成；正常 release/recovery/checker completion 未完成，不补造原 worker 终态 |

official R/T/A、A_volume、R00_s/R00_p/R00_total、重要衍射级、E/H 与参考平面均 `not_run`。p/h、Hybrid、M、MPI 扫描没有新增正式对照，不宣称连续极限收敛。

证据：[运行索引](records/run_index.json)、[测试摘要](test_summary.md)、[移交包](workstation_handoff.md)、[response_v1](../response_v1.md)。索引绑定本次 28 份 raw（含每周期 manifest/solution）及早先停止、入口失败、实现/修复记录；大型 raw/cache 保持 ignored。

下一步只提交集中审阅，决定如何解释中间逆已准确但外层仍昂贵的机制，以及是否开展新的算法比较。不自行延长预算、重跑 A2R、换 PC 或进入 A3/A4；当前未获最终 merge approval。
