# Task041 Response V11：Review V9 H0/H1进展记录

**状态：进行中。** H0只读审计、H1 fixed-H6组件/路由验证、13.5 nm Si回归及唯一一场W5 fixed-H6 public/service完整回归均已完成。W5场通过原五项残差、P4/recovery/physics和十项finalizer；但保持`performance_not_isolated`，且不是W2或0.7 nm资格。提交 `ce31f3738f469a04d23c50af0a7c7306afde3b38` 已加入严格限定的W5 fixed-H6 legacy-native descriptor路由，原validator/binder继续负责packet身份。2 nm旧packet可复用；新的fixed-H6 W2 consumer尚未启动。H2–H4仍未完成，0.7 nm/2 TB/48 h目标尚未达。

| Review V9 H0要求 | 处理 | 证据/边界 |
|---|---|---|
| 按共同边界给出5 nm非重叠阶段wall | 从两场 `consumer/markers.jsonl` 取`stage`/`wall_seconds`并计算相邻差值；monitor独占时间为unknown | [V9 H0 outcome](outcomes/hybrid_0p7nm_2tb_48h_v9.md) §逐段wall；[machine record](outcomes/records/task041_v9_h0_readonly.json) |
| 汇总1920 response与side审计全量工作 | 收入cost/modal/outer每侧行数、Q/P/PH/A6/H6调用、内部KSP迭代、P4回代和精化；指出modal 976条/侧中16条为样本/重复而960条才是formal | 两个1980行原始audit hash绑定在record；selected `operation_seconds`按phase/side保存per-RHS rank-max sums与缺失覆盖数，不累计为阶段墙钟 |
| 解释A6局部指标和完整consumer时间 | 并列局部融合/两RHS信号、outer完整阶段、P4计数差和两场 `performance_not_isolated` | 不把全流程差归到A6、P4或环境；outer PC计时按包含关系解读 |
| 13.5 nm anchor与接线链 | 记录Invocation `c0ef9dd4e7b2410182543d6c18a5e178` 的已存fixed-H6结果；说明public单`.dat`入口到factory路径、5 nm `5e-13` P4 target保留方式 | 不重跑数学未变anchor；P4精化与modal repeat/linearity是两个不同门 |
| H1 fixed-H6反馈门组件 | fixed-H6分支以8次固定反馈作用检查复数重复/线性及近零绝对误差；serial单参数1 passed，MPI2五selector每rank 8 passed | 组件测试本身只资格化门、受控错误共识和清理fixture；W5实际public/service数值结果另见下文，不从fixture推断 |
| H1 13.5 nm public/service回归 | 唯一Si anchor完整走单`.dat`、MPI8 consumer、outer、recovery、physics与十项finalizer；37 outer、264个`S_H`作用，五项真残差通过 | 一次研究锚点；`performance_not_isolated`，不外推W 5/2/0.7 nm |
| W 5 nm legacy packet与实际场 | 旧supervisor为`validated_legacy_native_packet`；唯一新W5 public/service场通过五残差、P4/recovery/physics及finalizer | packet身份沿原validator/binder核验；旧producer资源仍`unqualified`，新场资源独立记录；本场不是W2/0.7 nm资格 |
| H3材料、通道与容量只读审计 | Henke/NIST/CIAAW/BIPM/CODATA来源字节已在ignored准备目录封存并记SHA；给出0.7 nm候选插值与派生材料值；2 nm已有PEP/TOAR，`ncv/mpd`未知 | 候选材料不是正式`.dat`；未生成W 0.7输入、未运行QEP或PDE |

## 主要结论

1. Oct 3 W5参考wall为`202124.563261555 s`；新fixed-H6 W5 public-to-finalizer为`59914.951233018 s`（16.643 h）。新场outer为49而参考为5，内部侧区KSP迭代总数7732而参考为30296，P4回代/精化也更少；两场源码、方法和隔离条件不同，约70.36%的wall差只是描述，不能归因于fixed-H6单一因素。
2. 新W5累计原侧区P4 backsolve为27097、refinement为11633；owner C-LU为1次factor、307/307次累计attempt/success；固定反馈setup 8个`S_H`与正式求解合计315个`S_H`。计数按各自scope报告，不累加rank副本，也不把C matvec当作C-LU solve数。
3. 最新13.5 nm Si fixed-H6 public/service场于Invocation `443995ec69bd45d0a36a1be48ced33a3`完成，public-to-finalizer wall为`3181.091282263 s`。outer为37步、264次`S_H`；最终inner独立raw相对残差为`3.4826090281102427e-4 <= 1e-3`。只有最终inner终检值被持久保存，不能补称前36次均有逐次独立终检。此场可验证公共接线，不能代替W 5/2/0.7 nm资格。
4. 2 nm已有TOAR实现与producer数据；不是待迁移算法。0.7 nm缺正式钨材料封套、完整W外部keys和合格的h/M阶梯，2 TB与48 h都没有实测资格。
5. 下一步复用已有W2/M1200/MPI8 producer packet准备一次fixed-H6 public/service运行；不重跑QEP。保持cell-condensed、P4 target`5e-13`和最多两次同因子修正，CPU map等fresh准入时冻结。一次setup后在同一factor生命周期内连续经过outer、recovery和finalizer；32 outer只是成本/收敛判断点，不是自动停止阈值。

## 公共接线与后续W2边界

W5窄路由现已沿既有`python scripts/run_case.py <one-case.dat>`→launcher→supervisor/service→consumer链实施并完成唯一真实public/service场；没有新增第二runner或`.dat`身份字段。W5固定H6仍为显式研究分支，原方程、P4、五残差、恢复和物理门保持不变。旧producer资源`unqualified`，由新consumer自行通过资源门；这一事实不抹掉已核验的legacy-native数值packet身份。

下一步只计划复用同一public/service链读取既有W2 M1200/MPI8 producer packet，不重跑QEP。W2的官方输入记录`side_residual_correction_steps=1`，注册P4 refinement target仍为`5e-13`、最多两次同因子修正；两字段不能互相替代。CPU map、unit、root及资源门要在新准备包中一致绑定并在启动前重新准入。route-plan、leading-PH以及其他研究诊断保持关闭；不由W5结果宣称W2适配、容量通过或0.7 nm资格。

H0只读阶段没有执行测试、ABI、MPI、QEP、FE或checker。fixed-H6反馈门的production实现保持在source SHA `64ef9439ee2d527049877edfa88ce8e848e4370600f1a8b9ee41d4684709dea3`；本次H1测试阶段只改test350故障注入fixture，没有再改数值core。运行fresh serial/MPI2 ABI及下列定向测试，没有运行QEP、FE或public consumer。serial与MPI2父wall已按独立attempt各记一次V5，ABI/static/rank-local时间不计。

## H1 fixed-H6反馈门组件验证（非真实FE）

| attempt | 范围与结果 | parent `CLOCK_MONOTONIC` wall | 证据 |
|---|---|---:|---|
| Serial | `test_side_balh_fixed_h6_feedback_gate_rejects_invalid_outputs_and_cleans_up[nonfinite]`，1 passed；在原apply完成后仅污染最后rank输出，清理后完成真实allgather | 5.001762014115229 s | [serial stdout](../../results/task041_v9_fixed_h6_feedback_nonfinite_serial_20261006T032822Z/serial_pytest.stdout.log)、[attempt](../../results/task041_v9_fixed_h6_feedback_nonfinite_serial_20261006T032822Z/serial_pytest_attempt.json)、[compact](../../results/task041_v9_fixed_h6_feedback_nonfinite_serial_20261006T032822Z/serial_test_compact.json) |
| MPI2 | 五个selector、四种坏输出/重复/非线性故障参数；两个rank各8 passed，无warning；最后rank的非有限输出使全rank一致拒绝，随后collective可继续 | 5.001988966949284 s | [MPI2 stdout](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/mpi2_pytest.stdout.log)、[attempt](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/mpi2_pytest_attempt.json)、[compact](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/mpi2_test_compact.json) |

两次源码身份均为core `64ef9439ee2d527049877edfa88ce8e848e4370600f1a8b9ee41d4684709dea3`、test350 `941606bba844cdeabad3c44bedfe86c2578df7370690621c0a6611bbc32482a6`。setup门8次`S_H`、每侧H6 8次apply/16次矩阵乘、8次C动作与既有GMRES 9次solver作用加1次末检预算分列；这不是正式求解成本或性能结果。五条受保护dirty路径未变。V5 ledger由122条增至124条，SHA `60ee77b84661f91944ceffb22e9ab544178d607403f20696b5ffcd875f32fe67`；本轮仅增加两条pytest parent wall合计10.003750981064513 s。[唯一追加receipt](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/v5_ledger_append_receipt.json)。

此组件阶段的结论只限测试范围；之后的public接线和13.5 nm完整场已在下节单列。它没有资格化W 5 nm数值或性能，也没有改变普通默认。

## H1 13.5 nm Si fixed-H6 public/service完整回归

该场验证了真实`.dat`入口、service监督、consumer、外层求解、恢复与十项finalizer在一条生命周期内的接线。固定H6给模态方程提供廉价的近似反馈；它没有更换全局Maxwell方程，正式判断仍来自原外层五项真残差和物理门。

| 项目 | 实测 | 口径与边界 |
|---|---:|---|
| 身份 | source `836b7dfb377f11d8d9fd591eacb7a982f7cbbbac`；Invocation `443995ec69bd45d0a36a1be48ced33a3`；13.5 nm Si、p6/h10、M120、MPI8、cell-condensed | 研究锚点；route-plan与leading-PH复用未启用 |
| 外层/内层 | 37 outer；264次`S_H`；最终inner reason 2、7次solver作用+1次独立raw终检；raw相对残差`3.4826090281102427e-4 <= 1e-3` | 只持久化最后一次inner独立终检；不推断此前36次 |
| 原五项真残差 | global `1.8215487484151747e-9`；reported `1.821548606659606e-9`；bottom `2.284003276919731e-9`；top `5.083945967955327e-10`；modal `9.156507528011665e-10` | 五项均不超过`5e-9`；恢复、physics及80个external Q通道核验通过 |
| 物理结果 | `R/T/A/A_volume=0.3656257891736677 / 0.01299063241331313 / 0.6213835784130192 / 0.6213835795377933`；closure `1.1247740516751037e-9` | 不构成跨波长离散或0.7 nm资格 |
| setup固定反馈门 | 8次`S_H`、8次C matvec；每侧H6 8次apply、16次degree-3矩阵乘；原side预付probe为0、Schur materialized列数0 | setup门与后续求解成本分列；rank-local记录不乘8 |
| 原侧区/局部求解 | 每侧SideBalancedInverse 74次：37 first + 37 delta；内部KSP bottom/top 2410/2608步；P4 backsolve 4820/5216，refinement 0/0 | 每侧本地/复制计数，不跨rank求和；C matvec不能代表C-LU solve次数 |
| wall | setup至outer开始343.619396 s；outer 2821.718933 s；recovery 9.978173 s；recovery后至最终清理0.517839 s；consumer 3176.842516 s；public-to-finalizer 3180.339667 s；service parent 3180.537532 s；finalizer 3181.091282263 s | 按各自边界分别报告，不把嵌套区间相加；唯一workflow wall由现有finalizer记账 |
| 资源 | process-tree RSS 8,936,820,736 B；PSS 6,437,861,376 B；USS 6,069,190,656 B；专属job cgroup peak 6,214,434,816 B；job swap 0 | `performance_not_isolated`；process-tree与dedicated cgroup分列 |
| C-LU | owner rank 7 factor一次；rank-local累计字段0/0；owner last-solve报告8/8 | rank-local累计与owner单次报告scope不同；owner全run累计未持久化，记`unknown`，不从272次C matvec推算 |
| 终态 | service finalizer exit0，10/10 checks true；secondary integrated checker `not_available` | 完整13.5研究回归通过；不是W 5/2 nm、0.7 nm、2 TB或48 h资格 |

原始入口：[`consumer_summary.json`](../../../results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8_cell_condensed/task041_13p5nm_p6h10_m120_mpi8_cell_condensed__hybrid_iterative__mpi8__M120/20261006T052732.307687Z/consumer/consumer_summary.json)，SHA `21ac7e56c45d90cbe540587bda831540d42077a32477cfae8a1daa2ba11f54d9`；[finalizer summary](../../../results/task041_v9_13p5_fixed_h6_public_service_run_20261006T044333Z/finalizer/finalizer_summary.json)，SHA `04d0b4d8c2ade9f85340a363bb38b2abd9f64be4c4a0891bf9608e8fde0682f7`。V5 ledger为127项，SHA `15d4b5dcb1ed0a867e584dc89d33a52da453575697a16a45d2aed101b5964836`；该Invocation只计一次`3181.091282263 s`。不得再计consumer、outer、rank或phase时间。

## W 5 nm现有legacy-native packet与fixed-H6窄路由

本次只读检查10月3日完整5 nm运行时，结论是**数值身份未缺；fixed-H6路由兼容随后在提交`ce31f3738f469a04d23c50af0a7c7306afde3b38`中按注册W5范围实现；历史producer公共资源未资格化**。三者不能合并成“packet不合格”。本段保留路由实现前的审查时点；后续W5新consumer实测见本文末尾。

| 分类 | 现有证据 | 当前结论 |
|---|---|---|
| 数值/布局身份 | Oct 3 `run_manifest.json`：source `5bfb813870182fda172f658c8f276f58318844a5`、input SHA `a788489e9d3d582d2abbdf21b3edd535a35c9649c6d5cf7dd53952f30594c5dc`、physical SHA `65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4`、resolved SHA `278d5813aa0227d3a8ddcfb2759b197436e9f0e74fef82b7c7b01c00ce1421eb`；registered W5/p6/h4/M480/MPI8/cell-condensed、target`5e-13` | consumer身份完整；见run_manifest SHA `c75a912fab939127b422ec6882153b02281a847d988c9603e7b2c01b2385427f` |
| legacy packet | `supervisor_summary.json`记录`producer_reuse.status=validated_legacy_native_packet`，`phase_status=inherited_not_run`；descriptor `results/task041_side_balh_component_audit/task041_h3b_legacy_native_packet_descriptor.json`，SHA `175a2463e15e039ff4dec91eed6a1f011d8eca338e1d2cc98cd8e30e37d86c86` | 既有Oct3 supervisor已走legacy-native验证；当前轮未读取shards或重新运行validator |
| producer身份 | `task039.v4.h4.mode-identity.v1`；source `b01a5932e4dfaf895e81e0424e0dd88c276fb0d3`；M480/MPI8、p6/h4；input `dd7c945c1696b4f9da3e35c295071a24b796a10d164d2a819b4abe68f72f44ca`、resolved `80ce8af49e59df65b462d71a23a29d99e07a4fd77862e57b5efed4b659919b70`、physical `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` | producer是Task039 direct模型；已有legacy binding逐项核物理合同，material label不同但数值字段相等 |
| packet与keys | packet manifest SHA `306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f`，身份文件SHA `2a5cd006e87c48a89fa8166f687413ee0007346d6cf63d76c1cf9fb03ee994eb`，嵌入packet identity SHA `1e11de1d638dae427a9cf1e6dc0a3e00b26f888592cb22a3ae3428980a067b7d`；600 keys SHA `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` | `selected_mode_manifest.json` SHA `9db119a7890e00be36aaf6437299b450bc4df208b6a9e6fceea7902d4181fbe1`内`legacy_binding.pass=true`、physical equivalence与keys均pass |
| 目录契约 | 新profile validator继续要求producer root及父目录的原封套；旧布局由descriptor引用独立packet root、identity sibling和producer root | W5 fixed-H6分支现窄路由到既有legacy-native validator/binder；不复制或伪造新profile封套。13.5/2 nm和普通legacy路径不因此放宽 |
| producer资源 | Oct3 supervisor的`producer_reuse.resource.status=unqualified`、`resource_qualified=false`；只测worker tree RSS峰`10,039,554,048 B`，44,541样本，worker phase `11,447.683263 s`；public parent RSS、PSS/USS、cgroup/global swap均`not_measured` | 旧producer资源保持unqualified；不阻止复用其已验证数值packet，也不声称旧producer resource PASS。Oct3 consumer自身资源证据单独保留 |

【历史规划快照；实际状态见下方已实施记录】仅fixed-H6且严格注册W5 case允许`producer_packet_root`和`legacy_native_packet_descriptor`二选一；拒绝两者皆无或同时提供。保持`task041_legacy_native_profile`、`validate_task041_legacy_native_packet`和`bind_task041_legacy_native_consumer`的原物理、source/input/resolved、M/MPI、600-key、manifest与shard hash核验，不改新profile validator。只在`run_case.py`、`task038_launcher.py`、`task041_supervisor.py`、`task041_service.py`及`task041_exact_side_workflow.py`把fixed-H6 guard从“强制新producer root/拒绝legacy descriptor”收窄为这一W5例外，并让service command、manifest和worker传递同一个descriptor身份。P4 backend必须`cell_condensed`、target必须`5e-13`、MPI8、M480、p6/h4、V9 CPU map和V8资源合同全部继续匹配；无其他诊断，route-plan与leading-PH继续默认false。13.5/2 nm新profile路径及ordinary legacy默认保持原样。验证至少包含W5 descriptor接受、wrong target/map/scope拒绝、新root仍按原validator通过和默认legacy路径不变；不新增通用packet迁移框架。

## H1 W5 legacy路由与owner计数测试（2026-10-06）

实现提交为`ce31f3738f469a04d23c50af0a7c7306afde3b38`，parent为`4d823b9f4c85d0271f572e916ea7049d6b51fabc`。test351最终SHA为`b933f4b48581f70b8f03507db31f709ba2c776cfc6bc0522f4916c06a260431d`；其他八个源文件SHA与提交前冻结值一致。测试按修前/修后分attempt记录，不声称最终源码上的整组selector一次全过。

| Attempt | 实际执行与结果 | 父 wall | 证据 |
|---|---|---:|---|
| 初始serial | 六个selector按序启动；实际收集7项，6 passed后，第7项在worker路由selector中因fixture把默认CPU map错误期望为`None`而失败；`-x`后两个test350 selector未执行。失败只涉及测试期望 | `10.002066798973829 s` | [stdout](../../results/task041_v9_w5_legacy_count_serial_20261006T074100Z/serial_pytest.stdout.log) SHA `0451455663b41ce138cb3612a6ceba2fa65073ff3a0ed03ec500e597a422ef63`；[attempt](../../results/task041_v9_w5_legacy_count_serial_20261006T074100Z/serial_pytest_attempt.json) |
| 修正后定向serial | 一行test-only断言改为比较既有`default_rank_cpus`；随后worker路由与两个test350 solver selector共3项通过，保留一个由非有限PC故障注入产生的`RuntimeWarning` | `10.00147465406917 s` | [stdout](../../results/task041_v9_w5_legacy_count_serial_retry2_20261006T075129Z/serial_pytest.stdout.log) SHA `d60f8e9d22b7c219d38ca7b845e7b39ba73cbad20b4c4f0eb4323df7d36c5624`；[compact](../../results/task041_v9_w5_legacy_count_serial_retry2_20261006T075129Z/serial_compact.json) SHA `0414268eb680eccf42a92a88fdadb5c25078393c1b59d02ef46f5eedc19a272a` |
| MPI2 | 两个test350 solver selector；每rank `2 passed, 1 warning`，warning为同一受控非有限PC故障路径的`RuntimeWarning`，原文保留 | `5.00106007209979 s` | [stdout](../../results/task041_v9_w5_legacy_count_mpi2_20261006T075409Z/mpi2_pytest.stdout.log) SHA `5e3fe8ffd03a510491dad15b38b1cbc68f91bed06429ef4b26ee5cd089935b0c`；[compact](../../results/task041_v9_w5_legacy_count_mpi2_20261006T075409Z/mpi2_compact.json) SHA `2d8e98c1e60382bc8063b015a906aa67a2c378419a716f9aeb25f490133a181a` |

第一次重试派生runner因未设置`BLIS_NUM_THREADS`在pytest前停止（无pytest wall）；没有覆写该记录。实际charged V5 entries只包括初始失败serial、修正后定向serial和MPI2三个唯一pytest attempt；ABI/static及preflight-only错误不计。最终V5 ledger为130项、SHA `11679a139bbcd5f8a40a7b1758a9434df396d50c2e069fd46f115620d2a5c7f4`。该段只证明组件测试合同；随后W5实际场由新一节单独记录，不把路由fixture说成FE或MPI8证据。

## H1 W5 fixed-H6 public/service完整回归（2026-10-06）

| 项目 | 实测 | 边界 |
|---|---:|---|
| 身份 | source `d6fe6b2b239896e66d8c5d1bf9b8a0e45931a561`；Invocation `2539de4d129f41e2ac49536bfd3b6fde`；W5/p6h4/M480/MPI8/cell-condensed | 复用既有legacy-native packet；旧producer资源仍`unqualified` |
| 数值 | outer 49；五真残差最大`4.87285789944735e-9 <= 5e-9`；R/T/A/A_volume=`0.7331842734229947/0.00022009869546076797/0.2665956278815445/0.2665962726246991` | 原方程与物理门通过；qualification仍`research_only_approximate_candidate` |
| 固定反馈工作 | 原预付sample probe 0；setup `S_H` 8次；正式inner `S_H` 307次；合计315次；每侧H6 apply/MatMult为315/630；C matvec 315 | owner C-LU factor 1次、owner累计solve 307/307；不按rank求和 |
| 原侧区与P4 | bottom/top内部KSP 3839/3893；P4 backsolve 11551/15546；refinement 3873/7760 | 自适应侧BAL_H与固定H6反馈计数分列 |
| 生命周期/资源 | unique finalizer wall `59914.951233018 s`；process-tree RSS `42573258752 B`；job cgroup峰 `41376940032 B`；finalizer 10/10 | `performance_not_isolated`；integrated checker `not_available/not_run` |

marker非重叠阶段、owner计数scope、内存口径、Oct 3对照和完整artifact hashes见[W5 outcome](outcomes/hybrid_0p7nm_2tb_48h_v9.md)与[机器record](outcomes/records/task041_v9_fixed_h6_public_5nm.json)。唯一workflow wall由ExecStopPost finalizer记账；不另计consumer/outer/rank/phase时间。

## H2 W2 packet与容量只读计划（尚未准入）

官方W2输入为p6/h1.5、M1200、MPI8、cell-condensed；既有producer来自2026-09-18的TOAR packet，每方向选择1200模态，producer封套记录`TASK041_MODE_PREP_PACKET_READY`并已释放producer scope。旧packet与当前官方输入的SHA不同；先前逐行比较只见`model_id`和`run_id`不同，身份值分列保存，未改写packet。当前正式consumer仍须沿public链实际完成验证，本文没有读shards或运行validator。

旧W2 consumer在历史sampled-repeat门停止，formal为0/4800；这不是packet身份失败。旧consumer在正式响应前测到process-tree RSS峰`642449637376 B`。此前单次node0观察扣reserve后约`442474672128 B`，但该观察没有绑定独立raw快照且不是fresh admission；两者仅提示容量风险，不能预测fixed-H6新路线峰值。W2新unit/root、CPU map、ABI和资源策略均尚未准备或资格化，未运行QEP、FE或新场。详细身份哈希、容量口径和未来准入缺项见[W2只读计划](../../results/task041_v9_w2_fixed_h6_readonly_preparation_20261007/w2_readonly_plan.json)，SHA `e7f33e11636fc541958a343fae037cff0f14f91568751f1ba62f16ecc89f5aab`；W2计划不继承W5资源限值，也不把输入中的`side_residual_correction_steps=1`误作P4 target，注册P4仍是`5e-13`且最多两次同因子修正。
