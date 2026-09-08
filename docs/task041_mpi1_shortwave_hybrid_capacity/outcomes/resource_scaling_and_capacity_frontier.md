# Resource scaling and capacity frontier

## 两次 3 nm 资源记录（口径分开）

| 生命周期 | root | RSS / PSS / USS peak | wall | swap | status |
|---|---|---|---:|---:|---|
| 20260907 fresh producer+consumer attempt | 20260907T111441.388055Z | producer=16.784275055 / 15.785678864 / 15.674812317 GiB；consumer/workflow=255.465618134 / 253.694432259 / 253.435222626 GiB | 40216.175 s | 0 | IMPLEMENTATION_FAILURE at consumer_exit(solution_snapshot_destroyed) |
| 20260908 consumer-only retry | 20260908T001027.090767Z | cgroup peak=229028663296 B = 213.299564362 GiB；PSS/USS=NA | 17047.323762 s | 0 | candidate physics negative |

20260907 的 resource measurement 仍有效，但不能被描述成 formal success。20260908 是旧 producer packet 的 consumer-only implementation retry。两次峰值可以作跨 run 的资源比较，但不能相加为同一 workflow，也不能把峰值差直接写成对象释放量；factor NNZ 已发生变化。

20260907 producer telemetry：qep_begin=0.192512509 s、qep_ready=17998.540383 s、producer peak=16.784275055 GiB、packet bytes=913401973、packet write max-rank=0.963676714 s、consumer_qep_required=false。qep_begin 到 qep_ready 不被统称为 eigensolve。

## Factor 主导与 frontier 解释

两次 run 均为 MUMPS factor-only、ICNTL14=40，无 global direct、coarse 或 OOC。bottom/top corrected factor NNZ：fresh=3.259e9/3.716e9，retry=3.304e9/2.861e9。峰值在两侧 factor 同时驻留后的 top-factor/top-Woodbury；modal rank=1600，单个 modal Schur/constraint/LU 各=40960000 B。因此当前最大对象族是两侧 MUMPS factors。约 42.166 GiB 是跨 run 峰值差，不等于 lifecycle 释放量，因为 factor NNZ 已变化。

这些峰值都不是资源越线证据；停止由 3 nm M800 own-physics closure Gate 触发。因此 Task041 没有形成 3NM_RESOURCE_FRONTIER，也没有 1.50 TiB 下的 accuracy-qualified 最细网格结论。

关于 0.7 nm 的判断是推断而非正式容量外推：3 nm 尚未 accuracy-qualified，但 213–255 GiB 且 factor 主导，说明若以后进入 0.7 nm，仍需要 Task040 factor-free scalable architecture。
