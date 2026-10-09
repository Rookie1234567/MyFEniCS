# Review V11 执行交付进度

**状态：进行中；P0 完成并已推送，P1 准备与 post-ABI 门通过，等待主控唯一 dispatch 审核。** 本批实现一个只用于注册 W0.7 缩减 pilot 的 80 GiB 资源合同，不动 W5/13.5/W2 共用上限。W 是 cap 与 warning 的差额，作为预算政策余量；它不是峰值预测或误差上界。384 GiB node0 floor、V8 swap observe-only 和无 elapsed 强停保持。

| 项目 | 当前身份/结果 | 证据与边界 |
|---|---|---|
| P0 tracked 范围 | DAT、input validation、exact-side service contract、test351 四路径；commit `a3332dc12de1ddfec824a8b64ab5dcc23f68261b` / parent `cd43819dc91112b8ca49d1dd2c2066d0074eda44`，原分支与 upstream 同步，worktree 在起草本文件前 clean | protected stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 未 apply/drop |
| P0 测试 | 12 个唯一参数 case 跨三个 parent pytest attempt 通过；一个 fixture-only 首次失败保留，受影响节点单独重试后通过；父 wall 合计 `16.047360067022964 s`，V5 ledger 192 项 SHA `710b71f59d0109ace55963b2ac909eca5e4fccdcb8ef237259f9abff679ef774` | 分 attempt、test351 SHA 与 raw stdout SHA 见[Response V13](../response_v13.md)及[test summary](test_summary.md)；不是最终 SHA 单轮 12 passed |
| 资源合同 | hard `85,899,345,920 B`；warning `77,309,411,328 B`；W `8,589,934,592 B`；node0 floor `412,316,860,416 B` | cap 是运行限制，不是预测峰值；父级更严的实际 cgroup/node0 可用量仍会拒绝 |
| pilot 包 | runroot `results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z`；unit `task041-v11-w0p7-pilot80gib-pord-warm-cpu10-11-14-15-16-17-18-19-20261009T074322Z.service`；CPU `[10,11,14,15,16,17,18,19]` | config SHA `b4bf3edc0c7acfca3aa7b1d00c6b2f8a69c19f2caa220e44c05460ef83c22385`；argv SHA `363dbb74f6e23f46665c900dd0e31b4d4fcab48048fe764e5e28b47e30f42236` |
| fresh host / ABI | post-ABI 双样本 node0 floor/cap、manager、root、CPU 核查通过；MPI8 native ABI rc0，所有 rank map 与指定 .so 一致 | post-ABI host raw SHA `daafd23ba0df3146a7f06330ddba561913dde62cef969cae3a0e63dab479737a`；receipt SHA `76be97971219ab03155fe63deb0ba14fe918c55f66c7c8fd42bc3108fbd2bdc9`；桥 SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` |
| 算值与限制 | 当前 QEP 计划0；复用既有 producer 小封套；source binding 34 runtime + 5 tests；packet 11个轻量封套哈希重核通过 | 未读全 shards、未跑完整 packet validator、QEP、factor、FE 或 dispatch；PORD Δ仍是源码筛查量，不是 RSS 上界 |

post-ABI host raw 的两次采样为 `07:54:18.523917Z`、`07:54:23.603283Z`。候选 map 上未见固定数值邻任务；Task039 固定 CPU24、Task042 观测在 CPU26/6，未干预它们。Task042 宽 affinity 使 `performance_not_isolated` 继续成立。node0 MemFree 扣 floor 后 `306,780,303,360 B`，再扣 80 GiB cap 后余 `220,880,957,440 B`；host/cgroup/disk 与目标 unit 事实见 hash-bound post-ABI 收据。本文记录 P0 完成后的 P1 准备阶段；写作时尚未 dispatch，后续实际启动状态以终态记录更新。

W5 的弱显著衍射通道按用户决定延期处理，保留既有失败/比较工件，不写 PASS，不作为 0.7 前置。W2 本阶段未推进，避免延误 0.7 主线。下一步等待主控审阅已封存配置与 post-ABI 收据；不得把 ABI pass 解释成 FE、数值、资源峰值或模型资格通过。
