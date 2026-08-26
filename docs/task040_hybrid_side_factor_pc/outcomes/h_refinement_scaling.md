# T40-12 conditional h3 scaling

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权 h3/p6 scaling；不是 scaling 算法失败。

## Review V4 历史状态

T40-12 的 p6/h3 bottom scaling probe 只有在 h4 scalable candidate 通过数值和资源 Gate
后才允许启动。T40-3 transmission mechanism 未通过，所以没有 h3 DoF、PC retained bytes、
memory exponent、RSS、wall 或 swap 观测，也没有 0.7 nm 外推。

## V1-8 收口

V1-7 h3 scaling 仍为 `not_run_by_gate`。没有生成 h3 DoF、retained-byte exponent、RSS、wall
或 0.7 nm 外推；最新 V1-2 组件硬停止不能作为 scaling 测点。

## V2-G 收口

V2-F h3 scaling 为 `not_run_by_gate`。V2-B2 数值 Gate 已失败，没有 h3 DoF、retained-byte
exponent、RSS/wall scaling 或 0.7 nm 外推。

## V3-7 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span residual 未通过，未运行 bounded coarse、
h3 或 0.7 nm scaling；没有新的 DoF、retained-byte、RSS、wall 或近线性内存证据。

## Review V4 历史收口

`not_run_by_v4_1_identity_gate`。V4-9/V4-10 的 h3、p6 和 0.7 nm scaling 没有启动；没有
DoF、retained bytes、rank、rows、RSS、wall、swap 或内存增长数据，也没有 convergence claim。
V4-1 在 system/F/Vec/factor 之前因 canonical source-row bridge 缺失而受控停止，这不是
h-refinement 或 scaling 算法失败。详见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

h3/p6 scaling probe 与 0.7 nm-oriented scaling 均未运行，状态为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。没有 DoF、retained bytes、
memory exponent、rank、RSS/wall scaling 或 convergence 数据。Route C 的 h4 screen 不足以
外推 h3，更不能代替 0.7 nm PDE。
