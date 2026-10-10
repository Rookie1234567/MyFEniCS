# Response V13：Review V11 的 P0/P1 执行与 W0.7 首场终态

本文件回应 Task041 Review V11 的当前执行批次。任务目录未提供单独 `README.md`；本轮依照仓库规则读取 `task.md`、Review V11、此前 Response V12、outcomes、仓库文档规则及开发总账。W5 的弱显著衍射通道按用户决定延期处理；保留其原失败与比较工件，不写成通过，也不作为本轮 W0.7 的前置。W2 本批未推进，避免延误 W0.7 主线。

## 2026-10-10：W0.7 fixed physical BAL_H warm retry 终态（Invocation `45a94a21808643a0b446c357c39fa48c`）

这次运行复用了已合格的 producer packet，当前 Invocation 的 QEP=0。模型为缩减 pilot：0.7 nm、10×5 nm、p6/h0.70、M400、MPI8，接口2/22 nm、matched L20/N29/h20/29；请求方法为 `fixed_physical_balh_once`，consumer 实际方法为 `fixed_physical_balh_once_modal_gmres_research`。通俗地说，两侧因子已经算好，但连接它们的模态子求解没有把残差压到要求，因此没有得到合格全场。两侧 P4 numeric 与 admission、固定物理 BAL_H 反馈的8次线性样本均通过。失败发生于该反馈方法的第一次 modal solve，因而没有完成 outer、最终场恢复或物理输出。

| 项目 | 实际证据 | 边界 |
|---|---|---|
| 身份 | source HEAD `598596b029ce9d952e3587837b3b217320909182`；unit `task041-v11-w0p7-fixed-physical-balh-once-warm-retry-cpu10-11-14-15-16-17-18-19-20261009T235026Z.service`；runroot `results/task041_v11_w0p7_fixed_physical_balh_once_warm_retry_run_20261009T235026Z/`；CPU map `[10,11,14,15,16,17,18,19]` | producer复用，QEP=0；不是cold QEP到cleanup运行 |
| 启动绑定 | config SHA `c832b0960e8c4c34a5d979b43857231b61049e45e30b9cbd4c4f27b15b8922e6`；systemd argv SHA `bde97bd427ea2291a010763b44cf42c2df39be38ea1b8930ebf7725f2b4a1d40`；launch manifest SHA `9cd83e85e117caf2f44963e1275ba5c8618a39810e93974729eb3871c0869eb4` | 固定method请求与实际method匹配 |
| 首次 modal solve | 固定物理 BAL_H 反馈实际只记录1次 solve、1次未收敛；GMRES达到 `max_it=8`，reason `-3`；`rhs_norm=0.09648882926540421`，显式 `residual_norm=0.0018492374693352754`，`relative_residual=0.01916530113811127 > rtol=0.001`；`raw_residual_pass=false` | 未触发独立 S_H MatMult 调用预算拒绝（8/9，上限9/10，`budget_exhausted=false`） |
| 抛错调用链 | `FixedH6ModalBlockLDUPreconditioner.apply` 形成modal RHS后调用 modal Schur solve；`_FixedH6ModalKrylovSystem.solve` 显式计算残差，reason `-3` 使状态为 `ksp_not_converged` 并抛错，relative residual也超过rtol。原始 `failure_stage=top_construction_cleanup` 保留，但它是清理阶段标签，不是本次数值抛错位置 | `outer_solve_progress` 仅记录 iteration 0 / `ITERATING`；失败发生在第一次外层PC应用内、固定物理 BAL_H 反馈的第一次modal solve，不能表述为outer收敛 |
| 另一项side RHS记录 | writer-local `phase=outer,index=0`：bottom为 `ZERO_RHS_EXACT`、零迭代；top为 `INNER_APPROXIMATE_RETURN`，128/128步，relative residual `0.08801306313790089`、`rtol=0.01`、未达显式目标 | 这是独立side RHS样本，不能替代或混同上面的8步modal solve，也不据此称P4失败或budget exhausted |
| 未保存字段 | 失败modal RHS及迭代向量均为 `not_persisted`；diagnostic output关闭，consumer只保存last-solve标量记录 | 不重建、不补算这些向量 |
| 终态 | consumer `IMPLEMENTATION_FAILURE`；public `task041_public_command_nonzero` / rc3；finalizer `failed/service_boundary_failure`，11项9 true/2 false，false仅 `public_result_completed`、`service_terminal_normal`；`controlled_stop.active=false` | 资源与cleanup门未触发失败分类；没有outer收敛、最终五残差、recovery或physics结果 |
| 资源 | process-tree RSS authority峰 `46,405,410,816 B`；此前运行采样cgroup峰 `43,663,454,208 B`；finalizer `post_io.result.cgroup_history_peak_bytes` 为 `43,664,695,296 B`（含finalizer/post-IO生命周期）；warning `77,309,411,328 B`、hard cap `85,899,345,920 B`；最低host MemAvailable `1,915,343,118,336 B` | 两个cgroup数值分别是运行阶段快照与含finalizer/post-IO的最终峰；最终峰低于warning/cap。本场不是资源拒绝或OOM。node0 MemFree floor与host MemAvailable是不同检查 |
| 唯一服务账目 | finalizer unit wall `3,697.345224675 s`（约1.027 h）；V5 212项、SHA `632d802cc33112da7cdd44e05ad3ff06438ea70f9ba05d5639766a0a5600a2c5`，该runroot唯一命中第211行（0-based） | `parent_wall=3,696.5190987 s`、nested public phase `3,696.3200797229074 s`，两者为嵌套区间，不另计费；该1.027 h是失败warm服务时长，不能外推为成功cold流程耗时 |

hash-bound [终态compact](../../results/task041_v11_w0p7_fixed_physical_balh_once_warm_retry_run_20261009T235026Z/terminal_compact_v1.json) SHA `f5eeefa92c9c32df5eb556d8f9574cad06a92bf2ac7993d707b9a310f8cc331e`；它绑定consumer summary SHA `e0198e64822a2260602e048ac0139db203f3f66f3452070bcb8a3c251deb5a35`、markers/side RHS audits、service parent/finalizer、memory stages、launch manifest、V5 ledger、config及argv原件。

**目标缺口。** 这次只运行10×5 nm reduced pilot，未达到Review V11的50×25 nm目标单胞；没有目标尺度的mesh/模态数资格序列，也没有2 TB目标的完整对象驻留与峰值证据。当前outer尚未收敛，最终五项残差、恢复、完整E/H、R/T/A、`A_volume`、全衍射及physics均未完成。48 h目标要求cold QEP至cleanup的完整一次生命周期；本场复用packet且QEP=0，所以失败warm的1.027 h不构成48 h资格。W5弱显著通道按用户决定延期处理并保留原负结果；W2不为绕过本modal阻塞启动。本任务未完成，不能据此登记W0.7完整数值资格。

## 2026-10-10：fixed-Q 精确零分支计数合同事故与定向测试

本场复用了既有合格 producer packet，QEP=0。bottom、top 两个 P4 因子均完成 numeric；随后 fixed physical BAL_H 的 modal sample 固定-Q计数门拒绝。raw异常为 `fixed physical BAL_H Q did not perform exactly one same-factor P4 correction: backsolves=0`。原始 `failure_stage=top_construction_cleanup` 字段照录；marker顺序显示 modal sample 在两侧 P4 numeric 完成后开始，因此该标签不改写成资源/清理失败，也不据它说top numeric失败。

| 项目 | 实际证据与边界 |
|---|---|
| 身份 | Invocation `3cc1884481474e5ba390e757eeb482c0`；source `f4718519d8a244eae9ea87148422ade14771e534`；unit `task041-v11-w0p7-fixed-physical-balh-once-warm-retry-cpu10-11-14-15-16-17-18-19-20261009T155100Z.service`；runroot `results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261009T160948.696125Z` |
| 终态 | consumer `IMPLEMENTATION_FAILURE`；public rc1；service exit3；finalizer `failed/service_boundary_failure`，11项中9项true、2项false（`public_result_completed`、`service_terminal_normal`）；`controlled_stop.active=false`。这不是资源停止。 |
| 数值阶段 | 两侧 P4 numeric均完成；事故版本的旧检查一律要求每个Q有两次实际回代，而本场raw报告0次backsolve，因此fixed-Q modal sample计数门拒绝。未进入 outer迭代、五项最终残差、recovery或完整E/H、R/T/A、A_volume、衍射及physics输出。 |
| 零值根因边界 | 当前raw未持久化失败Q的输入/RHS、PH输出/port RHS和逐调用exact-zero证据。故无法确认该0次backsolve来自全局exact-zero、PH为零还是修正RHS精确为零；“全局零”仍是source-derived情况，不是本场实测根因。小测试也不能回填这些缺失字段。 |
| 服务计费 | V5条目按runroot唯一匹配一次，service wall `1771.020854749 s`；ledger共211项，SHA `00b34a553294f5b230c0572b174cc4af09ec7c0186f8422af4a85a4854cf0e15`。账目行没有Invocation字段，Invocation由runroot/launch/finalizer绑定。未把嵌套public/consumer wall重复收费。 |

固定Q中的“数学修正次数”与P4因子实际solve次数是两个量：每次Q仍请求恰好一次同因子数学修正；只有该次调用有明确的exact direct-zero审计证据时，实际solve次数才可为0。接近零的残差不能代替exact-zero证据；非零分支必须按真实回代计数。原A4物理/增广残差、复数线性、输入不变、普通P4 `5e-13/max2`及既有modal/outer门均未放宽。

四个pytest父wall按独立attempt保留：首次serial因test fixture缺少FixedH6对象而在数学断言前失败（`3.251639037858695 s`）；修复fixture后受影响serial selector为4 passed、1个MPI2-only skip（`3.2557253290433437 s`）；剩余serial selectors为4 passed（`2.134472551057115 s`）；MPI2两rank各6 passed（父wall `2.1931387439835817 s`）。总父wall `10.834975661942735 s`，V5从207到211项，每个attempt各计一次；不能写成同一源码SHA的一次完整serial组通过。当前tiny `P4CellCondensedInverse` fixture覆盖direct-zero分支、计数不匹配拒绝、复数线性和原矩阵残差；MPI2覆盖本地empty-owner与全局零判断边界。这些是小矩阵组件合同，不是W0.7 production数值资格。

原始文件未改。派生终态记录为 [terminal compact](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261009T160948.696125Z/terminal_compact_fixed_q_zero_audit_v11.json)，SHA `914696b024ac26b03aa3e818f238b9ca7d033ad7898e326d6206b2630f73ee79`。其绑定的consumer summary SHA `6448de7ad2723792e3b36fa7df4ec9cd55d87d1c9d9e710dd52d31e5d4257325`、markers、run manifest及finalizer原件均保持不变。固定Q计数合同修复与定向serial/MPI2验证已完成；下一步提交并准备一次正式warm事故重试。本次仍未产生完整W0.7数值结果，任务继续。

## 2026-10-09 后续事故：candidate setup 漏传反馈方法 selector

这次 Invocation 72f92a0cae6f4066a455bea0dba8561c 与下节 797ae38854d546898a895c81d803a5ec 是两次不同运行。前一场确实进入 outer iteration 1，fixed-H6 modal 第二次 solve 的显式残差未过门；本次事故则在 P4 侧构造前因方法身份接线失败，没有运行 fixed physical BAL_H 数值动作，也不是资源停止。

| 项目 | 实际证据 |
|---|---|
| 身份 | unit task041-v11-w0p7-fixed-physical-balh-once-warm-cpu10-11-14-15-16-17-18-19-20261009T142126Z.service；runroot results/task041_v11_w0p7_fixed_physical_balh_once_warm_run_20261009T142126Z；runtime source HEAD 3cbee8de6917b71a606830eedbf100331339172d。config SHA e4030ebff434225d502b3099f27a30cef5bee19f2f2c15e2aaac5aa31003e882，systemd argv SHA 9cef9825a74dc52dc37fbb6505304af3ebca82e59e0ba5a3ec6de5ead174d4b5 |
| 根因与阶段 | config/public 命令及 consumer sealed summary 请求 fixed_physical_balh_once；但 _run_task041_balh_candidate_setup 重建 task041_fixed_h6_modal_gmres_binding 时漏传 modal_feedback_method。binder 因而按纯 fixed-H6 处理，并在 factor_setup 被注册 W0.7 scope 检查拒绝。consumer 记录的 requested binding 存在，但 candidate/solve actual method 为 null、未建立 |
| 终态 | consumer IMPLEMENTATION_FAILURE / TASK041_CONSUMER_STAGE_FAILURE，错误 Task041ModePrepError、stage factor_setup；public task041_public_command_nonzero、rc3；finalizer failed/service_boundary_failure。11项检查为9 true/2 false，false仅 public_result_completed、service_terminal_normal；modal_feedback_method_matches_request=true，controlled_stop.active=false。supervisor actual-null 是上游 binding 拒绝的结果，不另列为根因 |
| 数值与资源边界 | QEP=0；one-cell 原排序因子完成后清理；bottom/top P4 inventory均为空，P4 numeric、outer、physics/RTA均 not_run。process-tree authority峰 33,847,504,896 B、专属job cgroup历史峰 31,681,507,328 B、job swap峰0，均未触80 GiB hard cap；本次不是资源停止 |
| 唯一服务计费 | public phase 1410.2277620248497 s、parent 1410.392929981 s 是嵌套区间；finalizer service wall 1410.90943187 s 保留为原V5唯一服务账目，没有再次追加 |
| 定向回归 | selector test_task041_w0p7_interfaces_reach_frozen_setup_boundary 真实通过 _run_task041_balh_candidate_setup 与 binder/expected-binding 比较，并在 global operator/P4 build 前截停。最终生产文件 SHA 06f59398dda6df6d7ce20148bfbdafce3d4f9442c1b169e706cbd2cb37210262；test351 SHA c169028e662c8c7fa9c0f7bbf9dfa16bee10bcc1155159a48017bb1eca941f09。首个预启动因 BLIS_NUM_THREADS 未设置而未启动pytest；实际 retry1 因测试spy未接收位置参数失败（5.374333790037781 s）；修正测试spy后 retry2 1 passed（5.382091078907251 s）。两实际pytest父wall合计 10.756424868945032 s，V5仅追加这两项，ledger 206项、SHA e1da804cd152958875b965fc94efaf22823c40dd8f60bfa79f40a820868bd21c；服务1410.909秒未重复计费 |

事故与回归的hash-bound终态 compact：results/task041_v11_w0p7_fixed_physical_balh_once_warm_run_20261009T142126Z/terminal_compact_modal_feedback_candidate_helper_v11.json，SHA b3444f82a70ff2f840b208f87f67f1c1316d6ef71cf8cd1c97c6446da29e533a。本阶段的一行生产修复已提交；本回归不是修复后的正式FE重跑或数值资格。


## 历史 P1：前一 W0.7 reduced warm 场终态（Invocation 797ae388）

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
## 2026-10-09：fixed physical BAL_H method 的提交、准入与待启动包

本节记录 V11 后续的一条显式可选反馈路径。它在固定-H6 模态迭代中调用物理侧平衡动作，并对每次 Q 使用固定一次同因子修正；普通的纯 fixed-H6 路径仍是默认。固定修正避免把普通侧求解器按 RHS 残差决定的动态修正策略塞进每次 MatMult。该方法只改变本候选 consumer 的反馈动作选择，不改变输入、网格、QEP、P4 原始目标、外层求解器或物理方程。本次只是准备和环境准入，尚未执行该动作。

| 项目 | 本阶段实值 | 边界 |
|---|---|---|
| 代码提交 | `fcae36494e65751ed918a8b591f4639d27b493c0`，parent `92914c5759281da51d7312040c30768ca0a00e07`，原分支 upstream 同步 `0/0`；提交仅含11个获审代码/测试路径 | stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 未 apply/drop；提交后 source/test bytes 绑定到该 HEAD |
| 选择请求 | config 与 public argv 显式请求 `modal_feedback_method=fixed_physical_balh_once` / `--task041-modal-feedback-method fixed_physical_balh_once`；预期实际方法标签 `fixed_physical_balh_once_modal_gmres_research` | config 与 service argv 的public command逐项相同；请求方法未在 FE 中运行，当前只核其身份链 |
| 唯一准备包 | `results/task041_v11_w0p7_fixed_physical_balh_once_warm_preparation_20261009T142126Z/`；unit `task041-v11-w0p7-fixed-physical-balh-once-warm-cpu10-11-14-15-16-17-18-19-20261009T142126Z.service`；runroot `results/task041_v11_w0p7_fixed_physical_balh_once_warm_run_20261009T142126Z/` | 当前 unit 未加载；runroot、服务日志和dispatch marker不存在。等待主控对本包作最后启动裁定 |
| 配置与argv | config SHA `06524840f62964436e0ac736b8fc9904f103f139786eec46c55d51afeab63231`；systemd argv SHA `b41a6e6d017620ccf56fce8528092a7c2dbb2e549ea6356f7100483509e02e31` | argv必须作为封存JSON数组执行；本阶段未执行 |
| source和原生桥 | 34 runtime + 5 test 共39条逐项绑定commit HEAD blob与工作树；source_bindings SHA `e2057884f3412674a18526b07c5caf77857db81eb416899968cf5561a3d19fe4`。原生桥路径 `/home/fenics/Projects/MyFEniCS/results/task041_petsc_lu_stage_bridge_jobnull_retry_20261008T081704Z/lib/petsc_lu_stage_bridge.cpython-312-x86_64-linux-gnu.so`，SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` | 未重建桥；ABI加载的是上述精确路径和字节 |
| producer | 复用source `2708214386d38bd69f73e6b196c8ed843bb53d81` 的 `validated_producer_root`；manifest `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`，identity `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6` | 本次QEP计划0；准备阶段仅复核小封套，不读全shards、不提前运行完整validator。正式服务链仍将按原位置做封套检查和packet reader/hydration |

注册模型仍为 W 材料、10×5 nm、p6/h0.70、M400、MPI8、cell-condensed，Hybrid接口2/22 nm、matched L20/N29/h20/29。PORD两侧仍用已绑定source model v2；ICNTL14=40、ICNTL28=1、ICNTL7=4；one-cell原排序不变。P4普通target `5e-13`、最多两次同因子修正；新方法每次固定Q恰一次修正、动态target关闭，原物理与增广残差 `<=1e-10` 门保留。fixed-H6 setup八次、inner 9+1、outer五项残差与完整恢复/物理合同都未改。route-plan、leading-PH和其他诊断关闭。

| 准入项目 | 实测 | 口径 |
|---|---|---|
| fresh宿主双样本 | `2026-10-09T14:26:35.842375Z` 与 `14:26:40.921032Z`；raw SHA `8424b0d22e28e63b917b7808d1fe30003893517ba3ca0ccbeb43489168af18d3` | 两点均核验目标user-manager unit未加载、无活动Task041、runroot/log/dispatch marker缺席；CPU10,11,14,15,16,17,18,19均在线且属于socket0/node0不同物理核。未见固定数值邻任务；GNOME宽affinity和轻量Task042 helper被观察但未干预，保留 `performance_not_isolated=true` |
| 内存、cgroup与磁盘 | node0 MemFree `774,555,791,360 B`；扣384 GiB floor后 `362,238,930,944 B`；再扣80 GiB case cap后余 `276,339,585,024 B`。host MemAvailable `2,139,694,497,792 B`；磁盘可用 `3,129,317,482,496 B` | hard cap `85,899,345,920 B`、warning `77,309,411,328 B`、政策W `8,589,934,592 B`、node0 floor `412,316,860,416 B`；swap仅观察，不设elapsed强停。case cap是运行上限，不是峰值预测 |
| fresh MPI8 native ABI | rc0，父wall `1.9973516720347106 s`；rank0–7分别落CPU `[10,11,14,15,16,17,18,19]`，各rank精确单核affinity、membind0；native marker、词法venv、complex128、Int32、六线程变量全为1；OpenMPI4.1.6、PETSc3.19.6、MUMPS5.6.2 | stdout SHA `e723181be00270fadf619e8f3903a05260495bfd9735ca44e6544ac34ab07099`；attempt SHA `7e7894e6c22ee229628fa3861247e187dbb2f772534b98cca52103817fe02be5`；精确桥SHA如上。ABI不计FE wall/V5 |
| post-ABI身份 | raw SHA `0e0525eef02cc6bcbe1cb9806f28f649061975299b1a7990733f04a8aeef7180`；identity receipt SHA `669e1cee445e1b94d99c30311d41c6afedb03f70ca0b922b2de662ed5f20aff7` | 同user-manager复核unit仍未加载、无活动Task041，runroot/log/dispatch marker仍不存在；39条源码绑定、HEAD/config/argv/.so未漂移。post-ABI receipt是身份复核，不冒称第二次资源双样本 |

最终合约测试是分批完成：serial与MPI2均通过各自最后获准节点，但初始fixture错误、数值平衡fixture错配和监督记录断言错误等首失败均留档；详见[test summary](outcomes/test_summary.md)。V5账本包含203项、SHA `a4514aa3499fe1df305317b65de91039214b178dd288c3f9e90ac903278c3fa8`；此次阶段没有新增pytest wall。源文件在 `fcae364...` 提交后未改；当时的文档草稿尚未提交。

**当前边界：**上述准入和ABI只说明本包身份、宿主和MPI栈可用，不是RAM容量预测、producer全shard验证、QEP、FE、数值结果或模型资格。当前没有service Invocation，也没有dispatch。下一步只有主控批准后，才用本包封存argv启动一次。W5弱显著衍射通道按用户决定延期处理，旧失败保留且不作本pilot前置；W2不延误W0.7主线。
