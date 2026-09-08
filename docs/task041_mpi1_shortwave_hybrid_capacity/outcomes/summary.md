# Task041 Outcomes Summary

本表只使用已核验标量。`NA` 表示未记录或未形成合格 authority；不以推测补值。20260907 与 20260908 是两个独立 3 nm 记录。

## 主结果表

| wavelength / mesh / M / MPI | status | source SHA | input / physical / resolved SHA | active rows / external keys | M | iterations / five residuals（reported/global/bottom/modal/top） | R / T / A_balance / A_volume | grid/M comparison | producer / consumer / workflow memory | wall / swap | factor inventory | classification | evidence |
|---|---|---|---|---|---:|---|---|---|---|---|---|---|---|
| 3 nm / p6h3 / M800 / MPI8 fresh `20260907T111441.388055Z` | `failed` | source=`48f56ad46c49519de363b90695d1ed219236c662` | input=`5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f`；physical=`0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81`；resolved=`726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782` | `268272 / 1748` | `800` | diagnostic marker only：`7.246419845266236e-10 / 6.711767430501667e-10 / 6.842952026951734e-12 / 7.252171978674087e-11 / 6.339676899706935e-10`；formal_result/gates/physics=null | `NA` | 未进入有效 qualification | producer RSS/PSS/USS=`16.784275055/15.785678864/15.674812317 GiB`；consumer/workflow=`255.465618134/253.694432259/253.435222626 GiB` | producer/consumer/workflow=`18000.658898/22215.056788/40216.175178 s`；swap=`0` | corrected bottom/top=`3.259e9/3.716e9`；MUMPS factor-only，ICNTL14=40；无 global direct/coarse/OOC | `IMPLEMENTATION_FAILURE` at `consumer_exit(solution_snapshot_destroyed)` | `.../20260907T111441.388055Z/` |
| 3 nm / p6h3 / M800 / MPI8 retry `20260908T001027.090767Z` | `measured_candidate_physics_negative`；solve/recovery mechanics PASS | consumer=`2dbe7ff76d734c7689740a656ba7c0fdb5ceadcb`；producer=`48f56ad46c49519de363b90695d1ed219236c662` | input=`5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f`；physical=`0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81`；resolved=`726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782` | `268272 / 1748` | `800` | `1.0614289127347946e-9 / 1.3530838051427825e-9 / 9.525482983090863e-12 / 5.059125745287973e-11 / 1.278144562727163e-9` | `0.8048686830648746 / 0.0002839834330554354 / 0.19484733350206998 / 0.19486649353451532`；abs(A_balance-A_volume)=`1.9160032445286745e-5`>1e-5 | M1200/M1600、h2.5/h2 未运行；无收敛结论 | peak=`229028663296 B = 213.299564362 GiB`；PSS/USS=`NA` | `17047.323762 s` / `swap=0` | bottom/top=`3.304e9/2.861e9`；MUMPS factor-only，ICNTL14=40；无 global direct/coarse/OOC | `TASK041_CONSUMER_NUMERICAL_FAILURE`；official RTA unavailable | `.../20260908T001027.090767Z/` |
| 5 nm / p6h4 / M480 / MPI8 Task039 inherited | `pass` | `9e31ecf189081afcb8ca27b0374ec89af0094e2d` | input=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`；physical/resolved=`NA`（原 record 本轮未展开） | `NA / NA` | `480` | `3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10` | `NA` | inherited reference | peak=`80.0258560180664 GiB`；PSS/USS=`NA` | `10126.231902 s` / 0` | `NA` | full numerical/recovery/physics PASS | `benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json` |
| 5 nm / p6h4 / M480 / MPI8 Task041 local reproduction | `pass` | `def547cfd139b6377b0cae2ba1736ec3591814b0` | input=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`；physical=`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`；resolved=`d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798f` | `NA / NA` | `480` | `2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10` | `0.7331842733894981 / 0.00022009869572663576 / 0.26659562791477526 / 0.2665962726231523` | local reproduction；非原继承 run | peak=`80.2187461853 GiB`；PSS/USS=`NA` | `8357.347033 s` / 0` | `NA`（本轮轻量 summary未保留） | solve/recovery/physics PASS | `results/task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf` |

## producer、factor 与生命周期

20260907 producer telemetry：qep_begin=`0.192512509 s`、qep_ready=`17998.540383 s`、producer peak=`16.784275055 GiB`、packet bytes=`913401973`、packet write max-rank=`0.963676714 s`、consumer_qep_required=false。qep_begin 到 qep_ready 不被统称为 eigensolve。

两次 3 nm run 均为 MUMPS factor-only、ICNTL14=`40`，无 global direct/coarse/OOC。modal rank=`1600`；单个 modal Schur、constraint、LU 各=`40960000 B`。峰值发生在两侧 factor 同时驻留后的 top-factor/top-Woodbury，当前最大对象族是两侧 MUMPS factors。corrected factor NNZ：fresh=`3.259e9/3.716e9`，retry=`3.304e9/2.861e9`；约 `42.166 GiB`跨 run 峰值差不能写成对象释放量，因为 factor NNZ 已变化。

fresh failed-attempt lifecycle：actions_destroyed=true、component_cleanup_pass=true、factor_cleanup_pass=true、factor_count_after_cleanup bottom/top=`0/0`、rss_drop=pass；memory authority=`274205020160→260347596800 B`。retry release-before-recovery：factor count `1/1→0/0`，actions/components destroyed，rss_drop=pass；cgroup authority=`229028663296→218838220800 B`，final marker=`211014574080 B`。


## 5 nm source semantics 与 MPI1

source-only root=`task041_s1_source_only_p6h4_m480_mpi1_6ae90799`，source=`6ae907991ceb3323c06b351d13a9557685e4d713`：keys、roundtrip、repeat通过，但 current_vs_persisted=`3.826978841496932e-9 > 1e-12`，分类=`REFERENCE_SOURCE_SEMANTICS_CHANGED`；旧 MPI8 authority 保留，corrected MPI1 不得声明完整 MPI 等价。

5 nm MPI1 最后 attempt 中 consumer solve/recovery/physics 与候选 RTA 通过，但 external_key_binding_pass=false（600 keys 数量相同而 hash 不符）；外层 terminal process-tree sample unreadable，分类为 task041_resource_sample_failure。因此没有合格 consumer/workflow 内存 authority 或完整 equivalence。

本机 5 nm reproduction 相对 inherited peak 增加 `0.192890167 GiB (+0.2410%)`，快 `1768.885 s (17.47%)`；这是跨 run 可比较的结果，不是同一 workflow 的相加项。

## 未运行矩阵

| 项目 | status | 原因 |
|---|---|---|
| 3 nm M1200、M1600、p6/h2.5、p6/h2 | `not_run` | `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |
| 全部 2 nm | `not_run` | `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |
| 3 nm Gate 后续 MPI1 | `not_run` | `NOT_RUN_DUE_TO_3NM_M800_PHYSICS_GATE` |
| 3 nm official RTA、grid/M convergence | `unavailable/not_run` | retry own physics Gate未通过 |

## §15 问题回答

1. 5 nm MPI1 与 MPI8：equivalence not established；source-only comparison 触发 REFERENCE_SOURCE_SEMANTICS_CHANGED。
2. 5 nm MPI1 packet、consumer、完整 workflow峰值：NA；最后 attempt 未形成合格 authority。
3. 相对 80.025856018 GiB：NA；没有合格 MPI1 workflow peak。
4. 3 nm 最小资格 M：NA；M800 own physics失败，M1200未运行。
5. 3 nm h3/h2.5/h2：无 mesh convergence 结论。
6. 2 nm 最小资格 M：NA。
7. 2 nm mesh convergence：not_run。
8. 1.50 TiB 下最细完成网格：只有 3 nm p6/h3/M800 candidate，不是 accuracy-qualified。
9. 最大内存对象：实测主导为两侧 MUMPS factors；modal rank1600的单个 Schur/constraint/LU 各 40960000 B。
10. 0.7 nm：这是推断而非正式容量外推；3 nm 未 accuracy-qualified，不能给出正式 0.7 nm capacity 结论，但 213–255 GiB 且 factor 主导说明仍需要 Task040 factor-free scalable architecture。

merge approval=`NO`；raw roots、diagnostic checkpoint、negative authority 和未运行项保留。
