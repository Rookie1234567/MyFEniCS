# V4 Full3D h4 生命周期与正式运行边界

## 结论

本轮正式 Full3D h4（5 nm、1° grazing、phi=0、S、p6/h4、MPI8；Hybrid M480 仅为
比较目标）在组装完成后进入 MUMPS `KSPSetUp`，运行满 21600 s 后由 launcher 按配置
timeout 结束。factor setup 已开始但 factorization 未返回、没有 factor-ready marker，
solve 未开始。因此 Full3D factor Gate 是 `not_completed`，不是一个把数值方法判负的
残差结果。原始 run 保留在 ignored result root，compact record 是
[task039_v4_full3d_h4_lifecycle_timeout_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_full3d_h4_lifecycle_timeout_v1.json)。

## 身份与阶段

| 项目 | 实测/绑定值 |
| --- | --- |
| source / input / resolved / physical | `8bcbee81d809f8135e81ccc8e906191aabb8d60f` / `e96cf2373618002137c28620963eea7b31de2e99c8f9b4a7b587527b09457937` / `6554db8fc4a502714c0423d2891929173d1411fddaafac2e2f67177a09d5cd66` / `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| internal modes / comparison target | Full3D internal M is `not_applicable`; comparison target is Hybrid M480 |
| dynamic external inventory | 600 unique keys；bottom/top 296/304；keys SHA256 `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` |
| final progress | 31 aligned rows；`during_ksp_setup_peak` / `active` |
| assembled system | 756600 rows；used NNZ 634515048；allocated NNZ 660585840 |
| factor / solve / recovery | factor setup started；factor `not_completed`；无 factor-ready 或 factor-destroy marker；solve/recovery `not_run` |

The worker had completed dynamic mode preparation and augmented-matrix assembly. It
then entered direct MUMPS factor setup. The last progress marker was
`during_ksp_setup_peak` at 418.514586 s; factorization never returned and no later solve,
packet, recovery, canonical, selected-field, `A_volume` or closure evidence exists.
The worker ledger explicitly says `worker_did_not_persist_record`.

## 资源口径

The complete process-tree sampler recorded a peak at
`2026-08-17T10:13:38.194943+00:00`:

| metric | measured |
| --- | ---: |
| RSS | 223676952576 B = 213314.96484375 MiB = 208.3153953552246 GiB |
| PSS / USS | 212270.60546875 / 212106.3203125 MiB |
| swap | 0 B |
| samples / poll | 19619 / 0.25 s |
| absolute hard stop | 224000000000 B |
| margin to hard stop | 323047424 B |

The 170 GiB warning and 195 GiB checkpoint were crossed, but the absolute byte hard
stop was not reached. The process group exited after the configured 21600 s timeout;
this must not be described as an OOM or memory-hard-stop classification. RSS/PSS/USS
are complete process-tree measurements, not a sum of per-rank estimates. Because the
timeout occurred during factor setup, this run provides no evidence that post-factor
lifecycle release could reduce that setup peak.
The UTC manifest wall-clock interval was 21092.211098 s while the monotonic watchdog
elapsed value was 21600.036032554985 s; the observed 507.82493455498487 s discrepancy
is retained as an observed clock discrepancy, without assigning an NTP cause.

## Evidence boundary and next phase

The older h4 partial result and the 2D Q8 result remain historical/incomplete
diagnostics. They do not complete this h4 authority and must not be used to claim a
Full3D solve, recovery, or a three-method comparison. This timeout does not block the
independent V4-4 shared selected-mode packet work. That packet is a separate
hash-bound data path: a QEP producer may write it and exit, while direct/iterative
consumers read the same selected M480 modes without starting QEP. It does not
retroactively turn this incomplete Full3D run into a solved authority.
