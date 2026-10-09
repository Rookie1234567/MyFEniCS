# Review V11 执行交付进度

## 2026-10-10：fixed-Q zero-count 事故收口

Invocation `3cc1884481474e5ba390e757eeb482c0`（source `f4718519d8a244eae9ea87148422ade14771e534`）复用既有producer、QEP=0；bottom/top P4 numeric都完成。随后 fixed physical BAL_H modal sample 固定Q门报 `backsolves=0`，而当前动作要求一次同因子数学修正；consumer为`IMPLEMENTATION_FAILURE`，public rc1、service exit3，finalizer `failed/service_boundary_failure`、9/11，false为`public_result_completed`和`service_terminal_normal`，`controlled_stop.active=false`。raw `failure_stage=top_construction_cleanup`保持原值；它不改变marker显示的modal sample失败位置。

原始失败Q的RHS/PH输出及逐调用exact-zero证据没有持久化，因此不能把0次backsolve解释为全局零、PH零或精确零修正中的任一种。全局零路径仍是source-derived。数学修正次数（每个Q一次）和因子实际LU次数分开记；仅逐调用exact direct-zero证据允许0次LU，容差内残差不够。原A4残差、精度、普通side target和全部外层数值门未改变。

服务finalizer wall `1771.020854749 s`在V5按runroot唯一计一次；ledger 211项，SHA `00b34a553294f5b230c0572b174cc4af09ec7c0186f8422af4a85a4854cf0e15`。pytest四attempt分别为：初次fixture缺FixedH6失败（3.251639037858695 s）；修正后serial 4 passed/1 MPI2-only skip（3.2557253290433437 s）；其余serial 4 passed（2.134472551057115 s）；MPI2两rank各6 passed（2.1931387439835817 s）。总pytest父wall `10.834975661942735 s`，ledger各attempt仅追加一次；分批结果不是单次整组通过。tiny真实P4 inverse与MPI2测试只核组件分支/残差合同，不资格化production pilot。终态compact：`results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261009T160948.696125Z/terminal_compact_fixed_q_zero_audit_v11.json`，SHA `914696b024ac26b03aa3e818f238b9ca7d033ad7898e326d6206b2630f73ee79`。原raw与账本不改；W5继续按用户决定延期，W2不阻0.7主线。

## 后续事故更正：候选方法 binding 在 P4 前拒绝（Invocation 72f92a0c）

下方 outer iteration 1 的残差失败属于先前 Invocation 797ae38854d546898a895c81d803a5ec。之后的 Invocation 72f92a0cae6f4066a455bea0dba8561c 是独立事故：_run_task041_balh_candidate_setup 没把显式 modal_feedback_method=fixed_physical_balh_once 传给固定-H6 binding 重建；注册 scope 因实际 candidate method 为 null 而在 factor_setup 拒绝，P4 side construction 前退出。这不是 BAL_H 残差或资源失败。

| 当前事故 | 实际结果 |
|---|---|
| 原始分类 | consumer IMPLEMENTATION_FAILURE/TASK041_CONSUMER_STAGE_FAILURE，public rc3 task041_public_command_nonzero，finalizer failed/service_boundary_failure；finalizer 11 checks 中9 true、2 false（public_result_completed、service_terminal_normal），controlled_stop.active=false。sealed request匹配检查为true；actual method未建立，supervisor actual-null是上游拒绝的结果 |
| 本场未到达 | QEP=0，one-cell完成并清理；bottom/top P4 inventory为空，P4 numeric、outer及physics/RTA均 not_run |
| 资源 | process-tree authority峰 33,847,504,896 B，job cgroup历史峰 31,681,507,328 B，job swap 0；低于80 GiB cap，本次非资源停止 |
| 服务账目 | 唯一finalizer service wall 1410.90943187 s；public与parent wall为嵌套值，不相加；既有service ledger行未重复收费 |
| 最小回归 | 一个test351 selector在真实candidate helper/binder/expected-binding边界通过，P4构造前截停。最终生产/test SHA为06f59398...10262 / c169028e...41f09；首次BLIS预启动未启动pytest，retry1为fixture spy位置参数错误，retry2 1 passed。两实际pytest墙钟合计 10.756424868945032 s，V5由204增至206，SHA e1da804cd152958875b965fc94efaf22823c40dd8f60bfa79f40a820868bd21c |

当前事故raw与compact见repo-root results/task041_v11_w0p7_fixed_physical_balh_once_warm_run_20261009T142126Z/，compact SHA b3444f82a70ff2f840b208f87f67f1c1316d6ef71cf8cd1c97c6446da29e533a。本阶段的单行生产修复已提交；本回归不是FE重跑，尚不能说明固定物理BAL_H实际方法或场已通过。


**前一次数值场（Invocation 797ae38854d546898a895c81d803a5ec）。** 该场到达 outer iteration 1，随后 fixed-H6 modal 内层第二次 solve 未通过显式残差门；没有完整场、恢复、最终物理量或数值资格。资源峰低于80 GiB cap，本场不是资源停止。W5弱显著衍射通道按用户决定延期处理，保留原失败工件、不写PASS、不作W0.7前置；W2本阶段未推进。

| 前一次数值场终态 | 实际结果与边界 |
|---|---|
| Invocation / 模型 | `797ae38854d546898a895c81d803a5ec`；W0.7 reduced，10×5 nm、p6/h0.70、M400/MPI8、接口2/22 nm、matched L20/N29/h20/29；复用 producer，QEP=0 |
| 实际启动绑定 | post-docs config SHA `9798da6cf29498ab20975e306674c95d80ac62b8abc636bf9ea76b97bb201291`，systemd argv SHA `0cbd2c1f6a72608c5bc418ceef324a70f42eaa645ece072e1a49b5894415cc80`；launch manifest指向post-docs封存config。下方`b4bf…/363dbb…`只是更早pre-docs准备快照 |
| 实际启动绑定 | post-docs config SHA `9798da6cf29498ab20975e306674c95d80ac62b8abc636bf9ea76b97bb201291`，systemd argv SHA `0cbd2c1f6a72608c5bc418ceef324a70f42eaa645ece072e1a49b5894415cc80`；launch manifest指向post-docs封存config。下方`b4bf…/363dbb…`只是更早pre-docs准备快照 |
| 数值进度 | one-cell、bottom/top P4 numeric 与 fixed-H6 setup repeat/linearity gate 完成；outer iteration 1 有 `ITERATING` 进度。第二次 fixed-H6 modal solve 得 KSP reason `-3`、8/8 iterations，显式相对残差 `0.005653709235402098` 高于 `rtol=0.001`；solver/total S_H MatMult 8/9，`budget_exhausted=false`。不是 9+1 预算耗尽 |
| 失败位置 | 在 outer right-FGMRES 的 modal Schur PC 后续调用中。`failure_stage=top_construction_cleanup` 是 cleanup 覆盖的末态标签，不是失败源；bottom/top factor release 和 cleanup markers 均在异常之后，destroy error 为0 |
| 资源 | case cap/warning/W=`85,899,345,920 / 77,309,411,328 / 8,589,934,592 B`，node0 MemFree reserve/floor=`412,316,860,416 B`，host MemAvailable独立检查。service summary process-tree peak=`47,073,288,192 B`，consumer resource summary process-tree peak=`47,027,847,168 B`，dedicated job cgroup peak=`44,504,326,144 B`；这些独立采样口径不相加，均低于cap。未发生预算拒绝、OOM或受控停止 |
| 终态与计费 | consumer `IMPLEMENTATION_FAILURE`、public rc3、finalizer `failed/service_boundary_failure`，8/10、`controlled_stop.active=false`；唯一 service wall `9,685.695409207 s`，V5 193项，SHA `803c4cb9c05b0c25426af3d75f6e20d9940bf08c351ed22a911f584e62e0b6ae`。没有 recovery、最终五残差、E/H/RTA、A_volume、衍射或 physics |

失败 solve 的 RHS 与 iterate 未持久化。`balh_side_rhs_audits.jsonl`的6条记录phase均为`outer`，是writer-local side记录；128/128步`INNER_APPROXIMATE_RETURN`与这次8步fixed-H6 modal solve分开，不把记录index映射为精确outer iteration。详见[Response V13](../response_v13.md)及repo-root ignored证据`results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/terminal_compact_v11.json`。

## 启动前准备快照（已由上方本轮终态更新）

| 项目 | 当前身份/结果 | 证据与边界 |
|---|---|---|
| P0 tracked 范围 | DAT、input validation、exact-side service contract、test351 四路径；commit `a3332dc12de1ddfec824a8b64ab5dcc23f68261b` / parent `cd43819dc91112b8ca49d1dd2c2066d0074eda44`，原分支与 upstream 同步，worktree 在起草本文件前 clean | protected stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 未 apply/drop |
| P0 测试 | 12 个唯一参数 case 跨三个 parent pytest attempt 通过；一个 fixture-only 首次失败保留，受影响节点单独重试后通过；父 wall 合计 `16.047360067022964 s`，V5 ledger 192 项 SHA `710b71f59d0109ace55963b2ac909eca5e4fccdcb8ef237259f9abff679ef774` | 分 attempt、test351 SHA 与 raw stdout SHA 见[Response V13](../response_v13.md)及[test summary](test_summary.md)；不是最终 SHA 单轮 12 passed |
| 资源合同 | hard `85,899,345,920 B`；warning `77,309,411,328 B`；W `8,589,934,592 B`；node0 MemFree reserve/floor `412,316,860,416 B` | cap是运行限制，不是预测峰值；host MemAvailable独立核验，父级更严的实际cgroup/node0可用量仍会拒绝 |
| pre-docs pilot包快照 | runroot `results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z`；unit `task041-v11-w0p7-pilot80gib-pord-warm-cpu10-11-14-15-16-17-18-19-20261009T074322Z.service`；CPU `[10,11,14,15,16,17,18,19]` | config SHA `b4bf3edc0c7acfca3aa7b1d00c6b2f8a69c19f2caa220e44c05460ef83c22385`；argv SHA `363dbb74f6e23f46665c900dd0e31b4d4fcab48048fe764e5e28b47e30f42236`；该binding后被post-docs版本取代 |
| fresh host / ABI | post-ABI 双样本 node0 floor/cap、manager、root、CPU 核查通过；MPI8 native ABI rc0，所有 rank map 与指定 .so 一致 | post-ABI host raw SHA `daafd23ba0df3146a7f06330ddba561913dde62cef969cae3a0e63dab479737a`；receipt SHA `76be97971219ab03155fe63deb0ba14fe918c55f66c7c8fd42bc3108fbd2bdc9`；桥 SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` |
| 算值与限制 | 当前 QEP 计划0；复用既有 producer 小封套；source binding 34 runtime + 5 tests；packet 11个轻量封套哈希重核通过 | 未读全 shards、未跑完整 packet validator、QEP、factor、FE 或 dispatch；PORD Δ仍是源码筛查量，不是 RSS 上界 |

post-ABI host raw 的两次采样为 `07:54:18.523917Z`、`07:54:23.603283Z`。候选 map 上未见固定数值邻任务；Task039 固定 CPU24、Task042 观测在 CPU26/6，未干预它们。Task042 宽 affinity 使 `performance_not_isolated` 继续成立。node0 MemFree 扣 floor 后 `306,780,303,360 B`，再扣 80 GiB cap 后余 `220,880,957,440 B`；host/cgroup/disk 与目标 unit 事实见 hash-bound post-ABI 收据。此段只记录 dispatch 前的准备状态，实际运行及终态见上表。

W5 的弱显著衍射通道按用户决定延期处理，保留既有失败/比较工件，不写 PASS，不作为 0.7 前置。W2 本阶段未推进，避免延误 0.7 主线。MPI8 ABI 和资源门只说明运行环境/资源准入；不等同 FE、数值或模型资格通过。
# 2026-10-09 后续：fixed physical BAL_H 候选包已准入，等待最后启动裁定

在原先V11 W0.7 warm consumer终态之后，已提交一条严格显式选择的 fixed physical BAL_H feedback 路径，并准备好一个独立 warm package。该动作把固定的一次P4修正用于modal反馈；它与普通动态P4目标路径区分，且不会自动更改纯fixed-H6默认路由。本阶段只验证source/配置/原生MPI身份与宿主门，方法本身尚未进入consumer。

| 项目 | 结果 |
|---|---|
| 代码 | `fcae36494e65751ed918a8b591f4639d27b493c0`，parent `92914c5759281da51d7312040c30768ca0a00e07`，upstream `0/0`；只含已审11路径 |
| 显式方法链 | config 与 public argv 同时请求 `fixed_physical_balh_once`；期望实际标签 `fixed_physical_balh_once_modal_gmres_research`。config SHA `06524840f62964436e0ac736b8fc9904f103f139786eec46c55d51afeab63231`，argv SHA `b41a6e6d017620ccf56fce8528092a7c2dbb2e549ea6356f7100483509e02e31` |
| ignored包 / service目标 | [execution contract](../../../results/task041_v11_w0p7_fixed_physical_balh_once_warm_preparation_20261009T142126Z/execution_contract.json)；unit `task041-v11-w0p7-fixed-physical-balh-once-warm-cpu10-11-14-15-16-17-18-19-20261009T142126Z.service`；runroot `results/task041_v11_w0p7_fixed_physical_balh_once_warm_run_20261009T142126Z` |
| source与桥 | 39个HEAD/worktree源绑定（34 runtime + 5 test），source_bindings SHA `e2057884f3412674a18526b07c5caf77857db81eb416899968cf5561a3d19fe4`；复用已构建bridge SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` |
| 宿主门 | 两个真实宿主样本；unit未加载，无active Task041；root/log/dispatch marker不存在；CPU map `[10,11,14,15,16,17,18,19]`为socket0/node0独立核。node0扣384 GiB floor及80 GiB cap后余 `276,339,585,024 B`；host MemAvailable `2,139,694,497,792 B` |
| MPI8 ABI | rc0，父wall `1.9973516720347106 s`；8 rank精确映射上述tuple、membind0、complex128/Int32、六线程1，精确加载上述bridge；stdout SHA `e723181be00270fadf619e8f3903a05260495bfd9735ca44e6544ac34ab07099` |
| post-ABI核对 | receipt SHA `669e1cee445e1b94d99c30311d41c6afedb03f70ca0b922b2de662ed5f20aff7`；同manager unit和所有输出root仍不存在、39项源码/config/argv/bridge身份不变 |
| 数值边界 | producer沿用旧合格小封套，QEP=0；尚未在此包运行完整validator/shard hydration、PORD数值factor、fixed physical方法、FE、physics或finalizer。当前无Invocation，需主控对精确argv作最终一次dispatch裁定 |

资源合同仍为hard/warning/W=`85,899,345,920 / 77,309,411,328 / 8,589,934,592 B`，node0 floor `412,316,860,416 B`；V8 swap仅观察，无elapsed强停。PORD、matched L20/N29、P4 `5e-13/max2`、固定Q一次修正与 `1e-10` 门、八次SH setup、9+1 inner、outer五门和完整恢复物理合同不变。该包不构成内存容量预测或数值资格。

前一唯一W0.7场的 `IMPLEMENTATION_FAILURE` 和未完成physics分类继续保留。W5弱显著衍射通道按用户决定延期处理，不写PASS、不作为本pilot前置；W2不延误W0.7主线。合约测试的分批attempt与SHA见[test summary](test_summary.md)；未把任何分批通过说成最终源码一次整组通过。
