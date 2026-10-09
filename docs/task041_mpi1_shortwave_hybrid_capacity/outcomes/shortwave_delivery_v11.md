# Review V11 执行交付进度

**状态：P0/P1 本轮已执行并终态。** 唯一 W0.7 reduced warm consumer 到达 outer iteration 1，随后 fixed-H6 modal 内层第二次 solve 未通过显式残差门；没有完整场、恢复、最终物理量或数值资格。实际资源峰低于本 pilot 的 80 GiB cap，本次不是资源停止。W5 弱显著衍射通道按用户决定延期处理，保留原失败工件，不写 PASS、不作 W0.7 前置；W2 本阶段未推进。

| 本轮终态 | 实际结果与边界 |
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
