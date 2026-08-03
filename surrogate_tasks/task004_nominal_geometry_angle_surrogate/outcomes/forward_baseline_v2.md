# M2R：五个 forward anchors

旧数学/离散参考仍是 Case119 的 Ny4/p5；本轮只替换执行身份为
clean-SHA `fdf961545f217d620e22800f2704ae9913a6d270` 加显式
`ICNTL(14)=40`。几何、网格 `(6,4,14)`、N1curl p5、observable-v3、MPI2
和物理参数没有改变，旧记录没有混入新训练数据。

五个固定 anchor 均使用一个 fresh process，actual ICNTL(14)=40，完整
direct solve、runtime topology、功率账本和 zero-swap Gate 全部通过。

| grazing | azimuth | aggregate max abs | shared power max abs | shared amplitude max abs | residual |
|---:|---:|---:|---:|---:|---:|
| 0.5 | 0 | `8.88e-16` | `3.59e-16` | `2.88e-15` | `2.85e-11` |
| 0.5 | 90 | `2.22e-15` | `7.77e-16` | `1.62e-15` | `1.68e-11` |
| 10 | 0 | `1.12e-14` | `1.10e-14` | `5.66e-15` | `5.46e-12` |
| 10 | 90 | `1.17e-14` | `1.17e-14` | `1.65e-14` | `3.81e-12` |
| 5.25 | 45 | `4.33e-15` | `2.22e-15` | `3.04e-15` | `1.28e-11` |

比较器的固定 Gate 是 aggregate ≤1e-10、shared order power ≤1e-10、shared
complex amplitude ≤1e-9，以及 order/wavevector/mask/dispersion identity
完全一致；五点全部通过。新的 forward baseline JSON 位于
`outcomes/TASK004_FORWARD_BASELINE_v2.json`，原始比较证据位于
`benchmarks/artifacts/cases/124_task004_mumps_workspace_and_anchor_requalification/forward_baseline_v2.json`。
