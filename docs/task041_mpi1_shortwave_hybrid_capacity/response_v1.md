# Task041 受控停止响应 v1

本响应保留两个 3 nm run 的独立身份，并区分 diagnostic marker、formal authority、资源和生命周期证据；不把失败 attempt 升级为 formal/physics pass。

## 3 nm 两次独立记录

| run | status / classification | 数值结论 | 资源与生命周期 |
|---|---|---|---|
| `20260907T111441.388055Z` fresh producer+consumer attempt | `failed` / `IMPLEMENTATION_FAILURE` | failure stage=`consumer_exit(solution_snapshot_destroyed)`；五残差仅为 independent diagnostic marker only：reported/global/bottom/modal/top=`7.246419845266236e-10 / 6.711767430501667e-10 / 6.842952026951734e-12 / 7.252171978674087e-11 / 6.339676899706935e-10`；formal_result/gates/physics=null，不是 formal authority | producer RSS/PSS/USS=`16.784275055/15.785678864/15.674812317 GiB`；consumer/workflow=`255.465618134/253.694432259/253.435222626 GiB`；producer/consumer/workflow wall=`18000.658898/22215.056788/40216.175178 s`；swap=`0`；failed-attempt lifecycle diagnostic通过 |
| `20260908T001027.090767Z` consumer-only implementation retry | `measured_candidate_physics_negative` / `TASK041_CONSUMER_NUMERICAL_FAILURE` | solve/recovery mechanics PASS；own physics FAIL only because abs(A_balance-A_volume)=`1.9160032445286745e-5`>`1e-5`；reported/global/bottom/modal/top=`1.0614289127347946e-9 / 1.3530838051427825e-9 / 9.525482983090863e-12 / 5.059125745287973e-11 / 1.278144562727163e-9` | peak=`229028663296 B = 213.299564362 GiB`；wall=`17047.323762 s`；swap=`0`；release-before-recovery通过 |

fresh failed-attempt lifecycle：supervisor_summary.consumer.lifecycle.outer_release 记录 actions_destroyed=true、component_cleanup_pass=true、factor_cleanup_pass=true、factor_count_after_cleanup bottom/top=0/0、rss_drop=pass；memory authority=`274205020160→260347596800 B`。这与 retry 的 release evidence 独立。

retry candidate R/T/A_balance/A_volume 为 `0.8048686830648746 / 0.0002839834330554354 / 0.19484733350206998 / 0.19486649353451532`；authority 的 `grid_payload=null`、`canonical=null`，official RTA unavailable。

两次 run 均为 MUMPS factor-only、ICNTL14=`40`，无 global direct、coarse 或 OOC。bottom/top corrected factor NNZ 分别为 fresh=`3.259e9/3.716e9`、retry=`3.304e9/2.861e9`。峰值位于两侧 factor 同时驻留后的 top-factor/top-Woodbury；modal rank=`1600`，单个 modal Schur/constraint/LU 各=`40960000 B`。当前最大对象族是两侧 MUMPS factors；约 `42.166 GiB`跨 run 峰值差不能解释为生命周期释放量，因为 factor NNZ 已变化。

retry lifecycle：bottom/top factor count `1/1→0/0`，actions/components destroyed，`rss_drop=pass`；cgroup authority `229028663296→218838220800 B`，final marker=`211014574080 B`。

producer stage boundaries（20260907 marker wall）：positive_qep_solve=`1.167750278 s`；negative_qep_solve=`3273.625841 s`，前段=`3272.458090 s`（含 positive right+adjoint basis，不是单次 solve）；raw_candidate_modes_ready=`4964.725796 s`（区间=`1691.099955 s`）；selected_biorthogonal_bases_ready=`7082.702076 s`（区间=`2117.976280 s`）；modal_qep_temporaries_released=`17997.088030 s`（之后=`10914.385954 s`）。
最后 10914 秒区间源码上主要只有 `pair_reciprocal_mode_bases` 与轻量收尾；旧 record 没有独立 pairing marker，故仅由源码成本支持其为主导，不能冒充独立计时。qep_begin=`0.192512509 s`、qep_ready=`17998.540383 s`、producer peak=`16.784275055 GiB`、packet bytes=`913401973`、packet write max-rank=`0.963676714 s`、consumer_qep_required=false；qep_begin 至 qep_ready 不被统称为 eigensolve。

## QEP 优化收口

旧 reciprocal mass overlap 为 `3PN` 次 MatMult：M800=`1,920,000`、M1200=`4,320,000`；新实现为 `P+N`：1600/2400，仍完整形成 P×N cost 与 dots 并执行 Hungarian assignment，不能宣称整体 1200/1800 倍提速。K0/K1/K2 Frobenius norms 已由逐 mode 重算改为每 operator tuple 一次，残差公式与 Gate 不变。phase6 新增并持久化 `timings[reciprocal_pairing]`；新归约顺序允许容差内浮点差异，下一次 packet 属于新的 source-bound hash，必须通过 canonical/selection Gate，不承诺与旧 packet byte-identical。
当前没有 post-change formal performance 数据，M1200 未运行；Task041 physics stop 仍有效，任何小时数均不得写成 measured。

## 5 nm 证据边界

Task039 继承基线与本机 MPI8 复现分开记录：

- 原继承 record：`benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json`，source=`9e31ecf189081afcb8ca27b0374ec89af0094e2d`，peak=`80.0258560180664 GiB`，wall=`10126.231902 s`，五残差（reported/global/bottom/modal/top）=`3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10`，full numerical/recovery/physics PASS。
- 本机 MPI8 复现 root：`results/task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf`，source=`def547cfd139b6377b0cae2ba1736ec3591814b0`，input=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`，physical=`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`，resolved=`d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798f`；peak=`80.2187461853 GiB`，elapsed=`8357.347033 s`，swap=`0`，五残差=`2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10`，R/T/A_balance/A_volume=`0.7331842733894981 / 0.00022009869572663576 / 0.26659562791477526 / 0.2665962726231523`，solve/recovery/physics PASS。

本机复现相对继承基线增加 `0.192890167 GiB`（`+0.2410%`），快 `1768.885 s`（`17.47%`）；这是用户授权的本机复现，不是原继承 run。

`task041_s1_source_only_p6h4_m480_mpi1_6ae90799`（source=`6ae907991ceb3323c06b351d13a9557685e4d713`）的 keys、roundtrip、repeat 通过，但 current_vs_persisted=`3.826978841496932e-9 > 1e-12`，分类为 `REFERENCE_SOURCE_SEMANTICS_CHANGED`；旧 MPI8 authority 保留，corrected MPI1 不得声明完整 MPI 等价。

5 nm MPI1 最后 attempt 的 consumer solve/recovery/physics 和候选 RTA 通过，但 `external_key_binding_pass=false`（600 keys 数量相同而 hash 不符）；外层又因 terminal process-tree sample unreadable 分类为 `task041_resource_sample_failure`，因此没有合格 consumer/workflow 内存 authority 或完整 equivalence。四次 attempt 的阶段表见 `outcomes/mpi1_5nm_equivalence.md`。

## 严格停止边界

3 nm M800 未达到 accuracy-qualified physics result；因此 M1200、M1600、3 nm h2.5/h2、全部 2 nm 及后续 MPI1 均为 `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE`，不是技术无能力或资源失败。213–255 GiB 且 factor 主导这一事实只能支持如下推断：3 nm 尚未 accuracy-qualified，不能作正式 0.7 nm 容量外推；若以后进入 0.7 nm，仍需要 Task040 的 factor-free scalable architecture。

merge approval=`NO`。失败 root、diagnostic checkpoint、negative authority、source-semantics negative 和所有未运行边界均保留。
