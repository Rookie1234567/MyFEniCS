# Task041 Response V8：D3a 2nm D1e 终态与 producer packet 边界

本报告只记录已自然触发 repeat Gate 终止的旧 D1e 及 producer metadata 复用核验，为 Review V5 R0 提供已有终态证据；不是 V5 整轮完成回应。R1–R6 均 `not_run`；实际分类保留 `IMPLEMENTATION_FAILURE`，不记人工受控停止。

## 结论先行

这是钨（W）、2nm、p6/h1.5、M1200、MPI8×1 的单次 D1e 运行。Schur 是供外层迭代使用的模态耦合预条件矩阵；本次 consumer 在正式全场 Schur 之前，用两侧合成模态 Schur 的重复样本检查一致性。该重复一致性门失败，consumer 以 `IMPLEMENTATION_FAILURE` 结束；这不是 OOM、超时、外部 kill，也不是投影误差结论。

失败不能归因到 top 单侧：`build_hybrid_action_modal_schur` 先由 bottom+top 形成 `sampled_first`，再由 bottom+top 形成 `sampled_second`。因此准确分类是“**两侧合成模态 Schur 样本重复一致性失败，侧别根因未定位**”；`top_construction_cleanup` 只是退出清理阶段 marker，不是 top 根因定位。

截至终态，producer 的 QEP packet 已保存，32 个 modal shard 保留；consumer 已完成 40 行小 RHS 记录（8 probe + 32 modal，bottom/top 各 16），但正式 Schur 为 `0/4800`，outer FGMRES 为 `not_started`/0 条 outer response，没有完整场、R/T/A 或 official qualification。`reason=2` 与 `true residual<=1e-2` 只说明这些小样本的内层求解达到原目标，不等于重复一致性或最终全局物理通过。

## 身份、终态与证据

| 项目 | 实际值 |
|---|---|
| canonical source / branch | `/home/fenics/Projects/MyFEniCS`；`codex/20260902-task41-mpi1-shortwave-hybrid-capacity`；运行 source `bde0686891af10bb489e4b1cb14500791cb50351` |
| report worktree | `/tmp/task041-d3b-terminal-review-20260920`，本报告不改变运行 checkout |
| report worktree HEAD | `83d84899c401df38dfe8ebc0ea1c56f0914887df`；running source 仍为 `bde0686891af10bb489e4b1cb14500791cb50351` |
| unit / invocation | `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` / `1cf5e34338754dbfa80df487b322c72c` |
| historical MainPID | `571560`；终态已退出 |
| runroot | [`20260918T095546.139183Z`](../../results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/) |
| service root | [`d1e_2nm_p6h1p5_m1200_mpi8_supervision`](../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_2nm_p6h1p5_m1200_mpi8_supervision/) |
| CPU / math threads | OS CPU1–8；MPI ranks 0–7；每 rank 数学线程 1；受保护 CPU23 项目未触碰 |
| report status | `terminal_controlled_negative`；D3a 文档阶段，不重启、不发 signal、不改源码 |

退出链为：producer wall `29504.116038094042 s`、rc0、进程组清理；consumer wall `135717.4772190291 s`、rc1、进程组清理；public total `165222.44361121487 s`。systemd 主进程于 `2026-09-20T07:49:30.066531Z`（CST `2026-09-20T15:49:30.066531+08:00`）以 `SERVICE_RESULT=exit-code`、`EXIT_STATUS=3` 退出；systemd 对代码3的展示别名是 `NOTIMPLEMENTED`，不是算法原因。控制进程于 `07:49:33.807150Z` 退出，failed record 为 `07:49:33.807349Z`。public `run_summary.exit_status=1` 与 service phase `returncode=3` 分别保留；finalizer charged wall 为 `165228.433265082 s`。

finalizer 的准确状态是 `status=failed`、`result=service_boundary_failure`：worker process group gone、post-hash、artifact hash、ledger 写入和专属树清理均为 true，但 `public_result_completed=false`、`service_terminal_normal=false`，不能称 finalizer PASS。原始 consumer 分类仍为 `IMPLEMENTATION_FAILURE`，不能改写为 OOM、resource stop 或 numerical projection failure。

证据入口与 hash 见 [`task041_d3a_terminal_20260920.json`](outcomes/records/task041_d3a_terminal_20260920.json)。主要终态摘要如下：

| 文件 | SHA256 |
|---|---|
| `run_summary.json` | `59ba533551d176feee6198308c3a8814e3ef2db8be051257c829e4ed11e3e0a6` |
| `consumer/consumer_summary.json` | `df2aff13add4a5cf8ddca9b720f0d980965165b9c25e9822607c258e0f9d8187` |
| `supervisor_summary.json` | `65edfd58060e49216b074bd59e27fe15b90a564288defcda50ac8abf400c1a6d` |
| service `summary.json` | `df4620f0fa8018e2a1d05645e1ea6b2c23d34647ee31adef218893863ca35f72` |
| `service_parent_summary.json` | `ee0dad15c23c18fe60c1814c82e66e33452ad534f40b1f887931d687a9c65c81` |
| finalizer summary | `d5ec69c414c93c52b748cdff12a96f9c824760135001bcf7bb44c4f4dbde95af` |
| 40-row RHS audit | `dd06b01eac2928ff0814bef9bd3951ac256d776366ed7fd177392374e0175cde` |

## 失败数值与样本范围

原始错误为：

```text
Early sampled modal repeat Gate failed: absolute=2.637750e-04,
reference_norm=5.957499e+00, relative=4.427612e-05,
max_column=1.169058e-04, finite=True, limit=1.000000e-10
```

上面数值按原 stdout 的 `.6e` 打印精度记录；更高精度原始值不可得，不能从显示值伪造 full precision。

其中 `max_column` 的字段语义是 `max_column_relative_error`，不是绝对差；触发位置为 `hybrid_fem_modal_block_ldu.py:542`，调用链经过 modal Schur 构造，退出阶段 marker 为 `top_construction_cleanup`。由于 first/second 两个合成样本都包含 bottom 与 top，不能从此记录选择失败侧。

| side | modal rows | iterations sum | elapsed sum (s) | true residual max | reason |
|---|---:|---:|---:|---:|---|
| bottom | 16 | 352 | `36004.124497986864` | `0.009981656767193032` | 全部 2 |
| top | 16 | 394 | `40527.54153031926` | `0.009939510152843832` | 全部 2 |

40 行由 8 probe + 32 modal 组成；bottom/top 各 16 modal 行。32 个 modal 行均为 `reason=2`，且 `explicit_true_target_reached=true`。因此小 RHS 内层 residual 门满足 `<=0.01`，但重复样本的 `relative=4.427612e-05` 大于 `1e-10`；这两个门不能互相替代。

正式进度仍是：formal Schur `0/4800`，outer FGMRES `not_started`、outer response `0`（分母不适用），full field/RTA `not_run`。没有把 32 个重复样本当成 4800 项正式进度，也没有把失败写成投影误差失败。

小样本总耗时是嵌套 modal row 成本，不是 service critical path。终态 32 条样本的固定算术为 `(36004.124497986864/16 + 40527.54153031926/16) × 2400 / 86400 = 132.86747574358702 days`；它不能给 ETA。D2a 旧 21 条样本的 `133.57896112787233 days` 只属于旧 bottom13/top8 窗口；旧 8-probe 的约 `115.17 days` 也单列，三者都不代表完整 consumer。`batch_size=32` 是逐批限制常驻内存，不是 32 个样本并行。

## 资源与终态边界

权威 service 全树 summary 的 `peak_process_tree_rss_bytes` 为 `642483171328 B`；较窄 public 树曾记录 `642449637376 B`，两者不可混称。专属 cgroup peak 为 `647904940032 B`；终态 cgroup 已清理，不把 D2a 的 cgroup current 快照写作当前值。PSS/USS 只有稀疏字段，不能替代 RSS。完整采样最大间隔为 `11.7317484519 s`，故短于采样间隔的局部峰不能称完整测得峰值。

global swap 基线为 `8192 B`，终态新增 used `290816 B`、`pswpout` 增加 71 页、`pswpin` 增加 0；job/cgroup swap 仍为 0。该变化需披露，但没有证据表明本 job 因 swap 触发停止，终止原因仍是 implementation failure。资源合同为 warning `1539316278886 B`、hard RSS `1759218604442 B`、runtime reserve `412316860416 B`；service summary 的 `minimum_host_memavailable_bytes=836790292480 B`，全树 sample_count 为 `407853`；PSS/USS 的完整 smaps 样本仅 `5480`，其余按稀疏未测处理。runtime reserve、identity 和清理证据按 service authority 保留；本次没有 RTA 或完整场可供后处理。

独立 2nm ledger 为 [`task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json`](../../results/task041_side_balh_component_audit/d1c_preparation_20260917_8d47747d/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json)，SHA `f01a0027b5303d7dae2ac0be542eb6273160c1ba150596907d55e09879cd2de9`。D1e 这一条 finalizer 只收费一次：before `77232.864925164 s`，charge `165228.433265082 s`，after `242461.29819024602 s`；旧 D1c/D1d records 保留，旧 V2 ledger 不改。

## Producer packet 与以后复用条件

producer 已写出 selected mode packet：32 个 shard、共 33 个文件、`4842723531 B`；manifest SHA 为 `7ef2ecc5587f79a123e44cacfe347356d13b36336948ade1672787c6430163d2`，此前已完成一次流式文件字节/SHA 核验。`mode_prep_summary` 为 `TASK041_MODE_PREP_PACKET_READY`，`producer_scope_released=true`，且 `qep_workspace_persisted=false`：保存的是 consumer 所需 selected packet，不是全部 QEP 中间 workspace。

终态后 `supervisor_summary.json` 已存在并有上表 SHA。随后一次只读 `validate_balh_producer_packet(..., require_public_supervisor_summary=True)` 返回 `rc=0/pass`、`producer_resource_qualified=true`，并核对原 2nm dat、完整 consumer source `bde0686891af10bb489e4b1cb14500791cb50351`、manifest 小文件和 packet 目录统计；结果日志为 [`d3a_producer_packet_validator_20260920.log`](../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_2nm_p6h1p5_m1200_mpi8_supervision/d3a_producer_packet_validator_20260920.log)，SHA `991a49001396b95ad7317148f56c3b05a815f2ff3963c995d6335768e29674b2`。`1.0323800740297884 s` 只是在已导入的同一 Python 进程内的 `load_and_resolve + validator` wall，imports/startup excluded；父侧完整 command wall `not_measured`。stderr 的 7 行 `Authorization required...` 原样保留，不是 validator 失败；本调用没有 fresh MPI8 ABI 或 32-shard hash 重验。这个结果只闭合 producer/public metadata qualification，不是 consumer-only restart 或全量 shard/ABI qualification。

未来启动沿用这次已通过的 metadata validator 入口；实际消费时仍需核对 32 shards、ABI、source/input/physical/resolved identity 与输入兼容性。内存中的 p4 factor、未完成 Schur 和 native workspace 没有 checkpoint，不能从 packet 继续恢复；受控结束也不等于任意强杀都可无条件续算。

已观察到的清理路径释放 owned packet/vector 引用，但未见删除 producer packet 的路径；因此 producer 证据应保留。新 consumer 若要复用，需在另一次明确授权的启动前以终态摘要和现有 validator 重新核验，不修改本次原始 run。

## 历史与后续边界

5nm BAL_H 曾有约 53 h 的组件/候选证据，但 public supervisor/resource 证据不完整，不能升级为完整容量资格；C2 common-layout 的约 26.6% 只属于同进程组件诊断边界，也不是本次 2nm 全场速度依据。D1c 的 `outer_mpi_identity` 失败、D1d 入口修复后的 affine geometry 误判、8ad30732 对平移浮点抵消的修复，以及 bde06868 绑定 D1e，均保留历史链条。

本次没有启动近似 Schur、没有重跑 QEP/PDE、没有改变 M、精度、物理定义、阈值或资源合同。没有完整场，所以没有“后处理拒绝 R/T/A”；RTA 的状态是 `not_run`。D3a 只整理终态证据，待主控审核后才可能推送文档；不修改 canonical 运行 HEAD。
