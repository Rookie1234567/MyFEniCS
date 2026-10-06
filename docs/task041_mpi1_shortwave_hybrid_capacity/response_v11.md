# Task041 Response V11：Review V9 H0/H1进展记录

**状态：进行中。** H0只读审计、H1 fixed-H6组件测试和一场13.5 nm Si public/service完整回归已完成。13.5 nm场通过原五项残差、恢复和物理门；它不是W 5 nm、2 nm或0.7 nm资格。Review V9的W 5 nm新路线尚未运行：10月3日已有完整5 nm数值锚点及经过legacy-native validator的packet，但当前fixed-H6入口只接收新profile目录形状。H2–H4仍未完成，0.7 nm/2 TB/48 h目标尚未达。

| Review V9 H0要求 | 处理 | 证据/边界 |
|---|---|---|
| 按共同边界给出5 nm非重叠阶段wall | 从两场 `consumer/markers.jsonl` 取`stage`/`wall_seconds`并计算相邻差值；monitor独占时间为unknown | [V9 H0 outcome](outcomes/hybrid_0p7nm_2tb_48h_v9.md) §逐段wall；[machine record](outcomes/records/task041_v9_h0_readonly.json) |
| 汇总1920 response与side审计全量工作 | 收入cost/modal/outer每侧行数、Q/P/PH/A6/H6调用、内部KSP迭代、P4回代和精化；指出modal 976条/侧中16条为样本/重复而960条才是formal | 两个1980行原始audit hash绑定在record；selected `operation_seconds`按phase/side保存per-RHS rank-max sums与缺失覆盖数，不累计为阶段墙钟 |
| 解释A6局部指标和完整consumer时间 | 并列局部融合/两RHS信号、outer完整阶段、P4计数差和两场 `performance_not_isolated` | 不把全流程差归到A6、P4或环境；outer PC计时按包含关系解读 |
| 13.5 nm anchor与接线链 | 记录Invocation `c0ef9dd4e7b2410182543d6c18a5e178` 的已存fixed-H6结果；说明public单`.dat`入口到factory路径、5 nm `5e-13` P4 target保留方式 | 不重跑数学未变anchor；P4精化与modal repeat/linearity是两个不同门 |
| H1 fixed-H6反馈门组件 | fixed-H6分支以8次固定反馈作用检查复数重复/线性及近零绝对误差；serial单参数1 passed，MPI2五selector每rank 8 passed | 只资格化组件门、受控错误共识和清理fixture；未证明public单`.dat`路由或真实5 nm FE |
| H1 13.5 nm public/service回归 | 唯一Si anchor完整走单`.dat`、MPI8 consumer、outer、recovery、physics与十项finalizer；37 outer、264个`S_H`作用，五项真残差通过 | 一次研究锚点；`performance_not_isolated`，不外推W 5/2/0.7 nm |
| W 5 nm legacy packet复用 | 10月3日supervisor记为`validated_legacy_native_packet`，selected-mode binding的物理合同和600 external keys通过；fixed-H6当前guard排斥descriptor/binding | 数值身份存在；是入口目录形状兼容缺口。旧producer公共父/cgroup资源未资格，仍记`unqualified`，不伪造成PASS |
| H3材料、通道与容量只读审计 | Henke/NIST/CIAAW/BIPM/CODATA来源字节已在ignored准备目录封存并记SHA；给出0.7 nm候选插值与派生材料值；2 nm已有PEP/TOAR，`ncv/mpd`未知 | 候选材料不是正式`.dat`；未生成W 0.7输入、未运行QEP或PDE |

## 主要结论

1. 最新完整5 nm场通过数值/物理门，但public-to-finalizer wall为`202124.563261555 s`（56.146 h），大于48 h目标。与9月28日的同类consumer时间相差约`+6.76%`，但两场source不同且均`performance_not_isolated`，只能作描述。
2. 两场内部KSP迭代合计同为30296；10月3日P4 backsolve与refinement各多8686次。数据证明计数工作有变化，不证明其单独导致wall差。
3. 最新13.5 nm Si fixed-H6 public/service场于Invocation `443995ec69bd45d0a36a1be48ced33a3`完成，public-to-finalizer wall为`3181.091282263 s`。outer为37步、264次`S_H`；最终inner独立raw相对残差为`3.4826090281102427e-4 <= 1e-3`。只有最终inner终检值被持久保存，不能补称前36次均有逐次独立终检。此场可验证公共接线，不能代替W 5/2/0.7 nm资格。
4. 2 nm已有TOAR实现与producer数据；不是待迁移算法。0.7 nm缺正式钨材料封套、完整W外部keys和合格的h/M阶梯，2 TB与48 h都没有实测资格。
5. 下一步针对注册W 5 nm fixed-H6研究scope，窄接通既有legacy-native validator/binder与fixed-H6候选；不要制造新profile封套。只接受精确5 nm、p6/h4、M480、MPI8、cell-condensed、P4 target`5e-13`、冻结CPU map和V8资源政策；13.5/2 nm与普通legacy路径保持原合同。保留原方程、五残差、recovery/physics门；旧producer资源仍为`unqualified`。

## 接线审查边界

建议使用现有`python scripts/run_case.py <one-case.dat>`和Task041 public supervisor/candidate consumer命令链，不引入第二runner，也不把flag塞入新`.dat`身份字段。未来实现需要以同一命令/manifest实际透传opt-in，worker不接受只有wrapper局部修改的隐式开关。13.5 Si仍要求`target=None`；5 nm W必须继续绑定registered cell-condensed正式case、`5e-13`侧区P4 refinement target和最多两次同factor correction。模态fixed-H6 repeat/linearity是另一个PC门，二者不能互相替代。

如果systemd service config也要验证flag与public argv一致，`src/runners/task041_service.py`包含受保护的Node0内存Gate工作区；以后只能叠加窄hunk并完整保留原五个dirty文件身份，不能用整文件替换或将该工作混入阶段提交。输入校验文件也有受保护Node0/2 nm改动；当前建议不新建`.dat`字段，因而不需要动它。

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
| C-LU | owner rank 7 factor一次；累计attempt/success字段0/0，但owner inventory和last-solve为8/8 | 全run累计字段互相矛盾，故总C-LU solve次数记unknown；不从272次C matvec推算 |
| 终态 | service finalizer exit0，10/10 checks true；secondary integrated checker `not_available` | 完整13.5研究回归通过；不是W 5/2 nm、0.7 nm、2 TB或48 h资格 |

原始入口：[`consumer_summary.json`](../../../results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8_cell_condensed/task041_13p5nm_p6h10_m120_mpi8_cell_condensed__hybrid_iterative__mpi8__M120/20261006T052732.307687Z/consumer/consumer_summary.json)，SHA `21ac7e56c45d90cbe540587bda831540d42077a32477cfae8a1daa2ba11f54d9`；[finalizer summary](../../../results/task041_v9_13p5_fixed_h6_public_service_run_20261006T044333Z/finalizer/finalizer_summary.json)，SHA `04d0b4d8c2ade9f85340a363bb38b2abd9f64be4c4a0891bf9608e8fde0682f7`。V5 ledger为127项，SHA `15d4b5dcb1ed0a867e584dc89d33a52da453575697a16a45d2aed101b5964836`；该Invocation只计一次`3181.091282263 s`。不得再计consumer、outer、rank或phase时间。

## W 5 nm现有legacy-native packet与fixed-H6入口兼容缺口

本次只读检查10月3日完整5 nm运行。结论是**数值身份未缺；当前fixed-H6入口目录契约不兼容既有legacy-native文件布局；历史producer公共资源未资格化**。三者不能合并成“packet不合格”。

| 分类 | 现有证据 | 当前结论 |
|---|---|---|
| 数值/布局身份 | Oct 3 `run_manifest.json`：source `5bfb813870182fda172f658c8f276f58318844a5`、input SHA `a788489e9d3d582d2abbdf21b3edd535a35c9649c6d5cf7dd53952f30594c5dc`、physical SHA `65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4`、resolved SHA `278d5813aa0227d3a8ddcfb2759b197436e9f0e74fef82b7c7b01c00ce1421eb`；registered W5/p6/h4/M480/MPI8/cell-condensed、target`5e-13` | consumer身份完整；见run_manifest SHA `c75a912fab939127b422ec6882153b02281a847d988c9603e7b2c01b2385427f` |
| legacy packet | `supervisor_summary.json`记录`producer_reuse.status=validated_legacy_native_packet`，`phase_status=inherited_not_run`；descriptor `results/task041_side_balh_component_audit/task041_h3b_legacy_native_packet_descriptor.json`，SHA `175a2463e15e039ff4dec91eed6a1f011d8eca338e1d2cc98cd8e30e37d86c86` | 既有Oct3 supervisor已走legacy-native验证；当前轮未读取shards或重新运行validator |
| producer身份 | `task039.v4.h4.mode-identity.v1`；source `b01a5932e4dfaf895e81e0424e0dd88c276fb0d3`；M480/MPI8、p6/h4；input `dd7c945c1696b4f9da3e35c295071a24b796a10d164d2a819b4abe68f72f44ca`、resolved `80ce8af49e59df65b462d71a23a29d99e07a4fd77862e57b5efed4b659919b70`、physical `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` | producer是Task039 direct模型；已有legacy binding逐项核物理合同，material label不同但数值字段相等 |
| packet与keys | packet manifest SHA `306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f`，身份文件SHA `2a5cd006e87c48a89fa8166f687413ee0007346d6cf63d76c1cf9fb03ee994eb`，嵌入packet identity SHA `1e11de1d638dae427a9cf1e6dc0a3e00b26f888592cb22a3ae3428980a067b7d`；600 keys SHA `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` | `selected_mode_manifest.json` SHA `9db119a7890e00be36aaf6437299b450bc4df208b6a9e6fceea7902d4181fbe1`内`legacy_binding.pass=true`、physical equivalence与keys均pass |
| 目录契约 | 现新profile validator要求producer root含`mode_prep_summary.json`、`packet_identity.json`、`selected_mode_packet/manifest.json`，父目录另有`supervisor_summary.json`和`selected_mode_manifest.json`。旧布局由descriptor引用独立packet root、identity sibling和producer root | 这是文件布局/入口兼容问题；不应复制或伪造新profile封套 |
| producer资源 | Oct3 supervisor的`producer_reuse.resource.status=unqualified`、`resource_qualified=false`；只测worker tree RSS峰`10,039,554,048 B`，44,541样本，worker phase `11,447.683263 s`；public parent RSS、PSS/USS、cgroup/global swap均`not_measured` | 旧producer资源保持unqualified；不阻止复用其已验证数值packet，也不声称旧producer resource PASS。Oct3 consumer自身资源证据单独保留 |

最薄后续方案（本轮不实施）：仅fixed-H6且严格注册W5 case允许`producer_packet_root`和`legacy_native_packet_descriptor`二选一；拒绝两者皆无或同时提供。保持`task041_legacy_native_profile`、`validate_task041_legacy_native_packet`和`bind_task041_legacy_native_consumer`的原物理、source/input/resolved、M/MPI、600-key、manifest与shard hash核验，不改新profile validator。只在`run_case.py`、`task038_launcher.py`、`task041_supervisor.py`、`task041_service.py`及`task041_exact_side_workflow.py`把fixed-H6 guard从“强制新producer root/拒绝legacy descriptor”收窄为这一W5例外，并让service command、manifest和worker传递同一个descriptor身份。P4 backend必须`cell_condensed`、target必须`5e-13`、MPI8、M480、p6/h4、V9 CPU map和V8资源合同全部继续匹配；无其他诊断，route-plan与leading-PH继续默认false。13.5/2 nm新profile路径及ordinary legacy默认保持原样。验证至少包含W5 descriptor接受、wrong target/map/scope拒绝、新root仍按原validator通过和默认legacy路径不变；不新增通用packet迁移框架。
