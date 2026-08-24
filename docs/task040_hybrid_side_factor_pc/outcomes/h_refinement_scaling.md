# T40-12 conditional h3 scaling

## Status: not_run_by_v3_2_numerical_gate

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
