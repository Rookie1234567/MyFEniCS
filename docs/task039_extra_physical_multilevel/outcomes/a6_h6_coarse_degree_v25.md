# V25 A6/H6 粗阶对照收口

本任务有两条主线。第一条是 S1/S2 工程实现：把 A6 与 H6 的重复局部计算改成可复用的 sum-factorized 后端，并把 P6q 粗阶参数、真实调用计数和 retained timing 接入 runner；它解决算子动作重复、难以核对的问题，代价是新增后端、schema 和测试。第二条是 S3–S6 正式证据：在实现冻结后，用同一 990-cell、13.5 nm、p6/h7.5、Full3D、MPI1、complex128 模型比较 p4、p3、p2 粗阶，并把残差、物理量和资源终态分开登记。

## 首屏结果

| 模型 | 完整流程或停止耗时（monotonic，s） | 纯 KSP monotonic（s） | 步数/进度 | 最后已测显式真残差 | RSS/PSS 峰值（B） | 状态 |
|---|---:|---:|---:|---:|---:|---|
| V24 p4 基线 | 4579.015917060999 | 3716.1522563079925 | 126 | 9.283164961979326e-7 | 7339319296 / 7307023360 | 已通过，authority limited |
| Q4 p4 | 4718.70844729399 | 3766.626355408 | 126 | 9.283165086752956e-7 | 7389360128 / 7357231104 | 已通过，authority limited |
| Q3 p3 | 7065.949492944987 | 6082.501362726 | 361 | 9.460140452867132e-7 | 4031815680 / 3999603712 | 已通过，authority limited |
| Q2 p2 | 15755.054311790009（start-to-stop） | unknown，无 KSP end | 1048 完成；PC 1049 ledger；PC 1052 active partial | 6.086703757232677e-4 | 2702069760 / 2670846976（observed PSS） | RESOURCE_CONTROLLED_STOP |

Q4 是 V25 中最快完成的同新 backend 场；Q3 是已通过场中 RSS/PSS 最低者。Q2 的较低已观测内存不能进入“合格最省内存”排名，因为它没有完成物理终态，且有一个早期编译器样本的 PSS 不可读。

按纯 KSP monotonic 除以已完成显式迭代计，V24/Q4 单步分别为 29.4932718755 s 与 29.8938599636 s；Q4 相对 V24 的完整 workflow 增加 2.3282088372 min、RSS 增加 50040832 B。Q3 单步为 16.8490342458 s，但步数是 Q4 的 2.865079365 倍；因此整体 workflow 反而比 Q4 增加 39.1206840942 min，同时 RSS 降低 45.43755332%。单步值不能替代完整 workflow 结论。

## 迭代 112 的 p4 基线

这里的“耗时”严格保留原始 monitor 字段 solve_seconds 的定义，不把它改称纯 KSP monotonic，也不与完整 KSP 区间混加。两条记录都是同一 990-cell p6/h7.5 模型、同一迭代 112 的原始字段。

| p4 基线 | 显式真残差 | 原始记录 solve_seconds（s） | 该次样本 RSS/PSS（B） | swap |
|---|---:|---:|---:|---:|
| V24 | 2.7139958442857524e-6 | 3606.8307935579464 | 7334645760 / 7302341632 | 0 |
| V25 Q4 | 2.71399585136905e-6 | 3437.2333360950015 | 7384477696 / 7352336384 | 0 |

这就是本轮要求的 p4 对照；旧 p6/h10 的 112 步记录不混入本表。Q3/Q2 的同号迭代 112 原始记录保存在各自 compact 中，但不作为 p4 基线。

## 每 16 次迭代的共同残差检查点

下表只取各场 `monitor_residuals.jsonl` 中的显式真残差，按相同迭代号对齐。`—` 表示该场在此迭代号没有记录；Q2 的 endpoint 不是 official final，而是受控停止前最后完成的显式 iteration 1048。

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

后续每 16 次的报告口径沿用这张表：残差、相同迭代号的原始 `solve_seconds`，以及该记录的 RSS/PSS；没有记录就明确写“无记录”。

## 阶段时间与生命周期口径

interface setup 是整体 setup 的一个 inclusive 子区间，不能和完整 setup 混比。

| 阶段 | Q4 | Q3 | Q2 |
|---|---:|---:|---:|
| 完整 setup monotonic | 836.8461274599977 s | 935.0583148549777 s | 486.12522399 s（事件起止派生） |
| interface setup inclusive 子区间 | 255.8490446670039 s | 112.08410538101452 s | unknown |
| factor symbolic / numeric | 0.597822266005096 / 218.3896326339891 s | 0.5611445909889881 / 93.70157288498012 s | 0.058441740984562784 / 3.920166377007263 s |
| p4 solve ledger | 129.8930470560881 s | 83.91039983707014 s | no terminal p4 end |
| 纯 KSP monotonic | 3766.626355408 s | 6082.501362726 s | unknown |
| final native check | 11.11452951899264 s | 5.658712063013809 s | not_run |
| release check | 28.718534543004353 s | 7.860895881021861 s | not_run |
| official postprocess | 33.62914118100889 s | 15.513572724012192 s | not_run |
| compile events | 11，11 hit，sum 0.016517077005119063 s | 11，10 hit/1 miss，sum 22.125253679056186 s | no terminal compile ledger |

Q4/Q3 的 factor numeric RSS/PSS 是单个 numeric_resource snapshot，不是整个 factor 窗口峰值：Q4 为 6564626432/6532520960 B，Q3 为 2792673280/2760546304 B。全流程峰值只采用上表首屏 watchdog 账本。此前的 4131.5857317930115 和 6650.853006977283 只保留为 raw solver 字段，不标成 final evaluation 阶段耗时。

按物理 summary 的 lifecycle 边界与 watchdog `parent_clock.monotonic` 重新对齐后，分阶段的 simultaneous process-tree 采样峰值如下；这些是窗口内采样峰值，不是把 raw `worker_phase=solve` 整段冒充纯 KSP。

| lifecycle 窗口 | Q4 RSS/PSS（B） | Q3 RSS/PSS（B） | 样本数 Q4/Q3 |
|---|---:|---:|---:|
| full setup | 7147806720 / 7115721728 | 3783094272 / 3750958080 | 3124 / 3451 |
| pure KSP solve_only | 7384489984 / 7352404992 | 4015337472 / 3983202304 | 13318 / 23088 |
| final native check | 7387275264 / 7355190272 | 4016586752 / 3984450560 | 38 / 22 |
| release check | 7387275264 / 7355173888 | 3994566656 / 3961381888 | 98 / 30 |
| official postprocess | 7375278080 / 7343121408 | 4031815680 / 3999603712 | 115 / 59 |

Q2 在受控停止前没有对应的 complete lifecycle/final 窗口，保留其 terminal sample 账本，不外推为纯 KSP 峰值。

## 尺寸、因子、缓存和调用

| 项目 | Q4 p4 | Q3 p3 |
|---|---:|---:|
| p6 full/active/interior/trace rows | 667152 / 199260 / 445500 / 221652 | 667152 / 199260 / 445500 / 221652 |
| coarse full/active/interior/trace rows | 201520 / 84600 / 106920 / 94600 | 86652 / 45360 / 35640 / 51012 |
| condensed rows；factor rows；NNZ used/allocated | 84680；84680；32320342 / 45403840 | 45440；45440；9982160 / 17152480 |
| factor allocated/used；entries | 4687 / 4326 MB；221594144 | 3171 / 1413 MB；73058906 |
| retained numeric cache；raw/oriented classes | 24541920 B；12 / 26 | 4047264 B；12 / 26 |
| native A4；p4 logical/physical；repairs | 267；262 / 267；5 | 726；726 / 726；0 |
| A6 live/native witness | 263 / 29 | 738 / 63 |
| H6 apply/matrix/power10；P/PH | 131 / 282 / 20；263 / 269 | 363 / 746 / 20；727 / 740 |

Q4 的 factor MUMPS used/allocated 与 simultaneous RSS 是不同账本，按上表分列。Q3 同理。Q4/Q3 共享缓存和调用计数来自各自 physical summary，不由汇总表重新推算。

累计工程耗时也按 parent/child 口径分开登记；父 wrapper 与子 kernel 可能重叠，不能相加成完整 workflow。

| 账本 | Q4 | Q3 |
|---|---:|---:|
| live A6 total；其中 volume / DtN | 1332.467643185184；1330.7428043539403 / 1.2753846961422823 s | 2569.307760093361；2565.767899198516 / 2.5622179692436475 s |
| native A6 witness total；volume / DtN | 225.27302363597846；224.5926196010114 / 0.6324881170003209 s | 356.3027427189809；355.94924291592906 / 0.2721792981028557 s |
| native A4 total | 655.2644249749428 s | 611.2342456796905 s（legacy key，实际为 A3） |
| H6 apply parent；B6 apply measured | 775.3049049579422；262 次 / 770.4665523900039 s | 1456.900879892928；726 次 / 1447.5354960261611 s |
| H6 matrix mult；power10 matrix mult | 282 / 810.283604650991 s；20 / 39.81705226098711 s | 746 / 1545.2455900621717 s；20 / 97.71009403601056 s |
| diagonal setup；power10 setup | 47.394968193999375 / 39.93837261298904 s | 112.18477031201473 / 97.9184494529909 s |
| p4 solve / reduce / recover | 129.8930470560881 / 114.03232426512113 / 113.30134338504286 s | 83.91039983707014 / 108.74270782875828 / 99.80366611870704 s |
| P / PH / route | 115.96566753796651 / 103.42713105508301 / 3.1915090329857776 s | 131.6326058304403 / 96.62534810282523 / 5.794357740494888 s |
| native Aq projection timing | 未单独记录；projection check PASS | 未单独记录；projection check PASS |

B6 的 measured apply 取同一 physical ledger 的 matrix-mult 总数减去 power10 的 20 次；metadata 中旧的 `calls_per_PC=4` 保留，但不用于推算实测调用数。

## S1/S2 operator evidence

实现冻结前的 sum-factorized operator pair 已完成 equivalence 检查。选中的 v27 compact 给出 A6 full 中位数 5.615303212005529 → 3.326707318992703 s、H6 apply 8.367951847998484 → 3.6148972290029633 s、H6 setup 144.1912405710027 → 89.64910604900797 s；最大相对差分别为 7.27e-15、2.16e-16、9.41e-16。配对进程 RSS/PSS 峰值为 1421533184/1389453312 B，包含 baseline 与 candidate 同时驻留，不能当 candidate-only 内存。

旧 v26 配对仍保留 H6 apply 中位比 1.0057808725574315 和一次 executor-controlled interruption 349.01716884099005 s；它是 operator 负候选，不是 formal PDE 失败。S1/S2 的收益没有直接升级成端到端 PDE 加速结论。

S1 选中的 v27 operator worker 为 MPI1/thread1，workflow monotonic 710.3849701840081 s，conservative settlement 789.6493765678632 s；保留的 v26 负候选为 915.8957639279979 s / 1016.5861852233071 s。2-thread 与 4-thread formal qualification 均未运行。

## Q2 受控停止

Q2 的完整 setup 为 486.12522399 s（既有事件起止派生）；p6 full/active/interior/slave/trace/appended rows 为 667152/199260/445500/22392/221652/80，coarse p2 为 26656/18180/5940/2536/20716/80，factor rows 为 18260，NNZ/entries 为 1913120/14359560。factor symbolic/numeric 为 0.058441740984562784/3.920166377007263 s，MUMPS allocated/used 为 2506/278 MB，retained cache 262704 B。已完成的 native Aq projection check 通过（DtN relative 5.362129756528201e-15、volume relative 1.1762517120345644e-14、slave-zero true）；这属于 setup/inner evidence，不是 terminal official result。

Q2 watchdog 在 156673.960582131 monotonic 发出 GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED，随后整棵子进程树清场，leader exit 为 -9，remaining children 为空。触发样本在 elapsed 15753.554006381979 s，RSS/PSS/VmSwap 为 2701971456/2669953024/0 B，effective available 为 11173453824 B；最后一个已完成显式 iteration 1048 的样本 effective available 为 11193122816 B。全局 pswpin 增量为 0、pswpout 增量为 7，但该全局活动无法归因给本作业，不是已证明 OOM。

Q2 最后一个完成的显式记录是 iteration 1048，真残差 0.0006086703757232677；PC 1049 只有 outer-PC ledger，PC 1052 是 active PC sequence，不是 outer iteration，raw p4 record 为 partial。没有 final KSP end、final native check、post-release residual、final field、official output 或终态 dynamic checker summary。因此 Q2 只能记为 RESOURCE_CONTROLLED_STOP / CONVERGENCE_NOT_ESTABLISHED_BEFORE_STOP，不能称数值方法失效、OOM 或 max-iteration 2048 不收敛。

对 active partial raw p4 packet `pc001052/logical002103`，inner revalidation 的 native Aq return residual 为 1.0078163816265527e-12；扫描 2103 个 raw inexact packet 的最大 native A4 residual/g norm 为 7.727968728108255e-12，超过 1e-10 的条目为 0，factor hash 唯一值为 46eb9afe3fe396410b95b001e836f77aed52bb807362ff49520617b16fc51ebc。该 packet 的累计 elapsed/reduce/solve/recover 为 320.0523956193065 / 140.69881518252078 / 48.80859945167322 / 129.88294802472228 s；它只能说明 inner raw packet 质量，不能升级为 outer 或 official 完成。

watchdog 60683 个样本中 RSS 全部可读，RSS 峰值 2702069760 B；PSS observed peak 为 2670846976 B。唯一缺口是启动后 8.177329701982671 s 的 setup compiler ld（PID 698126）一个样本 PSS 不可读，故记录 pss_all_readable=false；这不影响 RSS 账本。

## 证据边界

Q4、Q3 的 final explicit/post-release residual、官方 R/T/A、80 通道和动态 checker 均通过，但没有匹配的 h7.5 independent reference，不能宣称 continuum convergence。Q2 没有 official result。机器可读记录为 [components](records/a6_h6_coarse_degree_v25_components.json)、[frozen manifest](records/a6_h6_coarse_degree_v25_frozen_manifest.json)、[Q4](records/a6_h6_coarse_degree_v25_q4.json)、[Q3](records/a6_h6_coarse_degree_v25_q3.json)、[Q2](records/a6_h6_coarse_degree_v25_q2.json) 和 [decision](records/a6_h6_coarse_degree_v25_decision.json)。

没有在实现冻结后修改数值源码，没有重启 Q2，没有启动第四场，也没有因 metadata 重算旧证据。
