# Task033 内存预测与启动决策

## 1. Effective limits

| Limit | Nominal Task033 | Effective Task033 | Unit | 数据身份 | 证据 |
|---|---:|---:|---|---|---|
| hard upper | 14.000 | 13.6485 | GiB | measured/derived | `environment_and_base.md` |
| center/warning | 11.500 | 11.2113 | GiB | derived by preserved ratio | same |
| conservative upper | 12.800 | 12.4786 | GiB | derived by preserved ratio | same |
| controlled termination | 13.000 | 12.6736 | GiB | derived by preserved ratio | same |

The effective column preserves each task-book fraction of the hard budget and applies it to
the smaller Docker Engine memory total. `memory.max=max` does not override the smaller
numeric Docker VM ceiling.

## 2. Launch contract

| Check | Required condition | 当前状态 | 数据身份 | Action on failure |
|---|---|---|---|---|
| tracked source | clean commit and captured SHA | not_run | not_run | do not launch formal record |
| center predictions | two independent centers `<=11.2113 GiB` | not_run | not_run | `not_run_by_memory_gate` |
| conservative upper | `<=12.4786 GiB` | not_run | not_run | `not_run_by_memory_gate` |
| host available memory | refreshed and sufficient for declared safety margin | current Phase0 snapshot only 1.811 GiB free | measured snapshot | no large launch now |
| swap | disabled / zero use for formal case | not_run | not_run | terminate / reject record |
| watchdog | warning 11.2113; terminate 12.6736 GiB | not_run | not_run | do not launch without watchdog |
| concurrency | one large case at a time | not_run | not_run | serialize launches |

## 3. Candidate decisions

| Candidate group | Prediction | Launch decision | Current status | 数据身份 | Evidence |
|---|---|---|---|---|---|
| pure 3D microfixtures | pending implementation scale estimate | pending | not_run | not_run | Case090 pending |
| uniform p/h matrix | pending two-method prediction | pending | not_run | not_run | `uniform_p_h_matrix.csv` |
| adaptive p2 h5/h3 | pending mechanism and prediction Gate | pending | not_run | not_run | `adaptive_compression.csv` |
| conditional/locked large combinations | no prediction yet | do_not_run | not_run pending Gate | not_run | task matrix policy |

No numerical memory prediction has been produced and no large candidate has been launched.

