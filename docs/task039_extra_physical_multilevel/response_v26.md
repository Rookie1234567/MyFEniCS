# Response V26：Review V23 S0–S6 收口

## 结论先行

Review V23 的工作不是“只做三场降粗阶运行”。它先完成了 S1/S2 的数值后端、参数化、runner/schema 和测试，再在实现冻结后完成 S3–S5 的 Q4/Q3/Q2 正式场，最后由 S6 整理负结果和证据。最终 source 是 cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32；从 review base e63d2f49f19961f985faeadbe1ad3b89808369d1 到该 source 共 38 个文件、5244 行新增、223 行删除。

通俗地说，第一条主线把 A6/H6 中反复做的局部矩阵动作改为可复用的 sum-factorized 动作，并让 p6、p4、粗阶和修复调用的计数能被审计；第二条主线用冻结后的实现做 p4/p3/p2 对照，并把“数值通过”“资源受控停止”“没有终态”严格分开。前者解决工程成本和可追踪性，后者回答粗阶对收敛、耗时、内存和物理结果的影响。

| 模型 | full workflow / stop（s） | 纯 KSP monotonic（s） | 迭代或进度 | 最后显式真残差 | RSS/PSS 峰值（B） | 判定 |
|---|---:|---:|---:|---:|---:|---|
| V24 p4 | 4579.015917060999 | 3716.1522563079925 | 126 | 9.283164961979326e-7 | 7339319296 / 7307023360 | 通过，authority limited |
| Q4 p4 | 4718.70844729399 | 3766.626355408 | 126 | 9.283165086752956e-7 | 7389360128 / 7357231104 | 通过，authority limited |
| Q3 p3 | 7065.949492944987 | 6082.501362726 | 361 | 9.460140452867132e-7 | 4031815680 / 3999603712 | 通过，authority limited |
| Q2 p2 | 15755.054311790009 start-to-stop | unknown | 1048 explicit completed；PC 1049 ledger；PC 1052 partial | 6.086703757232677e-4 | 2702069760 / 2670846976 observed | RESOURCE_CONTROLLED_STOP |

V24 p4 仍是同一模型已完成场中的最快整体 workflow；Q4 是 V25 已完成同 backend 场中的最快者，但没有超过 V24。Q3 是已通过结果中的合格最低内存者。Q2 的已观测峰值不参与合格内存排名。按纯 KSP monotonic 除以已完成显式迭代计，V24/Q4 单步为 29.4932718755/29.8938599636 s；Q4 比 V24 整体多 2.3282088372 min、RSS 多 50040832 B。Q3 单步 16.8490342458 s，但步数为 Q4 的 2.865079365 倍，整体多 39.1206840942 min、RSS 少 45.43755332%；单步不能替代端到端结论。

## S0–S2：实现、参数化、冻结

S0 先冻结 ABI、source/input identity、线程合同和 artifact 入口。S1/S2 完成并保留了以下 base 到 final 的实现范围：

- src/solvers/fullspace_n1e_sum_factor.py 新增 443 行 sum-factorized N1E 内核；
- src/solvers/fullspace_partial_assembly.py、physical_equivalent_fast.py、physical_light_setup.py 等接入 A6/H6 实际调用和 retained timing；
- physical runner、retained outer adapter、task038 launcher、input schema/validation 接入 P6q 粗阶参数和可核验事件；
- benchmarks/task39extra_v25_dynamic_checker.py 与三个 v25 focused tests 增加原始字段重算和参数化检查；
- v25 q2/q3/q4 输入、common source freeze manifest、S1 operator compact 同一分支冻结。

实现冻结后，三场正式运行和 S6 整理没有再改数值源码；这不等于本 Review 没有数值实现。ordinary default 未改变。

S1 operator-only 资格证据如下：

| 动作 | baseline 中位数（s） | sum-factorized 中位数（s） | candidate/baseline | 最大相对差 |
|---|---:|---:|---:|---:|
| A6 full | 5.615303212005529 | 3.326707318992703 | 0.5977345519260012 | 7.268824811167207e-15 |
| A6 volume | 5.597440945501148 | 3.3534994010042283 | 0.5927790935924615 | 7.26882481148384e-15 |
| H6 apply | 8.367951847998484 | 3.6148972290029633 | 0.43298776361290847 | 2.156449381869184e-16 |
| H6 setup | 144.1912405710027 | 89.64910604900797 | 0.6217375320025971 | 9.40733840398024e-16 |

这些是相同输入的 operator pair，不是 full-PC 或 formal PDE 结论。配对 RSS/PSS 峰值 1421533184/1389453312 B 同时包含 baseline 和 candidate。旧 v26 配对的 H6 apply 比为 1.0057808725574315，并保留 executor-controlled interruption 349.01716884099005 s；该负候选不改写成通过。

S1 选中的 v27 operator worker 为 MPI1/thread1，workflow monotonic 710.3849701840081 s，conservative settlement 789.6493765678632 s；保留的 v26 负候选为 915.8957639279979 s / 1016.5861852233071 s。2-thread 与 4-thread formal qualification 均未运行。

## S3–S4：Q4/Q3 正式场

完整 setup 必须和 interface 子区间分开。Q4 完整 setup 为 836.8461274599977 s，其中 interface 子区间为 255.8490446670039 s；Q3 完整 setup 为 935.0583148549777 s，其中 interface 子区间为 112.08410538101452 s。Q4/Q3 的 final native check、release check、official postprocess monotonic 分别为 11.11452951899264/28.718534543004353/33.62914118100889 s 和 5.658712063013809/7.860895881021861/15.513572724012192 s。

Q4 使用 condensed rows 84680、NNZ used/allocated 32320342/45403840，MUMPS allocated/used 4687/4326 MB、entries 221594144，retained numeric cache 24541920 B；p6 full rows 667152，p4/coarse full rows 201520。调用计数为 native A4 267、p4 logical/physical 262/267（5 repairs）、A6 live/native witness 263/29、H6 apply/matrix/power10 131/282/20、P/PH 263/269。final explicit/post-release residual 为 9.283165086752956e-7；R/T/A/A_volume 为 0.3650975537006154 / 0.013016803347760878 / 0.6218856429516237 / 0.6218856421339276。

Q3 使用 condensed rows 45440、factor rows 45440、NNZ used/allocated 9982160/17152480，MUMPS allocated/used 3171/1413 MB、entries 73058906，retained numeric cache 4047264 B；p6 full rows 667152，p3/coarse full rows 86652。调用计数为 legacy key native A4（实际为 A3）726、p4 logical/physical 726/726（0 repairs）、A6 live/native witness 738/63、H6 apply/matrix/power10 363/746/20、P/PH 727/740。final explicit/post-release residual 为 9.460140452867132e-7；R/T/A/A_volume 为 0.3650975453210275 / 0.013016803435687712 / 0.6218856512432849 / 0.6218856293036095；R00_s/R00_p/R00_total 为 0.36506085452416953 / 1.2740189409450237e-22 / 0.36506085452416953。

Q4/Q3 的 factor numeric RSS/PSS 是单个 numeric_resource snapshot，分别为 6564626432/6532520960 B 和 2792673280/2760546304 B，不冒充 factor 窗口峰值。Q4 compile events 是 11 hit、总 0.016517077005119063 s；Q3 是 10 hit/1 miss、总 22.125253679056186 s。两场的 offline audit 和 dynamic checker 都通过；audit 入口及 hash 在各自 compact 的 audit_entry/evidence_hashes 中。

用 physical summary 的 lifecycle 边界和 watchdog `parent_clock.monotonic` 对齐后的窗口峰值如下；这避免把 raw `worker_phase=solve` 阶段误称为纯 KSP。

| 窗口 | Q4 RSS/PSS（B） | Q3 RSS/PSS（B） |
|---|---:|---:|
| full setup | 7147806720 / 7115721728 | 3783094272 / 3750958080 |
| pure KSP solve_only | 7384489984 / 7352404992 | 4015337472 / 3983202304 |
| final native / release | 7387275264 / 7355190272；7387275264 / 7355173888 | 4016586752 / 3984450560；3994566656 / 3961381888 |
| official postprocess | 7375278080 / 7343121408 | 4031815680 / 3999603712 |

累计工程账本（父 wrapper 与子 kernel 可重叠）为：Q4 live A6 1332.467643185184 s，其中 volume/DtN 1330.7428043539403/1.2753846961422823 s；native A6 witness 225.27302363597846 s，其中 volume/DtN 224.5926196010114/0.6324881170003209 s；native A4 655.2644249749428 s；H6 apply parent 775.3049049579422 s，B6 measured 262 次/770.4665523900039 s；diagonal/power10 setup 47.394968193999375/39.93837261298904 s；P/PH/route 115.96566753796651/103.42713105508301/3.1915090329857776 s。Q3 对应 live A6 2569.307760093361 s、volume/DtN 2565.767899198516/2.5622179692436475 s；native A6 witness 356.3027427189809 s、volume/DtN 355.94924291592906/0.2721792981028557 s；native A4 legacy key（实际 A3）611.2342456796905 s；H6 apply parent 1456.900879892928 s，B6 measured 726 次/1447.5354960261611 s；diagonal/power10 setup 112.18477031201473/97.9184494529909 s；P/PH/route 131.6326058304403/96.62534810282523/5.794357740494888 s。native Aq projection 两场都 PASS，但没有单独 timing 字段。

## 用户要求的 p4 基线：迭代 112

只取同一 990-cell p6/h7.5 的 V24 与 V25 Q4 记录，旧 p6/h10 112 步场不混入：

| 记录 | 显式真残差 | 原始 monitor solve_seconds（s） | 该次 RSS/PSS（B） |
|---|---:|---:|---:|
| V24 p4 | 2.7139958442857524e-6 | 3606.8307935579464 | 7334645760 / 7302341632 |
| V25 Q4 p4 | 2.71399585136905e-6 | 3437.2333360950015 | 7384477696 / 7352336384 |

solve_seconds 只按原始字段定义报告，不改称纯 KSP。V25 Q4 的完整纯 KSP monotonic 仍是 3766.626355408 s。

## 每 16 次迭代的共同残差检查点

显式真残差按相同迭代号对齐；没有记录就保留“—”。Q2 endpoint 是 iteration 1048 的最后完成显式记录，不是 official final。

| 检查点 | V24 p4 | Q4 p4 | Q3 p3 | Q2 p2 |
|---:|---:|---:|---:|---:|
| 8 | 0.012837270982779802 | 0.01283727098278337 | 0.17488597448132098 | 0.7952800898514276 |
| 16 | 0.004143722296400315 | 0.0041437222964080065 | 0.05955155645219348 | 0.6628304902854271 |
| 32 | 0.00033529179603668626 | 0.0003352917960387092 | 0.00746492907202232 | 0.31997605245428284 |
| 64 | 3.0233523447682185e-5 | 3.0233523443058283e-5 | 0.0016579487936124356 | 0.10025884261226853 |
| 96 | 3.7766999140939517e-6 | 3.7766998795463687e-6 | 0.00040709897769036584 | 0.05595733687269235 |
| 112 | 2.7139958442857524e-6 | 2.71399585136905e-6 | 0.00026401726943588134 | 0.04151166469355988 |
| 128 | — | — | 0.0001391798755711918 | 0.03340352398491927 |
| endpoint | 9.283164961979326e-7（126） | 9.283165086752956e-7（126） | 9.460140452867132e-7（361） | 0.0006086703757232677（1048，非 official） |

## S5：Q2 受控停止

Q2 的完整 setup 为 486.12522399 s（既有事件起止派生）；p6 full/active/interior/slave/trace/appended rows 为 667152/199260/445500/22392/221652/80，coarse p2 为 26656/18180/5940/2536/20716/80，factor rows 为 18260，NNZ/entries 为 1913120/14359560。factor symbolic/numeric 为 0.058441740984562784/3.920166377007263 s，MUMPS allocated/used 为 2506/278 MB，retained cache 262704 B。已完成的 native Aq projection check 通过（DtN relative 5.362129756528201e-15、volume relative 1.1762517120345644e-14、slave-zero true）；它是 setup/inner evidence，不是 terminal official result。Q2 在 156673.960582131 monotonic 触发 GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED，leader exit -9，整棵子树清场。

触发样本是 elapsed 15753.554006381979 s、RSS/PSS/VmSwap 2701971456/2669953024/0 B、effective available 11173453824 B；最后一个已完成显式 iteration 1048 样本的 effective available 是 11193122816 B，不能把后者称作 stop 瞬间值。全局 pswpin 增量 0、pswpout 增量 7，但无法归因给该作业；不是已证明 OOM。

最后完成显式 iteration 1048 的真残差为 0.0006086703757232677；PC 1049 只有 outer-PC ledger，PC 1052 是 PC sequence counter，不是 outer iteration，active raw p4 record 为 partial。没有 final KSP end、final native check、post-release residual、field、official output 或 terminal dynamic checker summary。故 Q2 是 RESOURCE_CONTROLLED_STOP / CONVERGENCE_NOT_ESTABLISHED_BEFORE_STOP，不是数值方法失败，也不是 max-iteration 2048 不收敛。

active partial raw p4 packet `pc001052/logical002103` 的 native Aq return residual 为 1.0078163816265527e-12；2103 个 raw inexact packet 的最大 native A4 residual/g norm 为 7.727968728108255e-12，超过 1e-10 的条目为 0，factor hash 唯一值为 46eb9afe3fe396410b95b001e836f77aed52bb807362ff49520617b16fc51ebc。该 packet 的 elapsed/reduce/solve/recover 为 320.0523956193065 / 140.69881518252078 / 48.80859945167322 / 129.88294802472228 s；这只能说明 inner raw packet 质量，不能升级为 outer 或 official 完成。

watchdog 60683 个样本的 RSS 全可读，RSS peak 2702069760 B；PSS observed peak 2670846976 B。唯一 PSS 缺口是 setup compiler ld 的一个早期样本（elapsed 8.177329701982671 s，PID 698126），因此 pss_all_readable=false；这不影响 RSS 和清场结论。

## S6：证据与选择性合并

S6 保留了 source/input/config、run summary、watchdog、资源增量、全样本 RSS/PSS/余量、清场状态、Q2 iteration 1048 真残差、未完成 PC/Aq 的 partial/unknown 分类和所有未运行终态。既有 FE audit glue 已以最小可审阅形式提升到 `benchmarks/fe_metric_v25_q4_glue.py`，只修正 repository-root `parents` 层级；旧 ignored tool SHA 和 audit 中记录的旧 SHA 均保留，提升后不重算 FE。没有用未过 1e-6 的场生成 Q2 official result，没有重启 Q2、第四场或新算法。

交付入口为 [V25 outcome](outcomes/a6_h6_coarse_degree_v25.md)、[components](outcomes/records/a6_h6_coarse_degree_v25_components.json)、[frozen manifest](outcomes/records/a6_h6_coarse_degree_v25_frozen_manifest.json)、[Q4](outcomes/records/a6_h6_coarse_degree_v25_q4.json)、[Q3](outcomes/records/a6_h6_coarse_degree_v25_q3.json)、[Q2](outcomes/records/a6_h6_coarse_degree_v25_q2.json)、[decision](outcomes/records/a6_h6_coarse_degree_v25_decision.json) 和 [selective merge manifest V25](outcomes/selective_merge_manifest_v25.md)。ordinary default 不变，master merge 仍需明确批准和用户授权。

## 用户追加授权：Q4 AC 重复运行

用户授权了一个独立的 Q4 original AC 重复运行，输入、物理模型、p6/h7.5、粗阶 p4、MPI1/thread1 和求解器参数保持不变；本次仅使用 `run_id` 分支记录授权，不改变数值算法，也不重跑 Q3/Q2/notch。旧 Q4 通过结果保持为独立历史记录。

该重复运行在 `iteration=18` 的 outer-PC 记录后受控停止，未产生 `iteration=32` 检查点、终态 KSP、final native check、post-release residual、field 或 official output。退出码为 `-9`，watchdog 分类为 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`：作业进程树采样的 VmSwap 峰值为 0 B、RSS/PSS 峰值为 7314296832/7282536448 B，时间门未超限；WSL 全局 pswpout 从 7 增至 9，但不能归因于该作业。因此该次记录是资源受控停止，不是 OOM 证明，也不是数值方法失败。

在唯一完整落盘的 16 步检查点，按 `solve_seconds` 原始字段同口径比较：

| 记录 | 显式真残差 | 原始 solve_seconds（s） | 全进程树 RSS/PSS（B） |
|---|---:|---:|---:|
| 本次 AC 重复 | 0.0041437222964080065 | 356.40948556199953 | 7299502080 / 7267741696 |
| 前一 Q4 案例 | 0.0041437222964080065 | 356.4489566070092 | 7290662912 / 7258555392 |

本次耗时少 0.03947104500967 s；残差完全一致。对应 `pc=16` 的 p4 baseline `logical_call=1` 也有记录：两次 `native_A4_relative_residual` 都是 `9.12762008915742e-12`，本次 p4 elapsed 为 0.8213633970008232 s，前一案例为 0.8465250529989135 s；p4 原始记录没有独立内存字段。该次重复运行未到 iteration 112，因此既有 V24/Q4 的 iteration-112 p4 baseline 结论不变。

重复运行的 compact 记录见 [v25 Q4 AC repeat result](outcomes/records/v25_q4_ac_repeat_result.json)，原始动态 checker 因终态字段缺失而标为 partial `DYNAMIC_FAIL`，这只确认“未完成”，不把受控停止误判成 solver convergence failure。
