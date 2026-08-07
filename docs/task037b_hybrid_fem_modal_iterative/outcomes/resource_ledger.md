# Task037b H1 resource ledger

## 口径

本次峰值是 H1 whole-job 在 mode classification 阶段的同步过程树峰值，不是成功 Hybrid 求解的内存需求预测。watchdog authority 使用同时存活 MPI worker 的 RSS 总和；PSS、USS 和 swap 单独记录，不能互相替代。

| 指标 | 实测值 |
|---|---:|
| wall time | 约 49.54 s |
| process-tree / worker RSS peak | 2647.4375 MiB |
| authority peak | 2.58538818359375 GiB |
| worker PSS peak | 1761.02734375 MiB |
| worker USS peak | 1637.375 MiB |
| process-tree swap peak | 0 |
| worker smaps swap | 0 |
| warning threshold | 12 GiB，未触发 |
| termination threshold | 16 GiB，未触发 |
| timeout | 1800 s，未触发 |
| memory authority gate | pass |

## 阶段

| 阶段 | progress elapsed |
|---|---:|
| cross_section_eigen_assembly | 0.00018878397531807423 s |
| cross_section_eigen_solve | 2.219110075966455 s |
| mode_classification | 12.238622940029018 s |
| timeline 最后可读样本 | 49.54167506797239 s |

进程在 mode classification 失败后由 MPI 正常收口；没有残留 worker，没有受控内存终止，也没有 swap 压力。

raw JSON 字段名虽含 max_*_mb，但这些数值由 bytes/1024^2 换算，本文统一显示为 MiB；authority 峰值保持 GiB。

## 证据

| 文件 | SHA256 |
|---|---|
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8.json | 2e03dd105665de6a7ad9d796de7dad7117cf803483d0ad4de8da6dd2480b246b |
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/worker_stdout.txt | eb03b75b5fba69bcf8e0304903d95b98286ac2756916749180cde99d851fe28e |
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/memory_timeline.csv | 79ed75dfd7b57fbbc20f9ff0e73749fbfa52ce1d694c2760d6ddf82239418259 |
| ../../../benchmarks/artifacts/task037b/h1_direct_authority_3f72ef3_mpi8/memory_stages.jsonl | 4e35d04896a04d1640438afa0b8241af0a765a3c093b238b464ad7a1dae4193e |

## Post-fix successful solve（2990f357）

首次 classification 失败的 `2.58538818359375 GiB` authority 峰值保留为历史证据；它不是成功 Hybrid solve 的峰值。post-fix formal 在同一冻结 H1 物理条件下完成有效求解，以下为 process-tree/worker simultaneous authority 与原始 timing 字段。

| 指标 | post-fix 实测值 |
|---|---:|
| process-tree RSS peak | 7934.6484375 MiB |
| worker RSS peak | 7926.7109375 MiB |
| worker PSS peak | 6186.951171875 MiB |
| worker USS peak | 5912.7421875 MiB |
| process-tree / worker swap | 0 / 0 |
| worker timing total | 314.0315530579537 s |
| timeline 最后可读 elapsed | 316.6363581159385 s |
| bottom/top streaming recovery | 4.041541184997186 / 3.7041287679458037 s |
| sequential recovery sum | 7.74566995294299 s |

### Post-fix 阶段耗时

| 阶段 | seconds |
|---|---:|
| cross_section_and_qep_assembly | 3.0135245269630104 |
| positive_and_negative_biorthogonal_bases | 52.7131977280369 |
| two_local_fem_dtn_systems | 167.3979164250195 |
| internal_modal_coupling | 47.298344147973694 |
| primary_system_build | 1.4724921690067276 |
| monolithic_assembly | 1.4724921690067276 |
| rta_evaluation | 0.02579140500165522 |
| physical_field_reconstruction | 22.055879381950945 |
| total | 314.0315530579537 |

### Post-fix stage process-tree RSS peaks

| 阶段 | MiB |
|---|---:|
| process_start | 1623.324 |
| cross eigen assembly | 1806.195 |
| cross eigen solve | 2510.660 |
| mode classification | 2605.527 |
| local FEM | 5195.578 |
| interface | 5848.668 |
| augmented factor | 7585.594 |
| official RTA | 7585.598 |
| middle | 7812.992 |
| full3d oracle | 7589.258 |
| record/release | 7934.648 |

post-fix summary 与 solver record 仍为 Git ignored artifact；tracked docs 只保存 hash-bound 引用：summary `e22aa1edfeab331d5a8be13ca085e029d5446a4fdf300a5787a00688ef700db2`，solver `290fc25c119bbf641b8f0277ed5f9a101bc11a4df898c9133509f53c56dd4a1c`，timeline `26aee5647d93d4d5e9657b6a00f63fed98ffb83347506fb7bc8ed82bbbbbb9a6`，stages `a30d7cd52385f5940ac23b90297e85bb7f23dab64e6964f640c3aed3e096dab5`。
