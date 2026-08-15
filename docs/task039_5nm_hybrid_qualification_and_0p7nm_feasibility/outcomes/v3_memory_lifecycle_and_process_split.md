# V3-6：内存生命周期与进程拆分取证

本阶段只做离线解析，不启动 PDE、MPI、QEP 或迭代求解。比较对象都是
p6/h5/M480/MPI8 Hybrid direct；历史案为 10°，当前案为 1°，因此两案只在入射角及
对应外部模式身份上不同。这里的 `stage-aligned` 是把 worker 的阶段 marker 与外层
process-tree 采样按同一条相对单调时钟对齐；它不是把对象容量相加，也不是把 marker
本身当成峰值。

完整的 hash-bound compact record：
[task039_v3_memory_lifecycle_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_memory_lifecycle_v1.json)。

## 1. 身份、路径与证据边界

|对象|正式 run root|源码/物理身份|telemetry 状态|
|---|---|---|---|
|历史 10° Hybrid direct|`results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h5_mpi8__hybrid_direct__mpi8__M480/20260814T113034.312872Z`|source `e58dfc6cc8d01c39e83f20cafdb52669809d50a9`；physical `e35907c72ab97069d9ab66958fd00787f98dea08dce1aa6f64c053b7bda46cdb`|三文件均在 canonical clone 存在并已解析|
|当前 1° Hybrid direct|`results/task039_5nm_v3_1deg_s5_hybrid_direct_m480/task039_v3_hybrid_direct_p6h5_m480_mpi8__hybrid_direct__mpi8__M480/20260815T111156.797076Z`|source `5bfab734a9ca053b69fa1f3f20d907aacbf8b07f`；physical `0462c9806f1eb0c525c3ab50fcd71e212c6d05337de49c76e7946a336ccd576d`|三文件均存在并已解析|
|同物理 Full3D h5 resource anchor|`results/task039_5nm_v3_1deg_s5_full3d/task039_v3_3d_p6h5_full3d_direct_mpi8__full3d_direct__mpi8__Mna/20260815T055152.423656Z`|source `5872cda24e47c750d654fa7b06d81057af5bf9fc`；physical 与当前 1° Hybrid 相同|仅作 compact 资源锚点，不参与 stage parser|

三份 telemetry 的 SHA256 已写入 compact record。关键 hash 为：

|对象|`memory_stages.jsonl`|`process_tree_samples.jsonl`|`memory_object_ledger.json`|
|---|---|---|---|
|历史 10°|`b856bb44300c6716e35baadfb8aec0dbd566d7a8c6d8df51b68eb59f879ce20a`|`cd2df1b8d00e88283f1f893efe2e080899604934a2410b5873aee7fe58c7f37b`|`2292ef233c9594592a6188b7f76646ad982fe0075a33e4d3c33e7094becbd948`|
|当前 1°|`1d14655fd599d6b49e2032d7ccfaaed1f99a3c396c86047f352338e3ecaebc8b`|`c0db00f278dd43e41436cb1fc4e728d389712e4579adc41273cece4c3b72cb96`|`d8e83fe350b79ae263394a42047c1989bcf085cb19e796921311b9c2f62f1a04`|

## 2. 18 阶段和采样完整性

解析器复用 `benchmarks.task039_memory_telemetry.py` 的固定 18 阶段顺序：
`baseline_before_mesh → mesh_spaces_ready → qep_matrices_ready → positive_qep_peak → negative_qep_peak → raw_candidate_modes_ready → selected_biorthogonal_bases_ready → canonical_traces_ready → projection_matrices_ready → traction_matrices_ready → local_fe_dtn_ready → hybrid_augmented_matrix_ready → mumps_analysis_ready_when_available → mumps_numeric_factor_ready → solution_ready → field_reconstruction_peak → modal_qep_temporaries_released → final_cleanup`。

|检查|历史 10°|当前 1°|
|---|---:|---:|
|stage count / unique / order|18 / true / true|18 / true / true|
|可读 process-tree 行数|8968 / 8968 valid|8842 / 8842 valid；numerical summary 的 authority count 为 8840|
|invalid sample|0|0|
|smaps attempted / complete|8968 / 8964|8842 / 8837|
|首个 sample elapsed (s)|0.004958940000506118|0.004988082000636496|
|最后 sample：`telemetry_span_seconds` (s)|3560.9153867349996|3773.4715124369977|
|poll interval|0.25 s|0.25 s|
|solver/launcher elapsed|`not_available`（raw 没有独立权威字段）|`not_available`（raw 没有独立权威字段）|

`telemetry_span_seconds` 是最后一个 process-tree sample 的时间跨度，不冒充 solver 总耗时。
单位为 MiB=`bytes/2^20`、GiB=`bytes/2^30`，十进制 GB=`bytes/1e9`。

非末段区间使用 `[start,next_start)`，末段才包含尾部，因此 next stage 的 entry sample
不会重复计入前一段。两案共同出现同 anchor 的阶段为：
`mesh_spaces_ready`、`qep_matrices_ready`、`canonical_traces_ready`、
`projection_matrices_ready`、`traction_matrices_ready`、`hybrid_augmented_matrix_ready`、
`mumps_numeric_factor_ready`、`modal_qep_temporaries_released`。

这些碰撞阶段仍保留 entry snapshot，但 local peak、exit delta 和 release 后的独立峰值
标为 `not_available_by_collision`。这不是把缺失值写成零，也不是把 marker 时间误读成
峰值。两案都在 `modal_qep_temporaries_released` 记录 `after_destroy=true`；allocator
counter 本身仍为 `not_available`。

## 3. 峰值与关键阶段表

两案的 global peak 都在 `field_reconstruction_peak`。下表列出真实可分辨的关键阶段；
RSS/PSS/USS 是分别取出的 process-tree 峰值，不能相加。

|case|stage|RSS (MiB)|PSS (MiB)|USS (MiB)|证据状态|
|---|---|---:|---:|---:|---|
|10° p6/h5|`selected_biorthogonal_bases_ready`|83836.828125|82692.39453125|82493.078125|measured|
|10° p6/h5|`mumps_analysis_ready_when_available`|86430.71484375|84990.013671875|84747.48046875|measured|
|10° p6/h5|`solution_ready`|86452.0|84990.5517578125|84747.55859375|measured|
|10° p6/h5|`field_reconstruction_peak`|86744.54296875|85040.2392578125|84748.19921875|measured global/stage peak|
|10° p6/h5|`modal_qep_temporaries_released`|31068.6640625|`not_available`|`not_available`|entry only; collision; after_destroy=true|
|10° p6/h5|`final_cleanup`|31068.6640625|29411.8818359375|29119.80859375|measured retention snapshot|
|1° p6/h5|`selected_biorthogonal_bases_ready`|83918.9765625|82817.931640625|82631.9140625|measured|
|1° p6/h5|`mumps_analysis_ready_when_available`|86751.1640625|85353.9033203125|85124.6328125|measured|
|1° p6/h5|`solution_ready`|86754.47265625|85354.416015625|85124.76171875|measured|
|1° p6/h5|`field_reconstruction_peak`|87064.125|85404.1533203125|85125.4296875|measured global/stage peak|
|1° p6/h5|`modal_qep_temporaries_released`|37090.43359375|`not_available`|`not_available`|entry only; collision; after_destroy=true|
|1° p6/h5|`final_cleanup`|37090.43359375|`not_available`|`not_available`|measured RSS retention snapshot|

从测量可直接得到的阶段差异是：

|case|selected bases 占最终 RSS 峰值|selected → MUMPS analysis|MUMPS analysis → field peak|
|---|---:|---:|---:|
|1° p6/h5|`83918.9765625 / 87064.125 = 96.3875%`|`+2832.19 MiB`|`+312.96 MiB`|
|10° p6/h5|`83836.828125 / 86744.54296875 = 96.648%`|`+2593.89 MiB`|`+313.83 MiB`|

这只是时间对齐后的测量推断，不是对象级因果分解。角度从 10° 改为 1° 后，global
RSS 只增加 `319.58203125 MiB`，相对增加 `0.368417447729%`。两案最终 cleanup 相对
峰值的 RSS 下降分别为 10° 的 `55675.87890625 MiB` 和 1° 的 `49973.69140625 MiB`。
这证明后段确实释放了大量 RSS，但释放发生在既有峰值之后，不能降低当前峰值。

## 4. Full3D 基准与迭代目标

|运行|RSS / PSS / USS (MiB)|RSS (GiB)|swap|elapsed 口径|
|---|---|---:|---:|---|
|历史 10° Hybrid direct|86744.54296875 / 85040.2392578125 / 84748.19921875|84.71146774291992|0|telemetry span 3560.915386735 s|
|当前 1° Hybrid direct|87064.125 / 85404.1533203125 / 85125.4296875|85.0235595703125|0|telemetry span 3773.471512437 s|
|1° Full3D h5 resource anchor|96151.16796875 / 94117.4697265625 / 93793.1796875|93.89762878417969|0|`not_available` in this record|

当前 1° Hybrid direct 相对同物理 Full3D h5 的 RSS 节省为 `9087.04296875 MiB`、
`8.876995086669922 GiB`，即 `9.450787921477%`。这不是 V3-10 iterative 资格。

```math
\mathrm{saving} =
\frac{96151.16796875-87064.125}{96151.16796875}
= 0.094507879215 = 9.450787921477\%.
```

Review 的 20% 目标要求 iterative RSS 不超过当前 direct 的 80%：

|目标|计算|结果|
|---|---|---:|
|iterative RSS 上限|`0.8 × 87064.125 MiB`|`69651.3 MiB = 68.01884765625 GiB`|
|相对当前 direct 还需降低|`87064.125 - 69651.3 MiB`|`17412.825 MiB = 17.004711914062 GiB`|
|V3-6 是否验证|没有 iterative qualification run|`not_evaluated`|

## 5. 保守归因与 M-A/M-B/M-C 顺序

`not_available` 表示证据缺失，不是零；`not_established` 表示当前测量不能唯一归因。
对象 ledger 的容量永远不与 process-tree 峰值相加。

|候选解释|当前证据|结论|
|---|---|---|
|QEP / modal basis|selected bases 已占峰值约 96.39%（1°）/96.648%（10°）|高优先级测量线索；不是对象级因果证明|
|P/T coupling|coupling 后到 peak 的可分辨增量很小|不把它单独判为 dominant|
|external DtN / augmented matrix|marker 有序，但碰撞使独立 local peak 不可分|`not_established`|
|MUMPS|global peak 可测，factor ownership 未拆分|`not_available`|
|field recovery|field marker 与 global peak 对齐|不能只据 marker 声称其为对象主因|
|lifecycle overlap|后段 RSS 大幅下降，但发生在 peak 后|hypothesis，未建立|
|allocator high-water|没有 allocator counter|唯一保守分类 `UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER`|

因此下一步优先级是：

1. **M-A：显式生命周期释放。** 在 `selected_biorthogonal_bases_ready` 之后、
   canonical/P/T/MUMPS 之前，针对 EPS/ST/KSP、QEP 矩阵、raw/未选 candidate 和不再需要
   的 full-mode 临时量做对象级 destroy/release 试验，并重新测量。不能声称 M-A 必然
   回收全部 `17,412.825 MiB`；若 PETSc/SLEPc/allocator 不把至少 `17.004711914062`
   GiB 还给 OS，再进入 M-B。
2. **M-B：进程拆分。** 将 QEP/modal preparation 与 solve 分进程，借助进程退出清空
   allocator；本轮没有实现或测试。
3. **M-C：P/T 流式组装。** 目标已经在 coupling 前被 selected bases 超过，因此不是
   首选；不等于证明流式组装没有收益，本轮没有实现或测试。

本轮未改变 ordinary defaults、solver、物理阈值或 raw。V3-7 及后续 PC/iterative
工作在 V3-6 受控停止，等待审阅；没有启动 PDE/MPI。
