# Resource scaling and capacity frontier

## 两次 3 nm 资源记录（口径分开）

| 生命周期 | root | RSS / PSS / USS peak | wall | swap | status |
|---|---|---|---:|---:|---|
| 20260907 fresh producer+consumer attempt | 20260907T111441.388055Z | producer=16.784275055 / 15.785678864 / 15.674812317 GiB；consumer/workflow=255.465618134 / 253.694432259 / 253.435222626 GiB | 40216.175 s | 0 | IMPLEMENTATION_FAILURE at consumer_exit(solution_snapshot_destroyed) |
| 20260908 consumer-only retry | 20260908T001027.090767Z | cgroup peak=229028663296 B = 213.299564362 GiB；PSS/USS=NA | 17047.323762 s | 0 | candidate physics negative |

20260907 的 resource measurement 仍有效，但不能被描述成 formal success。20260908 是旧 producer packet 的 consumer-only implementation retry。两次峰值可以作跨 run 的资源比较，但不能相加为同一 workflow，也不能把峰值差直接写成对象释放量；factor NNZ 已发生变化。

20260907 producer stage boundaries：positive_qep_solve=`1.167750278 s`；negative_qep_solve=`3273.625841 s`，前段=`3272.458090 s`（含 positive right+adjoint basis，不能称单次 solve）；raw_candidate_modes_ready=`4964.725796 s`（`1691.099955 s`）；selected_biorthogonal_bases_ready=`7082.702076 s`（`2117.976280 s`）；modal_qep_temporaries_released=`17997.088030 s`（之后=`10914.385954 s`）。最后区间旧 record 无独立 pairing marker，源码成本支持 `pair_reciprocal_mode_bases` 为主导，但不是独立实测计时。
qep_begin=`0.192512509 s`、qep_ready=`17998.540383 s`、producer peak=`16.784275055 GiB`、packet bytes=`913401973`、packet write max-rank=`0.963676714 s`、consumer_qep_required=false；qep_begin 到 qep_ready 不统称为 eigensolve，packet I/O 不是约 5 小时主因。

## QEP 优化的资源/计时边界

旧 reciprocal mass overlap 为 `3PN` MatMult（M800=`1,920,000`、M1200=`4,320,000`）；新实现为 `P+N`（1600/2400），但仍形成完整 P×N cost/dots 和 Hungarian assignment，不能写成整体 1200/1800 倍提速。K0/K1/K2 Frobenius norms 改为每 operator tuple 一次，公式/Gate不变；`timings[reciprocal_pairing]` 已写入 producer controlled-stop record。新归约顺序可能产生容差内浮点差异，下一次 packet 是新的 source-bound hash，必须通过 canonical/selection Gate，不承诺与旧 packet byte-identical。当前没有 post-change formal performance 数据，M1200 未运行，Task041 physics stop 仍有效。

### 可复用的单热点性能 SOP

冻结 source/input/physical/resolved hashes、M/mesh/MPI、线程、affinity、partition 与 factor fingerprints；每轮只改一个热点，先跑 focused correctness，再跑一次 candidate。仅在数值等价、阶段 wall、swap=0、producer 完全退出后才启动 consumer、无阶段重叠且 `workflow peak=max(producer,consumer)` 不增时验收；两阶段峰值不得相加。QEP 资源线为 preferred/warning/hard=`128/176/192 GiB`、swap=0，阶段内存可上升；同身份同 workload 的峰值须不高于实测 M800 retry=`213.299564362 GiB`，`256 GiB` 仅为跨 workload 安全硬线。M 变化是新 workload，须单列，不能冒充同 case 回归。

## Factor 主导与 frontier 解释

两次 run 均为 MUMPS factor-only、ICNTL14=40，无 global direct、coarse 或 OOC。bottom/top corrected factor NNZ：fresh=3.259e9/3.716e9，retry=3.304e9/2.861e9。峰值在两侧 factor 同时驻留后的 top-factor/top-Woodbury；modal rank=1600，单个 modal Schur/constraint/LU 各=40960000 B。因此当前最大对象族是两侧 MUMPS factors。约 42.166 GiB 是跨 run 峰值差，不等于 lifecycle 释放量，因为 factor NNZ 已变化。

这些峰值都不是资源越线证据；停止由 3 nm M800 own-physics closure Gate 触发。因此 Task041 没有形成 3NM_RESOURCE_FRONTIER，也没有 1.50 TiB 下的 accuracy-qualified 最细网格结论。

关于 0.7 nm 的判断是推断而非正式容量外推：3 nm 尚未 accuracy-qualified，但 213–255 GiB 且 factor 主导，说明若以后进入 0.7 nm，仍需要 Task040 factor-free scalable architecture。
