# 继承基线与本机复现权威

Task041 必须分开引用 Task039 继承基线和本机 MPI8 复现；后者不是前者的改写。

## Task039 继承基线

原 record：`benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json`。

| 字段 | 值 |
|---|---|
| source SHA | `9e31ecf189081afcb8ca27b0374ec89af0094e2d` |
| input SHA | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| configuration | 5 nm / p6h4 / M480 / MPI8 exact-side Hybrid iterative |
| peak / wall / swap | `80.0258560180664 GiB` / `10126.231902 s` / `0` |
| five residuals（reported/global/bottom/modal/top） | `3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10` |
| full numerical / recovery / physics | `PASS / PASS / PASS` |

该 record 是 MPI1 比较所用的历史 authority，不是本机执行的 resource measurement。

## Task041 本机 MPI8 复现

root：`results/task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf`。

| 字段 | 值 |
|---|---|
| source / input / physical / resolved SHA | `def547cfd139b6377b0cae2ba1736ec3591814b0` / `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` / `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` / `d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798f` |
| peak / elapsed / swap | `80.2187461853 GiB` / `8357.347033 s` / `0` |
| five residuals（reported/global/bottom/modal/top） | `2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10` |
| R / T / A_balance / A_volume | `0.7331842733894981 / 0.00022009869572663576 / 0.26659562791477526 / 0.2665962726231523` |
| solve / recovery / physics | `PASS / PASS / PASS` |

相对继承基线，本机复现 peak 增加 `0.192890167 GiB`（`+0.2410%`），快 `1768.885 s`（`17.47%`）。这是用户授权的本机复现，不能标记为原 Task039 run。

## 解释边界

本机 source-only 检查 root=`task041_s1_source_only_p6h4_m480_mpi1_6ae90799`，source=`6ae907991ceb3323c06b351d13a9557685e4d713`：keys、roundtrip、repeat 通过，但 current-vs-persisted 差=`3.826978841496932e-9`>`1e-12`，分类=`REFERENCE_SOURCE_SEMANTICS_CHANGED`。旧 MPI8 authority 保留；corrected MPI1 不得据此声明完整 MPI 等价。

Task040 experimental side PC 不是上述两套 authority 的算法身份，也不改变 ordinary defaults。
