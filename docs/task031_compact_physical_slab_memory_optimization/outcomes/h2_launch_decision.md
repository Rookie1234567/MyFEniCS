# h2 条件解锁决定

| Gate | 观测 | 结果 |
|---|---:|---|
| h5 full numeric pass | full `9.959903e-7` + official RTA | pass |
| h3 full numeric pass | full `9.973853e-7` + official RTA | pass |
| h3 reduction vs Task030 | 8.39897% | pass (`>=8%`) |
| affine central prediction | 8.50113 GiB | pass (`<=8.8`) |
| ratio-transfer prediction | 8.58735 GiB | pass (`<=8.8`) |
| conservative upper | 9.44653 GiB | pass (`<=10.0`) |
| same exact condensation / modes | exact `F-C H^-1D`, n_aux=80 | pass |
| h3 swap | 0 pages | pass |
| clean source | full SHA `45a0fc6e...` attested | pass |
| ordinary default | unchanged | pass |
| watchdog | 9.5 GiB warn / 11 GiB terminate | enabled |

决定：`RUN_H2=true`，只放行一个最佳综合候选；不放行第二候选。最终 h2 1977 步收敛，external worker peak 7.897675 GiB，warning/termination 均 false，swap=0，验证了解锁决定。
