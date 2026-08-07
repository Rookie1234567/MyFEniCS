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
