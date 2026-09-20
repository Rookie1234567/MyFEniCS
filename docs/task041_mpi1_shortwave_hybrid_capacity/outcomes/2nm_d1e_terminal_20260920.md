# Task041 2nm D1e 终态摘要（D3a）

## 结论

钨 W、2nm、p6/h1.5、M1200、MPI8×1 的 D1e 已结束。producer QEP 完成并保留 selected packet；consumer 在正式 Schur 前的**两侧合成** modal Schur 重复一致性检查失败，原始分类为 `IMPLEMENTATION_FAILURE`。不能把 `top_construction_cleanup` 解释成 top 侧根因：两次样本均由 bottom+top 合成，侧别未定位。

失败字段为 `relative=4.427612e-05 > 1e-10`、`max_column_relative_error=1.169058e-04`、`finite=true`；绝对差 `2.637750e-04`、reference norm `5.957499`。这些数值按原 stdout 的 `.6e` 打印精度记录，full precision unavailable。这与每条小 RHS 自己的 residual 门是两个独立问题。

## 运行与样本

| 项目 | 事实 |
|---|---|
| runroot | [`20260918T095546.139183Z`](../../../results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/) |
| unit / invocation | `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` / `1cf5e34338754dbfa80df487b322c72c` |
| producer / consumer | `29504.116038094042 s`, rc0 / `135717.4772190291 s`, rc1 |
| public / finalizer | `165222.44361121487 s` / charged `165228.433265082 s` |
| terminal | finalizer `failed/service_boundary_failure`；`SERVICE_RESULT=exit-code`, `EXIT_STATUS=3`；`NOTIMPLEMENTED` 仅为 systemd 展示别名；不是 OOM、超时或外部 kill |
| rows | 40 = 8 probe + 32 modal；bottom/top 各 16 modal |
| formal / outer / RTA | `0/4800` / `not_started`, 0 / `not_run` |

| side | count | iteration sum | elapsed sum (s) | max true residual | reason |
|---|---:|---:|---:|---:|---|
| bottom | 16 | 352 | `36004.124497986864` | `0.009981656767193032` | 2 |
| top | 16 | 394 | `40527.54153031926` | `0.009939510152843832` | 2 |

32 modal rows均 `explicit_true_target_reached=true`，但这不等于重复一致性通过，也不等于全局 residual 或 RTA。终态 32 条样本的固定算术为 `(36004.124497986864/16 + 40527.54153031926/16) × 2400 / 86400 = 132.86747574358702 days`；D2a 旧 21 条样本的 `133.57896112787233 days` 仅属于旧窗口，旧 8-probe 约 `115.17 days` 另列。它们都是条件算术，不能称 ETA，且不把 `batch_size=32` 写成 32 路并行。

## 资源、packet 与复用

权威全树 RSS peak `642483171328 B`，cgroup peak `647904940032 B`；终态 cgroup 已清理，不能填 D2a 旧 current。资源合同为 warning `1539316278886 B`、hard RSS `1759218604442 B`、runtime reserve `412316860416 B`；service minimum MemAvailable `836790292480 B`，全树采样 `407853`，PSS/USS 的完整 smaps 样本 `5480`。job/cgroup swap 为 0；global 基线 `8192 B`，新增 used `290816 B`、pswpout +71 页。采样最大 gap `11.7317484519 s`。producer packet 的 32 shard/33 文件、`4842723531 B` 与 manifest SHA `7ef2ecc5587f79a123e44cacfe347356d13b36336948ade1672787c6430163d2` 保留；`qep_workspace_persisted=false`。

终态已生成 public `supervisor_summary.json`（SHA `65edfd58060e49216b074bd59e27fe15b90a564288defcda50ac8abf400c1a6d`）。一次只读 producer validator 返回 `rc=0/pass`、`producer_resource_qualified=true`，in-process wall `1.0323800740297884 s`（imports/startup excluded），父侧完整 wall `not_measured`；没有 fresh ABI 或 32-shard hash 重验。日志及 stderr 原样见 [`d3a_producer_packet_validator_20260920.log`](../../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_2nm_p6h1p5_m1200_mpi8_supervision/d3a_producer_packet_validator_20260920.log)。这闭合 producer/public metadata qualification，但不等于 consumer-only restart 已运行或全量 shard/ABI 已复核。p4 factor、未完成 Schur 和 native workspace没有 checkpoint；后续复用仍需按现有身份、生命周期、资源和清理合同启动。

独立 ledger：[`task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json`](../../../results/task041_side_balh_component_audit/d1c_preparation_20260917_8d47747d/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json)，SHA `f01a0027b5303d7dae2ac0be542eb6273160c1ba150596907d55e09879cd2de9`；before `77232.864925164 s` → D1e charge `165228.433265082 s` → after `242461.29819024602 s`，该 unit 只收费一次。worker gone、post-hash、artifact hash、ledger 写入和 pre-exit members clean 为 true；`public_result_completed` 与 `service_terminal_normal` 为 false。

完整 hash-bound 字段见 [`task041_d3a_terminal_20260920.json`](records/task041_d3a_terminal_20260920.json) 与 [`Response V8`](../response_v8.md)。
