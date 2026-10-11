# V71：热接口作用通过，固定两层迭代因总因子容量未准入

本轮已连续完成真实热作用、全部38块主子矩阵、7068行粗层及独立保存数组审核。**没有取得新的完整迭代解：局部＋粗层双倍symbolic估计为74.8056918383GiB，超过Review V69的64GiB硬门。** 因而在任何numeric之前拒绝，正式KSP调用、迭代步、返回物理候选均为0。这个结果是固定候选的资源否决，不是OOM或不收敛；没有用identity PC、全局细层LU或提高额度收尾。

这次复用V70已经保存的单元响应，把重复读映射和逐单元乘法改成按精确类批量乘、汇回共享自由度。两层预条件器原本计划先用小全局空间传递远处信息，再用重叠局部块修正剩余误差；它允许局部与粗层因子，却要求这些因子的**总**预计驻留量有界。symbolic是在分解前按稀疏连接图估算因子内存，不是已经测得的RSS。组件代数可信不等于整个预条件器已资格化，更不等于完整物理解通过。

## 1. 身份和实际执行

| 项目 | 冻结身份 |
|---|---|
| canonical / 唯一分支 | `/home/fenics/Projects/NN-Lab` / `task42_neural_coarse_inverse` |
| base / Review commit | `ccd357885f7f9be84efe3be07868cc94f13d93fc` / `41ee5ea56e19de48bee71792cbcd7081ba6e755c` |
| Review blob / SHA256 | `0705d5d2217894ae6d18254ab9ad2df1d36b4cd9` / `c722b3200ce9c241108ef7874880a8579cc78b52107046cb8737f9f281bced83` |
| O实际source | `d064028e4813e2f944a2b994e88f93c9a65f4806` |
| P实际source | `ee13ea8419b2a6cb6f137d6d975135dfe1e510e5` |
| 最终checker / 定点资格source | `a8d73e8b4bb45c0b37d65fa46c785121048150ab` |
| 物理/离散 | 原κ、0.7nm真实NOTCH；25576tet，其中1000个NOTCH tet；p5/828模式；complex128/int64 |
| 实际规模 | 完整FE1943745，内部767280，retained FE1176465，含828端口1177293行 |
| 新窗口 | 首次UTC `2026-10-11T00:37:53.636300Z`；heavy-stop `13:37:53.636300Z`；总截止 `14:37:53.636300Z`；未刷新 |

Review正文日期字段只作历史文档元数据，不用来推算新窗口。首次实际核对确认无本任务actor，fetch/ff仅本分支，报告为祖先且blob/字节一致；未回退、reset/stash/clean、修改邻worktree或共享Git配置。资格化native activation、MPI1/math/CPU1、GPU/Loader0、原ABI、完整Cκ/双周期/全部端口保持。源码先clean提交，4个one-run输入再validate。实际source与后续文档HEAD分开；最终完整Git SHA和remote结算见交付回执。

[唯一身份](outcomes/records/authority_identity_v71.json) · [实际执行索引](outcomes/records/run_index_v71.json) · [源码字节](outcomes/records/source_bindings_v71.json)。

## 2. 真实组件结果与硬停止

| 真实计算 / 含义 | measured结果 | 门与结论 |
|---|---:|---|
| 两固定复向量新旧接口作用，FE / port最大运算尺度差 | 5.21846573209e-16 / 6.43620108577e-17 | ≤1e-10，组件PASS |
| 非零内部＋port RHS完整恢复 / 独立原作用恒等式 | 0 / 1.46526959602e-14 | 全部767280内部保留，组件PASS；不是物理入射新解 |
| 一次冷读/映射/完整边界聚合 | 71.8003688981s | measured设置费用，不免费 |
| 连续三次热作用 | 1.22402047995 / 1.23098633904 / 1.31843893789s | 按原action实测，未计为端到端速度比 |
| 热cache显式载荷 | 4047298428B | ≤12GiB；局部Schur直接复用，未重建第二套 |
| 几何core＋一层周期tet halo | 初始32，行门触发6次二分，实际38块 | 每块31965–68680行，≤80000；trace写回owner恰好一次 |
| 局部主子块实际存储项合计 | 374068350 | 从全部贡献单元形成；重复项合并，未阈值drop；不是全局S |
| 实际p2粗空间＋828端口 | 6240＋828＝7068行 | ≤8192；真实矩/Piola/方向/MPC映射 |
| 稀疏Z / 粗矩阵存储项 | 23529162 / 3541640 | 没有稠密N×coarse或全列作用库 |
| 两固定粗Galerkin全作用差 | 1.46467542646e-15 / 1.49728602378e-15 | ≤1e-10；FE/port/复对偶独立分列PASS |
| 全部局部 / 粗层双倍symbolic | 79520000000 / 802000000B | 全39个成功symbolic，INFOG16/17 decimal-MB，ICNTL22=0 |
| 合计 / 许可 | 80322000000 / 68719476736B | **74.8056918383 > 64GiB，FAIL**；超11602523264B |
| 本批原全域action / 未完成界 | 8 / 下界8、上界8 | O固定2＋计时3＋RHS1＋P Galerkin2；≤600且资格≤12 |
| numeric / 正式KSP / 候选 | local0、coarse0、fine0 / 0 / 0 | **NOT_RUN_CAPACITY_BLOCKED** |

最大单块合格不能替代总和检查；全进程96GiB规划不能挪来放宽64GiB因子总门。没有实际numeric、pivot、真实PC apply或迭代趋势，均为unknown/NOT_RUN。局部内部LU仍来自父packet，不能称factor-free；新局部/粗层numeric因子为0，全局细层K/S读取、形成、factor均为0。AH未在本轮资格化，不授distributed或波长鲁棒性。

[热作用与非零RHS](outcomes/records/hot_operator_qualification_v71.json) · [全部局部/粗层原始INFOG、owner与数组](outcomes/records/bounded_pc_inventory_v71.json) · [独立保存数组审核](outcomes/records/scientific_checks_v71.json) · [全部计数](outcomes/records/explicit_counters_v71.json)。

## 3. 完整场资格没有被组件结果替代

正式顺序执行了O、P和冻结后的唯一VERIFY。ITERATE输入已实现并validate，但在P拒绝后没有盲跑。VERIFY以新进程流式消费46个新数组包，核对file/member hash、形状、dtype、唯一owner、全部38块CSR、Z/E0、固定原作用与Galerkin见证，并从原始INFOG重算拒绝；新A/factor/KSP均为0。它接受组件与拒绝的证据，**不将整体pass_gate改为true**。

| 本批完整物理项目 | 状态与原因 |
|---|---|
| 新retained / 完整u / 内部恢复场 | NOT_RUN：没有合法启动的KSP及返回候选 |
| 原true/native/augmented/port与独立direct | NOT_RUN：没有物理候选；RHS恒等式不代替此门 |
| total/scattered E/H/curl、240点、828复通道与功率 | NOT_RUN；未读V70物理参考场评分，未造零解 |
| official R/T/A/A_volume/能量 | NOT_RUN；不复用旧功率填充新解 |
| 完整同离散迭代解、连续精度、2TB/48h、NN20 | 均未资格；本批NN训练/推理0 |

历史V70完整解及其formal PASS、strict direct FAIL保持；历史P6/L5散射E/H约1.14449e-4/1.23013e-4、240点约9.56042e-4仍超过1e-4，不回写也未重算。本批没有证据评判固定PC的收敛性，容量阻塞不证明其他迭代方法不可能。

## 4. 实际成本、内存与修复

| 不重复相加的完整分段 | measured wall（s） | 口径 |
|---|---:|---|
| O正式one-run | 219.764406361 | 进程启动到监督/后代清场结束，含准入与IO |
| P正式one-run | 3392.80855081 | 全38块、粗层、symbolic及保存；不是完整求解T_N1 |
| 独立VERIFY one-run | 207.839279009 | 保存数组审核、准入与清场，0新作用/因子 |
| P中粗Galerkin装配 | 2856.99820756 | **嵌套于P**，不再加进上述3392.80855s |
| P中局部形成/保存、symbolic | 153.209144415、18.2111280153 | 同样嵌套于P，未当每次PC apply费用 |
| 父V70 BUILD / prepared SOLVE | 9646.82648389 / 12666.5476045 | 已包含在历史前缀；本轮不再次加账 |

本批结算至科学VERIFY后的已知不重叠wrapper为4185.47040215s，另有首次实现/读取/定点检查1306.96139857s的inclusive wall；初始测试和修复子区间不重复相加。最终文档检查、元数据、闭窗及交付费用由[最终成本](outcomes/records/resource_costs_final_v71.json)续记；未知CPU、未分段实现/等待及无采样峰不填0。历史已知费用下界340487.167195462s继续计入，不用plan中的pre-V70旧前缀代替最终历史账。

全批当前实测采样树峰9444700160B＝8.79606246948GiB；P峰为该值。实际最大采样gap1.60104868095s，配置0.5s不能称连续硬峰；ownswap/OOC观测0。P有效watchdog规划96/警戒112/采样stop128GiB，VERIFY64/80/96；实时宿主/cgroup、PSI、384GiB邻增长和CPU/SMT准入均按原保护，未动邻任务。generic baseline中的旧默认字段不替代resolved和live envelope中的V71额度。

只读父local_packet约4.17GB，健康q47/q63保持原hash。新数组/日志约10.03GB，精确最终存储及free在最终账更新，许可32GiB/Task632GiB/free≥50GiB。全部新大数组ignored，增量manifest引用父hash，没有复制旧数万行JSON。

初始Ruff闭包问题、缺pre资格登记导致的零actor入口失败均保留；同轮定点修复后自动完成O/P。P前修复canonical周期实体中心、真实p2 descriptor和退出审核action预留；没有重放科学失败。独立checker补全owner/CSR/原RHS/INFOG资格，9项targeted通过。交付元数据脚本一次括号SyntaxError在任何科学消费前发生，保留失败原文并只补元数据，未重新运行O/P/VERIFY。详见[修复账](outcomes/records/repair_journal_v71.json)。

## 5. 可消费边界及唯一下一pilot

[接口合同](outcomes/records/retained_iterative_contract_v71.json)允许审阅者识别健康的热作用、稀疏Z与粗Galerkin准备包；**不授当前被冻结队列再次numeric/KSP的权限**。完整冷N=1、生产时间/峰比和目标规模因子fill仍unknown。65条retained V/Z主向量合计1224384720B只是derived，本批实际Krylov库分配0；trace＋port与完整FE向量不是同一口径。

唯一下一pilot建议：在新合同中保留同物理、halo、p2粗空间及RIGHT FGMRES，复用已资格Z/E0；以**全部双倍symbolic≤64GiB**而非仅单块80000行作为一次事前几何二分准入规则，最多64块，冻结后尝试同一迭代。仍超额即收口，不扫shift/ordering/粗阶/迭代参数。当前review仅准许超行数二分，因此本轮没有擅自执行这项改变。

[目标/成本缺口](outcomes/records/target_gap_v71.json) · [依赖分组与不提升production默认](outcomes/records/selective_merge_manifest_v71.json) · [raw增量](outcomes/records/raw_archive_index_v71.json)。全部旧负结果、任务/审阅/回应/raw保持；GitHub视觉NOT_VERIFIED，CI NOT_RUN。完成同分支push、remote/full SHA、clean/upstream、closed/active null、自身后代清场和锁释放后暂停；未merge、改邻支或通知隔壁。
