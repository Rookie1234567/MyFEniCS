# Response V13：Review V11 的 P0/P1 执行与 W0.7 首场终态

本文件回应 Task041 Review V11 的当前执行批次。任务目录未提供单独 `README.md`；本轮依照仓库规则读取 `task.md`、Review V11、此前 Response V12、outcomes、仓库文档规则及开发总账。W5 的弱显著衍射通道按用户决定延期处理；保留其原失败与比较工件，不写成通过，也不作为本轮 W0.7 的前置。W2 本批未推进，避免延误 W0.7 主线。

## P1：唯一 W0.7 reduced warm 场终态

本次是复用既有 producer packet 的一次 warm consumer。它真实构造并数值分解了两侧 P4，但在 fixed-H6 模态内层第二次求解中未通过残差门；因此只能说计算到达 outer iteration 1，不能说得到完整电磁场或通过数值验收。

| 项目 | 终态事实 |
|---|---|
| 身份 | Invocation `797ae38854d546898a895c81d803a5ec`；unit `task041-v11-w0p7-pilot80gib-pord-warm-cpu10-11-14-15-16-17-18-19-20261009T074322Z.service`；runroot `results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z`；runtime source `47fc621a478adf26ebe9ca41d54563e188bab1d1`。复用 producer source `2708214386d38bd69f73e6b196c8ed843bb53d81`，本 Invocation QEP=0 |
| 实际启动绑定 | post-docs 封存包 `results/task041_v11_w0p7_pilot80gib_pord_warm_preparation_20261009T074322Z_postdocs_20261009T080921Z/`；config SHA `9798da6cf29498ab20975e306674c95d80ac62b8abc636bf9ea76b97bb201291`；systemd argv SHA `0cbd2c1f6a72608c5bc418ceef324a70f42eaa645ece072e1a49b5894415cc80`。run launch manifest绑定此post-docs config；下方旧 `b4bf…/363dbb…` 仅是修订前准备快照，不是本次实际启动绑定 |
| 模型与启动链 | W 材料缩减 pilot，10×5 nm、p6/h0.70、M400/MPI8、接口2/22 nm、matched L20/N29/h20/29；CPU map `[10,11,14,15,16,17,18,19]`。packet 沿原 public consumer 验证/读取路径使用 |
| 资源门 | hard `85,899,345,920 B`、warning `77,309,411,328 B`、政策 W `8,589,934,592 B`、node0 MemFree reserve/floor `412,316,860,416 B`；host MemAvailable 是独立检查项。runroot service summary 的 process-tree 峰 `47,073,288,192 B`，专属 job cgroup 峰 `44,504,326,144 B`，job swap 峰0；consumer resource summary 另报 process-tree 峰 `47,027,847,168 B`，保留其独立记录口径。两路报告都低于 cap；未发生资源预算拒绝、OOM 或受控停止 |
| 启动 NUMA 资格 | consumer startup 的 MPI8 rank-NUMA collective qualification 为 `passed`；map `[10,11,14,15,16,17,18,19]`，rank affinity、node0 nodemask 与六线程变量通过；以该qualification记录为准，不以零散 `numa_maps` 行替代 |
| P1 阶段 | one-cell 数值因子完成后销毁；bottom 与 top P4 数值因子均完成；fixed-H6 的 setup 重复/线性检查通过。outer iteration 1 progress 在 wall `7483.011134606088 s`（elapsed `3446.190459259087 s`）记录decision `ITERATING`；当时`pc_apply_count=1`、modal inner solve count=1：global true relative residual `0.14384990469330358`，bottom `0.023151106492442418`，top `0.09198938711519462`，modal `0.8384510021279358`。这些是中途进度值，不是最终五项残差门 |
| 失败的内层求解 | fixed-H6 modal solve 总调用2次、其中1次未收敛。失败的第二次 solve：KSP reason `-3`，迭代8，`rtol=1e-3`，solver/total S_H MatMult 为8/9（上限9/10），`budget_exhausted=false`；显式 final relative residual `0.005653709235402098`，高于 `0.001`，`raw_residual_pass=false`。RHS norm `0.6301627488283656`、residual norm `0.0035627569528573033`；本次 solve 的 owner-authoritative LU attempts/successes 为9/9，累计为17/17；累计solver/total S_H MatMult为15/17（owner广播计数不跨rank求和）。这不是9+1预算耗尽，也不把负 KSP reason 或超限残差改写为近似通过。失败 RHS 与 iterate 未持久化 |
| side BAL_H 采样边界 | `balh_side_rhs_audits.jsonl` 有6项且phase均为`outer`：bottom/top各有index 0、1、2的writer-local记录；不把index硬配到精确outer iteration。1项bottom zero-RHS exact，另5项是`SideBalancedInverse`的`INNER_APPROXIMATE_RETURN`，各128/128步、KSP reason `-3`、`rtol=0.01`，真残差比为`0.0855020803 / 0.0231547806 / 0.1098160505 / 0.2534099108 / 0.2344232103`。这些outer side记录不同于失败的8步fixed-H6 modal solve |
| 失败发生位置 | outer right-FGMRES 的 PC 调用 `action_modal_schur_system.solve`；iteration 1 进度行记录了第一次 modal solve。之后第二次 fixed-H6 solve 抛出未收敛异常，发生在后续 outer PC 调用中；第二次调用对应的精确 outer KSP iteration 号未持久化。consumer 的 `failure_stage=top_construction_cleanup` 是 cleanup callback 覆盖的最后 stage 标签，不是失败来源。失败后 markers 顺序及 wall：bottom factor release `9678.965858784` → bottom cleanup `9679.078221075` → top release `9679.167618054` → top cleanup `9679.280467793` → all-setup cleanup `9680.569793493` → final cleanup `9680.610679717 s`；两侧 factor destroy error 均为0 |
| 运行区间与计费 | consumer compute wall `9,683.143932356033 s`；按 marker 切出的互不重叠区间：outer solve 开始前 `4,036.736691580154 s`，outer solve marker 至首次 teardown release `5,642.229167203885 s`，release 至 final cleanup marker `1.644820932997 s`。这是 marker 派生窗口，不是隔离的纯 CPU phase timer。唯一 service finalizer wall `9,685.695409207 s`；不再把 nested phase wall相加 |
| 分类与完整性 | consumer `IMPLEMENTATION_FAILURE`；public `task041_public_command_nonzero`/rc3；finalizer `failed/service_boundary_failure`，8/10，仅 `public_result_completed` 与 `service_terminal_normal` 为false；`controlled_stop.active=false`，清理检查通过。V5 ledger 为193项，SHA `803c4cb9c05b0c25426af3d75f6e20d9940bf08c351ed22a911f584e62e0b6ae`，runroot 唯一匹配 index192；ledger 行不直接保存 Invocation，由 runroot/launch/finalizer 绑定。recovery、最终五残差、E/H/RTA、A_volume、衍射和 physics 未到达 |

原始证据未改。主要 SHA：consumer summary `9c1d8011185f4235c6c2cc3259836f4f6520dd587c66ddf935aedcb8565ed6b7`；consumer markers `59cd40df259ccb47894a7249fb128f9c463983b416da3230fb01178a8648e280`；side RHS audits `2cbb802d9f85ea6f1605f8bb4ad264320f00430511e15b30575b343785c8c71d`；service summary `ef4bd70cc192d6b872bf4395fc3643578f914002b89c2172ca5ef4711796bd42`；finalizer summary `ed254817e55317f2feba3fbf5d0fc1488217cbdf800ee292dc37ef55d1d17c94`；rank NUMA evidence `5a490d8d98a21e845757e4b270e6042ff54aab41ec54fd757556fa91a90e50fe`；rank affinity `f46b6adb182e84549af66200518edc7b15b1210363b3929d8c3ebe7f7ac44a48`；ledger如上。compact证据路径为repo-root下`results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/terminal_compact_v11.json`，SHA `1435894639ffebc3979147ded7054283f54357179e49dc2531e6852b322fa469`。

### 唯一 fixed physical BAL_H 备选：只读接线评估

通俗地说，当前 fixed-H6 在每个模态反馈中只用固定的 H6 近似；Review V9 §2.2 允许的一个备选，是再用现有准确 P4 逆 `Q` 做一次固定平衡修正，并在前后继续应用原物理 `A6`。候选式为 `J[Q + (I-QA6)H6(I-A6Q)]J^H`。这只更换 fixed-H6 模态预条件器中的侧作用，不改全局 `A/f`、外层 right-FGMRES、P4 物理/增广残差门或最终物理门；它尚未实现或运行，也不保证收敛更快。

现成 `src/solvers/physical_balanced_coupling.py::PhysicalBalancedCoupling.apply` 已执行全空间 Q/A6/H6/Q 的该代数次序，并做 PH 平衡审计；`SideBalancedInverse` 已持有可借用的 P4 factor、A6、H6 和 owner transfer，对应回调为 `_apply_q_callback_impl`、`_apply_a6_callback`、`_apply_h6_callback`、`_apply_ph_callback`。最小接线是在 `src/solvers/physical_balanced_side_inverse.py` 加一个有界 fixed-Q side action，并给现有 Q 回调增加不改实例状态的 per-call 固定修正入口；该入口对同一 P4 factor 传 `diagnostic_correction_steps=1`、不传动态 target，不改 `configure_diagnostic_p4_corrections` 保存的普通 `5e-13/max2` 状态，也不重建 factor。然后在 `src/solvers/hybrid_fem_modal_block_ldu.py` 让现 modal S_H 接受该 action 协议并保留 FixedH6 默认分支，再由 `benchmarks/task041_exact_side_workflow.py` 只给注册 W0.7 增加一个显式策略选择。当前 `_FixedH6ModalKrylovSystem` 对 side action 做 `isinstance(FixedH6ActiveTraceAction)` 检查，这个边界需定向扩展，不能绕开输入/布局预检。

P4 精化必须隔离：当前普通 `SideBalancedInverse` 的 `refinement_target_tolerance=5e-13` 最多两次同因子修正，是按 RHS 残差目标决定何时停止；这种自适应操作不能直接放进每次 modal MatMult。fixed action 每次 Q 应对同一个 P4 factor显式请求恰好1次修正（`diagnostic_correction_steps=1`、不传动态 target），保留原A4物理与增广残差 `<=1e-10` 检查及固定作用的重复/线性门；若一次修正后原门未过，立即拒绝该候选，不改用更多修正或降门。普通 side inverse 仍保持 `5e-13/max2`，不可调用 `configure_diagnostic_p4_corrections` 去改它的共享可变状态，也不可把 `SideBalancedInverse.solve/apply` 自适应 FGMRES 塞进 MatMult。outer modal `rtol=1e-3`与8步/9+1作用预算不提高。

成本边界：一次 side BAL_H action 含2个 Q、2个 A6、1个 H6，并含既有 PH 平衡检查；每个 Q 的“初解+固定一次修正”最多2次 P4 backsolve，所以每侧每次 S_H MatMult最多4次 backsolve。两侧一次 S_H MatMult合计最多8次 P4 backsolve、4次 A6、2次H6，另有P/PH transfer与平衡审计。现有8次 repeat/linearity setup gate若执行新 action，最多64次 P4 backsolve；一个 inner solve 的9次 solver MatMult加1次final-check上限对应最多80次。它们是按源码公式推导的上限，不是本次已测成本；本次 fixed-H6 action 未执行这些 P4 backsolve。

必要验证应复用 `test_345_task041_balh_coupling.py` 的复数代数、重复输入与清理，`test_349_task041_balh_side_inverse.py` 的 P4固定修正/target互斥及原A4残差，`test_350_task041_balh_block_ldu.py` 的 modal action/预算/failure propagation与外层真门；若加策略选择，再给 test351 增一个严格限 W0.7 的路由合同。必须新增一条对真正 fixed-Q side action 的复杂向量重复/线性门和原 P4 物理/增广残差检查；这些当前测试尚未覆盖。此处只是只读方案，没有代码改动、测试、factor重建、QEP或第二次dispatch。

## P0：独立 W0.7 资源合同

P0 给注册的缩减 W0.7 case 独立配置 80 GiB 上限，避免为了 pilot 放宽共享常量而影响 W5、13.5 nm 或 W2。384 GiB node0 floor 仍独立生效；case cap 是运行限制，不是峰值预测。运行前只有当 host/node0、cgroup 与 case 限制均满足时才允许继续。

| 项目 | 结果与边界 |
|---|---|
| 变更 | 只修改 pilot DAT、`src/io/input_validation.py`、`benchmarks/task041_exact_side_workflow.py`、`src/test/test_351_task041_balh_public_workflow.py`；新增 pilot 独立资源合同，未改变共享 W5/13.5/W2 常量、未加 CLI 或 runner 框架 |
| 资源合同 | hard cap `85,899,345,920 B`；warning `77,309,411,328 B`；政策余量 W `8,589,934,592 B`；node0 floor `412,316,860,416 B`。swap 按 V8 仅观察；不设 elapsed 强停 |
| 提交 | `a3332dc12de1ddfec824a8b64ab5dcc23f68261b`，parent `cd43819dc91112b8ca49d1dd2c2066d0074eda44`，原分支已同步 upstream；protected stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 未动 |
| P0 测试范围 | 7 个批准 selector 的参数化合同共 12 个唯一 case，分三个 pytest attempt 完成；这些是注册/路由/预算/兼容性合同，不运行 QEP、FE 或 consumer numerical solve |

| pytest attempt | 源码边界、结果、唯一父 wall | 原始证据 |
|---|---|---|
| `task041_v11_p0_resource_contract_serial_20261009T072725Z` | 初始 test351 SHA `ef84f11829906c9e5dd73de70cb9a5f8dcdac7ad22a8702174301ab07cf2c6e8`；实际执行 2 项，1 passed、1 fixture assertion failed；parent wall `4.291536791017279 s`。失败为预算 fixture 读取不存在的 `cap_headroom_bytes` 键；保留原失败 | `results/task041_v11_p0_resource_contract_serial_20261009T072725Z/serial/pytest.stdout.log`，SHA `e7857bb4712a8acc1c7d11697a548320b628fa93e48ffd08b799eab50c47e83c` |
| `task041_v11_p0_stage_budget_retry_20261009T073055Z` | 修正后 test351 SHA `dbd840cc89427483dacca71412d1d80a63b81d2a02ab5204171bbcee9770e116`；受影响预算节点 1 passed；parent wall `3.2227331469766796 s` | `results/task041_v11_p0_stage_budget_retry_20261009T073055Z/serial/pytest.stdout.log`，SHA `cf686c05bfe0139c25a206ee55ec21e7cde334ccb5bbab67376ece2414185475` |
| `task041_v11_p0_serial_remaining_20261009T073150Z` | 同一 test351 SHA；余下 selector 参数化后 10 passed；parent wall `8.533090129029006 s` | `results/task041_v11_p0_serial_remaining_20261009T073150Z/serial/pytest.stdout.log`，SHA `c30d645302cb5ef96b0e8966a6f2c0f00258fdb8da6ff6f17443d22016133651` |

三个父 wall 合计 `16.047360067022964 s`，逐 attempt 唯一计入 V5，不重复计算失败后重试；ledger 为 192 项，SHA `710b71f59d0109ace55963b2ac909eca5e4fccdcb8ef237259f9abff679ef774`。12 个唯一参数 case 跨三次 attempt 通过；不能表述成最终 test351 SHA 在一次完整组运行中通过。延迟 `complete_numeric` 异常的 failure-classification 传播仍为 `not_covered`，本轮没有扩展分类框架。

## P1：W0.7 PORD 启动前封存包与准入记录（历史快照）

以下保留实际 dispatch 前的准备包、ABI 和宿主证据，供解释启动身份；它们不是当前“未启动”状态。

当前目标仍是已注册的缩减 W0.7 pilot：W 材料，10×5 nm，p6/h0.70、M400、MPI8，Hybrid 接口 2/22 nm，matched 全长 L20/N29/h20/29，fixed-H6。P4 target 为 `5e-13`，每个同因子最多两次修正；原方程、八次 fixed-H6 setup 作用、GMRES 9+1、五项真实残差和物理门均保留。route-plan、leading-PH 与其他研究诊断关闭。

| 包/身份 | 已核事实 |
|---|---|
| 当前源码 | HEAD `a3332dc12de1ddfec824a8b64ab5dcc23f68261b`；source binding 含 34 runtime + 5 test 共 39 条，已逐条比对 HEAD blob OID、Git blob bytes 与工作树 SHA |
| 准备包 | `results/task041_v11_w0p7_pilot80gib_pord_warm_preparation_20261009T074322Z/`；runroot `results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/`；unit `task041-v11-w0p7-pilot80gib-pord-warm-cpu10-11-14-15-16-17-18-19-20261009T074322Z.service` |
| pre-docs准备包config/argv（历史） | config SHA `b4bf3edc0c7acfca3aa7b1d00c6b2f8a69c19f2caa220e44c05460ef83c22385`；systemd argv SHA `363dbb74f6e23f46665c900dd0e31b4d4fcab48048fe764e5e28b47e30f42236`；post-ABI admission receipt SHA `76be97971219ab03155fe63deb0ba14fe918c55f66c7c8fd42bc3108fbd2bdc9`；包manifest有26个内容文件，checksum通过。实际启动使用上方post-docs绑定 |
| rank map / ABI | 排序 map `[10,11,14,15,16,17,18,19]`。fresh MPI8 ABI rc0，parent wall `1.8218492951709777 s`；8 ranks 精确按此 map、node0 membind、complex128、Int32、六线程变量全为1，并从指定路径加载 SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` 的原生桥 |
| producer | 复用 source `2708214386d38bd69f73e6b196c8ed843bb53d81` 的 validated producer-root；manifest SHA `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`，packet identity SHA `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`。11 个小封套文件哈希/字节数匹配；没有重求 QEP、预读 shards 或在准备阶段运行完整 validator。实际 public consumer 仍按原链执行封套验证及 packet reader/hydration |
| 启动前状态（历史） | 当时 unit 未加载，runroot/service logs/dispatch marker 不存在；随后按审核过的 sealed argv 启动一次，终态及唯一 Invocation 见本文 P1 终态表 |

post-ABI 两点真实 host 样本为 `2026-10-09T07:54:18.523917Z` 和 `07:54:23.603283Z`。同 user-manager 查询显示目标 unit 未加载、active Task041 units 为空。宿主进程视图看到了其他任务：Task039 在 CPU24，Task042 在 CPU26 及 CPU6；它们没有固定绑定到候选 map，本轮未干预。Task042 有宽 affinity，故仍保留 `performance_not_isolated=true`，不宣称核完全隔离。node0 MemFree `719,097,163,776 B`，扣 floor 后 `306,780,303,360 B`，再扣 80 GiB case cap 后余 `220,880,957,440 B`；node0 gate 通过。host MemAvailable `2,009,497,427,968 B`；user.slice 与 user-1000.slice 的 memory.max/high 均为 `max`；磁盘可用 `3,148,500,914,176 B`。swap 仅记录观察，没有把它作为硬门。

PORD source-counted Δ（bottom `3,962,155,812 B`、top `5,500,664,516 B`）仅供 symbolic 筛查，须与对应阶段 fresh B 和 W 一起判定，不能解释为 RSS 上界。numeric 门使用当场 fresh B + 单份当前 INFOG(17)×1,000,000 + W。bottom 因子在 top 取样时仍计入 fresh B，不重复相加；两侧预算尚未在真实矩阵上评估。

准备快照之后没有重求 QEP；本次实际 consumer 完成 packet 读取、one-cell 与两侧 P4 因子，并到达 outer iteration 1，随后 fixed-H6 modal 内层未通过残差门。没有最终五项残差、recovery、R/T/A 或完整 physics，所以不能称 pilot 通过或登记 W0.7 数值资格。50×25 nm、2 TB 和 48 h 仍未资格化；W5 弱显著衍射通道按用户决定延期处理，保留原失败工件。运行期文档仍只走本次 launch manifest 的既有 allowlist。
