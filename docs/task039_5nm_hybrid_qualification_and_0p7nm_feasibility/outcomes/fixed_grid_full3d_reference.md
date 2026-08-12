# T3：5 nm p6/h10 Full3D direct fixed-grid authority

本页记录 Task39 唯一 T3 Full3D direct MPI8 锚点。静态凝聚是先在每个单元
内部消去局部未知量，再把较小的界面系统装配到全局；直接法则对这个系统
做一次 MUMPS 因子分解并回代。它们改变计算流程和内存分布，不改变 Maxwell
方程。canonical vector 是按稳定自由度 key 保存的场值包，用来让后续
Full3D/Hybrid 比较同一物理位置；manifest 和 rank shard 只保存身份与复核所需
的完整分片信息。

## 1. 三次尝试

| attempt | raw run | 结果 | 保留边界 |
| --- | --- | --- | --- |
| a | results/task039_5nm_full3d_direct/.../20260812T193248.147644Z | configuration_input_failure | 旧显式 probe=110/10 与新 block 不相容；不是数值 authority |
| b | results/task039_5nm_full3d_direct/.../20260812T195748.825443Z | 数值/RSS 通过但 evidence incomplete | 缺 canonical vectors、PSS/USS；不覆盖 a |
| c | results/task039_5nm_full3d_direct/.../20260812T204543.545080Z | T3_FULL3D_DIRECT_AUTHORITY_ESTABLISHED | 本页及 compact record 的唯一最终 T3 authority |

详细字段、33 条 significant channel 和 16 个 canonical shard 的逐项 SHA 见
[T3 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t3_full3d_direct_mpi8_v1.json)。

## 2. 身份、网格与 A1 Gate

| 项目 | 实测值/判定 |
| --- | --- |
| source/input/resolved/physical | 76b6d6c08769496b60139797b2b9ab7849810964 / e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6 / 5e755e7499ada74c5cb5ec33a26afd87ba46820914d0c8bfddbe5bc387bb56bf / db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a |
| 物理身份 | 5 nm、p6/h10、S、grazing=10°/theta=80°、phi=0°、MPI8 |
| direct solve | pass；official_result=true、KSP converged |
| relative residual | 3.512831334578471e-11 <= 1e-9 |
| R/T/A/A_volume | 0.9094973679084956 / 0.0008705857370571771 / 0.08963204635444727 / 0.08963204635549822 |
| energy closure | 1.0509371151101732e-12 <= 1e-5 |
| unique propagating keys | 604/604 unique，pass |
| selected E/H | z=10/30/60/90/110 nm 全部存在，pass |
| process-tree telemetry | measured，920 attempted / 918 complete，pass |
| swap | 0 MiB，pass |

网格/线性代数规模为 252 cells、full DoF 173802、active trace rows 51192、
condensed rows 51796、external auxiliary rows 604；condensed matrix NNZ
43,283,050 used / 47,719,324 allocated，MUMPS factor NNZ 217,041,864。

## 3. 动态外部通道与后处理

唯一动态 DtN 文件有 604 条 order：bottom/top=300/304，S/P=302/302，
每侧为 150/150 与 152/152，604 条均 propagating，Rayleigh warning=0，zero
order 保留。50 条的 reporting 文件由 2×2 bound 产生，只是报告集合，不能代替
604 条 PDE mode selection。

以 incident power 归一化的 power_ratio >= 1e-8 significant 集合共有 33 条
（bottom 17、top 16）；每条的 key、ratio、R/T 和 outgoing amplitude 已逐条
写入 compact record。原始全量文件：

results/task039_5nm_full3d_direct/.../20260812T204543.545080Z/numerical_output/dtn_port_diffraction_orders_3d.json

SHA256 为 6d2ed0911a07b0fde09892e553fb7ed5c15aeec5d0b04653967e2f81ac7185a0。

## 4. Selected E/H 与 canonical

Selected archive 的 JSON/NPZ SHA 分别为
cb5da8a6c4887c5c4b4f3c050a76d1916d3648e40a1a6f43e5a7f00f32fd198a /
1602c66efcb69c070dbc2d71ba6e0166d269a10068fe017139c597c1d5edf681，shape 为
[5,20,40,3]，4000 points，z 为 10、30、60、90、110 nm。

| z (nm) | max abs(E) (V/m) | max abs(H) (A/m) |
| ---: | ---: | ---: |
| 10 | 0.03070066880223171 | 0.00007104643950481691 |
| 30 | 0.029365351134436467 | 0.00007465564592881413 |
| 60 | 0.03523485649078416 | 0.00008632105441161256 |
| 90 | 0.08880291901307337 | 0.00024756387697772326 |
| 110 | 0.41793512732453364 | 0.0012229082784090302 |

Canonical export 的两个角色均完成：

| role | manifest SHA | packet sum | rank shards |
| --- | --- | ---: | ---: |
| active_trace | f6603ab7e648bf3facf9de46b545f57ddc6eecebbf0d0d814236a3bee30d6b84 | 60402 | 8 |
| full_fe | 2b32c23b457d2e5edd3befa159a28ca97b93babf67dfec0ea4588998b820e0a5 | 173802 | 8 |

每个 rank shard 的实际 SHA 均与对应 manifest 相等，packet sum 与 manifest
global count 相等；逐项 filename/SHA/count/schema/duplicates 见 compact record。

## 5. 时间、资源与边界

| 阶段 | 秒 |
| --- | ---: |
| DtN assembly | 91.268220 |
| KSP setup/factor phase | 129.608784 |
| KSP solve | 0.199135 |
| postprocess | 8.928812 |
| numerical elapsed | 283.036048 |
| outer run wall | 290.480347 |

资源 measured 值详见 [resource ledger](resource_ledger.md)：

| simultaneous RSS peak | PSS peak | USS peak | swap |
| ---: | ---: | ---: | ---: |
| 15965.453125 MiB | 13932.458984375 MiB | 13611.3515625 MiB | 0 MiB |

p6/h10 是 algorithmic stress anchor，h/lambda=2；它证明本 profile 的执行和
authority 接线，不是 5 nm 网格收敛或 continuum 精度结论。T4 Full3D iterative、
T5/T6 Hybrid 仍未运行，本页不提前宣称跨方法准确性。
